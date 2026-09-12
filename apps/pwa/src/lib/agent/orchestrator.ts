/* ─────────────────────────────────────────────────────────────
   On-device pipelines — video and attachments, nothing else.

   This file used to call itself "the backend" and answer anything
   asked of it. It answered from invented material: a fake project,
   a fake search index, canned prose. On 03/09/2026 that reached
   the owner's phone as if it were his AI, and it was removed.

   What remains genuinely runs here, in the browser: probing a
   video, cutting it, reading an attached file. Every rendered
   activity still corresponds to an event yielded here — the
   difference is that the events now describe work that happened.

   Everything else belongs to his server, which answers or says it
   cannot: `offlineTransport` in `../activity/transport`.
   ───────────────────────────────────────────────────────────── */

import type { ActivityEvent, StreamChunk } from '../activity/types';
import { agentStrings, AgentDict } from './strings';
import { detectLanguage, uiLocale, Lang } from '../i18n';
import {
  AttachedVideo, probeVideo, extractThumbnails, trimVideo, trimSupported,
  parseTrimRange, fmtTime, fmtBytes, VideoMeta,
} from './video';
import {
  PendingAttachment, prepareAttachment, summarizeAttachment,
} from '../attachments';

/**
 * Ce qu'une execution sur appareil recoit du chat.
 *
 * Il portait `getTree`/`setTree` — un faux projet que six pipelines
 * pretendaient reparer. Ils sont supprimes (03/09/2026) ; la video et les
 * pieces jointes n'ont jamais eu besoin d'espace de travail. L'interface
 * reste pour ce qui viendra, sans rien inventer aujourd'hui.
 */
export type AgentContext = Record<string, never>;

/* ── primitives ── */

let _seq = 0;
const uid = () => `ev_${Date.now().toString(36)}_${(++_seq).toString(36)}`;
const beat = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
const rnd = (a: number, b: number) => a + Math.random() * (b - a);

function assertLive(signal?: AbortSignal) {
  if (signal?.aborted) throw new DOMException('The run was cancelled', 'AbortError');
}

type Evt = Omit<ActivityEvent, 'id' | 'startedAt' | 'phase' | 'status'> & {
  status?: ActivityEvent['status'];
  phase?: ActivityEvent['phase'];
};

function* evStart(p: Evt): Generator<StreamChunk, ActivityEvent> {
  const ev: ActivityEvent = {
    id: uid(), startedAt: Date.now(), phase: 'started', status: 'running', ...p,
  };
  yield { type: 'activity', event: ev };
  return ev;
}

function* evPatch(
  ev: ActivityEvent,
  patch: Partial<ActivityEvent>,
): Generator<StreamChunk, ActivityEvent> {
  const merged: ActivityEvent = {
    ...ev, ...patch, id: ev.id, startedAt: ev.startedAt,
  };
  const terminal = ['completed', 'failed', 'cancelled'].includes(merged.status);
  if (terminal && !merged.completedAt) {
    merged.completedAt = Date.now();
    merged.durationMs = merged.completedAt - merged.startedAt;
  }
  yield { type: 'activity', event: merged };
  return merged;
}

const evDone = (ev: ActivityEvent, patch: Partial<ActivityEvent> = {}) =>
  evPatch(ev, { phase: 'completed', status: 'completed', ...patch });

const evFail = (ev: ActivityEvent, patch: Partial<ActivityEvent> = {}) =>
  evPatch(ev, { phase: 'failed', status: 'failed', ...patch });

/** thinking step — high-level summaries only, never private reasoning */
async function* think(
  title: string, description: string | undefined, signal: AbortSignal | undefined,
  workMs: number = rnd(420, 900),
): AsyncGenerator<StreamChunk, ActivityEvent> {
  const ev = yield* evStart({ kind: 'thinking', title, description });
  await beat(workMs);
  assertLive(signal);
  return yield* evDone(ev);
}

/** stream the composed answer word-by-word as it is produced */
async function* streamText(text: string, signal?: AbortSignal): AsyncGenerator<StreamChunk> {
  const words = text.split(/(?<=\s)/);
  const long = text.length > 1200;
  let buf = '';
  let n = 0;
  for (const w of words) {
    buf += w;
    if (++n % 2 === 0) {
      yield { type: 'token', text: buf };
      buf = '';
      if (n % 4 === 0) {
        await beat(long ? rnd(8, 16) : rnd(14, 30));
        assertLive(signal);
      }
    }
  }
  if (buf) yield { type: 'token', text: buf };
}

