/* ─────────────────────────────────────────────────────────────
   Remote transport — connects Usman to a real AI backend over
   Server-Sent Events (POST + ReadableStream).

   Backend contract (one JSON object per SSE frame):

     data: {"type":"activity","event":{ …ActivityEvent… }}
     data: {"type":"token","text":"partial response "}
     data: {"type":"done","meta":{"sources":[…]}}

   ActivityEvent = {
     id, parentId?, kind, status, phase, tool?, title, description?,
     startedAt, input?, output?, progress?: { done, total, unit? },
     metadata?, durationMs?
   }

   kind:  thinking | planning | tool | search | file | terminal |
          code | browser | database | calculation | analysis |
          video | response | error
   status/phase lifecycle: running(started) → progress* →
          completed | failed | cancelled
   ───────────────────────────────────────────────────────────── */

import type { ActivityEvent, StreamChunk } from './types';
import { normaliserSources } from './sources';
import type { AgentTransport } from './transport';
import type { AgentRequest } from '../agent/orchestrator';
import { uiLocale } from '../i18n';
import { resolveActiveConnectors } from '../store/connectorStore';
import { delay, useNetwork, waitForOnline } from '../network/networkStore';
import { buildPersonaPrompt, usePersona } from '../store/personaStore';
import { getActiveMemoriesPayload } from '../memory/memoryStore';
import { useCapacite } from '../capacites';

export interface RemoteConfig {
  url: string;
  apiKey?: string;
}

/** Le contrat du serveur devient celui de l'interface — voir `./sources`. */
function normaliserChunk(chunk: StreamChunk): StreamChunk {
  if (chunk.type !== 'done' || !chunk.meta?.sources) return chunk;
  return { ...chunk, meta: { ...chunk.meta, sources: normaliserSources(chunk.meta.sources) } };
}

interface UploadedAttachment {
  id: string;
  name: string;
  size: number;
  type: string;
  kind: string;
  metadata?: Record<string, unknown>;
  extractedCharacters?: number;
  /** L'etat metier reel (PieceJointe.statut cote serveur) — LU/ECHEC/NON_PRIS_EN_CHARGE. */
  status?: string;
  /** Faux si le fichier n'a jamais ete lu (format non pris en charge, echec). */
  readable?: boolean;
  reason?: string | null;
}

interface UploadedMedia {
  status: string;
  filename: string;
  original_filename: string;
  path: string;
  size_bytes: number;
}

const OFFICE_EDITABLE_RE = /\.(?:xls|xlsx|xlsm|csv|tsv|doc|docx|ppt|pptx|pptm|ppsx|ppsm|potx)$/i;

function isEditableOfficeAttachment(name: string): boolean {
  return OFFICE_EDITABLE_RE.test(name.trim());
}

