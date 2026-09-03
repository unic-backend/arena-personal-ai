/* ─────────────────────────────────────────────────────────────
   Ce que jsdom n'implemente pas, et qu'il faut donc fournir.

   **Un bouchon ici ne cache jamais un defaut du code** : il comble un
   manque du navigateur simule. `matchMedia` existe dans tout navigateur
   reel depuis plus de dix ans ; jsdom ne l'a jamais implemente, et un
   module qui lit le theme du systeme leve donc a l'import.

   La regle : on bouche ce que le navigateur aurait fourni, jamais ce
   que le code doit produire. Un bouchon qui ferait passer un test sur
   une fonction d'ARENA serait un mensonge, pas une aide.
   ───────────────────────────────────────────────────────────── */

if (typeof window !== 'undefined' && !window.matchMedia) {
  window.matchMedia = ((requete: string) => ({
    matches: false,
    media: requete,
    onchange: null,
    addListener: () => {},      // deprecie, mais encore lu par des libs
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
}
