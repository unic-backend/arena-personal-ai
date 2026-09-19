import { useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Check, ChevronRight, Minus, X } from 'lucide-react';
import {
  ActivityNode, activeLabel, collectStats, echecNonResolu, etapesTerminees,
  formatDuration, flatten,
} from '../../lib/activity/types';
import { ActivityItem, ThinkingIndicator, ItemCtx } from './ActivityItem';
import { Logo } from '../chat/Sidebar';
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
  const unresolved = echecNonResolu(nodes, live);
  const recovered = !live && stats.failed > 0 && !unresolved;

  const headerText = live
    ? (current ?? t('act.thinking'))
    : unresolved
      ? `${t('act.workedFor', { d: formatDuration(elapsed) })} · ${t('act.fails', { n: stats.failed })}`
      : recovered
        ? `${t('act.workedFor', { d: formatDuration(elapsed) })} · ${t(stats.failed === 1 ? 'act.failsFixed.one' : 'act.failsFixed.many', { n: stats.failed })}`
        : t('act.workedFor', { d: formatDuration(elapsed) });

  const terminees = useMemo(() => etapesTerminees(nodes), [nodes]);

  const summary = useMemo(() => {
    const all = flatten(nodes).filter((n) => n.kind !== 'thinking' && n.kind !== 'planning');
    const done = all.filter((n) => n.status === 'completed');
    return { done: done.length, total: all.length, tail: [...all].slice(-3) };
  }, [nodes]);

  /* En cours : le petit logo qui tourne, ce qu'il fait a cote, et ce qu'il
     vient de finir en dessous — jamais un encadre. Une fois termine, le
     detail complet (etapes, duree) reste ouvert a la demande sur la carte
     ci-dessous, inchangee.

     Les etapes DEJA finies restent affichees depuis le 19/09/2026, sur sa
     demande : « je veux voir ce que l'IA fait en temps reel — reflexion,
     execution, raisonnement, memoire ». Une seule ligne qui se remplace
     montre l'etape en cours et efface les precedentes : au moment ou il
     regarde, il ne voit qu'un mot, et le travail deja fait a disparu.

     Les quatre dernieres, pas toutes : un tour qui enchaine dix outils
     pousserait sa question hors de l'ecran pendant qu'il attend la
     reponse. */
  if (live) {
    return (
      <motion.div
        role="region"
        aria-label={t('a11y.activityStatus', { status: headerText })}
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25 }}
        className="py-1"
      >
        <div className="flex items-center gap-2">
          <Logo size={15} className="thinking-logo shrink-0" />
          <span className="truncate text-[12.5px] font-medium text-shimmer">{headerText}</span>
        </div>
        {terminees.length > 0 && (
          <div className="mt-1 space-y-0.5 pl-[22px]">
            {terminees.map((n) => (
              <motion.div
                key={n.id}
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.2 }}
                className="flex items-center gap-1.5"
              >
                {n.status === 'failed'
                  ? <X size={10} className="shrink-0 text-red-400" />
                  : <Check size={10} className="shrink-0 text-emerald-400/70" />}
                <span className={cn(
                  'truncate text-[11.5px]',
                  n.status === 'failed' ? 'text-red-300/80' : 'text-zinc-500',
                )}>
                  {n.title}
                </span>
                {n.description && (
                  <span className="truncate text-[10.5px] text-zinc-600">{n.description}</span>
                )}
                {n.durationMs !== undefined && (
                  <span className="shrink-0 font-mono text-[9.5px] tabular-nums text-zinc-700">
                    {formatDuration(n.durationMs)}
                  </span>
                )}
              </motion.div>
            ))}
          </div>
        )}
      </motion.div>
    );
  }

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
            // Terminé et sans échec : un liseré, pas un encadré. La réponse
            // est ce qu'il vient lire ; le travail qui l'a produite reste
            // atteignable sans lui disputer l'écran.
            : 'border-white/[0.04] bg-transparent',
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
          // Une coche sobre, sans pastille pleine : le travail est fini, il
          // n'a plus besoin d'etre annonce — seulement d'etre retrouvable.
          <span className="grid h-[14px] w-[14px] place-items-center text-zinc-600">
            <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3.4" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
          </span>
        )}
        {unresolved && <span className="inline-block h-1.5 w-1.5 rounded-full bg-red-400" />}

        <span
          className={cn(
            'flex-1 truncate text-[12px] tracking-wide',
            live ? 'text-shimmer font-medium'
              : unresolved ? 'text-red-300/90 font-medium'
                : 'text-zinc-600',
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

      {/* Replie, on ne garde un apercu que s'il reste un ECHEC.
          **Demande du 19/09/2026** : « ce travail devrait etre apparent quand
          il travaille ; apres qu'il livre sa reponse il doit pas etre tres
          apparent ». Une fois la reponse ecrite, trois lignes de coches vertes
          au-dessus d'elle disent une chose deja acquise, et prennent la place
          de ce qu'il est venu lire.

          Un echec, lui, reste visible : le cacher parce que le tour est fini
          serait cacher ce qui n'a pas marche. Le detail complet reste a un
          appui sur l'en-tete, pour les deux cas. */}
      <AnimatePresence initial={false}>
        {!open && unresolved && (
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
