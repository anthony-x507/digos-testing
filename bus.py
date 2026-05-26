#!/usr/bin/env python3
"""
DIGOS Message Bus — Comunicación Multi-Agente vía Unix Sockets
================================================================
Sistema de mensajería local entre agentes DIGOS usando Unix Domain Sockets.
No requiere puertos TCP, no requiere dependencias externas.

Dos modos de operación:
  🔒 AISLADO — El agente solo ve a ControlTower. No sabe que existen otros.
  🤝 COLABORATIVO — El agente ve el directorio de agentes y puede comunicarse.

El USUARIO decide el modo. ControlTower solo activa/desactiva según lo que
el usuario ordene a través de su agente.

Arquitectura:
  ControlTower (broker central)
    ├── Socket principal: /tmp/digos/tower.sock
    ├── josecito:   /tmp/digos/josecito.sock   [colaborativo]
    ├── alex:       /tmp/digos/alex.sock       [colaborativo]
    ├── freya:      /tmp/digos/freya.sock      [aislado]
    └── yarimae:    /tmp/digos/yarimae.sock    [aislado]

Protocolo (JSON sobre Unix socket):
  {"cmd": "send",    "to": "alex", "content": "..."}
  {"cmd": "broadcast","topic": "alerta", "content": "..."}
  {"cmd": "list",    "filter": "collaborative"}
  Respuesta: {"type": "message", "from": "josecito", "content": "..."}

Sin dependencias externas. Solo stdlib (socket, json, os, threading).
"""

import json
import os
import socket
import threading
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, Dict, List, Any, Callable, Set


# ─────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────

BUS_DIR = Path("/tmp/digos")
TOWER_SOCKET = BUS_DIR / "tower.sock"

AGENT_MODES = {"isolated": "🔒", "collaborative": "🤝"}


# ─────────────────────────────────────────────
# MODELOS DE DATOS
# ─────────────────────────────────────────────


@dataclass
class AgentEndpoint:
    """Representa un agente conectado al bus."""
    name: str
    socket_path: str
    mode: str               # "isolated" | "collaborative"
    connected: bool = False
    subscribed_topics: Set[str] = field(default_factory=lambda: {"system"})
    last_seen: float = 0.0


@dataclass
class BusMessage:
    """Mensaje en el bus."""
    msg_type: str           # "message" | "broadcast" | "command" | "response"
    sender: str
    recipient: str = ""     # "" para broadcast
    content: str = ""
    topic: str = ""
    timestamp: float = 0.0

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @staticmethod
    def from_json(data: dict) -> "BusMessage":
        return BusMessage(
            msg_type=data.get("type", "message"),
            sender=data.get("from", ""),
            recipient=data.get("to", ""),
            content=data.get("content", ""),
            topic=data.get("topic", ""),
            timestamp=time.time(),
        )


# ─────────────────────────────────────────────
# AGENT CONNECTION (lado del agente)
# ─────────────────────────────────────────────


