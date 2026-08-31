import { useEffect } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { ChevronRight, Loader2, Lock, Plug, ShieldCheck, Unplug, X } from 'lucide-react';
import { CONNECTOR_CATALOG, CONNECTOR_CATEGORIES, ConnectorDef } from '../../lib/connectors/catalog';
import { useConnectors } from '../../lib/store/connectorStore';
import { useBackend } from '../../lib/store/backendStore';
import { useI18n } from '../../lib/i18n';
import { cn } from '../../utils/cn';

/* ── single connector row ── */
function ConnectorRow({ def }: { def: ConnectorDef }) {
  const { t, locale } = useI18n();
  const fr = locale === 'fr';
  const { connectors, disconnect, toggleEnabled, startOAuth } = useConnectors();
  const st = connectors[def.id] ?? { status: 'disconnected' as const, enabled: true, verified: false };

  const Icon = def.icon;
  const connected = st.status === 'connected';
  const connecting = st.status === 'connecting';

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
            <Lock size={9} className="shrink-0 text-zinc-600" />
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
            onClick={() => startOAuth(def.id)}
            className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-white/10 bg-white/5 px-2.5 py-1.5 text-[10.5px] font-medium text-zinc-200 transition hover:border-accent-500/40 hover:bg-accent-500/10 hover:text-accent-300 active:scale-95"
          >
            <Plug size={10} />
            {t('conn.connect')}
          </button>
        )}
      </div>
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
