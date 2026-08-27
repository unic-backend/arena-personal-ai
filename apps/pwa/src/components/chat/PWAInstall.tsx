import { AnimatePresence, motion } from 'framer-motion';
import { Check, Download, RefreshCw, Share, Smartphone } from 'lucide-react';
import { usePWA } from '../../lib/pwa';
import { useI18n } from '../../lib/i18n';
import { cn } from '../../utils/cn';

export function PWAInstall() {
  const { installable, installed, isIOS, updateReady, installing, install, applyUpdate } = usePWA();
  const { t } = useI18n();
  const showIOSHelp = isIOS && !installed && !installable;

  if (!installable && !installed && !showIOSHelp && !updateReady) return null;

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={updateReady ? 'update' : installed ? 'installed' : 'install'}
        initial={{ opacity: 0, y: 4 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -4 }}
        className={cn(
          'rounded-lg border px-2.5 py-2',
          updateReady
            ? 'border-accent-500/25 bg-accent-500/[0.06]'
            : 'border-white/8 bg-white/[0.02]',
        )}
      >
        <div className="flex items-center gap-2">
          <span className={cn(
            'grid h-6 w-6 shrink-0 place-items-center rounded-md',
            installed ? 'bg-emerald-400/10 text-emerald-400' : 'bg-accent-500/10 text-accent-300',
          )}>
            {updateReady ? <RefreshCw size={11} /> : installed ? <Check size={11} /> : <Smartphone size={11} />}
          </span>
          <div className="min-w-0 flex-1">
            <div className="truncate text-[10.5px] font-medium text-zinc-300">
              {updateReady ? t('pwa.updateReady') : installed ? t('pwa.installed') : t('pwa.title')}
            </div>
            <div className="truncate text-[9px] text-zinc-600">
              {updateReady ? t('pwa.updateHint') : installed ? t('pwa.installedHint') : showIOSHelp ? t('pwa.iosHint') : t('pwa.installHint')}
            </div>
          </div>
          {updateReady ? (
            <button
              type="button"
              onClick={applyUpdate}
              className="inline-flex shrink-0 items-center gap-1 rounded-md bg-accent-500 px-2 py-1 text-[9.5px] font-semibold text-ink-950 transition hover:bg-accent-400 active:scale-95"
            >
              <RefreshCw size={9} /> {t('pwa.update')}
            </button>
          ) : installable && !installed ? (
            <button
              type="button"
              disabled={installing}
              onClick={() => void install()}
              className="inline-flex shrink-0 items-center gap-1 rounded-md bg-accent-500 px-2 py-1 text-[9.5px] font-semibold text-ink-950 transition hover:bg-accent-400 active:scale-95 disabled:opacity-50"
            >
              {installing ? <RefreshCw size={9} className="animate-spin" /> : <Download size={9} />}
              {t('pwa.install')}
            </button>
          ) : showIOSHelp ? (
            <Share size={12} className="shrink-0 text-accent-300" />
          ) : null}
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
