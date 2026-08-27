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

export interface AgentTransport {
  run(
    request: AgentRequest,
    ctx: AgentContext,
    signal: AbortSignal,
  ): AsyncGenerator<StreamChunk>;
}

/** in-process transport: the orchestrator IS the backend */
export const localTransport: AgentTransport = {
  run: (request, ctx, signal) => runAgent(request, ctx, signal),
};

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
