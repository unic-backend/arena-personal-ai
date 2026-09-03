/* ─────────────────────────────────────────────────────────────
   Backend connection store — where "your AI" lives.
   Local runtime by default; flip to a remote API whenever your
   backend is ready. Persisted across sessions.
   ───────────────────────────────────────────────────────────── */

import { create } from 'zustand';
import { pingBackend, RemoteConfig } from '../activity/remoteTransport';

const KEY = 'usman.backend.v1';

/**
 * Attentes entre deux tentatives de sonde, en millisecondes.
 *
 * **Mesure du 03/09/2026 :** une seule sonde ratee coupait le serveur, et la
 * coupure etait enregistree — il fallait le rebrancher a la main. Un tunnel
 * qui se rendort, un telephone qui change d'antenne, et son IA devenait
 * injoignable jusqu'a ce qu'il ouvre le panneau.
 *
 * Trois tentatives, espacees : de quoi traverser une coupure passagere sans
 * transformer un hoquet en deconnexion.
 */
const ATTENTES = [800, 2500] as const;

const patienter = (ms: number) => new Promise((r) => setTimeout(r, ms));

export type BackendStatus = 'local' | 'checking' | 'online' | 'error';

interface BackendState {
  url: string;
  apiKey: string;
  enabled: boolean;
  status: BackendStatus;
  latencyMs?: number;
  remoteName?: string;
  remoteProvider?: string;
  remoteModel?: string;
  error?: string;
  setUrl(url: string): void;
  setApiKey(key: string): void;
  setEnabled(on: boolean): void;
  test(): Promise<boolean>;
  disconnect(): void;
}

function load(): { url: string; apiKey: string; enabled: boolean } {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) {
      const p = JSON.parse(raw) as { url?: string; apiKey?: string; enabled?: boolean };
      return { url: p.url ?? '', apiKey: p.apiKey ?? '', enabled: !!p.enabled };
    }
  } catch { /* ignore */ }
  return { url: '', apiKey: '', enabled: false };
}

function persist(s: Pick<BackendState, 'url' | 'apiKey' | 'enabled'>) {
  try {
    localStorage.setItem(KEY, JSON.stringify({ url: s.url, apiKey: s.apiKey, enabled: s.enabled }));
  } catch { /* ignore */ }
}

export const useBackend = create<BackendState>((set, get) => ({
  ...load(),
  status: 'local',

  setUrl: (url) => {
    set({ url });
    persist({ ...get(), url });
  },
  setApiKey: (apiKey) => {
    set({ apiKey });
    persist({ ...get(), apiKey });
  },
  setEnabled: (enabled) => {
    set({ enabled, status: enabled ? 'online' : 'local', error: undefined });
    persist({ ...get(), enabled });
  },

  async test() {
    const { url, apiKey } = get();
    if (!url.trim()) {
      set({ status: 'error', error: 'empty URL' });
      return false;
    }
    set({ status: 'checking', error: undefined });
    const cfg: RemoteConfig = { url: url.trim(), apiKey: apiKey.trim() || undefined };

    let dernier: { latencyMs?: number; error?: string } = {};
    for (let essai = 0; essai < ATTENTES.length + 1; essai += 1) {
      try {
        const r = await pingBackend(cfg);
        if (r.ok) {
          set({
            status: 'online',
            latencyMs: r.latencyMs,
            remoteName: r.name,
            remoteProvider: r.provider,
            remoteModel: r.model,
            enabled: true,
          });
          persist({ url: cfg.url, apiKey: cfg.apiKey ?? '', enabled: true });
          return true;
        }
        dernier = { latencyMs: r.latencyMs, error: r.error ?? 'Provider probe failed' };
      } catch (err) {
        dernier = { error: err instanceof Error ? err.message : String(err) };
      }
      if (essai < ATTENTES.length) await patienter(ATTENTES[essai]);
    }

    // Echec apres toutes les tentatives. **`enabled` ne bouge pas.**
    // Il dit ce que le proprietaire veut, pas ce que le reseau permet a cet
    // instant ; seul le bouton « Deconnecter » le change. L'etat, lui, dit la
    // verite du moment.
    set({ status: 'error', latencyMs: dernier.latencyMs, error: dernier.error });
    return false;
  },

  disconnect: () => {
    set({ enabled: false, status: 'local', error: undefined });
    persist({ ...get(), enabled: false });
  },
}));

/** effective config used by the chat layer */
export function activeRemoteCfg(): RemoteConfig | null {
  const { enabled, url, apiKey } = useBackend.getState();
  if (!enabled || !url.trim()) return null;
  return { url: url.trim(), apiKey: apiKey.trim() || undefined };
}

/**
 * Le reseau revient : on re-sonde, sans qu'il ait rien a faire.
 *
 * C'est la seconde moitie de la meme reparation. Reessayer trois fois traverse
 * une coupure de quelques secondes ; celle-ci rattrape les autres — un metro,
 * un avion, une nuit sans wifi. Sans elle, l'etat resterait « inaccessible »
 * jusqu'a ce qu'il ouvre le panneau et appuie sur « Re-tester ».
 *
 * Ne fait rien si aucun serveur n'est branche : re-sonder une adresse vide
 * afficherait une erreur a quelqu'un qui n'a jamais demande de serveur.
 */
if (typeof window !== 'undefined') {
  window.addEventListener('online', () => {
    const { enabled, url, status } = useBackend.getState();
    if (enabled && url.trim() && status !== 'checking') void useBackend.getState().test();
  });
}
