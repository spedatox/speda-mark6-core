# SPDX-FileCopyrightText: 2026 Ahmet Erol Bayrak
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Agent metadata and model allocation.

Core runs a single agent, so what is left of the multi-agent surface is the
model matrix: the profile's own defaults, the deployment override, and the
owner's runtime pin. There is no roster to list online, no comms channel, no
Legion worker matrix and no House Party — those went with the multi-agent
engine (see IGOR.md).
"""

import logging

from fastapi import APIRouter, HTTPException, Request

from app.core.runtime_state import (
    get_agent_models,
    get_telegram_models,
    set_agent_model,
    set_telegram_model,
)
from app.schemas.agent import (
    AgentModelInfo,
    AgentModelSet,
    AgentTelegramModelSet,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["agents"])


@router.get("/agents/models", response_model=list[AgentModelInfo])
async def agent_models(request: Request):
    """The agent's model allocation: profile defaults + the owner's runtime pin,
    if any. Feeds the model selector in the UI."""
    from app.config import settings

    overrides = get_agent_models()
    tg_overrides = get_telegram_models()
    return [
        AgentModelInfo(
            agent_id=p.agent_id,
            name=p.name,
            domain=p.domain,
            override=overrides.get(p.agent_id),
            telegram_override=tg_overrides.get(p.agent_id),
            # What allocate_model would pick WITHOUT the owner's pin — the .env
            # deployment override, else the profile's own models. The background
            # line is derived from the main model's PROVIDER (never a hardcoded
            # Anthropic tier), so the matrix shows what would actually run.
            default_main=settings.llm_main_model or p.sonnet_model,
            default_background=(
                settings.llm_background_model
                or p.cheap_tier(settings.llm_main_model or p.sonnet_model)
            ),
        )
        for p in request.app.state.profiles.roster()
    ]


@router.post("/agents/models", response_model=list[AgentModelInfo])
async def agent_model_set(body: AgentModelSet, request: Request):
    """Pin the agent to a model ref (or clear the pin with model=null). The pin
    wins over the profile's allocation for interactive runs."""
    if request.app.state.profiles.get(body.agent_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown agent '{body.agent_id}'")
    set_agent_model(body.agent_id, (body.model or "").strip() or None)
    return await agent_models(request)


@router.post("/agents/telegram-models", response_model=list[AgentModelInfo])
async def agent_telegram_model_set(body: AgentTelegramModelSet, request: Request):
    """Pin a Telegram-specific model (or clear with model=null)."""
    if request.app.state.profiles.get(body.agent_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown agent '{body.agent_id}'")
    set_telegram_model(body.agent_id, (body.model or "").strip() or None)
    return await agent_models(request)
