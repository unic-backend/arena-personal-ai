import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { ChevronRight } from 'lucide-react';
import type { ActivityNode, FileOpMeta } from '../../lib/activity/types';
import { formatDuration } from '../../lib/activity/types';
import { StatusIcon, kindIcon, KIND_ACCENT } from './StatusIcon';
import { useI18n } from '../../lib/i18n';
import {
  Chip, ResultChips, ProgressActivity, TerminalActivity, CodeExecutionActivity,
  SearchActivity, FileActivity, DiagnosticsActivity, ActivityError, SourceRow, PlanActivity, VideoActivity,
} from './bodies';
import { cn } from '../../utils/cn';

export interface ItemCtx {
  conversationId: string;
  messageId: string;
  onRetryCommand?: (messageId: string, nodeId: string) => void;
}

/* ── thinking rows get their own indicator treatment ── */
export function ThinkingIndicator({ title, running }: { title: string; running: boolean }) {
  return (
    <div className="flex items-center gap-2.5 py-0.5">
      <StatusIcon status={running ? 'running' : 'completed'} />
      <BrainGlyph />
      <span className={cn('text-[12.5px]', running ? 'text-shimmer font-medium' : 'text-zinc-500')}>
        {title}
      </span>
    </div>
  );
}

function BrainGlyph() {
  return <span className="text-violet-300/70">{kindIcon('thinking')}</span>;
}

function hasBody(node: ActivityNode): boolean {
  if (node.kind === 'terminal' || node.kind === 'code') return true;
  if (node.kind === 'video') return true;
  if (node.kind === 'search') return true;
  if (node.kind === 'planning' && Array.isArray(node.metadata?.steps)) return true;
  if (node.kind === 'analysis' && (node.output as { diagnostics?: unknown[] } | undefined)?.diagnostics?.length) return true;
  if (node.kind === 'browser' && node.metadata?.source) return true;
  if (node.metadata?.op) return true;
  return false;
}

export function ActivityItem({ node, ctx, depth = 0 }: { node: ActivityNode; ctx: ItemCtx; depth?: number }) {
  const expandable = hasBody(node) || node.children.length > 0;
  const [open, setOpen] = useState<boolean>(node.status !== 'completed');
  const userToggled = useRef(false);
  const { t } = useI18n();

  /* lifecycle: collapse detail rows when they finish (unless the user chose otherwise) */
  useEffect(() => {
    if (node.status === 'completed' && !userToggled.current) {
      if (node.kind === 'browser' || node.metadata?.op) setOpen(false);
    }
    if (node.status === 'failed') setOpen(true);
  }, [node.status, node.kind, node.metadata]);

  const toggle = () => {
    if (!expandable) return;
    userToggled.current = true;
    setOpen((o) => !o);
  };

  const body = (() => {
    switch (node.kind) {
      case 'terminal': return <TerminalActivity node={node} />;
      case 'code': return <CodeExecutionActivity node={node} />;
      case 'video': return <VideoActivity node={node} />;
      case 'search': return <SearchActivity node={node} />;
      case 'analysis': return <DiagnosticsActivity node={node} />;
      case 'planning': return <PlanActivity node={node} />;
      case 'browser': return node.metadata?.source ? <SourceRow node={node} /> : null;
      default: return node.metadata?.op ? <FileActivity node={node} /> : null;
    }
  })();

  const showError = node.status === 'failed' && node.kind !== 'terminal';
  const retryCommand = ctx.onRetryCommand
    ? () => ctx.onRetryCommand!(ctx.messageId, node.id)
    : undefined;

  const titleColor =
    node.status === 'failed'
      ? 'text-red-300'
      : node.status === 'running'
        ? 'text-zinc-100'
        : node.status === 'cancelled'
          ? 'text-zinc-600 line-through decoration-zinc-700'
          : 'text-zinc-400';

  return (
    <motion.div
      role="listitem"
      layout="position"
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.28, ease: [0.22, 0.9, 0.3, 1] }}
      className="relative"
    >
      <div
        role={expandable ? 'button' : undefined}
        tabIndex={expandable ? 0 : undefined}
        aria-expanded={expandable ? open : undefined}
        onClick={toggle}
        onKeyDown={(e) => {
          if (expandable && (e.key === 'Enter' || e.key === ' ')) {
            e.preventDefault();
            toggle();
          }
        }}
        className={cn(
          'group flex items-center gap-2.5 rounded-md py-[3px] pr-1',
          expandable && 'cursor-pointer focus-visible:outline-accent-500',
        )}
      >
        <span className="grid w-[14px] shrink-0 place-items-center">
          <StatusIcon status={node.status} />
        </span>
        <span className={cn('grid w-4 shrink-0 place-items-center', KIND_ACCENT[node.kind])}>
          {kindIcon(node.kind, node.tool, (node.metadata as FileOpMeta | undefined)?.op)}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2">
            <span className={cn('truncate text-[12.5px] font-medium leading-snug', titleColor)}>
              {node.title}
            </span>
            {node.status === 'running' && node.phase !== 'progress' && (
              <span className="inline-block h-1 w-1 animate-pulse-dot rounded-full bg-accent-500" />
            )}
          </div>
          {node.description && (
            <div
              className={cn(
                'truncate text-[11px] leading-snug',
                node.status === 'running' ? 'text-shimmer' : node.status === 'failed' ? 'text-red-400/80' : 'text-zinc-500',
              )}
            >
              {node.description}
            </div>
          )}
          <ProgressActivity node={node} />
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          {node.durationMs !== undefined && node.status !== 'running' && (
            <span className="font-mono text-[9.5px] tabular-nums text-zinc-600">
              {formatDuration(node.durationMs)}
            </span>
          )}
          {expandable && (
            <motion.span animate={{ rotate: open ? 90 : 0 }} transition={{ duration: 0.18 }}>
              <ChevronRight size={12} className="text-zinc-600 transition group-hover:text-zinc-400" />
            </motion.span>
          )}
        </div>
      </div>

      <ResultChips node={node} />
      {showError && <ActivityError node={node} onRetry={retryCommand} />}
      {node.kind === 'terminal' && node.status === 'failed' && !!node.metadata?.retryable && retryCommand && (
        <div className="mt-1.5">
          <button
            onClick={retryCommand}
            className="inline-flex items-center gap-1.5 rounded-md border border-white/10 bg-white/5 px-2.5 py-1 text-[10.5px] font-medium text-zinc-200 transition hover:border-white/20 hover:bg-white/10 active:scale-95"
          >
            {t('retry.command')}
          </button>
        </div>
      )}

      <AnimatePresence initial={false}>
        {expandable && open && (body || node.children.length > 0) && (
          <motion.div
            key="detail"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.26, ease: [0.22, 0.9, 0.3, 1] }}
            className="overflow-hidden"
          >
            <div className={cn(node.children.length > 0 && body ? '' : '', 'pl-[26px]')}>
              {body}
              {node.children.length > 0 && (
                <div className="ml-[-19px] mt-1 border-l border-white/7 pl-[18px]">
                  {node.children.map((c) => (
                    <ActivityItem key={c.id} node={c} ctx={ctx} depth={depth + 1} />
                  ))}
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

export { Chip };
