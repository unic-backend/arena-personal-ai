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

/* ─────────────────────────────────────────────────────────────
   L'etat metier de /files (readable/status), pas seulement le code HTTP.

   Audit externe (commit f7f0478) : `/files` rend TOUJOURS un objet avec un
   code 200, meme pour un fichier refuse (ECHEC/NON_PRIS_EN_CHARGE — un
   fichier audio joint, par exemple, qu'aucun lecteur ne sait extraire).
   Avant ce correctif, l'activite de cette piece etait quand meme marquee
   « completed » avec « Fichier reçu et inspecté » — l'interface annoncait
   une reussite pour un fichier jamais lu.
   ───────────────────────────────────────────────────────────── */
function fauxAttachment(kind: 'audio' | 'document' = 'audio') {
  return {
    id: `att-${kind}`,
    name: kind === 'audio' ? 'memo.mp3' : 'devis.pdf',
    size: 1234,
    type: kind === 'audio' ? 'audio/mpeg' : 'application/pdf',
    kind,
    file: new File(['x'], kind === 'audio' ? 'memo.mp3' : 'devis.pdf'),
    url: '',
    status: 'ready' as const,
  };
}

describe('makeRemoteTransport — statut metier des pieces jointes', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('un fichier refuse (readable=false) devient une activite "failed", jamais "completed"', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.endsWith('/files')) {
        return new Response(JSON.stringify({
          id: 'p1', name: 'memo.mp3', size: 1234, status: 'NON_PRIS_EN_CHARGE',
          readable: false, reason: 'format audio non pris en charge par /files',
          nature: 'document', truncated: false, characters: 0,
        }), { status: 200 });
      }
      return new Response('data: {"type":"done","meta":{}}\n\n', { status: 200 });
    }));

    const transport = makeRemoteTransport({ url: 'https://exemple.test' });
    const evenements = await collecter(transport.run(
      { text: 'voici un memo vocal', attachments: [fauxAttachment('audio')] } as never,
      {} as never,
      new AbortController().signal,
    ));

    const activites = evenements
      .filter((e): e is { type: 'activity'; event: import('./types').ActivityEvent } =>
        (e as { type: string }).type === 'activity')
      .map((e) => e.event);
    const pieceAudio = activites.filter((e) => e.tool === 'file_uploader').pop();
    expect(pieceAudio?.status).toBe('failed');
    expect(pieceAudio?.description).toContain('format audio non pris en charge');
  });

  it('un fichier reellement lu (readable=true) reste "completed"', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (url.endsWith('/files')) {
        return new Response(JSON.stringify({
          id: 'p2', name: 'devis.pdf', size: 1234, status: 'LU', readable: true,
          nature: 'document', truncated: false, characters: 42,
        }), { status: 200 });
      }
      return new Response('data: {"type":"done","meta":{}}\n\n', { status: 200 });
    }));

    const transport = makeRemoteTransport({ url: 'https://exemple.test' });
    const evenements = await collecter(transport.run(
      { text: 'voici mon devis', attachments: [fauxAttachment('document')] } as never,
      {} as never,
      new AbortController().signal,
    ));

    const activites = evenements
      .filter((e): e is { type: 'activity'; event: import('./types').ActivityEvent } =>
        (e as { type: string }).type === 'activity')
      .map((e) => e.event);
    const piece = activites.filter((e) => e.tool === 'file_uploader').pop();
    expect(piece?.status).toBe('completed');
  });
});
