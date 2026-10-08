"""Conexión SQLite, esquema, seed y consultas compartidas."""

import json
import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any

RAIZ = Path(__file__).resolve().parent.parent
SEED_PATH = RAIZ / "seed_productos.json"

SCHEMA = """
CREATE TABLE IF NOT EXISTS productos (
    id TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    categoria TEXT NOT NULL CHECK (categoria IN ('avicola', 'tipicos')),
    presentacion TEXT NOT NULL,
    unidad TEXT NOT NULL,
    precio INTEGER NOT NULL,
    stock INTEGER NOT NULL,
    alias TEXT NOT NULL,
    descripcion TEXT NOT NULL,
    activo INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS pedidos (
    numero TEXT PRIMARY KEY,
    cliente TEXT NOT NULL,
    telefono TEXT NOT NULL,
    modalidad TEXT NOT NULL CHECK (modalidad IN ('domicilio', 'recoger')),
    direccion TEXT,
    notas TEXT,
    subtotal INTEGER NOT NULL,
    costo_domicilio INTEGER NOT NULL,
    total INTEGER NOT NULL,
    estado TEXT NOT NULL DEFAULT 'recibido'
        CHECK (estado IN ('recibido', 'en_preparacion', 'entregado', 'cancelado')),
    creado_en TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pedido_items (
    id INTEGER PRIMARY KEY,
    pedido_numero TEXT NOT NULL REFERENCES pedidos(numero),
    producto_id TEXT NOT NULL REFERENCES productos(id),
    nombre_producto TEXT NOT NULL,
    cantidad INTEGER NOT NULL,
    precio_unitario INTEGER NOT NULL,
    subtotal INTEGER NOT NULL
);
"""


def get_db_path() -> Path:
    return Path(os.environ.get("DB_PATH", "./data/tienda.db"))


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path(), check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db() -> Iterator[sqlite3.Connection]:
    """Dependencia FastAPI: una conexión por request."""
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


def load_seed() -> dict[str, Any]:
    with SEED_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def get_negocio() -> dict[str, Any]:
    return load_seed()["negocio"]


def seed_productos(conn: sqlite3.Connection) -> int:
    productos = load_seed()["productos"]
    conn.executemany(
        """
        INSERT INTO productos
            (id, nombre, categoria, presentacion, unidad, precio, stock, alias, descripcion, activo)
        VALUES (:id, :nombre, :categoria, :presentacion, :unidad, :precio, :stock, :alias, :descripcion, 1)
        """,
        [{**p, "alias": json.dumps(p["alias"], ensure_ascii=False)} for p in productos],
    )
    return len(productos)


def init_db() -> None:
    """Crea la carpeta y el esquema; carga el seed si no hay productos."""
    get_db_path().parent.mkdir(parents=True, exist_ok=True)
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        vacia = conn.execute("SELECT COUNT(*) FROM productos").fetchone()[0] == 0
        if vacia:
            seed_productos(conn)
    finally:
        conn.close()


def reset_demo(conn: sqlite3.Connection) -> int:
    """Borra pedidos e ítems y recarga productos desde el seed. Devuelve productos cargados."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("DELETE FROM pedido_items")
        conn.execute("DELETE FROM pedidos")
        conn.execute("DELETE FROM productos")
        cargados = seed_productos(conn)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    return cargados


def producto_a_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "nombre": row["nombre"],
        "categoria": row["categoria"],
        "presentacion": row["presentacion"],
        "unidad": row["unidad"],
        "precio": row["precio"],
        "stock": row["stock"],
        "disponible": row["stock"] > 0,
        "descripcion": row["descripcion"],
    }


def fetch_productos(conn: sqlite3.Connection, categoria: str | None = None) -> list[sqlite3.Row]:
    sql = "SELECT * FROM productos WHERE activo = 1"
    params: list[str] = []
    if categoria:
        sql += " AND categoria = ?"
        params.append(categoria)
    return conn.execute(sql + " ORDER BY categoria, nombre", params).fetchall()


def fetch_producto(conn: sqlite3.Connection, producto_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM productos WHERE id = ?", (producto_id,)).fetchone()


def _items_por_pedido(conn: sqlite3.Connection, numeros: list[str]) -> dict[str, list[dict[str, Any]]]:
    items: dict[str, list[dict[str, Any]]] = {n: [] for n in numeros}
    if not numeros:
        return items
    marcas = ",".join("?" * len(numeros))
    rows = conn.execute(
        f"SELECT * FROM pedido_items WHERE pedido_numero IN ({marcas}) ORDER BY id", numeros
    ).fetchall()
    for r in rows:
        items[r["pedido_numero"]].append(
            {
                "producto_id": r["producto_id"],
                "nombre": r["nombre_producto"],
                "cantidad": r["cantidad"],
                "precio_unitario": r["precio_unitario"],
                "subtotal": r["subtotal"],
            }
        )
    return items


def _pedido_a_dict(row: sqlite3.Row, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "numero_pedido": row["numero"],
        "estado": row["estado"],
        "cliente": row["cliente"],
        "telefono": row["telefono"],
        "modalidad": row["modalidad"],
        "direccion": row["direccion"],
        "notas": row["notas"],
        "items": items,
        "subtotal": row["subtotal"],
        "costo_domicilio": row["costo_domicilio"],
        "total": row["total"],
        "creado_en": row["creado_en"],
    }


def fetch_pedido(conn: sqlite3.Connection, numero: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM pedidos WHERE numero = ?", (numero,)).fetchone()
    if row is None:
        return None
    return _pedido_a_dict(row, _items_por_pedido(conn, [numero])[numero])


def fetch_pedidos(
    conn: sqlite3.Connection, estado: str | None = None, limite: int = 20
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM pedidos"
    params: list[str | int] = []
    if estado:
        sql += " WHERE estado = ?"
        params.append(estado)
    sql += " ORDER BY creado_en DESC, numero DESC LIMIT ?"
    params.append(limite)
    rows = conn.execute(sql, params).fetchall()
    items = _items_por_pedido(conn, [r["numero"] for r in rows])
    return [_pedido_a_dict(r, items[r["numero"]]) for r in rows]
