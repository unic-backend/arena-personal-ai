/* ─────────────────────────────────────────────────────────────
   Backend connection store — where "your AI" lives.
   Local runtime by default; flip to a remote API whenever your
   backend is ready. Persisted across sessions.
   ───────────────────────────────────────────────────────────── */

import { create } from 'zustand';
import { pingBackend, RemoteConfig } from '../activity/remoteTransport';

const KEY = 'usman.backend.v1';

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
      set({ status: 'error', latencyMs: r.latencyMs, error: r.error ?? 'Provider probe failed', enabled: false });
      persist({ url: cfg.url, apiKey: cfg.apiKey ?? '', enabled: false });
      return false;
    } catch (err) {
      set({ status: 'error', error: err instanceof Error ? err.message : String(err), enabled: false });
      persist({ url: cfg.url, apiKey: cfg.apiKey ?? '', enabled: false });
      return false;
    }
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
