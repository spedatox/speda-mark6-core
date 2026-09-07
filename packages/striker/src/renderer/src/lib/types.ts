// SPDX-FileCopyrightText: 2026 Ahmet Erol Bayrak
// SPDX-License-Identifier: AGPL-3.0-or-later

export type Role = 'user' | 'assistant'

export interface ToolBadge {
  id: string
  name: string
  input?: unknown    // arguments the model passed (what it searched/added/ran)
  result?: string    // truncated tool output
  // How many characters of `content` had streamed when this tool fired — lets
  // the renderer interleave it at the point it actually happened instead of
  // always stacking every tool before the text. Undefined (older stored
  // messages, pre-dating this field) is treated as 0 — i.e. before all text,
  // reproducing the old stacked-on-top behavior with zero data migration.
  afterChars?: number
}

export interface ImageBlock {
  media_type: string
  data: string   // base64, no data: prefix
}

/** A non-image file upload (PDF, DOCX, XLSX, CSV, TXT, code, …). The backend
 *  extracts its text server-side; no client-side parsing. */
export interface DocBlock {
  name: string
  media_type: string
  data: string   // base64, no data: prefix
  size: number
}

/** Display chip for a file the user uploaded (not downloadable — just a marker). */
export interface UploadedFile {
  name: string
  size: number
}

export interface FileMeta {
  name: string
  title: string
  kind: string   // "PDF", "Word", "Image", …
  size: number
  url: string    // e.g. /files/report.pdf
}

/** Provenance for a turn the owner did not write — an n8n automation opening
 *  a session. Present only on such turns; the bubble is attributed to the
 *  sender instead of to the owner. */
export interface TriggerMeta {
  source: string        // "n8n"
  label: string         // human name of the sender ("Morning brief")
  job?: string          // the automation's job
  automation?: string
  from_agent?: string
  output_mode?: string  // "push" | "silent"
}

export interface ChatMessage {
  id: string
  role: Role
  content: string
  tools: ToolBadge[]
  isStreaming: boolean
  isError: boolean
  errorNote?: string  // error banner text — kept SEPARATE from content so an
                      // error (network drop, host restart) never erases what
                      // already streamed
  /** The turn died before the backend acknowledged it (no `start` event), so the
   *  user message it belongs to was never persisted server-side. Retrying such a
   *  turn has to RESEND that message, not regenerate on a history that never
   *  received it — see handleRegenerate in ChatMain. */
  unsent?: boolean
  images?: string[]   // data: URLs for display in the user bubble
  files?: FileMeta[]  // downloadable files Speda produced
  uploads?: UploadedFile[]  // non-image files the user attached (display chips)
  trigger?: TriggerMeta     // set when an automation, not the owner, sent this turn
  status?: string     // live status line while streaming (real phase, not looped filler)
  sessionId?: number  // which session a STREAMING bubble belongs to — lets
                      // SELECT_SESSION preserve an in-flight tail instead of
                      // wiping it in the history-load race
}

export interface Session {
  id: number
  title: string | null
  started_at: string
  /** Running token spend for this session, across every provider. Absent on
   *  responses from a backend older than the counter. */
  tokens_in?: number
  tokens_out?: number
}

export interface AppConfig {
  apiBase: string
  apiKey: string
  /** Backend agent this build targets — chat goes to /chat/{agentId} and the
   *  session list is scoped to it. Set from the active brand (profile). */
  agentId: string
}

export interface ModelInfo {
  id: string
  name: string
  description: string
  tags?: string[]
  provider?: string // 'anthropic' | 'openai' | 'gemini' | 'zai' | 'deepseek' | 'ollama' — absent on old backends
}

/** One question in a mid-turn interaction from a peer. */
export interface InteractionQuestion {
  question: string
  header?: string
  multiSelect?: boolean
  options?: { label: string; description?: string }[]
}

export interface QuestionRequest {
  questions?: InteractionQuestion[]
}

export interface SSEEvent {
  // The frames the full build also carries (subagent, permission_request,
  // house_party_auth, lockdown_auth, skyfall_arm) are deliberately absent: Core
  // has no roster, no peers and no deployment protocols, so the backend never
  // emits them and nothing here would handle them.
  type: 'start' | 'chunk' | 'tool' | 'tool_result' | 'file' | 'done' | 'error'
  data: unknown
  session_id: number
  request_id: string
}
