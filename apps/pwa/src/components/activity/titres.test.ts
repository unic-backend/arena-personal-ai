/* ─────────────────────────────────────────────────────────────
   Les titres d'une reponse s'affichent-ils comme des titres ?

   **Mesure du 15/09/2026, sur le telephone du proprietaire.** Une reponse
   du moteur de raisonnement est arrivee avec « #### 1️⃣ Identification » et
   « ## ✅ Solution finale » affiches AVEC leurs dieses, en plein texte.

   `parseBlocks` ne connaissait que `/^###\s+/`. `#`, `##` et `####` ne
   correspondaient a rien et tombaient dans le paragraphe courant — `####`
   n'etait meme pas attrape par erreur, la regex exigeant une espace apres
   exactement trois dieses.
   ───────────────────────────────────────────────────────────── */
import { describe, expect, it } from 'vitest';

/** La regle du parseur, isolee : quel niveau de titre pour cette ligne ? */
function niveauDeTitre(ligne: string): 2 | 3 | 4 | null {
  const titre = /^(#{1,6})\s+(.*)$/.exec(ligne);
  if (!titre) return null;
  const dieses = titre[1].length;
  return dieses <= 2 ? 2 : dieses === 3 ? 3 : 4;
}

describe('les titres markdown d\'une reponse', () => {
  it('reconnait tous les niveaux, pas seulement ###', () => {
    expect(niveauDeTitre('# Titre')).toBe(2);
    expect(niveauDeTitre('## Solution finale')).toBe(2);
    expect(niveauDeTitre('### Identification')).toBe(3);
    expect(niveauDeTitre('#### Discriminant')).toBe(4);
    expect(niveauDeTitre('##### Detail')).toBe(4);
  });

  it('les lignes exactes de la capture du proprietaire', () => {
    expect(niveauDeTitre('#### 1️⃣ Identification')).toBe(4);
    expect(niveauDeTitre('## ✅ Solution finale')).toBe(2);
  });

  it('ne prend pas un diese qui n\'ouvre pas un titre', () => {
    // Sans espace, ce n'est pas un titre : un mot-diese reste du texte.
    expect(niveauDeTitre('#chantier')).toBeNull();
    expect(niveauDeTitre('le #1 des BA13')).toBeNull();
    expect(niveauDeTitre('')).toBeNull();
  });
});
