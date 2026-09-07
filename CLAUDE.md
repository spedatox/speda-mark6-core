# Working agreement for this repo

This file is rules for how to work here, not architecture documentation. For that, read [README.md](README.md) for the system overview, and the relevant package doc before touching that package's code:

| Package | Doc |
|---|---|
| `packages/igor` | [IGOR.md](packages/igor/IGOR.md) |
| `packages/striker` | [CORE.md](packages/striker/CORE.md) |
| `packages/browser` | [README.md](packages/browser/README.md) |

## What this repo is, and is not

This is **SPEDA Mark VI Core**: one agent (Speda), one backend, one desktop client. It was forked by hand from the full build, [spedatox/speda-mark6](https://github.com/spedatox/speda-mark6), and stripped — the multi-agent engine, the Legion, House Party, the external-peer bridge, Hisar and the named deployment protocols (Skyfall, Octavius, Doormat, Lockdown, Lifeboat) are **deleted**, not flagged off.

That has a consequence worth stating plainly, because it is the mistake this repo invites: **do not re-add a multi-agent feature here.** If a change needs a roster, a dispatch, a worker corps or a peer, it belongs in the full build. What belongs here is anything a single agent can do on its own.

The sync is automated up to the point where judgement starts, and no further.
Every push to the full build's `main` runs its `sync-to-core` workflow, which
replays the new commits onto a branch here, strips the paths listed in
[`.github/sync-exclude`](.github/sync-exclude), and opens a **pull request**. It
never pushes to `main` and never merges.

That gate is the whole design. The strip is mechanical — it can remove
`packages/heartbreaker`, it cannot tell you whether a change to the shared chat
surface still means anything in a build with one agent. So read the carry PR for
exactly that: anything assuming a roster, a dispatch, a worker corps or a peer
belongs in the full build, not here. Close the PR rather than merging it if the
answer is no; `.github/sync-state` will have moved past those commits either way.

Two files drive it, and both live here because Core owns the definition of what
Core excludes:

| File | What it is |
|---|---|
| [`.github/sync-exclude`](.github/sync-exclude) | The strip list. If you delete the same file out of every carry PR by hand, put it here. |
| [`.github/sync-state`](.github/sync-state) | How far the carry has reached. Move it by hand to skip a commit or to re-carry one. |

A commit that conflicts stops the replay: the PR carries everything before it and
names the one that needs hand-carrying. That commit is still a deliberate act of
work — the automation just stops pretending otherwise.

The direction is one-way, full build → Core, because that is where the shared
chat surface is authored. Nothing carries back.

If any doc disagrees with the code, the code is right and the doc is wrong — fix the doc as part of whatever change you're making, don't leave it for later.

---

## Standing rules

**No hardcoded values.** Maximum configurability is the goal. If a value could plausibly need to change without a code change — a threshold, a limit, a model id, a timeout, a feature flag — it's a setting, not a literal. And it's not done halfway: wire it into the backend config schema *and* into the client's settings surface. A setting that only exists in `config.py` with no UI path to it isn't finished.

**Fix what you see.** If you notice an error while working — even one unrelated to the task — fix it, after the assigned task is done. Don't let it derail the task in progress, and don't leave it noticed-but-untouched either.

**Ship it.** Commit and push completed work without asking for confirmation first — that includes incidental fixes from the rule above. This does not extend to force-push or rewriting history; those still get flagged before they happen, every time.

**No co-author trailer.** Never add `Co-Authored-By: Claude ...` to a commit in this repo. This is his authorship record. Write the subject line and a prose body explaining the reasoning, and stop there.

---

## Licensing

AGPL-3.0-or-later. Every source file carries an SPDX header (`SPDX-FileCopyrightText` / `SPDX-License-Identifier`) — new files need one too.
