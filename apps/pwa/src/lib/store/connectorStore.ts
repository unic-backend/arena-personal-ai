/* ─────────────────────────────────────────────────────────────
   Connector store — user-granted integrations.

   · Security & Encryption: Secrets are encrypted with AES-GCM-256
     when Usman's Master Key Vault is active.
   · OAuth connectors: real popup flow against YOUR backend
     ({backend}/connectors/{id}/auth) + status polling.
   · API-key connectors: token stored locally/encrypted, verified
     through the backend (POST /connectors/verify) when online.
   ───────────────────────────────────────────────────────────── */

import { create } from 'zustand';
import { getConnector } from '../connectors/catalog';
import { activeRemoteCfg } from './backendStore';
import { useVault } from './vaultStore';
import { EncryptedPayload, encryptSecret, decryptSecret } from '../security/vault';

export interface ConnectorState {
  status: 'disconnected' | 'connecting' | 'connected';
  account?: string;
  token?: string; // Plaintext when no master key
  encryptedToken?: EncryptedPayload; // AES-256-GCM ciphertext when vault is active
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
  setToken(id: string, token: string): Promise<boolean>;
  disconnect(id: string): void;
  toggleEnabled(id: string): void;
  startOAuth(id: string): Promise<boolean>;
  encryptAllTokens(passphrase: string): Promise<void>;
  decryptAllTokens(passphrase: string): Promise<void>;
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

    /** API-key connector: store securely (AES-256 encrypted if master key is active) + verify */
    async setToken(id, token) {
      update(id, { status: 'connecting', verified: false });
      const cfg = activeRemoteCfg();
      let account = '';
      let verified = false;

      if (cfg) {
        try {
          const res = await fetch(`${cfg.url}/connectors/verify`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              ...(cfg.apiKey ? { Authorization: `Bearer ${cfg.apiKey}` } : {}),
            },
            body: JSON.stringify({ id, token }),
          });
          if (res.ok) {
            const data = (await res.json()) as { ok?: boolean; account?: string };
            if (data.ok !== false) {
              verified = true;
              account = data.account ?? '';
            } else {
              update(id, { status: 'disconnected' });
              return false;
            }
          }
        } catch {
          /* backend unreachable — store unverified */
        }
      }

      const tail = token.replace(/\s/g, '').slice(-4);
      const vault = useVault.getState();

      let encryptedPayload: EncryptedPayload | undefined;
      let plaintextToStore: string | undefined = token;

      // If Vault is active and unlocked, encrypt the token and do not store plaintext in storage
      if (vault.hasMasterKey && vault.isUnlocked && vault.sessionPassphrase) {
        const encrypted = await vault.encryptData(token);
        if (encrypted) {
          encryptedPayload = encrypted;
          plaintextToStore = undefined;
        }
      }

      update(id, {
        status: 'connected',
        verified,
        token: plaintextToStore,
        encryptedToken: encryptedPayload,
        account: account || `••••${tail || 'token'}`,
        connectedAt: Date.now(),
      });
      return true;
    },

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

      const authUrl = `${cfg.url}/connectors/${id}/auth?key=${encodeURIComponent(cfg.apiKey ?? 'anon')}`;
      const popup = window.open(authUrl, 'usman_oauth', 'width=620,height=760,menubar=no,toolbar=no');
      const deadline = Date.now() + 180_000;

      // Listen for instant postMessage notification from OAuth callback page
      let resolved = false;
      const messageHandler = (ev: MessageEvent) => {
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
        token: undefined,
        encryptedToken: undefined,
        verified: false,
      });
    },

    toggleEnabled: (id) => {
      const cur = get().connectors[id];
      update(id, { enabled: !(cur?.enabled ?? true) });
    },

    /** Encrypt all existing plaintext tokens when setting up a Master Key */
    async encryptAllTokens(passphrase: string) {
      const current = get().connectors;
      const updated: Map = { ...current };
      for (const [id, st] of Object.entries(current)) {
        if (st.token && !st.encryptedToken) {
          try {
            const encrypted = await encryptSecret(st.token, passphrase);
            updated[id] = { ...st, token: undefined, encryptedToken: encrypted };
          } catch {
            /* ignore */
          }
        }
      }
      persist(updated);
      set({ connectors: updated });
    },

    /** Decrypt all encrypted tokens when disabling Master Key */
    async decryptAllTokens(passphrase: string) {
      const current = get().connectors;
      const updated: Map = { ...current };
      for (const [id, st] of Object.entries(current)) {
        if (st.encryptedToken) {
          try {
            const decrypted = await decryptSecret(st.encryptedToken, passphrase);
            updated[id] = { ...st, token: decrypted, encryptedToken: undefined };
          } catch {
            /* ignore */
          }
        }
      }
      persist(updated);
      set({ connectors: updated });
    },
  };
});

/** payload attached to every agent request → your backend decides tool access */
export async function resolveActiveConnectors(): Promise<
  Array<{ id: string; token?: string; account?: string }>
> {
  const list = Object.entries(useConnectors.getState().connectors).filter(
    ([, s]) => s.status === 'connected' && s.enabled,
  );
  const vault = useVault.getState();

  const payload: Array<{ id: string; token?: string; account?: string }> = [];

  for (const [id, s] of list) {
    let resolvedToken = s.token;

    // Decrypt on the fly if encrypted
    if (!resolvedToken && s.encryptedToken && vault.isUnlocked && vault.sessionPassphrase) {
      try {
        resolvedToken = await decryptSecret(s.encryptedToken, vault.sessionPassphrase);
      } catch {
        /* ignore decryption errors */
      }
    }

    payload.push({ id, token: resolvedToken, account: s.account });
  }

  return payload;
}

/** Synchronous fallback used for quick status counts */
export function activeConnectorPayload(): Array<{ id: string; token?: string; account?: string }> {
  return Object.entries(useConnectors.getState().connectors)
    .filter(([, s]) => s.status === 'connected' && s.enabled)
    .map(([id, s]) => ({ id, token: s.token, account: s.account }));
}

export function connectedCount(): number {
  return Object.values(useConnectors.getState().connectors).filter((s) => s.status === 'connected').length;
}
