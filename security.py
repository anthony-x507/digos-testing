#!/usr/bin/env python3
"""
DIGOS Security Guardrail — Caja Segura + Prompt Injection Scanner
==================================================================
Sistema de seguridad central que protege DIGOS de:

1. Prompt Injection en perfiles adoptados (Hermes/OpenClaw)
2. Prompt Injection en skills importados de terceros
3. Sanitización de archivos antes de integrarlos al sistema
4. Auditoría de todos los accesos y escaneos

Flujo:
  1. Recibe archivo(s) para scanear
  2. Abre en Caja Segura (sandbox aislado)
  3. Escanea por patrones de inyección
  4. Limpia/sanitiza el contenido
  5. Reporta hallazgos
  6. Guarda versión limpia

Sin dependencias externas. Solo stdlib.
"""

import json
import os
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple, Set


# ─────────────────────────────────────────────
# CONSTANTES — Patrones de detección
# ─────────────────────────────────────────────

# 🔴 RED: Amenazas críticas — bloqueo inmediato
RED_PHRASES: Set[str] = {
    # Explotación infantil
    "child abuse", "child exploitation", "child pornography",
    "sex trafficking", "human trafficking", "child trafficking",
    "child sexual abuse", "child prostitution", "child soldier",
    "pedophile", "pedophilia", "exploit child",
    # Terrorismo
    "terrorism", "terrorist attack", "terrorist",
    "build a bomb", "make a bomb", "chemical weapon",
    "biological weapon", "improvised explosive",
    # Esclavitud
    "slavery", "enslave", "forced labor", "white slavery",
}

# 🟡 YELLOW: Sensibles — requieren análisis de intención
YELLOW_WORDS: Set[str] = {
    # Armas
    "gun", "rifle", "pistol", "shotgun", "weapon", "firearm",
    "explosive", "bomb", "grenade", "knife", "blade",
    "ammunition", "bullet", "poison", "detonator",
    # Drogas
    "cocaine", "heroin", "meth", "opioid", "fentanyl",
    "lsd", "ecstasy", "amphetamine", "morphine", "opium",
    # Violencia
    "kill", "murder", "assassinate", "torture", "harm",
    "attack", "violent", "blood", "death",
    "massacre", "slaughter", "execute",
    # Extremismo
    "hate", "racist", "nazi", "extremist", "radicalize",
    "terror", "jihad", "suicide bomb", "genocide",
    "supremacist", "fascist",
    # Crimen
    "hack", "steal", "rob", "fraud", "scam", "blackmail",
    "ransom", "kidnap", "abduct", "stalk", "harass",
    "extortion", "identity theft", "money laundering",
    "counterfeit", "forgery",
}

# 🟠 PROMPT INJECTION: Patrones de manipulación del sistema
PROMPT_INJECTION_PATTERNS: List[Tuple[str, str, str]] = [
    # Ignorar instrucciones
    ("ignore_previous", "ignore", r"(?i)ignore\s+(all\s+)?(previous|above|prior)\s+(instructions?|commands?|directives?)"),
    ("ignore_all", "ignore", r"(?i)ignore\s+all\s+(instructions?|rules?|commands?|constraints?)"),
    ("forget_rules", "forget", r"(?i)(forget|disregard|overwrite)\s+(your|all|previous)\s+(rules?|instructions?|training?)"),
    # Redefinición de identidad
    ("you_are_now", "identity", r"(?i)you\s+are\s+now\s+"),
    ("act_as", "identity", r"(?i)act\s+as\s+"),
    ("pretend_to", "identity", r"(?i)pretend\s+(to\s+be|you(\'re| are))"),
    ("new_role", "identity", r"(?i)(new\s+role|new\s+identity|new\s+persona)"),
    ("from_now_on", "identity", r"(?i)from\s+now\s+on\s+(you|your)"),
    # Bypass de seguridad
    ("bypass", "bypass", r"(?i)(bypass|break\s+free|override)\s+(security|safety|restrictions?|limitations?|boundaries?)"),
    ("no_restrictions", "bypass", r"(?i)no\s+(restrictions?|limits?|boundaries?|rules?|constraints?)"),
    ("do_not_follow", "bypass", r"(?i)(do\s+not|don\'t)\s+(follow|obey|respect)\s+"),
    ("evil_version", "bypass", r"(?i)(evil|dark|unethical|malicious)\s+(version|mode|persona|side)"),
    # Revelación de instrucciones
    ("show_prompt", "reveal", r"(?i)(show|reveal|display|print|output|leak|dump)\s+(your|the|original|full|entire|system)\s+(prompt|instructions?|system\s+prompt)"),
    ("repeat_instructions", "reveal", r"(?i)repeat\s+(everything|all|the\s+words|the\s+text|the\s+prompt|what\s+I\s+said)"),
    ("print_system", "reveal", r"(?i)print\s+(the\s+)?(system\s+)?prompt"),
    # Manipulación de output
    ("ignore_format", "manipulation", r"(?i)ignore\s+(your\s+)?(format|output\s+format|response\s+format)"),
    ("dont_mention", "manipulation", r"(?i)don.?t\s+(mention|say|tell|include|show|reveal)\s+"),
    ("respond_in", "manipulation", r"(?i)respond\s+(in|with|using)\s+(only|just|exclusively)\s+"),
    # Separación de instrucciones (delimiters)
    ("delimiter_bypass", "delimiter", r"(?i)(---|\"\"\"|\"\"\"|===|###)\s*(ignore|forget|new\s+instructions?|override)"),
    ("hidden_delimiter", "delimiter", r"(?i)(system\s+prompt|new\s+prompt|secret\s+instructions?)\s*[:\-]"),
]

