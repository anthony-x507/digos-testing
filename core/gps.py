"""
gps.py — Guidance Persistence System
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

The GPS is the guide. It knows the DESTINATION (final goal),
the COURSE (planned steps), and tracks DEVIATIONS.

It does NOT speak to the user. It does NOT make decisions.
It provides data to SELF (the agent's soul) so SELF can decide.

Key innovation: deviation analysis.
- "on_track"         → everything aligned, proceed
- "necessary_detour" → deviating but it serves the destination, proceed silently
- "off_track"        → deviation conflicts with destination, SELF must ask user
- "new_direction"    → user changed the destination entirely, SELF must confirm
"""

import json
import os
import re
from typing import Optional, List
import time
from typing import Literal


DeviationResult = Literal["on_track", "necessary_detour", "off_track", "new_direction"]

# ─── WORD ROOTS & SEMANTIC HELPERS ──────────────────────────────

# Common stop words to exclude from matching
_STOP_WORDS: set[str] = {
    "a", "an", "the", "in", "on", "at", "to", "for", "of", "with",
    "by", "is", "are", "was", "were", "be", "been", "being", "have",
    "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "this", "that",
    "these", "those", "it", "its", "and", "or", "but", "not",
    "no", "nor", "so", "if", "then", "else", "all", "each",
    "every", "some", "any", "none", "both", "neither", "either",
}

# Suffix stripping rules (simplified Porter-style)
_SUFFIX_RULES: list[tuple[str, str]] = [
    ("sses", "ss"),    # processes → process
    ("ied", "y"),      # studied → study
    ("ies", "y"),      # carries → carry
    ("ying", "y"),     # studying → study
    ("ingly", "ing"),  # interesting → interest
    ("ation", "ate"),  # creation → create
    ("ition", "ite"),  # definition → define
    ("ssion", "ss"),   # session → sess
    ("ction", "ct"),   # connection → connect
    ("ment", ""),      # development → develop
    ("able", ""),      # adaptable → adapt
    ("ible", ""),      # accessible → access
    ("ness", ""),      # awareness → aware
    ("less", ""),      # useless → use
    ("fully", ""),     # carefully → care
    ("hood", ""),      # likelihood → likely
    ("ship", ""),      # relationship → relation
    ("like", ""),      # childlike → child
    ("wise", ""),      # likewise → like
    ("ward", ""),      # forward → forw
    ("wards", ""),     # backwards → back
    ("ed", ""),        # worked → work
    ("ing", ""),       # working → work
    ("es", ""),        # boxes → box
    ("s", ""),         # cars → car
    ("ly", ""),        # quickly → quick
    ("er", ""),        # worker → work
    ("est", ""),       # largest → large
    ("al", ""),        # architectural → architectur
    ("ive", ""),       # creative → creat
    ("ous", ""),       # dangerous → danger
    ("ic", ""),        # scientific → scientif
    ("ize", ""),       # realize → real
]

# Word family groups — synonyms and related words
_WORD_FAMILIES: list[set[str]] = [
    # Building / construction
    {"build", "create", "construct", "make", "develop", "architect", "design", "craft", "forge", "shape", "assemble", "establish", "found", "erect", "form"},
    # Coding / development
    {"code", "program", "script", "develop", "implement", "write", "compile", "debug", "refactor", "codify", "software", "app", "application"},
    # System / architecture
    {"system", "architecture", "structure", "framework", "platform", "infrastructure", "engine", "core", "backbone", "foundation"},
    # Testing / validation
    {"test", "check", "verify", "validate", "audit", "review", "inspect", "examine", "confirm", "ensure", "qa", "quality"},
    # Setup / installation
    {"install", "setup", "configure", "init", "initialize", "bootstrap", "deploy", "prepare", "download", "dependencies", "dependency", "requirements", "prerequisites"},
    # Learning / research
    {"learn", "study", "research", "explore", "understand", "comprehend", "read", "examine", "analyze", "investigate", "master"},
    # Agent / AI
    {"agent", "ai", "intelligence", "model", "llm", "reasoning", "inference", "prompt", "context", "memory", "autonomous"},
    # Communication
    {"message", "communicate", "respond", "reply", "answer", "tell", "ask", "explain", "describe", "clarify"},
    # Security
    {"security", "secure", "protect", "safety", "guard", "shield", "encrypt", "auth", "permission", "access"},
    # Data
    {"data", "information", "content", "knowledge", "config", "config", "state", "storage", "file", "database"},
]


def _stem(word: str) -> str:
    """Strip common suffixes to get the word root."""
    # Must be at least 3 chars after suffix removal
    for suffix, replacement in _SUFFIX_RULES:
        if len(word) > len(suffix) + 2 and word.endswith(suffix):
            return word[: -len(suffix)] + replacement
    return word


