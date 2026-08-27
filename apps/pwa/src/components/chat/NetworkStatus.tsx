import { AnimatePresence, motion } from 'framer-motion';
import { CloudOff, RefreshCw, Wifi } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useNetwork } from '../../lib/network/networkStore';
import { useI18n } from '../../lib/i18n';

export function NetworkStatus() {
  const { online, reconnecting, retryAttempt } = useNetwork();
  const { t } = useI18n();
  const previousOnline = useRef(online);
  const [showRestored, setShowRestored] = useState(false);

  useEffect(() => {
    if (!previousOnline.current && online) {
      setShowRestored(true);
      const timer = window.setTimeout(() => setShowRestored(false), 2200);
      previousOnline.current = online;
      return () => clearTimeout(timer);
    }
    previousOnline.current = online;
  }, [online]);

  const visible = !online || reconnecting || showRestored;

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: 'auto', opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={{ duration: 0.22 }}
          className="relative z-20 overflow-hidden border-b border-white/6"
        >
          <div
            className={
              !online
                ? 'flex items-center justify-center gap-2 bg-amber-400/[0.08] px-3 py-1.5 text-amber-200'
                : reconnecting
                  ? 'flex items-center justify-center gap-2 bg-accent-500/[0.08] px-3 py-1.5 text-accent-200'
                  : 'flex items-center justify-center gap-2 bg-emerald-400/[0.08] px-3 py-1.5 text-emerald-300'
            }
          >
            {!online ? (
              <CloudOff size={12} />
            ) : reconnecting ? (
              <RefreshCw size={12} className="animate-spin" />
            ) : (
              <Wifi size={12} />
            )}
            <span className="text-[10.5px] font-medium">
              {!online
                ? t('network.offline')
                : reconnecting
                  ? t('network.reconnecting', { n: retryAttempt })
                  : t('network.online')}
            </span>
            {!online && (
              <span className="hidden text-[9.5px] text-amber-200/60 sm:inline">· {t('network.offlineHint')}</span>
            )}
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}