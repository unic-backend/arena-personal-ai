/* ─────────────────────────────────────────────────────────────
   Les salutations de l'écran d'accueil — plusieurs langues du
   Sénégal et d'ailleurs, selon le moment de la journée.

   Demandé par le propriétaire le 02/09/2026 : wolof, sérère, diola,
   peul, anglais, français, espagnol — et le moment (matin,
   après-midi, soir) plutôt qu'une seule langue fixe.

   Une langue est tirée au hasard à l'ouverture de l'application
   (une seule fois, pas à chaque re-rendu) : au fil des jours, le
   propriétaire voit tour à tour ses langues, plutôt qu'une case à
   choisir dans un réglage — c'est un geste, pas une préférence.

   Honnêteté sur ce qui suit : le wolof, le peul et le diola
   viennent de formules de salutation largement documentées ; je ne
   suis pas locuteur natif. Si l'une d'elles sonne faux, il suffit
   de corriger la ligne — c'est écrit pour ça. Le sérère est
   volontairement absent : je n'ai pas de formule fiable, plutôt que
   d'en inventer une.
   ───────────────────────────────────────────────────────────── */

export type MomentDeLaJournee = 'matin' | 'apres-midi' | 'soir';

interface TroisSalutations {
  matin: string;
  'apres-midi': string;
  soir: string;
}

/**
 * Une entrée par langue. Le diola garde la même formule aux trois
 * moments : « Kasumay » (paix) s'emploie à toute heure — lui inventer
 * des variantes matin/soir serait moins juste que de le répéter.
 */
const SALUTATIONS: Record<string, TroisSalutations> = {
  fr: { matin: 'Bonjour', 'apres-midi': 'Bonjour', soir: 'Bonsoir' },
  en: { matin: 'Good morning', 'apres-midi': 'Good afternoon', soir: 'Good evening' },
  es: { matin: 'Buenos días', 'apres-midi': 'Buenas tardes', soir: 'Buenas noches' },
  // Wolof : « as-tu passé la nuit/la journée/la soirée en paix ? »
  wo: { matin: 'Jamm nga fanaan', 'apres-midi': 'Jamm nga yendoo', soir: 'Jamm nga guddi' },
  // Peul / Pulaar : même schéma, « jam » (paix) + le moment.
  ff: { matin: 'Jam waali', 'apres-midi': 'Jam ñalli', soir: 'Jam hiiri' },
  // Diola : la salutation emblématique de la Casamance, à toute heure.
  dyo: { matin: 'Kasumay', 'apres-midi': 'Kasumay', soir: 'Kasumay' },
};

const LANGUES = Object.keys(SALUTATIONS);

/** Matin 5h–12h, après-midi 12h–18h, soir 18h–5h (la nuit y reste incluse). */
export function momentDeLaJournee(heure: number): MomentDeLaJournee {
  if (heure >= 5 && heure < 12) return 'matin';
  if (heure >= 12 && heure < 18) return 'apres-midi';
  return 'soir';
}

/** Tire une langue au hasard et rend sa salutation pour l'heure donnée. */
export function salutationAuHasard(heure: number): string {
  const langue = LANGUES[Math.floor(Math.random() * LANGUES.length)];
  return SALUTATIONS[langue][momentDeLaJournee(heure)];
}
