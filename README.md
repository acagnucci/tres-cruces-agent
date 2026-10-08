# Avícola Las Tres Cruces — backend de inventario y pedidos

API de inventario y pedidos para el agente de voz y chat de "Avícola Las Tres Cruces"
(ElevenAgents). Es la fuente de verdad de productos, stock y pedidos. El agente la consume
como *webhook tools*; las respuestas son JSON en español, pensadas para leerse al cliente.

Es un MVP de demostración con datos de prueba (`seed_productos.json`).

## Correr local

Requiere Python 3.12.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # editar API_KEY
uvicorn app.main:app --reload
```

Variables de entorno (`.env`, nunca se commitea):

| Variable  | Obligatoria | Default            | Descripción                                   |
|-----------|-------------|--------------------|-----------------------------------------------|
| `API_KEY` | sí          | —                  | Clave que exige el header `X-API-Key` en `/api/*` |
| `DB_PATH` | no          | `./data/tienda.db` | Archivo SQLite; la carpeta se crea sola       |
| `PORT`    | no          | `8000`             | Lo inyecta la plataforma de despliegue        |

Tests:

```bash
pytest
```

Panel de demo (solo lectura, sin API key): <http://localhost:8000/admin>

## Endpoints

Todos los `/api/*` salvo `/api/health` exigen `X-API-Key`. Sin ella o con clave incorrecta:
`401 {"error": "no_autorizado", "mensaje": "API key inválida"}`.

| Método  | Ruta                        | Qué hace                                                        |
|---------|-----------------------------|-----------------------------------------------------------------|
| `GET`   | `/api/health`               | `{"ok": true}`. Sin API key.                                    |
| `GET`   | `/api/negocio`              | Bloque `negocio` del seed (horario, zonas, costo de domicilio). |
| `GET`   | `/api/productos`            | Lista productos. Filtros: `q`, `categoria`, `solo_disponibles`. |
| `GET`   | `/api/productos/{id}`       | Un producto. `404` si no existe.                                |
| `POST`  | `/api/pedidos`              | Crea un pedido y descuenta stock en una transacción. `201`.     |
| `GET`   | `/api/pedidos`              | Últimos pedidos. Filtros: `estado`, `limite` (default 20).      |
| `GET`   | `/api/pedidos/{numero}`     | Un pedido con sus ítems. `404` si no existe.                    |
| `PATCH` | `/api/pedidos/{numero}`     | Cambia `estado`. Cancelar devuelve el stock.                    |
| `POST`  | `/api/admin/reset`          | Borra pedidos y recarga productos del seed.                     |
| `GET`   | `/admin`                    | Panel HTML de demo. Sin API key.                                |
| `GET`   | `/admin/data`               | Inventario + últimos 20 pedidos para el panel. Sin API key.     |
| `POST`  | `/admin/reset-ui`           | Igual que `/api/admin/reset`, para el botón del panel.          |

Errores de negocio en `POST /api/pedidos`:

| Código | `error`                  | Cuándo                                              |
|--------|--------------------------|-----------------------------------------------------|
| `404`  | `producto_no_encontrado` | Algún `producto_id` no existe. Lista en `problemas`. |
| `409`  | `stock_insuficiente`     | Algún ítem pide más que el stock. Lista en `problemas`. |
| `422`  | `datos_invalidos`        | Falta `direccion` en domicilio, `cantidad` < 1, etc. |

Si hay cualquier problema no se crea nada ni se toca el stock.

## Pendiente

Arquitectura e integración con ElevenLabs se documentan después.
