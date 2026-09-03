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
  /** L'adresse de repli, essayee quand la premiere ne repond pas. */
  urlSecours: string;
  apiKeySecours: string;
  /** Laquelle des deux a repondu au dernier essai. `null` = aucune. */
  serveurActif: 'principal' | 'secours' | null;
  enabled: boolean;
  status: BackendStatus;
  latencyMs?: number;
  remoteName?: string;
  remoteProvider?: string;
  remoteModel?: string;
  error?: string;
  setUrl(url: string): void;
  setApiKey(key: string): void;
  setUrlSecours(url: string): void;
  setApiKeySecours(key: string): void;
  setEnabled(on: boolean): void;
  test(): Promise<boolean>;
  disconnect(): void;
}

type Enregistre = {
  url: string; apiKey: string; enabled: boolean;
  urlSecours: string; apiKeySecours: string;
};


function load(): Enregistre {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) {
      const p = JSON.parse(raw) as {
        url?: string; apiKey?: string; enabled?: boolean; debrancheParLui?: boolean;
        urlSecours?: string; apiKeySecours?: string;
      };
      const url = p.url ?? '';

      // **Une adresse enregistree et debranchee SANS marque vient du defaut,
      // pas de lui.** Jusqu'au 03/09/2026 une seule sonde ratee ecrivait
      // `enabled: false` ici ; la coupure survivait aux redemarrages et il
      // fallait rouvrir le panneau pour rebrancher. Cet etat-la dort encore
      // sur son telephone, et rien ne l'effacerait tout seul — lui demander
      // d'aller le corriger, c'est lui faire reparer le bug.
      //
      // `debrancheParLui` n'est ecrit que par le bouton « Deconnecter ». Son
      // absence, avec une adresse presente, veut donc dire : personne n'a
      // choisi cette coupure. On rebranche, et la sonde du demarrage tranche.
      const secours = {
        urlSecours: p.urlSecours ?? '',
        apiKeySecours: p.apiKeySecours ?? '',
      };
      if (url && !p.enabled && !p.debrancheParLui) {
        return { url, apiKey: p.apiKey ?? '', enabled: true, ...secours };
      }
      return { url, apiKey: p.apiKey ?? '', enabled: !!p.enabled, ...secours };
    }
  } catch { /* ignore */ }
  return { url: '', apiKey: '', enabled: false, urlSecours: '', apiKeySecours: '' };
}

function persist(
  s: Pick<BackendState, 'url' | 'apiKey' | 'enabled' | 'urlSecours' | 'apiKeySecours'>,
  debrancheParLui = false,
) {
  try {
    localStorage.setItem(KEY, JSON.stringify({
      url: s.url, apiKey: s.apiKey, enabled: s.enabled, debrancheParLui,
      urlSecours: s.urlSecours, apiKeySecours: s.apiKeySecours,
    }));
  } catch { /* ignore */ }
}

