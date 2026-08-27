import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  AlertTriangle,
  Check,
  ChevronRight,
  KeyRound,
  Loader2,
  Lock,
  LockKeyhole,
  LockOpen,
  Plug,
  ShieldCheck,
  Trash2,
  Unplug,
  X,
} from 'lucide-react';
import { CONNECTOR_CATALOG, CONNECTOR_CATEGORIES, ConnectorDef } from '../../lib/connectors/catalog';
import { useConnectors } from '../../lib/store/connectorStore';
import { useBackend } from '../../lib/store/backendStore';
import { useVault } from '../../lib/store/vaultStore';
import { useI18n } from '../../lib/i18n';
import { cn } from '../../utils/cn';

/* ── Vault & Master Key Security Banner ── */
function VaultSecurityCard() {
  const { t } = useI18n();
  const {
    hasMasterKey,
    isUnlocked,
    error,
    setupMasterKey,
    unlockVault,
    lockVault,
    removeMasterKey,
  } = useVault();
  const { encryptAllTokens, decryptAllTokens } = useConnectors();

  const [openControls, setOpenControls] = useState(false);
  const [passphrase, setPassphrase] = useState('');
  const [localErr, setLocalErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const handleUnlock = async () => {
    if (!passphrase) return;
    setBusy(true);
    setLocalErr(null);
    const ok = await unlockVault(passphrase);
    setBusy(false);
    if (ok) {
      setPassphrase('');
    } else {
      setLocalErr(t('vault.wrongPassphrase'));
    }
  };

  const handleSetup = async () => {
    if (passphrase.length < 4) {
      setLocalErr(t('vault.tooShort'));
      return;
    }
    setBusy(true);
    setLocalErr(null);
    const ok = await setupMasterKey(passphrase);
    if (ok) {
      // Migrate all existing plaintext tokens to AES-GCM-256
      await encryptAllTokens(passphrase);
      setPassphrase('');
      setOpenControls(false);
    } else {
      setLocalErr('Error setting up master key');
    }
    setBusy(false);
  };

  const handleRemove = async () => {
    const vault = useVault.getState();
    if (vault.sessionPassphrase) {
      await decryptAllTokens(vault.sessionPassphrase);
    }
    removeMasterKey();
    setOpenControls(false);
    setPassphrase('');
    setLocalErr(null);
  };

  return (
    <div className="rounded-xl border border-white/8 bg-white/[0.025] overflow-hidden">
      <div className="flex items-center justify-between p-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <span
            className={cn(
              'grid h-8 w-8 shrink-0 place-items-center rounded-lg border',
              hasMasterKey && isUnlocked
                ? 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400'
                : hasMasterKey && !isUnlocked
                  ? 'border-amber-500/30 bg-amber-500/10 text-amber-400'
                  : 'border-white/10 bg-white/5 text-zinc-400',
            )}
          >
            {hasMasterKey ? isUnlocked ? <LockOpen size={14} /> : <LockKeyhole size={14} /> : <Lock size={14} />}
          </span>
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="text-[12px] font-medium text-zinc-200">{t('vault.title')}</span>
              <span
                className={cn(
                  'rounded px-1.5 py-0.2 font-mono text-[8.5px] uppercase tracking-wider',
                  hasMasterKey && isUnlocked
                    ? 'bg-emerald-500/15 text-emerald-300'
                    : hasMasterKey && !isUnlocked
                      ? 'bg-amber-500/15 text-amber-300'
                      : 'bg-white/5 text-zinc-500',
                )}
              >
                {hasMasterKey ? (isUnlocked ? t('vault.statusEncrypted') : t('vault.lockedDesc')) : t('vault.statusUnencrypted')}
              </span>
            </div>
            <p className="truncate text-[10px] text-zinc-500">
              {hasMasterKey
                ? isUnlocked
                  ? t('vault.unlockedDesc')
                  : t('vault.lockedDesc')
                : t('vault.noKeyDesc')}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1.5 shrink-0 ml-2">
          {hasMasterKey && isUnlocked ? (
            <button
              type="button"
              onClick={lockVault}
              className="inline-flex items-center gap-1 rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-[10px] font-medium text-zinc-300 transition hover:bg-white/10 active:scale-95"
              title={t('vault.lock')}
            >
              <Lock size={10} />
              {t('vault.lock')}
            </button>
          ) : (
            <button
              type="button"
              onClick={() => setOpenControls((v) => !v)}
              className="inline-flex items-center gap-1 rounded-lg border border-accent-500/30 bg-accent-500/10 px-2.5 py-1 text-[10.5px] font-medium text-accent-300 transition hover:bg-accent-500/20 active:scale-95"
            >
              <KeyRound size={11} />
              {hasMasterKey ? t('vault.unlock') : t('vault.setup')}
            </button>
          )}
        </div>
      </div>

      {/* Expandable Vault Unlock / Setup Form */}
      <AnimatePresence initial={false}>
        {openControls && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="overflow-hidden border-t border-white/6 bg-ink-950/60 p-3"
          >
            <div className="space-y-2">
              <div className="flex gap-2">
                <input
                  type="password"
                  value={passphrase}
                  onChange={(e) => {
                    setPassphrase(e.target.value);
                    setLocalErr(null);
                  }}
                  autoFocus
                  placeholder={hasMasterKey ? t('vault.passphrasePh') : t('vault.setupPh')}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      hasMasterKey ? handleUnlock() : handleSetup();
                    }
                  }}
                  className="min-w-0 flex-1 rounded-lg border border-white/10 bg-ink-950 px-2.5 py-1.5 font-mono text-[11px] text-zinc-100 outline-none focus:border-accent-500/50"
                />
                <button
                  type="button"
                  onClick={hasMasterKey ? handleUnlock : handleSetup}
                  disabled={busy || !passphrase}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-accent-500 px-3 py-1.5 text-[11px] font-medium text-ink-950 transition hover:bg-accent-400 disabled:opacity-40"
                >
                  {busy ? <Loader2 size={12} className="animate-spin" /> : <Check size={12} strokeWidth={2.5} />}
                  {hasMasterKey ? t('vault.unlock') : t('vault.setup')}
                </button>
              </div>

              {(localErr || error) && (
                <div className="flex items-center gap-1.5 text-[10px] text-red-400">
                  <AlertTriangle size={11} />
                  <span>{localErr || error}</span>
                </div>
              )}

              {hasMasterKey && isUnlocked && (
                <div className="flex justify-end pt-1">
                  <button
                    type="button"
                    onClick={handleRemove}
                    className="inline-flex items-center gap-1 text-[9.5px] text-zinc-500 transition hover:text-red-400"
                  >
                    <Trash2 size={10} />
                    {t('vault.remove')}
                  </button>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/* ── single connector row ── */
function ConnectorRow({ def }: { def: ConnectorDef }) {
  const { t, locale } = useI18n();
  const fr = locale === 'fr';
  const { connectors, setToken, disconnect, toggleEnabled, startOAuth } = useConnectors();
  const st = connectors[def.id] ?? { status: 'disconnected' as const, enabled: true, verified: false };
  const [tokenOpen, setTokenOpen] = useState(false);
  const [token, setTokenInput] = useState('');

  const Icon = def.icon;
  const connected = st.status === 'connected';
  const connecting = st.status === 'connecting';
  const isEncrypted = Boolean(st.encryptedToken);

  const save = async () => {
    if (!token.trim()) return;
    const ok = await setToken(def.id, token.trim());
    if (ok) {
      setTokenOpen(false);
      setTokenInput('');
    }
  };

  return (
    <motion.div
      layout="position"
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn(
        'rounded-xl border transition-colors',
        connected && st.enabled ? 'border-accent-500/25 bg-accent-500/[0.04]' : 'border-white/7 bg-white/[0.02]',
      )}
    >
      <div className="flex items-center gap-3 p-3">
        <span
          className={cn(
            'grid h-9 w-9 shrink-0 place-items-center rounded-lg border',
            connected && st.enabled
              ? 'border-accent-500/30 bg-accent-500/10 text-accent-300'
              : 'border-white/8 bg-white/4 text-zinc-400',
          )}
        >
          <Icon size={16} />
        </span>

        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate text-[12.5px] font-medium text-zinc-100">{def.name}</span>
            {def.auth === 'oauth' && <Lock size={9} className="shrink-0 text-zinc-600" />}
            {isEncrypted && (
              <span
                className="inline-flex items-center gap-0.5 rounded bg-emerald-500/10 px-1 py-0.2 font-mono text-[8px] text-emerald-400"
                title={t('conn.encrypted')}
              >
                <LockKeyhole size={8} />
                AES-256
              </span>
            )}
            {connected && st.verified && (
              <span title={t('conn.verified')}>
                <ShieldCheck size={11} className="shrink-0 text-emerald-400" />
              </span>
            )}
          </div>
          <div className="truncate text-[10.5px] text-zinc-500">
            {connected && st.account ? st.account : fr ? def.descriptionFr : def.description}
          </div>
        </div>

        {/* action zone */}
        {connecting ? (
          <span className="grid h-7 w-7 place-items-center">
            <Loader2 size={13} className="animate-spin text-accent-400" />
          </span>
        ) : connected ? (
          <div className="flex shrink-0 items-center gap-1.5">
            {/* per-chat kill switch */}
            <button
              onClick={() => toggleEnabled(def.id)}
              title={t('conn.use')}
              className={cn(
                'relative h-[18px] w-[32px] rounded-full transition-colors',
                st.enabled ? 'bg-accent-500' : 'bg-white/10',
              )}
            >
              <span
                className={cn(
                  'absolute top-[2px] h-[14px] w-[14px] rounded-full bg-white transition-all',
                  st.enabled ? 'left-[16px]' : 'left-[2px] opacity-60',
                )}
              />
            </button>
            <button
              onClick={() => disconnect(def.id)}
              title={t('conn.disconnect')}
              className="grid h-7 w-7 place-items-center rounded-md text-zinc-500 transition hover:bg-red-400/10 hover:text-red-300"
            >
              <Unplug size={12} />
            </button>
          </div>
        ) : (
          <button
            onClick={() => (def.auth === 'apikey' ? setTokenOpen((o) => !o) : startOAuth(def.id))}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-white/10 bg-white/5 px-2.5 py-1.5 text-[10.5px] font-medium text-zinc-200 transition hover:border-accent-500/40 hover:bg-accent-500/10 hover:text-accent-300 active:scale-95"
          >
            <Plug size={10} />
            {t('conn.connect')}
          </button>
        )}
      </div>

      {/* apikey inline form */}
      <AnimatePresence initial={false}>
        {tokenOpen && !connected && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.18 }}
            className="overflow-hidden"
          >
            <div className="space-y-1.5 border-t border-white/5 p-3 pt-2.5">
              <p className="font-mono text-[9px] text-zinc-600">{fr ? def.secretLabelFr : def.secretLabel}</p>
              <div className="flex gap-1.5">
                <input
                  value={token}
                  onChange={(e) => setTokenInput(e.target.value)}
                  type="password"
                  autoFocus
                  spellCheck={false}
                  placeholder="••••••••••••••••"
                  onKeyDown={(e) => e.key === 'Enter' && save()}
                  className="min-w-0 flex-1 rounded-md border border-white/8 bg-ink-950/70 px-2 py-1.5 font-mono text-[10.5px] text-zinc-200 outline-none focus:border-accent-500/40"
                />
                <button
                  onClick={save}
                  disabled={!token.trim()}
                  className="rounded-md bg-accent-500 px-2.5 text-[10.5px] font-medium text-ink-950 transition hover:bg-accent-400 disabled:opacity-40 active:scale-95"
                >
                  <Check size={12} />
                </button>
              </div>
              <p className="text-[9px] leading-relaxed text-zinc-600">{t('conn.secretHint')}</p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

/* ── the modal itself ── */
export function ConnectorsModal() {
  const { t, locale } = useI18n();
  const { modalOpen, setModalOpen, connectors } = useConnectors();
  const backend = useBackend();
  const connectedN = Object.values(connectors).filter((s) => s.status === 'connected').length;

  useEffect(() => {
    if (!modalOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setModalOpen(false);
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [modalOpen, setModalOpen]);

  return (
    <AnimatePresence>
      {modalOpen && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[60] bg-black/70 backdrop-blur-sm"
            onClick={() => setModalOpen(false)}
          />
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby="connectors-modal-title"
            initial={{ opacity: 0, scale: 0.96, y: 16 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: 12 }}
            transition={{ type: 'spring', stiffness: 380, damping: 32 }}
            className="fixed inset-x-3 top-[4vh] z-[61] mx-auto flex max-h-[92vh] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-white/10 bg-ink-900 shadow-[0_40px_120px_-20px_rgba(0,0,0,0.9)] sm:top-[6vh]"
          >
            <div className="flex items-center gap-2.5 border-b border-white/7 px-4 py-3">
              <span className="grid h-7 w-7 place-items-center rounded-lg border border-accent-500/30 bg-accent-500/10 text-accent-300">
                <Plug size={13} />
              </span>
              <div className="flex-1">
                <h2 id="connectors-modal-title" className="text-[13.5px] font-medium text-zinc-100">{t('conn.title')}</h2>
                <div className="font-mono text-[9px] text-zinc-400">
                  {connectedN > 0 ? t('conn.count', { n: connectedN }) : t('conn.none')}
                  {' · '}
                  {backend.enabled ? t('conn.routed') : t('conn.localOnly')}
                </div>
              </div>
              <button
                type="button"
                onClick={() => setModalOpen(false)}
                aria-label="Close"
                className="rounded-md p-1.5 text-zinc-500 transition hover:bg-white/5 hover:text-zinc-200"
              >
                <X size={15} />
              </button>
            </div>

            <div className="flex-1 space-y-4 overflow-y-auto p-4 scroll-slim">
              {/* Vault Card at top */}
              <VaultSecurityCard />

              {CONNECTOR_CATEGORIES.map((cat) => {
                const items = CONNECTOR_CATALOG.filter((c) => c.category === cat.id);
                if (!items.length) return null;
                return (
                  <section key={cat.id}>
                    <div className="mb-1.5 flex items-center gap-2 px-1">
                      <ChevronRight size={10} className="text-accent-500/70" />
                      <span className="font-mono text-[9px] uppercase tracking-[0.2em] text-zinc-600">
                        {locale === 'fr' ? cat.labelFr : cat.label}
                      </span>
                    </div>
                    <div className="space-y-1.5">
                      {items.map((def) => (
                        <ConnectorRow key={def.id} def={def} />
                      ))}
                    </div>
                  </section>
                );
              })}
            </div>

            <div className="border-t border-white/7 px-4 py-2.5">
              <p className="text-[9.5px] leading-relaxed text-zinc-600">{t('conn.footer')}</p>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
