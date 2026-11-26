# CLAUDE.md — convenciones del repo

Backend de inventario y pedidos para el agente de voz/chat de "Avícola Las Tres Cruces".
Las respuestas JSON las lee un agente de ElevenLabs y se las cuenta al cliente por teléfono:
mensajes claros, en español, sin ambigüedad. El brief original está en `BRIEF.md`.

## Stack (no negociable)

- Python 3.12, FastAPI, Uvicorn, Pydantic v2.
- SQLite con `sqlite3` de la stdlib. Sin ORM. Una conexión por request (`db.get_db`).
- Panel `/admin` es un único HTML con JS vanilla, sin build.
- Dependencias mínimas y pinneadas en `requirements.txt`.

## Estructura

```
app/main.py        app FastAPI, middleware CORS solo para /admin, handlers de error, lifespan
app/db.py          conexión, esquema, seed, reset y consultas compartidas (dicts listos para responder)
app/models.py      modelos Pydantic de request/response
app/routes_api.py  rutas /api/* (requieren X-API-Key, salvo /api/health)
app/admin.py       /admin (HTML), /admin/data, /admin/reset-ui (sin API key)
app/static/admin.html
seed_productos.json
tests/test_api.py
agent/             config exportada del agente de ElevenAgents (prompt, tools, tests). Si cambias
                   el agente en la plataforma, actualiza estos archivos. Nunca pongas valores de secretos.
```

## Cómo correr

```bash
source .venv/bin/activate
cp .env.example .env            # editar API_KEY
uvicorn app.main:app --reload   # http://localhost:8000/admin
pytest                          # usa DB temporal por test, no toca ./data
```

## Estilo

- Type hints en todo. Nada de `print`: usar `logging.getLogger("tienda")`.
- Claves JSON en español, snake_case. Errores siempre `{"error": "<codigo>", "mensaje": "<texto>"}`;
  se lanzan como `HTTPException(status, dict)` y `main.py` los serializa tal cual.
- Precios en COP, siempre `int`. Nunca floats.
- Fechas en `America/Bogota` con `zoneinfo`, ISO 8601 con offset.
- Búsqueda insensible a mayúsculas y tildes (`routes_api.normalizar`).
- Escrituras que tocan varias tablas van en `BEGIN IMMEDIATE` ... `COMMIT` con rollback en `except`.
- Los ítems de pedido guardan snapshot de `nombre_producto` y `precio_unitario`.
- Sin código muerto ni sobre-ingeniería: es un MVP de demo.

## Decisiones tomadas (ver también README)

- `tiempo_estimado`: para `domicilio` sale del seed; para `recoger` es la constante `TIEMPO_RECOGER`.
- Un pedido `cancelado` no se puede modificar; cancelar uno `entregado` da `409`.
- Ítems repetidos en un pedido se suman en una sola línea.
- El listado de productos solo muestra `activo = 1`; un producto inactivo no se puede pedir.
- CORS abierto solo bajo `/admin` (middleware `CORSSoloAdmin` en `main.py`).
