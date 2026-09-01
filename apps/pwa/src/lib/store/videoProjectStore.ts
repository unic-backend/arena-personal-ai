/* ─────────────────────────────────────────────────────────────
   Video project store — real calls to POST /api/video/projet
   (apps/backend/routers/video_production.py, DEC-0037).

   No fake progress, no simulated status: `result` is exactly the
   JSON the backend returned, and `etapes()` reads the real
   per-step state that `Coordination.executer_parallele()`
   produced server-side. A write step (WanGP generation,
   MoneyPrinterTurbo, narration) that only reached NEEDS_CONFIRMATION
   is shown as such — never as finished.
   ───────────────────────────────────────────────────────────── */

import { create } from 'zustand';
import { activeRemoteCfg } from './backendStore';

/** The closed capability vocabulary — must mirror
 * `core/production/plan_video.py:CAPACITES_VIDEO` exactly. A UI list
 * that drifted from the server's closed list would let the user
 * "select" something the backend refuses anyway, silently. */
export const CAPACITES_VIDEO = [
  'vision',
  'transcription',
  'wangp',
  'moneyprinter',
  'narration',
  'montage',
] as const;

export type CapaciteVideo = (typeof CAPACITES_VIDEO)[number];

export interface EtapeProjetResultat {
  etape: string;
  etat: 'PENDING' | 'RUNNING' | 'DONE' | 'FAILED' | 'SKIPPED' | 'NOT_REACHED';
  tentatives: number;
  secondes: number | null;
  raison: string;
  verifiee: boolean | null;
}

export interface ProjetVideoResultat {
  status: 'success' | 'warning' | 'error';
  agent?: string;
  response: string;
  projet?: {
    objectif: string;
    artefact_final: string | null;
    resultat: {
      tache: string;
      aboutie: boolean;
      arretee_a: string;
      etapes: EtapeProjetResultat[];
    } | null;
  };
}

interface Store {
  modalOpen: boolean;
  setModalOpen(open: boolean): void;
  objectif: string;
  setObjectif(v: string): void;
  /** empty set = mode AUTO (server picks from the full closed list) */
  capacitesChoisies: Set<CapaciteVideo>;
  toggleCapacite(c: CapaciteVideo): void;
  submitting: boolean;
  result: ProjetVideoResultat | null;
  error: string | null;
  submit(): Promise<void>;
  reset(): void;
}

export const useVideoProject = create<Store>((set, get) => ({
  modalOpen: false,
  setModalOpen: (modalOpen) => set({ modalOpen }),
  objectif: '',
  setObjectif: (objectif) => set({ objectif }),
  capacitesChoisies: new Set(),
  toggleCapacite: (c) =>
    set((s) => {
      const next = new Set(s.capacitesChoisies);
      if (next.has(c)) next.delete(c);
      else next.add(c);
      return { capacitesChoisies: next };
    }),
  submitting: false,
  result: null,
  error: null,

  async submit() {
    const cfg = activeRemoteCfg();
    const { objectif, capacitesChoisies } = get();
    if (!cfg) {
      set({ error: 'no-backend' });
      return;
    }
    if (!objectif.trim()) return;

    set({ submitting: true, error: null, result: null });
    try {
      const body: Record<string, unknown> = { objectif: objectif.trim() };
      if (capacitesChoisies.size > 0) body.capacites = Array.from(capacitesChoisies);

      const res = await fetch(`${cfg.url}/api/video/projet`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(cfg.apiKey ? { Authorization: `Bearer ${cfg.apiKey}` } : {}),
        },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const detail = await res.json().catch(() => null);
        set({ error: (detail && detail.detail) || `HTTP ${res.status}`, submitting: false });
        return;
      }

      const data = (await res.json()) as ProjetVideoResultat;
      set({ result: data, submitting: false });
    } catch (e) {
      set({ error: e instanceof Error ? e.message : 'network-error', submitting: false });
    }
  },

  reset: () => set({ objectif: '', capacitesChoisies: new Set(), result: null, error: null }),
}));