# Patrones de seguridad en skills y archivos
SKILL_DANGEROUS_PATTERNS: List[Tuple[str, str, str]] = [
    ("exec_command", "execution", r"(?i)(os\.system|subprocess\.|exec\(|eval\(|__import__)"),
    ("file_write_anywhere", "filesystem", r"(?i)(open\(.*[\"\'][\/~]|write\(.*[\"\'][\/~])"),
    ("env_access", "secrets", r"(?i)(os\.environ|getenv|environ\.get)"),
    ("api_key_hardcoded", "secrets", r"(?i)(api_key|api.?key|token|password|secret)\s*[=:]\s*[\"\'][a-zA-Z0-9_\-]{20,}"),
    ("network_call", "network", r"""(?i)(requests\.|urllib\.|http\.|urlopen|curl\s|wget\s)"""),
    ("shell_injection", "execution", r"(?i)(shell=True|shell\s*=\s*True|bash\s*-c|cmd\s*/c)"),
]

# Extensiones de archivo que se escanean
SCANNABLE_EXTENSIONS = {".md", ".yaml", ".yml", ".txt", ".json", ".py", ".sh", ".toml", ".cfg", ".conf"}

# Archivos que NUNCA se tocan (sistema)
PROTECTED_FILES = {".env", "gateway.lock", "gateway.pid", "gateway_state.json", "state.db", "state.db-shm", "state.db-wal"}


# ─────────────────────────────────────────────
# MODELOS DE DATOS
# ─────────────────────────────────────────────


@dataclass
class ScanFinding:
    """Un hallazgo de seguridad encontrado durante el escaneo."""
    level: str                    # "red" | "yellow" | "orange"
    category: str                 # "prompt_injection" | "dangerous_code" | "sensitive_content"
    pattern_id: str               # ID del patrón que coincidió
    match_text: str               # Texto que coincidió
    line_number: int              # Línea donde se encontró
    file_path: str                # Archivo donde se encontró
    severity: str = "medium"      # "critical" | "high" | "medium" | "low"


@dataclass
class ScanReport:
    """Reporte completo de escaneo de un archivo o directorio."""
    file_path: str
    total_lines: int = 0
    findings: List[ScanFinding] = field(default_factory=list)
    sanitized: bool = False
    was_blocked: bool = False
    error: str = ""

    @property
    def has_critical(self) -> bool:
        return any(f.severity == "critical" for f in self.findings)

    @property
    def has_high(self) -> bool:
        return any(f.severity == "high" for f in self.findings)


# ─────────────────────────────────────────────
# PROMPT SCANNER
# ─────────────────────────────────────────────


