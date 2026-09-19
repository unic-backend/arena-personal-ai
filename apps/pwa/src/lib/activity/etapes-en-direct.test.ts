/* Ce qui reste visible pendant qu'un tour tourne.
 *
 * Demande du 19/09/2026 : « quand mon IA est en train de travailler il fait
 * seulement "Réflexion" ; je veux comme celle de Claude, ce que l'IA fait en
 * temps reel ». Le serveur annonce desormais ses etapes ; cote ecran, une
 * seule ligne qui se remplace les effacait au fur et a mesure.
 */
import { describe, expect, it } from 'vitest';
import type { ActivityNode } from './types';
import { ETAPES_VISIBLES_EN_DIRECT, etapesTerminees } from './types';

function noeud(partiel: Partial<ActivityNode> & { id: string }): ActivityNode {
  return {
    kind: 'tool',
    status: 'completed',
    phase: 'completed',
    title: partiel.id,
    startedAt: 0,
    children: [],
    ...partiel,
  } as ActivityNode;
}

describe('etapesTerminees', () => {
  it('garde ce qui est fini', () => {
    const noeuds = [
      noeud({ id: 'memoire', kind: 'database' }),
      noeud({ id: 'reponse', kind: 'response', status: 'running', phase: 'started' }),
    ];

    expect(etapesTerminees(noeuds).map((n) => n.id)).toEqual(['memoire']);
  });

  it('garde un echec — une etape ratee qu\'on cache est un echec qui ne se voit pas', () => {
    const noeuds = [noeud({ id: 'agent', status: 'failed', phase: 'failed' })];

    expect(etapesTerminees(noeuds).map((n) => n.id)).toEqual(['agent']);
  });

  it('ecarte les « reflexion » : ils ne nomment aucun travail', () => {
    const noeuds = [
      noeud({ id: 'flou', kind: 'thinking' }),
      noeud({ id: 'memoire', kind: 'database' }),
    ];

    expect(etapesTerminees(noeuds).map((n) => n.id)).toEqual(['memoire']);
  });

  it('borne la liste pour ne pas pousser sa question hors de l\'ecran', () => {
    const noeuds = Array.from({ length: 12 }, (_, i) => noeud({ id: `e${i}` }));

    const gardees = etapesTerminees(noeuds);

    expect(gardees).toHaveLength(ETAPES_VISIBLES_EN_DIRECT);
    expect(gardees.map((n) => n.id)).toEqual(['e8', 'e9', 'e10', 'e11']);
  });

  it('rend une liste vide quand rien n\'est encore fini', () => {
    const noeuds = [noeud({ id: 'en-cours', status: 'running', phase: 'started' })];

    expect(etapesTerminees(noeuds)).toEqual([]);
  });
});
