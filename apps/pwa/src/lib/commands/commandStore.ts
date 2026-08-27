/* ─────────────────────────────────────────────────────────────
   Command Palette Store & Action Dispatcher
   ───────────────────────────────────────────────────────────── */

import { create } from 'zustand';

interface CommandPaletteState {
  isOpen: boolean;
  search: string;
  setIsOpen: (open: boolean) => void;
  openPalette: () => void;
  closePalette: () => void;
  togglePalette: () => void;
  setSearch: (search: string) => void;
}

export const useCommandPalette = create<CommandPaletteState>((set) => ({
  isOpen: false,
  search: '',
  setIsOpen: (isOpen) => set({ isOpen, search: '' }),
  openPalette: () => set({ isOpen: true, search: '' }),
  closePalette: () => set({ isOpen: false, search: '' }),
  togglePalette: () => set((s) => ({ isOpen: !s.isOpen, search: '' })),
  setSearch: (search) => set({ search }),
}));
