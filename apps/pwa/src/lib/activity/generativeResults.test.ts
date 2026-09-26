import { describe, expect, it } from 'vitest';
import { cartesSources } from './generativeResults';

describe('cartesSources', () => {
  it('conserve uniquement les donnees sourcees et supprime les doublons URL', () => {
    const cartes = cartesSources([
      { title: 'Article A', domain: 'example.com', url: 'https://example.com/a', date: '2026-09-26', excerpt: 'Resume reel' },
      { title: 'Doublon', domain: 'example.com', url: 'https://example.com/a' },
      { title: 'Article B', domain: 'news.test', url: 'https://news.test/b' },
    ]);
    expect(cartes).toEqual([
      { title: 'Article A', domain: 'example.com', url: 'https://example.com/a', date: '2026-09-26', excerpt: 'Resume reel' },
      { title: 'Article B', domain: 'news.test', url: 'https://news.test/b', date: undefined, excerpt: undefined },
    ]);
  });

  it('ne fabrique aucune carte sans sources', () => {
    expect(cartesSources(undefined)).toEqual([]);
  });
});
