"""Rutas /api/* consumidas por el agente de ElevenLabs."""

import hmac
import logging
import os
import sqlite3
import unicodedata
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from app import db
from app.models import (
    Categoria,
    Estado,
    EstadoUpdate,
    HealthResponse,
    Pedido,
    PedidoIn,
    PedidosResponse,
    ProblemaItem,
    ProductosResponse,
    Producto,
    ResetResponse,
)

logger = logging.getLogger("tienda")

ZONA_COLOMBIA = ZoneInfo("America/Bogota")
TIEMPO_RECOGER = "20 a 30 minutos"


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    esperada = os.environ.get("API_KEY", "")
    if not x_api_key or not hmac.compare_digest(x_api_key.encode(), esperada.encode()):
        raise HTTPException(401, {"error": "no_autorizado", "mensaje": "API key inválida"})


router_publico = APIRouter(prefix="/api")
router = APIRouter(prefix="/api", dependencies=[Depends(require_api_key)])


def normalizar(texto: str) -> str:
    """Minúsculas y sin tildes, para búsquedas tolerantes al ASR."""
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c)
    )
    return sin_tildes.lower().strip()


def tiempo_estimado(modalidad: str) -> str:
    if modalidad == "domicilio":
        return str(db.get_negocio()["domicilio"]["tiempo_estimado"])
    return TIEMPO_RECOGER


def con_tiempo(pedido: dict[str, Any]) -> dict[str, Any]:
    return {**pedido, "tiempo_estimado": tiempo_estimado(pedido["modalidad"])}


@router_publico.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(ok=True)


@router.get("/negocio")
def negocio() -> dict[str, Any]:
    return db.get_negocio()


@router.get("/productos", response_model=ProductosResponse)
def listar_productos(
    q: str | None = None,
    categoria: Categoria | None = None,
    solo_disponibles: bool = False,
    conn: sqlite3.Connection = Depends(db.get_db),
) -> ProductosResponse:
    rows = db.fetch_productos(conn, categoria)
    productos = [db.producto_a_dict(r) for r in rows]
    if q and q.strip():
        termino = normalizar(q)
        alias_por_id = {r["id"]: r["alias"] for r in rows}
        productos = [
            p
            for p in productos
            if termino in normalizar(p["nombre"]) or termino in normalizar(alias_por_id[p["id"]])
        ]
    if solo_disponibles:
        productos = [p for p in productos if p["disponible"]]
    return ProductosResponse(productos=productos, total=len(productos))


@router.get("/productos/{producto_id}", response_model=Producto)
def obtener_producto(
    producto_id: str, conn: sqlite3.Connection = Depends(db.get_db)
) -> dict[str, Any]:
    row = db.fetch_producto(conn, producto_id)
    if row is None:
        raise HTTPException(
            404,
            {"error": "producto_no_encontrado", "mensaje": f"No existe el producto '{producto_id}'"},
        )
    return db.producto_a_dict(row)


def pedido_o_404(conn: sqlite3.Connection, numero: str) -> dict[str, Any]:
    pedido = db.fetch_pedido(conn, numero)
    if pedido is None:
        raise HTTPException(
            404, {"error": "pedido_no_encontrado", "mensaje": f"No existe el pedido '{numero}'"}
        )
    return pedido


def siguiente_numero(conn: sqlite3.Connection) -> str:
    ultimo = conn.execute("SELECT MAX(CAST(SUBSTR(numero, 4) AS INTEGER)) FROM pedidos").fetchone()[0]
    return f"TC-{(ultimo or 0) + 1:04d}"


