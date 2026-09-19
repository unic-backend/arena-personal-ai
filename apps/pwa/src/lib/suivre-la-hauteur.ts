/* Garder le bas du fil visible pendant qu'il grandit.
 *
 * **Mesuré sur son téléphone le 19/09/2026** : « quand mon IA écrit et qu'il
 * descend en bas du téléphone, les écritures continuent en bas sans que je le
 * voie, je dois scroller pour suivre ».
 *
 * La cause n'est pas le défilement automatique, qui existe et marche : il se
 * déclenche sur les changements de DONNÉES (un jeton reçu, une étape
 * annoncée). Or le texte n'apparaît pas quand il arrive — il est révélé
 * lettre par lettre par `useTexteRevele` (200 caractères/seconde), dans un
 * état local au composant qui l'affiche. La hauteur grandit donc pendant des
 * secondes sans qu'aucune donnée ne change, et la page reste où elle était.
 *
 * Suivre la HAUTEUR plutôt que ce qui la cause rattrape aussi une image qui
 * finit de charger et un bloc qui se déplie.
 */

/** Ce que ce module attend d'un observateur de taille. */
export type FabriqueObservateur = new (rappel: () => void) => {
  observe(cible: Element): void;
  disconnect(): void;
};

/**
 * Colle le conteneur à son bas tant que `estAncre()` dit oui.
 *
 * @param conteneur l'élément qui défile.
 * @param estAncre consulté à CHAQUE changement de hauteur, jamais mémorisé :
 *   remonter volontairement doit couper le suivi tout de suite.
 * @param Observateur injectable pour les tests ; `ResizeObserver` par défaut.
 * @returns de quoi arrêter d'observer. Une fonction vide quand il n'y a rien
 *   à observer — l'appelant n'a pas à distinguer les deux cas.
 */
export function suivreLaHauteur(
  conteneur: HTMLElement | null,
  estAncre: () => boolean,
  Observateur?: FabriqueObservateur,
): () => void {
  const Fabrique = Observateur
    ?? (typeof ResizeObserver !== 'undefined'
      ? (ResizeObserver as unknown as FabriqueObservateur)
      : undefined);
  if (!conteneur || !Fabrique) return () => {};

  const observateur = new Fabrique(() => {
    if (estAncre()) conteneur.scrollTop = conteneur.scrollHeight;
  });

  // Le conteneur défilant ne change pas de taille : c'est son CONTENU qui
  // grandit. On observe donc ses enfants, pas son cadre.
  for (const enfant of Array.from(conteneur.children)) observateur.observe(enfant);

  return () => observateur.disconnect();
}
