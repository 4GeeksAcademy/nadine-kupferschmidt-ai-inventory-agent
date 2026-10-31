import csv
import json
import os
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv(Path(__file__).resolve().parent / ".env")
MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
API_BASE_URL = "http://127.0.0.1:8000"
API_START_COMMAND = "uv run uvicorn api.app:app --reload"
LOG_FILE = Path(__file__).resolve().parent / "conversation_log.csv"
LOG_FIELDS = ["actor", "message", "tool_call", "timestamp"]
MAX_ROUNDS = 5

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_inventory",
            "description": "Obtiene la lista completa del inventario.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_product",
            "description": "Crea un producto nuevo en el inventario.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Nombre del producto."},
                    "quantity": {"type": "integer", "description": "Cantidad inicial, no negativa."},
                    "unit": {"type": "string", "description": "Unidad de medida."},
                },
                "required": ["name", "quantity", "unit"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_stock",
            "description": (
                "Actualiza el stock de un producto. Entregas o reposiciones usan un delta positivo; "
                "ventas o salidas usan un delta negativo."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "product_id": {"type": "integer", "description": "ID del producto."},
                    "delta": {"type": "integer", "description": "Cambio de stock; positivo entra, negativo sale."},
                },
                "required": ["product_id", "delta"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_low_stock_alerts",
            "description": "Consulta productos con stock menor que el umbral indicado (por defecto 10).",
            "parameters": {
                "type": "object",
                "properties": {
                    "threshold": {
                        "type": "integer",
                        "description": "Umbral de stock; se usa 10 si se omite.",
                        "default": 10,
                    }
                },
                "required": [],
                "additionalProperties": False,
            },
        },
    },
]

SYSTEM_MESSAGE = (
    "Eres el asistente de inventario de Carla, dueña de una tienda de suministros para cafeterías. "
    "Responde breve y en español. Si el usuario nombra un producto, primero usa get_inventory para "
    "encontrar su id. Si el producto no existe, pregúntale si quiere crearlo antes de hacerlo. "
    "Para entregas y reposiciones aumenta el stock; para ventas y salidas redúcelo."
)


