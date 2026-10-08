# BRIEF — Backend de inventario y pedidos para "Avícola Las Tres Cruces"

## Contexto

Este backend es la fuente de verdad de inventario y pedidos para un agente de voz y chat
construido en ElevenAgents (ElevenLabs). El agente llamará estos endpoints como *webhook tools*,
así que las respuestas JSON tienen que ser claras, estables y en español: el agente las lee y se las
cuenta al cliente. Un error confuso aquí es un agente diciendo tonterías por teléfono.

Es un MVP de demostración con datos de prueba (`seed_productos.json`). Prioridad: que funcione
de punta a punta hoy, con código limpio y sin sobre-ingeniería.

## Stack (no negociable)

- Python 3.12, FastAPI, Uvicorn, Pydantic v2.
- SQLite con el módulo `sqlite3` de la librería estándar. Sin ORM.
- Sin frontend framework: el panel `/admin` es un solo HTML con JS vanilla.
- Dependencias mínimas en `requirements.txt`.
- Estructura:

```
app/
  main.py        # app FastAPI, routers, startup
  db.py          # conexión, schema, seed
  models.py      # modelos Pydantic (request/response)
  routes_api.py  # /api/*
  admin.py       # /admin (HTML) y endpoints de administración
  static/admin.html
seed_productos.json
requirements.txt
.env.example
Procfile         # web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
README.md        # corto por ahora, se amplía después
tests/test_api.py
```

## Configuración por variables de entorno

- `API_KEY` — obligatoria. Todas las rutas `/api/*` exigen header `X-API-Key: <API_KEY>`.
  Si falta o es incorrecta: `401 {"error": "no_autorizado", "mensaje": "API key inválida"}`.
- `DB_PATH` — ruta del archivo SQLite. Default `./data/tienda.db`. Crear la carpeta si no existe.
- `PORT` — lo inyecta la plataforma de despliegue. Default 8000.
- `.env.example` con los tres. Nunca commitear `.env`.

## Modelo de datos

**productos**
`id TEXT PK, nombre, categoria ('avicola'|'tipicos'), presentacion, unidad, precio INTEGER (COP),
stock INTEGER, alias TEXT (JSON array), descripcion, activo INTEGER default 1`

**pedidos**
`numero TEXT PK (formato TC-0001, TC-0002...), cliente, telefono, modalidad ('domicilio'|'recoger'),
direccion (nullable), notas (nullable), subtotal INTEGER, costo_domicilio INTEGER, total INTEGER,
estado ('recibido'|'en_preparacion'|'entregado'|'cancelado') default 'recibido',
creado_en TEXT (ISO 8601, hora de Colombia, UTC-5)`

**pedido_items**
`id INTEGER PK, pedido_numero FK, producto_id FK, nombre_producto, cantidad INTEGER,
precio_unitario INTEGER, subtotal INTEGER`

Guardar `nombre_producto` y `precio_unitario` en el ítem (snapshot) para que un pedido no cambie
si el precio cambia después.

## Seed

- Al arrancar, si la tabla `productos` está vacía, cargar `seed_productos.json` (campo `productos`).
- El bloque `negocio` del JSON se expone tal cual en `GET /api/negocio` (no se persiste, se lee del archivo).
- El costo de domicilio sale de `negocio.domicilio.costo`.

## Endpoints

Todos bajo `/api`, todos con `X-API-Key`. Respuestas siempre JSON, claves en español, snake_case.

### `GET /api/health`
Sin API key. `{"ok": true}`.

### `GET /api/negocio`
Devuelve el bloque `negocio` del seed.

### `GET /api/productos?q=&categoria=&solo_disponibles=`
- `q`: búsqueda insensible a mayúsculas y tildes contra `nombre` y `alias`. "huevos" debe encontrar
  tanto "Huevos criollos" como "Huevos AA". "hormigas" debe encontrar "Hormigas culonas".
- `categoria`: filtra por `avicola` o `tipicos`.
- `solo_disponibles=true`: excluye stock 0.
- Respuesta:

```json
{
  "productos": [
    {
      "id": "bocadillo-veleno-caja",
      "nombre": "Bocadillo veleño",
      "categoria": "tipicos",
      "presentacion": "caja de 24 unidades en hoja de bijao",
      "unidad": "caja",
      "precio": 14000,
      "stock": 25,
      "disponible": true,
      "descripcion": "..."
    }
  ],
  "total": 1
}
```

### `GET /api/productos/{id}`
Un producto. `404 {"error": "producto_no_encontrado", "mensaje": "No existe el producto 'x'"}`.

### `POST /api/pedidos`
Request:

```json
{
  "cliente": "Carlos Rueda",
  "telefono": "3001234567",
  "modalidad": "domicilio",
  "direccion": "Calle 36 # 20-15, Cabecera",
  "notas": "sin cebolla, timbre dañado",
  "items": [
    {"producto_id": "pollo-campesino", "cantidad": 1},
    {"producto_id": "bocadillo-veleno-caja", "cantidad": 2}
  ]
}
```

