import { useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Check, ChevronRight, Minus, X } from 'lucide-react';
import {
  ActivityNode, activeLabel, collectStats, formatDuration, flatten,
} from '../../lib/activity/types';
import { ActivityItem, ThinkingIndicator, ItemCtx } from './ActivityItem';
import { useI18n } from '../../lib/i18n';
import { cn } from '../../utils/cn';

/* ── plain timeline ── */
export function ActivityTimeline({ nodes, ctx }: { nodes: ActivityNode[]; ctx: ItemCtx }) {
  return (
    <div role="list" className="space-y-0.5">
      {nodes.map((n) =>
        n.kind === 'thinking' ? (
          <ThinkingRow key={n.id} node={n} />
        ) : (
          <ActivityItem key={n.id} node={n} ctx={ctx} />
        ),
      )}
    </div>
  );
}

function ThinkingRow({ node }: { node: ActivityNode }) {
  return (
    <motion.div
      role="listitem"
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
    >
      <ThinkingIndicator title={node.title} running={node.status === 'running'} />
    </motion.div>
  );
}

/* tick once per 250ms while the block is live */
function useNow(active: boolean) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(t);
  }, [active]);
  return now;
}

/* ═── the collapsible activity card attached to every assistant turn ──╚ */
export function AIActivity({
  nodes,
  ctx,
  live,
  startedAt,
}: {
  nodes: ActivityNode[];
  ctx: ItemCtx;
  live: boolean;
  startedAt: number;
}) {
  const stats = useMemo(() => collectStats(nodes), [nodes]);
  const now = useNow(live);
  const [open, setOpen] = useState(true);
  const userToggled = useRef(false);
  const { t } = useI18n();

  /* Auto-collapse shortly after Usman completes the work. */
  useEffect(() => {
    if (live || userToggled.current) return;
    const t = setTimeout(() => setOpen(false), 1100);
    return () => clearTimeout(t);
  }, [live, nodes]);

  const current = live ? activeLabel(nodes) : undefined;
  const elapsed = live ? now - startedAt : stats.durationMs;
  /* a failure resolved by later steps (e.g. first build) is reported, not alarmed */
  const lastRoot = nodes[nodes.length - 1];
  const unresolved = !live && stats.failed > 0 && !!lastRoot && lastRoot.status === 'failed';
  const recovered = !live && stats.failed > 0 && !unresolved;

  const headerText = live
    ? (current ?? t('act.thinking'))
    : unresolved
      ? `${t('act.workedFor', { d: formatDuration(elapsed) })} · ${t('act.fails', { n: stats.failed })}`
      : recovered
        ? `${t('act.workedFor', { d: formatDuration(elapsed) })} · ${t(stats.failed === 1 ? 'act.failsFixed.one' : 'act.failsFixed.many', { n: stats.failed })}`
        : t('act.workedFor', { d: formatDuration(elapsed) });

  const summary = useMemo(() => {
    const all = flatten(nodes).filter((n) => n.kind !== 'thinking' && n.kind !== 'planning');
    const done = all.filter((n) => n.status === 'completed');
    return { done: done.length, total: all.length, tail: [...all].slice(-3) };
  }, [nodes]);

  return (
    <motion.section
      role="region"
      aria-label={t('a11y.activityStatus', { status: headerText })}
      layout="position"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.22, 0.9, 0.3, 1] }}
      className={cn(
        'overflow-hidden rounded-xl border transition-colors duration-500',
        live
          ? 'border-accent-500/25 bg-accent-500/[0.035] activity-glow'
          : unresolved
            ? 'border-red-400/18 bg-red-400/[0.03]'
            : 'border-white/8 bg-white/[0.02]',
      )}
    >
      {/* header — always visible */}
      <button
        type="button"
        aria-expanded={open}
        aria-label={t('a11y.toggleActivity')}
        onClick={() => { userToggled.current = true; setOpen((o) => !o); }}
        className="flex w-full items-center gap-2 px-3.5 py-2.5 text-left transition hover:bg-white/[0.025]"
      >
        <motion.span animate={{ rotate: open ? 90 : 0 }} transition={{ duration: 0.18 }}>
          <ChevronRight size={13} className="text-zinc-500" />
        </motion.span>

        {live && <span className="inline-block h-1.5 w-1.5 animate-pulse-dot rounded-full bg-accent-500" />}
        {!live && !unresolved && (
          <span className="grid h-[14px] w-[14px] place-items-center rounded-full bg-emerald-400/12 text-emerald-400">
            <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.4" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
          </span>
        )}
        {unresolved && <span className="inline-block h-1.5 w-1.5 rounded-full bg-red-400" />}

        <span
          className={cn(
            'flex-1 truncate text-[12px] font-medium tracking-wide',
            live ? 'text-shimmer' : unresolved ? 'text-red-300/90' : 'text-zinc-400',
          )}
        >
          {headerText}
        </span>

        {live && (
          <span className="shrink-0 font-mono text-[10px] tabular-nums text-zinc-500">
            {(elapsed / 1000).toFixed(0)}s
          </span>
        )}
        {!live && (
          <span className="shrink-0 font-mono text-[10px] text-zinc-600">
            {t('act.steps', { done: summary.done, total: summary.total })}
          </span>
        )}
      </button>

      {/* collapsed peek: last few steps stay glanceable */}
      <AnimatePresence initial={false}>
        {!open && (
          <motion.div
            key="peek"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.24, ease: [0.22, 0.9, 0.3, 1] }}
            className="overflow-hidden"
          >
            <div className="space-y-1 border-t border-white/5 px-3.5 py-2.5">
              {summary.tail.map((n) => (
                <div key={n.id} className="flex items-center gap-2 text-[11px]">
                  {n.status === 'completed' && <Check size={10} className="shrink-0 text-emerald-400/90" strokeWidth={3} />}
                  {n.status === 'failed' && <X size={10} className="shrink-0 text-red-400" strokeWidth={3} />}
                  {n.status === 'cancelled' && <Minus size={10} className="shrink-0 text-zinc-600" strokeWidth={3} />}
                  {n.status === 'running' && <span className="inline-block h-1 w-1 shrink-0 animate-pulse-dot rounded-full bg-accent-500" />}
                  <span className={cn('truncate', n.status === 'running' ? 'text-zinc-300' : 'text-zinc-500')}>
                    {n.title}
                  </span>
                  {n.description && n.kind !== 'thinking' && (
                    <span className="truncate text-zinc-600">· {n.description}</span>
                  )}
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* full timeline */}
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            key="full"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease: [0.22, 0.9, 0.3, 1] }}
            className="overflow-hidden"
          >
            <div className="border-t border-white/5 px-3.5 py-2.5">
              {nodes.length === 0 ? (
                <ThinkingIndicator title={t('act.warming')} running />
              ) : (
                <ActivityTimeline nodes={nodes} ctx={ctx} />
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.section>
  );
}
