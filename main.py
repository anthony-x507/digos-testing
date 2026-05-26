#!/usr/bin/env python3
"""
DIGOS 0.1 — Main Entry Point
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FINAL FLOW (DESPUÉS de refactorizar debut FÁBRICA):
  1. FÁBRICA se activa — verifica si ya hay configuración
  2. Si NO hay: FÁBRICA corre onboarding completo (sin Tower)
     → Guarda todo en Vault encriptado
  3. Control Tower nace (lee config desde Vault)
  4. Torre produce Agente Primero (con Kendo + WORK DESTINATION)
  5. Gateway daemon inicia (lee token desde Vault)
  6. Handoff: Agente Primero toma control

Principio:
  FÁBRICA → Vault → Tower → Gateway → Agent
  (Cada fase lee del Vault, no recibe objetos de fases anteriores)

Usage:
  python main.py
"""
import os
import sys
import time

_PROJECT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT not in sys.path:
    sys.path.insert(0, _PROJECT)


def main():
    # ── 1. FÁBRICA se activa primero ──
    from puerta.vault import Vault

    vault = Vault()
    is_configured = vault.is_configured()

    if not is_configured:
        print("[DIGOS] Primera ejecución — FÁBRICA iniciando onboarding...")
        from puerta.onboarding import run_onboarding

        # FÁBRICA corre onboarding sin Tower: idioma → API key → gateway token
        success = run_onboarding(vault)
        if not success:
            print("[DIGOS] Onboarding falló — no se puede continuar.")
            sys.exit(1)

        vault.mark_configured()
        print("[DIGOS] FÁBRICA: configuración completada y almacenada.")
    else:
        print("[DIGOS] FÁBRICA: configuración previa detectada.")

    # ── 2. Control Tower nace (DESPUÉS de onboarding) ──
    from puerta.torre import ControlTower, KendoSeed, WorkDestinationSeed

    torre = ControlTower(vault=vault)
    torre.nacer()

    # ── 3. Agente Primero nace (con Kendo + WORK DESTINATION) ──
    ap = torre.get_agente_primero()
    if ap is None:
        # Tower lee provider/model del vault
        ap = torre.spawn_agente_primero()
        print(f"[DIGOS] Agente Primero nació: {ap.agent_id}")
        print(f"[DIGOS]   Kendo:          {'✓' if ap.has_kendo else '✗'}")
        print(f"[DIGOS]   WORK DEST:      {'✓' if ap.has_work_destination else '✗'}")
        print(f"[DIGOS]   Proveedor:      {ap.provider or '?'}")
        print(f"[DIGOS]   Modelo:         {ap.model or '?'}")
        print(f"[DIGOS]   Gateway:        {vault.get('config:gateway_type', '?')}")

    # ── 4. Gateway daemon inicia (token desde Vault) ──
    gateway_type = vault.get("config:gateway_type")
    if gateway_type and gateway_type != "cli":
        token = vault.get(f"gateway:{gateway_type}")
        if token:
            print(f"[DIGOS] Iniciando gateway {gateway_type}...")
            # TODO (Fase 4 CAJA): gateway daemon real con polling
            print(f"[DIGOS]   Gateway {gateway_type} listo (token en vault).")

    # ── 5. Status ──
    status = torre.status_report()
    lang = vault.get("config:language", "?")
    provider = vault.get("config:provider", "?")
    gw = vault.get("config:gateway_type", "none")
    print(f"""
[DIGOS] ──── Status ────
  Uptime:       {status['uptime_seconds']}s
  Configurado:  {'✓' if is_configured else '✗'}
  Idioma:       {lang}
  Proveedor:    {provider}
  Gateway:      {gw}
  Agente Prim:  {ap.agent_id[:16] if ap else 'none'}...
  Sub-agentes:  {status['sub_agentes_count']}
[DIGOS] ────────────────""")

    # ── 6. Handoff: Agente Primero toma control ──
    if gateway_type and gateway_type != "cli":
        print("[DIGOS] ✓ Handoff completo. Agente Primero al mando via", gateway_type)
    else:
        print("[DIGOS] Modo CLI — agente listo para interactuar.")

    return torre


if __name__ == "__main__":
    torre = main()
