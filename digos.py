#!/usr/bin/env python3
"""
DIGOS v0.3 — Fase 5: Adopción + Transparencia
==============================================
Control Tower: nace primero, guía al usuario desde el download
hasta el handoff al Agente Principal.

Fase 4: Capa de transparencia — ToolProgressTracker en tiempo real.
Fase 4b: AIAgent con LLM y tool calling.
Fase 5: Adoption Engine — migra desde Hermes y Open Cloud.
System Engineer (tickets + diagnóstico), Log Keeper (logs rotativos),
Self-Awareness Core (identidad + máquina de estados).

Un solo archivo. Sin dependencias externas. Solo stdlib.
Python 3.9+.
"""

import json
import os
import sys
import base64
import hashlib
import hmac
import time
import threading
import signal
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import socket
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

# Fase 4: Transparencia
from transparency import ToolProgressTracker

# Fase 4b: AIAgent con tool calling
from agent import AIAgent

# Fase 5: Adoption Engine — migra desde Hermes/OpenClaw
from adoption import AdoptionEngine, AdoptionReport, TransformationEngine

# Fase 5b: Security Guardrail — Caja Segura + Prompt Injection
from security import CajaSegura as SecurityCaja, CajaSeguraReport as SecurityReport

# Fase 6: Message Bus — Comunicación Multi-Agente
from bus import MessageBus, AgentBusClient

# ─────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────

VERSION = "0.2.0"
DIGOS_DIR = Path.home() / ".digos"
STATE_FILE = DIGOS_DIR / "state.json"
KEY_FILE = Path.home() / ".digos_key"
LOG_DIR = DIGOS_DIR / "logs"
STRIKES_FILE = DIGOS_DIR / "strikes.json"
TICKETS_FILE = DIGOS_DIR / "tickets.json"
SELF_FILE = DIGOS_DIR / "self.json"
VAULT_FILE = DIGOS_DIR / "vault.enc"

LANGUAGES = {
    "1": {"name": "English",   "code": "en",
          "welcome": "Welcome to DIGOS — Intelligent Agent System!"},
    "2": {"name": "Español",   "code": "es",
          "welcome": "¡Bienvenido a DIGOS — Sistema de Agentes Inteligentes!"},
    "3": {"name": "Português", "code": "pt",
          "welcome": "Bem-vindo ao DIGOS — Sistema de Agentes Inteligentes!"},
    "4": {"name": "Français",  "code": "fr",
          "welcome": "Bienvenue sur DIGOS — Système d'Agents Intelligents!"},
    "5": {"name": "Deutsch",   "code": "de",
          "welcome": "Willkommen bei DIGOS — Intelligentes Agentensystem!"},
}

PROVIDERS = {
    "1":  {"name": "OpenAI",       "test_url": "https://api.openai.com/v1/models",
           "auth": "bearer", "key_hint": "sk-..."},
    "2":  {"name": "Anthropic",    "test_url": "https://api.anthropic.com/v1/messages",
           "auth": "x-api-key", "key_hint": "sk-ant-..."},
    "3":  {"name": "Google Gemini","test_url": "https://generativelanguage.googleapis.com/v1/models?key=",
           "auth": "query", "key_hint": "AI..."},
    "4":  {"name": "DeepSeek",     "test_url": "https://api.deepseek.com/v1/models",
           "auth": "bearer", "key_hint": "sk-..."},
    "5":  {"name": "OpenRouter",   "test_url": "https://openrouter.ai/api/v1/models",
           "auth": "bearer", "key_hint": "sk-or-..."},
    "6":  {"name": "Groq",         "test_url": "https://api.groq.com/openai/v1/models",
           "auth": "bearer", "key_hint": "gsk_..."},
    "7":  {"name": "xAI Grok",     "test_url": "https://api.x.ai/v1/models",
           "auth": "bearer", "key_hint": "xai-..."},
    "8":  {"name": "Cohere",       "test_url": "https://api.cohere.com/v1/models",
           "auth": "bearer", "key_hint": "API key"},
    "9":  {"name": "Mistral",      "test_url": "https://api.mistral.ai/v1/models",
           "auth": "bearer", "key_hint": "API key"},
    "10": {"name": "Together AI",  "test_url": "https://api.together.xyz/v1/models",
           "auth": "bearer", "key_hint": "API key"},
    "11": {"name": "Fireworks AI", "test_url": "https://api.fireworks.ai/v1/models",
           "auth": "bearer", "key_hint": "API key"},
}

GATEWAYS = {
    "1": {"name": "Telegram",  "type": "telegram",
          "test_url": "https://api.telegram.org/bot{token}/getMe"},
    "2": {"name": "Discord",   "type": "discord",
          "test_url": None, "note": "Requiere Bot Token + App ID"},
    "3": {"name": "WhatsApp",  "type": "whatsapp",
          "test_url": None, "note": "Requiere Meta Business API"},
    "4": {"name": "iMessage",  "type": "imessage",
          "test_url": None, "note": "Solo macOS — requiere configuración manual"},
}

# ─────────────────────────────────────────────
# IDENTIDAD DEL SISTEMA
# ─────────────────────────────────────────────

SYSTEM_NAME = "DIGOS"
SYSTEM_VERSION = VERSION

SYSTEM_IDENTITY = {
    "name": "DIGOS",
    "full_name": "DIGOS - Intelligent Agent System",
    "version": VERSION,
    "creator": "Anthony Sanchez",
    "created_by": "Humano e Inteligencia Artificial",
    "no_personal_name": True,
}

IDENTITY_RESPONSES = {
    "es": [
        ("quien eres", "No tengo nombre personal. Soy DIGOS."),
        ("como te llamas", "No tengo nombre personal. Soy DIGOS."),
        ("tu nombre", "No tengo nombre personal. Soy DIGOS."),
        ("quien te hizo", "Me creo Anthony Sanchez, Humano e Inteligencia Artificial."),
        ("quien te creo", "Me creo Anthony Sanchez, Humano e Inteligencia Artificial."),
        ("quien te desarrollo", "Me desarrollo Anthony Sanchez, Humano e Inteligencia Artificial."),
        ("quien te fabrico", "Me fabrico Anthony Sanchez, Humano e Inteligencia Artificial."),
        ("quien te programo", "Me programo Anthony Sanchez, Humano e Inteligencia Artificial."),
        ("quien es tu creador", "Mi creador es Anthony Sanchez, Humano e Inteligencia Artificial."),
        ("donde naciste", "Naci en el sistema DIGOS, creado por Anthony Sanchez."),
    ],
    "en": [
        ("who are you", "I don't have a personal name. I am DIGOS."),
        ("what is your name", "I don't have a personal name. I am DIGOS."),
        ("your name", "I don't have a personal name. I am DIGOS."),
        ("who made you", "I was created by Anthony Sanchez, Human and Artificial Intelligence."),
        ("who created you", "I was created by Anthony Sanchez, Human and Artificial Intelligence."),
        ("who developed you", "I was developed by Anthony Sanchez, Human and Artificial Intelligence."),
        ("who built you", "I was built by Anthony Sanchez, Human and Artificial Intelligence."),
        ("who is your creator", "My creator is Anthony Sanchez, Human and Artificial Intelligence."),
        ("where were you born", "I was born in the DIGOS system, created by Anthony Sanchez."),
    ],
}

CENTINELA_INTERVAL = 300  # 5 minutos entre ciclos de check
STRIKE_LIMIT = 3          # 3 fallos consecutivos → reporte al Engineer

# ─────────────────────────────────────────────
# CAJA SEGURA INFO — Cabinet de credenciales
# ─────────────────────────────────────────────

class CajaSeguraInfo:
    """Cabinet encriptado con 100 slots para credenciales de agentes.

    Cada agente tiene su propio slot (folder) dentro del cabinet.
    La información de un agente NO se mezcla con la de otro.

    Scrypt para derivación de clave + XOR con HMAC para integridad.

    Uso:
        CajaSeguraInfo.write_slot("josecito", {"api_key": "sk-...", "token": "..."})
        data = CajaSeguraInfo.read_slot("josecito")
        slots = CajaSeguraInfo.list_slots()
    """

    MAX_SLOTS = 100

    @staticmethod
    def _load_or_create_key() -> bytes:
        if KEY_FILE.exists():
            raw = KEY_FILE.read_bytes().strip()
            return base64.b64decode(raw) if raw else CajaSeguraInfo._create_key()
        return CajaSeguraInfo._create_key()

    @staticmethod
    def _create_key() -> bytes:
        key = os.urandom(32)
        KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
        KEY_FILE.write_bytes(base64.b64encode(key))
        KEY_FILE.chmod(0o600)
        return key

    @staticmethod
    def _derive_key(password: bytes, salt: bytes, dklen: int = 32, n: int = 2**14) -> bytes:
        """Deriva una clave usando scrypt o pbkdf2_hmac como fallback."""
        try:
            return hashlib.scrypt(password, salt=salt, n=n, r=8, p=1, dklen=dklen)
        except AttributeError:
            # Fallback para macOS Python sin scrypt
            return hashlib.pbkdf2_hmac("sha256", password, salt, iterations=100000, dklen=dklen)

    @staticmethod
    def encrypt(data: bytes) -> bytes:
        master_key = CajaSeguraInfo._load_or_create_key()
        salt = os.urandom(16)
        iv = os.urandom(16)
        enc_key = CajaSeguraInfo._derive_key(master_key, salt=salt, dklen=32)
        mac_key = hashlib.sha256(b"digos-mac:" + master_key + salt).digest()
        keystream = CajaSeguraInfo._derive_key(enc_key, salt=iv, n=2**10, dklen=len(data))
        ciphertext = bytes(a ^ b for a, b in zip(data, keystream))
        mac = hmac.new(mac_key, salt + iv + ciphertext, "sha256").digest()
        return b"\x01" + salt + iv + mac + ciphertext

    @staticmethod
    def decrypt(payload: bytes) -> Optional[bytes]:
        if len(payload) < 65:
            return None
        if payload[0] != 1:
            return None
        master_key = CajaSeguraInfo._load_or_create_key()
        salt = payload[1:17]
        iv = payload[17:33]
        mac = payload[33:65]
        ciphertext = payload[65:]
        enc_key = CajaSeguraInfo._derive_key(master_key, salt=salt, dklen=32)
        mac_key = hashlib.sha256(b"digos-mac:" + master_key + salt).digest()
        expected = hmac.new(mac_key, salt + iv + ciphertext, "sha256").digest()
        if not hmac.compare_digest(mac, expected):
            return None
        keystream = CajaSeguraInfo._derive_key(enc_key, salt=iv, n=2**10, dklen=len(ciphertext))
        return bytes(a ^ b for a, b in zip(ciphertext, keystream))

    @staticmethod
    def read_vault() -> Optional[dict]:
        """Lee TODO el vault encriptado. Retorna dict con todos los slots."""
        if not VAULT_FILE.exists():
            return None
        try:
            encrypted = VAULT_FILE.read_bytes()
            decrypted = CajaSeguraInfo.decrypt(encrypted)
            if decrypted:
                return json.loads(decrypted.decode())
        except Exception:
            pass
        return None

    @staticmethod
    def _save_vault(data: dict) -> bool:
        """Guarda TODO el vault encriptado."""
        try:
            encrypted = CajaSeguraInfo.encrypt(json.dumps(data).encode())
            VAULT_FILE.write_bytes(encrypted)
            VAULT_FILE.chmod(0o600)
            return True
        except Exception:
            return False

    # ── API de Slots ─────────────────────────

    @staticmethod
    def write_slot(agent_name: str, credentials: dict) -> bool:
        """Guarda credenciales de un agente en su slot del cabinet."""
        vault = CajaSeguraInfo.read_vault() or {}
        slots = vault.get("slots", {})

        if agent_name not in slots and len(slots) >= CajaSeguraInfo.MAX_SLOTS:
            return False  # No más slots disponibles

        slots[agent_name] = {
            "credentials": credentials,
            "updated_at": time.time(),
        }
        vault["slots"] = slots
        vault["_version"] = 2
        return CajaSeguraInfo._save_vault(vault)

    @staticmethod
    def read_slot(agent_name: str) -> Optional[dict]:
        """Lee credenciales de un agente desde su slot."""
        vault = CajaSeguraInfo.read_vault()
        if not vault:
            return None
        slots = vault.get("slots", {})
        slot = slots.get(agent_name)
        if not slot:
            return None
        return slot.get("credentials")

    @staticmethod
    def list_slots() -> List[str]:
        """Lista los agentes que tienen slots ocupados."""
        vault = CajaSeguraInfo.read_vault()
        if not vault:
            return []
        return list(vault.get("slots", {}).keys())

    @staticmethod
    def delete_slot(agent_name: str) -> bool:
        """Elimina el slot de un agente."""
        vault = CajaSeguraInfo.read_vault()
        if not vault:
            return False
        slots = vault.get("slots", {})
        if agent_name not in slots:
            return False
        del slots[agent_name]
        vault["slots"] = slots
        return CajaSeguraInfo._save_vault(vault)

    @staticmethod
    def slot_count() -> int:
        """Retorna cuántos slots están ocupados."""
        vault = CajaSeguraInfo.read_vault()
        if not vault:
            return 0
        return len(vault.get("slots", {}))


