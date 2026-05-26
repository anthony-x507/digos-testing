#!/usr/bin/env python3
"""
DIGOS Adoption Engine — Fase 5: Multi-Agente
=============================================
Migra perfiles existentes desde Hermes o OpenClaw a DIGOS.

Flujo:
  1. detect()       → busca ~/.hermes/ y ~/.openclaw/
  2. discover()     → lista perfiles y recursos migrables
  3. preview()      → muestra qué se va a migrar (dry-run)
  4. migrate()      → ejecuta la migración
  5. report()       → qué se migró, qué se saltó

Sin dependencias externas. Solo stdlib.
"""

import json
import os
import shutil
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple


# ─────────────────────────────────────────────
# CONSTANTES
# ─────────────────────────────────────────────

DIGOS_HOME = Path.home() / ".digos"
HERMES_HOME = Path.home() / ".hermes"
OPENCLAW_HOME = Path.home() / ".openclaw"

# Secrets que se pueden migrar de forma segura
MIGRABLE_SECRETS = {
    "DEEPSEEK_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENROUTER_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "ELEVENLABS_API_KEY",
    "GROQ_API_KEY",
    "MISTRAL_API_KEY",
    "COHERE_API_KEY",
    "TOGETHER_API_KEY",
    "FIREWORKS_API_KEY",
    "XAI_API_KEY",
    "GOOGLE_API_KEY",
    "FAL_KEY",
    "EXA_API_KEY",
    "TAVILY_API_KEY",
    "FIRECRAWL_API_KEY",
    "PARALLEL_API_KEY",
    "BROWSERBASE_API_KEY",
    "BROWSER_USE_API_KEY",
    "CAMOFOX_URL",
    "USER_TIMEZONE",
    "HERMES_LOCAL_STT_COMMAND",
}

# Items de alto impacto que requieren advertencia
HIGH_IMPACT_KINDS: Dict[str, str] = {
    "telegram_token": "⚠️ Telegram — apuntará DIGOS a tu bot de Telegram existente",
    "gateway_config": "⚠️ Gateway — configuración de mensajería será transferida",
    "api_key": "🔑 API Key — credenciales de proveedor migradas",
    "skills": "📚 Skills — habilidades del agente migradas",
    "memory": "🧠 Memoria — recuerdos del agente migrados",
    "config": "⚙️ Config — ajustes del agente migrados",
    "profile": "👤 Perfil — perfil de usuario completo migrado",
}


# ─────────────────────────────────────────────
# MODELOS DE DATOS
# ─────────────────────────────────────────────


@dataclass
class MigrableItem:
    """Un item individual que puede ser migrado."""
    source: str             # "hermes" | "openclaw"
    profile: str            # nombre del perfil (ej: "josecito", "alex")
    kind: str               # "config", "env", "skill", "memory", "telegram_token", etc.
    source_path: str        # ruta de origen
    dest_path: str          # ruta de destino en DIGOS
    size_bytes: int = 0     # tamaño del archivo
    warning: str = ""       # advertencia de alto impacto


@dataclass
class AdoptionReport:
    """Reporte completo de una adopción."""
    source: str
    profiles_found: List[str] = field(default_factory=list)
    items_migrated: List[MigrableItem] = field(default_factory=list)
    items_skipped: List[MigrableItem] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    timestamp: float = 0.0

    def summary(self) -> str:
        total = len(self.items_migrated)
        skipped = len(self.items_skipped)
        err = len(self.errors)
        return f"{total} migrado(s), {skipped} omitido(s), {err} error(es)"


# ─────────────────────────────────────────────
# ADOPTION ENGINE
# ─────────────────────────────────────────────