class AgentBusClient:
    """Cliente del bus — se conecta al socket del agente desde el agente mismo.

    Uso (modo colaborativo):
        client = AgentBusClient("alex", mode="collaborative")
        client.connect()
        client.send("josecito", "Hola hermano!")
        messages = client.poll()

    Uso (modo aislado):
        client = AgentBusClient("freya", mode="isolated")
        client.connect()
        # Solo puede recibir de ControlTower
        client.send_to_supervisor("Usuario pide X")
    """

    def __init__(self, agent_name: str, mode: str = "isolated"):
        self._name = agent_name
        self._mode = mode
        self._socket_path = BUS_DIR / f"{agent_name}.sock"
        self._sock: Optional[socket.socket] = None
        self._connected = False
        self._buffer = b""

    def connect(self) -> bool:
        """Conecta al socket del agente."""
        try:
            BUS_DIR.mkdir(parents=True, exist_ok=True)
            self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self._sock.settimeout(5.0)
            self._sock.connect(str(self._socket_path))
            self._connected = True
            self._sock.settimeout(0.1)  # no-blocking después de conectar

            # Registrar modo
            self._send_raw({
                "cmd": "register",
                "name": self._name,
                "mode": self._mode,
            })
            return True
        except (socket.error, FileNotFoundError) as e:
            self._connected = False
            return False

    def disconnect(self):
        """Desconecta del bus."""
        if self._sock:
            try:
                self._send_raw({"cmd": "unregister"})
                self._sock.close()
            except Exception:
                pass
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected and self._sock is not None

    def send(self, to: str, content: str) -> bool:
        """Envía un mensaje a otro agente (solo modo colaborativo)."""
        if self._mode == "isolated" and to != "tower":
            return False
        return self._send_raw({
            "cmd": "send",
            "to": to,
            "content": content,
        })

    def send_to_supervisor(self, content: str) -> bool:
        """Envía mensaje al supervisor (ControlTower). Disponible en ambos modos."""
        return self._send_raw({
            "cmd": "send",
            "to": "tower",
            "content": content,
        })

    def broadcast(self, topic: str, content: str) -> bool:
        """Envía un broadcast a todos los agentes suscritos al topic."""
        return self._send_raw({
            "cmd": "broadcast",
            "topic": topic,
            "content": content,
        })

    def list_agents(self, filter_mode: str = "") -> Optional[list]:
        """Solicita lista de agentes conectados. Solo modo colaborativo."""
        if self._mode == "isolated":
            return None
        # Enviar request con ID único
        import uuid
        req_id = str(uuid.uuid4())[:8]
        self._send_raw({"cmd": "list", "filter": filter_mode, "req_id": req_id})
        # Esperar respuesta con timeout
        deadline = time.time() + 3.0
        while time.time() < deadline:
            resp = self._read_line()
            if resp:
                try:
                    data = json.loads(resp)
                    if data.get("type") == "agent_list":
                        return data.get("agents", [])
                except json.JSONDecodeError:
                    continue
            time.sleep(0.05)
        return None

    def poll(self, timeout: float = 0.5) -> List[BusMessage]:
        """Lee mensajes pendientes."""
        messages = []
        if not self._connected or not self._sock:
            return messages
        try:
            self._sock.settimeout(timeout)
            while True:
                data = self._sock.recv(4096)
                if not data:
                    break
                self._buffer += data
                while b"\n" in self._buffer:
                    line, self._buffer = self._buffer.split(b"\n", 1)
                    if line.strip():
                        try:
                            msg_data = json.loads(line.decode())
                            msg = BusMessage.from_json(msg_data)
                            messages.append(msg)
                        except (json.JSONDecodeError, KeyError):
                            continue
        except socket.timeout:
            pass
        except Exception:
            self._connected = False
        return messages

    def switch_mode(self, new_mode: str):
        """Cambia el modo del agente (solicitado por el usuario)."""
        if new_mode not in AGENT_MODES:
            return
        old_mode = self._mode
        self._mode = new_mode
        self._send_raw({
            "cmd": "switch_mode",
            "mode": new_mode,
            "old_mode": old_mode,
        })

    # ── Internals ──

    def _send_raw(self, data: dict) -> bool:
        if not self._connected or not self._sock:
            return False
        try:
            payload = json.dumps(data) + "\n"
            self._sock.sendall(payload.encode())
            return True
        except Exception:
            self._connected = False
            return False

    def _read_line(self) -> str:
        if not self._sock:
            return ""
        try:
            while b"\n" not in self._buffer:
                chunk = self._sock.recv(4096)
                if not chunk:
                    break
                self._buffer += chunk
            if b"\n" in self._buffer:
                line, self._buffer = self._buffer.split(b"\n", 1)
                return line.decode().strip()
        except Exception:
            pass
        return ""


# ─────────────────────────────────────────────
# MESSAGE BUS (lado de ControlTower)
# ─────────────────────────────────────────────


