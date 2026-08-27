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
import type { AgentTransport } from './transport';
import type { AgentRequest } from '../agent/orchestrator';
import { uiLocale } from '../i18n';
import { resolveActiveConnectors } from '../store/connectorStore';
import { delay, useNetwork, waitForOnline } from '../network/networkStore';
import { buildPersonaPrompt, usePersona } from '../store/personaStore';
import { getActiveMemoriesPayload } from '../memory/memoryStore';

export interface RemoteConfig {
  url: string;
  apiKey?: string;
}

interface UploadedAttachment {
  id: string;
  name: string;
  size: number;
  type: string;
  kind: string;
  metadata?: Record<string, unknown>;
  extractedCharacters?: number;
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

export function makeRemoteTransport(cfg: RemoteConfig): AgentTransport {
  const base = cfg.url.replace(/\/+$/, '');
  return {
    async *run(request: AgentRequest, _ctx, signal: AbortSignal) {
      const fr = uiLocale() === 'fr';
      const uploaded: UploadedAttachment[] = [];
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
            form.append('kind', attachment.kind);
            const upload = await fetch(`${base}/files`, {
              method: 'POST',
              headers: cfg.apiKey ? { Authorization: `Bearer ${cfg.apiKey}` } : {},
              body: form,
              signal,
            });
            if (!upload.ok) {
              const detail = await upload.text().catch(() => '');
              throw new Error(`${upload.status}${detail ? ` · ${detail.slice(0, 160)}` : ''}`);
            }
            const result = (await upload.json()) as UploadedAttachment;
            uploaded.push(result);
            child = finishEvent(child, 'completed', {
              description: fr ? 'Fichier reçu et inspecté' : 'File received and inspected',
              output: {
                id: result.id,
                kind: result.kind,
                metadata: result.metadata,
                extractedCharacters: result.extractedCharacters,
              },
            });
            yield { type: 'activity', event: child };

            root = {
              ...root,
              phase: 'progress',
              description: fr
                ? `${uploaded.length}/${attachments.length} fichiers envoyés`
                : `${uploaded.length}/${attachments.length} files uploaded`,
              progress: { done: uploaded.length, total: attachments.length, unit: fr ? 'fichiers' : 'files' },
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
            ? `${uploaded.length} pièce(s) jointe(s) préparée(s)`
            : `${uploaded.length} attachment(s) prepared`,
          output: { files: uploaded.length, attachments: uploaded },
          progress: { done: uploaded.length, total: attachments.length, unit: fr ? 'fichiers' : 'files' },
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
        connectors: await resolveActiveConnectors(),
        run_id: runId,
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
                yield chunk;
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
  const base = cfg.url.replace(/\/+$/, '');
  const started = performance.now();
  const res = await fetch(`${base}/health`, {
    headers: cfg.apiKey ? { Authorization: `Bearer ${cfg.apiKey}` } : {},
    signal: AbortSignal.timeout(6000),
  });
  const latencyMs = Math.round(performance.now() - started);
  if (!res.ok) return { ok: false, latencyMs };
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
