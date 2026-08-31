/* ─────────────────────────────────────────────────────────────
   Connector store — user-granted integrations.

   Reconciled 31/08/2026 (chapitre 8.2, audit + owner decision) :
   secrets now live ONLY on ARENA's own server (.env / process env,
   never the browser) — consistent with the rest of ARENA
   (core/security/trust.py, core/permissions/). The AES-256 browser
   vault that used to encrypt tokens in localStorage is gone; there
   is nothing left here for it to protect, since the only real
   connector (Gmail) is OAuth against ARENA's own backend
   (apps/backend/routers/connectors.py), which stores the resulting
   token server-side.

   OAuth flow: real popup against YOUR backend
   ({backend}/connectors/{id}/auth) + postMessage / status polling.
   ───────────────────────────────────────────────────────────── */

import { create } from 'zustand';
import { getConnector } from '../connectors/catalog';
import { activeRemoteCfg } from './backendStore';

export interface ConnectorState {
  status: 'disconnected' | 'connecting' | 'connected';
  account?: string;
  /** allowed for use in prompts (per-user kill switch) */
  enabled: boolean;
  verified: boolean;
  connectedAt?: number;
}

type Map = Record<string, ConnectorState>;

const KEY = 'usman.connectors.v1';

function load(): Map {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return JSON.parse(raw) as Map;
  } catch {
    /* ignore */
  }
  return {};
}

function persist(map: Map) {
  try {
    localStorage.setItem(KEY, JSON.stringify(map));
  } catch {
    /* ignore */
  }
}

interface Store {
  connectors: Map;
  modalOpen: boolean;
  setModalOpen(open: boolean): void;
  disconnect(id: string): void;
  toggleEnabled(id: string): void;
  startOAuth(id: string): Promise<boolean>;
}

export const useConnectors = create<Store>((set, get) => {
  const update = (id: string, patch: Partial<ConnectorState>) =>
    set((s) => {
      const prev: ConnectorState =
        s.connectors[id] ?? { status: 'disconnected', enabled: true, verified: false };
      const connectors = { ...s.connectors, [id]: { ...prev, ...patch } };
      persist(connectors);
      return { connectors };
    });

  return {
    connectors: load(),
    modalOpen: false,
    setModalOpen: (modalOpen) => set({ modalOpen }),

    /** OAuth connector: popup → consent on YOUR backend → postMessage / poll status */
    async startOAuth(id) {
      const cfg = activeRemoteCfg();
      const def = getConnector(id);
      if (!def) return false;
      update(id, { status: 'connecting' });

      // without a backend, open nothing — caller shows the hint
      if (!cfg) {
        update(id, { status: 'disconnected' });
        return false;
      }

      const backendOrigin = new URL(cfg.url).origin;
      // `cle`, pas `key` : c'est le nom que le backend d'ARENA attend
      // (apps/backend/security.py, meme convention que /media/rendered).
      const authUrl = `${cfg.url}/connectors/${id}/auth?cle=${encodeURIComponent(cfg.apiKey ?? 'anon')}`;
      const popup = window.open(authUrl, 'usman_oauth', 'width=620,height=760,menubar=no,toolbar=no');
      const deadline = Date.now() + 180_000;

      // Listen for instant postMessage notification from OAuth callback page
      let resolved = false;
      const messageHandler = (ev: MessageEvent) => {
        // Le popup est servi par le meme backend qu'on vient d'appeler :
        // n'importe quelle autre origine est ignoree, jamais fait confiance.
        if (ev.origin !== backendOrigin) return;
        if (ev.data?.type === 'usman_oauth_success' && ev.data?.connector === id) {
          resolved = true;
          update(id, {
            status: 'connected',
            account: ev.data.account || 'Connected Account',
            verified: true,
            connectedAt: Date.now(),
          });
        }
      };
      window.addEventListener('message', messageHandler);

      try {
        while (Date.now() < deadline) {
          if (resolved) return true;
          await new Promise((r) => setTimeout(r, 1200));
          if (resolved) return true;

          try {
            const res = await fetch(`${cfg.url}/connectors/${id}/status`, {
              headers: cfg.apiKey ? { Authorization: `Bearer ${cfg.apiKey}` } : {},
            });
            if (res.ok) {
              const data = (await res.json()) as { connected?: boolean; account?: string; verified?: boolean };
              if (data.connected) {
                if (popup && !popup.closed) popup.close();
                update(id, {
                  status: 'connected',
                  account: data.account || 'Connected Account',
                  verified: data.verified !== false,
                  connectedAt: Date.now(),
                });
                return true;
              }
            }
          } catch {
            /* retry until deadline */
          }
          if (popup && popup.closed) {
            // Give one final chance for status
            await new Promise((r) => setTimeout(r, 500));
            const check = await fetch(`${cfg.url}/connectors/${id}/status`, {
              headers: cfg.apiKey ? { Authorization: `Bearer ${cfg.apiKey}` } : {},
            }).catch(() => null);
            if (check && check.ok) {
              const finalData = await check.json().catch(() => ({}));
              if (finalData.connected) {
                update(id, {
                  status: 'connected',
                  account: finalData.account || 'Connected Account',
                  verified: finalData.verified !== false,
                  connectedAt: Date.now(),
                });
                return true;
              }
            }
            break;
          }
        }
      } finally {
        window.removeEventListener('message', messageHandler);
      }

      if (!resolved) {
        update(id, { status: 'disconnected' });
      }
      return resolved;
    },

    disconnect: (id) => {
      const cfg = activeRemoteCfg();
      if (cfg) {
        void fetch(`${cfg.url}/connectors/${id}/disconnect`, {
          method: 'POST',
          headers: cfg.apiKey ? { Authorization: `Bearer ${cfg.apiKey}` } : {},
        }).catch(() => {});
      }
      update(id, {
        status: 'disconnected',
        account: undefined,
        verified: false,
      });
    },

    toggleEnabled: (id) => {
      const cur = get().connectors[id];
      update(id, { enabled: !(cur?.enabled ?? true) });
    },
  };
});

/** payload attached to every agent request → your backend decides tool access */
export async function resolveActiveConnectors(): Promise<
  Array<{ id: string; account?: string }>
> {
  return activeConnectorPayload();
}

export function activeConnectorPayload(): Array<{ id: string; account?: string }> {
  return Object.entries(useConnectors.getState().connectors)
    .filter(([, s]) => s.status === 'connected' && s.enabled)
    .map(([id, s]) => ({ id, account: s.account }));
}

export function connectedCount(): number {
  return Object.values(useConnectors.getState().connectors).filter((s) => s.status === 'connected').length;
}