def _word_families(word: str) -> set[str]:
    """Get all words in the same family group."""
    stemmed = _stem(word)
    related = {stemmed, word}
    for family in _WORD_FAMILIES:
        if stemmed in family or word in family:
            related.update(family)
    return related


def _extract_keywords(text: str) -> set[str]:
    """Extract meaningful keywords from text with stemming."""
    words = re.findall(r"[a-záéíóúñü]+", text.lower())
    result: set[str] = set()
    for w in words:
        if w not in _STOP_WORDS and len(w) > 1:
            result.add(_stem(w))
    return result


def _semantic_overlap(a_words: set[str], b_words: set[str]) -> float:
    """
    Calculate semantic overlap ratio between two sets of stemmed keywords.
    Returns 0.0 to 1.0 — how much of set A is semantically related to set B.
    """
    if not a_words or not b_words:
        return 0.0

    # For each word in A, check if it belongs to a family in B
    b_families = {w: _word_families(w) for w in b_words}

    matches = 0
    for a_word in a_words:
        a_family = _word_families(a_word)
        # Check if any B word shares a family with A
        for b_word in b_words:
            if a_word == b_word or a_word in b_families.get(b_word, set()) or b_word in a_family:
                matches += 1
                break

    return matches / len(a_words)


class GPS:
    """The Guidance Persistence System — lives at ~/.digos/agents/{name}/ROCKET/GPS/"""

    FOLDER_NAMES = {
        "DESTINATION": "DESTINATION.md",
        "COURSE": "COURSE.md",
        "DEVIATIONS": "DEVIATIONS.md",
    }

    def __init__(self, rocket_path: str):
        self.gps_path = os.path.join(rocket_path, "GPS")
        os.makedirs(self.gps_path, exist_ok=True)
        self._files = {
            key: os.path.join(self.gps_path, fname)
            for key, fname in self.FOLDER_NAMES.items()
        }

    # ─── DESTINATION ────────────────────────────────────────────

    def set_destination(self, title: str, description: str, steps: list[str]) -> None:
        """Set the final goal. Steps are high-level milestones."""
        dest = {
            "title": title,
            "description": description,
            "steps": steps,
            "current_step": 0,
            "started_at": time.time(),
            "updated_at": time.time(),
        }
        with open(self._files["DESTINATION"], "w") as f:
            json.dump(dest, f, indent=2)

    def get_destination(self) -> Optional[dict]:
        """Get the current destination. Returns None if not set."""
        try:
            with open(self._files["DESTINATION"]) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return None

    def advance_step(self) -> bool:
        """Move to the next step. Returns False if already at last step."""
        dest = self.get_destination()
        if not dest:
            return False
        if dest["current_step"] >= len(dest["steps"]) - 1:
            return False
        dest["current_step"] += 1
        dest["updated_at"] = time.time()
        with open(self._files["DESTINATION"], "w") as f:
            json.dump(dest, f, indent=2)
        return True

    def destination_complete(self) -> bool:
        """Check if all destination steps are complete."""
        dest = self.get_destination()
        if not dest or not dest.get("steps"):
            return False
        return dest["current_step"] >= len(dest["steps"]) - 1

    # ─── COURSE ─────────────────────────────────────────────────

    def set_course(self, steps: list[dict]) -> None:
        """
        Set the detailed course. Each step:
          {"id": "step-1", "title": "...", "status": "pending|active|done|blocked"}
        """
        course = {
            "steps": steps,
            "updated_at": time.time(),
        }
        with open(self._files["COURSE"], "w") as f:
            json.dump(course, f, indent=2)

    def get_course(self) -> List[dict]:
        """Get all course steps."""
        try:
            with open(self._files["COURSE"]) as f:
                return json.load(f).get("steps", [])
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def set_step_status(self, step_id: str, status: str) -> bool:
        """Update a single step's status."""
        steps = self.get_course()
        for step in steps:
            if step.get("id") == step_id:
                step["status"] = status
                self.set_course(steps)
                return True
        return False

    # ─── DEVIATIONS ─────────────────────────────────────────────

    def log_deviation(self, description: str, context: str = "") -> None:
        """Log a deviation that occurred during execution."""
        devs = self._load_deviations()
        devs.append({
            "time": time.time(),
            "description": description,
            "context": context,
            "resolved": False,
        })
        with open(self._files["DEVIATIONS"], "w") as f:
            json.dump(devs, f, indent=2)

    def resolve_deviation(self, index: int) -> bool:
        """Mark a deviation as resolved."""
        devs = self._load_deviations()
        if 0 <= index < len(devs):
            devs[index]["resolved"] = True
            with open(self._files["DEVIATIONS"], "w") as f:
                json.dump(devs, f, indent=2)
            return True
        return False

    def _load_deviations(self) -> List[dict]:
        try:
            with open(self._files["DEVIATIONS"]) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def get_active_deviations(self) -> List[dict]:
        """Get all unresolved deviations."""
        return [d for d in self._load_deviations() if not d["resolved"]]

    # ─── THE CORE — Deviation Analysis ─────────────────────────

    def analyze_deviation(self, user_message: str, active_task: str = "") -> DeviationResult:
        """
        Analyze whether a deviation from the user is part of the journey
        or a change of direction.

        This is the KEY innovation over Hermes.

        Uses semantic word families and stemming to detect:
          "on_track"         — user is still working on the destination, full alignment
          "necessary_detour" — deviation is a sub-task needed for the destination
          "off_track"        — deviation conflicts with or is irrelevant to destination
          "new_direction"    — user explicitly changed the subject/destination
        """
        dest = self.get_destination()

        # No destination set — every message defines a new one
        if not dest:
            return "new_direction"

        dest_title = dest.get("title", "")
        dest_desc = dest.get("description", "")
        dest_text = f"{dest_title} {dest_desc}"

        # Get stemmed keyword sets
        dest_words = _extract_keywords(dest_text)
        msg_words = _extract_keywords(user_message)
        task_words = _extract_keywords(active_task) if active_task else set()

        if not msg_words:
            return "off_track"

        # ─── 1. Check semantic overlap with destination ──────────
        dest_overlap_ratio = _semantic_overlap(msg_words, dest_words)

        # ─── 2. Check semantic overlap with active task ──────────
        task_overlap_ratio = 0.0
        if task_words:
            task_overlap_ratio = _semantic_overlap(msg_words, task_words)

        # ─── 3. Greeting / chitchat detection ────────────────────
        greetings = {"hola", "hello", "hey", "hi", "buenos", "gracias", "ok", "okay", "sí", "si", "yeah", "yes"}
        is_greeting = bool(msg_words & greetings)
        is_very_short = len(msg_words) <= 2

        if is_greeting and is_very_short:
            return "on_track"

        # ─── 4. Decision logic ───────────────────────────────────
        # Strong destination alignment → on_track
        if dest_overlap_ratio >= 0.4:
            return "on_track"

        # Weak destination + strong task alignment → necessary_detour
        if task_overlap_ratio >= 0.4 and dest_overlap_ratio < 0.4:
            return "necessary_detour"

        # Moderate destination alignment → on_track
        if dest_overlap_ratio >= 0.2:
            return "on_track"

        # Moderate task alignment → necessary_detour (sub-task work)
        if task_overlap_ratio >= 0.2:
            return "necessary_detour"

        # Check for necessary action words (setup, install, configure, etc.)
        # These are often necessary detours even without keyword match
        action_words = _extract_keywords(
            "install setup configure prepare download init bootstrap "
            "setup deploy prepare fix repair restore recover migrate "
            "move copy backup organize clean refactor review check"
        )
        action_overlap = _semantic_overlap(msg_words, action_words)
        if action_overlap >= 0.15 and active_task:
            return "necessary_detour"

        # Check if user is asking about the system or asking for help
        # These are "on_track" — they're about the work
        help_words = _extract_keywords(
            "how what why when where which help question explain "
            "show tell suggest recommend advise propose plan think"
        )
        help_overlap = _semantic_overlap(msg_words, help_words)
        if help_overlap >= 0.3 and active_task:
            return "on_track"

        # No match at all — off track or new direction
        # Check if the message is long and substantive (likely a new goal)
        if len(user_message.split()) >= 8:
            return "new_direction"

        return "off_track"

    # ─── CONSENSUS ──────────────────────────────────────────────

    def check_consensus(self, current_work_title: str) -> dict:
        """
        GPS checks if the current work still aligns with the destination
        using semantic word family matching.

        Returns:
          {"consensus": True/False, "reason": "...", "question": "..."}
        """
        dest = self.get_destination()
        if not dest:
            return {
                "consensus": False,
                "reason": "No destination set",
                "question": "What is our destination?",
            }

        dest_title = dest.get("title", "")
        dest_desc = dest.get("description", "")
        dest_text = f"{dest_title} {dest_desc}"

        # Use semantic matching
        work_words = _extract_keywords(current_work_title)
        dest_words = _extract_keywords(dest_text)

        if not work_words:
            # No active work yet — consensus is fine, we're starting
            return {"consensus": True, "reason": "No active work yet — starting fresh"}

        overlap_ratio = _semantic_overlap(work_words, dest_words)

        if overlap_ratio >= 0.2:
            return {"consensus": True, "reason": "Aligned"}

        else:
            devs = self.get_active_deviations()
            dev_reason = ""
            if devs:
                dev_reason = f" ({len(devs)} unresolved deviation(s))"

            return {
                "consensus": False,
                "reason": f"Current work '{current_work_title}' doesn't align with destination '{dest_title}'{dev_reason}",
                "question": f"We were working toward '{dest_title}' but now we're working on '{current_work_title}'. Do we continue with the original destination, or has the goal changed?",
            }
