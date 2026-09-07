# S.P.E.D.A. Mark VI Core

**S**pecialized · **P**ersonal · **E**xecutive · **D**igital · **A**ssistant

A self-hosted, single-owner AI assistant. One agent, one backend process, one desktop client — the whole platform reduced to the part that answers.

It keeps persistent memory across sessions, runs scheduled and event-driven work without anyone present, and acts on the owner's own accounts through their own connected services. Anything with a real-world consequence goes through the owner, not around them.

This is the **Core** build. The full Mark VI — eight agents, a research swarm, an all-hands mode, a mobile client, two smartwatch clients and a set of named deployment protocols — lives in [spedatox/speda-mark6](https://github.com/spedatox/speda-mark6). Core is not that build with features switched off; it is a hand-stripped fork with the multi-agent engine removed.

---

## Contents

- [Architecture](#architecture)
- [Capabilities](#capabilities)
- [Integrations](#integrations)
- [What Core deliberately excludes](#what-core-deliberately-excludes)
- [Tech stack](#tech-stack)
- [Repository layout](#repository-layout)
- [Deployment](#deployment)
- [License](#license)

---

## Architecture

Everything runs through one FastAPI process (`packages/igor`). The agent, the memory system, the tool registry and the background job queue share that process, one database, and one event loop.

A single API key authenticates every request, over an HTTP/SSE endpoint for interactive chat. A third-party workflow engine (n8n) owns all scheduling — the backend itself never runs a clock; it exposes trigger and probe endpoints that n8n calls on a timer.

Tool capabilities are organized in tiers, all exposed to the model through one registry:

| Tier | What it is |
|---|---|
| Skills | In-process Python capabilities — the bulk of what's listed below |
| MCP servers | Third-party integrations reached over the Model Context Protocol |
| Adapters & sidecars | Full external applications wrapped over HTTP, running in their own containers |

A turn runs **detached** from the HTTP request that started it, so a dropped connection is a reconnect rather than a lost answer: the client mints the turn id, re-attaches to the live stream, and the event buffer replays.

---

## Capabilities

### Memory, recall & knowledge management

- A durable, schema-enforced memory store: topic-organized documents (who the owner is, ongoing projects, people, running history) that the agent reads and rewrites over time, not a chat log.
- Shape-aware writers that append to the correct ledger period, create or update a person's or project's own file, or revise one chapter of a biography — without corrupting neighboring entries.
- A sourced, addressable layer of individual facts beneath the memory documents, each traceable to its evidence, ranked by relevance and reinforcement, and softly demoted when it turns out wrong.
- Exact keyword and date search across the full raw conversation history.
- Meaning-based (hybrid vector + keyword) recall across every past conversation.
- Pattern detection: a fact or behavior observed enough times graduates into a recorded pattern the agent checks *before* planning or promising anything.

### Communication & automation

- Push messages, files, and generated documents to the owner's Telegram, from the agent's own bot — and hold a full conversation there.
- Device push notifications.
- Persistent, self-repeating reminders that keep re-asking until answered, with a history of what was taken or missed.
- Full control over recurring briefings, reminders, and proactive watchers — page-change hooks, keyword hooks, inbound-mail hooks, RSS watches, webhooks — backed by an n8n workflow engine.
- On-demand loading of additional integrations and skills, so the active prompt only carries what a given task needs.

### Files, storage & documents

- Generate downloadable PPTX, DOCX, and PDF files from Markdown, branded and signed.
- Write arbitrary generated text or code to a real downloadable file.
- Pull files produced inside the code sandbox out to the user as a download.

### Code execution & web automation

- Run shell commands in an isolated Linux sandbox with a persistent workspace — Python, pip, git, and data tooling available for real computation, not just text generation.
- Render JavaScript-heavy or blocked pages, drive multi-step browser interactions (click, fill, upload, download, tabs, dialogs), and sign into the owner's own saved web portals without the password ever passing through the model.

### Research, news & OSINT

- Two-tier news system: a free, always-on RSS store with keyword watchlists that flag and push breaking terms, a quota-budgeted deep-analyst tier for cross-outlet corroboration, and full-text article extraction.
- A dozen read-only OSINT and threat-intelligence lookups for authorized security research: IP geolocation and reputation, malicious-URL and malware-IOC feeds, breached-password checking (k-anonymity, password never transmitted), dark-web and leak-metadata search, internet-wide device exposure, domain-based email discovery, and cryptocurrency wallet tracing.

### Health & academic

- Query synced biometrics — steps, sleep stages, heart rate, exercise sessions, body composition — with trend comparisons and a freshness gate that refuses to answer present-tense questions with stale data.
- Read the owner's class attendance ledger and report remaining absence budget per course against the official attendance rule; push a one-tap "did you attend?" prompt to a registered watch.

### Navigation, transit & weather

- Live-traffic-aware turn-by-turn directions across drive, walk, transit, and bike modes, with congestion breakdown and an interactive map card.
- Nearby place search and on-duty pharmacy lookup, rendered as tappable map markers.
- Live flight tracking by tail number, flight number, or callsign.
- Live city-bus arrival board for a given stop.
- Current conditions and multi-day forecast for any named place or the owner's home location.

### Voice

- Transcribe uploaded audio to text.
- Convert text to a downloadable spoken response in the agent's own neural voice.
- Spoken turns are a **presentation brief**, not "the reply read aloud": the agent narrates while the client's canvas carries the evidence — a figure as a stat tile, a source as a cutting, a person as a file — each placed at the point the narration reaches it.

---

## Integrations

Reached over the Model Context Protocol, each optional and skipped at startup if unconfigured:

- **Notion** — read, search, create, and edit pages and databases.
- **Google Workspace** — Gmail, Calendar, Tasks, Drive, and Contacts.
- **Microsoft Graph** — Outlook mail.
- **Brave Search, Tavily, Exa** — general and research-grade web search.
- **Fetch** — turns a URL into readable Markdown.
- **GitHub** — repository, issue, and code operations.
- **Alpha Vantage** — financial market data.
- **arXiv** — academic paper search.
- **CVE intelligence** — security vulnerability lookups.
- **Filesystem** — read/write scoped to the assistant's own output directory.
- **Playwright MCP** — full browser automation for the open public web, in its own container, never used for the owner's saved logins.
- Owners can register their own custom MCP servers by command or URL.

**Adapters & sidecars** — full external applications, each isolated in its own container:

- **Deep research** — a wrapped open-source research engine for comprehensive, multi-source reports.
- **Security analysis** — a wrapped security toolkit for vulnerability scans, CVE lookups, and network reconnaissance against a named target.
- **Sandbox** — a no-secrets container that executes arbitrary shell commands with a hard timeout.
- **Browser** — the assistant's eyes on the web: renders pages, returns readable text and an accessibility snapshot of what's clickable, and holds the owner's portal sessions in a persisted per-profile cookie jar so a password never becomes text the model produces.

---

## What Core deliberately excludes

Absences, not stubs. The code is gone from both the backend and the client:

| Excluded | Lives in |
|---|---|
| The eight-agent roster, per-agent Telegram bots, inter-agent dispatch and the shared agent channel | the full build |
| **Legion** — the parallel research worker swarm (the `Task` tool) | the full build |
| **House Party** — the all-hands mode and its war-room command channel | the full build |
| The external-peer WebSocket bridge, and with it **Forge** routing and peer permission asks | the full build |
| **Hisar** — the owner's self-hosted cloud vault, and the `hisar` skill | its own repo, reachable only from the full build |
| **Skyfall, Octavius, Doormat, Lockdown, Lifeboat** — the named deployment and safety protocols, and the host-ops SSH bridge they rely on | the full build |
| Heartbreaker (desktop deck), Speda GO (Android), Ultron Wear and Atomix Wear | their own repos |

Memory-document ownership is the one place the strip is visible in behavior rather than absence: the full build refuses a write to a domain another agent owns. Core has one agent, so it owns every document and that gate is gone. The domain folders (`finance/`, `wellness/`, `academic/`, `cybersec/`, `ops/`) and their enforced shapes remain.

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python 3.11+, FastAPI, uvicorn, SQLAlchemy (async) |
| Database | SQLite (production), Postgres-compatible |
| LLM / AI | Anthropic SDK, OpenAI SDK, Model Context Protocol |
| Embeddings & search | OpenAI embeddings, brute-force vector search + full-text keyword search, fused |
| Background work | Database-backed job queue with durable drain; n8n for all scheduling |
| Desktop | Electron, React, TypeScript, electron-vite |
| Browser automation | Playwright (owner-login sidecar) and the official Playwright MCP server (open web), each containerized separately |
| Code execution | Isolated Python/shell sandbox container |
| Infrastructure | Docker Compose, Caddy (reverse proxy, automatic HTTPS), n8n |

---

## Repository layout

| Package | Description |
|---|---|
| `packages/igor` | The backend — the agent, the memory system, the tool registry, the orchestrator |
| `packages/striker` | The desktop client, shipped as SPEDA Mark VI Core |
| `packages/browser` | Playwright sidecar for rendering pages and the owner's portal logins |
| `packages/playwright-mcp` | Official Playwright MCP server, open web only |
| `packages/sandbox` | Isolated code-execution sidecar |

---

## Deployment

The stack runs as a set of Docker Compose services on one internal network — the backend, n8n, the sandbox, the browser sidecar, and Playwright MCP — with only the backend and an optional Caddy reverse proxy exposed. `./deploy.sh` builds and starts the whole stack; set `DOMAIN` in `packages/igor/.env` to also bring up Caddy with automatic HTTPS.

---

## License

AGPL-3.0. See [LICENSE](LICENSE). Running a modified version of this software as a network service requires making that modified source available to its users under the same license.
