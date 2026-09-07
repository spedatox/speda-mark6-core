# SPDX-FileCopyrightText: 2026 Ahmet Erol Bayrak
# SPDX-License-Identifier: AGPL-3.0-or-later

"""
Automated (n8n) turn runner — an automated turn IS a chat turn.

Rule 1 keeps the trigger router logic-free; this module is where that logic
lives. It exists because the two paths had silently drifted apart: a chat turn
was persisted, stamped, titled, indexed and detached, while a triggered turn
was an ad-hoc loop inside the router that streamed into a list and threw
everything away. The session row was still created, so the owner saw a "New
conversation" in the sidebar that opened empty — the work happened, nothing
survived it — and the next run started blind because no history existed.

So a triggered run now goes through exactly the machinery a chat turn does:

  seed → saved as a real user message → load_history (timestamp-stamped from
  created_at, same as chat) → AgentContext → TurnRegistry.start(...) → the
  assistant turn (with its tool calls and files) is persisted by the runner →
  post-turn tasks (session log, recap, compaction, embeddings) → delivery.

Consequences that are the whole point: the transcript is readable in the app,
`/chat/attach/{request_id}` can tail a briefing live, `/chat/cancel` stops one,
a crashed run still leaves its partial work behind, and the next turn in that
session sees what the last one did.

Delivery (push → Telegram → Notification row) hangs off the settle hook rather
than the success hook, so a run that errors half-way still delivers what it
produced — the pre-existing behaviour, kept deliberately.
"""

import logging
import time
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.clock import owner_now
from app.core.context import AgentContext
from app.database import AsyncSessionLocal
from app.models.message import Message
from app.services import language
from app.services.chat_history import final_answer_text

logger = logging.getLogger(__name__)

# How much of a worker's raw findings the report card carries for display. The
# reply is the answer; this is the receipt behind it, and a receipt nobody can
# scroll is no better than one nobody can open.
REPORT_DISPLAY_CHARS = 6000


def format_trigger_context(payload: dict) -> dict:
    """
    Normalise an n8n trigger payload into a standard context dict.
    Adds defaults for fields n8n may omit.
    """
    return {
        "type": payload.get("type", "unknown"),
        "job": payload.get("job"),
        "from_agent": payload.get("from"),
        "event": payload.get("event"),
        "raw": payload,
    }


def _language_clause() -> str:
    """The language contract, restated at the END of an automated seed.

    It is already in the system prompt, and for a chat turn that is enough. An
    automation is the case where it is not: the stored `intent` was composed in
    whatever language the owner's original wish happened to be written in, it
    sits immediately above the reply the model is about to write, and a concrete
    "ÇIKTI: …" section beats an abstract rule twenty thousand tokens earlier.
    That is why briefings kept arriving in Turkish however firmly the contract
    was worded — the instruction the agent was actually reading contradicted it.

    So it is repeated here, last, where recency is on its side, and it says
    explicitly that the intent's own language is not a signal. New intents are
    composed in the chosen language now (services/automation_intent.py), but
    every automation stored before that still carries the old one, and this is
    what makes those fire correctly without a migration.
    """
    name = language.name_of()
    return (
        f"\n\nLANGUAGE — the message you are about to write goes to the owner in "
        f"{name}, every word of it. The intent above may be written in another "
        f"language; that is an artifact of when it was composed and is NOT an "
        f"instruction about which language to answer in. Read it in whatever "
        f"language it is in, and write the message itself in {name} — section "
        f"labels, day names, dates and units included."
    )


