/* ─────────────────────────────────────────────────────────────
   Lanceur de tests de la PWA.

   Il n'y en avait aucun jusqu'au 03/09/2026, et `docs/REPRISE.md` le
   notait comme « un travail a part ». Entre-temps, le code qui decide
   si une demo du navigateur peut repondre a la place du serveur — donc
   se faire passer pour son IA — n'etait garde que par des tests Python
   qui LISENT le source TypeScript. Une garde qui lit du texte ne voit
   pas un comportement : elle voit une forme.

   `jsdom` est necessaire, pas decoratif : `backendStore` lit
   `localStorage` et s'abonne a l'evenement `online`. Sans navigateur
   simule, ces chemins-la ne s'executent pas du tout.
   ───────────────────────────────────────────────────────────── */
import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'jsdom',
    setupFiles: ['./vitest.setup.ts'],
    include: ['src/**/*.test.ts'],
    restoreMocks: true,
  },
});
