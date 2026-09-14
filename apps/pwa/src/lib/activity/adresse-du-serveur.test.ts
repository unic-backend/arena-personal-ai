/* ─────────────────────────────────────────────────────────────
   Une adresse sans schema n'est pas une adresse

   **Mesure du 14/09/2026, 03h41.** Le panneau affichait
   `BACKEND · INACCESSIBLE` et « Provider probe failed » alors que le
   serveur repondait `200` en 0,7 s. Le champ portait
   `arena-personal-ai-production.up.railway.app`, sans `https://`. Le
   navigateur l'a lue comme un chemin RELATIF : depuis la PWA servie par
   ce meme domaine, le sondage partait vers
   `…railway.app/arena-personal-ai-production.up.railway.app/health` et
   rendait 404.

   Deux defauts, pas un : l'adresse acceptee telle quelle, et un message
   d'echec qui ne designait ni l'adresse ni le 404 — assez vague pour
   envoyer chercher du cote de la cle.
   ───────────────────────────────────────────────────────────── */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative, sep } from 'node:path';

import { describe, expect, it } from 'vitest';

import { adresseDuServeur } from './remoteTransport';

const SRC = join(process.cwd(), 'src');

/** Tous les .ts/.tsx de `src`, sauf les tests. */
function sources(dossier: string): string[] {
  const trouves: string[] = [];
  for (const nom of readdirSync(dossier)) {
    const chemin = join(dossier, nom);
    if (statSync(chemin).isDirectory()) {
      trouves.push(...sources(chemin));
    } else if (/\.tsx?$/.test(nom) && !/\.test\.tsx?$/.test(nom)) {
      trouves.push(chemin);
    }
  }
  return trouves;
}

/** Le chemin relatif a `src`, toujours en `/` — portable, Windows compris. */
function cle(chemin: string): string {
  return relative(SRC, chemin).split(sep).join('/');
}

/**
 * Les deux facons d'ecrire une adresse sans passer par le normaliseur. Les
 * onze appelants les utilisaient toutes les deux avant le 14/09/2026.
 */
const BRUTS = [/cfg\.url\.replace\(/, /\$\{cfg\.url\}/];

/** Le module qui DEFINIT `adresseDuServeur` : il ne s'appelle pas lui-meme. */
const DEFINIT = 'lib/activity/remoteTransport.ts';

describe('adresseDuServeur', () => {
  it('ajoute https quand rien n\'est ecrit', () => {
    expect(adresseDuServeur('arena-personal-ai-production.up.railway.app'))
      .toBe('https://arena-personal-ai-production.up.railway.app');
  });

  it('ne touche pas a une adresse qui porte deja son schema', () => {
    expect(adresseDuServeur('https://exemple.test')).toBe('https://exemple.test');
    // `http` reste `http` : un serveur local n'est pas joignable en https, et
    // le forcer casserait le montage « ma machine » au lieu de le reparer.
    expect(adresseDuServeur('http://127.0.0.1:8000')).toBe('http://127.0.0.1:8000');
  });

  it('enleve les / finaux, y compris quand il faut aussi ajouter le schema', () => {
    expect(adresseDuServeur('https://exemple.test/')).toBe('https://exemple.test');
    expect(adresseDuServeur('exemple.test///')).toBe('https://exemple.test');
  });

  it('rend la chaine vide pour une saisie vide', () => {
    // Vide reste vide : c'est l'appelant qui decide quoi en faire. Rendre
    // `https://` serait une adresse qui ne designe rien.
    expect(adresseDuServeur('')).toBe('');
    expect(adresseDuServeur('   ')).toBe('');
  });

  it('coupe les espaces autour d\'une adresse collee', () => {
    expect(adresseDuServeur('  exemple.test  ')).toBe('https://exemple.test');
  });
});

describe('la regle de l\'adresse du serveur', () => {
  /**
   * **Une regle apprise a un endroit et jamais portee sur les autres est le
   * defaut le plus cher de ce depot** — c'est deja ce que dit
   * `regle-de-panne.test.ts`. Le 14/09/2026, onze appels composaient leur
   * adresse a la main : sondage, flux, dictee, televersement, capacites
   * video, projet video, connecteurs (cinq), confirmation d'action,
   * synchronisation des conversations, et le href du lien « Ouvrir le
   * document ». Chacun aurait produit le meme 404 silencieux.
   */
  it('aucun module ne compose une adresse a la main', () => {
    const fautifs: string[] = [];

    for (const chemin of sources(SRC)) {
      const relatif = cle(chemin);
      if (relatif === DEFINIT) continue;
      const texte = readFileSync(chemin, 'utf8');
      if (BRUTS.some((motif) => motif.test(texte))) fautifs.push(relatif);
    }

    expect(fautifs,
      `Module(s) composant une adresse sans passer par adresseDuServeur : ${fautifs.join(', ')}. `
      + 'Une adresse collee sans https:// devient un chemin relatif, et la requete '
      + 'part vers le domaine de la PWA au lieu du serveur.').toEqual([]);
  });
});
