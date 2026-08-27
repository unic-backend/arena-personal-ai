/* ─────────────────────────────────────────────────────────────
   Usman Personal Memory Store
   · Transparent, inspectable, and editable long-term memory.
   · Categorized facts, user preferences, project details.
   · Injected into AI requests; user can edit/delete any memory.
   ───────────────────────────────────────────────────────────── */

import { create } from 'zustand';

export type MemoryCategory = 'preference' | 'project' | 'fact' | 'instruction';

export interface MemoryItem {
  id: string;
  category: MemoryCategory;
  content: string;
  enabled: boolean;
  source?: string;
  createdAt: number;
  updatedAt: number;
}

const MEMORY_STORAGE_KEY = 'usman.memory.v1';

const SEED_MEMORIES: MemoryItem[] = [
  {
    id: 'mem_1',
    category: 'preference',
    content: 'Préfère des explications directes avec du code propre et commenté.',
    enabled: true,
    source: 'system',
    createdAt: Date.now() - 86400000 * 2,
    updatedAt: Date.now() - 86400000 * 2,
  },
  {
    id: 'mem_2',
    category: 'project',
    content: 'Travaille sur des projets Web modernes avec React 19, TypeScript strict et Tailwind CSS.',
    enabled: true,
    source: 'system',
    createdAt: Date.now() - 86400000,
    updatedAt: Date.now() - 86400000,
  },
];

function loadMemories(): MemoryItem[] {
  try {
    const raw = localStorage.getItem(MEMORY_STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) return parsed;
    }
  } catch {
    /* ignore */
  }
  return SEED_MEMORIES;
}

function persistMemories(items: MemoryItem[]) {
  try {
    localStorage.setItem(MEMORY_STORAGE_KEY, JSON.stringify(items));
  } catch {
    /* ignore */
  }
}

function uid() {
  return `mem_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 7)}`;
}

interface MemoryState {
  memories: MemoryItem[];
  modalOpen: boolean;
  setModalOpen: (open: boolean) => void;
  addMemory: (content: string, category?: MemoryCategory) => void;
  updateMemory: (id: string, content: string, category?: MemoryCategory) => void;
  toggleMemory: (id: string) => void;
  deleteMemory: (id: string) => void;
  clearAllMemories: () => void;
  resetToDefaults: () => void;
}

export const useMemory = create<MemoryState>((set, get) => ({
  memories: loadMemories(),
  modalOpen: false,

  setModalOpen: (modalOpen) => set({ modalOpen }),

  addMemory: (content, category = 'preference') => {
    const trimmed = content.trim();
    if (!trimmed) return;
    const newItem: MemoryItem = {
      id: uid(),
      category,
      content: trimmed,
      enabled: true,
      source: 'user',
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };
    const updated = [newItem, ...get().memories];
    persistMemories(updated);
    set({ memories: updated });
  },

  updateMemory: (id, content, category) => {
    const trimmed = content.trim();
    if (!trimmed) return;
    const updated = get().memories.map((m) =>
      m.id === id
        ? {
            ...m,
            content: trimmed,
            category: category ?? m.category,
            updatedAt: Date.now(),
          }
        : m,
    );
    persistMemories(updated);
    set({ memories: updated });
  },

  toggleMemory: (id) => {
    const updated = get().memories.map((m) =>
      m.id === id ? { ...m, enabled: !m.enabled, updatedAt: Date.now() } : m,
    );
    persistMemories(updated);
    set({ memories: updated });
  },

  deleteMemory: (id) => {
    const updated = get().memories.filter((m) => m.id !== id);
    persistMemories(updated);
    set({ memories: updated });
  },

  clearAllMemories: () => {
    persistMemories([]);
    set({ memories: [] });
  },

  resetToDefaults: () => {
    persistMemories(SEED_MEMORIES);
    set({ memories: SEED_MEMORIES });
  },
}));

/**
 * Returns formatted string of active memories for prompt context
 */
export function buildMemoryPromptContext(): string {
  const active = useMemory.getState().memories.filter((m) => m.enabled && m.content.trim());
  if (!active.length) return '';

  const lines = ['[Usman Long-Term Memory & User Facts]'];
  active.forEach((m) => {
    lines.push(`- [${m.category.toUpperCase()}] ${m.content.trim()}`);
  });
  return lines.join('\n');
}

/**
 * Returns active memories array for API payloads
 */
export function getActiveMemoriesPayload(): Array<{ id: string; category: string; content: string }> {
  return useMemory
    .getState()
    .memories.filter((m) => m.enabled && m.content.trim())
    .map((m) => ({ id: m.id, category: m.category, content: m.content.trim() }));
}
