"""Panel /admin: HTML estático y endpoints internos sin API key (solo demo)."""

import sqlite3
from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app import db
from app.models import AdminData, ResetResponse
from app.routes_api import con_tiempo

ADMIN_HTML = Path(__file__).resolve().parent / "static" / "admin.html"

router = APIRouter(prefix="/admin")


@router.get("", include_in_schema=False)
def panel() -> FileResponse:
    return FileResponse(ADMIN_HTML, media_type="text/html")


@router.get("/data", response_model=AdminData)
def data(conn: sqlite3.Connection = Depends(db.get_db)) -> AdminData:
    inventario = [db.producto_a_dict(r) for r in db.fetch_productos(conn)]
    pedidos = [con_tiempo(p) for p in db.fetch_pedidos(conn, limite=20)]
    return AdminData(inventario=inventario, pedidos=pedidos)


@router.post("/reset-ui", response_model=ResetResponse)
def reset_ui(conn: sqlite3.Connection = Depends(db.get_db)) -> ResetResponse:
    return ResetResponse(ok=True, productos_cargados=db.reset_demo(conn))
