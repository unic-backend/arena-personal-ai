/* ─────────────────────────────────────────────────────────────
   Network resilience state for Usman.
   Tracks browser connectivity, SSE retries, and offline mode.
   ───────────────────────────────────────────────────────────── */

import { create } from 'zustand';

interface NetworkState {
  online: boolean;
  reconnecting: boolean;
  retryAttempt: number;
  lastOnlineAt?: number;
  lastOfflineAt?: number;
  setOnline(online: boolean): void;
  setReconnecting(reconnecting: boolean, attempt?: number): void;
}

export const useNetwork = create<NetworkState>((set) => ({
  online: typeof navigator === 'undefined' ? true : navigator.onLine,
  reconnecting: false,
  retryAttempt: 0,
  lastOnlineAt: typeof navigator === 'undefined' || navigator.onLine ? Date.now() : undefined,
  lastOfflineAt: typeof navigator !== 'undefined' && !navigator.onLine ? Date.now() : undefined,

  setOnline: (online) =>
    set({
      online,
      ...(online ? { lastOnlineAt: Date.now() } : { lastOfflineAt: Date.now() }),
    }),

  setReconnecting: (reconnecting, attempt = 0) =>
    set({ reconnecting, retryAttempt: reconnecting ? attempt : 0 }),
}));

if (typeof window !== 'undefined') {
  window.addEventListener('online', () => useNetwork.getState().setOnline(true));
  window.addEventListener('offline', () => useNetwork.getState().setOnline(false));
}

export function waitForOnline(signal: AbortSignal): Promise<void> {
  if (typeof navigator === 'undefined' || navigator.onLine) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const cleanup = () => {
      window.removeEventListener('online', onOnline);
      signal.removeEventListener('abort', onAbort);
    };
    const onOnline = () => {
      cleanup();
      resolve();
    };
    const onAbort = () => {
      cleanup();
      reject(new DOMException('The run was cancelled', 'AbortError'));
    };
    window.addEventListener('online', onOnline, { once: true });
    signal.addEventListener('abort', onAbort, { once: true });
  });
}

export function delay(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => {
      signal.removeEventListener('abort', onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(timer);
      reject(new DOMException('The run was cancelled', 'AbortError'));
    };
    signal.addEventListener('abort', onAbort, { once: true });
  });
}