/* ─────────────────────────────────────────────────────────────
   Usman Theming Engine
   · Accent Colors (Ember, Violet, Azure, Emerald, Rose, Amber, Cyan)
   · Color Mode: Dark, Light, System
   · Haptic & Tactile Feedback (navigator.vibrate)
   · Smooth runtime variable injection
   ───────────────────────────────────────────────────────────── */

import { create } from 'zustand';

export type ColorMode = 'dark' | 'light' | 'system';

export interface Accent {
  id: string;
  label: string;
  labelFr: string;
  c300: string;
  c400: string;
  c500: string;
  c600: string;
  glow: string;
  swatch: string;
}

export const ACCENTS: Accent[] = [
  { id: 'ember', label: 'Ember', labelFr: 'Braise', c300: '#f2a489', c400: '#e9906f', c500: '#e07856', c600: '#c85f40', glow: 'rgba(224,120,86,0.35)', swatch: '#e07856' },
  { id: 'violet', label: 'Violet', labelFr: 'Violet', c300: '#c4b0f5', c400: '#a98df0', c500: '#8f6ae8', c600: '#7450c9', glow: 'rgba(143,106,232,0.35)', swatch: '#8f6ae8' },
  { id: 'azure', label: 'Azure', labelFr: 'Azur', c300: '#8ec8f6', c400: '#63aef0', c500: '#3f92e6', c600: '#2d76c4', glow: 'rgba(63,146,230,0.35)', swatch: '#3f92e6' },
  { id: 'emerald', label: 'Emerald', labelFr: 'Émeraude', c300: '#7fe0b5', c400: '#4fd39c', c500: '#2bbd85', c600: '#1f9c6d', glow: 'rgba(43,189,133,0.35)', swatch: '#2bbd85' },
  { id: 'rose', label: 'Rose', labelFr: 'Rose', c300: '#f5a8bd', c400: '#ef83a1', c500: '#e45f86', c600: '#c2486c', glow: 'rgba(228,95,134,0.35)', swatch: '#e45f86' },
  { id: 'amber', label: 'Amber', labelFr: 'Ambre', c300: '#f2d089', c400: '#eac061', c500: '#ddab3c', c600: '#bd8d28', glow: 'rgba(221,171,60,0.35)', swatch: '#ddab3c' },
  { id: 'cyan', label: 'Cyan', labelFr: 'Cyan', c300: '#7fdceb', c400: '#4ecbdd', c500: '#2ab3c9', c600: '#1d91a6', glow: 'rgba(42,179,201,0.35)', swatch: '#2ab3c9' },
];

const ACCENT_KEY = 'usman.accent.v1';
const COLOR_MODE_KEY = 'usman.colormode.v1';

function applyAccent(a: Accent) {
  const r = document.documentElement.style;
  r.setProperty('--color-accent-300', a.c300);
  r.setProperty('--color-accent-400', a.c400);
  r.setProperty('--color-accent-500', a.c500);
  r.setProperty('--color-accent-600', a.c600);
  r.setProperty('--glow', a.glow);
}

function resolveEffectiveMode(mode: ColorMode): 'dark' | 'light' {
  if (mode === 'system') {
    return typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: light)').matches
      ? 'light'
      : 'dark';
  }
  return mode;
}

function applyColorMode(mode: ColorMode) {
  const effective = resolveEffectiveMode(mode);
  const root = document.documentElement;
  root.dataset.colorMode = mode;
  root.dataset.theme = effective;

  if (effective === 'light') {
    root.classList.add('light-mode');
    root.classList.remove('dark-mode');
  } else {
    root.classList.add('dark-mode');
    root.classList.remove('light-mode');
  }
}

function initialAccent(): Accent {
  try {
    const saved = localStorage.getItem(ACCENT_KEY);
    const found = ACCENTS.find((a) => a.id === saved);
    if (found) return found;
  } catch {
    /* ignore */
  }
  return ACCENTS[0];
}

function initialColorMode(): ColorMode {
  try {
    const saved = localStorage.getItem(COLOR_MODE_KEY) as ColorMode;
    if (saved === 'dark' || saved === 'light' || saved === 'system') return saved;
  } catch {
    /* ignore */
  }
  return 'dark';
}

interface ThemeState {
  accent: Accent;
  colorMode: ColorMode;
  effectiveColorMode: 'dark' | 'light';
  hapticsEnabled: boolean;
  setAccent(id: string): void;
  setColorMode(mode: ColorMode): void;
  toggleColorMode(): void;
  setHapticsEnabled(enabled: boolean): void;
}

export const useTheme = create<ThemeState>((set, get) => ({
  accent: initialAccent(),
  colorMode: initialColorMode(),
  effectiveColorMode: resolveEffectiveMode(initialColorMode()),
  hapticsEnabled: true,

  setAccent: (id) => {
    const accent = ACCENTS.find((a) => a.id === id) ?? ACCENTS[0];
    try {
      localStorage.setItem(ACCENT_KEY, accent.id);
    } catch {
      /* ignore */
    }
    applyAccent(accent);
    set({ accent });
  },

  setColorMode: (mode) => {
    try {
      localStorage.setItem(COLOR_MODE_KEY, mode);
    } catch {
      /* ignore */
    }
    applyColorMode(mode);
    set({
      colorMode: mode,
      effectiveColorMode: resolveEffectiveMode(mode),
    });
  },

  toggleColorMode: () => {
    const current = get().colorMode;
    const next: ColorMode = current === 'dark' ? 'light' : current === 'light' ? 'system' : 'dark';
    get().setColorMode(next);
  },

  setHapticsEnabled: (hapticsEnabled) => set({ hapticsEnabled }),
}));

/**
 * Trigger subtle haptic tactile feedback on mobile devices
 */
export function triggerHaptic(type: 'light' | 'medium' | 'success' | 'warning' = 'light') {
  if (typeof navigator === 'undefined' || !('vibrate' in navigator)) return;
  if (!useTheme.getState().hapticsEnabled) return;

  try {
    switch (type) {
      case 'light':
        navigator.vibrate(10);
        break;
      case 'medium':
        navigator.vibrate(25);
        break;
      case 'success':
        navigator.vibrate([15, 40, 15]);
        break;
      case 'warning':
        navigator.vibrate([40, 30, 40]);
        break;
    }
  } catch {
    /* ignore unsupported vibration calls */
  }
}

// Initial setup
const initAcc = initialAccent();
const initMode = initialColorMode();
applyAccent(initAcc);
applyColorMode(initMode);

// Listen to system color scheme changes
if (typeof window !== 'undefined') {
  window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', () => {
    if (useTheme.getState().colorMode === 'system') {
      applyColorMode('system');
      useTheme.setState({ effectiveColorMode: resolveEffectiveMode('system') });
    }
  });
}
