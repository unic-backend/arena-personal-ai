/* ─────────────────────────────────────────────────────────────
   Transport layer — the contract between backend and UI.

   Today the backend runs in-process (localTransport). Swap this
   for an SSE/WebSocket implementation later without touching a
   single component:

     Agent Request → Orchestrator → Tools → Activity Events
       → Transport → Timeline → Streamed Response
   ───────────────────────────────────────────────────────────── */

import type { StreamChunk } from './types';
import { runAgent, AgentContext, AgentRequest } from '../agent/orchestrator';
import { makeRemoteTransport, RemoteConfig } from './remoteTransport';
import { useBackend } from '../store/backendStore';

export interface AgentTransport {
  run(
    request: AgentRequest,
    ctx: AgentContext,
    signal: AbortSignal,
  ): AsyncGenerator<StreamChunk>;
}

/**
 * On-device transport. **Reserved for what genuinely runs on the phone** —
 * today, video editing. It is no longer the chat's fallback: see
 * `offlineTransport` below for why.
 */
export const localTransport: AgentTransport = {
  run: (request, ctx, signal) => runAgent(request, ctx, signal),
};

/**
 * What answers when the owner's server does not.
 *
 * **Measured on 03/09/2026, on his phone.** He typed « Bonjour ». His backend
 * was disconnected, so the chat silently fell back to `localTransport` and an
 * in-browser demo answered him — signed *Usman*, offering « exécution
 * terminal réelle » and « une vraie arborescence projet ». Both were false:
 * that demo works on an invented project named *pulseboard* held in
 * localStorage. Nothing on screen distinguished it from his real AI.
 *
 * A platform that cannot do something says so. It does not produce a
 * plausible answer instead — that rule is the whole repository's, and this is
 * where it was being broken in the one place he actually reads.
 *
 * So: no answer at all, and the reason. An empty screen he understands beats
 * a full one he cannot trust.
 */
export const offlineTransport: AgentTransport = {
  // eslint-disable-next-line require-yield
  async *run() {
    // Dire **pourquoi**, pas seulement quoi faire. « Rebranche-le dans le
    // panneau » envoie chercher une panne sans dire laquelle : le
    // 03/09/2026 a 02:19, le proprietaire est revenu avec le meme ecran,
    // parce que la phrase ne distinguait pas « aucun serveur enregistre »
    // de « le serveur ne repond pas », et ne portait pas l'erreur mesuree.
    const { url, error } = useBackend.getState();
    if (!url.trim()) throw new Error('BACKEND_ABSENT');
    throw new Error(error ? `BACKEND_OFFLINE::${error}` : 'BACKEND_OFFLINE');
  },
};

/**
 * The single decision point. `surAppareil` is true only for work that really
 * runs here (video). Everything else needs the server, or says it cannot.
 *
 * Three call sites used to spell this out themselves, and each could drift.
 */
export function choisirTransport(
  remote: RemoteConfig | null,
  surAppareil = false,
): AgentTransport {
  if (surAppareil) return localTransport;
  if (remote) return makeRemoteTransport(remote);
  return offlineTransport;
}

/**
 * Drop-in replacement once a network backend exists:
 *
 * export const sseTransport: AgentTransport = {
 *   async *run(request, _ctx, signal) {
 *     const res = await fetch('/api/agent/stream', { method: 'POST', body: JSON.stringify(request), signal });
 *     for await (const chunk of parseSSE(res.body)) yield chunk as StreamChunk;
 *   },
 * };
 */
