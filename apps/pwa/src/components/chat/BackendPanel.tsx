import { useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { ChevronRight, Cloud, HardDrive, Loader2, PlugZap, Unplug } from 'lucide-react';
import { useBackend } from '../../lib/store/backendStore';
import { useI18n } from '../../lib/i18n';
import { cn } from '../../utils/cn';

export function BackendPanel() {
  const { t } = useI18n();
  const {
    url, apiKey, enabled, status, latencyMs, remoteName, remoteProvider, remoteModel, error,
    urlSecours, apiKeySecours, serveurActif,
    setUrl, setApiKey, setUrlSecours, setApiKeySecours, test, disconnect,
  } = useBackend();
  const [open, setOpen] = useState(false);

  const dot =
    status === 'online' && enabled
      ? 'bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.7)]'
      : status === 'checking'
        ? 'animate-pulse-dot bg-accent-400'
        : status === 'error'
          ? 'bg-red-400'
          : 'bg-zinc-500';

  const label =
    status === 'online' && enabled
      ? `${remoteName ?? t('backend.api')} · ${latencyMs ?? '—'}ms`
      : status === 'checking'
        ? t('backend.checking')
        : status === 'error'
          ? t('backend.unreachable')
          : t('backend.local');

  return (
    <div className="rounded-lg border border-white/8 bg-white/[0.02]">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-2.5 py-2 text-left transition hover:bg-white/[0.03]"
      >
        <motion.span animate={{ rotate: open ? 90 : 0 }} transition={{ duration: 0.16 }}>
          <ChevronRight size={11} className="text-zinc-600" />
        </motion.span>
        {enabled ? <Cloud size={11} className="shrink-0 text-accent-300" /> : <HardDrive size={11} className="shrink-0 text-zinc-500" />}
        <span className="flex-1 truncate font-mono text-[9px] uppercase tracking-[0.14em] text-zinc-500">
          {t('backend.title')} · <span className={cn(enabled && status === 'online' ? 'text-emerald-300/90' : 'text-zinc-600')}>{label}</span>
        </span>
        <span className={cn('inline-block h-1.5 w-1.5 shrink-0 rounded-full', dot)} />
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22, ease: [0.22, 0.9, 0.3, 1] }}
            className="overflow-hidden"
          >
            <div className="space-y-2 border-t border-white/5 px-2.5 pb-2.5 pt-2">
              <input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder={t('backend.urlPh')}
                spellCheck={false}
                className="w-full rounded-md border border-white/8 bg-ink-950/70 px-2 py-1.5 font-mono text-[10.5px] text-zinc-200 outline-none placeholder:text-zinc-700 focus:border-accent-500/40"
              />
              <input
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={t('backend.keyPh')}
                type="password"
                spellCheck={false}
                className="w-full rounded-md border border-white/8 bg-ink-950/70 px-2 py-1.5 font-mono text-[10.5px] text-zinc-200 outline-none placeholder:text-zinc-700 focus:border-accent-500/40"
              />
              {/* La seconde adresse, essayee quand la premiere ne repond pas.
                  Le proprietaire n'en retenait qu'une : brancher son PC
                  effacait Railway, et PC eteint plus rien ne repondait
                  jusqu'a ce qu'il recolle l'adresse a la main
                  (mesure du 03/09/2026). */}
              <p className="pt-1 font-mono text-[9px] uppercase tracking-wide text-zinc-600">
                {t('backend.secours')}
              </p>
              <input
                value={urlSecours}
                onChange={(e) => setUrlSecours(e.target.value)}
                placeholder={t('backend.secoursPh')}
                spellCheck={false}
                className="w-full rounded-md border border-white/8 bg-ink-950/70 px-2 py-1.5 font-mono text-[10.5px] text-zinc-200 outline-none placeholder:text-zinc-700 focus:border-accent-500/40"
              />
              <input
                value={apiKeySecours}
                onChange={(e) => setApiKeySecours(e.target.value)}
                placeholder={t('backend.keyPh')}
                type="password"
                spellCheck={false}
                className="w-full rounded-md border border-white/8 bg-ink-950/70 px-2 py-1.5 font-mono text-[10.5px] text-zinc-200 outline-none placeholder:text-zinc-700 focus:border-accent-500/40"
              />
              <p className="text-[9.5px] leading-relaxed text-zinc-600">
                {t('backend.secoursAide')}
              </p>
              {remoteModel && enabled && (
                <p className="truncate font-mono text-[9px] text-zinc-600">
                  {/* **Laquelle des deux repond.** Sans ca, l'ecran dit « en
                      ligne » sans dire ou part le texte : son PC ou le cloud. */}
                  {serveurActif === 'secours' ? `${t('backend.viaSecours')} · ` : ''}
                  {remoteProvider ? `${remoteProvider} · ` : ''}{remoteModel}
                </p>
              )}
              {error && (
                <p className="truncate font-mono text-[9px] text-red-300/80">{error}</p>
              )}
              <div className="flex gap-1.5">
                <button
                  onClick={() => test()}
                  disabled={status === 'checking'}
                  className="flex flex-1 items-center justify-center gap-1.5 rounded-md border border-accent-500/30 bg-accent-500/10 px-2 py-1.5 text-[10px] font-medium text-accent-300 transition hover:bg-accent-500/20 active:scale-[0.98] disabled:opacity-50"
                >
                  {status === 'checking' ? <Loader2 size={10} className="animate-spin" /> : <PlugZap size={10} />}
                  {enabled && status === 'online' ? t('backend.retest') : t('backend.connect')}
                </button>
                {enabled && (
                  <button
                    onClick={disconnect}
                    className="flex items-center justify-center gap-1.5 rounded-md border border-white/10 px-2 py-1.5 text-[10px] text-zinc-400 transition hover:border-white/20 hover:text-zinc-200 active:scale-[0.98]"
                    title={t('backend.disconnect')}
                  >
                    <Unplug size={10} />
                  </button>
                )}
              </div>
              <p className="text-[9px] leading-relaxed text-zinc-600">{t('backend.hint')}</p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
