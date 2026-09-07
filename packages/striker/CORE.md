# Striker

The client. `Striker` is the codename; what it ships as is **SPEDA Mark VI Core** — a single-agent Electron desktop app over the Igor backend in this same repo. No roster, no switcher, no war room, no House Party, no comms tray.

---

## Contents

- [What it is](#what-it-is)
- [Directory structure](#directory-structure)
- [Dev workflow](#dev-workflow)
- [Profile system](#profile-system)
- [Projects](#projects)
- [Screen lock](#screen-lock)
- [Surviving a dropped connection](#surviving-a-dropped-connection)
- [What Core does not have](#what-core-does-not-have)
- [Configuration](#configuration)

---

## What it is

Striker was produced by manually copying Heartbreaker's source tree — the full Mark VI deck, which lives in [spedatox/speda-mark6](https://github.com/spedatox/speda-mark6) — and stripping it down. There is no scripted fork process, and there isn't going to be one. Don't go looking for fork tooling; it doesn't exist.

The two builds share the chat-surface components by convention, not by a package: a change made to one is hand-carried to the other. `theme/striker.css` ends with a parity layer that answers the deck's `--r-*` radius scale with rounded values, so the same component tree renders sharp there and soft here without an `if (core)` anywhere in a `.tsx` file.

---

## Directory structure

Same `electron-vite` layout as Heartbreaker (`main/`, `preload/`, `renderer/src/{components,lib,profile,store,theme}`), no `teaser/` build. `profile/` carries three files — `index.ts`, `theme.ts`, `types.ts` — and `index.ts` hardcodes the single profile rather than selecting from a roster.

---

## Dev workflow

```bash
# from packages/striker
npm run dev
npm run build
npm run typecheck    # single tsconfig, unlike Heartbreaker's split node/web configs
npm run web:dev
npm run dist          # electron-vite build + electron-builder --win
```

From the repo root: `npm run striker:dev`, `:build`, `:typecheck`, `:web:dev`, `:web:build`, `:dist`. Baking a server URL and key into a packaged build means setting `MAIN_VITE_SPEDA_API_BASE` / `MAIN_VITE_SPEDA_API_KEY` before running `dist`.

---

## Profile system

`profile/index.ts` hardcodes a single `AppProfile` — Speda, with its accent color and product name — directly in the file, with no environment-variable selection. There is no roster and no switcher by design, and no `brands.ts` map to select from.

---

## Projects

A project is a named workspace owning its own chats, standing instructions and
knowledge base. `ProjectsView` is both halves — the card grid and one project's
detail pane — and it REPLACES the chat column rather than floating over it
(`Layout` holds `projectsAt`), because it is a place you go, not a dialog you
dismiss; the sidebar stays put so the conversation list is still one click away.

Three things worth knowing before touching this:

- **New chat from the sidebar is always a LOOSE chat**, even while a project is
  open. `NEW_CHAT` takes an explicit `projectId` and treats its absence as "no
  project", never as "keep the current one" — inheriting it there is how a
  workspace's standing instructions end up on an unrelated conversation.
- **A chat's project is fixed at birth.** `streamChat` sends `projectId` on every
  turn and the backend reads it only on the one that creates the session, so
  there is no client-side "move this chat" path and there should not be one.
- **Project chats stay in the main history list**, badged with a folder glyph
  rather than hidden. Hiding them is how you lose a conversation.

Core has no roster, so a project with no colour of its own falls back to the one
theme accent (`ACCENT` at the top of the file) rather than to a per-agent profile.
That is the only intentional divergence from the full build's copy of this
component; everything else is the same file. The backend contracts live in
[IGOR.md](../igor/IGOR.md#projects).

---

## Screen lock

`LockScreen` + `LockScreensaver`, driven by `lib/useScreenLock.ts` and configured under Settings → Interface. `Ctrl+L` locks, the lock can be raised on launch, and an idle stretch raises it by itself; the passcode lives as a SHA-256 in `localStorage`. The screensaver parades agent cards — Core has one agent, so it is a parade of one.

---

## Surviving a dropped connection

A turn runs **detached** on the backend (`app/core/turn_runner.py`) — the HTTP response is only a subscriber, and dropping it never cancels the run. So a dropped socket is a reconnect, not a failed answer. The client mints the turn's `request_id` itself and sends it in the `POST /chat/{agent}` body (so the turn is recoverable from the instant Send is pressed, before any `start` event has arrived), re-attaches on `GET /chat/attach/{request_id}` when the stream drops, and checks `GET /chat/active` before ever telling the owner the backend is unreachable. Attach replays the whole event buffer, so a reconnect rewinds the bubble and lets the replay rebuild it.

Reconnect count and give-up timeout are owner settings, not constants.

---

## What Core does not have

These are absences, not stubs — the code is gone, and the backend in this repo does not serve the endpoints either. Listed because someone reading Heartbreaker's tree alongside this one will look for them:

| Missing | Why |
|---|---|
| Roster strip, agent switcher, `profile/brands.ts` | One agent |
| War room, House Party authorization window, `hbPartyCycle` colour parade | No all-hands mode to stage |
| Comms tray, `CommBubble`, `/agents/comms` | No inter-agent traffic to show |
| Subagent panel, the `subagent` SSE frame | No Legion, no delegating peer |
| `PermissionPrompt`, the `permission_request` SSE frame, `/agents/asks` | No external peer with a safety gate to relay |
| Forge link indicator, the workspace `cwd` setting, `useOnlineAgents` | No peer to link to |
| Protocols tab (Skyfall / Octavius / Doormat / Lockdown / Lifeboat) | Those protocols aren't in the Core backend |
| Legion worker model matrix, `ROSTER CORES` window | One agent, one model pin — it lives on the Systems board |

The i18n dictionaries (`lib/i18n/{en,tr}.ts`) carry only the eleven groups the surviving components actually read. A key with no call site is a compile error waiting to happen at the next rename, so they get deleted rather than kept "in case".

---

## Configuration

There's no `connection.json` persistence and no in-app way to change the server URL or key after packaging. `App.tsx` resolves the connection once at boot — from `window.api.getConfig()` on Electron, or `VITE_API_BASE` / `VITE_API_KEY` with a local fallback on the web build — and that's final for the session. Same `X-API-Key` auth scheme as the backend expects on every route.
