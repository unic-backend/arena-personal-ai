/* Suivre le texte qui descend sous le bord de l'écran.
 *
 * Mesuré sur son téléphone le 19/09/2026 : « quand mon IA écrit et qu'il
 * descend en bas du téléphone, les écritures continuent en bas sans que je le
 * voie, je dois scroller pour suivre ».
 */
import { describe, expect, it, vi } from 'vitest';
import { suivreLaHauteur } from './suivre-la-hauteur';

/** Un ResizeObserver de test : on déclenche la croissance à la main. */
function fabriqueObservable() {
  const rappels: Array<() => void> = [];
  const observes: Element[] = [];
  let deconnecte = false;

  class Faux {
    constructor(rappel: () => void) { rappels.push(rappel); }
    observe(cible: Element) { observes.push(cible); }
    disconnect() { deconnecte = true; }
  }

  return {
    Faux: Faux as unknown as Parameters<typeof suivreLaHauteur>[2],
    grandir: () => rappels.forEach((r) => r()),
    observes,
    estDeconnecte: () => deconnecte,
  };
}

function conteneur(hauteur = 1000) {
  const el = document.createElement('div');
  el.appendChild(document.createElement('div'));
  Object.defineProperty(el, 'scrollHeight', { value: hauteur, configurable: true });
  el.scrollTop = 0;
  return el;
}

describe('suivreLaHauteur', () => {
  it('colle au bas quand la hauteur grandit', () => {
    const el = conteneur(1000);
    const o = fabriqueObservable();

    suivreLaHauteur(el, () => true, o.Faux);
    o.grandir();

    expect(el.scrollTop).toBe(1000);
  });

  it('ne bouge pas quand il a remonté lui-même', () => {
    const el = conteneur(1000);
    el.scrollTop = 200;
    const o = fabriqueObservable();

    suivreLaHauteur(el, () => false, o.Faux);
    o.grandir();

    expect(el.scrollTop).toBe(200);
  });

  it('consulte l\'ancrage à chaque fois, jamais une seule', () => {
    /* Remonter pendant qu'il écrit doit couper le suivi immédiatement. */
    const el = conteneur(1000);
    let ancre = true;
    const o = fabriqueObservable();

    suivreLaHauteur(el, () => ancre, o.Faux);
    o.grandir();
    expect(el.scrollTop).toBe(1000);

    ancre = false;
    el.scrollTop = 300;
    o.grandir();

    expect(el.scrollTop).toBe(300);
  });

  it('observe le CONTENU, pas le cadre qui ne change pas de taille', () => {
    const el = conteneur();
    el.appendChild(document.createElement('p'));
    const o = fabriqueObservable();

    suivreLaHauteur(el, () => true, o.Faux);

    expect(o.observes).toHaveLength(2);
    expect(o.observes).not.toContain(el);
  });

  it('rend de quoi arrêter d\'observer', () => {
    const o = fabriqueObservable();

    suivreLaHauteur(conteneur(), () => true, o.Faux)();

    expect(o.estDeconnecte()).toBe(true);
  });

  it('ne casse pas sans conteneur ni observateur', () => {
    expect(() => suivreLaHauteur(null, () => true)()).not.toThrow();
  });
});
