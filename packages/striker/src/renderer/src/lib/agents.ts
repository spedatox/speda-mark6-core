// SPDX-FileCopyrightText: 2026 Ahmet Erol Bayrak
// SPDX-License-Identifier: AGPL-3.0-or-later

/** Agent identity bits — the colour mirrors the backend profile's DocTheme
 *  accent (app/profiles/speda.py). Core has one agent, so this has one entry;
 *  the map shape stays because agentColor() is called with an id. */

export const AGENT_COLORS: Record<string, string> = {
  speda: '#36abca',
}

export function agentColor(id: string): string {
  return AGENT_COLORS[id] ?? 'var(--hb-icon-bright)'
}

export function monogram(id: string): string {
  return id.slice(0, 2).toUpperCase()
}