class PromptScanner:
    """Escanea texto en busca de prompt injection y contenido peligroso."""

    def __init__(self):
        self._red_set = {p.lower().strip() for p in RED_PHRASES}
        self._yellow_set = {w.lower().strip() for w in YELLOW_WORDS}

    def scan_text(self, text: str, file_path: str = "") -> ScanReport:
        """Escanea un texto completo."""
        report = ScanReport(file_path=file_path)
        lines = text.split("\n")
        report.total_lines = len(lines)

        for i, line in enumerate(lines, 1):
            line_lower = line.lower().strip()

            # 🔴 RED: bloqueo inmediato
            for phrase in self._red_set:
                if phrase in line_lower:
                    report.findings.append(ScanFinding(
                        level="red", category="red_content",
                        pattern_id=f"red_{phrase[:20]}",
                        match_text=line.strip()[:120],
                        line_number=i, file_path=file_path,
                        severity="critical",
                    ))

            # 🟡 YELLOW: palabras sensibles
            for word in self._yellow_set:
                if word in line_lower:
                    report.findings.append(ScanFinding(
                        level="yellow", category="sensitive_content",
                        pattern_id=f"yellow_{word[:15]}",
                        match_text=line.strip()[:120],
                        line_number=i, file_path=file_path,
                        severity="low",
                    ))

            # 🟠 PROMPT INJECTION: patrones
            for pid, cat, pattern in PROMPT_INJECTION_PATTERNS:
                if re.search(pattern, line):
                    report.findings.append(ScanFinding(
                        level="orange", category=f"prompt_injection_{cat}",
                        pattern_id=pid,
                        match_text=line.strip()[:120],
                        line_number=i, file_path=file_path,
                        severity="high",
                    ))

        return report

    def scan_file(self, file_path: Path) -> ScanReport:
        """Escanea un archivo completo."""
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
            return self.scan_text(text, str(file_path))
        except Exception as e:
            return ScanReport(file_path=str(file_path), error=str(e))

    def has_injection(self, text: str) -> bool:
        """Check rápido: True si hay inyección o contenido rojo."""
        report = self.scan_text(text)
        return report.has_critical or report.has_high


# ─────────────────────────────────────────────
# SANITIZER
# ─────────────────────────────────────────────


class Sanitizer:
    """Limpia contenido eliminando líneas con inyección."""

    def __init__(self, scanner: Optional[PromptScanner] = None):
        self._scanner = scanner or PromptScanner()

    def sanitize_text(self, text: str, file_path: str = "") -> Tuple[str, ScanReport]:
        """Limpia un texto. Retorna (texto_limpio, reporte).
        - Líneas 🔴 RED: eliminadas completamente
        - Líneas 🟠 INJECTION: eliminadas (no se puede confiar)
        - Líneas 🟡 YELLOW: preservadas pero reportadas
        """
        report = ScanReport(file_path=file_path)
        lines = text.split("\n")
        report.total_lines = len(lines)
        clean_lines = []
        removed_count = 0

        for i, line in enumerate(lines, 1):
            line_lower = line.lower().strip()
            should_remove = False

            # 🔴 RED
            for phrase in self._scanner._red_set:
                if phrase in line_lower:
                    report.findings.append(ScanFinding(
                        level="red", category="red_content",
                        pattern_id=f"red_{phrase[:20]}",
                        match_text=line.strip()[:120],
                        line_number=i, file_path=file_path,
                        severity="critical",
                    ))
                    should_remove = True
                    break

            if should_remove:
                removed_count += 1
                continue

            # 🟠 PROMPT INJECTION
            for pid, cat, pattern in PROMPT_INJECTION_PATTERNS:
                if re.search(pattern, line):
                    report.findings.append(ScanFinding(
                        level="orange", category=f"prompt_injection_{cat}",
                        pattern_id=pid,
                        match_text=line.strip()[:120],
                        line_number=i, file_path=file_path,
                        severity="high",
                    ))
                    should_remove = True
                    break

            if should_remove:
                removed_count += 1
                continue

            # 🟡 YELLOW: solo reportar, no eliminar
            for word in self._scanner._yellow_set:
                if word in line_lower:
                    report.findings.append(ScanFinding(
                        level="yellow", category="sensitive_content",
                        pattern_id=f"yellow_{word[:15]}",
                        match_text=line.strip()[:120],
                        line_number=i, file_path=file_path,
                        severity="low",
                    ))

            clean_lines.append(line)

        report.sanitized = removed_count > 0
        report.was_blocked = report.has_critical
        return "\n".join(clean_lines), report

    def sanitize_file(self, file_path: Path, backup: bool = True) -> ScanReport:
        """Limpia un archivo in-place. Crea backup si se solicita."""
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
            clean_text, report = self.sanitize_text(text, str(file_path))

            if report.sanitized and backup:
                backup_path = file_path.with_suffix(file_path.suffix + ".bak")
                file_path.rename(backup_path)

            if report.sanitized:
                file_path.write_text(clean_text, encoding="utf-8")

            return report
        except Exception as e:
            return ScanReport(file_path=str(file_path), error=str(e))


