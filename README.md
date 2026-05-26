# DIGOS — Intelligent Agent System

Versión 0.3 — Fase 7: Producción

Sistema multi-agente con Control Tower, orquestación de agentes,
capa de transparencia en tiempo real, seguridad por capas y
comunicación entre agentes vía Unix Sockets.

## Arquitectura

```
Control Tower (broker central)
├── Fase 1: Onboarding Engine
├── Fase 2: TORRE (Centinela, Engineer, Self-Awareness)
├── Fase 3: Gateways (Telegram, CLI)
├── Fase 4: Transparencia + AIAgent con LLM
├── Fase 5: Adoption + Security Guardrail
├── Fase 6: Message Bus + Tickets por perfil
└── Fase 7: Auto-launch (launchd)
```

## Componentes

| Archivo | Descripción |
|---------|-------------|
| `digos.py` | Control Tower + TORRE + Gateways |
| `agent.py` | AIAgent con LLM y tool calling |
| `transparency.py` | ToolProgressTracker en tiempo real |
| `adoption.py` | Adoption + Transformation Engine |
| `security.py` | CajaSeguraInfo + SecurityCaja + SecurityGate |
| `bus.py` | Message Bus multi-agente (Unix Sockets) |
| `tests.py` | Suite de pruebas (36 tests) |
| `engineer-manual.md` | Manual del Ingeniero Jefe |

## Uso

```bash
# Iniciar DIGOS
python3 digos.py

# Modo daemon 24/7
python3 digos.py --daemon

# Instalar auto-arranque
python3 digos.py --install

# Estado del sistema
python3 digos.py --status

# Ejecutar tests
python3 tests.py
```
