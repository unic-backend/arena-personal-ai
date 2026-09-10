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
import { activeRemoteCfg, signalerSiPanne } from './backendStore';

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
  'xaar_kaname',
  'montage',
  'krillin_subtitle',
  'krillin_tts',
  'krillin_render_horizontal',
  'krillin_render_vertical',
  'krillin_cover',
  'drift',
  'hidream_image',
] as const;

export type CapaciteVideo = (typeof CAPACITES_VIDEO)[number];

/** Un fichier source envoye au serveur (POST /api/upload), pour devenir une
 *  reference du projet. Sans ceci, `vision`, `transcription` et `montage`
 *  echouaient TOUJOURS : le formulaire n'avait aucun moyen de fournir le
 *  fichier qu'elles exigent — mesure le 02/09/2026, signale par le
 *  proprietaire ("ici aussi rien ne marche"). */
export interface ReferenceFile {
  id: string;
  name: string;
  /** Chemin sous MEDIA_DIR renvoye par le serveur — `null` tant que l'envoi n'a pas abouti. */
  path: string | null;
  status: 'uploading' | 'ready' | 'failed';
  error?: string;
}

function idReference() {
  return `ref_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
}

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
  /** Ce que la machine branchee sait reellement faire. `null` = pas encore
   *  demande — on n'affiche alors aucun verdict plutot qu'un faux. */
  disponibilite: Record<string, { disponible: boolean; raison: string }> | null;
  chargerDisponibilite(): Promise<void>;
  references: ReferenceFile[];
  addReferenceFiles(files: FileList | File[]): Promise<void>;
  removeReference(id: string): void;
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

  disponibilite: null,

  /**
   * Demande au serveur ce qu'il sait faire.
   *
   * **Mesure du 03/09/2026.** Le proprietaire, sur son telephone branche a
   * Railway, cochait « Narration » et « Vision » : aucun de ces moteurs n'y
   * existe, ils tournent sur son PC. Le projet partait quand meme et echouait
   * apres coup sur `All connection attempts failed`.
   *
   * En cas d'echec on reste a `null` : ne rien savoir s'affiche comme ne rien
   * savoir, jamais comme « tout marche ».
   */
  async chargerDisponibilite() {
    const cfg = activeRemoteCfg();
    if (!cfg) {
      set({ disponibilite: null });
      return;
    }
    try {
      const res = await fetch(`${cfg.url.replace(/\/+$/, '')}/agent/capabilities`, {
        headers: cfg.apiKey ? { Authorization: `Bearer ${cfg.apiKey}` } : {},
        signal: AbortSignal.timeout(8000),
      });
      if (!res.ok) { set({ disponibilite: null }); return; }
      const corps = await res.json() as {
        video?: Record<string, { disponible: boolean; raison: string }>;
      };
      set({ disponibilite: corps.video ?? null });
    } catch (e) {
      // Ne rien savoir reste `null` — mais le panneau, lui, doit apprendre que
      // le serveur n'a pas repondu. Sans ca, la page video restait vide sur un
      // panneau vert (mesure du 04/09/2026).
      signalerSiPanne(e, true);
      set({ disponibilite: null });
    }
  },
  references: [],

  /* Envoie chaque fichier a POST /api/upload (le meme point d'entree que la
     pipeline /api/process-video) et garde son chemin MEDIA_DIR une fois pret.
     Un echec reste local a ce fichier — les autres continuent. */
  async addReferenceFiles(files) {
    const cfg = activeRemoteCfg();
    const liste = Array.from(files);
    if (!cfg || !liste.length) return;

    const attentes: ReferenceFile[] = liste.map((f) => ({
      id: idReference(), name: f.name, path: null, status: 'uploading' as const,
    }));
    set((s) => ({ references: [...s.references, ...attentes] }));

    await Promise.all(liste.map(async (file, i) => {
      const attente = attentes[i];
      try {
        const form = new FormData();
        form.append('file', file);
        const res = await fetch(`${cfg.url}/api/upload`, {
          method: 'POST',
          headers: cfg.apiKey ? { Authorization: `Bearer ${cfg.apiKey}` } : {},
          body: form,
        });
        if (!res.ok) {
          // **Un refus n'est pas une panne de liaison.** Il etait jete dans le
          // meme `catch` que les erreurs reseau : impossible d'y distinguer
          // « le serveur a dit non » de « le serveur n'a pas repondu ». On le
          // traite ici, et le `catch` ne garde que le reseau.
          const detail = await res.json().catch(() => null);
          const raison = (detail && detail.detail) || `HTTP ${res.status}`;
          set((s) => ({
            references: s.references.map((r) =>
              r.id === attente.id ? { ...r, status: 'failed' as const, error: raison } : r),
          }));
          return;
        }
        const data = (await res.json()) as { path: string };
        set((s) => ({
          references: s.references.map((r) =>
            r.id === attente.id ? { ...r, path: data.path, status: 'ready' as const } : r),
        }));
      } catch (e) {
        signalerSiPanne(e, true);
        set((s) => ({
          references: s.references.map((r) =>
            r.id === attente.id
              ? { ...r, status: 'failed' as const, error: e instanceof Error ? e.message : String(e) }
              : r),
        }));
      }
    }));
  },

  removeReference: (id) => set((s) => ({ references: s.references.filter((r) => r.id !== id) })),

  submitting: false,
  result: null,
  error: null,

  async submit() {
    const cfg = activeRemoteCfg();
    const { objectif, capacitesChoisies, references } = get();
    if (!cfg) {
      set({ error: 'no-backend' });
      return;
    }
    if (!objectif.trim()) return;

    set({ submitting: true, error: null, result: null });
    try {
      const body: Record<string, unknown> = { objectif: objectif.trim() };
      if (capacitesChoisies.size > 0) body.capacites = Array.from(capacitesChoisies);
      const pretes = references.filter((r) => r.status === 'ready' && r.path);
      if (pretes.length) body.references = pretes.map((r) => r.path);

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
      signalerSiPanne(e, true);
      set({ error: e instanceof Error ? e.message : 'network-error', submitting: false });
    }
  },

  reset: () => set({ objectif: '', capacitesChoisies: new Set(), references: [], result: null, error: null }),
}));