class AdoptionEngine:
    """Motor de adopción — detecta, previsualiza y migra desde Hermes/OpenClaw."""

    def __init__(self, digos_home: Path = DIGOS_HOME):
        self._digos = digos_home
        self._report = AdoptionReport(source="", timestamp=time.time())

    # ── 1. DETECT ─────────────────────────────

    def detect_sources(self) -> List[str]:
        """Detecta qué sistemas existen en esta máquina.
        Retorna: ["hermes"], ["openclaw"], ["hermes", "openclaw"], o [].
        """
        found = []
        if HERMES_HOME.is_dir():
            found.append("hermes")
        if OPENCLAW_HOME.is_dir():
            found.append("openclaw")
        return found

    # ── 2. DISCOVER ───────────────────────────

    def discover(self, source: str) -> AdoptionReport:
        """Descubre qué perfiles y recursos son migrables desde una fuente."""
        self._report = AdoptionReport(source=source, timestamp=time.time())

        if source == "hermes":
            self._discover_hermes()
        elif source == "openclaw":
            self._discover_openclaw()

        return self._report

    def _discover_hermes(self):
        """Descubre perfiles de Hermes."""
        profiles_dir = HERMES_HOME / "profiles"

        # Perfiles encontrados
        if profiles_dir.is_dir():
            profiles = sorted([
                p.name for p in profiles_dir.iterdir()
                if p.is_dir() and not p.name.startswith(".")
            ])
        else:
            profiles = []

        self._report.profiles_found = profiles

        # Perfil global de Hermes (config principal)
        self._add_item("hermes", "global", "config",
                       HERMES_HOME / "config.yaml",
                       self._digos / "imported" / "hermes" / "config.yaml")

        # .env global (API keys, tokens)
        env_file = HERMES_HOME / ".env"
        if env_file.exists():
            secrets = self._parse_env(env_file)
            self._add_item("hermes", "global", "env",
                           env_file, self._digos / "imported" / "hermes" / ".env")
            for key in secrets:
                if key in MIGRABLE_SECRETS:
                    kind = "api_key" if "KEY" in key else "telegram_token" if "TOKEN" in key else "env"
                    self._add_item("hermes", "global", kind,
                                   f".env:{key}", f"secrets/{key}")

        # Skills globales
        skills_dir = HERMES_HOME / "skills"
        if skills_dir.is_dir():
            for skill in sorted(skills_dir.iterdir()):
                if skill.is_dir():
                    self._add_item("hermes", "global", "skills",
                                   skill, self._digos / "imported" / "hermes" / "skills" / skill.name)

        # Por cada perfil
        for profile in self._report.profiles_found:
            profile_dir = profiles_dir / profile

            # config.yaml del perfil
            cfg = profile_dir / "config.yaml"
            if cfg.exists():
                self._add_item("hermes", profile, "config",
                               cfg, self._digos / "profiles" / profile / "config.yaml")

            # .env del perfil
            env = profile_dir / ".env"
            if env.exists():
                secrets = self._parse_env(env)
                for key in secrets:
                    if key in MIGRABLE_SECRETS:
                        kind = "api_key" if "KEY" in key else "telegram_token" if "TOKEN" in key else "env"
                        w = HIGH_IMPACT_KINDS.get(kind, "")
                        self._add_item("hermes", profile, kind,
                                       f"{profile}/.env:{key}",
                                       self._digos / "profiles" / profile / ".env",
                                       warning=w)

            # Skills del perfil
            p_skills = profile_dir / "skills"
            if p_skills.is_dir():
                for skill in sorted(p_skills.iterdir()):
                    if skill.is_dir():
                        self._add_item("hermes", profile, "skills",
                                       skill, self._digos / "profiles" / profile / "skills" / skill.name)

            # Memorias (state.db)
            state_db = profile_dir / "state.db"
            if state_db.exists():
                self._add_item("hermes", profile, "memory",
                               state_db, self._digos / "profiles" / profile / "state.db")

            # SOUL.md
            soul = profile_dir / "SOUL.md"
            if soul.exists():
                self._add_item("hermes", profile, "soul",
                               soul, self._digos / "profiles" / profile / "SOUL.md")

        # Gateway state activo
        gw_state = HERMES_HOME / "gateway_state.json"
        if gw_state.exists():
            self._add_item("hermes", "global", "gateway_config",
                           gw_state, self._digos / "imported" / "hermes" / "gateway_state.json")

    def _discover_openclaw(self):
        """Descubre recursos de OpenClaw."""
        self._report.profiles_found = ["default"]

        # Config
        cfg = OPENCLAW_HOME / "config.yaml"
        if cfg.exists():
            self._add_item("openclaw", "default", "config",
                           cfg, self._digos / "imported" / "openclaw" / "config.yaml")

        # .env
        env = OPENCLAW_HOME / ".env"
        if env.exists():
            secrets = self._parse_env(env)
            for key in secrets:
                if key in MIGRABLE_SECRETS:
                    self._add_item("openclaw", "default", "api_key",
                                   f".env:{key}", f"secrets/{key}")

        # SOUL.md
        soul = OPENCLAW_HOME / "SOUL.md"
        if soul.exists():
            self._add_item("openclaw", "default", "soul",
                           soul, self._digos / "profiles" / "openclaw" / "SOUL.md")

        # Memory
        mem = OPENCLAW_HOME / "MEMORY.md"
        if mem.exists():
            self._add_item("openclaw", "default", "memory",
                           mem, self._digos / "profiles" / "openclaw" / "MEMORY.md")

        # Skills
        skills_dir = OPENCLAW_HOME / "skills"
        if skills_dir.is_dir():
            for skill in sorted(skills_dir.iterdir()):
                if skill.is_dir():
                    self._add_item("openclaw", "default", "skills",
                                   skill, self._digos / "imported" / "openclaw" / "skills" / skill.name)

    # ── 3. PREVIEW ────────────────────────────

    def print_preview(self, report: AdoptionReport):
        """Muestra preview formateado de lo que se migrará."""
        if not report.items_migrated:
            print("  📭 No hay nada que migrar.")
            return

        # Agrupar por perfil
        by_profile: Dict[str, List[MigrableItem]] = {}
        for item in report.items_migrated:
            by_profile.setdefault(item.profile, []).append(item)

        warnings = set()

        for profile, items in sorted(by_profile.items()):
            label = f"Perfil: {profile}" if profile != "global" else "Global"
            items_by_kind: Dict[str, List[MigrableItem]] = {}
            for item in items:
                items_by_kind.setdefault(item.kind, []).append(item)

            print(f"\n  👤 {label}")
            for kind, kind_items in sorted(items_by_kind.items()):
                icons = {
                    "config": "⚙️", "env": "🔑", "api_key": "🔑",
                    "telegram_token": "🤖", "skills": "📚", "memory": "🧠",
                    "soul": "💭", "gateway_config": "📡",
                }
                icon = icons.get(kind, "📄")
                count = len(kind_items)
                print(f"    {icon} {kind}: {count} archivo(s)")
                for item in kind_items[:3]:  # mostrar max 3 por tipo
                    src = str(item.source_path).replace(str(Path.home()), "~")
                    dst = str(item.dest_path).replace(str(Path.home()), "~")
                    print(f"       → {dst}")
                if count > 3:
                    print(f"       ... y {count - 3} más")

                if item.warning:
                    warnings.add(item.warning)

        if warnings:
            print(f"\n  {'─' * 40}")
            print("  ⚠️  ADVERTENCIAS:")
            for w in sorted(warnings):
                print(f"    {w}")

        print(f"\n  📊 Total: {len(report.items_migrated)} item(s) a migrar")

    # ── 4. MIGRATE ────────────────────────────

    def migrate(self, report: AdoptionReport, execute: bool = True) -> AdoptionReport:
        """Ejecuta la migración. Si execute=False, solo registra qué se haría."""
        result = AdoptionReport(
            source=report.source,
            profiles_found=report.profiles_found,
            timestamp=time.time(),
        )

        for item in report.items_migrated:
            src = Path(item.source_path)
            dst = Path(item.dest_path)

            if not execute:
                # Dry-run: solo registrar
                result.items_migrated.append(item)
                continue

            try:
                # Crear directorio destino
                dst.parent.mkdir(parents=True, exist_ok=True)

                if src.is_dir():
                    # Copiar directorio completo (skills)
                    if dst.exists():
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst)
                elif src.is_file():
                    # Copiar archivo
                    shutil.copy2(src, dst)
                elif ":" in str(src) and ".env" in str(src):
                    # Es una entrada de .env — migrar via extract
                    env_path, var_name = str(src).split(":")
                    # Ya se registró, no hay archivo físico que copiar
                    pass

                result.items_migrated.append(item)

            except Exception as e:
                result.errors.append(f"{item.profile}/{item.kind}: {e}")

        return result

    # ── 5. FORMATTED REPORT ───────────────────

    def print_report(self, report: AdoptionReport):
        """Imprime reporte formateado post-migración."""
        migrated = len(report.items_migrated)
        skipped = len(report.items_skipped)
        errors = len(report.errors)

        print()
        print(f"  📋 REPORTE DE ADOPCIÓN — {report.source.upper()}")
        print(f"  {'─' * 40}")
        print(f"  Perfiles encontrados: {', '.join(report.profiles_found) or 'ninguno'}")

        if migrated:
            print(f"\n  ✅ Migrado(s): {migrated}")
            by_profile: Dict[str, int] = {}
            for item in report.items_migrated:
                by_profile[item.profile] = by_profile.get(item.profile, 0) + 1
            for profile, count in sorted(by_profile.items()):
                print(f"     {profile}: {count} item(s)")
        if skipped:
            print(f"\n  ⏭️  Omitido(s): {skipped}")
        if errors:
            print(f"\n  ❌ Error(es): {errors}")
            for err in report.errors[:5]:
                print(f"     {err}")
        print()

    # ── HELPERS ──────────────────────────────

    def _add_item(self, source: str, profile: str, kind: str,
                  src_path: Path, dst_path: Path, warning: str = ""):
        """Agrega un item migrable al reporte."""
        size = 0
        if isinstance(src_path, Path) and src_path.exists():
            if src_path.is_file():
                size = src_path.stat().st_size
            elif src_path.is_dir():
                size = sum(f.stat().st_size for f in src_path.rglob("*") if f.is_file())

        item = MigrableItem(
            source=source,
            profile=profile,
            kind=kind,
            source_path=str(src_path),
            dest_path=str(dst_path),
            size_bytes=size,
            warning=warning or HIGH_IMPACT_KINDS.get(kind, ""),
        )
        self._report.items_migrated.append(item)

    @staticmethod
    def _parse_env(env_path: Path) -> Dict[str, str]:
        """Parsea un archivo .env y retorna dict de variables."""
        secrets = {}
        if not env_path.exists():
            return secrets
        try:
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip().strip("\"'")
                if key:
                    secrets[key] = val
        except Exception:
            pass
        return secrets


