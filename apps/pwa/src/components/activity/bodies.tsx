import { motion } from 'framer-motion';
import { RotateCcw, AlertTriangle } from 'lucide-react';
import type { ActivityNode, FileOpMeta, SourceMeta } from '../../lib/activity/types';
import { DomainMark } from './StatusIcon';
import { useI18n } from '../../lib/i18n';
import { cn } from '../../utils/cn';

/* ═── shared chips ──╚ */

export function Chip({ children, tone = 'zinc' }: { children: React.ReactNode; tone?: 'zinc' | 'green' | 'red' | 'accent' }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 font-mono text-[10px] leading-none',
        tone === 'zinc' && 'border-white/8 bg-white/4 text-zinc-400',
        tone === 'green' && 'border-emerald-400/20 bg-emerald-400/8 text-emerald-300',
        tone === 'red' && 'border-red-400/20 bg-red-400/8 text-red-300',
        tone === 'accent' && 'border-accent-500/25 bg-accent-500/10 text-accent-300',
      )}
    >
      {children}
    </span>
  );
}

/* ═── structured result summary (never raw JSON) ──╚ */

export function ResultChips({ node }: { node: ActivityNode }) {
  const out = node.output as Record<string, unknown> | undefined;
  const chips: React.ReactNode[] = [];
  if (!out) return null;

  if (typeof out.result_count === 'number') chips.push(<Chip key="rc" tone="accent">{out.result_count} results</Chip>);
  if (Array.isArray(out.sources)) chips.push(<Chip key="sc" tone="accent">{out.sources.length} sources</Chip>);
  if (typeof out.files === 'number') chips.push(<Chip key="fc">{out.files} files</Chip>);
  if (typeof out.lines === 'number') chips.push(<Chip key="lc">{Number(out.lines).toLocaleString()} lines</Chip>);
  if (typeof out.dependencies === 'number') chips.push(<Chip key="dc">{out.dependencies} deps</Chip>);
  if (typeof out.result === 'string') chips.push(<Chip key="res" tone="green">{out.result}</Chip>);
  if (out.totals && typeof out.totals === 'object') {
    const t = out.totals as { passed: number; failed: number; total: number };
    chips.push(<Chip key="tp" tone="green">{t.passed} passed</Chip>);
    if (t.failed > 0) chips.push(<Chip key="tf" tone="red">{t.failed} failed</Chip>);
  }
  if (typeof out.exitCode === 'number') {
    chips.push(
      <Chip key="ec" tone={out.exitCode === 0 ? 'green' : 'red'}>exit {out.exitCode}</Chip>,
    );
  }
  if (!chips.length) return null;
  return <div className="mt-1.5 flex flex-wrap gap-1">{chips}</div>;
}

/* ═── progress (only shown when the backend reports real numbers) ──╚ */

export function ProgressActivity({ node }: { node: ActivityNode }) {
  const p = node.progress;
  if (!p || p.total <= 0) return null;
  const pct = Math.min(100, Math.round((p.done / p.total) * 100));
  return (
    <div className="mt-2">
      <div className="h-[3px] w-full overflow-hidden rounded-full bg-white/6">
        <motion.div
          className={cn(
            'h-full rounded-full',
            node.status === 'completed' ? 'bg-emerald-400/80' : 'bg-accent-500',
          )}
          initial={false}
          animate={{ width: `${pct}%` }}
          transition={{ type: 'spring', stiffness: 160, damping: 26 }}
        />
      </div>
      <div className="mt-1 flex justify-between font-mono text-[10px] text-zinc-500">
        <span>{p.done} / {p.total} {p.unit}</span>
        <span>{pct}%</span>
      </div>
    </div>
  );
}

/* ═── terminal ──╚ */

interface TermOut {
  command?: string;
  stdout?: string[];
  stderr?: string;
  exitCode?: number;
  diagnostics?: Array<{ file: string; line: number; code: string; message: string }>;
}

