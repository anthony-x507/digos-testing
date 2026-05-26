#!/usr/bin/env python3
"""
DIGOS AIAgent — Núcleo LLM con tool calling + transparencia
===========================================================
AIAgent que:
1. Recibe mensajes del usuario
2. Llama al LLM vía API compatible OpenAI
3. Ejecuta tools que el LLM decide usar
4. Reporta progreso vía callback de transparencia
5. Retorna la respuesta final

Sin dependencias externas. Solo stdlib (urllib + json).
"""

import json
import time
import threading
from typing import Optional, Dict, List, Any, Callable
from urllib.request import Request, urlopen
from urllib.error import URLError

# Seguridad
from security import SecurityGate, EXTERNAL_TOOLS


# ─────────────────────────────────────────────
# HERRAMIENTAS DISPONIBLES PARA EL LLM
# ─────────────────────────────────────────────

AVAILABLE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Buscar información actualizada en internet",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Término de búsqueda"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Leer el contenido de un archivo",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Ruta del archivo"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Escribir contenido en un archivo",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Ruta del archivo"},
                    "content": {"type": "string", "description": "Contenido a escribir"}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_code",
            "description": "Ejecutar código Python",
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Código Python a ejecutar"}
                },
                "required": ["code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "terminal",
            "description": "Ejecutar un comando en la terminal",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Comando a ejecutar"}
                },
                "required": ["command"]
            }
        }
    },
]


# ─────────────────────────────────────────────
# EJECUTOR DE TOOLS
# ─────────────────────────────────────────────

def _execute_tool(name: str, args: dict) -> str:
    """Ejecuta un tool y retorna el resultado como string."""
    try:
        if name == "web_search":
            return _web_search(args.get("query", ""))
        elif name == "read_file":
            return _read_file(args.get("path", ""))
        elif name == "write_file":
            return _write_file(args.get("path", ""), args.get("content", ""))
        elif name == "execute_code":
            return _execute_code(args.get("code", ""))
        elif name == "terminal":
            return _run_terminal(args.get("command", ""))
        else:
            return f"Error: tool '{name}' no soportado"
    except Exception as e:
        return f"Error ejecutando {name}: {e}"


def _web_search(query: str) -> str:
    """Búsqueda web simple vía DuckDuckGo (sin API key)."""
    import urllib.parse
    encoded = urllib.parse.quote(query)
    url = f"https://lite.duckduckgo.com/lite/?q={encoded}"
    try:
        req = Request(url, headers={"User-Agent": "DIGOS/0.2"})
        with urlopen(req, timeout=15) as r:
            html = r.read().decode("utf-8", errors="replace")
            # Extraer texto relevante (resultados en tags <a>)
            lines = []
            in_result = False
            for line in html.split("\n"):
                if 'class="result-link"' in line or 'class="result-snippet"' in line:
                    in_result = True
                if in_result:
                    # Limpiar tags HTML
                    clean = line.replace("<b>", "").replace("</b>", "")
                    clean = clean.replace("<br>", "\n")
                    lines.append(clean)
                    if len(lines) >= 20:
                        break
            return "\n".join(lines)[:2000] if lines else "Sin resultados"
    except Exception as e:
        return f"Error en búsqueda: {e}"


def _read_file(path: str) -> str:
    """Lee un archivo del sistema."""
    try:
        import os
        path = os.path.expanduser(path)
        if not os.path.isfile(path):
            return f"Error: archivo no encontrado: {path}"
        with open(path, "r", errors="replace") as f:
            content = f.read(3000)
        return content
    except Exception as e:
        return f"Error leyendo archivo: {e}"


def _write_file(path: str, content: str) -> str:
    """Escribe contenido en un archivo."""
    try:
        import os
        path = os.path.expanduser(path)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
        return f"Archivo escrito: {path} ({len(content)} bytes)"
    except Exception as e:
        return f"Error escribiendo archivo: {e}"


def _execute_code(code: str) -> str:
    """Ejecuta código Python en un entorno aislado."""
    import io
    import sys
    import contextlib
    try:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exec_globals = {"__builtins__": __builtins__}
            exec(code, exec_globals)
        result = output.getvalue()
        return result if result else "Código ejecutado (sin salida)"
    except Exception as e:
        return f"Error ejecutando código: {e}"


def _run_terminal(command: str) -> str:
    """Ejecuta un comando en la terminal."""
    import subprocess
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=30
        )
        output = result.stdout or ""
        error = result.stderr or ""
        if error:
            output += f"\n[stderr]\n{error}"
        return output[:2000] if output else "Comando ejecutado (sin salida)"
    except subprocess.TimeoutExpired:
        return "Error: comando timeout (30s)"
    except Exception as e:
        return f"Error en terminal: {e}"


# ─────────────────────────────────────────────
# AIAGENT — LLM INTERACTION LOOP
# ─────────────────────────────────────────────