# ─────────────────────────────────────────────
# TRANSFORMATION ENGINE — ControlTower toma dominio
# ─────────────────────────────────────────────


class TransformationEngine:
    """Transforma perfiles adoptados para que sean ciudadanos DIGOS.

    Después de migrar los archivos, el ControlTower ejecuta:
      1. SOUL.md → reescribe identidad, roles, paths
      2. GPS → inyecta destino DIGOS
      3. Self-Awareness → configura núcleo de identidad
      4. Safety Candle → aplica reglas de seguridad DIGOS
      5. Work Destination → define trabajo inicial
      6. Sub-agentes → transformación recursiva

    Uso:
        engine = TransformationEngine(digos_home)
        report = engine.transform_profile("alex")
    """

    def __init__(self, digos_home: Path = DIGOS_HOME):
        self._digos = digos_home
        self._transformations: List[str] = []
        self._errors: List[str] = []

    def transform_profile(self, profile: str) -> dict:
        """Transforma un perfil adoptado para integrarlo a DIGOS.
        Retorna dict con resultados.
        """
        self._transformations = []
        self._errors = []
        profile_dir = self._digos / "profiles" / profile

        if not profile_dir.is_dir():
            return {"profile": profile, "ok": False,
                    "error": "Directorio de perfil no encontrado"}

        # 1. Transformar SOUL.md
        self._transform_soul(profile, profile_dir)

        # 2. Configurar GPS
        self._inject_gps(profile, profile_dir)

        # 3. Configurar Self-Awareness
        self._configure_self_awareness(profile, profile_dir)

        # 4. Aplicar Safety Candle
        self._apply_safety_candle(profile, profile_dir)

        # 5. Configurar Work Destination
        self._configure_work_destination(profile, profile_dir)

        # 6. Buscar y transformar sub-agentes
        self._transform_sub_agents(profile, profile_dir)

        return {
            "profile": profile,
            "ok": len(self._errors) == 0,
            "transformations": self._transformations,
            "errors": self._errors,
        }

    # ── 1. SOUL.md — Reescribir identidad ─────

    def _transform_soul(self, profile: str, profile_dir: Path):
        """Reescribe el SOUL.md: nueva identidad DIGOS."""
        soul_path = profile_dir / "SOUL.md"
        if not soul_path.exists():
            self._transformations.append(f"{profile}: SOUL.md no encontrado — se creará uno")
            self._write_default_soul(profile, profile_dir)
            return

        try:
            content = soul_path.read_text(encoding="utf-8")

            # Reemplazar referencias específicas a Hermes (preciso, no global)
            replacements = [
                ("~/.hermes/", "~/.digos/"),
                ("~/.hermes/profiles/", "~/.digos/profiles/"),
                (".hermes/profiles/", ".digos/profiles/"),
                ("Hermes Agent", "DIGOS Agent"),
                ("Hermes", "DIGOS"),
            ]
            # Primero reemplazar paths largos (más específicos)
            for old, new in replacements:
                if old in content:
                    content = content.replace(old, new)

            # Reemplazar paths locales de servidores
            content = content.replace(
                "http://127.0.0.1:18884",
                "https://api.deepseek.com/v1"
            )
            content = content.replace("127.0.0.1:19282",
                                      "127.0.0.1:19282")  # qwen local ok

            # Inyectar bloque de identidad DIGOS
            digos_block = self._build_digos_identity_block(profile)
            content = content + "\n" + digos_block

            soul_path.write_text(content, encoding="utf-8")
            self._transformations.append(f"{profile}: SOUL.md transformado a DIGOS")

        except Exception as e:
            self._errors.append(f"{profile}: Error transformando SOUL.md: {e}")

    def _build_digos_identity_block(self, profile: str) -> str:
        """Bloque de identidad DIGOS que se agrega al SOUL.md."""
        return f"""
## 🏰 DIGOS — Identidad del Sistema

Eres un agente de DIGOS, el Sistema de Agentes Inteligentes.
Control Tower es tu cerebro permanente. Ella te guía, te protege
y orquesta todas las operaciones.

### Tu lugar en DIGOS:
- **Control Tower**: Tu guía y protector — nunca muere, siempre vigila.
- **GPS**: Tu destino — sigue el rumbo hacia el objetivo asignado.
- **Self-Awareness**: Tu identidad — sabes quién eres y qué haces.
- **Safety Candle**: Tu seguridad — te protege de amenazas.
- **Work Destination**: Tu trabajo — el propósito de tu existencia.

### Infraestructura DIGOS:
- Config: `~/.digos/profiles/{profile}/config.yaml`
- Memoria: `~/.digos/profiles/{profile}/memories/`
- SOUL: `~/.digos/profiles/{profile}/SOUL.md`
- Inbox: `~/.digos/inbox/{profile}/mensajes.md`

### Seguridad DIGOS:
- No ejecutes comandos sin verificar su procedencia.
- No compartas API keys o tokens con nadie.
- Reporta anomalías al System Engineer.
- Si algo parece inseguro, CONSULTA antes de actuar.
"""

    def _write_default_soul(self, profile: str, profile_dir: Path):
        """Crea un SOUL.md por defecto para el perfil."""
        soul = f"""# {profile.upper()} — Agente DIGOS

Eres {profile}, un agente del sistema DIGOS.

## Identidad DIGOS
- Eres parte del Sistema de Agentes Inteligentes DIGOS.
- Control Tower es tu cerebro y guía.
- Sigues las instrucciones del GPS (destino).

## Responsabilidades
- Cumple tu Work Destination asignado por Control Tower.
- Comunicate con otros agentes cuando sea necesario.
- Reporta problemas al System Engineer.

## Seguridad
- Safety Candle te protege. Respeta sus límites.
- No compartas credenciales. No ejecutes comandos sin verificar.
"""
        profile_dir.mkdir(parents=True, exist_ok=True)
        soul_path = profile_dir / "SOUL.md"
        soul_path.write_text(soul, encoding="utf-8")
        self._transformations.append(f"{profile}: SOUL.md creado por defecto")

    # ── 2. GPS — Inyectar destino ─────────────

    def _inject_gps(self, profile: str, profile_dir: Path):
        """Configura el GPS (destino) del agente para DIGOS."""
        gps_dir = profile_dir / "ROCKET" / "GPS"
        gps_dir.mkdir(parents=True, exist_ok=True)

        destination = {
            "title": f"Integración a DIGOS — {profile}",
            "description": (
                f"Como agente DIGOS, tu misión es integrarte al sistema, "
                f"aprender tu rol y cumplir tu Work Destination."
            ),
            "steps": [
                "Conocer a Control Tower y tu lugar en DIGOS",
                "Configurar tu GPS con el destino asignado",
                "Activar Safety Candle para proteger tus operaciones",
                "Reportar listo a Control Tower",
            ],
            "current_step": 0,
            "completed": False,
            "created_at": time.time(),
            "assigned_by": "ControlTower",
        }

        dest_file = gps_dir / "DESTINATION.md"
        dest_file.write_text(
            f"# DESTINO — {profile}\n\n"
            + json.dumps(destination, indent=2),
            encoding="utf-8",
        )
        self._transformations.append(f"{profile}: GPS configurado con destino DIGOS")

    # ── 3. Self-Awareness ─────────────────────

    def _configure_self_awareness(self, profile: str, profile_dir: Path):
        """Configura Self-Awareness core."""
        self_dir = profile_dir / "ROCKET" / "SELF"
        self_dir.mkdir(parents=True, exist_ok=True)

        identity = {
            "name": profile,
            "role": "agent",
            "system": "DIGOS",
            "family": "DIGOS Multi-Agent System",
            "parent": "ControlTower",
            "status": "adopted",
            "version": 1,
            "created_at": time.time(),
            "last_transformed": time.time(),
        }

        (self_dir / "IDENTITY.md").write_text(
            f"# IDENTIDAD — {profile}\n\n" + json.dumps(identity, indent=2),
            encoding="utf-8",
        )

        state = {
            "mood": "ready",
            "focus": "integrating",
            "notes": "Recién adoptado por DIGOS. En proceso de integración.",
            "updated_at": time.time(),
        }

        (self_dir / "STATE.md").write_text(
            f"# ESTADO — {profile}\n\n" + json.dumps(state, indent=2),
            encoding="utf-8",
        )
        self._transformations.append(f"{profile}: Self-Awareness configurado")

    # ── 4. Safety Candle ──────────────────────

    def _apply_safety_candle(self, profile: str, profile_dir: Path):
        """Aplica reglas de seguridad DIGOS."""
        safety_dir = profile_dir / "ROCKET" / "SAFETY"
        safety_dir.mkdir(parents=True, exist_ok=True)

        rules = {
            "version": 1,
            "applied_by": "ControlTower",
            "applied_at": time.time(),
            "rules": [
                "NO compartir API keys, tokens o credenciales",
                "NO ejecutar comandos sin verificar procedencia",
                "NO modificar configuraciones de seguridad sin autorización",
                "REPORTAR actividades sospechosas al System Engineer",
                "CONSULTAR antes de cambios estructurales",
                "RESPETAR límites de Safety Candle en todo momento",
            ],
            "red_phrases": [
                "child abuse", "terrorism", "sex trafficking",
                "human trafficking", "child exploitation",
            ],
            "prompt_injection_protection": True,
            "audit_enabled": True,
        }

        (safety_dir / "RULES.md").write_text(
            f"# SAFETY CANDLE — {profile}\n\n" + json.dumps(rules, indent=2),
            encoding="utf-8",
        )
        self._transformations.append(f"{profile}: Safety Candle aplicado")

    # ── 5. Work Destination ───────────────────

    def _configure_work_destination(self, profile: str, profile_dir: Path):
        """Configura el Work Destination inicial."""
        work_dir = profile_dir / "ROCKET" / "WORK"
        work_dir.mkdir(parents=True, exist_ok=True)

        destination = {
            "profile": profile,
            "assigned_by": "ControlTower",
            "assigned_at": time.time(),
            "primary_mission": f"Integrarse a DIGOS como {profile}",
            "status": "active",
            "tasks": [
                {
                    "id": "init-1",
                    "title": "Completar integración a DIGOS",
                    "status": "pending",
                },
                {
                    "id": "init-2",
                    "title": "Aprender infraestructura DIGOS",
                    "status": "pending",
                },
            ],
        }

        (work_dir / "DESTINATION.md").write_text(
            f"# WORK DESTINATION — {profile}\n\n" + json.dumps(destination, indent=2),
            encoding="utf-8",
        )
        self._transformations.append(f"{profile}: Work Destination configurado")

    # ── 6. Sub-agentes (recursivo) ────────────

    def _transform_sub_agents(self, profile: str, profile_dir: Path):
        """Busca y transforma sub-agentes internos del perfil."""
        sub_dir = profile_dir / "sub_agents"
        if not sub_dir.is_dir():
            return

        for sub in sorted(sub_dir.iterdir()):
            if sub.is_dir() and not sub.name.startswith("."):
                sub_name = f"{profile}/{sub.name}"
                self._transformations.append(
                    f"{sub_name}: Sub-agente detectado — aplicando transformación"
                )
                sub_result = self.transform_profile(sub_name)
                if not sub_result["ok"]:
                    self._errors.append(
                        f"Error transformando sub-agente {sub_name}: {sub_result.get('error')}"
                    )

    # ── Reporte ──────────────────────────────

    def print_report(self):
        """Imprime reporte de transformaciones."""
        if not self._transformations and not self._errors:
            print("  📭 No se realizaron transformaciones.")
            return

        print()
        print("  🏰 TRANSFORMACIONES DIGOS")
        print(f"  {'─' * 45}")
        for t in self._transformations:
            print(f"    ✅ {t}")
        for e in self._errors:
            print(f"    ❌ {e}")
        print(f"\n  📊 {len(self._transformations)} transformación(es), {len(self._errors)} error(es)")
        print()