/* ═══════════════════ PIPELINE: analyze project & fix build ═══════════════════ */

/* ─────────────────────────────────────────────────────────────
   Six pipelines vivaient ici : reparation de build, recherche,
   calcul, execution de code, terminal, et conversation. Aucun ne
   touchait quoi que ce soit de reel — ils travaillaient sur un
   projet invente nomme *pulseboard*, garde dans le localStorage.

   Le 03/09/2026, a 01:36, ils ont repondu au proprietaire en se
   faisant passer pour son IA. Supprimes le meme jour.

   Ce qui reste ici tourne vraiment sur l appareil : la video et
   les pieces jointes. Le reste passe par son serveur, ou ne
   repond pas — voir `offlineTransport` dans `../activity/transport`.
   ───────────────────────────────────────────────────────────── */

async function* pipelineVideo(
  video: AttachedVideo, text: string, signal: AbortSignal, d: AgentDict, lang: Lang,
): AsyncGenerator<StreamChunk, Record<string, never>> {
  yield* think(d.think.analyzing, d.think.readingMsg, signal, rnd(300, 560));

  /* ── 1 · probe: real container metadata ── */
  const probe = yield* evStart({
    kind: 'video', tool: 'video_probe', title: d.video.probeTitle,
    description: d.video.probeDesc,
    input: { name: video.name, size: video.size, type: video.type },
  });
  let meta: VideoMeta;
  try {
    meta = await probeVideo(video);
  } catch (err) {
    yield* evFail(probe, {
      title: d.video.probeTitle,
      description: err instanceof Error ? err.message : String(err),
    });
    yield* think(d.think.preparingShort, undefined, signal, 240);
    yield* streamText(
      lang === 'fr'
        ? `Impossible de décoder **${video.name}** avec les codecs du navigateur. Le fichier n'a pas pu être analysé — la carte d'activité montre l'erreur exacte.`
        : `**${video.name}** could not be decoded by the browser codecs, so nothing was analyzed — the activity card shows the exact error.`,
      signal,
    );
    return {};
  }
  assertLive(signal);
  yield* evDone(probe, {
    description: d.video.probeDone(fmtTime(meta.duration), `${meta.width}×${meta.height}`),
    output: { video: true, ...meta, durationLabel: fmtTime(meta.duration), sizeLabel: fmtBytes(meta.size) },
  });

  /* ── 2 · real frame extraction with real per-frame progress ── */
  const frames = yield* evStart({
    kind: 'video', tool: 'video_frames', title: d.video.framesTitle,
    description: d.video.framesDesc,
  });
  let frameCount = 0;
  let framesSettled = false;
  const thumbsPromise = extractThumbnails(video, meta.duration, 5, (done) => { frameCount = done; })
    .then((t) => { framesSettled = true; return t; });
  while (!framesSettled) {
    await beat(120);
    assertLive(signal);
    yield* evPatch(frames, {
      phase: 'progress',
      progress: { done: frameCount, total: 5, unit: 'frames' },
    });
  }
  const thumbs = await thumbsPromise;
  yield* evDone(frames, {
    description: d.video.framesDone(thumbs.length),
    output: { frames: thumbs.length, thumbs: thumbs.map((t) => ({ ts: t.ts, dataUrl: t.dataUrl })) },
    progress: { done: thumbs.length, total: 5, unit: 'frames' },
  });

  /* ── 3 · optional trim — real MediaRecorder re-encode ── */
  const range = parseTrimRange(text);
  let trimNote: string | undefined;
  if (range && meta.duration > 0) {
    const start = Math.min(range.start, Math.max(meta.duration - 0.5, 0));
    const end = Math.min(range.end, meta.duration);
    if (end - start >= 0.5) {
      const trim = yield* evStart({
        kind: 'video', tool: 'video_editor', title: d.video.trimTitle,
        description: d.video.trimDesc(fmtTime(start), fmtTime(end)),
        input: { start, end, startLabel: fmtTime(start), endLabel: fmtTime(end) },
      });
      if (!trimSupported()) {
        yield* evFail(trim, { title: d.video.trimFail, description: d.video.unsupported });
      } else {
        /* poll genuine recorder progress while the encoder runs in real time */
        let probe = { ratio: 0, at: start };
        let settled = false;
        const run = trimVideo(video, start, end, (ratio, at) => { probe = { ratio, at }; }, () => signal.aborted)
          .then((r) => { settled = true; return r; });
        while (!settled) {
          await beat(320);
          assertLive(signal);
          yield* evPatch(trim, {
            phase: 'progress',
            description: `${fmtTime(probe.at)} · ${Math.round(probe.ratio * 100)}%`,
            progress: { done: Math.round(probe.ratio * 100), total: 100, unit: '%' },
          });
        }
        try {
          const result = await run;
          yield* evDone(trim, {
            description: d.video.trimDone(fmtBytes(result.size)),
            output: {
              start, end, startLabel: fmtTime(start), endLabel: fmtTime(end),
              download: {
                url: result.blobUrl,
                name: `${video.name.replace(/\.[^.]+$/, '')}_clip.${result.mimeType.includes('mp4') ? 'mp4' : 'webm'}`,
                size: result.size, sizeLabel: fmtBytes(result.size), mime: result.mimeType,
              },
            },
            progress: { done: 100, total: 100, unit: '%' },
          });
          trimNote = d.video.trimNoteOk(fmtTime(start), fmtTime(end), fmtBytes(result.size));
        } catch (err) {
          yield* evFail(trim, {
            title: d.video.trimFail,
            description: err instanceof Error ? err.message : String(err),
          });
        }
      }
    }
  }

  /* ── 4 · compose the report ── */
  const summary = yield* evStart({
    kind: 'analysis', tool: 'analysis', title: d.video.summaryTitle,
    description: d.video.summaryDesc,
  });
  await beat(rnd(340, 560));
  assertLive(signal);
  yield* evDone(summary);

  yield* think(d.think.preparingShort, undefined, signal, rnd(240, 380));
  const codec = (meta.type || 'video/*').replace(/;.*$/, '');
  const text2 = d.video.answerMeta(
    meta.name,
    d.video.metaLines(fmtTime(meta.duration), `${meta.width}×${meta.height}`, fmtBytes(meta.size), codec, thumbs.length),
    trimNote ?? (range ? undefined : d.video.trimNoteHint),
  );
  yield* streamText(text2, signal);
  return {};
}

