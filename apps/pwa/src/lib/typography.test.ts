/* L'echelle de lecture, et la migration qui la fait arriver jusqu'a lui.
 *
 * Mesure du 19/09/2026, sur capture d'ecran de son telephone : le corps de
 * texte etait a 13 px et le plus GRAND reglage disponible valait 15 px —
 * sous les ~16-17 px de Claude a cote. Aucun reglage ne pouvait donc lui
 * donner ce qu'il demandait ; ce n'etait pas une preference mal reglee,
 * c'etait une echelle trop basse.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const KEY = 'usman.typography.v1';

/** Recharge le module pour de vrai.
 *
 *  Les preferences sont lues **une seule fois**, a l'import — c'est le
 *  comportement reel au demarrage de l'application. Sans `resetModules`, le
 *  second test relirait l'etat du premier et passerait sans rien mesurer. */
async function charger() {
  vi.resetModules();
  const { useTypography } = await import('./typography');
  return useTypography.getState();
}

beforeEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute('data-reading-size');
  document.documentElement.removeAttribute('data-reading-weight');
});

describe('les defauts', () => {
  it('ouvrent sur un texte plus grand et plus gras', async () => {
    const etat = await charger();

    expect(etat.size).toBe('comfortable');
    expect(etat.weight).toBe('medium');
  });

  it('sont poses sur la racine du document, pas seulement en memoire', async () => {
    await charger();

    expect(document.documentElement.dataset.readingSize).toBe('comfortable');
    expect(document.documentElement.dataset.readingWeight).toBe('medium');
  });
});

describe('la migration', () => {
  it('remplace une preference qui vaut exactement les anciens defauts', async () => {
    /* La sienne : enregistree parce qu'il n'a jamais ouvert le panneau, pas
       parce qu'il a choisi « regular ». Sans ce rattrapage, relever les
       defauts ne changeait rien sur le seul ecran qui compte. */
    localStorage.setItem(KEY, JSON.stringify({
      family: 'sans', size: 'comfortable', weight: 'regular', relaxed: true,
    }));

    const etat = await charger();

    expect(etat.weight).toBe('medium');
  });

  it('ne touche pas une preference reellement choisie', async () => {
    localStorage.setItem(KEY, JSON.stringify({
      family: 'serif', size: 'compact', weight: 'regular', relaxed: false,
    }));

    const etat = await charger();

    expect(etat).toMatchObject({
      family: 'serif', size: 'compact', weight: 'regular', relaxed: false,
    });
  });

  it('ne touche pas un seul cran deplace', async () => {
    localStorage.setItem(KEY, JSON.stringify({
      family: 'sans', size: 'compact', weight: 'regular', relaxed: true,
    }));

    const etat = await charger();

    expect(etat.size).toBe('compact');
    expect(etat.weight).toBe('regular');
  });
});

describe('le cran XL', () => {
  it('existe et se pose sur la racine', async () => {
    const etat = await charger();

    etat.setSize('xlarge');

    expect(document.documentElement.dataset.readingSize).toBe('xlarge');
  });
});