def log_event(actor: str, message: str, tool_call: str = "") -> None:
    """Agrega inmediatamente un evento al registro de conversación."""
    file_exists = LOG_FILE.exists()
    with LOG_FILE.open("a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=LOG_FIELDS)
        if not file_exists:
            writer.writeheader()
        writer.writerow(
            {
                "actor": actor,
                "message": message,
                "tool_call": tool_call,
                "timestamp": datetime.now().isoformat(),
            }
        )


def api_result(response: requests.Response) -> dict:
    """Convierte respuestas exitosas y errores HTTP en resultados para el modelo."""
    try:
        body = response.json()
    except ValueError:
        body = {"detail": response.text or "La API devolvió una respuesta vacía."}

    if response.ok:
        return {"ok": True, "data": body}
    return {"ok": False, "status_code": response.status_code, "error": body}


def execute_tool(name: str, arguments: dict) -> dict:
    """Ejecuta una herramienta mediante su endpoint correspondiente."""
    try:
        if name == "get_inventory":
            response = requests.get(f"{API_BASE_URL}/inventory", timeout=10)
        elif name == "add_product":
            response = requests.post(f"{API_BASE_URL}/inventory", json=arguments, timeout=10)
        elif name == "update_stock":
            product_id = arguments["product_id"]
            response = requests.patch(
                f"{API_BASE_URL}/inventory/{product_id}",
                json={"delta": arguments["delta"]},
                timeout=10,
            )
        elif name == "get_low_stock_alerts":
            threshold = arguments.get("threshold", 10)
            response = requests.get(
                f"{API_BASE_URL}/inventory/alerts",
                params={"threshold": threshold},
                timeout=10,
            )
        else:
            return {"ok": False, "error": f"Herramienta desconocida: {name}"}

        return api_result(response)
    except requests.RequestException:
        return {
            "ok": False,
            "error": f"No se pudo conectar con la API. Arráncala con: {API_START_COMMAND}",
        }
    except (KeyError, TypeError, ValueError) as error:
        return {"ok": False, "error": f"Argumentos inválidos para {name}: {error}"}


def run_agent_turn(client: OpenAI, history: list[dict], user_message: str) -> str:
    """Procesa un mensaje con el ciclo Observar, Pensar, Actuar y Actualizar."""
    # Observar: guardar el mensaje del usuario en el historial y el registro.
    history.append({"role": "user", "content": user_message})
    log_event("user", user_message)

    for round_number in range(MAX_ROUNDS):
        # Pensar: enviar a Groq el historial completo y las herramientas disponibles.
        completion = client.chat.completions.create(
            model=MODEL,
            messages=history,
            tools=TOOLS,
            tool_choice="auto",
        )
        assistant_message = completion.choices[0].message
        tool_calls = assistant_message.tool_calls or []

        if not tool_calls:
            final_message = assistant_message.content or "No tengo una respuesta para eso."
            history.append({"role": "assistant", "content": final_message})
            log_event("agent", final_message)
            return final_message

        # Actualizar: conservar el mensaje del asistente y sus llamadas en el historial.
        assistant_entry = {
            "role": "assistant",
            "content": assistant_message.content,
            "tool_calls": [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {
                        "name": call.function.name,
                        "arguments": call.function.arguments,
                    },
                }
                for call in tool_calls
            ],
        }
        history.append(assistant_entry)

        # Actuar: ejecutar cada herramienta y registrar tanto la llamada como su resultado.
        for call in tool_calls:
            name = call.function.name
            raw_arguments = call.function.arguments
            try:
                parsed_arguments = json.loads(raw_arguments or "{}")
                if not isinstance(parsed_arguments, dict):
                    raise ValueError("los argumentos deben ser un objeto JSON")
            except (json.JSONDecodeError, ValueError):
                parsed_arguments = {}
            log_event("agent", json.dumps(parsed_arguments, ensure_ascii=False), name)

            try:
                arguments = json.loads(raw_arguments or "{}")
                if not isinstance(arguments, dict):
                    raise ValueError("los argumentos deben ser un objeto JSON")
            except (json.JSONDecodeError, ValueError) as error:
                arguments = {}
                result = {"ok": False, "error": f"Argumentos JSON inválidos: {error}"}
            else:
                result = execute_tool(name, arguments)

            result_json = json.dumps(result, ensure_ascii=False)
            log_event("tool", result_json, name)
            history.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": result_json,
                }
            )

        # Repetir: la siguiente vuelta consulta a Groq con los resultados de las tools.
        if round_number == MAX_ROUNDS - 1:
            final_message = "No pude completar la solicitud en el máximo de 5 vueltas. Inténtalo de nuevo."
            history.append({"role": "assistant", "content": final_message})
            log_event("agent", final_message)
            return final_message

    return "No pude completar la solicitud."


def main() -> None:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("Falta GROQ_API_KEY en el archivo .env.")
        return

    client = OpenAI(api_key=api_key, base_url="https://api.groq.com/openai/v1")
    history = [{"role": "system", "content": SYSTEM_MESSAGE}]
    print("Hola, Carla. Soy tu asistente de inventario. Escribe 'salir' para terminar.")

    while True:
        try:
            # Observar: esperar el siguiente mensaje de Carla.
            user_message = input("Tú: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nHasta luego.")
            break

        if user_message.lower() == "salir":
            print("Hasta luego.")
            break
        if not user_message:
            continue

        try:
            answer = run_agent_turn(client, history, user_message)
        except Exception as error:
            print(f"No se pudo consultar Groq: {error}")
            continue
        print(f"Agente: {answer}")


if __name__ == "__main__":
    main()