def build_seed(payload: dict, output_mode: str) -> str:
    """The single user turn that kicks off an automated run.

    An automation fires with no human in the loop, so the seed must push the
    agent to EXECUTE its stored workflow with real tools — not to narrate or
    fabricate. The old wording ("compose the message the owner should see") let
    weaker models write a plausible-looking briefing without ever calling Gmail,
    the calendar, news_headlines or system_info. This says the opposite,
    explicitly, and tells the agent how its output is delivered so it doesn't
    double-send via send_telegram_message on a push.

    Returned RAW, with no timestamp: the caller persists it and reads it back
    through load_history, which stamps it from its stored created_at exactly
    like a chat message. That stamp is how any agent knows the current date —
    the system prompt deliberately carries no clock (it would churn the cached
    prefix every minute), and an unstamped automated turn left agents date-blind,
    querying date-scoped tools against whatever "today" their training suggested.
    """
    intent = payload.get("intent") or ""
    delivery = {
        "respond": "Your reply streams straight back to the owner.",
        "push": (
            "Whatever you write as your reply IS delivered to the owner as a push "
            "notification — so do NOT also call send_telegram_message; that would "
            "double-send. Your composed text is the delivery."
        ),
        "silent": (
            "This is a silent run: your reply is stored, not shown to anyone right "
            "now. Still do the real work; keep the write-up brief."
        ),
    }.get(output_mode, "")

    return (
        "AUTOMATED TRIGGER — no human is waiting on this turn, so you must ACT, "
        "not narrate.\n\n"
        "The `intent` below is a workflow you wrote earlier for your future self. "
        "Execute it now, step by step, with your real tools:\n"
        "- Actually CALL each tool the intent implies. If a tool isn't loaded yet "
        "(Gmail, Calendar, Notion, …), load it with use_toolset first, then call "
        "it. news_headlines and system_info are always available.\n"
        "- Build every part of your message ONLY from what the tools actually "
        "return. If a tool errors or a section has nothing, SAY SO plainly — "
        "'no new important mail', 'calendar unavailable'. Never invent mail, "
        "events, headlines, or numbers. Fabricated data is a failure, not a "
        "fallback.\n"
        "- Your reply IS the message, start to finish — no transition sentence "
        "about writing it first ('I have everything I need, let me compose "
        "the briefing', 'here's the summary:'). The owner never sees that "
        "line as a separate step; it just reads as the opening of the report, "
        "which makes no sense there.\n"
        f"- {delivery}\n\n"
        f"intent: {intent}\n\n"
        f"full payload: {payload}"
        + _language_clause()
    )


def trigger_meta(payload: dict, output_mode: str) -> dict:
    """Display-only provenance for the seed turn, carried in the `_speda_meta`
    block the UI already knows how to recover on reload.

    A triggered run is a normal conversation in the app — but the owner did not
    write its opening message, and a bubble attributed to them would be a lie
    the next reader has no way to catch. This is what lets the UI label the
    sender as the automation instead. `_clean` strips the block before the
    history goes back to the model, so it costs nothing in the prompt.
    """
    meta = {
        "source": "n8n",
        "from_agent": payload.get("to_agent") or "",
        "label": _label(payload),
        "job": payload.get("job") or payload.get("event") or payload.get("type") or "",
        "automation": payload.get("automation") or "",
        "output_mode": output_mode,
    }
    return meta


def _label(payload: dict) -> str:
    raw = (
        payload.get("automation")
        or payload.get("job")
        or payload.get("event")
        or payload.get("type")
        or "Automated run"
    )
    label = str(raw).replace("_", " ").replace("-", " ").strip() or "Automated run"
    return f"{label[:1].upper()}{label[1:]}"


def session_title(payload: dict, today: datetime | None = None) -> str:
    """Name the session from the automation itself, at launch.

    Set up front rather than left to generate_title: the owner should be able to
    tell this morning's brief from yesterday's in the sidebar the moment it
    fires, and a model-written title derived from the seed would just paraphrase
    the "AUTOMATED TRIGGER" boilerplate every time. generate_title is idempotent
    on an already-titled session, so it steps aside.
    """
    # The owner's date, not the container's: a run at 01:00 Istanbul is still
    # "yesterday" in UTC, and the sidebar would name it the wrong day.
    stamp = (today or owner_now()).strftime("%d %b")
    return f"{_label(payload)} · {stamp}"[:255]


