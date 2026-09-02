import { memo, useEffect, useRef, useState } from 'react';
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

/* Caracteres reveles par seconde pendant la marche. Un agent specialise
   (devis, email...) ne flux pas depuis le modele : il compose sa reponse
   entiere cote serveur puis l'envoie en un seul morceau — sans ceci, elle
   s'affichait d'un bloc, jamais mot a mot comme chez Claude ou GPT. Le
   proprietaire l'a signale le 02/09/2026 : "les reponses devraient venir
   comme en marchant". 200/s est un rythme de lecture, pas la vitesse reelle
   du reseau ou du modele — les deux peuvent etre plus rapides ou plus
   lents, la marche les lisse egalement. */
const CARACTERES_PAR_SECONDE = 200;

/** Revele `texte` progressivement plutot que d'un bloc, que le texte soit
 *  arrive au fil de l'eau (plusieurs petits morceaux) ou d'un coup (un
 *  agent specialise qui compose sa reponse entiere avant de l'envoyer) —
 *  les deux cas produisent la meme marche cote ecran, invisible depuis
 *  l'appelant.
 *
 *  Ne saute jamais directement a la fin quand le reseau dit "termine" :
 *  pour un agent specialise, le morceau complet et l'evenement "termine"
 *  arrivent quasi au meme instant — si la marche s'arretait la, elle
 *  n'aurait jamais le temps de jouer. `streaming` decide seulement si la
 *  marche continue apres avoir rattrape le texte disponible ; jamais si
 *  elle doit sauter en avant. */
function useTexteRevele(texte: string, streaming: boolean): string {
  const texteRef = useRef(texte);
  texteRef.current = texte;
  const streamingRef = useRef(streaming);
  streamingRef.current = streaming;

  // Vrai des que `streaming` a ete observe au moins une fois pendant la vie
  // de ce composant : decide si on anime DU TOUT. Un message deja termine
  // au montage (historique charge, F5 en cours de conversation) s'affiche
  // entier tout de suite — rejouer sa marche serait un theatre, pas une
  // information.
  const dejaEnMarcheRef = useRef(streaming);
  if (streaming) dejaEnMarcheRef.current = true;

  const [longueur, setLongueur] = useState(() => (streaming ? 0 : texte.length));
  const dernierTsRef = useRef<number | undefined>(undefined);

  useEffect(() => {
    if (!dejaEnMarcheRef.current) {
      setLongueur(texteRef.current.length);
      return;
    }
    let cadre: number | undefined;
    dernierTsRef.current = undefined;
    const marcher = (ts: number) => {
      const cible = texteRef.current.length;
      let arrete = false;
      setLongueur((n) => {
        if (n >= cible) {
          // Rattrape ET plus rien n'arrivera : la marche s'arrete d'elle-meme.
          arrete = !streamingRef.current;
          return n;
        }
        const dt = dernierTsRef.current ? ts - dernierTsRef.current : 16;
        const pas = Math.max(1, Math.round((CARACTERES_PAR_SECONDE * dt) / 1000));
        return Math.min(cible, n + pas);
      });
      dernierTsRef.current = ts;
      if (!arrete) cadre = requestAnimationFrame(marcher);
    };
    cadre = requestAnimationFrame(marcher);
    return () => {
      if (cadre !== undefined) cancelAnimationFrame(cadre);
    };
  }, [streaming]);

  return texte.slice(0, Math.min(longueur, texte.length));
}

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
  const visible = useTexteRevele(text, streaming);
  if (!text && streaming) {
    return <div className="stream-caret" aria-label="generating" />;
  }
  // Le curseur reste tant que la marche n'a pas rattrape le texte — meme si
  // le reseau a deja dit "termine" (agent specialise : les deux arrivent
  // quasi ensemble).
  const encoreEnMarche = visible.length < text.length;
  return (
    <div className={cn((streaming || encoreEnMarche) && 'stream-caret')}>
      <MarkdownLite text={visible} sources={sources} />
    </div>
  );
}
