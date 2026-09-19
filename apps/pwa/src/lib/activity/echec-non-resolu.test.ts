/* Ce qui reste visible une fois la réponse écrite.
 *
 * Demande du 19/09/2026 : « ce travail devrait être apparent quand il
 * travaille ; après qu'il livre sa réponse il doit pas être très apparent ».
 * Le détail s'efface — sauf un échec que rien n'a rattrapé.
 */
import { describe, expect, it } from 'vitest';
import type { ActivityNode } from './types';
import { echecNonResolu } from './types';

function noeud(id: string, status: ActivityNode['status']): ActivityNode {
  return {
    id, kind: 'tool', status, phase: 'completed', title: id,
    startedAt: 0, children: [],
  } as ActivityNode;
}

describe('echecNonResolu', () => {
  it('rien à signaler quand tout a réussi', () => {
    expect(echecNonResolu([noeud('a', 'completed')], false)).toBe(false);
  });

  it('un échec en dernier reste visible', () => {
    expect(echecNonResolu([noeud('a', 'completed'), noeud('b', 'failed')], false))
      .toBe(true);
  });

  it('un échec rattrapé ensuite n\'en est plus un', () => {
    /* Le premier essai d'un build qui a fini par passer. */
    expect(echecNonResolu([noeud('a', 'failed'), noeud('b', 'completed')], false))
      .toBe(false);
  });

  it('pendant le travail, rien n\'est encore conclu', () => {
    expect(echecNonResolu([noeud('a', 'failed')], true)).toBe(false);
  });

  it('une liste vide ne signale rien', () => {
    expect(echecNonResolu([], false)).toBe(false);
  });
});