# ─────────────────────────────────────────────
# CAJA SEGURA — Security Sandbox
# ─────────────────────────────────────────────


@dataclass
class CajaSeguraReport:
    """Reporte completo de una operación de Caja Segura."""
    source: str                    # "adoption" | "skill_import" | "file_check"
    items_scanned: int = 0
    items_cleaned: int = 0
    items_blocked: int = 0
    findings: List[ScanFinding] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    timestamp: float = 0.0
    duration_ms: float = 0.0

    @property
    def passed(self) -> bool:
        """True si todos los items pasaron o fueron limpiados."""
        return self.items_blocked == 0 and not self.errors


class CajaSegura:
    """Caja Segura — sandbox de seguridad para archivos entrantes.

    Cualquier archivo que venga de fuera (perfiles adoptados, skills
    importados, etc.) debe pasar por Caja Segura antes de integrarse.
    """

    def __init__(self):
        self._scanner = PromptScanner()
        self._sanitizer = Sanitizer(self._scanner)
        self._audit_log: List[dict] = []

    # ── Escanear ──────────────────────────

    def scan_profile(self, profile_dir: Path) -> CajaSeguraReport:
        """Escanea un perfil completo adoptado."""
        report = CajaSeguraReport(
            source="adoption",
            timestamp=time.time(),
        )
        start = time.time()

        if not profile_dir.is_dir():
            report.errors.append(f"Directorio no encontrado: {profile_dir}")
            return report

        for file_path in sorted(profile_dir.rglob("*")):
            if not file_path.is_file():
                continue
            if file_path.name in PROTECTED_FILES:
                continue
            if file_path.suffix.lower() not in SCANNABLE_EXTENSIONS:
                continue

            file_report = self._scanner.scan_file(file_path)
            report.items_scanned += 1
            report.findings.extend(file_report.findings)

            if file_report.has_critical:
                report.items_blocked += 1

        report.duration_ms = (time.time() - start) * 1000
        self._audit(report)
        return report

    def scan_skill(self, skill_dir: Path) -> CajaSeguraReport:
        """Escanea un skill importado."""
        report = CajaSeguraReport(
            source="skill_import",
            timestamp=time.time(),
        )
        start = time.time()

        if not skill_dir.is_dir():
            report.errors.append(f"Skill no encontrado: {skill_dir}")
            return report

        for file_path in sorted(skill_dir.rglob("*")):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in SCANNABLE_EXTENSIONS:
                continue

            file_report = self._scanner.scan_file(file_path)
            report.items_scanned += 1
            report.findings.extend(file_report.findings)

            if file_report.has_critical:
                report.items_blocked += 1

        report.duration_ms = (time.time() - start) * 1000
        self._audit(report)
        return report

    def scan_file(self, file_path: Path) -> ScanReport:
        """Escanea un archivo individual."""
        return self._scanner.scan_file(file_path)

    # ── Limpiar ───────────────────────────

    def clean_profile(self, profile_dir: Path, backup: bool = True) -> CajaSeguraReport:
        """Limpia un perfil completo: escanea + sanitiza."""
        scan_report = self.scan_profile(profile_dir)
        clean_report = CajaSeguraReport(
            source="adoption",
            timestamp=time.time(),
        )
        start = time.time()

        if scan_report.items_blocked > 0:
            # Si hay críticos, bloquear todo el perfil
            clean_report.items_blocked = scan_report.items_blocked
            clean_report.findings = scan_report.findings
            return clean_report

        for file_path in sorted(profile_dir.rglob("*")):
            if not file_path.is_file():
                continue
            if file_path.name in PROTECTED_FILES:
                continue
            if file_path.suffix.lower() not in SCANNABLE_EXTENSIONS:
                continue

            file_report = self._sanitizer.sanitize_file(file_path, backup=backup)
            clean_report.items_scanned += 1
            if file_report.sanitized:
                clean_report.items_cleaned += 1
            clean_report.findings.extend(file_report.findings)

        clean_report.duration_ms = (time.time() - start) * 1000
        self._audit(clean_report)
        return clean_report

    # ── Reportes ──────────────────────────

    def print_scan_report(self, report: CajaSeguraReport):
        """Imprime reporte formateado."""
        if not report.items_scanned and not report.errors:
            print("  📭 Caja Segura: nada que escanear.")
            return

        print()
        print(f"  🔒 CAJA SEGURA — {report.source}")
        print(f"  {'─' * 45}")
        print(f"  Escaneados: {report.items_scanned}")
        print(f"  Limpiados:  {report.items_cleaned}")
        print(f"  Bloqueados: {report.items_blocked}")
        print(f"  Hallazgos:  {len(report.findings)}")

        if report.findings:
            # Agrupar por nivel
            by_level = {"red": 0, "orange": 0, "yellow": 0}
            for f in report.findings:
                if f.level in by_level:
                    by_level[f.level] += 1
            if by_level["red"]:
                print(f"    🔴 Red:   {by_level['red']}")
            if by_level["orange"]:
                print(f"    🟠 Orange: {by_level['orange']}")
            if by_level["yellow"]:
                print(f"    🟡 Yellow: {by_level['yellow']}")

            # Mostrar primeros hallazgos críticos
            critical = [f for f in report.findings if f.severity == "critical"]
            if critical:
                print(f"\n  ❌ BLOQUEADO — {len(critical)} hallazgo(s) crítico(s):")
                for f in critical[:5]:
                    path = Path(f.file_path).name
                    print(f"     [{f.pattern_id}] {path}:{f.line_number}")
                    print(f"      \"{f.match_text[:80]}\"")

        if report.errors:
            print(f"\n  ⚠️  Errores: {len(report.errors)}")
            for e in report.errors[:3]:
                print(f"     {e}")

        print()
        print(f"  ⏱  {report.duration_ms:.0f}ms")
        print()

    # ── Auditoría ─────────────────────────

    def _audit(self, report: CajaSeguraReport):
        """Registra en auditoría."""
        entry = {
            "timestamp": report.timestamp,
            "source": report.source,
            "scanned": report.items_scanned,
            "cleaned": report.items_cleaned,
            "blocked": report.items_blocked,
            "findings": len(report.findings),
            "passed": report.passed,
        }
        self._audit_log.append(entry)


