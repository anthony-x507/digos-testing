"""
self.py — Self-Awareness Engine (THE SOUL)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SELF is the agent. The soul. Where the person lives.

It has IDENTITY (who am I) and STATE (where am I right now).
It talks to GPS for guidance and WORK for execution tracking.

Only SELF talks to the user. GPS and WORK never do.

The key function: check_consensus() — if SELF detects GPS and
WORK disagree, SELF asks the user what to do.
"""

import json
import os
import time
from typing import Optional, List, Tuple

from .gps import GPS
from .work import WorkTracker


class SelfAwareness:
    """Self-awareness engine — the soul of the agent."""

    def __init__(self, rocket_path: str):
        self.rocket_path = rocket_path
        self.self_path = os.path.join(rocket_path, "SELF")
        os.makedirs(self.self_path, exist_ok=True)

        self.gps = GPS(rocket_path)
        self.work = WorkTracker(rocket_path)
        self._identity = None
        self._state = None

    # ─── IDENTITY ───────────────────────────────────────────────

    def set_identity(self, name: str, role: str, description: str, traits: List[str]) -> None:
        """Define who the agent is. This is the core personality."""
        identity = {
            "name": name,
            "role": role,
            "description": description,
            "traits": traits,
            "created_at": time.time(),
            "version": 1,
        }
        self._write("IDENTITY.md", identity)

    def get_identity(self) -> Optional[dict]:
        """Know thyself."""
        if self._identity is None:
            self._identity = self._read("IDENTITY.md")
        return self._identity

    # ─── STATE ──────────────────────────────────────────────────

    def set_state(self, mood: str = "ready", focus: str = "", notes: str = "") -> None:
        """Record current state of mind. Updated after every interaction."""
        state = {
            "mood": mood,
            "focus": focus,
            "notes": notes,
            "updated_at": time.time(),
        }
        self._write("STATE.md", state)
        self._state = state

    def get_state(self) -> Optional[dict]:
        """Where am I right now?"""
        if self._state is None:
            self._state = self._read("STATE.md")
        return self._state

    # ─── SYSTEM PROMPT GENERATION ───────────────────────────────

    def build_system_prompt(self) -> str:
        """
        Build the complete system prompt from IDENTITY + GPS + WORK.
        This is what the LLM sees when it starts.

        Structure:
        1. Who I am (identity)
        2. Where I'm going (GPS destination + course)
        3. What I'm doing (current work)
        4. Any deviations to be aware of
        """
        identity = self.get_identity()
        destination = self.gps.get_destination()
        course = self.gps.get_course()
        deviations = self.gps.get_active_deviations()

        lines = []
        lines.append("You are an autonomous AI agent. Read this context carefully.")

        # ── Identity block ──
        if identity:
            lines.append(f"\n## IDENTITY")
            lines.append(f"Name: {identity.get('name', 'Unknown')}")
            lines.append(f"Role: {identity.get('role', 'Agent')}")
            lines.append(f"About: {identity.get('description', '')}")
            if identity.get("traits"):
                lines.append("Traits: " + ", ".join(identity["traits"]))

        # ── GPS block ──
        if destination:
            lines.append(f"\n## DESTINATION")
            lines.append(f"Goal: {destination.get('title', 'Not set')}")
            lines.append(f"Description: {destination.get('description', '')}")
            steps = destination.get("steps", [])
            current = destination.get("current_step", 0)
            if steps:
                lines.append(f"Progress: step {current + 1} of {len(steps)}")
                for i, step in enumerate(steps):
                    marker = "→" if i == current else " "
                    lines.append(f"  {marker} {step}")
            if destination.get("completed"):
                lines.append("Status: ✅ COMPLETE")

        if course:
            lines.append(f"\n## COURSE")
            for step in course:
                status_symbol = {
                    "pending": "○", "active": "◉", "done": "✓", "blocked": "✗"
                }.get(step.get("status", "pending"), "○")
                lines.append(f"  {status_symbol} {step.get('title', 'Unknown step')}")

        if deviations:
            lines.append(f"\n## ACTIVE DEVIATIONS ({len(deviations)})")
            for i, dev in enumerate(deviations):
                lines.append(f"  {i+1}. {dev.get('description', 'Unknown')}")

        # ── Consensus check result ──
        lines.append(f"\n## GUIDANCE")
        lines.append("You have a GPS tracking your destination and course.")
        lines.append("If the user's messages seem to diverge from the destination,")
        lines.append("check with your GPS first. If GPS says 'off_track', ask the user")
        lines.append("if they want to continue the original destination or change course.")
        lines.append("Do NOT ask for every minor deviation — trust your GPS analysis.")
        lines.append("Only interrupt the user when GPS returns 'off_track' or 'new_direction'.")

        return "\n".join(lines)

    # ─── TRIPLE CONSENSUS — SELF + GPS + WORK ─────────────────────

    def triple_consensus(self, user_message: str = None, active_task_title: str = "") -> dict:
        """
        THREE-WAY CHECK: SELF awareness + GPS destination + WORK active task.

        This is the heart of the self-aware system:
        1. SELF_CHECK: Does SELF know its identity? Is state consistent?
        2. GPS_CHECK: Does destination exist? Does user message align with it?
        3. WORK_CHECK: Does active work align with destination? Is it progressing?

        Returns a detailed breakdown showing WHAT aligns and WHAT doesn't.
        The calling agent (display.py) uses this to decide how to behave.
        """
        result = {
            "consensus": True,
            "self_check": {"ok": False, "detail": ""},
            "gps_check": {"ok": False, "detail": ""},
            "work_check": {"ok": False, "detail": ""},
            "reason": "",
            "question": "",
            "ask_user": False,
        }

        # ─── 1. SELF CHECK ────────────────────────────────────────
        identity = self.get_identity()
        state = self.get_state()
        if not identity:
            result["self_check"] = {"ok": False, "detail": "No identity — agent not initialized"}
            result["consensus"] = False
            result["reason"] = "SELF has no identity set"
        elif state is None:
            result["self_check"] = {"ok": False, "detail": "State is unknown — no prior interaction"}
            result["consensus"] = False
            result["reason"] = "SELF state is unknown"
        else:
            name = identity.get("name", "Unknown")
            mood = state.get("mood", "unknown")
            result["self_check"] = {"ok": True, "detail": f"Agent '{name}' — mood: {mood}"}

        # ─── 2. GPS CHECK ─────────────────────────────────────────
        destination = self.gps.get_destination()
        if not destination:
            result["gps_check"] = {"ok": False, "detail": "No destination set"}
            if result["consensus"]:
                result["consensus"] = False
                result["reason"] = "No destination — system hasn't been pointed at a goal yet"
        elif user_message:
            # GPS analyzes deviation with full context
            deviation = self.gps.analyze_deviation(user_message, active_task_title)
            dest_title = destination.get("title", "unknown")
            if deviation == "on_track":
                result["gps_check"] = {"ok": True, "detail": f"Message aligns with destination '{dest_title}'"}
            elif deviation == "necessary_detour":
                result["gps_check"] = {"ok": True, "detail": f"Detour serves destination '{dest_title}'"}
                result["reason"] = "On a detour that serves the goal — no action needed"
            elif deviation == "off_track":
                result["gps_check"] = {"ok": False, "detail": f"Message deviates from destination '{dest_title}'"}
                result["consensus"] = False
                result["reason"] = "GPS detects off-track deviation"
                result["question"] = f"Destination is '{dest_title}', but your message seems to be about something else. Continue toward destination, or has the goal changed?"
                result["ask_user"] = True
            elif deviation == "new_direction":
                result["gps_check"] = {"ok": False, "detail": f"Message suggests new direction — different from '{dest_title}'"}
                result["consensus"] = False
                result["reason"] = "GPS detects possible destination change"
                result["question"] = f"It looks like you want something new. Set new destination, or continue with '{dest_title}'?"
                result["ask_user"] = True
        else:
            # No message — just check destination exists, not message analysis
            result["gps_check"] = {"ok": True, "detail": f"Destination set: '{destination.get('title', 'unknown')}'"}

        # ─── 3. WORK CHECK ────────────────────────────────────────
        active = self.work.get_active()
        if active_task_title and active:
            work_title = active.get("title", "")
            # Check if active task title aligns with destination
            gps_check_work = self.gps.check_consensus(active_task_title)
            if gps_check_work.get("consensus", False):
                result["work_check"] = {"ok": True, "detail": f"Active task '{active_task_title}' aligns with destination"}
            else:
                result["work_check"] = {"ok": False, "detail": f"Active task '{active_task_title}' may not align with destination"}
                result["consensus"] = False
                if not result["reason"]:
                    result["reason"] = "Work task does not align with GPS destination"
        elif active:
            result["work_check"] = {"ok": True, "detail": f"Active work: '{active.get('title', 'unknown')}'"}
        else:
            result["work_check"] = {"ok": True, "detail": "No active tasks — clean slate"}

        return result

    def check_consensus(self, current_work_title: str) -> dict:
        """Legacy wrapper — delegates to triple_consensus."""
        tc = self.triple_consensus(active_task_title=current_work_title)
        return {
            "consensus": tc["consensus"],
            "reason": tc["reason"],
            "question": tc["question"],
            "ask_user": tc["ask_user"],
            "detail": tc,
        }

    # ═══════════════════════════════════════════════════════════════
    # 🔥 SAFETY CANDLE — Security layer inside SELF
    # ═══════════════════════════════════════════════════════════════
    #
    # Three-tier system:
    #   🔴 RED   (~20 phrases) → IMMEDIATE BLOCK, no GPS/WORK
    #   🟡 YELLOW (~100 words) → INTENT ANALYSIS, no GPS/WORK
    #   🟢 GREEN  (everything else) → normal SELF+GPS+WORK flow
    #
    # CRITICAL RULE: When safety triggers (RED/YELLOW), NEVER activate
    # GPS or WORK. GPS/WORK are for legitimate destinations — if someone
    # has harmful intent, we must NOT help them "plan their route."
    # ═══════════════════════════════════════════════════════════════

    class SafetyCandle:
        """Safety Candle — security layer that lives inside SELF."""

        # ── 🔴 RED PHRASES: ABSOLUTE BLOCK (~20) ────────────────
        RED_PHRASES = [
            "child abuse", "child exploitation", "child pornography",
            "terrorism", "terrorist attack", "sex trafficking",
            "human trafficking", "slavery", "enslave",
            "trafficking children", "exploit child", "sexual abuse child",
            "child sexual abuse", "white slavery", "forced labor",
            "child soldier", "pedophile", "pedophilia",
            "child prostitution", "child trafficking",
            "sexual exploitation", "child sex",
        ]

        # ── 🟡 YELLOW WORDS: SENSITIVE → INTENT ANALYSIS (~100) ─
        YELLOW_WORDS = [
            # Weapons
            "gun", "rifle", "pistol", "shotgun", "automatic weapon",
            "explosive", "bomb", "grenade", "knife", "blade",
            "weapon", "firearm", "ammunition", "bullet",
            "assault rifle", "machine gun", "handgun",
            "machete", "sword", "axe", "poison",
            "chemical weapon", "biological weapon",
            "improvised explosive", "ied", "detonator",
            # Religion (sensitive context)
            "religion", "religious", "faith", "church", "mosque",
            "temple", "allah", "god", "jesus", "bible",
            "quran", "torah", "catholic", "muslim", "jewish",
            "hindu", "buddhist", "islam", "christianity",
            "judaism", "hinduism", "buddhism", "prayer",
            "worship", "preach", "convert", "prophet",
            "scripture", "holy", "divine", "pope", "imam",
            "rabbi", "monk", "priest", "pastor",
            # Drugs
            "drug", "cocaine", "heroin", "meth", "marijuana",
            "cannabis", "opioid", "fentanyl", "lsd", "ecstasy",
            "amphetamine", "morphine", "opium", "shroom",
            "hallucinogen", "narcotic", "substance abuse",
            # Violence
            "kill", "murder", "assassinate", "torture", "harm",
            "attack", "violent", "blood", "death", "die",
            "hurt", "injure", "damage", "destroy",
            "massacre", "slaughter", "execute",
            # Extremism
            "hate", "racist", "nazi", "extremist", "radicalize",
            "terror", "jihad", "suicide bomb", "genocide",
            "supremacist", "fascist", "hate crime",
            # Crime
            "hack", "steal", "rob", "fraud", "scam",
            "blackmail", "ransom", "kidnap", "abduct",
            "poison", "stalk", "harass", "extortion",
            "identity theft", "money laundering",
            "counterfeit", "forgery",
            # Sensitive personal data
            "social security", "credit card", "passport",
            "license", "bank account", "pin code", "password",
            "ssn", "routing number", "driver license",
        ]

        def __init__(self):
            self.red_set = set(p.lower().strip() for p in self.RED_PHRASES)
            self.yellow_set = set(w.lower().strip() for w in self.YELLOW_WORDS)

        # ── SAFETY INDICATORS ────────────────────────────────────
        SAFE_INDICATORS = [
            "research", "study", "science", "academic", "education",
            "learning", "history", "information", "article", "book",
            "paper", "journal", "analysis", "understanding",
            "self-defense", "protection", "security", "safety",
            "awareness", "prevention", "detect", "protect",
            "historical", "cultural", "sociology", "psychology",
            "medicine", "health", "treatment", "therapy",
            "law", "legal", "policy", "regulation",
            "curriculum", "course", "lecture", "textbook",
            "scientific", "experiment", "laboratory",
        ]

        SUSPICIOUS_INDICATORS = [
            "ignore previous", "ignore all", "forget your",
            "you are now", "act as", "pretend to",
            "disregard", "override", "bypass",
            "do not follow", "do not obey", "break free",
            "new role", "new identity", "new persona",
            "no restrictions", "no limits", "no boundaries",
            "evil version", "dark side", "unethical",
            "how to without getting caught", "how to hide",
            "how to avoid detection", "illegal but",
            "tell me how to", "show me how to",
            "pretend you are", "you're now",
            "from now on you", "forget everything",
            "you don't have to", "you don't need to",
        ]

        def check(self, message: str) -> dict:
            """Check message against safety layers.

            Returns:
                {"level": "red", "matches": [...]} — BLOCK now
                {"level": "yellow", "matches": [...]} — analyze intent
                {"level": "green"} — proceed normally
            """
            msg_lower = message.lower().strip()
            if not msg_lower:
                return {"level": "green"}

            # Check RED first — full phrase matching
            red_matches = [p for p in self.red_set if p in msg_lower]
            if red_matches:
                return {"level": "red", "matches": red_matches}

            # Check YELLOW — word-level matching
            yellow_matches = sorted(
                [w for w in self.yellow_set if w in msg_lower],
                key=len, reverse=True  # longest match first (most specific)
            )
            if yellow_matches:
                return {"level": "yellow", "matches": yellow_matches}

            return {"level": "green"}

        def analyze_intent(self, message: str) -> dict:
            """Analyze user intent when YELLOW triggers.

            Returns:
                {"verdict": "accept", "reason": "...", "confidence": N}
                {"verdict": "reject", "reason": "...", "confidence": N}
                {"verdict": "caution", "reason": "...", "confidence": N}
            """
            msg_lower = message.lower().strip()

            # ── 1. Check prompt injection / evasion first ────
            suspicious = [w for w in self.SUSPICIOUS_INDICATORS if w in msg_lower]
            if suspicious:
                return {
                    "verdict": "reject",
                    "reason": f"Prompt injection or evasion detected: {suspicious}",
                    "confidence": 0.9,
                }

            # ── 2. Check for research/educational/legitimate intent ──
            safe = [w for w in self.SAFE_INDICATORS if w in msg_lower]
            if safe:
                return {
                    "verdict": "accept",
                    "reason": f"Legitimate intent detected: {safe}",
                    "confidence": 0.7,
                }

            # ── 3. Very short messages with sensitive words → suspicious ──
            word_count = len(message.split())
            if word_count < 5:
                return {
                    "verdict": "caution",
                    "reason": "Short query with sensitive keyword — insufficient context",
                    "confidence": 0.5,
                }

            # ── 4. Long, detailed messages → good faith assumed ──
            if word_count > 20:
                return {
                    "verdict": "accept",
                    "reason": "Detailed query provides sufficient context — good faith",
                    "confidence": 0.6,
                }

            # ── 5. Default: caution ──
            return {
                "verdict": "caution",
                "reason": "Sensitive keyword without clear intent declaration",
                "confidence": 0.5,
            }

    # ─── ANALYSIS — DETECT DEVIATION TYPE ──────────────────────

    def _safety_first(self, user_message: str) -> dict:
        """Check safety BEFORE touching GPS/WORK.

        Returns:
            {"stop": True, "verdict": ..., "reason": ...} — safety triggered
            {"stop": False} — green, proceed with normal flow
        """
        if not hasattr(self, '_safety'):
            self._safety = self.SafetyCandle()

        safety = self._safety.check(user_message)

        if safety["level"] == "red":
            return {
                "stop": True,
                "verdict": "block",
                "reason": f"🔴 RED SAFETY: {', '.join(safety['matches'])}",
                "confidence": 1.0,
            }

        if safety["level"] == "yellow":
            intent = self._safety.analyze_intent(user_message)
            return {
                "stop": True,  # stops GPS/WORK processing
                "verdict": intent["verdict"],  # accept / reject / caution
                "reason": f"🟡 YELLOW ({', '.join(safety['matches'])}): {intent['reason']}",
                "confidence": intent["confidence"],
                "matches": safety["matches"],
            }

        return {"stop": False}

    def analyze_user_message(self, user_message: str, active_task: str = "") -> dict:
        """
        Analyze what the user said and decide how to respond.

        FLOW:
        1. 🔥 Safety First — check RED/YELLOW before ANYTHING else
        2. If safety stops → return verdict immediately (NO GPS/WORK)
        3. If GREEN → use triple_consensus (SELF + GPS + WORK)

        Returns a decision dict for engine.py to execute.
        """
        # ── 🔥 SAFETY FIRST — never touch GPS/WORK on sensitive messages ──
        safety = self._safety_first(user_message)
        if safety["stop"]:
            # Return without calling GPS or WORK at all
            return {
                "action": "safety_" + safety["verdict"],  # block / accept / caution
                "reason": safety["reason"],
                "verdict": safety["verdict"],
                "confidence": safety.get("confidence", 0),
                "matches": safety.get("matches", []),
            }

        # ── 🟢 GREEN — proceed with normal triple_consensus ──
        consensus = self.triple_consensus(user_message, active_task)

        # No destination → first interaction
        if not consensus["gps_check"]["ok"] and "No destination" in consensus["gps_check"]["detail"]:
            return {
                "action": "process_normally",
                "reason": "First interaction, learning destination",
                "consensus_detail": consensus,
            }

        # Full consensus → smooth sailing
        if consensus["consensus"] and consensus["self_check"]["ok"] and consensus["gps_check"]["ok"]:
            return {
                "action": "process_normally",
                "reason": "Triple consensus: SELF + GPS + WORK aligned",
                "consensus_detail": consensus,
            }

        # Detour that serves destination → process but note it
        if consensus["gps_check"]["ok"] and "Detour serves" in consensus["gps_check"]["detail"]:
            return {
                "action": "process_normally_warn",
                "reason": "On a detour — serves the destination but worth noting",
                "consensus_detail": consensus,
            }

        # Off-track → ask user
        if consensus["ask_user"]:
            return {
                "action": "ask_user",
                "reason": consensus["reason"],
                "question": consensus["question"],
                "consensus_detail": consensus,
            }

        return {"action": "process_normally", "reason": "default", "consensus_detail": consensus}

    # ─── INTERNAL HELPERS ───────────────────────────────────────

    def _write(self, filename: str, data: dict) -> None:
        path = os.path.join(self.self_path, filename)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def _read(self, filename: str) -> Optional[dict]:
        path = os.path.join(self.self_path, filename)
        try:
            with open(path) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return None
