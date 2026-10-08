"""App FastAPI: routers, manejo de errores, CORS para /admin y arranque."""

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send

from app import admin, db, routes_api

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

ERRORES_HTTP = {404: "no_encontrado", 405: "metodo_no_permitido"}
MENSAJES_VALIDACION = {
    "missing": "Falta este campo",
    "greater_than_equal": "Debe ser mayor o igual a {ge}",
    "too_short": "Debe tener al menos {min_length} elemento(s)",
    "string_too_short": "No puede estar vacío",
    "literal_error": "Valor no permitido; opciones: {expected}",
    "int_parsing": "Debe ser un número entero",
    "int_type": "Debe ser un número entero",
    "string_type": "Debe ser texto",
    "json_invalid": "El cuerpo no es JSON válido",
}


def mensaje_validacion(error: dict[str, Any]) -> str:
    plantilla = MENSAJES_VALIDACION.get(error["type"])
    if plantilla is None:
        return str(error["msg"]).removeprefix("Value error, ")
    ctx = {k: str(v).replace(" or ", " o ") for k, v in error.get("ctx", {}).items()}
    return plantilla.format(**ctx)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    if not os.environ.get("API_KEY"):
        raise RuntimeError("Falta la variable de entorno API_KEY")
    db.init_db()
    yield


class CORSSoloAdmin:
    """Aplica CORS abierto únicamente a las rutas /admin/*."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self.cors = CORSMiddleware(app, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"].startswith("/admin"):
            await self.cors(scope, receive, send)
        else:
            await self.app(scope, receive, send)


app = FastAPI(title="Avícola Las Tres Cruces — Inventario y pedidos", lifespan=lifespan)
app.add_middleware(CORSSoloAdmin)
app.include_router(routes_api.router_publico)
app.include_router(routes_api.router)
app.include_router(admin.router)


@app.exception_handler(StarletteHTTPException)
async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    cuerpo: dict[str, Any]
    if isinstance(exc.detail, dict):
        cuerpo = exc.detail
    else:
        cuerpo = {"error": ERRORES_HTTP.get(exc.status_code, "error"), "mensaje": str(exc.detail)}
    return JSONResponse(status_code=exc.status_code, content=cuerpo, headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    detalles = [
        {
            "campo": "" if e["type"] == "json_invalid" else ".".join(str(p) for p in e["loc"][1:]),
            "mensaje": mensaje_validacion(e),
        }
        for e in exc.errors()
    ]
    mensaje = detalles[0]["mensaje"] if detalles else "Datos inválidos"
    if detalles and detalles[0]["campo"]:
        mensaje = f"{mensaje} (campo: {detalles[0]['campo']})"
    return JSONResponse(
        status_code=422,
        content={"error": "datos_invalidos", "mensaje": mensaje, "detalles": detalles},
    )
