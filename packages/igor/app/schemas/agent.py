# SPDX-FileCopyrightText: 2026 Ahmet Erol Bayrak
# SPDX-License-Identifier: AGPL-3.0-or-later

from datetime import datetime

from pydantic import BaseModel


class AgentModelInfo(BaseModel):
    """One agent's model allocation, as shown in the model routing UI."""

    agent_id: str
    name: str
    domain: str
    override: str | None      # owner's runtime pin; None = profile policy
    telegram_override: str | None = None
    default_main: str         # profile's interactive-grade model
    default_background: str   # profile's background-tier model


class AgentModelSet(BaseModel):
    agent_id: str
    model: str | None = None  # None/empty = clear the pin, back to profile policy


class AgentTelegramModelSet(BaseModel):
    agent_id: str
    model: str | None = None  # None/empty = clear the pin, use desktop model
