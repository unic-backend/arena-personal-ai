/* ─────────────────────────────────────────────────────────────
   Le PC s'eteint pendant qu'il confirme.

   **Mesure du 04/09/2026.** La regle « un envoi rate previent le
   panneau » a ete posee le 03/09 dans `chatStore`, et nulle part
   ailleurs. Cinq autres modules parlent au serveur — dont celui-ci,
   qui porte le « oui » : la confirmation d'une action reelle.

   Concretement : il appuie sur Confirmer, sa machine vient de
   s'eteindre, l'ecran dit « le serveur n'a pas repondu » — et le
   panneau reste `online`. La veille ne demarre pas, le secours n'est
   jamais essaye, et tout ce qu'il fait ensuite part dans le vide
   jusqu'a ce qu'il rouvre le panneau lui-meme.

   Avec un PC allume quatre heures par jour, ce chemin est le cas
   normal.
   ───────────────────────────────────────────────────────────── */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const CLE = 'usman.backend.v1';

/** Un magasin branche sur une adresse, comme sur son telephone. */
async function brancher() {
  vi.resetModules();
  localStorage.setItem(CLE, JSON.stringify({
    url: 'https://sa-machine.test', apiKey: 'k', enabled: true,
    urlSecours: 'https://permanent.test', apiKeySecours: 'k2',
  }));
  const { useBackend } = await import('../store/backendStore');
  useBackend.setState({ status: 'online', serveurActif: 'principal' });
  return useBackend;
}

describe('confirmer une action pendant que la machine s\'eteint', () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it('un serveur injoignable fait passer le panneau en erreur', async () => {
    const magasin = await brancher();
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));

    const { confirmerAction } = await import('./confirmer');
    const resultat = await confirmerAction('action-42');

    expect(resultat.ok).toBe(false);
    // Le point du test : le panneau APPREND la panne. Sans ca, il reste
    // `online` sur une machine eteinte et rien ne bascule.
    expect(magasin.getState().status).not.toBe('online');
  });

  it('un refus du serveur n\'est PAS une panne de serveur', async () => {
    /** Il a repondu — il a dit non. Basculer de serveur sur un refus
     *  enverrait l'action suivante ailleurs pour une raison qui n'a
     *  rien a voir avec la liaison. */
    const magasin = await brancher();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false, status: 403,
      json: async () => ({ detail: 'Action expiree.' }),
    }));

    const { confirmerAction } = await import('./confirmer');
    const resultat = await confirmerAction('action-42');

    expect(resultat.ok).toBe(false);
    expect(resultat.message).toContain('expiree');
    expect(magasin.getState().status).toBe('online');
  });
});