async def start_trigger_turn(
    *,
    db: AsyncSession,
    profile,
    payload: dict,
    output_mode: str,
    request_id: str,
    orchestrator,
    turns,
    session_manager,
    telegram_bots,
    user_id: int = 1,
    triggered_by: str = "n8n",
    session_id: int | None = None,
) -> tuple[str | None, int]:
    """Launch an automated turn as a detached, persisted chat turn.

    Returns (request_id | None, session_id) — None means the turn registry was
    at capacity and nothing was started, which the router reports to n8n so it
    can retry instead of assuming the job ran.

    `triggered_by` defaults to "n8n" because that is who fires all of these.

    `session_id` continues an EXISTING conversation instead of opening a new
    one. n8n never passes it — each run is its own thread.
    """
    agent_id = profile.agent_id
    model = profile.allocate_model(triggered_by)

    session = await session_manager.get_or_create(
        db=db,
        user_id=user_id,
        triggered_by=triggered_by,
        model_used=model,
        agent_id=agent_id,
        session_id=session_id,
    )
    if session_id is not None and session.agent_id != agent_id:
        # Wrong room. Sessions are scoped by (user_id, agent_id), so appending
        # here would hand this turn another transcript's history as context.
        logger.warning(
            "report_room_mismatch",
            extra={
                "request_id": request_id, "agent_id": agent_id,
                "session_id": session_id, "session_agent": session.agent_id,
            },
        )
        session = await session_manager.get_or_create(
            db=db,
            user_id=user_id,
            triggered_by=triggered_by,
            model_used=model,
            agent_id=agent_id,
        )
    if session.title is None:
        session.title = session_title(payload)
        await db.commit()

    # Persist FIRST, then load history back — the same order chat uses, so the
    # seed is stamped from its own created_at and the transcript the owner opens
    # is byte-identical to the prompt the model saw.
    meta = trigger_meta(payload, output_mode)
    seed_block: dict = {"type": "_speda_meta", "trigger": meta}
    if meta.get("report"):
        # What the BUBBLE would show, if anything ever falls back to showing one:
        # a headline, never the seed. The seed is scaffolding — the instructions
        # the agent needed to write the reply — and rendering it as a message
        # from the owner is both a lie and a wall of text over the answer.
        seed_block["text"] = report_headline(meta["report"])
    await session_manager.save_message(
        db,
        session.id,
        "user",
        [
            {"type": "text", "text": build_seed(payload, output_mode)},
            seed_block,
        ],
    )
    history = await session_manager.load_history(db, session.id)

    context = AgentContext(
        agent_id=agent_id,
        user_id=user_id,
        session_id=session.id,
        request_id=request_id,
        triggered_by=triggered_by,
        trigger_payload=format_trigger_context(payload),
        output_mode=output_mode,
        model=model,
        system_prompt="",
        conversation_history=history,
        db=db,  # replaced with the runner's own session before the engine runs
        timezone=settings.owner_timezone,
    )
    # Toolsets loaded in an earlier turn of this session stay loaded, exactly as
    # in chat — otherwise every run re-calls use_toolset and rewrites the cache.
    context.extra["active_servers"] = session_manager.get_loaded_servers(session.id)
    # The same provenance the seed was persisted with, handed to the STREAM. A
    # client watching this turn arrive must render what a client reloading it
    # later renders — one card, from one dict, whichever way it got here.
    context.extra["trigger_meta"] = meta

    bg_model = profile.background_model(model)

    async def on_complete() -> None:
        from app.services.memory import run_post_turn_tasks

        await run_post_turn_tasks(session.id, request_id, user_id, bg_model)

    async def on_settle(status: str) -> None:
        await _deliver(
            agent_id=agent_id,
            session_id=session.id,
            request_id=request_id,
            user_id=user_id,
            output_mode=output_mode,
            payload=payload,
            telegram_bots=telegram_bots,
            status=status,
            profile=profile,
            sanitize_model=bg_model,
        )

    started = turns.start(
        context=context,
        engine_factory=lambda ctx: orchestrator.run(ctx),
        format_error=lambda exc: f"Automated run failed: {exc}",
        on_complete=on_complete,
        on_settle=on_settle,
    )
    return started, session.id


