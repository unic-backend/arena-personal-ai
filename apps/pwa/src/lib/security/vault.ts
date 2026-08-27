/* ─────────────────────────────────────────────────────────────
   Usman Security Vault — Client-Side Encryption (Web Crypto API)
   · Algorithm: AES-GCM 256-bit with PBKDF2 (100,000 iterations, SHA-256)
   · Protects connector tokens, API keys, and personal credentials.
   · Zero plaintext stored in localStorage when master key is active.
   ───────────────────────────────────────────────────────────── */

export interface EncryptedPayload {
  v: 1;
  ct: string; // Base64 ciphertext
  iv: string; // Base64 12-byte IV
  salt: string; // Base64 16-byte salt
}

function bufferToBase64(buf: ArrayBuffer | Uint8Array): string {
  const bytes = buf instanceof Uint8Array ? buf : new Uint8Array(buf);
  let binary = '';
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

function base64ToBuffer(b64: string): Uint8Array {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

async function deriveKey(passphrase: string, salt: Uint8Array): Promise<CryptoKey> {
  const enc = new TextEncoder();
  const rawKey = enc.encode(passphrase);

  const baseKey = await crypto.subtle.importKey(
    'raw',
    rawKey,
    { name: 'PBKDF2' },
    false,
    ['deriveKey'],
  );

  return crypto.subtle.deriveKey(
    {
      name: 'PBKDF2',
      salt: salt as BufferSource,
      iterations: 100000,
      hash: 'SHA-256',
    },
    baseKey,
    { name: 'AES-GCM', length: 256 },
    false,
    ['encrypt', 'decrypt'],
  );
}

/**
 * Encrypt a secret string with a passphrase using AES-256-GCM
 */
export async function encryptSecret(secret: string, passphrase: string): Promise<EncryptedPayload> {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const key = await deriveKey(passphrase, salt);

  const enc = new TextEncoder();
  const ciphertext = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv },
    key,
    enc.encode(secret),
  );

  return {
    v: 1,
    ct: bufferToBase64(ciphertext),
    iv: bufferToBase64(iv),
    salt: bufferToBase64(salt),
  };
}

/**
 * Decrypt an AES-256-GCM payload with a passphrase
 */
export async function decryptSecret(payload: EncryptedPayload, passphrase: string): Promise<string> {
  const salt = base64ToBuffer(payload.salt);
  const iv = base64ToBuffer(payload.iv);
  const ct = base64ToBuffer(payload.ct);
  const key = await deriveKey(passphrase, salt);

  const decrypted = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: iv as BufferSource },
    key,
    ct as BufferSource,
  );

  return new TextDecoder().decode(decrypted);
}

/**
 * Create a verification hash so we can check the master passphrase quickly without decrypting everything.
 */
export async function createPassphraseVerifier(passphrase: string): Promise<{ hash: string; salt: string }> {
  const salt = crypto.getRandomValues(new Uint8Array(16));
  const key = await deriveKey(passphrase, salt);
  const enc = new TextEncoder();
  const signature = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv: new Uint8Array(12) },
    key,
    enc.encode('usman_vault_verified'),
  );
  return {
    hash: bufferToBase64(signature),
    salt: bufferToBase64(salt),
  };
}

/**
 * Check if a passphrase matches the saved verifier.
 */
export async function verifyPassphrase(passphrase: string, hash: string, saltB64: string): Promise<boolean> {
  try {
    const salt = base64ToBuffer(saltB64);
    const ct = base64ToBuffer(hash);
    const key = await deriveKey(passphrase, salt);
    const decrypted = await crypto.subtle.decrypt(
      { name: 'AES-GCM', iv: new Uint8Array(12) },
      key,
      ct as BufferSource,
    );
    return new TextDecoder().decode(decrypted) === 'usman_vault_verified';
  } catch {
    return false;
  }
}