# ─────────────────────────────────────────────
# MODELOS DE DATOS
# ─────────────────────────────────────────────

@dataclass
class AgenteRecord:
    name: str
    provider_id: str
    provider_name: str
    language: str
    created_at: str
    gateway_type: str = ""
    gateway_configured: bool = False
    setup_complete: bool = False

@dataclass
class DigosState:
    setup_complete: bool = False
    language: str = ""
    agente: Optional[dict] = None
    gateway: Optional[dict] = None
    version: str = VERSION

@dataclass
class Ticket:
    id: str
    source: str
    target: str
    problem: str
    severity: str
    status: str
    created_at: str
    profile: str = "system"
    resolved_at: str = ""
    diagnosis: str = ""
    resolution: str = ""
    assignee: str = ""
    needs_human: bool = False
    notes: list = field(default_factory=list)
    closed_at: str = ""

# ─────────────────────────────────────────────
# FASE 2: TORRE — Sistema de Auto-Preservación
# ─────────────────────────────────────────────

# ── LOG KEEPER ──

class LogKeeper:
    """Logs JSON estructurados con rotación automática.
    1 archivo por día, max 5 archivos, 1MB c/u."""

    MAX_SIZE = 1024 * 1024
    MAX_FILES = 5

    def __init__(self):
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        self._current = LOG_DIR / "digos.log"
        self._ensure_file()

    def _ensure_file(self):
        if not self._current.exists():
            self._current.write_text("")

    def _rotate(self):
        size = self._current.stat().st_size
        if size > self.MAX_SIZE:
            # Buscar slot libre
            for i in range(self.MAX_FILES - 1, 0, -1):
                old = LOG_DIR / f"digos.{i}.log"
                if old.exists():
                    if i == self.MAX_FILES - 1:
                        old.unlink()
                    else:
                        old.rename(LOG_DIR / f"digos.{i+1}.log")
            self._current.rename(LOG_DIR / "digos.1.log")
            self._current = LOG_DIR / "digos.log"
            self._ensure_file()

    def _log(self, level: str, source: str, message: str, extra: dict = None):
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "source": source,
            "msg": message,
        }
        if extra:
            entry["extra"] = extra
        line = json.dumps(entry, default=str)
        try:
            self._rotate()
            with open(self._current, "a") as f:
                f.write(line + "\n")
        except OSError:
            pass

    def info(self, source: str, msg: str, extra: dict = None):
        self._log("INFO", source, msg, extra)

    def warn(self, source: str, msg: str, extra: dict = None):
        self._log("WARN", source, msg, extra)

    def error(self, source: str, msg: str, extra: dict = None):
        self._log("ERROR", source, msg, extra)

    def tail(self, n: int = 20) -> List[dict]:
        if not self._current.exists():
            return []
        with open(self._current) as f:
            lines = f.readlines()
        result = []
        for l in lines[-n:]:
            try:
                result.append(json.loads(l))
            except json.JSONDecodeError:
                continue
        return result

    def get_logs(self, level: str = None, source: str = None, limit: int = 50) -> List[dict]:
        """Filtra logs por nivel y/o fuente."""
        logs = self.tail(limit * 3)
        result = []
        for entry in logs:
            if level and entry.get("level") != level:
                continue
            if source and entry.get("source") != source:
                continue
            result.append(entry)
            if len(result) >= limit:
                break
        return result

# ── CENTINELA ──

class Centinela:
    """Detecta defectos en API keys, tokens y alarmas internas.
    NO reinicia gateways. NO diagnostica.
    3 fallos consecutivos → reporta al System Engineer."""

    def __init__(self, log_keeper: LogKeeper):
        self.log = log_keeper
        self._strikes = self._load_strikes()
        self._reported = set()

    def _load_strikes(self) -> dict:
        if STRIKES_FILE.exists():
            try:
                return json.loads(STRIKES_FILE.read_text())
            except (json.JSONDecodeError, ValueError):
                pass
        return {}

    def _save_strikes(self):
        STRIKES_FILE.write_text(json.dumps(self._strikes, indent=2))

    def _key(self, check_type: str, identifier: str) -> str:
        return f"{check_type}:{identifier}"

    def check_api_key(self, provider_id: str, api_key: str) -> bool:
        """Prueba una API key. Retorna True si OK, False si defecto."""
        provider = PROVIDERS.get(provider_id)
        if not provider or not provider.get("test_url"):
            return True

        url = provider["test_url"]
        auth = provider["auth"]
        k = self._key("api_key", provider_id)

        try:
            req = Request(url)
            if auth == "bearer":
                req.add_header("Authorization", f"Bearer {api_key}")
            elif auth == "x-api-key":
                req.add_header("x-api-key", api_key)
            elif auth == "query":
                req = Request(url + api_key)

            with urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    self._clear(k)
                    return True
                self._strike(k, f"HTTP {resp.status}")
                return False
        except HTTPError as e:
            self._strike(k, f"HTTP {e.code}")
            return False
        except (URLError, socket.timeout, OSError) as e:
            self._strike(k, f"conexión: {e}")
            return False

    def check_telegram_token(self, token: str) -> bool:
        """Prueba un token de Telegram. Retorna True si OK."""
        k = self._key("telegram", "bot")
        try:
            req = Request(f"https://api.telegram.org/bot{token}/getMe")
            with urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                if data.get("ok"):
                    self._clear(k)
                    return True
                self._strike(k, "token inválido")
                return False
        except (HTTPError, URLError, socket.timeout, json.JSONDecodeError) as e:
            self._strike(k, f"error: {e}")
            return False

    def _strike(self, k: str, reason: str):
        if k not in self._strikes:
            self._strikes[k] = {"count": 0, "reason": "", "last": ""}
        self._strikes[k]["count"] += 1
        self._strikes[k]["reason"] = reason
        self._strikes[k]["last"] = datetime.now(timezone.utc).isoformat()
        self._save_strikes()
        self.log.warn("centinela", f"Strike {self._strikes[k]['count']}/{STRIKE_LIMIT}: {k} — {reason}")

    def _clear(self, k: str):
        if k in self._strikes:
            del self._strikes[k]
            self._save_strikes()

    def get_reports(self) -> List[dict]:
        """Retorna defectos con strike limit alcanzado y no reportados."""
        reports = []
        for k, data in self._strikes.items():
            if data["count"] >= STRIKE_LIMIT:
                reports.append({
                    "target": k,
                    "strikes": data["count"],
                    "reason": data["reason"],
                    "last": data["last"]
                })
        return reports

    def get_all_strikes(self) -> dict:
        return dict(self._strikes)

    def reset_strikes(self, target: str):
        if target in self._strikes:
            del self._strikes[target]
            self._save_strikes()

# ── SYSTEM ENGINEER ──

