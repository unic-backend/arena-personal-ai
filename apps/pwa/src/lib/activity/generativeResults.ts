import type { SourceMeta } from './types';

export interface SourceCard {
  title: string;
  domain: string;
  url?: string;
  date?: string;
  excerpt?: string;
}

export function cartesSources(sources: SourceMeta[] | undefined): SourceCard[] {
  if (!sources?.length) return [];
  const vues = new Set<string>();
  const cartes: SourceCard[] = [];
  for (const source of sources) {
    const cle = source.url || `${source.domain || ''}|${source.title}`;
    if (vues.has(cle)) continue;
    vues.add(cle);
    cartes.push({
      title: source.title || source.domain || 'Source',
      domain: source.domain || '',
      url: source.url,
      date: source.date,
      excerpt: source.excerpt,
    });
  }
  return cartes;
}
