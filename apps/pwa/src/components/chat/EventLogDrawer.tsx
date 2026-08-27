import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Pause, Play, Trash2, X } from 'lucide-react';
import { useChat } from '../../lib/store/chatStore';
import type { StreamChunk } from '../../lib/activity/types';
import { useI18n } from '../../lib/i18n';
import { cn } from '../../utils/cn';

const TYPE_STYLE: Record<StreamChunk['type'], { label: string; cls: string }> = {
  activity: { label: 'event', cls: 'text-accent-300' },
  token: { label: 'token', cls: 'text-violet-300' },
  done: { label: 'done ', cls: 'text-emerald-300' },
  error: { label: 'error', cls: 'text-red-300' },
};

function summarize(chunk: StreamChunk, t: ReturnType<typeof useI18n.getState>['t']): string {
  switch (chunk.type) {
    case 'activity': {
      const e = chunk.event;
      const tool = e.tool ? `${e.tool}.` : '';
      const extra = e.progress ? ` [${e.progress.done}/${e.progress.total}]` : '';
      return `${tool}${e.phase} · ${e.title}${e.description ? ` — ${e.description}` : ''}${extra}`;
    }
    case 'token': return JSON.stringify(chunk.text);
    case 'done': return chunk.meta?.sources ? t('log.doneMeta', { n: chunk.meta.sources.length }) : t('log.done');
    case 'error': return chunk.message;
  }
}

export function EventLogDrawer() {
  const { eventLog, logOpen, toggleLog, clearLog } = useChat();
  const { t } = useI18n();
  const [paused, setPaused] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const frozen = useRef(eventLog);

  useEffect(() => {
    if (!paused) frozen.current = eventLog;
  }, [eventLog, paused]);

  useEffect(() => {
    const el = scrollRef.current;
    if (el && !paused) el.scrollTop = el.scrollHeight;
  }, [frozen.current, paused, logOpen]);

  useEffect(() => {
    if (!logOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') toggleLog();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [logOpen, toggleLog]);

  const rows = paused ? frozen.current : eventLog;

  return (
    <AnimatePresence>
      {logOpen && (
        <motion.aside
          role="dialog"
          aria-modal="true"
          aria-label={t('a11y.eventLogTitle')}
          initial={{ x: 420, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: 420, opacity: 0 }}
          transition={{ type: 'spring', stiffness: 300, damping: 32 }}
          className="fixed bottom-0 right-0 top-0 z-50 flex w-full max-w-[400px] flex-col border-l border-white/8 bg-ink-900/98 shadow-2xl backdrop-blur"
        >
          <div className="flex items-center gap-2 border-b border-white/6 px-4 py-3">
            <span className="inline-block h-1.5 w-1.5 animate-pulse-dot rounded-full bg-accent-500" />
            <div className="flex-1">
              <div className="text-[12.5px] font-medium text-zinc-200">{t('log.title')}</div>
              <div className="font-mono text-[9px] text-zinc-600">{t('log.transport', { n: rows.length })}</div>
            </div>
            <button
              onClick={() => setPaused((p) => !p)}
              className="rounded-md p-1.5 text-zinc-500 transition hover:bg-white/5 hover:text-zinc-200"
              title={paused ? t('log.resume') : t('log.pause')}
            >
              {paused ? <Play size={13} /> : <Pause size={13} />}
            </button>
            <button onClick={clearLog} className="rounded-md p-1.5 text-zinc-500 transition hover:bg-white/5 hover:text-zinc-200" title={t('log.clear')}>
              <Trash2 size={13} />
            </button>
            <button onClick={toggleLog} className="rounded-md p-1.5 text-zinc-500 transition hover:bg-white/5 hover:text-zinc-200" title={t('log.close')}>
              <X size={14} />
            </button>
          </div>

          <div
            ref={scrollRef}
            role="log"
            aria-live="polite"
            className="flex-1 overflow-y-auto px-4 py-3 font-mono text-[10px] leading-relaxed scroll-slim"
          >
            {rows.length === 0 && (
              <p className="text-zinc-600">{t('log.empty')}</p>
            )}
            {rows.map((r, i) => (
              <div key={i} className="flex gap-2 border-b border-white/[0.03] py-1">
                <span className="shrink-0 text-zinc-700">{new Date(r.ts).toLocaleTimeString('en-GB', { hour12: false })}.{String(r.ts % 1000).padStart(3, '0').slice(0, 2)}</span>
                <span className={cn('w-[42px] shrink-0', TYPE_STYLE[r.chunk.type].cls)}>{TYPE_STYLE[r.chunk.type].label}</span>
                <span className="min-w-0 break-all text-zinc-400">{summarize(r.chunk, t)}</span>
              </div>
            ))}
            {paused && <div className="sticky bottom-0 mt-2 rounded bg-amber-400/10 px-2 py-1 text-center text-amber-300">{t('log.paused')}</div>}
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
  );
}
