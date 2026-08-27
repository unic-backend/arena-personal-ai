/* PWA install/update controller. Browser prompts are never simulated. */
import { create } from 'zustand';

interface BeforeInstallPromptEvent extends Event {
  prompt(): Promise<void>;
  userChoice: Promise<{ outcome: 'accepted' | 'dismissed'; platform: string }>;
}

interface PWAState {
  installable: boolean;
  installed: boolean;
  isIOS: boolean;
  updateReady: boolean;
  installing: boolean;
  setPrompt(event: BeforeInstallPromptEvent | null): void;
  setInstalled(installed: boolean): void;
  setUpdateReady(ready: boolean): void;
  install(): Promise<'accepted' | 'dismissed' | 'unavailable'>;
  applyUpdate(): void;
}

let deferredPrompt: BeforeInstallPromptEvent | null = null;
let waitingWorker: ServiceWorker | null = null;
let initialized = false;

function standalone() {
  return typeof window !== 'undefined' && (
    window.matchMedia('(display-mode: standalone)').matches ||
    Boolean((navigator as Navigator & { standalone?: boolean }).standalone)
  );
}

function ios() {
  if (typeof navigator === 'undefined') return false;
  return /iPad|iPhone|iPod/.test(navigator.userAgent) ||
    (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
}

export const usePWA = create<PWAState>((set) => ({
  installable: false,
  installed: standalone(),
  isIOS: ios(),
  updateReady: false,
  installing: false,

  setPrompt: (event) => {
    deferredPrompt = event;
    set({ installable: Boolean(event), installing: false });
  },
  setInstalled: (installed) => set({ installed, installable: false, installing: false }),
  setUpdateReady: (updateReady) => set({ updateReady }),

  async install() {
    if (!deferredPrompt) return 'unavailable';
    set({ installing: true });
    await deferredPrompt.prompt();
    const choice = await deferredPrompt.userChoice;
    deferredPrompt = null;
    set({ installable: false, installing: false, installed: choice.outcome === 'accepted' || standalone() });
    return choice.outcome;
  },

  applyUpdate() {
    waitingWorker?.postMessage({ type: 'SKIP_WAITING' });
  },
}));

export function initializePWA() {
  if (initialized || typeof window === 'undefined') return;
  initialized = true;

  window.addEventListener('beforeinstallprompt', (event) => {
    event.preventDefault();
    usePWA.getState().setPrompt(event as BeforeInstallPromptEvent);
  });

  window.addEventListener('appinstalled', () => {
    usePWA.getState().setInstalled(true);
  });

  window.matchMedia('(display-mode: standalone)').addEventListener('change', (event) => {
    usePWA.getState().setInstalled(event.matches);
  });

  if (!('serviceWorker' in navigator) || !import.meta.env.PROD) return;
  window.addEventListener('load', async () => {
    try {
      const registration = await navigator.serviceWorker.register('/sw.js', { scope: '/' });
      if (registration.waiting) {
        waitingWorker = registration.waiting;
        usePWA.getState().setUpdateReady(true);
      }
      registration.addEventListener('updatefound', () => {
        const worker = registration.installing;
        if (!worker) return;
        worker.addEventListener('statechange', () => {
          if (worker.state === 'installed' && navigator.serviceWorker.controller) {
            waitingWorker = worker;
            usePWA.getState().setUpdateReady(true);
          }
        });
      });
      navigator.serviceWorker.addEventListener('controllerchange', () => window.location.reload());
      // Ask for updates occasionally without delaying first paint.
      window.setTimeout(() => void registration.update(), 10_000);
    } catch (error) {
      console.warn('Usman service worker registration failed:', error);
    }
  }, { once: true });
}
