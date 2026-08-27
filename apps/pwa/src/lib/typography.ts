/* Persistent reading/writing preferences for the personal workspace. */
import { create } from 'zustand';

export type FontFamily = 'sans' | 'serif' | 'mono';
export type TextSize = 'compact' | 'comfortable' | 'large';
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
const DEFAULTS = {
  family: 'sans' as FontFamily,
  size: 'comfortable' as TextSize,
  weight: 'regular' as TextWeight,
  relaxed: true,
};

function load(): typeof DEFAULTS {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return { ...DEFAULTS, ...JSON.parse(raw) };
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