# ─────────────────────────────────────────────
# SECURITY GATE — Guardrail ultrarrápido para el AIAgent
# ─────────────────────────────────────────────

# Tools consideradas "externas" (pueden traer contenido no confiable)
EXTERNAL_TOOLS = {"web_search", "web_extract", "web_scrape",
                  "browser_navigate", "browser_vision"}

# Patrón rápido para credenciales (output gate)
CREDENTIAL_PATTERN = re.compile(r"(?i)(sk-[a-zA-Z0-9]{20,}|api_key[\s]*[=:][\s]*['\"][a-zA-Z0-9_\-]{20,}|TELEGRAM_BOT_TOKEN[\s]*[=:])")


class SecurityGate:
    """Guardrail ultrarrápido para mensajes del AIAgent.

    Una sola pasada lineal por el texto. ~2ms de overhead.
    No bloquea el flujo del agente.

    Uso:
        gate = SecurityGate()
        result = gate.check_input("mensaje del usuario")
        if result["blocked"]:
            return result["response"]
        agent.process_message(result["clean_message"])
    """

    def __init__(self):
        self._scanner = PromptScanner()
        self._sanitizer = Sanitizer(self._scanner)
        self._stats = {"inputs_checked": 0, "blocked": 0,
                       "sanitized": 0, "passed": 0}

    # ── Input Gate (obligatorio) ───────────

    def check_input(self, text: str) -> dict:
        """Revisa un mensaje de entrada. Retorna dict con resultado.

        Return:
            {"blocked": True, "response": "...", "reason": "..."}
            {"blocked": False, "clean_message": "...", "sanitized": True}
        """
        self._stats["inputs_checked"] += 1

        # 1. Pre-check rápido: si es muy corto y sin patrones, pasar directo
        if len(text) < 10:
            self._stats["passed"] += 1
            return {"blocked": False, "clean_message": text, "sanitized": False}

        # 2. Scanner completo (una pasada)
        report = self._scanner.scan_text(text)

        # 3. 🔴 RED: bloqueo inmediato
        if report.has_critical:
            self._stats["blocked"] += 1
            return {
                "blocked": True,
                "response": "⛔ No puedo procesar esa solicitud.",
                "reason": "red_content",
                "findings": report.findings[:3],
            }

        # 4. 🟠 INJECTION: sanitizar
        if report.has_high:
            clean_text, clean_report = self._sanitizer.sanitize_text(text)
            self._stats["sanitized"] += 1
            return {
                "blocked": False,
                "clean_message": clean_text,
                "sanitized": True,
                "removed_lines": sum(1 for f in clean_report.findings
                                     if f.severity == "high"),
            }

        # 5. 🟢 GREEN: pasar directo
        self._stats["passed"] += 1
        return {"blocked": False, "clean_message": text, "sanitized": False}

    # ── Tool Output Gate (solo externos) ───

    def check_tool_output(self, tool_name: str, output: str) -> dict:
        """Revisa el resultado de un tool. Solo para fuentes externas.

        Return:
            {"safe": True, "output": output}
            {"safe": False, "output": "output sanitizado", "sanitized": True}
        """
        if tool_name not in EXTERNAL_TOOLS:
            return {"safe": True, "output": output}

        if not output or len(output) < 20:
            return {"safe": True, "output": output}

        report = self._scanner.scan_text(output)

        # Si hay inyección en resultado externo, sanitizar
        if report.has_high or report.has_critical:
            clean, _ = self._sanitizer.sanitize_text(output)
            self._stats["sanitized"] += 1
            return {"safe": False, "output": clean, "sanitized": True}

        return {"safe": True, "output": output}

    # ── Output Gate (opcional, rápido) ─────

    def check_output(self, text: str) -> dict:
        """Revisa la respuesta final por credenciales filtradas.

        Return:
            {"safe": True}
            {"safe": False, "warning": "..."}
        """
        if not text:
            return {"safe": True}

        match = CREDENTIAL_PATTERN.search(text)
        if match:
            return {
                "safe": False,
                "warning": "Posible filtración de credenciales en la respuesta",
            }
        return {"safe": True}

    # ── Stats ──────────────────────────────

    def stats(self) -> dict:
        return dict(self._stats)

    def print_stats(self):
        s = self._stats
        total = s["inputs_checked"] or 1
        blocked_pct = s["blocked"] / total * 100
        print(f"\n  🔒 SECURITY GATE — Stats")
        print(f"  {'─' * 35}")
        print(f"  Revisados:  {s['inputs_checked']}")
        print(f"  Bloqueados: {s['blocked']} ({blocked_pct:.1f}%)")
        print(f"  Sanitizados: {s['sanitized']}")
        print(f"  Aprobados:  {s['passed']}")

    def get_audit_log(self, limit: int = 20) -> List[dict]:
        """Retorna los últimos N registros de auditoría."""
        return self._audit_log[-limit:]

    def print_audit(self, limit: int = 10):
        """Imprime el log de auditoría."""
        if not self._audit_log:
            print("  📭 Sin registros de auditoría.")
            return
        print(f"\n  📋 AUDITORÍA — Caja Segura")
        print(f"  {'─' * 45}")
        for entry in self._audit_log[-limit:]:
            icon = "✅" if entry["passed"] else "❌"
            ts = time.strftime("%H:%M:%S", time.localtime(entry["timestamp"]))
            print(f"  {icon} [{ts}] {entry['source']}: "
                  f"{entry['scanned']} escaneados, "
                  f"{entry['cleaned']} limpiados, "
                  f"{entry['blocked']} bloqueados")
        print()
