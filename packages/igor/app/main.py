# SPDX-FileCopyrightText: 2026 Ahmet Erol Bayrak
# SPDX-License-Identifier: AGPL-3.0-or-later

import asyncio
import logging
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import configure_logging, settings
from app.profiles.speda import AGENT_NAME

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup sequence — order is non-negotiable (CLAUDE.md Build Order).
    Phase 1 done signal: all five criteria in CLAUDE.md must pass.
    """
    logger.info("startup_begin", extra={"version": "0.1.0"})

    # ── 1. Database ────────────────────────────────────────────────────────────
    from app.database import close_db, init_db

    await init_db()
    logger.info("startup_db_ready")

    # ── 2. LLM Client ─────────────────────────────────────────────────────────
    from app.services.llm_client import LLMClient

    llm_client = LLMClient()

    # ── 2.5 Profile ───────────────────────────────────────────────────────────
    # Core is single-agent. The registry stays because the rest of the engine
    # (orchestrator, model resolution, welcome cache) is written against a
    # roster interface — it is simply a roster of one, and there is no
    # dispatcher for it to feed.
    from app.profiles.registry import ProfileRegistry
    from app.profiles.speda import SPEDAProfile

    profiles = ProfileRegistry()
    profiles.register(SPEDAProfile())

    # ── 2.6 Telegram bot ──────────────────────────────────────────────────────
    # Built here (after the profile, before Tier-1 skills) so the delivery skill
    # can take the registry in its constructor. Core has exactly one agent, so
    # this is one bot — constructed only when its token is configured.
    from app.telegram.registry import TelegramBotRegistry

    telegram_agent_ids = {
        p.agent_id for p in profiles.roster() if getattr(p, "telegram_enabled", False)
    }
    telegram_bots = TelegramBotRegistry.from_config(telegram_agent_ids)

    # ── 3. Capability Registry ─────────────────────────────────────────────────
    from app.core.registry import CapabilityRegistry

    registry = CapabilityRegistry(client=llm_client, profiles=profiles)

    # Tier 1 — Python Skills
    # read_skill is the progressive-disclosure meta-tool (registered first so it's
    # always available when Claude wants to load full SKILL.md instructions).
    from app.skills.automations import AutomationsSkill
    from app.skills.budget import BudgetModeSkill
    from app.skills.sandbox import RunCommandSkill, DeliverFileSkill
    from app.skills.toolsets import UseToolsetSkill
    from app.skills.documents import DocumentsSkill
    from app.skills.save_file import SaveFileSkill
    from app.skills.atomix_reports import GenerateDailyTrainingProgramSkill
    from app.skills.memory import MemorySkill
    from app.skills.memory_write import (
        LedgerAppendSkill,
        NarrativeReviseSkill,
        RegistryUpsertSkill,
    )
    from app.skills.observations import (
        ForgetObservationSkill,
        RecordObservationSkill,
        SearchMemorySkill,
    )
    from app.skills.news import (
        NewsDeepDiveSkill,
        NewsHeadlinesSkill,
        NewsWatchSkill,
        ReadArticleSkill,
    )
    from app.skills.notifications import NotificationsSkill
    from app.skills.telegram import SendTelegramFileSkill, SendTelegramMessageSkill
    from app.skills.osint import OSINT_SKILLS
    from app.skills.read_skill import ReadSkillSkill
    from app.skills.search_history import SearchHistorySkill
    from app.skills.semantic_search import SemanticSearchSkill
    from app.skills.stt import STTSkill
    from app.skills.system import SystemSkill
    from app.skills.tts import TTSSkill

    await registry.register_skill(ReadSkillSkill())
    await registry.register_skill(MemorySkill())
    # The observation tier — the sourced, addressable facts beneath the memory
    # files. Registered next to the memory tool because they are one capability
    # with two layers: the file is what gets read, the observation is what can be
    # traced. See app/skills/observations.py.
    # Shape-aware writes: the agent names a month, a date, a person or a chapter,
    # and the placement follows from it. See app/skills/memory_write.py.
    await registry.register_skill(LedgerAppendSkill())
    await registry.register_skill(RegistryUpsertSkill())
    await registry.register_skill(NarrativeReviseSkill())
    await registry.register_skill(RecordObservationSkill())
    await registry.register_skill(SearchMemorySkill())
    await registry.register_skill(ForgetObservationSkill())
    await registry.register_skill(SearchHistorySkill())
    await registry.register_skill(SemanticSearchSkill())
    await registry.register_skill(TTSSkill())
    await registry.register_skill(STTSkill())
    await registry.register_skill(NotificationsSkill())
    await registry.register_skill(SendTelegramMessageSkill(telegram_bots))
    await registry.register_skill(SendTelegramFileSkill(telegram_bots))
    await registry.register_skill(DocumentsSkill())
    await registry.register_skill(SaveFileSkill())
    await registry.register_skill(GenerateDailyTrainingProgramSkill())
    await registry.register_skill(SystemSkill())
    await registry.register_skill(BudgetModeSkill())
    await registry.register_skill(RunCommandSkill())
    await registry.register_skill(DeliverFileSkill())
    # News desk — Tier 1 (RSS store + watchlist + free article read) and Tier 2
    # (NewsData.io analyst, quota-budgeted).
    await registry.register_skill(NewsHeadlinesSkill())
    await registry.register_skill(NewsWatchSkill())
    await registry.register_skill(NewsDeepDiveSkill())
    await registry.register_skill(ReadArticleSkill())
    # Navigation desk — traffic-aware routing + place search (Google Maps
    # Platform). Backend-only key; clients render the ```map fence.
    from app.skills.navigation import GetRouteSkill, FindPlacesSkill
    await registry.register_skill(GetRouteSkill())
    await registry.register_skill(FindPlacesSkill())
    # Aircraft desk — live ADS-B lookup by tail number (airplanes.live,
    # keyless). Read-only + network-gated. Clients render the ```aircraft fence.
    from app.skills.aircraft import TrackAircraftSkill
    await registry.register_skill(TrackAircraftSkill())
    # Weather desk — current conditions + forecast (Open-Meteo, keyless).
    # Read-only + network-gated.
    from app.skills.weather import WeatherSkill
    await registry.register_skill(WeatherSkill())
    # Pharmacy desk — nearest on-duty pharmacies from the official NosyAPI
    # roster. Read-only + network-gated; reuses the find_places place store and
    # ```map fence, so there is no client-side work for it to render.
    from app.skills.pharmacies import OnDutyPharmacySkill
    await registry.register_skill(OnDutyPharmacySkill())
    # Health desk — the owner's biometrics, synced from the phone via Health
    # Connect. Read-only.
    from app.skills.health_data import HealthDataSkill
    await registry.register_skill(HealthDataSkill())

    # The browser — Playwright in its own container (packages/browser). The plan B
    # under every HTTP-only read path, and the only way into the owner's logged-in
    # portals. Skipped entirely when BROWSER_URL is unset: three tools advertising
    # a capability that cannot run costs a turn to discover, every turn.
    from app.skills.browser import BROWSER_SKILLS, browser_available

    if browser_available():
        for _browser_skill in BROWSER_SKILLS:
            await registry.register_skill(_browser_skill())
    else:
        logger.warning("browser_skills_skipped", extra={"reason": "BROWSER_URL not set"})

    # Ankara bus desk — live EGO "Otobüs Nerede?" arrivals by stop number. No
    # official API, and the form's POST sits behind a WAF that only a real
    # browser clears (see services/transit.py) — riding on the sidecar above,
    # so it needs the same BROWSER_URL and is gated the same way.
    if browser_available():
        from app.skills.transit import BusArrivalsSkill
        await registry.register_skill(BusArrivalsSkill())

    # Academic desk — the course attendance ledger, written from the watch
    # (Ultron Wear) and read back here. check_attendance is read-only, so Speda
    # can answer "kaç hakkım kaldı" directly;
    # ask_attendance is the push side, normally driven by the n8n per-lecture
    # trigger. save_schedule is the other direction — the owner's timetable,
    # authored in chat, replacing what the watch caches — and pushes a resync
    # over the same FCM channel ask_attendance uses. See docs/ULTRON_WEAR.md.
    from app.skills.attendance import AskAttendanceSkill, AttendanceStatusSkill
    from app.skills.schedule import SaveScheduleSkill
    await registry.register_skill(AttendanceStatusSkill())
    await registry.register_skill(AskAttendanceSkill())
    await registry.register_skill(SaveScheduleSkill())
    # Persistent reminders — closing one from chat ("aldım") so the 5-minute
    # nag stops. The button on the reminder itself resolves without a turn.
    from app.skills.reminders import RemindersSkill
    await registry.register_skill(RemindersSkill(telegram_bots))
    await registry.register_skill(UseToolsetSkill())
    # Progressive tool disclosure — resolves a deferred tool's full schema on
    # demand. Must be registered (and never itself deferred), or the tools named
    # in the prompt's "Additional tools" index have no way to become callable.
    from app.skills.tool_search import ToolSearchSkill
    await registry.register_skill(ToolSearchSkill())
    # Kept in a local var (not thrown away like most Tier-1 skills) — its
    # action='test' needs engine refs that do not exist yet at this point in
    # startup, wired in later at the same spot the trigger reporters are.
    automations_skill = AutomationsSkill()
    await registry.register_skill(automations_skill)
    # OSINT / threat-intelligence suite (ip-api, AbuseIPDB, abuse.ch URLhaus/
    # ThreatFox/MalwareBazaar, HIBP Pwned Passwords, Ahmia dark-web search).
    # All read-only + network-gated (dropped in the Dead Zone).
    for _osint_skill in OSINT_SKILLS:
        await registry.register_skill(_osint_skill())

    # Tier 2 — MCP Servers
    from app.mcp.servers import register_all_mcp_servers

    await register_all_mcp_servers(registry)

    # Tier 3 — OSS Adapters
    from app.adapters.gpt_researcher import GptResearcherAdapter
    from app.adapters.shannon import ShannonAdapter

    await registry.register_adapter(GptResearcherAdapter())
    await registry.register_adapter(ShannonAdapter())

    # ── 4. Health checks — non-fatal (degraded = logged, not fatal) ────────────
    health = await registry.health_check_all()
    degraded = [name for name, ok in health.items() if not ok]
    if degraded:
        logger.warning("startup_adapters_degraded", extra={"degraded": degraded})
    logger.info(
        "startup_registry_ready",
        extra={"tools": len(registry.list_tools()), "degraded": degraded},
    )

    # ── 5. Recall cache ───────────────────────────────────────────────────────
    from app.skills.memory import MemoryRecallCache

    # One instance for the process (Rule 6).
    memory_cache = MemoryRecallCache()

    # ── 6. Session Manager ─────────────────────────────────────────────────────
    from app.core.session_manager import SessionManager

    session_manager = SessionManager()

    # ── 7. Orchestrator (reuses the client already injected into the registry) ─
    from app.core.orchestrator import AgentOrchestrator
    from app.services.welcome import WelcomeCache

    # One instance each for the process (Rule 6) — threaded into the
    # orchestrator/router instead of living as bare module globals.
    welcome_cache = WelcomeCache()
    orchestrator = AgentOrchestrator(registry, llm_client, profiles, memory_cache)

    # ── 7.5 Telegram channel — gateway + ingress ───────────────────────────────
    # The gateway turns an inbound update into a normal orchestrator run; it needs
    # the full engine, so it is built here (after the orchestrator exists) and
    # ingress is started per settings.telegram_mode (webhook sets the bot's
    # webhook; polling spawns a long-poll task; off = outbound-only).
    from app.telegram.gateway import TelegramGateway

    # The detached turn runner is created HERE, before the gateway and its
    # pollers start, so /break and steering can find an in-flight turn from the
    # first message. It is otherwise the same instance the rest of the app uses
    # via app.state.turns below.
    from app.core.turn_runner import TurnRegistry

    turns = TurnRegistry(session_manager)

    telegram_gateway = TelegramGateway(
        orchestrator=orchestrator,
        session_manager=session_manager,
        profiles=profiles,
        bots=telegram_bots,
        turns=turns,
    )
    telegram_poll_tasks = await telegram_bots.start(telegram_gateway)

    # ── 8. Inject into app.state ───────────────────────────────────────────────
    app.state.registry = registry
    app.state.orchestrator = orchestrator
    app.state.memory_cache = memory_cache
    app.state.welcome_cache = welcome_cache
    app.state.session_manager = session_manager
    app.state.profiles = profiles
    app.state.telegram_bots = telegram_bots
    app.state.telegram_gateway = telegram_gateway

    # ── 8.5 Detached turn runner (BgOps) ───────────────────────────────────────
    # Runs chat turns in their own asyncio tasks, decoupled from the HTTP request,
    # so a client disconnect can never lose a turn and a client can re-attach to
    # a live stream. One instance on app.state (Rule 6). Created above (before the
    # gateway) so /break and steering have it from the first message; published
    # here.
    app.state.turns = turns

    # A finished background job reports in on the agent that started it. Wired
    # HERE rather than at registration: the callback closes over the
    # orchestrator, the turn registry and the session manager, none of which
    # exist earlier in startup.
    reporter_deps = {
        "profiles": profiles,
        "orchestrator": orchestrator,
        "turns": app.state.turns,
        "session_manager": session_manager,
        "telegram_bots": telegram_bots,
    }
    # action='test' on manage_automations needs to start a real trigger turn,
    # and this is the first point in startup where everything it needs exists.
    automations_skill.wire(**reporter_deps)

    # ── 9. Child process — the local sandbox ──────────────────────────────────
    # Best-effort: a missing dependency logs a warning and Speda keeps running.
    # The sandbox gives the run_command skill a computer without Docker.
    from app.services.sandbox_launcher import SandboxLauncher

    sandbox_launcher = SandboxLauncher()
    await sandbox_launcher.start()
    app.state.sandbox_launcher = sandbox_launcher

    # ── 10. Recover post-turn work the previous process did not finish ────────
    # background_jobs left "running" at boot died with the last process. They
    # are retryable, so they go back on the queue and a detached drain works
    # through them while the app serves requests. See app/services/task_queue.py.
    from app.services.task_queue import recover_on_startup

    reclaimed_jobs = await recover_on_startup()

    logger.info(
        "startup_complete",
        extra={
            "tools_registered": len(registry.list_tools()),
            "api_key_set": settings.speda_api_key != "dev-key",
            "anthropic_key_set": settings.anthropic_api_key != "not-set",
            "jobs_reclaimed": reclaimed_jobs,
        },
    )

    # The event-loop stall watchdog. Started last and cheap by design: one
    # sleeping task whose only job is to notice when something else held the
    # loop long enough to cost every WebSocket its ping deadline.
    loop_watch = None
    if settings.loop_stall_threshold_s > 0:
        from app.services.loop_monitor import watch_event_loop

        loop_watch = asyncio.create_task(watch_event_loop(
            settings.loop_stall_check_interval_s, settings.loop_stall_threshold_s,
        ))

    yield

    # ── Shutdown ───────────────────────────────────────────────────────────────
    logger.info("shutdown_begin")
    if loop_watch is not None:
        loop_watch.cancel()
    await app.state.turns.shutdown()
    await sandbox_launcher.stop()
    for task in telegram_poll_tasks:
        task.cancel()
    await telegram_bots.aclose()
    await registry.shutdown_adapters()
    await close_db()
    logger.info("shutdown_complete")


def create_app() -> FastAPI:
    # Interactive docs and the OpenAPI schema expose the full API surface, so
    # they are DISABLED outside DEBUG. On an internet-facing server they must
    # never be public (CLAUDE.md / endpoint-leak hardening).
    docs_enabled = settings.debug
    app = FastAPI(
        title=f"Igor — {AGENT_NAME} Backend",
        description="Igor, the agent backend core — identity defined in prompts/core/01_identity.md",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )

    # ── CORS — locked down ──────────────────────────────────────────────────────
    # The API is header-authenticated (Bearer / X-API-Key), which browsers never
    # attach cross-origin automatically, so CSRF risk is low — but we still refuse
    # to advertise "*". Origins come from config; DEBUG additionally allows local
    # dev servers.
    #
    # The packaged desktop client IS a browser origin: the renderer is served
    # over the `app://bundle` custom scheme, registered `standard: true` in
    # packages/heartbreaker/src/main/index.ts precisely so it gets a real
    # (non-opaque) origin. That means its fetches are ordinary cross-origin
    # requests and are preflighted, so `app://bundle` must be allowed here or the
    # desktop app cannot talk to the server at all.
    from fastapi.middleware.cors import CORSMiddleware

    DESKTOP_ORIGIN = "app://bundle"
    origins = [o.strip() for o in settings.cors_allowed_origins.split(",") if o.strip()]
    if DESKTOP_ORIGIN not in origins:
        origins.append(DESKTOP_ORIGIN)

    LOCAL_ORIGIN_RE = re.compile(r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$")
    allow_origin_regex = LOCAL_ORIGIN_RE.pattern if settings.debug else None

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_origin_regex=allow_origin_regex,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-API-Key", "X-N8N-Secret"],
    )

    # ── Global exception handler — never leak internals ─────────────────────────
    # Any unhandled exception is logged in full server-side and returned to the
    # caller as a generic 500. Prevents stack traces / paths / SQL from leaking
    # through endpoints. HTTPExceptions keep their intended status/detail.
    #
    # It carries the CORS header itself, which CORSMiddleware cannot do for it:
    # Starlette runs the error handler in ServerErrorMiddleware, OUTSIDE the whole
    # middleware stack, so a 500 leaves without Access-Control-Allow-Origin and a
    # browser client discards it unread — the desktop app then reports a genuine
    # server error as "couldn't reach the backend", which sends every diagnosis
    # after the wrong thing. A 500 must arrive as a 500.
    from fastapi.responses import JSONResponse as _JSONResponse

    def _cors_headers(request) -> dict[str, str]:  # noqa: ANN001
        origin = request.headers.get("origin")
        if not origin:
            return {}
        if origin in origins or (allow_origin_regex and LOCAL_ORIGIN_RE.match(origin)):
            return {"Access-Control-Allow-Origin": origin, "Vary": "Origin"}
        return {}

    @app.exception_handler(Exception)
    async def _unhandled(request, exc):  # noqa: ANN001
        logger.error(
            "unhandled_exception",
            extra={"path": request.url.path, "error": str(exc)},
            exc_info=exc,
        )
        return _JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
            headers=_cors_headers(request),
        )

    # Middleware (Starlette applies these in REVERSE registration order, so the
    # LAST added runs FIRST: security headers wrap everything, then auth gates
    # before any router logic).
    from app.middleware.auth import AuthMiddleware
    from app.middleware.security import SecurityHeadersMiddleware

    app.add_middleware(AuthMiddleware)
    app.add_middleware(SecurityHeadersMiddleware)

    # Routers
    from app.routers import (
        academic, admin, agents, aircraft, automations, browser as browser_router,
        chat, config as config_router, connections, files, health, import_chats,
        mail, media, memory, navigation, news, outlook, reminders, telegram,
        trigger, voice, web_watch,
    )

    app.include_router(health.router)
    app.include_router(chat.router)
    app.include_router(trigger.router)
    app.include_router(agents.router)
    app.include_router(admin.router)
    app.include_router(import_chats.router)
    app.include_router(files.router)
    app.include_router(media.router)
    app.include_router(connections.router)
    # Web portals live under /connections/portals — same family as the OAuth
    # connections above, different enough to keep in its own module.
    app.include_router(browser_router.router)
    app.include_router(automations.router)
    app.include_router(memory.router)
    app.include_router(telegram.router)
    app.include_router(news.router)
    app.include_router(academic.router)
    app.include_router(mail.router)
    app.include_router(outlook.router)
    app.include_router(web_watch.router)
    app.include_router(reminders.router)
    app.include_router(navigation.router)
    app.include_router(aircraft.router)
    app.include_router(voice.router)
    app.include_router(config_router.router)

    return app


app = create_app()
