/* ─────────────────────────────────────────────────────────────
   Export Modal State Store
   ───────────────────────────────────────────────────────────── */

import { create } from 'zustand';

interface ExportState {
  isOpen: boolean;
  setIsOpen: (open: boolean) => void;
  openExport: () => void;
  closeExport: () => void;
}

export const useExport = create<ExportState>((set) => ({
  isOpen: false,
  setIsOpen: (isOpen) => set({ isOpen }),
  openExport: () => set({ isOpen: true }),
  closeExport: () => set({ isOpen: false }),
}));
