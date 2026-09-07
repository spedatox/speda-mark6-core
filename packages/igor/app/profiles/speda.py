# SPDX-FileCopyrightText: 2026 Ahmet Erol Bayrak
# SPDX-License-Identifier: AGPL-3.0-or-later

import re
from pathlib import Path

from app.profiles.base import AgentProfile, DocTheme
from app.prompts.loader import assemble, build_skills_manifest, derive_iteration

_IDENTITY_PATH = Path(__file__).parent.parent / "prompts" / "core" / "01_identity.md"


def _derive_agent_name() -> str:
    """
    Single source of the agent's display name: the identity file's H1 heading.
    `# IDENTITY — Speda Mark VI` → "Speda Mark VI". Falls back to "Speda".
    This means editing prompts/core/01_identity.md rebrands the back-end too —
    no need to touch this file.
    """
    try:
        first_line = _IDENTITY_PATH.read_text(encoding="utf-8").splitlines()[0]
        match = re.match(r"#\s*IDENTITY\s*[—\-:]\s*(.+)", first_line)
        if match:
            return match.group(1).strip()
    except Exception:
        pass
    return "Speda"


# Derived once at import — the agent's display name (used for the FastAPI title).
AGENT_NAME = _derive_agent_name()

# Core sections assembled in order.
# The skills manifest is appended dynamically — it reads SKILL.md frontmatter at
# request time so adding a new skill only requires dropping a SKILL.md file.
PROMPT_SECTIONS = [
    "core/01_identity.md",   # full identity: who/how/boundaries/runtime
    "core/02_voice.md",      # register
    "core/03_capabilities.md",
    "core/04_decision_policy.md",
    "core/05_output_policy.md",
    "core/06_visual_output.md",   # always-loaded — no tool backs this, must be in core
    "core/07_formatting.md",      # math/LaTeX + currency formatting guidance
    "core/08_memory.md",          # persistent memory protocol (Anthropic memory pattern)
    "core/09_environment.md",  # Core ecosystem glossary (Igor/Striker/sandbox/browser/n8n)
    "core/10_patterns.md",   # the pattern loop: induce a repeat, pre-empt it next time
    "core/11_signature.md",   # sign every artifact you leave outside the chat
    "core/12_calendar.md",   # all time-related work: read the calendar, then write it properly
    "core/13_language.md",   # the one language the owner picked — every word, every surface
]


class SPEDAProfile(AgentProfile):
    """
    Speda — the one and only agent on Core, addressed by agent_id="speda".
    Never put prompt content in core modules.
    """

    agent_id = "speda"
    domain = "orchestration & general executive assistance"
    doc_theme = DocTheme(accent="#36abca")   # signature cyan — matches the UI brand
    # None = full registry access. Core has one agent and it sees every tool.
    tool_allowlist = None
    episodic_recall_scope = "all"

    name = AGENT_NAME   # derived from 01_identity.md — never hardcode here
    # The agent's own iteration, read off PROMPT_SECTIONS[0] (its identity
    # prompt). Bump the `Iteration:` line there and the signature follows.
    mark = derive_iteration(PROMPT_SECTIONS[0])
    sonnet_model = "claude-sonnet-4-6"
    haiku_model = "claude-haiku-4-5-20251001"
    # ElevenLabs "Adam" (deep, steady — the default assistant voice) — verify this id exists in the
    # owner's ElevenLabs voice library (GET /voice/voices) and swap it
    # if not; premade voice ids can vary by plan/account.
    # Was Azure "en-US-BrianMultilingualNeural" before the ElevenLabs move.
    voice_id = "elevenlabs:eleven_multilingual_v2:pNInz6obpgDQGcFmaJgB"
    canvas_brief = (
        "Presenting as the orchestrator: whatever the answer is ABOUT gets a "
        "window — a person or place as a card with its photo, a set of figures as "
        "stat tiles or a chart, a set of dates as a timeline, a source as an "
        "article. You are the one who decides the board is worth opening at all, "
        "so open it when there is something to see and simply speak when there is "
        "not"
    )

    # Cheapest sensible model per non-Anthropic provider, used for background
    # tasks when the user is chatting on that provider (see base.background_model).
    background_models = {
        "openai": "openai:gpt-5-mini",
        "gemini": "gemini:gemini-3.5-flash-lite",
        "vertex": "vertex:google/gemini-3.5-flash-lite",
        "zai": "zai:glm-4.5-air",
        "deepseek": "deepseek:deepseek-v4-flash",
        "nvidia": "nvidia:meta/llama-3.1-8b-instruct",
    }

    def build_system_prompt(self, context_vars: dict) -> str:
        core = assemble(PROMPT_SECTIONS, context_vars)
        manifest = build_skills_manifest()
        return f"{core}\n\n{manifest}" if manifest else core
