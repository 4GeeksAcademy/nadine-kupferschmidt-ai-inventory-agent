# AI Inventory Agent

Agente de IA por terminal para Carla, dueña de una tienda de suministros para cafeterías. Permite consultar y actualizar el inventario mediante una conversación en español.

## Estructura del proyecto

- `api/app.py`: API REST con FastAPI.
- `agent.py`: agente en Python que usa Groq y llama a la API mediante tools.
- `products.csv`: almacenamiento del inventario.
- `conversation_log.csv`: registro de eventos de conversación.
- `.env.example`: ejemplo de las variables de entorno necesarias.

## Instalación

1. Instala las dependencias:

   ```bash
   uv sync
   ```

2. Copia `.env.example` a `.env` y añade tu clave de Groq en `GROQ_API_KEY`:

   ```bash
   cp .env.example .env
   ```

   Variables de entorno:

   - `GROQ_API_KEY`: clave de API de Groq.
   - `GROQ_MODEL`: modelo de Groq que usará el agente.
   - `GROQ_TEMPERATURE`: temperatura de generación; por defecto, `0.2`.
   - `GROQ_MAX_TOKENS`: máximo de tokens de salida; por defecto, `400`.

## Cómo arrancar

Se necesitan **dos terminales**. Arranca primero la API y luego el agente.

**Terminal 1 — API:**

```bash
uv run uvicorn api.app:app --reload
```

**Terminal 2 — agente:**

```bash
uv run python agent.py
```

## Cómo detenerlo

Escribe `salir` para cerrar el agente, o pulsa `Ctrl+C`. Si detienes los procesos manualmente, detén primero el agente y después la API.

## Endpoints de la API

| Método | Ruta | Qué hace |
|---|---|---|
| `GET` | `/inventory` | Consulta el inventario completo. |
| `POST` | `/inventory` | Crea un producto. |
| `PATCH` | `/inventory/{product_id}` | Actualiza el stock del producto indicado. |
| `GET` | `/inventory/alerts?threshold=10` | Consulta los productos con stock inferior al umbral. |

## Tools del agente

| Nombre | Endpoint que usa |
|---|---|
| `get_inventory` | `GET /inventory` |
| `add_product` | `POST /inventory` |
| `update_stock` | `PATCH /inventory/{product_id}` |
| `get_low_stock_alerts` | `GET /inventory/alerts?threshold=...` |

## Ejemplo de conversación

```text
Tú: acaban de llegar 30 litros de leche de avena
Agente: Listo, se añadieron 30 litros a Leche de avena. Ahora tienes 38 litros en stock.

Tú: vendimos 12 bolsas de arábica hoy
Agente: Se registró la venta de 12 bolsas de Café arábica. Quedan 13 bolsas en stock.

Tú: ¿qué productos están por agotarse?
Agente: - Azúcar: 5 kg
```

## Registro de conversación

`conversation_log.csv` contiene las columnas `actor`, `message`, `tool_call` y `timestamp`. El registro es solo de adición: nunca se sobrescribe; los eventos nuevos se agregan al final.

## Notas

- No se usa ningún framework de agentes. El agente implementa manualmente el bucle **Observar → Pensar → Actuar → Actualizar → Repetir**.
- El agente solo responde sobre temas del inventario de la tienda.
