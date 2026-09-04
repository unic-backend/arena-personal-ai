/* ─────────────────────────────────────────────────────────────
   La regle voyage-t-elle ?

   **Le defaut le plus cher de ce depot n'est pas un bug : c'est une
   regle apprise a un endroit et jamais portee sur les autres.** Sept
   occurrences dans l'audit du 01/09/2026, une huitieme ici.

   Le 03/09, `chatStore` a appris qu'un envoi rate doit prevenir le
   panneau — sans quoi il reste vert sur une machine eteinte. Le 04/09,
   cinq autres modules parlaient encore au serveur en silence : la
   confirmation d'action, la dictee, la video (trois points) et les
   connecteurs.

   Ce test-ci est structurel, et il le dit : il verifie qu'un module qui
   prend une adresse sait signaler une panne. Il ne verifie PAS que
   l'appel est au bon endroit — c'est le role des tests de
   comportement, a cote. Les deux ensemble, parce qu'aucun des deux ne
   suffit : « une garde qui verifie qu'une piece existe ne verifie pas
   qu'elle est branchee ».
   ───────────────────────────────────────────────────────────── */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

// `process.cwd()` est `apps/pwa` : vitest y est lance. `import.meta.url` rend
// ici un chemin relatif au projet, pas au disque — premier essai : ENOENT '/src'.
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

/**
 * Modules autorises a prendre une adresse sans signaler de panne, avec la
 * raison. **Une exemption sans raison ecrite est une exemption qui sera
 * recopiee.**
 */
const EXEMPTES: Record<string, string> = {
  'lib/store/backendStore.ts':
    "c'est lui qui definit signalerSiPanne et qui sonde : il ne s'appelle pas lui-meme",
  'components/chat/ChatMessage.tsx':
    "il ne PARLE pas au serveur : il prend l'adresse pour fabriquer le href du lien "
    + "« Ouvrir le document » (04/09/2026, DEC-0041). Un lien qu'on tape navigue, il n'y "
    + "a ni fetch ni catch ou signaler quoi que ce soit — et un lien mort se voit dans "
    + "le navigateur, il ne part pas dans le vide en silence.",
};

describe('la regle du signalement de panne', () => {
  it('tout module qui prend une adresse sait signaler une panne', () => {
    const manquants: string[] = [];

    for (const chemin of sources(SRC)) {
      const texte = readFileSync(chemin, 'utf8');
      if (!texte.includes('activeRemoteCfg')) continue;

      const relatif = chemin.slice(chemin.indexOf('/src/') + 5);
      if (relatif in EXEMPTES) continue;
      if (!texte.includes('signalerSiPanne')) manquants.push(relatif);
    }

    expect(manquants,
      `Module(s) parlant au serveur sans jamais prevenir le panneau : ${manquants.join(', ')}. `
      + 'Sur une machine allumee 4 h par jour, ce silence laisse le panneau vert '
      + 'et envoie tout le reste dans le vide.').toEqual([]);
  });

  it('chaque exemption porte sa raison', () => {
    for (const [fichier, raison] of Object.entries(EXEMPTES)) {
      expect(raison.length, `${fichier} est exempte sans raison ecrite`).toBeGreaterThan(20);
    }
  });
});
