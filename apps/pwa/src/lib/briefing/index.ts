/* Le briefing du matin vient a lui (DEC-0168).
 *
 * Le serveur compose le briefing chaque jour a `BRIEFING_HEURE` (DEC-0166),
 * mais personne ne le voyait tant qu'il ne le demandait pas : « chaque matin,
 * ARENA te resume seul » n'etait vrai qu'a moitie.
 *
 * A l'ouverture, l'application demande seulement s'il y en a un de PRET
 * (`seulement_pret=true`) — jamais d'en composer un, ce qui lancerait quatre
 * recherches parce qu'on a ouvert l'ecran. Une fois ferme, il ne revient pas
 * avant le lendemain.
 */
import { activeRemoteCfg, signalerSiPanne } from '../store/backendStore';
import { adresseDuServeur } from '../activity/remoteTransport';

export type EtatRubrique = 'OK' | 'NON_CONFIGURE' | 'INDISPONIBLE' | 'INCONNU';

export interface RubriqueBriefing {
  titre: string;
  etat: EtatRubrique;
  texte: string;
}

export interface BriefingDuJour {
  /** « 2026-09-29 » : le jour qu'il resume. */
  jour: string;
  /** « 2026-09-29T07:00 » : quand il a ete compose. */
  composeA: string;
  rubriques: RubriqueBriefing[];
  /** Le texte complet, tel qu'il se lit a voix haute. */
  texte: string;
}

const ETATS: readonly EtatRubrique[] = ['OK', 'NON_CONFIGURE', 'INDISPONIBLE', 'INCONNU'];
const CLE_VU = 'usman.briefing.vu';

/** La reponse du serveur, verifiee. `null` quand rien n'est pret ou que la
 *  forme est inattendue : on n'affiche jamais un briefing a moitie lu. */
export function briefingDepuis(corps: unknown): BriefingDuJour | null {
  if (!corps || typeof corps !== 'object') return null;
  const c = corps as Record<string, unknown>;
  if (c.pret !== true || typeof c.jour !== 'string' || !Array.isArray(c.rubriques)) return null;
  const rubriques: RubriqueBriefing[] = [];
  for (const r of c.rubriques) {
    if (!r || typeof r !== 'object') return null;
    const { titre, etat, texte } = r as Record<string, unknown>;
    if (typeof titre !== 'string' || typeof texte !== 'string') return null;
    if (!ETATS.includes(etat as EtatRubrique)) return null;
    rubriques.push({ titre, etat: etat as EtatRubrique, texte });
  }
  return {
    jour: c.jour,
    composeA: typeof c.compose_a === 'string' ? c.compose_a : '',
    rubriques,
    texte: typeof c.texte === 'string' ? c.texte : '',
  };
}

/** « 07:00 », lu dans l'horodatage du serveur — sans fuseau ni locale. */
export function heureDeComposition(composeA: string): string {
  const m = /T(\d{2}:\d{2})/.exec(composeA);
  return m ? m[1] : '';
}

function lireVu(): string | null {
  try {
    return localStorage.getItem(CLE_VU);
  } catch {
    return null;
  }
}

/** Deja ferme aujourd'hui ? Un stockage illisible compte comme « pas vu » :
 *  mieux vaut le montrer deux fois que jamais. */
export function dejaVu(jour: string): boolean {
  return lireVu() === jour;
}

export function marquerVu(jour: string): void {
  try {
    localStorage.setItem(CLE_VU, jour);
  } catch {
    /* navigation privee : il reviendra a la prochaine ouverture, sans plus */
  }
}

/** Le briefing pret aujourd'hui et pas encore ferme, ou `null`. Aucun message
 *  d'erreur a l'ecran — c'est une attention, pas une fonction qu'on a
 *  demandee — mais le panneau apprend la panne, comme partout ailleurs. */
export async function briefingAMontrer(): Promise<BriefingDuJour | null> {
  const cfg = activeRemoteCfg();
  if (!cfg) return null;
  try {
    const res = await fetch(`${adresseDuServeur(cfg.url)}/api/briefing?seulement_pret=true`, {
      headers: cfg.apiKey ? { Authorization: `Bearer ${cfg.apiKey}` } : {},
    });
    if (!res.ok) return null;
    const briefing = briefingDepuis(await res.json().catch(() => null));
    if (!briefing || dejaVu(briefing.jour)) return null;
    return briefing;
  } catch (err) {
    signalerSiPanne(err, true);
    return null;
  }
}
