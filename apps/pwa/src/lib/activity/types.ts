/* ─────────────────────────────────────────────────────────────
   Activity event model — the single source of truth for what
   the UI is allowed to show. The interface renders exclusively
   from these events; nothing is fabricated client-side.
   ───────────────────────────────────────────────────────────── */

import type { AttachmentSummary } from '../attachments';

export type ActivityStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled';

export type ActivityKind =
  | 'thinking'
  | 'planning'
  | 'tool'
  | 'search'
  | 'file'
  | 'terminal'
  | 'code'
  | 'browser'
  | 'database'
  | 'calculation'
  | 'analysis'
  | 'video'
  | 'response'
  | 'error';

/** wire-level phases a tool/activity can emit */
export type ActivityPhase =
  | 'started'
  | 'progress'
  | 'updated'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface ActivityProgress {
  done: number;
  total: number;
  unit?: string; // e.g. "files"
}

export interface SourceMeta {
  title: string;
  /** Facultatif : le serveur envoie une adresse, jamais un domaine. Il est
   *  deduit a la frontiere (`normaliserSources`) et reste absent quand
   *  l'adresse est illisible — l'affichage doit savoir s'en passer. Le declarer
   *  obligatoire ne le rendait pas present : ca cachait seulement le trou, que
   *  le rendu decouvrait en plantant. */
  domain?: string;
  url?: string;
  date?: string;
  excerpt?: string;
}

export interface FileOpMeta {
  path: string;
  op:
    | 'read'
    | 'create'
    | 'edit'
    | 'delete'
    | 'rename'
    | 'move'
    | 'search'
    | 'parse'
    | 'upload'
    | 'download';
  added?: number;
  removed?: number;
  bytes?: number;
}

export interface ActivityEvent {
  id: string;
  parentId?: string;
  kind: ActivityKind;
  status: ActivityStatus;
  phase: ActivityPhase;
  /** registry id of the tool producing this event, if any */
  tool?: string;
  /** short high-level summary — never private chain-of-thought */
  title: string;
  description?: string;
  startedAt: number;
  completedAt?: number;
  durationMs?: number;
  /** structured input/output payloads (command, query, path, code…) */
  input?: unknown;
  output?: unknown;
  progress?: ActivityProgress;
  metadata?: Record<string, unknown>;
}

export type StreamChunk =
  | { type: 'activity'; event: ActivityEvent }
  | { type: 'token'; text: string }
  | { type: 'done'; meta?: MessageMeta }
  | { type: 'error'; message: string };

import type { ActionEnAttente } from '../actions/confirmer';

/** Un document reellement ecrit pendant le tour, avec l'adresse qui l'ouvre. */
export interface DocumentProduit {
  url: string;
  action: string;
  message: string;
}

export interface MessageMeta {
  sources?: SourceMeta[];
  query?: string;
  /** Ce qui attend un accord : l'interface pose un bouton dessus. */
  en_attente?: ActionEnAttente[];
  /** Ce qui vient d'etre ECRIT pendant ce tour et qu'il peut ouvrir tout de
   *  suite — un devis PDF depuis qu'il ne passe plus par la confirmation
   *  (04/09/2026). Sans ce champ, le fichier existe sur le serveur et aucun
   *  ecran ne peut l'atteindre. Miroir de `_documents_produits`. */
  documents?: DocumentProduit[];
  /** Identifiant confirmé par une phrase (« c'est bon ») pendant ce tour. */
  confirme?: string;
  provider?: string;
  model?: string;
  attachments?: AttachmentSummary[];
  /** Legacy video field retained for already persisted conversations. */
  video?: { name: string; size: number; type: string };
}

export interface ActivityNode extends ActivityEvent {
  children: ActivityNode[];
}

/* ── tree helpers ── */

export function upsertNode(nodes: ActivityNode[], ev: ActivityEvent): ActivityNode[] {
  const idx = nodes.findIndex((n) => n.id === ev.id);
  if (idx >= 0) {
    const next = [...nodes];
    next[idx] = { ...next[idx], ...ev, children: next[idx].children };
    return next;
  }
  const node: ActivityNode = { ...ev, children: [] };
  if (ev.parentId) {
    return nodes.map((n) =>
      n.id === ev.parentId ? { ...n, children: upsertNode(n.children, ev) } : n,
    );
  }
  return [...nodes, node];
}

export function flatten(nodes: ActivityNode[]): ActivityNode[] {
  const out: ActivityNode[] = [];
  const walk = (ns: ActivityNode[]) => ns.forEach((n) => { out.push(n); walk(n.children); });
  walk(nodes);
  return out;
}

export function findNode(nodes: ActivityNode[], id: string): ActivityNode | undefined {
  return flatten(nodes).find((n) => n.id === id);
}

/** deepest running leaf — drives the live "current status" text */
export function activeLabel(nodes: ActivityNode[]): string | undefined {
  const all = flatten(nodes);
  const running = all.filter((n) => n.status === 'running');
  const last = running[running.length - 1];
  return last?.title;
}

export interface ActivityStats {
  total: number;
  completed: number;
  failed: number;
  running: number;
  toolCount: number;
  durationMs: number;
}

export function collectStats(nodes: ActivityNode[]): ActivityStats {
  const all = flatten(nodes).filter((n) => n.kind !== 'thinking');
  const start = Math.min(...all.map((n) => n.startedAt));
  const ends = all.map((n) => n.completedAt ?? Date.now());
  return {
    total: all.length,
    completed: all.filter((n) => n.status === 'completed').length,
    failed: all.filter((n) => n.status === 'failed').length,
    running: all.filter((n) => n.status === 'running').length,
    toolCount: new Set(all.map((n) => n.tool).filter(Boolean)).size,
    durationMs: all.length ? Math.max(...ends) - start : 0,
  };
}

/** Never leave a transient state on screen after reload. */
export function normalizeLoaded(nodes: ActivityNode[]): ActivityNode[] {
  return nodes.map((n) => ({
    ...n,
    status: n.status === 'running' || n.status === 'pending' ? 'cancelled' : n.status,
    phase:
      n.phase === 'started' || n.phase === 'progress' || n.phase === 'updated'
        ? 'cancelled'
        : n.phase,
    description:
      n.status === 'running' ? 'Interrupted when the session was closed' : n.description,
    children: normalizeLoaded(n.children),
  }));
}

export function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.max(1, Math.round(ms))}ms`;
  const s = ms / 1000;
  return `${s < 10 ? s.toFixed(1) : Math.round(s)}s`;
}