async def _deliver(
    *,
    agent_id: str,
    session_id: int,
    request_id: str,
    user_id: int,
    output_mode: str,
    payload: dict,
    telegram_bots,
    status: str,
    profile=None,
    sanitize_model: str = "",
) -> None:
    """Post-run delivery: stamp the automation, record what happened, then
    push if asked.

    The text comes back out of the DB rather than off a stream, so what the
    owner is sent is the turn the transcript shows — including the runner's
    marker when a turn broke off early. Not all of it, though: delivery takes
    the turn's closing answer only, never the between-tool narration that
    precedes it (see chat_history.final_answer_text).
    """
    async with AsyncSessionLocal() as db:
        automation_name = payload.get("automation")
        automation_row = None
        if automation_name:
            from app.automations.manager import mark_fired

            automation_row = await mark_fired(str(automation_name), db)

        # Fetched unconditionally — a proactive_ask or silent firing delivers
        # nothing through this function (the reminders tool does its own
        # delivery mid-turn, or there is simply nothing to push), but the run
        # history below still wants to know what the turn actually produced.
        text = await _last_assistant_text(db, session_id)
        delivered = False
        channel = "silent"

        if output_mode != "push":
            pass
        elif not text:
            logger.warning(
                "trigger_push_empty",
                extra={"request_id": request_id, "status": status},
            )
        else:
            # The sender bot is derived from the agent, never passed by n8n —
            # a push speaks from the agent's own bot. If every bot is
            # unreachable, persist a Notification row so nothing is lost.
            if payload.get("voice"):
                delivered = await _deliver_voice(
                    agent_id=agent_id, text=text, profile=profile,
                    title=str(payload.get("automation") or ""), telegram_bots=telegram_bots,
                    request_id=request_id, sanitize_model=sanitize_model,
                )
                channel = "voice"
            else:
                # A push has not been shown to him yet, so unlike a streamed
                # chat reply a language leak here is still repairable — and a
                # Telegram notification is exactly the surface where a stray
                # word is most visible, because there is no conversation
                # around it to explain itself. The voice branch above does
                # not need this: it runs the same check inside
                # tts.prepare_speech_text, and paying for two rewrite passes
                # on one message would be the wrong trade.
                text = await language.enforce(text, sanitize_model)
                delivered = await telegram_bots.deliver_message(agent_id, text)
                channel = "text"
            if not delivered:
                await _store_notification(db, agent_id, user_id, request_id, text, payload)
            logger.info(
                "trigger_push_delivered" if delivered else "trigger_push_stored",
                extra={"request_id": request_id, "chars": len(text), "status": status},
            )

        if automation_row is not None:
            from app.automations.manager import record_run

            await record_run(
                automation_row.id, db,
                status=status, delivered=delivered, channel=channel, report=text,
                request_id=request_id, session_id=session_id,
            )


