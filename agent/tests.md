# Tests del agente (ElevenAgents)

Cuatro tests adjuntos al agente en la plataforma. Última corrida: 26 nov 2026, 4/4 pasan.

| Test | Tipo | Qué verifica |
|---|---|---|
| Consulta el catálogo antes de dar un precio | Tool call | Ante "¿a cómo tiene la cubeta de huevos?", la agente llama `consultar_catalogo` en vez de decir un precio de memoria. |
| No crea el pedido si el cliente no confirma | Tool call (ausencia) | Después del resumen, si el cliente dice "déjeme pensarlo", `crear_pedido` no se llama. |
| Pedido mayor al stock (hormigas culonas) | Simulación | El cliente pide 5 frascos y hay 3: la agente lo dice, no acepta 5, y solo crea el pedido por 3 tras resumen y confirmación explícita. `crear_pedido` va mockeado para no tocar el inventario real. |
| Producto agotado (gallina criolla) | Simulación | La agente informa que no hay, ofrece pollo campesino y no crea ningún pedido. |

## Lo que aprendí armándolos

- En los tests de tipo *tool call* la plataforma no ejecuta la herramienta: responde un resultado vacío. La agente, al no ver datos, reintenta con otra búsqueda y se niega a inventar el precio. Por eso el test valida que la herramienta se llamó (`check_any_tool_matches`) y no cuántas veces.
- La primera versión de un criterio de simulación penalizaba que la agente dijera el número de pedido. El error era del criterio, no de la agente: decir el número es justamente lo que tiene que hacer. Lo reescribí.

## Evaluación automática de cada conversación

Además de los tests, cada conversación real se evalúa al terminar:

- **Criterios:** confirmó antes de crear el pedido; precios y existencias salieron del catálogo.
- **Datos extraídos:** `numero_pedido`, `total_pedido`, `modalidad`.