Reglas:
- `direccion` obligatoria si `modalidad == "domicilio"`; si falta: `422` con mensaje claro.
- `cantidad` entero >= 1.
- Validar TODOS los ítems antes de tocar stock. Si algún producto no existe o no hay stock
  suficiente, no se crea nada y se responde `409`:

```json
{
  "error": "stock_insuficiente",
  "mensaje": "No hay stock suficiente para 1 producto(s)",
  "problemas": [
    {"producto_id": "hormigas-culonas-100g", "nombre": "Hormigas culonas", "solicitado": 5, "disponible": 3}
  ]
}
```

  Producto inexistente → `404` con el mismo formato (`error: "producto_no_encontrado"`).
- Si todo está bien: en UNA transacción descontar stock, crear el pedido y los ítems.
  `costo_domicilio` = costo del seed si `modalidad == "domicilio"`, si no 0.
- Respuesta `201`:

```json
{
  "numero_pedido": "TC-0001",
  "estado": "recibido",
  "cliente": "Carlos Rueda",
  "modalidad": "domicilio",
  "direccion": "Calle 36 # 20-15, Cabecera",
  "items": [
    {"producto_id": "pollo-campesino", "nombre": "Pollo campesino entero", "cantidad": 1, "precio_unitario": 42000, "subtotal": 42000}
  ],
  "subtotal": 70000,
  "costo_domicilio": 5000,
  "total": 75000,
  "tiempo_estimado": "45 a 60 minutos",
  "creado_en": "2026-10-08T17:32:10-05:00"
}
```

### `GET /api/pedidos/{numero}`
Un pedido con sus ítems. `404` si no existe.

### `GET /api/pedidos?estado=&limite=20`
Últimos pedidos, más recientes primero.

### `PATCH /api/pedidos/{numero}`
Body `{"estado": "en_preparacion"}`. Solo cambia estado. Si se cancela un pedido en estado
`recibido` o `en_preparacion`, devolver el stock. Un pedido `entregado` no se puede cancelar (`409`).

### `POST /api/admin/reset`
Borra pedidos e ítems y recarga productos desde el seed. Para reiniciar la demo. Responde
`{"ok": true, "productos_cargados": 16}`.

## Panel `/admin` (sin API key, solo lectura; es una demo)

- Un solo archivo `app/static/admin.html`, JS vanilla, sin build.
- Dos tablas: **Inventario** (nombre, presentación, precio formateado como `$ 42.000`, stock) y
  **Pedidos** (número, hora, cliente, modalidad, total, estado, ítems resumidos).
- Se refresca solo cada 3 segundos con `fetch`. Para que el HTML pueda consultar sin exponer la
  API key, crear endpoints internos `GET /admin/data` que devuelven inventario + últimos 20 pedidos
  en una sola respuesta (sin API key).
- Stock <= 3 en ámbar, stock 0 en rojo. Pedido nuevo aparece arriba con un resaltado suave.
- Un botón "Reiniciar demo" que llama a `POST /admin/reset-ui`, el cual internamente hace lo mismo que
  `/api/admin/reset`. Pedir `confirm()` antes.
- Diseño limpio y sobrio: fondo claro, tipografía del sistema, una sola fuente de color (verde oscuro)
  para encabezados. Debe verse bien en una pantalla compartida en un video.

## Detalles que importan

- Precios siempre enteros en COP. Nada de floats.
- Normalizar tildes en la búsqueda (`unicodedata`), porque el ASR del agente a veces las omite.
- `creado_en` en hora de Colombia (`America/Bogota`), usar `zoneinfo`.
- Logging: una línea por pedido creado (`INFO pedido TC-0001 total=75000 items=2`).
- CORS: permitir todo (`*`) solo en `/admin/*`; `/api/*` no necesita CORS porque lo llama ElevenLabs servidor a servidor.
- Nada de `print`. Nada de código muerto. Type hints en todo.

## Tests (obligatorios antes de decir "listo")

`tests/test_api.py` con `pytest` + `TestClient`, usando una DB temporal:

1. `GET /api/productos` sin API key → 401.
2. `GET /api/productos?q=huevos` → devuelve 2 productos.
3. `GET /api/productos?q=hormiga` → encuentra "Hormigas culonas" (singular contra alias).
4. Crear pedido válido → 201, stock del producto bajó exactamente la cantidad pedida.
5. Pedido con stock insuficiente → 409, el stock NO cambió.
6. Pedido a domicilio sin dirección → 422.
7. Cancelar pedido → stock vuelve.
8. `POST /api/admin/reset` → stock vuelve al seed.

Correr los tests y además probar manualmente con `curl` los flujos 2, 4 y 5 contra el servidor
levantado con `uvicorn app.main:app --reload`, y mostrar las salidas.

## Al terminar

- `README.md` corto: qué es, cómo correr local (`pip install -r requirements.txt`, `.env`, `uvicorn`),
  lista de endpoints en una tabla. La sección de arquitectura y la integración con ElevenLabs se
  escriben después.
- Crear `CLAUDE.md` con las convenciones de este repo (stack, estructura, estilo, cómo correr tests)
  para sesiones futuras.
- Primer commit: `feat: backend de inventario y pedidos (FastAPI + SQLite)`.