async def _deliver_voice(
    *, agent_id: str, text: str, profile, title: str, telegram_bots, request_id: str,
    sanitize_model: str = "",
) -> bool:
    """Speak `text` and send it as a Telegram audio message instead of plain
    text — the point of an automation's "reply as voice" checkbox
    (composer.py bakes `voice: true` into the trigger payload; see
    automations/templates.py).

    Resolves voice + tuning through the SAME precedence /voice/speak uses
    (tts.resolve_voice/resolve_voice_settings): the owner's pin from
    Settings → Voices outranks the profile's own default. Falls back to
    plain text on ANY synthesis or delivery failure — a misconfigured or
    rate-limited TTS key must never mean the owner gets nothing instead of
    the briefing he actually asked to hear, only in a format he didn't ask
    for.

    `sanitize_model` is the caller's already-resolved background-tier model
    (Rule 10 — this module names none itself); passed to
    `tts.prepare_speech_text` so a stray unit or leftover "let me compose
    this" line gets a real model's read on it. Text is prepared ONCE and the
    same spoken string is used for both the audio and its caption/fallback —
    the owner must never see a transcript that says something different from
    what the clip actually says.
    """
    from app.services import tts

    voice_ref = tts.resolve_voice(None, agent_id, profile=profile)
    voice_settings = tts.resolve_voice_settings(agent_id)
    try:
        spoken = await tts.prepare_speech_text(text, sanitize_model=sanitize_model)
        audio = await tts.synthesize_prepared(spoken, voice_ref, voice_settings=voice_settings)
    except tts.TTSError as exc:
        logger.warning(
            "automation_voice_synthesis_failed",
            extra={"request_id": request_id, "agent_id": agent_id, "error": str(exc)},
        )
        return await telegram_bots.deliver_message(agent_id, text)

    # Truncate the NAME first, then append the extension — slicing the whole
    # "name.mp3" string can land mid-extension for a long title and hand
    # Telegram a file with no recognizable type.
    short_title = (title or agent_id)[:60]
    ok = await telegram_bots.deliver_voice(
        agent_id, audio, f"{short_title}.mp3", title=short_title, caption=spoken,
    )
    if not ok:
        return await telegram_bots.deliver_message(agent_id, spoken)
    # Telegram caps a caption at 1024 chars — send_audio truncates silently to
    # respect that. A voice briefing stays well under it (the polisher's own
    # 80-120 word budget), but the transcript itself must never be the thing
    # that gets cut, so anything that could overflow the cap also goes out as
    # its own message, in full.
    if len(spoken) > 1000:
        await telegram_bots.deliver_message(agent_id, spoken)
    return True


async def _last_assistant_text(db: AsyncSession, session_id: int) -> str:
    """What gets delivered for the newest assistant turn: its closing answer,
    with the model's between-tool narration left behind in the transcript.

    A briefing is written after the last tool returns; everything before that is
    the agent talking to itself about which tool to reach for next. On a push
    there is no stream and no tool disclosure to give that text a context, so it
    lands in Telegram as a preamble of stage directions above the report."""
    row = (
        await db.execute(
            select(Message)
            .where(Message.session_id == session_id, Message.role == "assistant")
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(1)
        )
    ).scalars().first()
    if row is None:
        return ""
    if isinstance(row.content, str):
        return row.content.strip()
    return final_answer_text(row.content)


async def _store_notification(
    db: AsyncSession, agent_id: str, user_id: int, request_id: str,
    text: str, payload: dict,
) -> None:
    """Fallback when no Telegram bot could deliver (unconfigured / unlinked):
    persist the push as a Notification row so the desktop app surfaces it on next
    open. Best-effort — a storage failure must not crash the task."""
    try:
        from app.models.notification import Notification

        title = str(payload.get("event") or payload.get("job") or "Update")[:255]
        db.add(
            Notification(
                user_id=user_id,
                source_agent=agent_id,
                triggered_by="n8n",
                title=title,
                body=text,
                priority=str(payload.get("priority", "normal")),
                delivered=False,
            )
        )
        await db.commit()
    except Exception as e:  # noqa: BLE001
        logger.error(
            "trigger_notification_store_failed",
            extra={"request_id": request_id, "error": str(e)},
        )


# ── Background completion reports ────────────────────────────────────────────


# How long a finished report waits for the room to be free before giving up and
# opening its own session. Generous on purpose: the alternative to waiting is
# the context loss this whole path exists to avoid, and the waiting happens in
# a detached background task with a durable ticket behind it.
_ROOM_WAIT_S = 300.0
