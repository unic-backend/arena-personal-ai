/* Persistent reading/writing preferences for the personal workspace. */
import { create } from 'zustand';

export type FontFamily = 'sans' | 'serif' | 'mono';
export type TextSize = 'compact' | 'comfortable' | 'large' | 'xlarge';
export type TextWeight = 'regular' | 'medium' | 'bold';

interface TypographyState {
  family: FontFamily;
  size: TextSize;
  weight: TextWeight;
  relaxed: boolean;
  setFamily(family: FontFamily): void;
  setSize(size: TextSize): void;
  setWeight(weight: TextWeight): void;
  setRelaxed(relaxed: boolean): void;
  reset(): void;
}

const KEY = 'usman.typography.v1';

/* Defauts releves le 19/09/2026 : « je veux comme celle de Claude, un peu
   grand, texte gras aussi ». Le corps passe de 400 a 500 ; la taille suit
   l'echelle relevee dans `index.css` (`comfortable` vaut desormais 17 px, pas
   13). */
const DEFAULTS = {
  family: 'sans' as FontFamily,
  size: 'comfortable' as TextSize,
  weight: 'medium' as TextWeight,
  relaxed: true,
};

/* Ce que valaient les defauts AVANT ce changement.

   Sa preference est deja enregistree sur son telephone, et elle vaut
   exactement ces valeurs-la — parce qu'il n'a jamais ouvert le panneau, pas
   parce qu'il a choisi « regular ». Relever les defauts sans ceci n'aurait
   donc rien change pour lui : le seul ecran qui compte aurait garde l'ancien
   reglage.

   On ne remplace QUE cette combinaison exacte. Un reglage choisi — meme un
   seul cran deplace — n'est pas touche : le sien est une preference, pas un
   defaut a rattraper. */
const ANCIENS_DEFAUTS = {
  family: 'sans',
  size: 'comfortable',
  weight: 'regular',
  relaxed: true,
};

function jamaisChoisi(value: typeof DEFAULTS): boolean {
  return (Object.keys(ANCIENS_DEFAUTS) as Array<keyof typeof ANCIENS_DEFAUTS>)
    .every((cle) => value[cle] === ANCIENS_DEFAUTS[cle]);
}

function load(): typeof DEFAULTS {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) {
      const enregistre = { ...DEFAULTS, ...JSON.parse(raw) } as typeof DEFAULTS;
      return jamaisChoisi(enregistre) ? DEFAULTS : enregistre;
    }
  } catch { /* ignore invalid preferences */ }
  return DEFAULTS;
}

function persist(value: typeof DEFAULTS) {
  try { localStorage.setItem(KEY, JSON.stringify(value)); } catch { /* ignore */ }
}

function apply(value: typeof DEFAULTS) {
  const root = document.documentElement;
  root.dataset.readingFont = value.family;
  root.dataset.readingSize = value.size;
  root.dataset.readingWeight = value.weight;
  root.dataset.readingLeading = value.relaxed ? 'relaxed' : 'normal';
}

const initial = load();
apply(initial);

export const useTypography = create<TypographyState>((set, get) => {
  const patch = (next: Partial<typeof DEFAULTS>) => {
    const value = {
      family: next.family ?? get().family,
      size: next.size ?? get().size,
      weight: next.weight ?? get().weight,
      relaxed: next.relaxed ?? get().relaxed,
    };
    apply(value);
    persist(value);
    set(value);
  };

  return {
    ...initial,
    setFamily: (family) => patch({ family }),
    setSize: (size) => patch({ size }),
    setWeight: (weight) => patch({ weight }),
    setRelaxed: (relaxed) => patch({ relaxed }),
    reset: () => patch(DEFAULTS),
  };
});