class MessageBus:
    """Message Bus central — corre dentro de ControlTower.

    ControlTower crea una instancia del bus y luego:
      bus.register_agent("josecito", "collaborative")
      bus.register_agent("freya", "isolated")
      bus.start()  # empieza a escuchar

    Cuando un agente se conecta, el bus maneja el ruteo de mensajes.
    """

    def __init__(self):
        self._agents: Dict[str, AgentEndpoint] = {}
        self._connections: Dict[str, socket.socket] = {}
        self._tower_sock: Optional[socket.socket] = None
        self._running = False
        self._lock = threading.Lock()
        self._on_message: Optional[Callable] = None  # callback para ControlTower
        self._thread: Optional[threading.Thread] = None

    def set_message_callback(self, callback: Callable):
        """Callback cuando llega un mensaje. ControlTower lo usa para logging."""
        self._on_message = callback

    def register_agent(self, name: str, mode: str = "isolated"):
        """Registra un agente en el bus y crea su socket."""
        socket_path = BUS_DIR / f"{name}.sock"
        agent = AgentEndpoint(
            name=name,
            socket_path=str(socket_path),
            mode=mode,
        )
        with self._lock:
            self._agents[name] = agent
        return agent

    def unregister_agent(self, name: str):
        """Elimina un agente del bus y cierra su conexión."""
        with self._lock:
            self._agents.pop(name, None)
            sock = self._connections.pop(name, None)
        if sock:
            try:
                sock.close()
            except Exception:
                pass
        socket_path = BUS_DIR / f"{name}.sock"
        try:
            socket_path.unlink(missing_ok=True)
        except Exception:
            pass

    def get_mode(self, name: str) -> str:
        """Retorna el modo de un agente."""
        with self._lock:
            agent = self._agents.get(name)
            return agent.mode if agent else "isolated"

    def switch_mode(self, name: str, new_mode: str) -> bool:
        """Cambia el modo de un agente."""
        if new_mode not in AGENT_MODES:
            return False
        with self._lock:
            agent = self._agents.get(name)
            if not agent:
                return False
            agent.mode = new_mode
        return True

    def list_agents(self, filter_mode: str = "") -> List[dict]:
        """Lista agentes conectados. Si filter_mode, solo los de ese modo."""
        with self._lock:
            agents = []
            for name, agent in self._agents.items():
                if filter_mode and agent.mode != filter_mode:
                    continue
                agents.append({
                    "name": name,
                    "mode": agent.mode,
                    "connected": agent.connected,
                    "last_seen": agent.last_seen,
                })
            return agents

    # ── Iniciar/Detener ──

    def start(self):
        """Inicia el bus en un hilo separado."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        """Detiene el bus."""
        self._running = False
        if self._tower_sock:
            try:
                self._tower_sock.close()
            except Exception:
                pass
        # Cerrar conexiones de agentes
        for name in list(self._connections.keys()):
            self.unregister_agent(name)

    def _run(self):
        """Loop principal del bus."""
        BUS_DIR.mkdir(parents=True, exist_ok=True)

        # Socket principal de ControlTower
        try:
            TOWER_SOCKET.unlink(missing_ok=True)
        except Exception:
            pass

        self._tower_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._tower_sock.settimeout(1.0)
        self._tower_sock.bind(str(TOWER_SOCKET))
        self._tower_sock.listen(10)
        os.chmod(str(TOWER_SOCKET), 0o700)

        # Crear sockets individuales para agentes registrados
        agent_sockets: Dict[str, socket.socket] = {}
        for name, agent in self._agents.items():
            sock = self._create_agent_socket(name)
            if sock:
                agent_sockets[name] = sock

        # Las conexiones entran por el socket del agente individual
        # y el socket principal de ControlTower es solo administrativo
        all_sockets = [self._tower_sock] + list(agent_sockets.values())

        while self._running:
            try:
                # Usar select para monitorear múltiples sockets
                readable, _, _ = self._select_wrapper(all_sockets, timeout=1.0)
                if not readable:
                    continue

                for sock in readable:
                    if sock == self._tower_sock:
                        # Nueva conexión administrativa
                        try:
                            conn, _ = sock.accept()
                            conn.close()
                        except Exception:
                            pass
                    elif sock in agent_sockets.values():
                        # Mensaje de un agente — manejar en hilo separado
                        try:
                            conn, _ = sock.accept()
                            t = threading.Thread(
                                target=self._handle_agent_connection,
                                args=(conn,),
                                daemon=True,
                            )
                            t.start()
                        except BlockingIOError:
                            continue
                        except Exception:
                            continue

            except Exception:
                continue

        # Limpieza
        for sock in all_sockets:
            try:
                sock.close()
            except Exception:
                pass

    def _create_agent_socket(self, name: str) -> Optional[socket.socket]:
        """Crea socket Unix para un agente."""
        socket_path = BUS_DIR / f"{name}.sock"
        try:
            socket_path.unlink(missing_ok=True)
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.settimeout(1.0)
            sock.bind(str(socket_path))
            sock.listen(5)
            os.chmod(str(socket_path), 0o600)
            return sock
        except Exception:
            return None

    def _handle_agent_connection(self, conn: socket.socket):
        """Maneja una conexión entrante de un agente."""
        conn.settimeout(5.0)
        buffer = b""

        try:
            while self._running:
                data = conn.recv(4096)
                if not data:
                    break
                buffer += data

                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    if not line.strip():
                        continue

                    try:
                        msg = json.loads(line.decode())
                        self._process_message(msg, conn)
                    except json.JSONDecodeError:
                        continue

        except (socket.timeout, ConnectionError):
            pass
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _process_message(self, msg: dict, conn: socket.socket):
        """Procesa un mensaje entrante."""
        cmd = msg.get("cmd", "")

        if cmd == "register":
            name = msg.get("name", "")
            mode = msg.get("mode", "isolated")
            with self._lock:
                agent = self._agents.get(name)
                if agent:
                    agent.connected = True
                    agent.last_seen = time.time()
                    self._connections[name] = conn
            self._notify(f"Agent '{name}' registered ({mode})")

        elif cmd == "unregister":
            name = self._find_agent_by_conn(conn)
            if name:
                self.unregister_agent(name)
                self._notify(f"Agent '{name}' unregistered")

        elif cmd == "send":
            self._route_message(msg, conn)

        elif cmd == "broadcast":
            self._broadcast(msg)

        elif cmd == "list":
            filter_mode = msg.get("filter", "")
            agents = self.list_agents(filter_mode)
            self._send_to_conn(conn, {
                "type": "agent_list",
                "agents": agents,
            })

        elif cmd == "switch_mode":
            name = self._find_agent_by_conn(conn)
            new_mode = msg.get("mode", "")
            if name and self.switch_mode(name, new_mode):
                self._notify(f"Agent '{name}' switched to {new_mode}")
                self._send_to_conn(conn, {
                    "type": "mode_changed",
                    "mode": new_mode,
                })
                # Notificar a los demás agentes colaborativos
                self._broadcast({
                    "topic": "system",
                    "content": f"Agent '{name}' is now {new_mode}",
                })

    def _route_message(self, msg: dict, conn: socket.socket):
        """Enruta un mensaje al destinatario."""
        sender = self._find_agent_by_conn(conn)
        recipient = msg.get("to", "")
        content = msg.get("content", "")

        if not sender:
            return

        # Si el remitente está en modo aislado, solo puede enviar a tower
        sender_agent = self._agents.get(sender)
        if sender_agent and sender_agent.mode == "isolated" and recipient != "tower":
            self._send_to_conn(conn, {
                "type": "error",
                "content": "Isolated agents can only message ControlTower",
            })
            return

        if recipient == "tower":
            # Mensaje para ControlTower
            self._notify(f"From {sender}: {content[:100]}")
            return

        # Enrutar al destinatario
        recipient_conn = self._connections.get(recipient)
        if recipient_conn:
            self._send_to_conn(recipient_conn, {
                "type": "message",
                "from": sender,
                "content": content,
            })
            self._notify(f"Routed: {sender} → {recipient}")
        else:
            self._send_to_conn(conn, {
                "type": "error",
                "content": f"Agent '{recipient}' not connected",
            })

    def _broadcast(self, msg: dict):
        """Broadcast a todos los agentes colaborativos."""
        topic = msg.get("topic", "general")
        content = msg.get("content", "")
        sender = msg.get("from", "tower")

        with self._lock:
            for name, agent in self._agents.items():
                if not agent.connected:
                    continue
                if topic not in agent.subscribed_topics and topic != "system":
                    continue
                sock = self._connections.get(name)
                if sock:
                    try:
                        self._send_to_conn(sock, {
                            "type": "broadcast",
                            "from": sender,
                            "topic": topic,
                            "content": content,
                        })
                    except Exception:
                        pass

    def _send_to_conn(self, conn: socket.socket, data: dict):
        """Envía datos JSON a una conexión."""
        try:
            payload = json.dumps(data) + "\n"
            conn.sendall(payload.encode())
        except Exception:
            pass

    def _find_agent_by_conn(self, conn: socket.socket) -> Optional[str]:
        """Encuentra el nombre del agente por su conexión."""
        with self._lock:
            for name, sock in self._connections.items():
                if sock == conn:
                    return name
        return None

    def _notify(self, message: str):
        """Notifica a ControlTower via callback."""
        if self._on_message:
            try:
                self._on_message(message)
            except Exception:
                pass

    @staticmethod
    def _select_wrapper(sockets: list, timeout: float = 1.0):
        """Wrapper para select.select con manejo de errores."""
        import select
        try:
            return select.select(sockets, [], [], timeout)
        except (ValueError, TypeError):
            return [], [], []

    # ── Estado ──

    def status(self) -> dict:
        """Estado completo del bus."""
        with self._lock:
            return {
                "running": self._running,
                "agents": [
                    {
                        "name": agent.name,
                        "mode": agent.mode,
                        "connected": agent.connected,
                        "icon": AGENT_MODES.get(agent.mode, "❓"),
                    }
                    for agent in self._agents.values()
                ],
            }

    def print_status(self):
        """Imprime estado del bus."""
        status = self.status()
        print()
        print("  📡 MESSAGE BUS — Estado")
        print(f"  {'─' * 45}")
        print(f"  {'🟢' if status['running'] else '🔴'} Bus: {'Activo' if status['running'] else 'Detenido'}")
        print(f"  Agentes: {len(status['agents'])}")
        for agent in status['agents']:
            icon = agent['icon']
            conn = "🟢" if agent['connected'] else "⚫"
            print(f"    {icon} {conn} {agent['name']} ({agent['mode']})")
        print()
