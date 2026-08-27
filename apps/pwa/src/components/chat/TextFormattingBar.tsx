import type { RefObject } from 'react';
import {
  Bold, Code2, Heading3, Italic, List, ListOrdered, Quote, Strikethrough,
} from 'lucide-react';
import { useI18n } from '../../lib/i18n';

export type FormatAction =
  | 'bold'
  | 'italic'
  | 'strike'
  | 'heading'
  | 'bullet'
  | 'ordered'
  | 'quote'
  | 'code';

interface Props {
  textarea: RefObject<HTMLTextAreaElement | null>;
  value: string;
  setValue(value: string): void;
}

function lineRange(value: string, start: number, end: number) {
  const nextBreak = value.indexOf('\n', end);
  return {
    start: value.lastIndexOf('\n', Math.max(0, start - 1)) + 1,
    end: nextBreak === -1 ? value.length : nextBreak,
  };
}

export function applyTextFormat(
  action: FormatAction,
  textarea: HTMLTextAreaElement,
  value: string,
): { value: string; start: number; end: number } {
  const selectedStart = textarea.selectionStart;
  const selectedEnd = textarea.selectionEnd;
  const selected = value.slice(selectedStart, selectedEnd);

  const wrap = (before: string, after = before, fallback = 'text') => {
    const inner = selected || fallback;
    return {
      value: value.slice(0, selectedStart) + before + inner + after + value.slice(selectedEnd),
      start: selectedStart + before.length,
      end: selectedStart + before.length + inner.length,
    };
  };

  if (action === 'bold') return wrap('**', '**', 'bold text');
  if (action === 'italic') return wrap('*', '*', 'italic text');
  if (action === 'strike') return wrap('~~', '~~', 'struck text');
  if (action === 'code') {
    return selected.includes('\n')
      ? wrap('```\n', '\n```', 'code')
      : wrap('`', '`', 'code');
  }

  const range = lineRange(value, selectedStart, selectedEnd);
  const block = value.slice(range.start, range.end);
  const lines = (block || (action === 'heading' ? 'Title' : 'Text')).split('\n');
  const transformed = lines.map((line, i) => {
    const clean = line.replace(/^(?:###\s+|>\s+|-\s+|\d+\.\s+)/, '');
    if (action === 'heading') return `### ${clean}`;
    if (action === 'quote') return `> ${clean}`;
    if (action === 'bullet') return `- ${clean}`;
    return `${i + 1}. ${clean}`;
  }).join('\n');
  return {
    value: value.slice(0, range.start) + transformed + value.slice(range.end),
    start: range.start,
    end: range.start + transformed.length,
  };
}

export function TextFormattingBar({ textarea, value, setValue }: Props) {
  const { t } = useI18n();
  const items: Array<{ action: FormatAction; label: string; icon: React.ReactNode }> = [
    { action: 'bold', label: t('format.bold'), icon: <Bold size={13} /> },
    { action: 'italic', label: t('format.italic'), icon: <Italic size={13} /> },
    { action: 'strike', label: t('format.strike'), icon: <Strikethrough size={13} /> },
    { action: 'heading', label: t('format.heading'), icon: <Heading3 size={14} /> },
    { action: 'bullet', label: t('format.bullets'), icon: <List size={14} /> },
    { action: 'ordered', label: t('format.ordered'), icon: <ListOrdered size={14} /> },
    { action: 'quote', label: t('format.quote'), icon: <Quote size={13} /> },
    { action: 'code', label: t('format.code'), icon: <Code2 size={14} /> },
  ];

  const run = (action: FormatAction) => {
    const el = textarea.current;
    if (!el) return;
    const result = applyTextFormat(action, el, value);
    setValue(result.value);
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(result.start, result.end);
    });
  };

  return (
    <div className="flex items-center gap-0.5 overflow-x-auto border-b border-white/6 px-2 py-1 scroll-slim">
      <span className="shrink-0 px-1.5 font-serif text-[13px] text-zinc-500">Aa</span>
      <span className="mr-1 h-4 w-px shrink-0 bg-white/8" />
      {items.map((item) => (
        <button
          key={item.action}
          type="button"
          title={item.label}
          aria-label={item.label}
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => run(item.action)}
          className="grid h-7 w-7 shrink-0 place-items-center rounded-md text-zinc-500 transition hover:bg-white/6 hover:text-zinc-100 active:scale-90"
        >
          {item.icon}
        </button>
      ))}
      <span className="ml-auto hidden shrink-0 px-2 font-mono text-[8.5px] text-zinc-700 sm:block">
        {t('format.markdown')}
      </span>
    </div>
  );
}