export const useBackend = create<BackendState>((set, get) => ({
  ...load(),
  status: 'local',
  serveurActif: null,

  setUrlSecours: (urlSecours) => {
    set({ urlSecours });
    persist({ ...get(), urlSecours });
  },
  setApiKeySecours: (apiKeySecours) => {
    set({ apiKeySecours });
    persist({ ...get(), apiKeySecours });
  },

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
    persist({ ...get(), enabled }, !enabled);
  },

  async test() {
    const etat = get();
    if (!etat.url.trim() && !etat.urlSecours.trim()) {
      set({ status: 'error', error: 'empty URL' });
      return false;
    }
    set({ status: 'checking', error: undefined });

    /** Un serveur, reessaye. Rend son etat sans rien enregistrer. */
    const sonder = async (cfg: RemoteConfig) => {
      let dernier: { latencyMs?: number; error?: string } = {};
      for (let essai = 0; essai < ATTENTES.length + 1; essai += 1) {
        try {
          const r = await pingBackend(cfg);
          if (r.ok) return { ok: true as const, r };
          dernier = { latencyMs: r.latencyMs, error: r.error ?? 'Provider probe failed' };
        } catch (err) {
          dernier = { error: err instanceof Error ? err.message : String(err) };
        }
        if (essai < ATTENTES.length) await patienter(ATTENTES[essai]);
      }
      return { ok: false as const, dernier };
    };

    // **Le principal d'abord, toujours.** C'est sa machine : le modele y
    // tourne chez lui et rien ne part chez un tiers (DEC-0002). Le secours
    // n'est essaye que quand le principal ne repond pas, jamais en parallele
    // — sinon un message pourrait partir dehors alors que son PC etait juste
    // lent a repondre.
    const candidats: Array<{ cfg: RemoteConfig; quel: 'principal' | 'secours' }> = [];
    if (etat.url.trim()) {
      candidats.push({
        cfg: { url: etat.url.trim(), apiKey: etat.apiKey.trim() || undefined },
        quel: 'principal',
      });
    }
    if (etat.urlSecours.trim()) {
      candidats.push({
        cfg: { url: etat.urlSecours.trim(), apiKey: etat.apiKeySecours.trim() || undefined },
        quel: 'secours',
      });
    }

    let dernier: { latencyMs?: number; error?: string } = {};
    for (const { cfg, quel } of candidats) {
      const issue = await sonder(cfg);
      if (issue.ok) {
        set({
          status: 'online',
          latencyMs: issue.r.latencyMs,
          remoteName: issue.r.name,
          remoteProvider: issue.r.provider,
          remoteModel: issue.r.model,
          enabled: true,
          serveurActif: quel,
          error: undefined,
        });
        persist({ ...get(), enabled: true });
        return true;
      }
      dernier = issue.dernier;
    }

    // Echec apres toutes les tentatives, sur les deux adresses.
    // **`enabled` ne bouge pas.** Il dit ce que le proprietaire veut, pas ce
    // que le reseau permet a cet instant ; seul le bouton « Deconnecter » le
    // change. L'etat, lui, dit la verite du moment.
    set({
      status: 'error', latencyMs: dernier.latencyMs, error: dernier.error,
      serveurActif: null,
    });
    return false;
  },

  disconnect: () => {
    // Signee : c'est ce qui la distingue d'une coupure subie, et ce qui la
    // fait tenir au prochain demarrage.
    set({ enabled: false, status: 'local', error: undefined });
    persist({ ...get(), enabled: false }, true);
  },
}));

/** effective config used by the chat layer */
export function activeRemoteCfg(): RemoteConfig | null {
  const { enabled, url, apiKey, urlSecours, apiKeySecours, serveurActif } =
    useBackend.getState();
  if (!enabled) return null;

  // Celui qui a REPONDU a la derniere sonde, pas celui qu'on prefere. Rendre
  // le principal alors que c'est le secours qui repond enverrait chaque
  // message dans le vide (mesure du 03/09/2026 : une seule adresse etait
  // retenue, et son PC eteint coupait tout jusqu'a ce qu'il recolle
  // l'adresse a la main).
  if (serveurActif === 'secours' && urlSecours.trim()) {
    return { url: urlSecours.trim(), apiKey: apiKeySecours.trim() || undefined };
  }
  if (url.trim()) return { url: url.trim(), apiKey: apiKey.trim() || undefined };
  if (urlSecours.trim()) {
    return { url: urlSecours.trim(), apiKey: apiKeySecours.trim() || undefined };
  }
  return null;
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

/**
 * Tant que le serveur est branche mais muet, on continue de frapper.
 *
 * **Cette veille est ce qui rend vraie la phrase montree dans le chat.**
 * Le message dit « il est reessaye tout seul » ; sans ce qui suit, ce serait
 * une promesse de plus — exactement le defaut qu'on vient de retirer de
 * l'ecran d'accueil. Une phrase et le code qui la tient s'ecrivent ensemble.
 *
 * L'evenement `online` ne couvre que le reseau du telephone. Il ne dit rien
 * d'un serveur qui redemarre, d'un tunnel qui se rendort ou d'un hebergeur
 * qui met deux minutes a repondre — les cas reels ici.
 *
 * L'attente s'allonge jusqu'a une minute : assez pour rattraper vite une
 * panne courte, assez peu pour ne pas marteler une adresse morte toute la
 * nuit sur sa batterie.
 */
const VEILLE_MIN = 15_000;
const VEILLE_MAX = 60_000;
let attente = VEILLE_MIN;
let veille: ReturnType<typeof setTimeout> | null = null;

function programmerVeille() {
  if (veille) return;
  veille = setTimeout(async () => {
    veille = null;
    const { enabled, url, status } = useBackend.getState();
    if (!enabled || !url.trim()) return;
    if (status === 'error') {
      const ok = await useBackend.getState().test();
      attente = ok ? VEILLE_MIN : Math.min(attente * 2, VEILLE_MAX);
    }
    if (useBackend.getState().status === 'error') programmerVeille();
  }, attente);
}

if (typeof window !== 'undefined') {
  useBackend.subscribe((etat, precedent) => {
    if (etat.status === 'error' && precedent.status !== 'error') {
      attente = VEILLE_MIN;
      programmerVeille();
    }
  });
}