@router.post("/pedidos", response_model=Pedido, status_code=201)
def crear_pedido(pedido: PedidoIn, conn: sqlite3.Connection = Depends(db.get_db)) -> dict[str, Any]:
    negocio_info = db.get_negocio()
    cantidades: dict[str, int] = {}
    for item in pedido.items:
        cantidades[item.producto_id] = cantidades.get(item.producto_id, 0) + item.cantidad

    conn.execute("BEGIN IMMEDIATE")
    try:
        inexistentes: list[ProblemaItem] = []
        sin_stock: list[ProblemaItem] = []
        filas: dict[str, sqlite3.Row] = {}
        for producto_id, cantidad in cantidades.items():
            row = db.fetch_producto(conn, producto_id)
            if row is None or not row["activo"]:
                inexistentes.append(
                    ProblemaItem(producto_id=producto_id, nombre=None, solicitado=cantidad, disponible=0)
                )
            elif row["stock"] < cantidad:
                sin_stock.append(
                    ProblemaItem(
                        producto_id=producto_id,
                        nombre=row["nombre"],
                        solicitado=cantidad,
                        disponible=row["stock"],
                    )
                )
            else:
                filas[producto_id] = row

        if inexistentes:
            raise HTTPException(
                404,
                {
                    "error": "producto_no_encontrado",
                    "mensaje": f"No existe(n) {len(inexistentes)} producto(s)",
                    "problemas": [p.model_dump() for p in inexistentes],
                },
            )
        if sin_stock:
            raise HTTPException(
                409,
                {
                    "error": "stock_insuficiente",
                    "mensaje": f"No hay stock suficiente para {len(sin_stock)} producto(s)",
                    "problemas": [p.model_dump() for p in sin_stock],
                },
            )

        numero = siguiente_numero(conn)
        creado_en = datetime.now(ZONA_COLOMBIA).isoformat(timespec="seconds")
        subtotal = sum(filas[pid]["precio"] * cant for pid, cant in cantidades.items())
        costo_domicilio = (
            int(negocio_info["domicilio"]["costo"]) if pedido.modalidad == "domicilio" else 0
        )
        conn.execute(
            """
            INSERT INTO pedidos
                (numero, cliente, telefono, modalidad, direccion, notas,
                 subtotal, costo_domicilio, total, estado, creado_en)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'recibido', ?)
            """,
            (
                numero,
                pedido.cliente,
                pedido.telefono,
                pedido.modalidad,
                pedido.direccion,
                pedido.notas,
                subtotal,
                costo_domicilio,
                subtotal + costo_domicilio,
                creado_en,
            ),
        )
        for producto_id, cantidad in cantidades.items():
            row = filas[producto_id]
            conn.execute(
                "UPDATE productos SET stock = stock - ? WHERE id = ?", (cantidad, producto_id)
            )
            conn.execute(
                """
                INSERT INTO pedido_items
                    (pedido_numero, producto_id, nombre_producto, cantidad, precio_unitario, subtotal)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (numero, producto_id, row["nombre"], cantidad, row["precio"], row["precio"] * cantidad),
            )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    creado = pedido_o_404(conn, numero)
    logger.info("pedido %s total=%s items=%s", numero, creado["total"], len(creado["items"]))
    return con_tiempo(creado)


@router.get("/pedidos", response_model=PedidosResponse)
def listar_pedidos(
    estado: Estado | None = None,
    limite: int = Query(default=20, ge=1, le=100),
    conn: sqlite3.Connection = Depends(db.get_db),
) -> PedidosResponse:
    pedidos = [con_tiempo(p) for p in db.fetch_pedidos(conn, estado, limite)]
    return PedidosResponse(pedidos=pedidos, total=len(pedidos))


@router.get("/pedidos/{numero}", response_model=Pedido)
def obtener_pedido(numero: str, conn: sqlite3.Connection = Depends(db.get_db)) -> dict[str, Any]:
    return con_tiempo(pedido_o_404(conn, numero))


@router.patch("/pedidos/{numero}", response_model=Pedido)
def actualizar_estado(
    numero: str, cambio: EstadoUpdate, conn: sqlite3.Connection = Depends(db.get_db)
) -> dict[str, Any]:
    conn.execute("BEGIN IMMEDIATE")
    try:
        pedido = pedido_o_404(conn, numero)
        actual = pedido["estado"]
        if actual == "cancelado":
            raise HTTPException(
                409,
                {
                    "error": "pedido_cancelado",
                    "mensaje": f"El pedido {numero} está cancelado y no se puede modificar",
                },
            )
        if cambio.estado == "cancelado":
            if actual == "entregado":
                raise HTTPException(
                    409,
                    {
                        "error": "pedido_entregado",
                        "mensaje": f"El pedido {numero} ya fue entregado y no se puede cancelar",
                    },
                )
            for item in pedido["items"]:
                conn.execute(
                    "UPDATE productos SET stock = stock + ? WHERE id = ?",
                    (item["cantidad"], item["producto_id"]),
                )
        conn.execute("UPDATE pedidos SET estado = ? WHERE numero = ?", (cambio.estado, numero))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return con_tiempo(pedido_o_404(conn, numero))


@router.post("/admin/reset", response_model=ResetResponse)
def reset(conn: sqlite3.Connection = Depends(db.get_db)) -> ResetResponse:
    return ResetResponse(ok=True, productos_cargados=db.reset_demo(conn))
