/* ─────────────────────────────────────────────────────────────
   La coupure subie, et celle qu'il a choisie.

   **Mesure du 03/09/2026.** Une seule sonde ratee ecrivait
   `enabled: false` et l'enregistrait. Un tunnel, un changement
   d'antenne, et son IA restait injoignable jusqu'a ce qu'il rouvre le
   panneau. C'est ce mecanisme qui l'a fait parler a une demo pendant
   une heure sans le savoir.

   Ces tests EXECUTENT le magasin. Les tests Python equivalents lisaient
   le source : ils voyaient `debrancheParLui` ecrit quelque part, pas
   l'etat rendu au demarrage suivant.
   ───────────────────────────────────────────────────────────── */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const CLE = 'usman.backend.v1';

/** Recharge le module : `load()` ne tourne qu'a l'import. */
async function magasinFrais() {
  vi.resetModules();
  return (await import('./backendStore')).useBackend;
}

describe('reprise apres une coupure subie', () => {
  beforeEach(() => localStorage.clear());

  it('une adresse debranchee SANS signature revient branchee', async () => {
    // L'ancien defaut ecrivait exactement ceci sur son telephone.
    localStorage.setItem(CLE, JSON.stringify({
      url: 'https://son-serveur.test', apiKey: 'k', enabled: false,
    }));

    const magasin = await magasinFrais();

    expect(magasin.getState().enabled).toBe(true);
    expect(magasin.getState().url).toBe('https://son-serveur.test');
  });

  it('une coupure SIGNEE tient au redemarrage', async () => {
    // Le bouton « Deconnecter » : son choix, pas un accident.
    localStorage.setItem(CLE, JSON.stringify({
      url: 'https://son-serveur.test', apiKey: '', enabled: false,
      debrancheParLui: true,
    }));

    const magasin = await magasinFrais();

    expect(magasin.getState().enabled).toBe(false);
  });

  it('sans adresse enregistree, rien n\'est branche', async () => {
    const magasin = await magasinFrais();

    expect(magasin.getState().enabled).toBe(false);
    expect(magasin.getState().url).toBe('');
  });
});

describe('le bouton Deconnecter', () => {
  beforeEach(() => localStorage.clear());

  it('signe sa coupure, a l\'ecran ET pour le prochain demarrage', async () => {
    const magasin = await magasinFrais();
    magasin.setState({ url: 'https://son-serveur.test', enabled: true, status: 'online' });

    magasin.getState().disconnect();

    expect(magasin.getState().enabled).toBe(false);
    const garde = JSON.parse(localStorage.getItem(CLE) ?? '{}');
    expect(garde.debrancheParLui).toBe(true);
  });
});

describe('la sonde', () => {
  beforeEach(() => localStorage.clear());

  it('reessaie avant d\'abandonner', async () => {
    // Une coupure passagere ne doit plus coûter une deconnexion.
    const magasin = await magasinFrais();
    magasin.setState({ url: 'https://son-serveur.test', enabled: true });

    const appels = vi.fn().mockRejectedValue(new Error('reseau'));
    vi.doMock('../activity/remoteTransport', () => ({ pingBackend: appels }));

    const frais = await magasinFrais();
    frais.setState({ url: 'https://son-serveur.test', enabled: true });
    await frais.getState().test();

    expect(appels.mock.calls.length).toBeGreaterThan(1);
    vi.doUnmock('../activity/remoteTransport');
  });

  it('un echec ne debranche PAS le serveur', async () => {
    vi.doMock('../activity/remoteTransport', () => ({
      pingBackend: vi.fn().mockResolvedValue({ ok: false, latencyMs: 1, error: 'HTTP 502' }),
    }));
    const magasin = await magasinFrais();
    magasin.setState({ url: 'https://son-serveur.test', enabled: true });

    await magasin.getState().test();

    // `enabled` dit ce que le proprietaire veut ; `status` dit l'etat
    // du reseau. Les confondre est ce qui l'a laisse deconnecte.
    expect(magasin.getState().enabled).toBe(true);
    expect(magasin.getState().status).toBe('error');
    expect(magasin.getState().error).toContain('502');
    vi.doUnmock('../activity/remoteTransport');
  });
});