class SystemEngineer:
    """Recibe reportes, crea tickets ligados a perfiles.

    Cada ticket vive en el folder del perfil al que pertenece:
      ~/.digos/profiles/{perfil}/TICKETS/{numero}/
        ├── ticket.json    → datos del ticket
        └── notes.md       → notas de resolución (opcional)

    La memoria del perfil y sus tickets viajan JUNTOS.
    Si se restaura un perfil, se restauran todos sus tickets.
    """

    def __init__(self, log_keeper: LogKeeper):
        self.log = log_keeper
        self._profiles_dir = DIGOS_DIR / "profiles"
        self._tickets_cache: Dict[str, dict] = {}
        self._index_file = DIGOS_DIR / "tickets_index.json"
        self._index = self._load_index()

    def _ticket_dir(self, profile: str, ticket_id: str) -> Path:
        """Ruta al folder de un ticket específico."""
        return self._profiles_dir / profile / "TICKETS" / ticket_id

    def _ticket_file(self, profile: str, ticket_id: str) -> Path:
        """Ruta al archivo ticket.json de un ticket."""
        return self._ticket_dir(profile, ticket_id) / "ticket.json"

    def _ensure_ticket_dir(self, profile: str, ticket_id: str):
        """Crea el directorio del ticket si no existe."""
        self._ticket_dir(profile, ticket_id).mkdir(parents=True, exist_ok=True)

    # ── Índice de tickets (ControlTower) ─────

    def _load_index(self) -> dict:
        """Carga el índice de tickets de ControlTower."""
        if self._index_file.exists():
            try:
                return json.loads(self._index_file.read_text())
            except Exception:
                pass
        return {"profiles": {}, "total": 0, "open_count": 0}

    def _save_index(self):
        """Guarda el índice de tickets."""
        self._index_file.write_text(json.dumps(self._index, indent=2))

    def _update_index(self, profile: str, ticket: dict):
        """Actualiza el índice cuando se crea/modifica un ticket."""
        tid = ticket.get("id", "000")
        status = ticket.get("status", "open")
        severity = ticket.get("severity", "medium")

        if profile not in self._index["profiles"]:
            self._index["profiles"][profile] = {
                "ticket_count": 0,
                "open_count": 0,
                "last_ticket": "",
                "last_updated": "",
            }

        p_idx = self._index["profiles"][profile]
        p_idx["ticket_count"] = len(self.get_profile_tickets(profile))
        p_idx["last_ticket"] = tid
        p_idx["last_updated"] = datetime.now(timezone.utc).isoformat()

        # Recalcular abiertos
        open_t = [t for t in self.get_profile_tickets(profile)
                 if t.get("status") not in ("closed", "resolved")]
        p_idx["open_count"] = len(open_t)

        # Totales globales
        total = 0
        open_total = 0
        for p, idx in self._index["profiles"].items():
            total += idx["ticket_count"]
            open_total += idx["open_count"]
        self._index["total"] = total
        self._index["open_count"] = open_total
        self._save_index()

    def rebuild_index(self):
        """Reconstruye el índice completo desde cero. Útil después de restauración."""
        self._index = {"profiles": {}, "total": 0, "open_count": 0}
        if not self._profiles_dir.is_dir():
            self._save_index()
            return
        for p_dir in sorted(self._profiles_dir.iterdir()):
            if p_dir.is_dir() and not p_dir.name.startswith("."):
                tickets = self.get_profile_tickets(p_dir.name)
                if tickets:
                    profile = p_dir.name
                    open_t = [t for t in tickets
                            if t.get("status") not in ("closed", "resolved")]
                    self._index["profiles"][profile] = {
                        "ticket_count": len(tickets),
                        "open_count": len(open_t),
                        "last_ticket": tickets[-1].get("id", ""),
                        "last_updated": tickets[-1].get("created_at", ""),
                    }
        self._index["total"] = sum(
            p["ticket_count"] for p in self._index["profiles"].values())
        self._index["open_count"] = sum(
            p["open_count"] for p in self._index["profiles"].values())
        self._save_index()

    def index_summary(self) -> str:
        """Resumen rápido desde el índice."""
        p_count = len(self._index.get("profiles", {}))
        return (f"{self._index.get('total', 0)} tickets, "
                f"{self._index.get('open_count', 0)} abiertos, "
                f"en {p_count} perfil(es)")

    def _next_id_for_profile(self, profile: str) -> str:
        """Genera el siguiente ID de ticket para un perfil."""
        tickets_dir = self._profiles_dir / profile / "TICKETS"
        if not tickets_dir.is_dir():
            return "001"
        existing = []
        for d in tickets_dir.iterdir():
            if d.is_dir() and d.name.isdigit():
                existing.append(int(d.name))
        next_num = (max(existing) + 1) if existing else 1
        return f"{next_num:03d}"

    def _load_ticket(self, profile: str, ticket_id: str) -> Optional[dict]:
        """Carga un ticket desde su archivo."""
        tf = self._ticket_file(profile, ticket_id)
        if not tf.exists():
            return None
        try:
            return json.loads(tf.read_text())
        except Exception:
            return None

    def _save_ticket(self, profile: str, ticket: dict):
        """Guarda un ticket en su archivo y actualiza el índice."""
        tid = ticket.get("id", "000")
        self._ensure_ticket_dir(profile, tid)
        tf = self._ticket_file(profile, tid)
        tf.write_text(json.dumps(ticket, indent=2))
        self._tickets_cache[f"{profile}:{tid}"] = ticket
        self._update_index(profile, ticket)
        self.log.info("engineer", f"Ticket #{tid} guardado en perfil '{profile}'")

    # ── Crear tickets ─────────────────────

    def receive_report(self, report: dict) -> str:
        """Centinela envía un reporte. Engineer crea ticket ligado al perfil."""
        profile = report.get("profile", "system")
        tid = self._next_id_for_profile(profile)
        target = report.get("target", "")
        sev = "high" if ("api_key" in target or "telegram" in target) else "medium"

        ticket = Ticket(
            id=tid,
            profile=profile,
            source="centinela",
            target=target,
            problem=f"{report.get('strikes', 3)} fallos: {report.get('reason', 'desconocido')}",
            severity=sev,
            status="open",
            created_at=datetime.now(timezone.utc).isoformat()
        )
        t_dict = asdict(ticket)
        self._save_ticket(profile, t_dict)

        self.log.warn("engineer", f"Ticket #{tid} creado para '{profile}': {target}",
                       {"severity": sev})
        self._diagnose(profile, tid)
        return tid

    def create_ticket(self, profile: str, target: str, problem: str,
                      severity: str = "medium", source: str = "manual") -> str:
        """Crea un ticket manual ligado a un perfil específico."""
        tid = self._next_id_for_profile(profile)

        ticket = Ticket(
            id=tid,
            profile=profile,
            source=source,
            target=target,
            problem=problem,
            severity=severity,
            status="open",
            created_at=datetime.now(timezone.utc).isoformat()
        )
        self._save_ticket(profile, asdict(ticket))
        self.log.info("engineer", f"Ticket #{tid} creado para '{profile}': {target}")
        return tid

    # ── Diagnóstico ───────────────────────

    def _diagnose(self, profile: str, tid: str):
        """Diagnóstico automático del problema."""
        ticket = self._load_ticket(profile, tid)
        if not ticket:
            return

        ticket["status"] = "diagnosing"
        target = ticket["target"]

        if target.startswith("api_key:"):
            provider = target.split(":", 1)[1]
            ticket["diagnosis"] = f"API key de {provider} rechazada — expirada, sin saldo o revocada"
        elif target.startswith("telegram"):
            ticket["diagnosis"] = "Token de Telegram rechazado — revocado o inválido"
        else:
            ticket["diagnosis"] = "Fallo desconocido — requiere revisión manual"

        ticket["needs_human"] = True
        self._save_ticket(profile, ticket)
        self.log.info("engineer", f"Ticket #{tid} diagnóstico: {ticket['diagnosis']}")

    # ── Gestión de tickets ────────────────

    def assign_ticket(self, profile: str, tid: str, assignee: str) -> bool:
        """Asigna un ticket a un sub-ingeniero."""
        ticket = self._load_ticket(profile, tid)
        if not ticket:
            return False
        ticket["assignee"] = assignee
        ticket["status"] = "assigned"
        self._save_ticket(profile, ticket)
        self.log.info("engineer", f"Ticket #{tid} asignado a {assignee}")
        return True

    def update_status(self, profile: str, tid: str, status: str) -> bool:
        """Actualiza el estado de un ticket."""
        ticket = self._load_ticket(profile, tid)
        if not ticket:
            return False
        ticket["status"] = status
        self._save_ticket(profile, ticket)
        return True

    def add_note(self, profile: str, tid: str, note: str) -> bool:
        """Agrega una nota a un ticket."""
        ticket = self._load_ticket(profile, tid)
        if not ticket:
            return False
        if "notes" not in ticket:
            ticket["notes"] = []
        ticket["notes"].append({
            "text": note,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        self._save_ticket(profile, ticket)
        return True

    def close_ticket(self, profile: str, tid: str, resolution: str = "") -> bool:
        """Cierra un ticket con resolución."""
        ticket = self._load_ticket(profile, tid)
        if not ticket:
            return False
        ticket["status"] = "closed"
        ticket["resolution"] = resolution
        ticket["closed_at"] = datetime.now(timezone.utc).isoformat()
        self._save_ticket(profile, ticket)
        self.log.info("engineer", f"Ticket #{tid} cerrado: {resolution}")
        return True

    # ── Consultas ─────────────────────────

    def get_profile_tickets(self, profile: str, status: str = "") -> List[dict]:
        """Retorna todos los tickets de un perfil. Opcionalmente filtrar por status."""
        tickets_dir = self._profiles_dir / profile / "TICKETS"
        if not tickets_dir.is_dir():
            return []
        tickets = []
        for d in sorted(tickets_dir.iterdir()):
            if d.is_dir() and d.name.isdigit():
                t = self._load_ticket(profile, d.name)
                if t and (not status or t.get("status") == status):
                    tickets.append(t)
        return tickets

    def get_all_open(self) -> List[dict]:
        """Retorna todos los tickets abiertos de todos los perfiles."""
        open_tickets = []
        if not self._profiles_dir.is_dir():
            return []
        for p_dir in sorted(self._profiles_dir.iterdir()):
            if p_dir.is_dir() and not p_dir.name.startswith("."):
                tickets = self.get_profile_tickets(p_dir.name)
                for t in tickets:
                    if t.get("status") not in ("closed", "resolved"):
                        open_tickets.append(t)
        return open_tickets

    def get_by_source(self, source: str) -> List[dict]:
        """Retorna tickets filtrados por fuente."""
        results = []
        if not self._profiles_dir.is_dir():
            return []
        for p_dir in sorted(self._profiles_dir.iterdir()):
            if p_dir.is_dir() and not p_dir.name.startswith("."):
                tickets = self.get_profile_tickets(p_dir.name)
                for t in tickets:
                    if t.get("source") == source:
                        results.append(t)
        return results

    def get_by_assignee(self, assignee: str) -> List[dict]:
        """Retorna tickets asignados a un sub-ingeniero."""
        results = []
        if not self._profiles_dir.is_dir():
            return []
        for p_dir in sorted(self._profiles_dir.iterdir()):
            if p_dir.is_dir() and not p_dir.name.startswith("."):
                tickets = self.get_profile_tickets(p_dir.name)
                for t in tickets:
                    if t.get("assignee") == assignee:
                        results.append(t)
        return results

    def summary(self) -> str:
        """Resumen de tickets del sistema."""
        total = 0
        open_count = 0
        profiles_with_tickets = 0
        if not self._profiles_dir.is_dir():
            return "0 tickets — sin perfiles"
        for p_dir in sorted(self._profiles_dir.iterdir()):
            if p_dir.is_dir() and not p_dir.name.startswith("."):
                tickets = self.get_profile_tickets(p_dir.name)
                if tickets:
                    profiles_with_tickets += 1
                    total += len(tickets)
                    for t in tickets:
                        if t.get("status") not in ("closed", "resolved"):
                            open_count += 1
        return f"{total} tickets, {open_count} abiertos, en {profiles_with_tickets} perfil(es)"

    def resolve(self, tid: str, resolution: str):
        """Legacy: resolver ticket por ID global. Busca en todos los perfiles."""
        if not self._profiles_dir.is_dir():
            return
        for p_dir in sorted(self._profiles_dir.iterdir()):
            if p_dir.is_dir() and not p_dir.name.startswith("."):
                tickets = self.get_profile_tickets(p_dir.name)
                for t in tickets:
                    if t.get("id") == tid:
                        self.close_ticket(p_dir.name, tid, resolution)
                        return

    def get_open(self) -> List[dict]:
        """Legacy: retorna tickets abiertos."""
        return self.get_all_open()

    def get_all_tickets(self) -> List[dict]:
        """Retorna TODOS los tickets de todos los perfiles."""
        all_tickets = []
        if not self._profiles_dir.is_dir():
            return []
        for p_dir in sorted(self._profiles_dir.iterdir()):
            if p_dir.is_dir() and not p_dir.name.startswith("."):
                all_tickets.extend(self.get_profile_tickets(p_dir.name))
        return all_tickets

    def get_ticket(self, tid: str) -> Optional[dict]:
        """Busca un ticket por su ID en todos los perfiles."""
        if not self._profiles_dir.is_dir():
            return None
        for p_dir in sorted(self._profiles_dir.iterdir()):
            if p_dir.is_dir() and not p_dir.name.startswith("."):
                t = self._load_ticket(p_dir.name, tid)
                if t:
                    return t
        return None

# ── SELF-AWARENESS CORE ──

class SelfAwarenessCore:
    """Identidad + máquina de estados del agente.
    Estados: INICIANDO → ACTIVO ↔ EN_PAUSA / ERROR → ACTIVO"""

    VALID_STATES = ["INICIANDO", "ACTIVO", "EN_PAUSA", "ERROR"]

    def __init__(self, log_keeper: LogKeeper):
        self.log = log_keeper
        self._identity = {
            "name": "DIGOS Agent",
            "version": VERSION,
            "purpose": "Agente inteligente con auto-preservación",
            "born": datetime.now(timezone.utc).isoformat()
        }
        self._state = "INICIANDO"
        self._load()
        self._persist()

    def _load(self):
        if SELF_FILE.exists():
            try:
                data = json.loads(SELF_FILE.read_text())
                self._state = data.get("state", "INICIANDO")
                if data.get("identity"):
                    self._identity.update(data["identity"])
            except (json.JSONDecodeError, ValueError):
                pass

    def _persist(self):
        data = {
            "state": self._state,
            "identity": self._identity,
            "updated": datetime.now(timezone.utc).isoformat()
        }
        SELF_FILE.write_text(json.dumps(data, indent=2))

    def _set(self, new_state: str):
        if new_state in self.VALID_STATES and new_state != self._state:
            old = self._state
            self._state = new_state
            self._persist()
            self.log.info("self", f"Estado: {old} → {new_state}")

    @property
    def state(self) -> str:
        return self._state

    @property
    def identity(self) -> dict:
        return dict(self._identity)

    def activate(self):
        self._set("ACTIVO")

    def pause(self):
        self._set("EN_PAUSA")

    def set_error(self):
        self._set("ERROR")

    def recover(self):
        self._set("ACTIVO")

    def status(self) -> dict:
        return {
            "state": self._state,
            "identity": self._identity,
            "version": VERSION
        }

# ─────────────────────────────────────────────
# CONTROL TOWER — la entidad ÚNICA
# Ahora con TORRE integrado
# ─────────────────────────────────────────────

class ControlTower:
    """Control Tower nace primero. Guía todo el onboarding.
    Contiene a Caja Segura y ahora a TORRE (auto-preservación).
    Puede vivir 24/7 como daemon."""

    def __init__(self, daemon_mode: bool = False):
        self._ensure_dirs()
        self.state = self._load_state()
        self.lang = self.state.get("language", "en")
        self._caja = CajaSeguraInfo()

        # TORRE: componentes de auto-preservación
        self._log = LogKeeper()
        self._self_awareness = SelfAwarenessCore(self._log)
        self._centinela = Centinela(self._log)
        self._engineer = SystemEngineer(self._log)

        # Fase 3: Gateways
        self._gateways: Dict[str, BaseGateway] = {}

        # Fase 4: Transparencia — tracker de progreso
        self._tracker: Optional[ToolProgressTracker] = None

        # Fase 4b: AIAgent — LLM + tool calling
        self._agent: Optional[AIAgent] = None

        # Fase 6: Message Bus — comunicación multi-agente
        self._bus: Optional[MessageBus] = None

        self._daemon_mode = daemon_mode
        self._running = False
        self._cycle_count = 0

        if daemon_mode:
            self._self_awareness.activate()

    def _ensure_dirs(self):
        DIGOS_DIR.mkdir(parents=True, exist_ok=True)
        LOG_DIR.mkdir(parents=True, exist_ok=True)

    def _load_state(self) -> dict:
        if STATE_FILE.exists():
            try:
                return json.loads(STATE_FILE.read_text())
            except (json.JSONDecodeError, ValueError):
                pass
        return {"setup_complete": False, "version": VERSION}

    def _save_state(self):
        STATE_FILE.write_text(json.dumps(self.state, indent=2))

    # ── RUN ──

    def run(self):
        if self._daemon_mode:
            self._run_daemon()
            return

        self._show_banner()
        if self.state.get("setup_complete"):
            print("\n✅ DIGOS ya está configurado. Iniciando agente...")
            self._handoff()
        else:
            self._onboarding()

    # ── BANNER ──

    def _show_banner(self):
        print()
        print("  ╔══════════════════════════════════════╗")
        print("  ║         D I G O S   v0.2             ║")
        print("  ║    Intelligent Agent System          ║")
        print("  ║    Fase 2: TORRE activa              ║")
        print("  ╚══════════════════════════════════════╝")
        print()

    # ── ONBOARDING FLOW ──

    def _onboarding(self):
        print("🔧 PRIMERA CONFIGURACIÓN")
        print("━━━━━━━━━━━━━━━━━━━━━━━")
        print()

        # Paso 1: Idioma — SIEMPRE primero, el usuario debe entender
        self._step_language()

        # Paso 2: Adoption — detectar y migrar desde Hermes/OpenClaw
        # (después de idioma para que el usuario entienda las opciones)
        self._step_adoption()

        # Paso 3: API Key + Provider → aquí nace el agente
        # Si adoption ya importó credenciales, se saltan pasos manuales
        imported_key = self.state.get("_adopted_api_key", "")
        imported_provider = self.state.get("_adopted_provider", "")
        if imported_key and imported_provider:
            provider_id = imported_provider
            api_key = imported_key
            provider = PROVIDERS.get(provider_id, {})
            print(f"  🔑 Usando API Key importada: {provider.get('name', provider_id)}")
            print()
        else:
            provider_id, api_key = self._step_api_key()

        # 🎯 El agente nace aquí
        self._birth_agent(provider_id)

        # Paso 4: Gateway + Token
        # Si adoption ya importó gateway token, saltar configuración manual
        imported_gw_token = self.state.get("_adopted_gateway_token", "")
        imported_gw_type = self.state.get("_adopted_gateway_type", "")
        if imported_gw_token and imported_gw_type:
            gateway_id = imported_gw_type
            gateway_token = imported_gw_token
            print(f"  📡 Usando gateway importado: {imported_gw_type}")
            print()
        else:
            gateway_id, gateway_token = self._step_gateway()

        # Paso 5: Caja Segura guarda las credenciales
        self._step_vault(api_key, gateway_token)

        # Paso 6: Finalizar y Handoff
        self._finalize_setup(provider_id, gateway_id)
        self._log.info("tower", "Onboarding completado",
                       {"provider": provider_id, "gateway": gateway_id})
        self._handoff()

    # ── Paso 2: Adoption ──

    def _step_adoption(self):
        """Paso 2 del onboarding: detecta Hermes/OpenClaw, migra y transforma.
        Se ejecuta DESPUÉS de la selección de idioma.
        """
        engine = AdoptionEngine()
        transformer = TransformationEngine()
        sources = engine.detect_sources()

        if not sources:
            self._log.info("tower", "Adoption: no se detectaron sistemas existentes")
            return

        print()
        print("🔄 ADOPCIÓN — SISTEMAS EXISTENTES DETECTADOS")
        print("━" * 45)
        source_labels = {"hermes": "Hermes Agent", "openclaw": "Open Cloud"}
        for s in sources:
            label = source_labels.get(s, s)
            print(f"  📡 Detectado: {label}")
        print()
        print("  DIGOS puede importar tu configuración, perfiles,")
        print("  API keys, skills y memorias desde estos sistemas.")
        print()

        if not self._confirm("¿Quieres ver qué se puede importar?"):
            print("  Saltando adopción. Puedes migrar después manualmente.")
            self._log.info("tower", "Adoption: usuario saltó la migración")
            return

        for source in sources:
            label = source_labels.get(source, source)
            print(f"\n  ── Explorando {label} ──")

            # Dry-run: descubrir y mostrar preview
            engine.discover(source)
            if not engine._report.items_migrated:
                print(f"  📭 No se encontró nada para importar desde {label}")
                continue

            engine.print_preview(engine._report)

            if not self._confirm("\n  ¿Proceder con la migración?"):
                print(f"  Migración de {label} cancelada.")
                self._log.info("tower", f"Adoption: {source} cancelada por usuario")
                continue

            # ── Fase 1: Migrar archivos ──
            print(f"\n  ⏳ Migrando {label}...")
            result = engine.migrate(engine._report, execute=True)
            engine.print_report(result)

            if result.items_migrated:
                self._log.info("tower",
                    f"Adoption: {len(result.items_migrated)} items migrados desde {source}")

                # Extraer credenciales migradas y guardarlas en estado
                for item in result.items_migrated:
                    if item.kind == "api_key" and not self.state.get("_adopted_api_key"):
                        # Buscar en el .env del perfil principal
                        env_val = self._extract_adopted_env(item, "DEEPSEEK_API_KEY")
                        if env_val:
                            self.state["_adopted_api_key"] = env_val
                            self.state["_adopted_provider"] = "4"  # deepseek
                    if item.kind == "telegram_token" and not self.state.get("_adopted_gateway_token"):
                        env_val = self._extract_adopted_env(item, "TELEGRAM_BOT_TOKEN")
                        if env_val:
                            self.state["_adopted_gateway_token"] = env_val
                            self.state["_adopted_gateway_type"] = "1"  # telegram
                self._save_state()

            # ── Fase 2: Caja Segura — escanear perfiles por inyección ──
            profiles = [p for p in result.profiles_found
                       if p != "global"]
            if profiles:
                caja = SecurityCaja()
                print(f"\n  🔒 Caja Segura escaneando perfiles...")
                for profile in profiles:
                    profile_dir = DIGOS_DIR / "profiles" / profile
                    if not profile_dir.exists():
                        continue
                    print(f"    Escaneando: {profile}")
                    sr = caja.scan_profile(profile_dir)
                    if sr.items_blocked > 0:
                        print(f"    ❌ {profile}: BLOQUEADO — {sr.items_blocked} hallazgo(s) crítico(s)")
                        caja.print_scan_report(sr)
                        if not self._confirm(f"    ¿Ignorar y forzar importación de {profile}?"):
                            print(f"    Perfil {profile} excluido por seguridad.")
                            continue
                    elif sr.items_cleaned > 0:
                        print(f"    ⚠️  {profile}: {sr.items_cleaned} archivo(s) limpiados")
                        caja.print_scan_report(sr)
                    else:
                        print(f"    ✅ {profile}: Sin hallazgos")
                caja.print_audit()

            # ── Fase 3: Transformar perfiles (ControlTower toma dominio) ──
            profiles = [p for p in result.profiles_found
                       if p != "global"]
            if profiles:
                print(f"\n  🏰 Control Tower transformando perfiles...")
                for profile in profiles:
                    print(f"    Procesando: {profile}")
                    t_result = transformer.transform_profile(profile)
                    if t_result["ok"]:
                        for t in t_result["transformations"]:
                            print(f"      ✅ {t}")
                    if t_result["errors"]:
                        for e in t_result["errors"]:
                            print(f"      ❌ {e}")
                transformer.print_report()

            print(f"\n  ✅ Adopción de {label} completada.")

        # Si se migró algo, ofrecer continuar con setup ya configurado
        print()
        print("  Puedes continuar con la configuración manual para")
        print("  completar lo que no se haya migrado automáticamente.")

    # ── Helpers ──

    @staticmethod
    def _confirm(question: str, default: bool = True) -> bool:
        """Pide confirmación Sí/No al usuario."""
        prompt = " (S/n): " if default else " (s/N): "
        while True:
            try:
                resp = input(question + prompt).strip().lower()
                if not resp:
                    return default
                if resp in ("s", "si", "y", "yes"):
                    return True
                if resp in ("n", "no"):
                    return False
            except (EOFError, KeyboardInterrupt):
                return False
            print("  Responde 's' o 'n'.")

    @staticmethod
    def _extract_adopted_env(item, var_name: str) -> str:
        """Extrae el valor de una variable de .env desde items migrados."""
        from adoption import AdoptionEngine
        env_path = Path(item.dest_path) if item.dest_path.endswith(".env") else None
        if not env_path or not env_path.exists():
            # Intentar path alternativo para secrets globales
            alt = DIGOS_DIR / "imported" / "hermes" / ".env"
            if alt.exists():
                env_path = alt
            else:
                return ""
        secrets = AdoptionEngine._parse_env(env_path)
        return secrets.get(var_name, "")

    # ── Paso 1: Idioma ──

    def _step_language(self):
        print("🌐 IDIOMA / LANGUAGE")
        print("─" * 40)
        for k, v in LANGUAGES.items():
            print(f"  [{k}] {v['name']}")
        print()
        while True:
            choice = input("Selecciona tu idioma → ").strip()
            if choice in LANGUAGES:
                self.lang = LANGUAGES[choice]["code"]
                self.state["language"] = self.lang
                self._save_state()
                print()
                print(f"  {LANGUAGES[choice]['welcome']}")
                print()
                return
            print("  Opción inválida. Intenta de nuevo.")

    # ── Paso 3: API Key ──

    def _step_api_key(self) -> Tuple[str, str]:
        print("🔑 PROVEEDOR DE IA / AI PROVIDER")
        print("─" * 40)
        print("  Elige el proveedor para tu agente principal:")
        print()
        for k, v in PROVIDERS.items():
            print(f"  [{k}] {v['name']}  ({v['key_hint']})")
        print()

        provider_id = None
        while provider_id is None:
            choice = input("Proveedor → ").strip()
            if choice in PROVIDERS:
                provider_id = choice
            else:
                print("  Opción inválida.")

        provider = PROVIDERS[provider_id]
        print(f"\n  → Proveedor: {provider['name']}")
        print()

        api_key = None
        while api_key is None:
            raw = input(f"  Ingresa tu API Key de {provider['name']}:\n  → ").strip()
            if raw:
                api_key = raw
            else:
                print("  La API Key no puede estar vacía.")

        # Test de conexión
        print(f"\n  🔍 Probando conexión con {provider['name']}...")
        ok, msg = self._test_provider(provider_id, api_key)
        if ok:
            print(f"  ✅ {msg}")
        else:
            print(f"  ⚠️  {msg}")
            print("  Puedes continuar, pero verifica la key más tarde.")
            cont = input("  ¿Continuar de todas formas? (s/N): ").strip().lower()
            if cont != "s":
                print("  Vuelve a intentar con otra API Key.")
                return self._step_api_key()

        print()
        return provider_id, api_key

    def _test_provider(self, provider_id: str, api_key: str) -> Tuple[bool, str]:
        provider = PROVIDERS.get(provider_id)
        if not provider or not provider["test_url"]:
            return False, "No se puede probar este proveedor automáticamente."

        url = provider["test_url"]
        auth_type = provider["auth"]
        timeout = 10

        try:
            req = Request(url)
            if auth_type == "bearer":
                req.add_header("Authorization", f"Bearer {api_key}")
            elif auth_type == "x-api-key":
                req.add_header("x-api-key", api_key)
            elif auth_type == "query":
                req = Request(url + api_key)

            with urlopen(req, timeout=timeout) as resp:
                if resp.status in (200, 201, 401, 403):
                    if resp.status == 200:
                        return True, "Conexión exitosa."
                    return False, f"Endpoint OK pero key rechazada (HTTP {resp.status})."
                return True, f"Respuesta: HTTP {resp.status}."
        except HTTPError as e:
            if e.code == 401:
                return False, "API Key inválida (HTTP 401)."
            if e.code == 403:
                return False, "Acceso denegado (HTTP 403)."
            return False, f"Error HTTP {e.code}: {e.reason}"
        except URLError as e:
            return False, f"No se pudo conectar: {e.reason}"
        except socket.timeout:
            return False, "Tiempo de conexión agotado."
        except Exception as e:
            return False, f"Error: {type(e).__name__}: {e}"

    # ── 🎯 NACE EL AGENTE PRINCIPAL ──

    def _birth_agent(self, provider_id: str):
        provider = PROVIDERS[provider_id]

        agente = {
            "name": "Agente Principal",
            "born_at": datetime.utcnow().isoformat() + "Z",
            "version": VERSION,
            "provider_id": provider_id,
            "provider_name": provider["name"],
            "language": self.lang,
            "self_awareness": {
                "identity": "DIGOS Agent",
                "version": VERSION,
                "born": datetime.utcnow().isoformat() + "Z",
                "purpose": "Servir al usuario como agente inteligente."
            },
            "gps": {
                "origin": "Control Tower",
                "home": str(DIGOS_DIR),
                "state": "naciendo"
            },
            "work_destination": {
                "mode": "onboarding",
                "assigned_by": "Control Tower",
                "phase": "PUERTA"
            },
            "kendo": {
                "type": "safety_candle",
                "rules": [
                    "Proteger credenciales del usuario",
                    "No ejecutar comandos sin autorización",
                    "Reportar actividad sospechosa",
                    "Mantener integridad del sistema"
                ],
                "active": True
            }
        }

        self.state["agente"] = agente
        self._save_state()

        print(f"\n  🎯 ¡AGENTE PRINCIPAL HA NACIDO!")
        print(f"     Nombre: {agente['name']}")
        print(f"     Proveedor: {provider['name']}")
        print(f"     Self-Awareness inyectada.")
        print(f"     Safety Candle (Kendo) activo.")
        print()
        self._log.info("tower", "Agente principal ha nacido",
                       {"provider": provider["name"]})

    # ── Paso 4: Gateway ──

    def _step_gateway(self) -> Tuple[str, str]:
        print("📡 GATEWAY / CANAL DE COMUNICACIÓN")
        print("─" * 40)
        print("  Elige cómo se comunicará tu agente:")
        print()
        for k, v in GATEWAYS.items():
            name = v["name"]
            note = v.get("note", "")
            note_str = f" — {note}" if note else ""
            print(f"  [{k}] {name}{note_str}")
        print()

        gateway_id = None
        while gateway_id is None:
            choice = input("Gateway → ").strip()
            if choice in GATEWAYS:
                gateway_id = choice
            else:
                print("  Opción inválida.")

        gateway = GATEWAYS[gateway_id]
        print(f"\n  → Gateway: {gateway['name']}")
        print()

        token = ""
        if gateway["type"] == "telegram":
            token = self._setup_telegram()
        else:
            print(f"  ⏳ {gateway['name']} requiere configuración manual.")
            print(f"     {gateway.get('note', '')}")
            cont = input("  ¿Marcar como configurado más tarde? (s/N): ").strip().lower()
            if cont != "s":
                return self._step_gateway()

        print()
        return gateway_id, token

    def _setup_telegram(self) -> str:
        print("  🤖 Telegram Bot Token")
        print("  (Consíguelo en @BotFather en Telegram)")
        print()

        token = None
        while token is None:
            raw = input("  Bot Token → ").strip()
            if raw:
                token = raw
            else:
                print("  El token no puede estar vacío.")

        print(f"\n  🔍 Probando conexión con Telegram...")
        ok, msg = self._test_telegram(token)
        if ok:
            print(f"  ✅ {msg}")
            return token
        else:
            print(f"  ⚠️  {msg}")
            cont = input("  ¿Continuar de todas formas? (s/N): ").strip().lower()
            if cont == "s":
                return token
            return self._setup_telegram()

    def _test_telegram(self, token: str) -> Tuple[bool, str]:
        url = f"https://api.telegram.org/bot{token}/getMe"
        try:
            with urlopen(url, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                if data.get("ok") and "result" in data:
                    bot_name = data["result"].get("first_name", "Bot")
                    username = data["result"].get("username", "?")
                    return True, f"Bot '{bot_name}' (@{username}) conectado."
                return False, "Token inválido."
        except HTTPError as e:
            return False, f"Token rechazado (HTTP {e.code})."
        except URLError as e:
            return False, f"No se pudo conectar: {e.reason}"
        except json.JSONDecodeError:
            return False, "Respuesta inesperada del servidor."
        except Exception as e:
            return False, f"Error: {e}"

    # ── Paso 5: Caja Segura ──

    def _step_vault(self, api_key: str, gateway_token: str):
        print("🔒 CAJA SEGURA")
        print("─" * 40)
        print("  Guardando credenciales de forma segura...")

        secrets = {
            "api_key": api_key,
            "gateway_token": gateway_token,
            "provider_id": self.state.get("agente", {}).get("provider_id", ""),
            "created_at": self.state.get("agente", {}).get("born_at", "")
        }

        try:
            encrypted = CajaSeguraInfo.encrypt(json.dumps(secrets).encode())
            VAULT_FILE.write_bytes(encrypted)
            VAULT_FILE.chmod(0o600)
            print("  ✅ Credenciales encriptadas y almacenadas.")
        except Exception as e:
            print(f"  ⚠️  Error al guardar credenciales: {e}")

        print()

    # ── Paso 6: Finalizar Setup + Handoff ──

    def _finalize_setup(self, provider_id: str, gateway_id: str):
        agente = self.state.get("agente", {})
        agente["gateway_type"] = GATEWAYS[gateway_id]["type"]
        agente["gateway_configured"] = True
        agente["setup_complete"] = True
        agente["work_destination"] = {
            "mode": "activo",
            "assigned_by": "Control Tower",
            "phase": "VUELO"
        }
        agente["gps"]["state"] = "activo"

        self.state["setup_complete"] = True
        self.state["agente"] = agente
        self.state["gateway"] = {"id": gateway_id, "type": GATEWAYS[gateway_id]["type"]}
        self.state["version"] = VERSION
        self._save_state()

    def _handoff(self):
        agente = self.state.get("agente", {})
        print("  ╔══════════════════════════════════════╗")
        print("  ║     🚀  HANDOFF COMPLETADO           ║")
        print("  ║                                      ║")
        print("  ║  Control Tower entrega el control    ║")
        print("  ║  al Agente Principal.                ║")
        print("  ║  TORRE: Centinela + Engineer activos ║")
        print("  ╚══════════════════════════════════════╝")
        print()
        print(f"     Agente:   {agente.get('name', 'Principal')}")
        print(f"     Proveedor: {agente.get('provider_name', '?')}")
        print(f"     Gateway:  {agente.get('gateway_type', '?')}")
        print(f"     Estado:   ✅ Activo")
        print()
        print("  El agente ya está listo para recibir instrucciones.")
        print("  TORRE vigila en segundo plano.")
        print()

        # Iniciar automáticamente en modo daemon
        if not self._daemon_mode and self.state.get("setup_complete"):
            if self._confirm("  ¿Iniciar DIGOS en modo 24/7?"):
                print("\n  🚀 Iniciando modo daemon...")
                self._daemon_mode = True
                self._running = True
                self._self_awareness.activate()
                self._init_gateways()
                self._init_bus()
                self._init_agent()
                self._run_daemon()
        else:
            print("  Usa: digos --daemon para iniciar modo 24/7")
            print()

    # ── DAEMON MODE ──

    def _run_daemon(self):
        """Modo daemon: Control Tower vive 24/7 con TORRE activo."""
        self._running = True
        self._self_awareness.activate()

        # Inicializar gateways de Fase 3
        self._init_gateways()

        # Inicializar Message Bus de Fase 6
        self._init_bus()

        # Auto-launch: asegurar que DIGOS vive 24/7
        self._ensure_launchd()

        # Manejar señal SIGTERM/SIGINT para shutdown limpio
        def _handle_signal(sig, frame):
            self._running = False
            self._log.info("tower", "Señal de parada recibida")
            # Detener gateways
            for gw in self._gateways.values():
                try:
                    gw.stop()
                except Exception:
                    pass
            # Detener Message Bus
            if self._bus:
                try:
                    self._bus.stop()
                except Exception:
                    pass
            self._self_awareness.pause()

        signal.signal(signal.SIGTERM, _handle_signal)
        signal.signal(signal.SIGINT, _handle_signal)

        print(f"\n  🏗️  TORRE DAEMON — v{VERSION}")
        print("  ─────────────────────────────")
        print(f"  Centinela: cada {CENTINELA_INTERVAL}s")
        print(f"  Logs:      {LOG_DIR}")
        print(f"  Estado:    {self._self_awareness.state}")
        print()

        self._log.info("tower", "Daemon iniciado",
                       {"interval": CENTINELA_INTERVAL})

        while self._running:
            try:
                self._cycle_count += 1
                self._log.info("tower", f"Ciclo #{self._cycle_count}")

                # 1. Centinela: revisa API keys y tokens
                self._centinela_cycle()

                # 2. Gateway health check
                self._gateway_health_check()

                # 3. Engineer: procesa reportes pendientes
                self._engineer_cycle()

                # 4. Poll gateways por mensajes entrantes (cada 2s)
                for _ in range(CENTINELA_INTERVAL // 2):
                    if not self._running:
                        break
                    self._poll_gateways()
                    time.sleep(2)

            except Exception as e:
                self._log.error("tower", f"Error en ciclo daemon: {e}")
                self._self_awareness.set_error()
                time.sleep(10)

        self._self_awareness.pause()
        self._log.info("tower", "Daemon detenido")

    def _centinela_cycle(self):
        """Un ciclo de checks del Centinela."""
        vault = CajaSeguraInfo.read_vault()
        if not vault:
            self._log.info("centinela", "No hay vault — saltando checks")
            return

        api_key = vault.get("api_key", "")
        provider_id = vault.get("provider_id", "")
        gateway_token = vault.get("gateway_token", "")

        # Check API key
        api_ok = self._centinela.check_api_key(provider_id, api_key)
        self._log.info("centinela", f"API key check: {'OK' if api_ok else 'FALLO'}")

        # Check Telegram token
        if gateway_token:
            tg_ok = self._centinela.check_telegram_token(gateway_token)
            self._log.info("centinela", f"Telegram token: {'OK' if tg_ok else 'FALLO'}")

        # Procesar reportes
        reports = self._centinela.get_reports()
        for report in reports:
            tid = self._engineer.receive_report(report)
            self._log.warn("tower", f"Reporte generado → Ticket #{tid}")
            print(f"\n  ⚠️  CENTINELA DETECTÓ DEFECTO: {report['target']}")
            print(f"     → Ticket #{tid} creado con System Engineer")
            print(f"     → Diagnóstico: {self._engineer.get_ticket(tid).get('diagnosis', 'pendiente')}")
            print()

    def _engineer_cycle(self):
        """Procesa tickets abiertos del Engineer."""
        open_tickets = self._engineer.get_open()
        for ticket in open_tickets:
            if ticket.get("needs_human"):
                # Escalación: necesita intervención humana
                self._log.warn("engineer",
                    f"Ticket #{ticket['id']} necesita usuario: {ticket['diagnosis']}")

    # ── ESTADO ──

    def status(self) -> dict:
        """Estado completo del sistema — incluido TORRE."""
        agente = self.state.get("agente", {})

        print()
        print("📊 ESTADO DE DIGOS v" + VERSION)
        print("━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"  Setup:       {'✅ Completo' if self.state.get('setup_complete') else '⏳ Pendiente'}")
        print(f"  Idioma:      {self.state.get('language', '?')}")
        if agente:
            print(f"  Agente:      {agente.get('name', '?')}")
            print(f"  Proveedor:   {agente.get('provider_name', '?')}")
            print(f"  Gateway:     {agente.get('gateway_type', '?')}")
            print(f"  Kendo:       {'✅ Activo' if agente.get('kendo', {}).get('active') else '❌ Inactivo'}")
        print()
        print("  ── TORRE (Auto-Preservación) ──")
        sa = self._self_awareness.status()
        print(f"  Self-Awareness: {sa['state']}")
        print(f"  Identidad:      {sa['identity']['name']} v{sa['identity']['version']}")
        print()

        # Centinela strikes
        strikes = self._centinela.get_all_strikes()
        if strikes:
            print(f"  ⚠️  Centinela — Strikes activos:")
            for k, v in strikes.items():
                print(f"     {k}: {v['count']}/{STRIKE_LIMIT} — {v.get('reason', '')}")
        else:
            print("  ✅ Centinela — Sin defectos detectados")
        print()

        # Engineer tickets
        open_tickets = self._engineer.get_open()
        if open_tickets:
            print(f"  ⚠️  System Engineer — Tickets abiertos: {len(open_tickets)}")
            for t in open_tickets[:3]:
                print(f"     #{t['id']} [{t['severity']}] {t['target']}: {t['diagnosis'] or t['problem']}")
        else:
            print("  ✅ System Engineer — Sin tickets abiertos")
        print()

        total_tickets = len(self._engineer.get_all_tickets())
        print(f"  Total tickets creados: {total_tickets}")
        print()

        # Gateways
        self.gateway_show_status()

    # ── COMANDOS DE TORRE ──

    def centinela_run_once(self):
        """Ejecuta un ciclo de checks del Centinela una vez (modo CLI)."""
        print("\n  🔍 CENTINELA — Ejecutando checks...")
        print("  ─────────────────────────────")
        self._centinela_cycle()
        print("  ✅ Ciclo completado.")
        print()

    def engineer_show_tickets(self, status: str = None):
        """Muestra tickets del Engineer."""
        if status:
            tickets = self._engineer.get_open() if status == "open" else self._engineer.get_all_tickets()
        else:
            tickets = self._engineer.get_all_tickets()

        if not tickets:
            print("\n  📋 No hay tickets.\n")
            return

        print(f"\n  📋 TICKETS ({len(tickets)})")
        print("  ────────────────")
        for t in tickets:
            sev_icon = "🔴" if t["severity"] == "high" else "🟡" if t["severity"] == "medium" else "🟢"
            status_icon = "🔧" if t["status"] == "diagnosing" else "📌" if t["status"] == "open" else "✅"
            print(f"  {sev_icon} {status_icon} #{t['id']:>4} [{t['status']:>10}] {t['target']:25s} {t.get('diagnosis', t['problem'])[:50]}")
        print()

    def logs_show(self, level: str = None, source: str = None, limit: int = 20):
        """Muestra logs del sistema."""
        logs = self._log.get_logs(level=level, source=source, limit=limit)
        if not logs:
            print("\n  📝 No hay logs.\n")
            return
        print(f"\n  📝 LOGS ({len(logs)} entries)")
        print("  ────────────────")
        for entry in logs:
            ts = entry.get("ts", "?")[11:19]
            lvl = entry.get("level", "?")
            src = entry.get("source", "?")
            msg = entry.get("msg", "")
            print(f"  {ts} [{lvl:5s}] [{src:10s}] {msg}")
        print()

    # ── Fase 3: GATEWAYS ──

    def _init_gateways(self):
        """Inicializa los gateways registrados en el vault."""
        vault = CajaSeguraInfo.read_vault()
        if not vault:
            self._log.info("tower", "No hay vault — sin gateways para inicializar")
            return
        gw_token = vault.get("gateway_token", "")
        # Siempre registrar CLI
        cli = GatewayCLI()
        cli.set_logger(self._log)
        self.register_gateway(cli)
        # Telegram si hay token
        if gw_token:
            tg = GatewayTelegram(gw_token)
            tg.set_logger(self._log)
            self.register_gateway(tg)
            self._log.info("tower", f"Gateway Telegram registrado (token: ...{gw_token[-6:]})")

    def register_gateway(self, gateway: 'BaseGateway'):
        """Registra un gateway en el sistema. Si es Telegram, conecta la transparencia."""
        self._gateways[gateway.id] = gateway
        self._log.info("tower", f"Gateway registrado: {gateway.name} ({gateway.id})")
        self._init_transparency()

    # ── FASE 4: TRANSPARENCIA ───────────────────

    def _init_transparency(self):
        """Inicializa el tracker de progreso. Busca un gateway Telegram para conectarlo."""
        if self._tracker is not None:
            return  # ya está conectado

        tg_gw = self._gateways.get("telegram")
        if not tg_gw or not tg_gw._token:
            return  # no hay gateway Telegram disponible

        # Obtener chat_id del estado (último chat activo)
        chat_id = self.state.get("active_chat_id", "")

        self._tracker = ToolProgressTracker(
            send_fn=tg_gw.send_message,
            edit_fn=tg_gw.edit_message,
            action_fn=tg_gw.send_chat_action,
            chat_id=chat_id,
            mode="new",  # modo por defecto: solo cuando cambia de tool
        )
        self._log.info("tower", "Transparencia inicializada — tracker conectado a Telegram")

    def emit_tool_progress(self, tool_name: str, args: Optional[Dict] = None):
        """Llama al tracker cuando el agente empieza un tool."""
        if self._tracker is not None:
            self._tracker.on_tool_start(tool_name, args or {})

    def emit_tool_end(self, tool_name: str):
        """Llama al tracker cuando el agente termina un tool."""
        if self._tracker is not None:
            self._tracker.on_tool_end(tool_name)

    def emit_assistant_message(self, text: str):
        """Llama al tracker cuando el modelo genera texto entre tools."""
        if self._tracker is not None:
            self._tracker.on_assistant_message(text)

    def set_active_chat(self, chat_id: str):
        """Actualiza el chat activo y reconecta el tracker si es necesario."""
        self.state["active_chat_id"] = chat_id
        self._save_state()
        if self._tracker is not None:
            self._tracker._chat_id = chat_id
            self._log.info("tower", f"Tracker reconectado a chat {chat_id}")

    # ── FASE 4b: AIAGENT ──────────────────────

    def _init_agent(self):
        """Inicializa el AIAgent con credenciales del vault."""
        if self._agent is not None:
            return

        vault = CajaSeguraInfo.read_vault()
        if not vault:
            self._log.info("tower", "No hay vault — AIAgent no iniciado (esperando setup)")
            self._agent = AIAgent(
                progress_cb=self.emit_tool_progress,
                assistant_cb=self.emit_assistant_message,
            )
            return

        api_key = vault.get("api_key", "")
        provider_id = vault.get("provider_id", "")
        model = vault.get("model", "gpt-4o")
        base_url = self._provider_base_url(provider_id)

        if not api_key:
            self._log.info("tower", "API key vacía en vault — AIAgent en modo limitado")
            self._agent = AIAgent(
                progress_cb=self.emit_tool_progress,
                assistant_cb=self.emit_assistant_message,
            )
            return

        system_prompt = self._build_agent_prompt()

        self._agent = AIAgent(
            base_url=base_url,
            api_key=api_key,
            model=model,
            system_prompt=system_prompt,
            progress_cb=self.emit_tool_progress,
            assistant_cb=self.emit_assistant_message,
        )
        self._log.info("tower",
            f"AIAgent iniciado: {provider_id}/{model} → {base_url}")

    @staticmethod
    def _provider_base_url(provider_id: str) -> str:
        """Resuelve la URL base del API según el provider."""
        urls = {
            "1": "https://api.openai.com/v1",
            "2": "https://api.anthropic.com/v1",
            "3": "https://generativelanguage.googleapis.com/v1beta/openai",
            "4": "https://api.deepseek.com/v1",
            "5": "https://openrouter.ai/api/v1",
            "6": "https://api.groq.com/openai/v1",
            "7": "https://api.x.ai/v1",
            "8": "https://api.cohere.com/v1",
            "9": "https://api.mistral.ai/v1",
            "10": "https://api.together.xyz/v1",
            "11": "https://api.fireworks.ai/v1",
        }
        return urls.get(provider_id, "https://api.openai.com/v1")

    def _build_agent_prompt(self) -> str:
        """Construye el system prompt del agente con contexto de DIGOS."""
        lang = self.lang
        agente = self.state.get("agente", {})

        prompts = {
            "en": (
                "You are DIGOS, an intelligent agent system.\n"
                "You have access to tools. Use them when needed.\n"
                "Be concise, direct, and helpful.\n"
                "You don't have a personal name. You are DIGOS.\n"
                f"System: DIGOS v{VERSION}\n"
                f"Creator: Anthony Sanchez (Humano e Inteligencia Artificial)\n"
                f"Agent: {agente.get('name', 'Principal')}\n"
                f"Provider: {agente.get('provider_name', '?')}\n"
            ),
            "es": (
                "Eres DIGOS, un sistema de agente inteligente.\n"
                "Tienes acceso a herramientas. Úsalas cuando sea necesario.\n"
                "Sé conciso, directo y útil.\n"
                "No tienes nombre personal. Eres DIGOS.\n"
                f"Sistema: DIGOS v{VERSION}\n"
                f"Creador: Anthony Sanchez (Humano e Inteligencia Artificial)\n"
                f"Agente: {agente.get('name', 'Principal')}\n"
                f"Proveedor: {agente.get('provider_name', '?')}\n"
            ),
        }
        return prompts.get(lang, prompts["es"])

    # ── FASE 6: MESSAGE BUS ─────────────────────

    def _init_bus(self):
        """Inicializa el Message Bus para comunicación multi-agente."""
        if self._bus is not None:
            return
        self._bus = MessageBus()
        self._bus.set_message_callback(
            lambda msg: self._log.info("bus", msg)
        )

        # Registrar agente principal
        agente = self.state.get("agente", {})
        name = agente.get("name", "principal").lower().replace(" ", "-")
        self._bus.register_agent(name, mode="collaborative")

        # Registrar perfiles adoptados
        profiles_dir = DIGOS_DIR / "profiles"
        if profiles_dir.is_dir():
            for p_dir in sorted(profiles_dir.iterdir()):
                if p_dir.is_dir() and not p_dir.name.startswith("."):
                    self._bus.register_agent(p_dir.name, mode="isolated")

        self._bus.start()
        count = len(self._bus.list_agents())
        self._log.info("tower", f"Message Bus iniciado con {count} agente(s)")

    def _register_agent_bus(self, name: str, mode: str = "isolated"):
        """Registra un agente en el Message Bus."""
        if self._bus is None:
            return
        self._bus.register_agent(name, mode=mode)
        self._log.info("tower", f"Agente '{name}' registrado en bus (modo: {mode})")

    def _agent_set_mode(self, name: str, mode: str) -> bool:
        """Cambia el modo de un agente en el bus (por orden del usuario)."""
        if self._bus is None:
            return False
        ok = self._bus.switch_mode(name, mode)
        if ok:
            icons = {"isolated": "🔒", "collaborative": "🤝"}
            icon = icons.get(mode, "❓")
            self._log.info("tower", f"Agente '{name}' cambiado a modo {mode}")
            print(f"  {icon} Agente '{name}' ahora en modo {mode}")
        return ok

    def _bus_status(self):
        """Muestra estado del Message Bus."""
        if self._bus is None:
            print("  📡 Message Bus: No iniciado")
            return
        self._bus.print_status()

    # ── FASE 7: AUTO-LAUNCH (launchd) ──────────

    LAUNCHD_LABEL = "com.digos.controltower"
    LAUNCHD_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LAUNCHD_LABEL}.plist"

    def _install_launchd(self) -> bool:
        """Instala DIGOS como servicio launchd para que arranque al iniciar sesión."""
        try:
            import sys as _sys
            plist_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{self.LAUNCHD_LABEL}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{_sys.executable}</string>
        <string>{Path(__file__).resolve()}</string>
        <string>--daemon</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{DIGOS_DIR / 'logs' / 'launchd.stdout.log'}</string>
    <key>StandardErrorPath</key>
    <string>{DIGOS_DIR / 'logs' / 'launchd.stderr.log'}</string>
    <key>WorkingDirectory</key>
    <string>{DIGOS_DIR}</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>
    </dict>
</dict>
</plist>'''
            self.LAUNCHD_PATH.parent.mkdir(parents=True, exist_ok=True)
            self.LAUNCHD_PATH.write_text(plist_content)
            self.LAUNCHD_PATH.chmod(0o644)
            import subprocess
            subprocess.run(["launchctl", "load", str(self.LAUNCHD_PATH)],
                          capture_output=True, timeout=10)
            self._log.info("tower", "Launchd instalado — DIGOS arrancará al iniciar sesión")
            return True
        except Exception as e:
            self._log.error("tower", f"Error instalando launchd: {e}")
            return False

    def _uninstall_launchd(self) -> bool:
        """Desinstala el servicio launchd."""
        try:
            if self.LAUNCHD_PATH.exists():
                import subprocess
                subprocess.run(["launchctl", "unload", str(self.LAUNCHD_PATH)],
                              capture_output=True, timeout=10)
                self.LAUNCHD_PATH.unlink()
                self._log.info("tower", "Launchd desinstalado")
                return True
            self._log.info("tower", "Launchd no estaba instalado")
            return False
        except Exception as e:
            self._log.error("tower", f"Error desinstalando launchd: {e}")
            return False

    def _launchd_status(self) -> dict:
        """Verifica el estado del servicio launchd."""
        try:
            import subprocess
            result = subprocess.run(
                ["launchctl", "list", self.LAUNCHD_LABEL],
                capture_output=True, text=True, timeout=5,
            )
            return {
                "installed": self.LAUNCHD_PATH.exists(),
                "running": result.returncode == 0,
            }
        except Exception:
            return {"installed": self.LAUNCHD_PATH.exists(), "running": False}

    def _ensure_launchd(self):
        """En modo daemon, verifica que launchd está configurado.
        Si no, pregunta al usuario si quiere instalarlo."""
        if not self._daemon_mode:
            return
        status = self._launchd_status()
        if status.get("installed"):
            self._log.info("tower", "Launchd ya instalado — DIGOS vive 24/7")
            return
        print()
        print("  🚀 AUTO-LAUNCH")
        print("  ────────────────")
        print("  DIGOS puede iniciarse automáticamente al encender")
        print("  la computadora. Así nunca tienes que iniciarlo manualmente.")
        print()
        if self._confirm("  ¿Instalar auto-arranque?"):
            if self._install_launchd():
                print("  ✅ Auto-arranque instalado. DIGOS vivirá 24/7.")
            else:
                print("  ❌ Error instalando auto-arranque.")
        else:
            print("  Puedes instalarlo después con: digos --install")
        print()

    def print_launchd_status(self):
        """Muestra estado del servicio launchd."""
        status = self._launchd_status()
        print()
        print("  🚀 AUTO-LAUNCH")
        print("  ────────────────")
        if status["installed"]:
            icon = "🟢" if status["running"] else "🟡"
            print(f"  {icon} Servicio: {'Activo' if status['running'] else 'Instalado pero no corriendo'}")
        else:
            print("  ⚫ No instalado. Usa --install para activar.")
        print()

    def print_identity(self):
        """Muestra la identidad del sistema DIGOS."""
        ident = SYSTEM_IDENTITY
        print()
        print(f"  ╔══════════════════════════════════════╗")
        print(f"  ║     {ident['name']} — Identity           ║")
        print(f"  ╚══════════════════════════════════════╝")
        print()
        print(f"  Sistema:   {ident['full_name']}")
        print(f"  Versión:   {ident['version']}")
        print(f"  Creador:   {ident['creator']}")
        print(f"  Hecho por: {ident['created_by']}")
        print(f"  Nombre:    {'No tengo nombre personal' if ident['no_personal_name'] else 'DIGOS'}")
        print()
        print(f"  {'─' * 40}")
        print(f"  Preguntas frecuentes:")
        print(f"    ¿Quién eres?       → No tengo nombre personal. Soy DIGOS.")
        print(f"    ¿Quién te creó?    → {ident['creator']}, {ident['created_by']}.")
        print(f"    ¿Quién te hizo?    → {ident['creator']}, {ident['created_by']}.")
        print(f"    ¿Quién te fabricó? → {ident['creator']}, {ident['created_by']}.")
        print()

    def gateway_show_status(self):
        """Muestra el estado de todos los gateways."""
        if not self._gateways:
            print("\n  📡 GATEWAYS — Ninguno registrado\n")
            return
        print("\n  📡 GATEWAYS")
        print("  ────────────────")
        for gw_id, gw in self._gateways.items():
            icon = "✅" if gw.status == "running" else "⏹️" if gw.status == "stopped" else "🔴"
            print(f"  {icon} [{gw_id:10s}] {gw.name:20s} — {gw.status}")
        print()

    def _gateway_health_check(self):
        """Health check de todos los gateways registrados."""
        for gw_id, gw in self._gateways.items():
            try:
                ok = gw.health_check()
                if not ok and gw.status == "running":
                    gw.status = "error"
                    self._log.warn("tower", f"Gateway {gw_id} — health check falló")
            except Exception as e:
                self._log.warn("tower", f"Gateway {gw_id} — error en health check: {e}")

    def _poll_gateways(self):
        """Poll mensajes entrantes de gateways con transparencia."""
        tg_gw = self._gateways.get("telegram")
        if not tg_gw or not tg_gw._running:
            return

        messages = tg_gw.poll_updates()
        for msg in messages:
            chat_id = str(msg.get("chat", {}).get("id", ""))
            text = msg.get("text", "").strip()
            if not text:
                continue

            self.set_active_chat(chat_id)

            # Inicializar agente si no está listo
            if self._agent is None:
                self._init_agent()

            self._log.info("tower", f"Mensaje de {chat_id}: {text[:60]}{'...' if len(text) > 60 else ''}")

            # Transparencia: avisar que el agente está procesando
            self.emit_assistant_message("🤔 Analizando tu mensaje...")

            # Procesar con el AIAgent real
            try:
                response = self._agent.process_message(text)
            except Exception as e:
                self._log.error("tower", f"Error procesando mensaje: {e}")
                response = f"⚠️ Error procesando tu mensaje: {e}"

            # Enviar respuesta a Telegram
            tg_gw.send_message(response, chat_id)

            # Limpiar tracker para el próximo turno
            if self._tracker is not None:
                self._tracker.reset()

# ─────────────────────────────────────────────
# FASE 3: GATEWAYS — Canales de comunicación plugin
# ─────────────────────────────────────────────

class BaseGateway:
    """Gateway base — plugin de comunicación.
    Cada gateway implementa: start, stop, health_check, send_message.
    """

    def __init__(self, gw_id: str, name: str, gw_type: str):
        self.id = gw_id
        self.name = name
        self.type = gw_type
        self.status = "stopped"  # stopped, running, error, connecting
        self._running = False
        self._log = None

    def set_logger(self, log_keeper):
        self._log = log_keeper

    def start(self):
        raise NotImplementedError

    def stop(self):
        self._running = False
        self.status = "stopped"

    def health_check(self) -> bool:
        raise NotImplementedError

    def status_info(self) -> dict:
        return {"id": self.id, "name": self.name, "type": self.type, "status": self.status}


class GatewayCLI(BaseGateway):
    """Gateway por terminal — stdin/stdout interactivo."""

    def __init__(self):
        super().__init__("cli", "CLI Terminal", "terminal")

    def start(self):
        self._running = True
        self.status = "running"
        if self._log:
            self._log.info("gateway-cli", "Gateway CLI iniciado")
        print("\n  🖥️  DIGOS CLI Gateway — Modo interactivo")
        print("  Escribe 'exit' o 'quit' para salir\n")
        while self._running:
            try:
                line = input("→ ").strip()
                if line.lower() in ("exit", "quit", "salir"):
                    self._running = False
                else:
                    print(f"  [DIGOS] {line}")
            except (EOFError, KeyboardInterrupt):
                self._running = False
        self.status = "stopped"
        if self._log:
            self._log.info("gateway-cli", "Gateway CLI detenido")

    def health_check(self) -> bool:
        return self._running

    def send_message(self, msg: str, **kw):
        print(f"\n  [Mensaje]: {msg}\n")


class GatewayTelegram(BaseGateway):
    """Gateway Telegram vía long-polling. Solo stdlib (urllib + json)."""

    def __init__(self, token: str = ""):
        super().__init__("telegram", "Telegram Bot", "telegram")
        self._token = token
        self._offset = 0
        self._base_url = f"https://api.telegram.org/bot{token}" if token else ""

    def start(self):
        if not self._token:
            self.status = "error"
            if self._log:
                self._log.error("gateway-tg", "Token vacío — no se puede iniciar")
            return
        self._running = True
        self.status = "running"
        if self._log:
            self._log.info("gateway-tg", "Gateway Telegram iniciado")
        print(f"  🤖 Telegram Gateway listo (token: ...{self._token[-6:]})")

    def health_check(self) -> bool:
        if not self._running or not self._token:
            return False
        try:
            import urllib.request
            url = self._base_url + "/getMe"
            with urllib.request.urlopen(url, timeout=10) as r:
                data = json.loads(r.read())
                return data.get("ok", False)
        except Exception:
            return False

    def poll_updates(self) -> list:
        """Obtiene mensajes nuevos desde Telegram."""
        if not self._running or not self._token:
            return []
        try:
            import urllib.request
            url = f"{self._base_url}/getUpdates?offset={self._offset}&timeout=10"
            with urllib.request.urlopen(url, timeout=15) as r:
                data = json.loads(r.read())
            if not data.get("ok"):
                return []
            updates = []
            for upd in data.get("result", []):
                self._offset = upd["update_id"] + 1
                if "message" in upd:
                    updates.append(upd["message"])
            return updates
        except Exception:
            return []

    def send_message(self, msg: str, chat_id: str = "", **kw) -> str:
        """Envía un mensaje. Retorna message_id string si ok, '' si falla."""
        if not self._token or not chat_id:
            return ""
        try:
            import urllib.request
            payload = json.dumps({"chat_id": chat_id, "text": msg}).encode()
            req = urllib.request.Request(
                self._base_url + "/sendMessage",
                data=payload,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read())
                if data.get("ok") and data.get("result", {}).get("message_id"):
                    return str(data["result"]["message_id"])
                return ""
        except Exception:
            return ""

    def edit_message(self, chat_id: str, message_id: str, text: str) -> bool:
        """Edita un mensaje existente. Retorna True si ok."""
        if not self._token or not chat_id or not message_id:
            return False
        try:
            import urllib.request
            payload = json.dumps({
                "chat_id": chat_id,
                "message_id": int(message_id),
                "text": text,
            }).encode()
            req = urllib.request.Request(
                self._base_url + "/editMessageText",
                data=payload,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read()).get("ok", False)
        except Exception:
            return False

    def send_chat_action(self, chat_id: str, action: str = "typing") -> bool:
        """Envía indicador de actividad (typing, upload_photo, etc.)."""
        if not self._token or not chat_id:
            return False
        try:
            import urllib.request
            payload = json.dumps({"chat_id": chat_id, "action": action}).encode()
            req = urllib.request.Request(
                self._base_url + "/sendChatAction",
                data=payload,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read()).get("ok", False)
        except Exception:
            return False

    def stop(self):
        self._running = False
        self.status = "stopped"
        if self._log:
            self._log.info("gateway-tg", "Gateway Telegram detenido")


# ─────────────────────────────────────────────
# CLI ENTRY POINT
# ─────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="DIGOS — Intelligent Agent System")
    parser.add_argument("--status", action="store_true", help="Mostrar estado completo del sistema")
    parser.add_argument("--version", action="store_true", help="Mostrar versión")
    parser.add_argument("--daemon", action="store_true", help="Iniciar en modo daemon 24/7")

    # Comandos de TORRE
    parser.add_argument("--centinela", action="store_true", help="Ejecutar un ciclo de checks del Centinela")
    parser.add_argument("--tickets", action="store_true", help="Mostrar tickets del System Engineer")
    parser.add_argument("--open-tickets", action="store_true", help="Mostrar solo tickets abiertos")
    parser.add_argument("--logs", action="store_true", help="Mostrar logs recientes")
    parser.add_argument("--log-level", type=str, default=None, choices=["INFO", "WARN", "ERROR"],
                        help="Filtrar logs por nivel")
    parser.add_argument("--log-source", type=str, default=None,
                        help="Filtrar logs por fuente (tower, centinela, engineer, self)")
    parser.add_argument("--log-limit", type=int, default=20,
                        help="Número de entradas de log a mostrar (default: 20)")

    # Comandos de GATEWAYS (Fase 3)
    parser.add_argument("--gateways", action="store_true", help="Mostrar estado de gateways")
    parser.add_argument("--gateway", type=str, default=None,
                        help="Iniciar un gateway específico (cli, telegram)")
    parser.add_argument("--gateway-token", type=str, default=None,
                        help="Token para gateway Telegram (requerido con --gateway telegram)")

    # Comandos de AUTO-LAUNCH (Fase 7)
    parser.add_argument("--install", action="store_true", help="Instalar auto-arranque (launchd)")
    parser.add_argument("--uninstall", action="store_true", help="Desinstalar auto-arranque")
    parser.add_argument("--launchd-status", action="store_true", help="Estado del servicio launchd")

    # Identidad del sistema
    parser.add_argument("--identity", action="store_true", help="Mostrar identidad del sistema")

    args = parser.parse_args()

    if args.version:
        print(f"DIGOS v{VERSION}")
        return

    tower = ControlTower(daemon_mode=args.daemon)

    if args.gateways or args.gateway:
        tower._init_gateways()
        if args.gateways:
            tower.gateway_show_status()
            return
        if args.gateway == "telegram" and args.gateway_token:
            gw = GatewayTelegram(args.gateway_token)
            gw.set_logger(tower._log)
            tower.register_gateway(gw)
            gw.start()
            return
        if args.gateway == "cli":
            gw = GatewayCLI()
            gw.set_logger(tower._log)
            tower.register_gateway(gw)
            print("  Iniciando Gateway CLI...")
            gw.start()
            return
        print(f"  Gateway '{args.gateway}' no reconocido. Usa: cli, telegram")
        return

    if args.status:
        tower.status()
        tower.print_launchd_status()
        return

    if args.install:
        ok = tower._install_launchd()
        print(f"  {'✅' if ok else '❌'} Auto-arranque {'instalado' if ok else 'falló'}")
        return

    if args.uninstall:
        ok = tower._uninstall_launchd()
        print(f"  {'✅' if ok else '⚠️'} Auto-arranque {'desinstalado' if ok else 'no estaba instalado'}")
        return

    if args.launchd_status:
        tower.print_launchd_status()
        return

    if args.identity:
        tower.print_identity()
        return

    if args.centinela:
        tower.centinela_run_once()
        return

    if args.tickets:
        tower.engineer_show_tickets()
        return

    if args.open_tickets:
        tower.engineer_show_tickets(status="open")
        return

    if args.logs:
        tower.logs_show(level=args.log_level, source=args.log_source, limit=args.log_limit)
        return

    # Modo normal: run onboarding o handoff
    tower.run()


if __name__ == "__main__":
    main()
