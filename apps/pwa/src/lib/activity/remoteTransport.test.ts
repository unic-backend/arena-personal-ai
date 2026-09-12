/* ─────────────────────────────────────────────────────────────
   Continuite de conversation : `conversation_id` part bien dans le corps
   de `/agent/stream`, distinct du `run_id` genere a chaque appel.

   Audit externe (commit f7f0478) : l'interface n'envoyait qu'un `run_id`
   NEUF a chaque message, et le serveur l'utilisait comme session memoire —
   chaque message ouvrait donc une session vierge. Corrige le 12/09/2026 des
   deux cotes (voir apps/backend/routers/pwa_gateway.py). Ce test EXECUTE le
   transport et lit le vrai corps envoye, plutot que de relire le source.
   ───────────────────────────────────────────────────────────── */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { makeRemoteTransport } from './remoteTransport';

async function collecter(gen: AsyncGenerator<unknown>) {
  const morceaux: unknown[] = [];
  for await (const morceau of gen) morceaux.push(morceau);
  return morceaux;
}

function reponseSSE(trames: string[]) {
  const corps = trames.join('');
  return new Response(corps, {
    status: 200,
    headers: { 'Content-Type': 'text/event-stream' },
  });
}

describe('makeRemoteTransport — identite de conversation', () => {
  let appels: Array<{ url: string; body: Record<string, unknown> }>;

  beforeEach(() => {
    appels = [];
    vi.stubGlobal('fetch', vi.fn(async (url: string, init: RequestInit) => {
      appels.push({ url, body: JSON.parse(String(init.body)) });
      return reponseSSE(['data: {"type":"done","meta":{}}\n\n']);
    }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('envoie le conversation_id fourni, distinct du run_id', async () => {
    const transport = makeRemoteTransport({ url: 'https://exemple.test' });
    await collecter(transport.run(
      { text: 'Bonjour', conversationId: 'conv-abc' } as never,
      {} as never,
      new AbortController().signal,
    ));

    expect(appels).toHaveLength(1);
    const { body } = appels[0];
    expect(body.conversation_id).toBe('conv-abc');
    expect(typeof body.run_id).toBe('string');
    expect(body.run_id).not.toBe('conv-abc');
  });

  it('sans conversation_id (ancien client), le champ est absent — le serveur retombe sur run_id', async () => {
    const transport = makeRemoteTransport({ url: 'https://exemple.test' });
    await collecter(transport.run(
      { text: 'Bonjour' } as never,
      {} as never,
      new AbortController().signal,
    ));

    expect(appels[0].body.conversation_id).toBeUndefined();
  });

  it('deux messages de la MEME conversation envoient le meme conversation_id, avec des run_id differents', async () => {
    const transport = makeRemoteTransport({ url: 'https://exemple.test' });
    await collecter(transport.run(
      { text: 'Premier message', conversationId: 'conv-xyz' } as never,
      {} as never, new AbortController().signal,
    ));
    await collecter(transport.run(
      { text: 'Deuxieme message', conversationId: 'conv-xyz' } as never,
      {} as never, new AbortController().signal,
    ));

    expect(appels).toHaveLength(2);
    expect(appels[0].body.conversation_id).toBe('conv-xyz');
    expect(appels[1].body.conversation_id).toBe('conv-xyz');
    expect(appels[0].body.run_id).not.toBe(appels[1].body.run_id);
  });
});
