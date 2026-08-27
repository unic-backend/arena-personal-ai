import { memo } from 'react';
import type { SourceMeta } from '../../lib/activity/types';
import { cn } from '../../utils/cn';

/* ── inline: **bold**, *italic*, ~~strike~~, `code`, [n] citations ── */
function renderInline(str: string, sources: SourceMeta[] | undefined, keyBase: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*)|(~~[^~]+~~)|(\*[^*]+\*)|(`[^`]+`)|(\[(\d{1,2})\])/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let k = 0;
  while ((m = re.exec(str))) {
    if (m.index > last) out.push(str.slice(last, m.index));
    if (m[1]) {
      out.push(<strong key={`${keyBase}-b${k++}`}>{m[1].slice(2, -2)}</strong>);
    } else if (m[2]) {
      out.push(<del key={`${keyBase}-d${k++}`} className="text-zinc-500">{m[2].slice(2, -2)}</del>);
    } else if (m[3]) {
      out.push(<em key={`${keyBase}-i${k++}`}>{m[3].slice(1, -1)}</em>);
    } else if (m[4]) {
      out.push(<code key={`${keyBase}-c${k++}`} className="inline">{m[4].slice(1, -1)}</code>);
    } else if (m[5]) {
      const idx = parseInt(m[6], 10);
      const src = sources?.[idx - 1];
      out.push(
        <span
          key={`${keyBase}-s${k++}`}
          className="cite-chip"
          title={src ? `${src.title} — ${src.domain}${src.date ? ` · ${src.date}` : ''}` : `source ${idx}`}
        >
          {idx}
        </span>,
      );
    }
    last = m.index + m[0].length;
  }
  if (last < str.length) out.push(str.slice(last));
  return out;
}

/* ── blocks ── */
type Block =
  | { t: 'p'; text: string }
  | { t: 'h3'; text: string }
  | { t: 'pre'; text: string }
  | { t: 'quote'; text: string }
  | { t: 'ul'; items: string[] }
  | { t: 'ol'; items: string[] }
  | { t: 'hr' };

function parseBlocks(text: string): Block[] {
  const lines = text.split('\n');
  const blocks: Block[] = [];
  let i = 0;
  let buf: string[] = [];
  const flush = () => {
    const t = buf.join('\n').trim();
    if (t) blocks.push({ t: 'p', text: t });
    buf = [];
  };
  while (i < lines.length) {
    const line = lines[i];
    if (line.startsWith('```')) {
      flush();
      const code: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith('```')) code.push(lines[i++]);
      i++;
      blocks.push({ t: 'pre', text: code.join('\n') });
      continue;
    }
    if (/^###\s+/.test(line)) { flush(); blocks.push({ t: 'h3', text: line.replace(/^###\s+/, '') }); i++; continue; }
    if (/^>\s?/.test(line)) {
      flush();
      const q: string[] = [];
      while (i < lines.length && /^>\s?/.test(lines[i])) q.push(lines[i++].replace(/^>\s?/, ''));
      blocks.push({ t: 'quote', text: q.join(' ') });
      continue;
    }
    if (/^-\s+/.test(line)) {
      flush();
      const items: string[] = [];
      while (i < lines.length && /^-\s+/.test(lines[i])) items.push(lines[i++].replace(/^-\s+/, ''));
      blocks.push({ t: 'ul', items });
      continue;
    }
    if (/^\d+\.\s+/.test(line)) {
      flush();
      const items: string[] = [];
      while (i < lines.length && /^\d+\.\s+/.test(lines[i])) items.push(lines[i++].replace(/^\d+\.\s+/, ''));
      blocks.push({ t: 'ol', items });
      continue;
    }
    if (/^---+$/.test(line.trim())) { flush(); blocks.push({ t: 'hr' }); i++; continue; }
    if (line.trim() === '') { flush(); i++; continue; }
    buf.push(line);
    i++;
  }
  flush();
  return blocks;
}

export const MarkdownLite = memo(function MarkdownLite({
  text,
  sources,
}: {
  text: string;
  sources?: SourceMeta[];
}) {
  const blocks = parseBlocks(text);
  return (
    <div className="md text-zinc-300">
      {blocks.map((b, i) => {
        switch (b.t) {
          case 'h3': return <h3 key={i}>{renderInline(b.text, sources, `h${i}`)}</h3>;
          case 'pre': return <pre key={i} className="scroll-slim">{b.text}</pre>;
          case 'quote': return <blockquote key={i}>{renderInline(b.text, sources, `q${i}`)}</blockquote>;
          case 'ul': return <ul key={i}>{b.items.map((it, j) => <li key={j}>{renderInline(it, sources, `u${i}-${j}`)}</li>)}</ul>;
          case 'ol': return <ol key={i}>{b.items.map((it, j) => <li key={j}>{renderInline(it, sources, `o${i}-${j}`)}</li>)}</ol>;
          case 'hr': return <hr key={i} />;
          default: return <p key={i}>{renderInline(b.text, sources, `p${i}`)}</p>;
        }
      })}
    </div>
  );
});

/* ── response with the blinking stream caret while tokens arrive ── */
export function StreamingResponse({
  text,
  streaming,
  sources,
}: {
  text: string;
  streaming: boolean;
  sources?: SourceMeta[];
}) {
  if (!text && streaming) {
    return <div className="stream-caret" aria-label="generating" />;
  }
  return (
    <div className={cn(streaming && 'stream-caret')}>
      <MarkdownLite text={text} sources={sources} />
    </div>
  );
}