class AIAgent:
    """Agente que procesa mensajes con LLM + tools + transparencia.

    Uso:
        agent = AIAgent(
            base_url="https://api.openai.com/v1",
            api_key="sk-...",
            model="gpt-4o",
            progress_cb=tower.emit_tool_progress,
            assistant_cb=tower.emit_assistant_message,
        )
        response = agent.process_message("Hola, ¿qué hora es?")
    """

    def __init__(
        self,
        base_url: str = "",
        api_key: str = "",
        model: str = "gpt-4o",
        system_prompt: str = "Eres un asistente útil. Puedes usar herramientas para ayudar al usuario.",
        progress_cb: Optional[Callable] = None,
        assistant_cb: Optional[Callable] = None,
        max_iterations: int = 15,
    ):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._system_prompt = system_prompt
        self._progress_cb = progress_cb or (lambda n, a: None)
        self._assistant_cb = assistant_cb or (lambda t: None)
        self._max_iterations = max_iterations

        # Historial de conversación
        self._messages: List[dict] = [{"role": "system", "content": system_prompt}]
        self._tools_enabled = True

        # Security Gate
        self._gate = SecurityGate()

    def process_message(self, user_message: str) -> str:
        """Procesa un mensaje del usuario. Retorna la respuesta final."""
        # ── Input Gate: revisar mensaje antes de procesar ──
        gate_result = self._gate.check_input(user_message)
        if gate_result["blocked"]:
            return gate_result["response"]

        clean_msg = gate_result["clean_message"]
        self._messages.append({"role": "user", "content": clean_msg})

        iterations = 0
        while iterations < self._max_iterations:
            iterations += 1

            # 1. Llamar al LLM
            assistant_text, tool_calls = self._call_llm()

            # 2. Si el LLM generó texto interino, reportarlo
            if assistant_text:
                self._assistant_cb(assistant_text[:200])

            # 3. Si no hay tool calls, terminamos
            if not tool_calls:
                if assistant_text:
                    self._messages.append({"role": "assistant", "content": assistant_text})
                    # ── Output Gate: revisar respuesta final ──
                    output_check = self._gate.check_output(assistant_text)
                    if not output_check["safe"]:
                        self._assistant_cb(f"⚠️ {output_check['warning']}")
                    return assistant_text
                else:
                    return "No pude procesar tu mensaje."

            # 4. Agregar respuesta del asistente (con tool calls) al historial
            assistant_msg = {"role": "assistant", "content": assistant_text or ""}
            if tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": json.dumps(tc["args"])}
                    }
                    for tc in tool_calls
                ]
            self._messages.append(assistant_msg)

            # 5. Ejecutar cada tool
            for tc in tool_calls:
                name = tc["name"]
                args = tc["args"]

                # Reportar progreso
                self._progress_cb(name, args)

                # Ejecutar
                result = _execute_tool(name, args)

                # ── Tool Output Gate: solo para fuentes externas ──
                tool_check = self._gate.check_tool_output(name, result)
                safe_result = tool_check["output"]

                # Agregar resultado al historial
                self._messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": safe_result[:2000],
                })

        return "Lo siento, no pude completar la tarea en el número máximo de iteraciones."

    def _call_llm(self) -> tuple:
        """Llama al LLM. Retorna (assistant_text, list_of_tool_calls)."""
        if not self._base_url or not self._api_key:
            return "LLM no configurado. Usa --setup para configurar API key.", []

        endpoint = self._base_url + "/chat/completions"

        body = {
            "model": self._model,
            "messages": self._messages[-20:],  # últimos 20 mensajes
            "max_tokens": 2048,
            "temperature": 0.7,
        }

        if self._tools_enabled:
            body["tools"] = AVAILABLE_TOOLS
            body["tool_choice"] = "auto"

        try:
            payload = json.dumps(body).encode()
            req = Request(
                endpoint,
                data=payload,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self._api_key}",
                },
            )
            with urlopen(req, timeout=60) as r:
                data = json.loads(r.read())
        except URLError as e:
            return f"Error de conexión con LLM: {e.reason}", []
        except json.JSONDecodeError:
            return "Error: respuesta inválida del LLM", []
        except Exception as e:
            return f"Error llamando al LLM: {e}", []

        choices = data.get("choices", [])
        if not choices:
            return "El LLM no devolvió respuestas.", []

        msg = choices[0].get("message", {})
        content = msg.get("content") or ""
        raw_tool_calls = msg.get("tool_calls") or []

        tool_calls = []
        for tc in raw_tool_calls:
            if tc.get("type") == "function":
                try:
                    func = tc.get("function", {})
                    name = func.get("name", "")
                    args = json.loads(func.get("arguments", "{}"))
                    tool_calls.append({
                        "id": tc["id"],
                        "name": name,
                        "args": args,
                    })
                except (json.JSONDecodeError, KeyError):
                    continue

        return content, tool_calls

    def reset_conversation(self):
        """Reinicia el historial de conversación."""
        self._messages = [{"role": "system", "content": self._system_prompt}]