/* ═══════════════════ PIPELINE: local attachment inspection ═══════════════════ */

async function* pipelineAttachments(
  attachments: PendingAttachment[],
  signal: AbortSignal,
  d: AgentDict,
  lang: Lang,
): AsyncGenerator<StreamChunk, Record<string, never>> {
  yield* think(
    d.think.analyzing,
    lang === 'fr' ? 'Identification des formats joints' : 'Identifying attached formats',
    signal,
    rnd(220, 380),
  );

  let root = yield* evStart({
    kind: 'tool',
    tool: 'attachment_inspector',
    title: lang === 'fr' ? 'Inspection des pièces jointes' : 'Inspecting attachments',
    description: lang === 'fr'
      ? `${attachments.length} fichier(s) à vérifier…`
      : `${attachments.length} file(s) to inspect…`,
    progress: { done: 0, total: attachments.length, unit: lang === 'fr' ? 'fichiers' : 'files' },
  });
  const inspected: PendingAttachment[] = [];
  const failed: PendingAttachment[] = [];

  for (const original of attachments) {
    assertLive(signal);
    let child = yield* evStart({
      parentId: root.id,
      kind: original.kind === 'video' ? 'video' : 'file',
      tool: `${original.kind}_inspector`,
      title: original.name,
      description: lang === 'fr' ? 'Lecture du fichier…' : 'Reading file…',
      input: { name: original.name, size: original.size, type: original.type },
      metadata: { op: 'parse', path: original.name, bytes: original.size },
    });
    const value = await prepareAttachment(original);
    assertLive(signal);
    if (value.status === 'failed') {
      failed.push(value);
      child = yield* evFail(child, { description: value.error });
    } else {
      inspected.push(value);
      const facts = Object.entries(value.metadata ?? {})
        .filter(([, fact]) => fact !== undefined)
        .map(([key, fact]) => `${key}: ${fact}`)
        .join(' · ');
      child = yield* evDone(child, {
        description: facts || (lang === 'fr' ? 'Format vérifié' : 'Format verified'),
        output: { attachment: summarizeAttachment(value), extractedCharacters: value.extractedText?.length ?? 0 },
      });
    }
    const done = inspected.length + failed.length;
    root = yield* evPatch(root, {
      phase: 'progress',
      description: lang === 'fr'
        ? `${done}/${attachments.length} fichiers inspectés`
        : `${done}/${attachments.length} files inspected`,
      progress: { done, total: attachments.length, unit: lang === 'fr' ? 'fichiers' : 'files' },
    });
  }

  root = yield* (failed.length ? evFail : evDone)(root, {
    description: failed.length
      ? (lang === 'fr' ? `${failed.length} fichier(s) illisible(s)` : `${failed.length} unreadable file(s)`)
      : (lang === 'fr' ? `${inspected.length} fichier(s) vérifié(s)` : `${inspected.length} file(s) verified`),
    output: { files: inspected.length, failed: failed.length },
    progress: { done: attachments.length, total: attachments.length, unit: lang === 'fr' ? 'fichiers' : 'files' },
  });

  yield* think(d.think.preparingShort, undefined, signal, rnd(220, 360));
  const lines = inspected.map((value) => {
    const meta = value.metadata ?? {};
    const details = [
      fmtBytes(value.size),
      meta.width && meta.height ? `${meta.width}×${meta.height}` : '',
      meta.duration ? fmtTime(Number(meta.duration)) : '',
      meta.pages ? `${meta.pages} ${lang === 'fr' ? 'pages' : 'pages'}` : '',
      meta.characters ? `${Number(meta.characters).toLocaleString()} ${lang === 'fr' ? 'caractères' : 'characters'}` : '',
    ].filter(Boolean).join(' · ');
    return `- **${value.name}** — ${value.kind} · ${details || value.type}`;
  });
  const excerpts = inspected
    .filter((value) => value.extractedText)
    .slice(0, 2)
    .map((value) => `### ${value.name}\n\n> ${value.extractedText!.slice(0, 280).replace(/\s+/g, ' ')}${value.extractedText!.length > 280 ? '…' : ''}`);
  const answer = lang === 'fr'
    ? [
        `J’ai inspecté localement **${inspected.length}/${attachments.length} pièces jointes**.`,
        '', ...lines, '',
        'Cette inspection locale confirme les formats et métadonnées réels. Pour une analyse sémantique complète des images, PDF ou fichiers audio, connecte le backend IA : les fichiers seront alors envoyés par le canal sécurisé et transmis au modèle compatible.',
        ...(excerpts.length ? ['', ...excerpts] : []),
      ].join('\n')
    : [
        `I locally inspected **${inspected.length}/${attachments.length} attachments**.`,
        '', ...lines, '',
        'This local inspection confirms real formats and metadata. For full semantic analysis of images, PDFs or audio, connect the AI backend: files will then use the secure upload channel and reach the compatible model.',
        ...(excerpts.length ? ['', ...excerpts] : []),
      ].join('\n');
  yield* streamText(answer, signal);
  return {};
}

