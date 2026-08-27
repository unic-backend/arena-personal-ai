import {
  ActivityKind, ActivityStatus, FileOpMeta,
} from '../../lib/activity/types';
import { getConnector } from '../../lib/connectors/catalog';
import {
  Search, FileText, FilePlus2, FilePenLine, FileX2, FileSearch, FolderSearch,
  TerminalSquare, Code2, Globe, Database, Calculator, ScanSearch, Sparkles,
  ListChecks, BrainCircuit, AlertTriangle, X, Check, Ban, CircleDashed,
  ArrowRightLeft, FileUp, FileDown, Wrench, AppWindow, BookOpenText,
  Clapperboard, Scissors, Images, Headphones, FileCheck2,
} from 'lucide-react';
import { cn } from '../../utils/cn';

/* ── status glyphs ── */

export function StatusIcon({ status, size = 12 }: { status: ActivityStatus; size?: number }) {
  switch (status) {
    case 'running':
      return <span className="activity-spinner" style={{ width: size, height: size }} />;
    case 'completed':
      return (
        <span className="grid place-items-center rounded-full bg-emerald-400/12 text-emerald-400" style={{ width: size + 2, height: size + 2 }}>
          <Check size={size - 2} strokeWidth={3.2} />
        </span>
      );
    case 'failed':
      return (
        <span className="grid place-items-center rounded-full bg-red-400/12 text-red-400" style={{ width: size + 2, height: size + 2 }}>
          <X size={size - 2} strokeWidth={3.2} />
        </span>
      );
    case 'cancelled':
      return (
        <span className="grid place-items-center rounded-full bg-zinc-500/15 text-zinc-500" style={{ width: size + 2, height: size + 2 }}>
          <Ban size={size - 3} strokeWidth={2.6} />
        </span>
      );
    default:
      return <CircleDashed size={size} className="text-zinc-600" />;
  }
}

/* ── kind / tool glyphs ── */

export function kindIcon(kind: ActivityKind, tool?: string, op?: FileOpMeta['op']) {
  const cls = 'shrink-0';
  if (op) {
    switch (op) {
      case 'read': return <BookOpenText size={13} className={cls} />;
      case 'create': return <FilePlus2 size={13} className={cls} />;
      case 'edit': return <FilePenLine size={13} className={cls} />;
      case 'delete': return <FileX2 size={13} className={cls} />;
      case 'rename': case 'move': return <ArrowRightLeft size={13} className={cls} />;
      case 'search': return <FileSearch size={13} className={cls} />;
      case 'parse': return <FileText size={13} className={cls} />;
      case 'upload': return <FileUp size={13} className={cls} />;
      case 'download': return <FileDown size={13} className={cls} />;
    }
  }
  if (tool) {
    if (tool.startsWith('model_')) return <BrainCircuit size={13} className={cls} />;
    // events emitted by your backend for a granted connector (tool: "conn_gmail")
    if (tool.startsWith('conn_')) {
      const def = getConnector(tool.slice(5));
      if (def) {
        const ConnIcon = def.icon;
        return <ConnIcon size={13} className={cls} />;
      }
    }
    switch (tool) {
      case 'web_search': return <Search size={13} className={cls} />;
      case 'browser': return <AppWindow size={13} className={cls} />;
      case 'vfs_scan': return <FolderSearch size={13} className={cls} />;
      case 'terminal': return <TerminalSquare size={13} className={cls} />;
      case 'code_runner': return <Code2 size={13} className={cls} />;
      case 'calculator': return <Calculator size={13} className={cls} />;
      case 'analysis': return <ScanSearch size={13} className={cls} />;
      case 'attachment_upload': case 'file_uploader': return <FileUp size={13} className={cls} />;
      case 'attachment_inspector': return <FileCheck2 size={13} className={cls} />;
      case 'image_inspector': return <Images size={13} className={cls} />;
      case 'audio_inspector': return <Headphones size={13} className={cls} />;
      case 'pdf_inspector': case 'document_inspector': return <FileText size={13} className={cls} />;
      case 'video_probe': return <Clapperboard size={13} className={cls} />;
      case 'video_frames': return <Images size={13} className={cls} />;
      case 'video_editor': return <Scissors size={13} className={cls} />;
      case 'memory_vault': return <Database size={13} className={cls} />;
    }
  }
  switch (kind) {
    case 'thinking': return <BrainCircuit size={13} className={cls} />;
    case 'planning': return <ListChecks size={13} className={cls} />;
    case 'search': return <Search size={13} className={cls} />;
    case 'file': return <FileText size={13} className={cls} />;
    case 'terminal': return <TerminalSquare size={13} className={cls} />;
    case 'code': return <Code2 size={13} className={cls} />;
    case 'browser': return <Globe size={13} className={cls} />;
    case 'database': return <Database size={13} className={cls} />;
    case 'calculation': return <Calculator size={13} className={cls} />;
    case 'analysis': return <ScanSearch size={13} className={cls} />;
    case 'response': return <Sparkles size={13} className={cls} />;
    case 'error': return <AlertTriangle size={13} className={cls} />;
    default: return <Wrench size={13} className={cls} />;
  }
}

export const KIND_ACCENT: Record<ActivityKind, string> = {
  thinking: 'text-violet-300/90',
  planning: 'text-sky-300/90',
  tool: 'text-zinc-400',
  search: 'text-amber-300/90',
  file: 'text-sky-300/80',
  terminal: 'text-emerald-300/90',
  code: 'text-cyan-300/90',
  browser: 'text-amber-300/80',
  database: 'text-fuchsia-300/80',
  calculation: 'text-lime-300/90',
  analysis: 'text-violet-300/80',
  video: 'text-rose-300/90',
  response: 'text-accent-400',
  error: 'text-red-400',
};

/* deterministic letter-mark for a source domain (no external favicon calls) */
export function DomainMark({ domain, className }: { domain: string; className?: string }) {
  let h = 0;
  for (let i = 0; i < domain.length; i++) h = (h * 31 + domain.charCodeAt(i)) % 360;
  const letter = domain.replace(/^(www\.)?/, '')[0]?.toUpperCase() ?? '?';
  return (
    <span
      className={cn('grid shrink-0 place-items-center rounded-md text-[9px] font-semibold text-white/90', className)}
      style={{
        width: 18, height: 18,
        background: `linear-gradient(135deg, hsl(${h} 45% 32%), hsl(${(h + 40) % 360} 45% 22%))`,
      }}
    >
      {letter}
    </span>
  );
}

export { X, Check };
