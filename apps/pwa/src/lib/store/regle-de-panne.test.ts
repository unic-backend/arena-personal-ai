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
import { join, relative, sep } from 'node:path';

import { describe, expect, it } from 'vitest';

// `process.cwd()` est `apps/pwa` : vitest y est lance. `import.meta.url` rend
// ici un chemin relatif au projet, pas au disque — premier essai : ENOENT '/src'.
const SRC = join(process.cwd(), 'src');

/**
 * La cle d'un module dans `EXEMPTES` : son chemin relatif a `src`, toujours
 * ecrit avec des `/`.
 *
 * **Mesure du 14/09/2026.** Ce calcul etait `chemin.slice(chemin.indexOf('/src/') + 5)`.
 * Sur Windows — la machine du proprietaire — `join` rend des `\`, `indexOf('/src/')`
 * rend `-1`, et la cle devenait `sers\saer\...\ChatMessage.tsx`. Aucune exemption
 * ne pouvait plus correspondre : le test signalait `ChatMessage.tsx` alors que le
 * depot l'exempte nommement, et affichait un chemin abime dans son message.
 * Vert sur Linux, rouge sur Windows, pour une raison que rien ne disait.
 */
function cle(chemin: string): string {
  return relative(SRC, chemin).split(sep).join('/');
}

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

      const relatif = cle(chemin);
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

  /**
   * **Une exemption qui ne designe aucun fichier n'exempte rien**, et personne
   * ne s'en apercoit : le test reste vert, et le module qu'elle croit couvrir
   * est soit absent, soit signale sous une autre cle.
   *
   * C'est exactement ce qui arrivait sur Windows avant le 14/09/2026 — la cle
   * calculee ne ressemblait a aucune entree, l'exemption de `ChatMessage.tsx`
   * ne s'appliquait jamais, et le test echouait en montrant un chemin abime.
   * Ce test-ci tient la derivation de la cle, la ou les deux autres ne tiennent
   * que son resultat.
   */
  it('chaque exemption designe un fichier qui existe vraiment', () => {
    const connus = new Set(sources(SRC).map(cle));

    for (const fichier of Object.keys(EXEMPTES)) {
      expect(connus.has(fichier),
        `${fichier} est exempte mais ne figure pas parmi les sources de src/. `
        + 'Soit le fichier a ete renomme ou supprime et l\'exemption est morte, '
        + 'soit le calcul de la cle ne rend pas ce que EXEMPTES attend.').toBe(true);
    }
  });
});
