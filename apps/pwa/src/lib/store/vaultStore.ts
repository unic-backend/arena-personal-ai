/* ─────────────────────────────────────────────────────────────
   Vault Store — Master Key & Credential Encryption Manager
   ───────────────────────────────────────────────────────────── */

import { create } from 'zustand';
import {
  createPassphraseVerifier,
  verifyPassphrase,
  encryptSecret,
  decryptSecret,
  EncryptedPayload,
} from '../security/vault';

const VAULT_META_KEY = 'usman.vault.meta.v1';

interface VaultMetadata {
  hasMasterKey: boolean;
  verifierHash?: string;
  verifierSalt?: string;
  createdAt?: number;
}

function loadVaultMeta(): VaultMetadata {
  try {
    const raw = localStorage.getItem(VAULT_META_KEY);
    if (raw) return JSON.parse(raw);
  } catch {
    /* ignore */
  }
  return { hasMasterKey: false };
}

function persistVaultMeta(meta: VaultMetadata) {
  try {
    localStorage.setItem(VAULT_META_KEY, JSON.stringify(meta));
  } catch {
    /* ignore */
  }
}

interface VaultState {
  hasMasterKey: boolean;
  isUnlocked: boolean;
  sessionPassphrase: string | null;
  error: string | null;

  setupMasterKey(passphrase: string): Promise<boolean>;
  unlockVault(passphrase: string): Promise<boolean>;
  lockVault(): void;
  removeMasterKey(): void;
  encryptData(secret: string): Promise<EncryptedPayload | null>;
  decryptData(payload: EncryptedPayload): Promise<string | null>;
}

export const useVault = create<VaultState>((set, get) => {
  const meta = loadVaultMeta();

  return {
    hasMasterKey: meta.hasMasterKey,
    isUnlocked: !meta.hasMasterKey, // If no master key, vault is open in plaintext mode
    sessionPassphrase: null,
    error: null,

    async setupMasterKey(passphrase: string) {
      if (!passphrase || passphrase.length < 4) {
        set({ error: 'min_length_4' });
        return false;
      }

      try {
        const { hash, salt } = await createPassphraseVerifier(passphrase);
        const newMeta: VaultMetadata = {
          hasMasterKey: true,
          verifierHash: hash,
          verifierSalt: salt,
          createdAt: Date.now(),
        };
        persistVaultMeta(newMeta);
        set({
          hasMasterKey: true,
          isUnlocked: true,
          sessionPassphrase: passphrase,
          error: null,
        });
        return true;
      } catch (err) {
        set({ error: 'setup_failed' });
        return false;
      }
    },

    async unlockVault(passphrase: string) {
      const currentMeta = loadVaultMeta();
      if (!currentMeta.verifierHash || !currentMeta.verifierSalt) {
        set({ error: 'no_verifier' });
        return false;
      }

      const valid = await verifyPassphrase(
        passphrase,
        currentMeta.verifierHash,
        currentMeta.verifierSalt,
      );

      if (valid) {
        set({
          isUnlocked: true,
          sessionPassphrase: passphrase,
          error: null,
        });
        return true;
      } else {
        set({ error: 'invalid_passphrase' });
        return false;
      }
    },

    lockVault() {
      const currentMeta = loadVaultMeta();
      set({
        isUnlocked: !currentMeta.hasMasterKey,
        sessionPassphrase: null,
        error: null,
      });
    },

    removeMasterKey() {
      try {
        localStorage.removeItem(VAULT_META_KEY);
      } catch {
        /* ignore */
      }
      set({
        hasMasterKey: false,
        isUnlocked: true,
        sessionPassphrase: null,
        error: null,
      });
    },

    async encryptData(secret: string) {
      const { sessionPassphrase, isUnlocked } = get();
      if (!isUnlocked || !sessionPassphrase) return null;
      try {
        return await encryptSecret(secret, sessionPassphrase);
      } catch {
        return null;
      }
    },

    async decryptData(payload: EncryptedPayload) {
      const { sessionPassphrase, isUnlocked } = get();
      if (!isUnlocked || !sessionPassphrase) return null;
      try {
        return await decryptSecret(payload, sessionPassphrase);
      } catch {
        return null;
      }
    },
  };
});