function eventId(prefix: string) {
  return `${prefix}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
}

function finishEvent(
  event: ActivityEvent,
  status: 'completed' | 'failed',
  patch: Partial<ActivityEvent> = {},
): ActivityEvent {
  const completedAt = Date.now();
  return {
    ...event,
    ...patch,
    status,
    phase: status,
    completedAt,
    durationMs: completedAt - event.startedAt,
  };
}

const MAX_STREAM_RETRIES = 4;

function isRetryableStatus(status: number) {
  return status === 408 || status === 425 || status === 429 || status >= 500;
}

function parseRetryAfter(value: string | null): number | undefined {
  if (!value) return undefined;
  const seconds = Number(value);
  if (Number.isFinite(seconds)) return Math.max(0, seconds * 1000);
  const date = Date.parse(value);
  return Number.isNaN(date) ? undefined : Math.max(0, date - Date.now());
}

function makeRunId() {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : eventId('run');
}

/**
 * L'adresse d'un serveur, prete a etre appelee : sans `/` final, et TOUJOURS
 * avec un schema.
 *
 * **Mesure du 14/09/2026.** Le champ de reglages accepte ce qu'on y tape. Colle
 * `arena-personal-ai-production.up.railway.app` sans `https://` et le navigateur
 * la lit comme un chemin RELATIF : depuis une PWA servie par ce meme domaine, le
 * sondage partait vers
 * `https://…railway.app/arena-personal-ai-production.up.railway.app/health` et
 * rendait 404. Le panneau affichait « Provider probe failed » — un message qui
 * ne designe ni l'adresse, ni le 404, et qui a envoye chercher du cote de la cle.
 *
 * On ne devine qu'une chose, et seulement quand rien n'est ecrit : `https`. Une
 * adresse qui porte deja un schema — `http://` sur un reseau local, par
 * exemple — n'est pas touchee.
 */
export function adresseDuServeur(url: string): string {
  const propre = url.trim().replace(/\/+$/, '');
  if (!propre) return '';
  return /^[a-z][a-z0-9+.-]*:\/\//i.test(propre) ? propre : `https://${propre}`;
}

export function makeRemoteTransport(cfg: RemoteConfig): AgentTransport {
  const base = adresseDuServeur(cfg.url);
  return {
    async *run(request: AgentRequest, _ctx, signal: AbortSignal) {
      const fr = uiLocale() === 'fr';
      const uploaded: UploadedAttachment[] = [];
      const mediaPaths: string[] = [];
      const officePaths: string[] = [];
      let preparedCount = 0;
      const attachments = request.attachments ?? [];

      if (attachments.length) {
        let root: ActivityEvent = {
          id: eventId('upload'),
          kind: 'tool',
          tool: 'attachment_upload',
          title: fr ? 'Envoi des pièces jointes' : 'Uploading attachments',
          description: fr
            ? `${attachments.length} fichier(s) vers le backend…`
            : `${attachments.length} file(s) to the backend…`,
          status: 'running',
          phase: 'started',
          startedAt: Date.now(),
          progress: { done: 0, total: attachments.length, unit: fr ? 'fichiers' : 'files' },
        };
        yield { type: 'activity', event: root };

        for (const attachment of attachments) {
          let child: ActivityEvent = {
            id: eventId('file'),
            parentId: root.id,
            kind: 'file',
            tool: 'file_uploader',
            title: attachment.name,
            description: fr ? 'Transfert sécurisé…' : 'Secure upload…',
            status: 'running',
            phase: 'started',
            startedAt: Date.now(),
            input: { name: attachment.name, size: attachment.size, type: attachment.type },
            metadata: { op: 'upload', path: attachment.name, bytes: attachment.size },
          };
          yield { type: 'activity', event: child };

          try {
            const form = new FormData();
            form.append('file', attachment.file, attachment.name);
            const isMedia = attachment.kind === 'audio' || attachment.kind === 'video';
            const isOffice = isEditableOfficeAttachment(attachment.name);
            if (!isMedia && !isOffice) form.append('kind', attachment.kind);

            // Trois contrats : documents/images -> extraction éphémère /files ;
            // médias -> stockage média ; Office éditable -> staging binaire
            // persistant juste assez longtemps pour l'import Univer.
            const uploadPath = isMedia
              ? '/api/upload'
              : isOffice
                ? '/office/files'
                : '/files';
            const upload = await fetch(`${base}${uploadPath}`, {
              method: 'POST',
              headers: cfg.apiKey ? { Authorization: `Bearer ${cfg.apiKey}` } : {},
              body: form,
              signal,
            });
            if (!upload.ok) {
              const detail = await upload.text().catch(() => '');
              throw new Error(`${upload.status}${detail ? ` · ${detail.slice(0, 160)}` : ''}`);
            }

            if (isMedia || isOffice) {
              const result = (await upload.json()) as UploadedMedia;
              if (result.status !== 'success' || !result.path) {
                throw new Error(
                  isOffice
                    ? (fr ? 'Le document Office n\'a pas été stocké.' : 'The Office document was not stored.')
                    : (fr ? 'Le média n\'a pas été stocké.' : 'The media was not stored.'),
                );
              }
              if (isOffice) officePaths.push(result.path);
              else mediaPaths.push(result.path);
              child = finishEvent(child, 'completed', {
                description: isOffice
                  ? (fr ? 'Document Office reçu et prêt à modifier' : 'Office document received and ready to edit')
                  : (fr ? 'Média reçu et prêt à analyser' : 'Media received and ready to analyze'),
                output: {
                  kind: isOffice ? 'office' : attachment.kind,
                  path: result.path,
                  size: result.size_bytes,
                },
              });
            } else {
              const result = (await upload.json()) as UploadedAttachment;
              uploaded.push(result);
              // HTTP 200 ne veut dire que « le serveur a repondu » : /files
              // rend toujours un objet, meme pour un fichier refuse.
              if (result.readable === false) {
                child = finishEvent(child, 'failed', {
                  description: result.reason
                    || (fr ? 'Ce fichier n\'a pas pu être lu.' : 'This file could not be read.'),
                  output: {
                    id: result.id,
                    kind: result.kind,
                    status: result.status,
                    readable: false,
                  },
                });
              } else {
                child = finishEvent(child, 'completed', {
                  description: fr ? 'Fichier reçu et inspecté' : 'File received and inspected',
                  output: {
                    id: result.id,
                    kind: result.kind,
                    metadata: result.metadata,
                    extractedCharacters: result.extractedCharacters,
                  },
                });
              }
            }
            preparedCount += 1;
            yield { type: 'activity', event: child };

            root = {
              ...root,
              phase: 'progress',
              description: fr
                ? `${preparedCount}/${attachments.length} fichiers envoyés`
                : `${preparedCount}/${attachments.length} files uploaded`,
              progress: { done: preparedCount, total: attachments.length, unit: fr ? 'fichiers' : 'files' },
            };
            yield { type: 'activity', event: root };
          } catch (error) {
            const description = error instanceof Error ? error.message : String(error);
            child = finishEvent(child, 'failed', { description });
            yield { type: 'activity', event: child };
            root = finishEvent(root, 'failed', { description });
            yield { type: 'activity', event: root };
            throw error;
          }
        }

        root = finishEvent(root, 'completed', {
          description: fr
            ? `${preparedCount} pièce(s) jointe(s) préparée(s)`
            : `${preparedCount} attachment(s) prepared`,
          output: {
            files: preparedCount,
            attachments: uploaded,
            mediaPaths,
            officePaths,
          },
          progress: { done: preparedCount, total: attachments.length, unit: fr ? 'fichiers' : 'files' },
        });
        yield { type: 'activity', event: root };
      }

      const runId = makeRunId();
      const personaProfile = usePersona.getState();
      const personaInstructions = buildPersonaPrompt(personaProfile);

      const requestBody = {
        text: request.text,
        locale: uiLocale(),
        history: request.history ?? [],
        attachments: uploaded.map((value) => value.id),
        media_paths: mediaPaths,
        office_paths: officePaths,
        connectors: await resolveActiveConnectors(),
        run_id: runId,
        // Identite STABLE du fil (le `activeId` du store), distincte de
        // `run_id` ci-dessus qui change a chaque message : sans elle, le
        // serveur utilisait `run_id` comme session de memoire et perdait
        // les tours precedents a chaque nouveau message (corrige le
        // 12/09/2026). Absent (ancien client, ou aucune conversation active
        // encore creee) : le serveur retombe sur `run_id`, comportement
        // inchange.
        conversation_id: request.conversationId,
        // L'espace ouvert dans l'interface, pour que le serveur route direct
        // vers l'agent dedie au lieu de deviner l'intention depuis la phrase.
        // `null` (Usman general) ne change rien : le classifieur habituel
        // continue de decider, comme avant ce changement.
        espace: useCapacite.getState().active,
        persona: {
          user_name: personaProfile.userName,
          user_role: personaProfile.userRole,
          tone: personaProfile.assistantTone,
          format: personaProfile.responseFormat,
          instructions: personaInstructions,
        },
        memories: getActiveMemoriesPayload(),
      };
      let lastEventId: string | undefined;
      let attempt = 0;

      try {
        while (attempt <= MAX_STREAM_RETRIES) {
          if (!navigator.onLine) await waitForOnline(signal);
          try {
            const res = await fetch(`${base}/agent/stream`, {
              method: 'POST',
              headers: {
                'Content-Type': 'application/json',
                Accept: 'text/event-stream',
                ...(cfg.apiKey ? { Authorization: `Bearer ${cfg.apiKey}` } : {}),
                ...(lastEventId ? { 'Last-Event-ID': lastEventId } : {}),
                'X-Usman-Run-ID': runId,
              },
              body: JSON.stringify(requestBody),
              signal,
            });
            if (!res.ok || !res.body) {
              const detail = await res.text().catch(() => '');
              const error = new Error(
                `AI backend responded ${res.status}${detail ? ` — ${detail.slice(0, 180)}` : ''}`,
              ) as Error & { retryable?: boolean; retryAfter?: number };
              error.retryable = isRetryableStatus(res.status);
              error.retryAfter = parseRetryAfter(res.headers.get('Retry-After'));
              throw error;
            }

            useNetwork.getState().setReconnecting(false);
            const reader = res.body.getReader();
            const decoder = new TextDecoder();
            let buf = '';
            for (;;) {
              const { done, value } = await reader.read();
              if (done) break;
              buf += decoder.decode(value, { stream: true });
              buf = buf.replace(/\r\n/g, '\n');
              let idx: number;
              while ((idx = buf.indexOf('\n\n')) >= 0) {
                const frame = buf.slice(0, idx);
                buf = buf.slice(idx + 2);
                let frameId: string | undefined;
                let payload = '';
                for (const line of frame.split('\n')) {
                  if (line.startsWith('id:')) frameId = line.slice(3).trim();
                  if (line.startsWith('data:')) payload += line.slice(5).trim();
                }
                if (frameId) lastEventId = frameId;
                if (!payload || payload === '[DONE]') continue;
                const chunk = JSON.parse(payload) as StreamChunk;
                if (chunk.type === 'error') throw new Error(chunk.message);
                yield normaliserChunk(chunk);
                if (chunk.type === 'done') return;
              }
            }
            throw Object.assign(new Error('AI stream closed before the completion event'), { retryable: true });
          } catch (rawError) {
            if (signal.aborted) throw rawError;
            const error = rawError as Error & { retryable?: boolean; retryAfter?: number };
            const retryable = error.retryable !== false && !(error instanceof SyntaxError);
            if (!retryable || attempt >= MAX_STREAM_RETRIES) throw error;
            attempt += 1;
            useNetwork.getState().setReconnecting(true, attempt);
            if (!navigator.onLine) await waitForOnline(signal);
            const backoff = error.retryAfter ?? Math.min(8000, 500 * 2 ** (attempt - 1) + Math.random() * 350);
            await delay(backoff, signal);
          }
        }
      } finally {
        useNetwork.getState().setReconnecting(false);
      }
      throw new Error('AI stream retry budget exhausted');
    },
  };
}

/** connectivity probe — GET /health, expects { ok: true, name?, model? } */
export async function pingBackend(
  cfg: RemoteConfig,
): Promise<{
  ok: boolean;
  latencyMs: number;
  name?: string;
  provider?: string;
  model?: string;
  configured?: boolean;
  error?: string;
}> {
  const base = adresseDuServeur(cfg.url);
  const started = performance.now();
  const res = await fetch(`${base}/health`, {
    headers: cfg.apiKey ? { Authorization: `Bearer ${cfg.apiKey}` } : {},
    signal: AbortSignal.timeout(6000),
  });
  const latencyMs = Math.round(performance.now() - started);
  // Le code HTTP voyage avec l'echec. Sans lui, l'appelant n'a que son
  // message par defaut — « Provider probe failed » — qui ne dit ni ou ca a
  // echoue ni pourquoi. Un `404` designe l'adresse, un `502` le serveur.
  if (!res.ok) return { ok: false, latencyMs, error: `HTTP ${res.status}` };
  const data = (await res.json().catch(() => ({}))) as {
    ok?: boolean;
    name?: string;
    provider?: string;
    model?: string;
    configured?: boolean;
    error?: string;
  };
  return {
    ok: data.ok !== false,
    latencyMs,
    name: data.name,
    provider: data.provider,
    model: data.model,
    configured: data.configured,
    error: data.error,
  };
}