/* ═══════════════════ ENTRY POINT ═══════════════════ */

export interface AgentRequest {
  text: string;
  video?: AttachedVideo;
  attachments?: PendingAttachment[];
  /** recent conversation turns, for remote backends */
  history?: Array<{ role: 'user' | 'assistant'; content: string }>;
  /**
   * Stable conversation identity (the store's `activeId`) — distinct from
   * the per-execution run id the transport generates on every call. The
   * backend uses this to key its memory session; without it, a specialized
   * agent (fresh info, plaquiste…) never sees the previous turn.
   */
  conversationId?: string;
}

export async function* runAgent(
  request: AgentRequest,
  _ctx: AgentContext,
  signal?: AbortSignal,
): AsyncGenerator<StreamChunk> {
  await beat(rnd(220, 420)); // connection ramp — first event arrives shortly after send
  const lang: Lang = detectLanguage(request.text) ?? uiLocale();
  const d = agentStrings(lang);

  // A single video keeps the specialized edit/thumbnail pipeline.
  if (request.video) {
    yield* pipelineVideo(request.video, request.text, signal!, d, lang);
    yield { type: 'done', meta: {} };
    return;
  }

  if (request.attachments?.length) {
    yield* pipelineAttachments(request.attachments, signal!, d, lang);
    yield { type: 'done', meta: {} };
    return;
  }

  // Rien d'autre ne tourne ici. `choisirTransport` ne mene a ce fichier que
  // pour la video ; y arriver autrement serait un cablage casse, et un texte
  // rendu a la place serait exactement le defaut retire le 03/09/2026.
  throw new Error('BACKEND_OFFLINE');
}