export function TerminalActivity({ node }: { node: ActivityNode }) {
  const input = node.input as { command?: string } | undefined;
  const out = node.output as TermOut | undefined;
  const cmd = input?.command ?? out?.command;
  const { t } = useI18n();
  if (!cmd && !out) return null;
  const failed = node.status === 'failed';
  return (
    <div className="mt-2 overflow-hidden rounded-lg border border-white/8 bg-[#0c0c0e]">
      {cmd && (
        <div className="flex items-center gap-2 border-b border-white/6 px-3 py-1.5">
          <span className="font-mono text-[10px] text-zinc-600">$</span>
          <span className="font-mono text-[11px] text-zinc-200">{cmd}</span>
        </div>
      )}
      <div className="max-h-44 overflow-y-auto px-3 py-2 font-mono text-[10.5px] leading-relaxed scroll-slim">
        {out?.stdout?.map((l, i) => (
          <div key={i} className={cn('whitespace-pre-wrap break-all', l.startsWith('✗') ? 'text-red-300/90' : l.startsWith('✓') ? 'text-emerald-300/80' : 'text-zinc-400')}>{l || ' '}</div>
        ))}
        {out?.stderr?.split('\n').map((l, i) => (
          <div key={`e${i}`} className="whitespace-pre-wrap break-all text-red-300/90">{l}</div>
        ))}
        {node.status === 'running' && <div className="text-zinc-600">{t('term.waiting')}</div>}
      </div>
      {(out?.exitCode !== undefined || node.status === 'running') && (
        <div className="flex items-center justify-between border-t border-white/6 px-3 py-1.5">
          <span className="font-mono text-[9.5px] uppercase tracking-wider text-zinc-600">
            {failed ? t('term.failed') : node.status === 'running' ? t('term.running') : t('term.exited')}
          </span>
          {out?.exitCode !== undefined && <Chip tone={out.exitCode === 0 ? 'green' : 'red'}>exit {out.exitCode}</Chip>}
        </div>
      )}
    </div>
  );
}

/* ═── code execution ──╚ */

export function CodeExecutionActivity({ node }: { node: ActivityNode }) {
  const input = node.input as { language?: string; code?: string } | undefined;
  const out = node.output as
    | { stdout?: Array<{ level: string; text: string }>; error?: string; durationMs?: number; language?: string }
    | undefined;
  const { t } = useI18n();
  if (!input?.code) return null;
  return (
    <div className="mt-2 space-y-1.5">
      <div className="overflow-hidden rounded-lg border border-white/8 bg-[#0c0c0e]">
        <div className="flex items-center justify-between border-b border-white/6 px-3 py-1.5">
          <span className="font-mono text-[9.5px] uppercase tracking-wider text-accent-300/80">{input.language ?? 'code'}</span>
          {out?.durationMs !== undefined && (
            <span className="font-mono text-[9.5px] text-zinc-600">{out.durationMs.toFixed(1)}ms</span>
          )}
        </div>
        <pre className="max-h-40 overflow-y-auto px-3 py-2 font-mono text-[10.5px] leading-relaxed text-zinc-300 scroll-slim">
          {input.code}
        </pre>
      </div>
      {(out?.stdout || out?.error) && (
        <div className="overflow-hidden rounded-lg border border-white/8 bg-[#0c0c0e]">
          <div className="border-b border-white/6 px-3 py-1 font-mono text-[9.5px] uppercase tracking-wider text-zinc-600">{t('code.output')}</div>
          <div className="max-h-32 overflow-y-auto px-3 py-2 font-mono text-[10.5px] leading-relaxed scroll-slim">
            {out?.stdout?.map((l, i) => (
              <div key={i} className={cn(l.level === 'error' ? 'text-red-300/90' : l.level === 'warn' ? 'text-amber-300/90' : 'text-zinc-300')}>{l.text}</div>
            ))}
            {out?.error && <div className="text-red-300/90">{out.error}</div>}
          </div>
        </div>
      )}
    </div>
  );
}

/* ═── web search body ──╚ */

export function SearchActivity({ node }: { node: ActivityNode }) {
  const input = node.input as { query?: string } | undefined;
  const out = node.output as
    | { query?: string; result_count?: number; results?: Array<{ title: string; domain: string; date?: string }> }
    | undefined;
  const { t } = useI18n();
  const query = input?.query ?? out?.query;
  return (
    <div className="mt-2 space-y-2">
      {query && (
        <div className="font-mono text-[11px] text-zinc-400">
          <span className="text-zinc-600">{t('search.query')}&nbsp;</span>
          <span className="rounded-md border border-white/8 bg-white/4 px-2 py-0.5 text-zinc-200">“{query}”</span>
        </div>
      )}
      {out?.results && out.results.length > 0 && (
        <div className="overflow-hidden rounded-lg border border-white/8">
          {out.results.slice(0, 6).map((r, i) => (
            <div
              key={i}
              className={cn(
                'flex items-center gap-2.5 px-3 py-1.5',
                i !== 0 && 'border-t border-white/5',
              )}
            >
              <DomainMark domain={r.domain} />
              <div className="min-w-0 flex-1">
                <div className="truncate text-[11px] text-zinc-300">{r.title}</div>
                <div className="truncate font-mono text-[9.5px] text-zinc-600">{r.domain}{r.date ? ` · ${r.date}` : ''}</div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ═── file op body ──╚ */

export function FileActivity({ node }: { node: ActivityNode }) {
  const meta = node.metadata as (FileOpMeta & Record<string, unknown>) | undefined;
  if (!meta?.path) return null;
  return (
    <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1">
      <span className="rounded-md border border-white/8 bg-white/4 px-1.5 py-0.5 font-mono text-[10px] text-zinc-300">
        {meta.op} · {meta.path}
      </span>
      {(meta.added !== undefined || meta.removed !== undefined) && (
        <span className="flex gap-1">
          {!!meta.added && <Chip tone="green">+{meta.added}</Chip>}
          {!!meta.removed && <Chip tone="red">−{meta.removed}</Chip>}
        </span>
      )}
      {meta.bytes !== undefined && <Chip>{formatBytes(meta.bytes)}</Chip>}
    </div>
  );
}

function formatBytes(b: number) {
  return b < 1024 ? `${b} B` : `${(b / 1024).toFixed(1)} kB`;
}

/* ═── source card (browser child) ──╚ */

export function SourceRow({ node }: { node: ActivityNode }) {
  const source = node.metadata?.source as SourceMeta | undefined;
  return (
    <div className="mt-1.5 flex items-start gap-2.5 rounded-lg border border-white/6 bg-white/[0.025] px-2.5 py-2">
      <DomainMark domain={source?.domain ?? node.title} />
      <div className="min-w-0">
        <div className="truncate text-[11px] leading-tight text-zinc-200">{source?.title ?? node.description}</div>
        <div className="mt-0.5 flex items-center gap-1.5 font-mono text-[9.5px] text-zinc-600">
          <span>{source?.domain ?? node.title}</span>
          {source?.date && <><span>·</span><span>{source.date}</span></>}
        </div>
        {source?.excerpt && (
          <div className="mt-1 line-clamp-2 text-[10.5px] leading-snug text-zinc-500">{source.excerpt}</div>
        )}
      </div>
    </div>
  );
}

/* ═── diagnostics list (analysis) ──╚ */

export function DiagnosticsActivity({ node }: { node: ActivityNode }) {
  const out = node.output as { diagnostics?: Array<{ file: string; line: number; code: string; message: string }> } | undefined;
  if (!out?.diagnostics?.length) return null;
  return (
    <div className="mt-2 space-y-1">
      {out.diagnostics.map((d, i) => (
        <div key={i} className="flex items-start gap-2 rounded-lg border border-red-400/12 bg-red-400/[0.04] px-2.5 py-1.5">
          <AlertTriangle size={11} className="mt-0.5 shrink-0 text-red-400" />
          <div className="min-w-0 font-mono text-[10px] leading-relaxed">
            <span className="text-zinc-300">{d.file}:{d.line}</span>
            <span className="text-zinc-600"> {d.code} </span>
            <span className="text-zinc-500">{d.message}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

/* ═── video body — probe meta, real thumbnails, downloadable clip ──╚ */

interface VideoOut {
  video?: boolean;
  durationLabel?: string;
  sizeLabel?: string;
  width?: number;
  height?: number;
  name?: string;
  thumbs?: Array<{ ts: number; dataUrl: string }>;
  download?: { url: string; name: string; sizeLabel: string };
  startLabel?: string;
  endLabel?: string;
}

function fmtTs(ts: number) {
  const m = Math.floor(ts / 60);
  const s = Math.floor(ts % 60);
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

export function VideoActivity({ node }: { node: ActivityNode }) {
  const out = node.output as VideoOut | undefined;
  if (!out) return null;
  return (
    <div className="mt-2 space-y-2">
      {(out.durationLabel || out.width) && (
        <div className="flex flex-wrap gap-1">
          {out.durationLabel && <Chip>◷ {out.durationLabel}</Chip>}
          {out.width ? <Chip>{out.width}×{out.height}</Chip> : null}
          {out.sizeLabel && <Chip>{out.sizeLabel}</Chip>}
        </div>
      )}
      {out.thumbs && out.thumbs.length > 0 && (
        <div className="flex gap-1.5 overflow-x-auto scroll-slim pb-1">
          {out.thumbs.map((th, i) => (
            <div key={i} className="relative shrink-0 overflow-hidden rounded-md border border-white/10">
              <img src={th.dataUrl} alt={`frame ${i + 1}`} className="h-[54px] w-[96px] object-cover" />
              <span className="absolute bottom-0.5 right-0.5 rounded bg-black/70 px-1 font-mono text-[8px] text-zinc-200">
                {fmtTs(th.ts)}
              </span>
            </div>
          ))}
        </div>
      )}
      {out.download && node.status === 'completed' && (
        <motion.a
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          href={out.download.url}
          download={out.download.name}
          className="inline-flex items-center gap-2 rounded-lg border border-accent-500/35 bg-accent-500/12 px-3 py-1.5 text-[11px] font-medium text-accent-300 transition hover:bg-accent-500/22 active:scale-[0.98]"
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
          {out.download.name} · {out.download.sizeLabel}
        </motion.a>
      )}
      {out.startLabel && (
        <div className="font-mono text-[10px] text-zinc-500">
          {out.startLabel} → {out.endLabel}
        </div>
      )}
    </div>
  );
}

/* ═── plan checklist ──╚ */

export function PlanActivity({ node }: { node: ActivityNode }) {
  const steps = node.metadata?.steps as string[] | undefined;
  if (!steps?.length) return null;
  return (
    <ol className="mt-1.5 space-y-0.5">
      {steps.map((s, i) => (
        <li key={i} className="flex items-center gap-2 font-mono text-[10.5px] text-zinc-500">
          <span className="grid h-3.5 w-3.5 shrink-0 place-items-center rounded border border-white/8 bg-white/4 text-[8.5px] text-zinc-400">{i + 1}</span>
          {s}
        </li>
      ))}
    </ol>
  );
}

/* ═── error + retry ──╚ */

export function ActivityError({ node, onRetry }: { node: ActivityNode; onRetry?: () => void }) {
  const { t } = useI18n();
  const retryable = !!node.metadata?.retryable && !!onRetry;
  return (
    <motion.div
      initial={{ opacity: 0, y: 3 }}
      animate={{ opacity: 1, y: 0 }}
      className="mt-2 flex items-center gap-2.5 rounded-lg border border-red-400/15 bg-red-400/[0.05] px-3 py-2"
    >
      <AlertTriangle size={12} className="shrink-0 text-red-400" />
      <span className="min-w-0 flex-1 truncate text-[11px] text-red-200/90">
        {node.description ?? 'The operation failed'}
      </span>
      {retryable && (
        <button
          onClick={onRetry}
          className="inline-flex shrink-0 items-center gap-1 rounded-md border border-white/10 bg-white/5 px-2 py-1 text-[10px] font-medium text-zinc-200 transition hover:border-white/20 hover:bg-white/10 active:scale-95"
        >
          <RotateCcw size={10} />
          {t('retry')}
        </button>
      )}
    </motion.div>
  );
}
