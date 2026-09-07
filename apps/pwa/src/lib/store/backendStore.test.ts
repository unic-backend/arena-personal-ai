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

//: Le budget des tests qui empruntent le chemin de REESSAI de la sonde.
//
//: Ces tests attendent pour de vrai : 3 tentatives x (800 + 2500 ms) par
//: serveur. Sur cette machine ils tiennent en ~3,3 s, mais le plafond par
//: defaut de vitest est de 5000 ms — moins de 1,7 s de marge, qu'un runner
//: charge mange sans difficulte. Mesure du 07/09/2026 : « le principal muet »
//: a echoue en CI a **5002 ms** pendant qu'il passait a 3311 ms ici.
//:
//: Ce n'etait donc pas un alea : c'est un budget qui n'avait jamais ete
//: dimensionne. Le voisin « les deux muets » portait deja cette correction
//: (20000 ms) et son arithmetique en commentaire ; elle n'avait simplement
//: pas ete appliquee aux trois autres. (Deux tests de plus l'avaient deja,
//: sous la forme du dernier argument `}, 20000)` — c'est `tsc` qui l'a
//: rappele quand j'ai voulu leur en donner un second.)
const BUDGET_REESSAI = 20000

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

  it('reessaie avant d\'abandonner', { timeout: BUDGET_REESSAI }, async () => {
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

  it('un echec ne debranche PAS le serveur', { timeout: BUDGET_REESSAI }, async () => {
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

describe('deux adresses, bascule automatique', () => {
  beforeEach(() => localStorage.clear());

  it('le principal repond : le secours n\'est jamais appele', async () => {
    // **L'ordre n'est pas un detail.** Sa machine d'abord : le modele y
    // tourne chez lui et rien ne part chez un tiers (DEC-0002). Sonder les
    // deux en parallele pourrait envoyer un message dehors alors que son PC
    // etait seulement lent.
    const ping = vi.fn().mockResolvedValue({ ok: true, latencyMs: 5, provider: 'ollama' });
    vi.doMock('../activity/remoteTransport', () => ({ pingBackend: ping }));

    const magasin = await magasinFrais();
    magasin.setState({
      url: 'https://mon-pc.test', urlSecours: 'https://railway.test', enabled: true,
    });
    await magasin.getState().test();

    expect(ping).toHaveBeenCalledTimes(1);
    expect(ping.mock.calls[0][0].url).toBe('https://mon-pc.test');
    expect(magasin.getState().serveurActif).toBe('principal');
    vi.doUnmock('../activity/remoteTransport');
  });

  it('le principal muet : le secours prend le relais', { timeout: BUDGET_REESSAI }, async () => {
    const ping = vi.fn(async (cfg: { url: string }) =>
      cfg.url.includes('railway')
        ? { ok: true, latencyMs: 40, provider: 'groq' }
        : { ok: false, latencyMs: 1, error: 'injoignable' });
    vi.doMock('../activity/remoteTransport', () => ({ pingBackend: ping }));

    const magasin = await magasinFrais();
    magasin.setState({
      url: 'https://mon-pc.test', urlSecours: 'https://railway.test', enabled: true,
    });
    await magasin.getState().test();

    expect(magasin.getState().status).toBe('online');
    expect(magasin.getState().serveurActif).toBe('secours');
    expect(magasin.getState().remoteProvider).toBe('groq');
    vi.doUnmock('../activity/remoteTransport');
  });

  // 2 serveurs x 3 tentatives x (800 + 2500 ms) : l'echec TOTAL prend ~13 s.
  // C'est le prix de la bascule, et il se paie une seule fois.
  it('les deux muets : aucun n\'est declare actif', { timeout: 20000 }, async () => {
    vi.doMock('../activity/remoteTransport', () => ({
      pingBackend: vi.fn().mockResolvedValue({ ok: false, latencyMs: 1, error: 'rien' }),
    }));

    const magasin = await magasinFrais();
    magasin.setState({
      url: 'https://mon-pc.test', urlSecours: 'https://railway.test', enabled: true,
    });
    await magasin.getState().test();

    expect(magasin.getState().status).toBe('error');
    expect(magasin.getState().serveurActif).toBeNull();
    // `enabled` ne bouge toujours pas : il dit ce qu'il veut, pas ce que le
    // reseau permet.
    expect(magasin.getState().enabled).toBe(true);
    vi.doUnmock('../activity/remoteTransport');
  });

  it('le chat parle a CELUI qui a repondu, pas au prefere', async () => {
    // Sans ca, chaque message partirait vers le PC eteint pendant que le
    // panneau affiche « en ligne » grace au secours.
    // `magasinFrais()` fait un `vi.resetModules()` : importer
    // `activeRemoteCfg` AVANT donnait une autre instance du module, donc un
    // autre magasin. Le test ecrivait dans l'un et lisait dans l'autre.
    vi.resetModules();
    const module = await import('./backendStore');
    const { activeRemoteCfg } = module;
    const magasin = module.useBackend;
    magasin.setState({
      url: 'https://mon-pc.test', apiKey: 'a',
      urlSecours: 'https://railway.test', apiKeySecours: 'b',
      enabled: true, serveurActif: 'secours',
    });

    expect(activeRemoteCfg()?.url).toBe('https://railway.test');
    expect(activeRemoteCfg()?.apiKey).toBe('b');
  });

  it('les deux adresses survivent au redemarrage', async () => {
    const magasin = await magasinFrais();
    magasin.getState().setUrl('https://mon-pc.test');
    magasin.getState().setUrlSecours('https://railway.test');

    const frais = await magasinFrais();
    expect(frais.getState().urlSecours).toBe('https://railway.test');
  });
});

describe('le PC s\'eteint pendant l\'usage', () => {
  beforeEach(() => localStorage.clear());

  it('un envoi rate declenche la bascule vers le secours', async () => {
    // **Le cas NORMAL, pas le cas rare** : son PC ne tourne qu'environ 4 h
    // par jour. Sans ce chemin, le panneau restait « en ligne » sur une
    // machine eteinte et chaque message suivant partait dans le vide.
    const ping = vi.fn(async (cfg: { url: string }) =>
      cfg.url.includes('railway')
        ? { ok: true, latencyMs: 30, provider: 'groq' }
        : { ok: false, latencyMs: 1, error: 'PC eteint' });
    vi.doMock('../activity/remoteTransport', () => ({ pingBackend: ping }));

    // **Par le vrai chemin.** Le premier essai appelait `signalerEchec`
    // directement : retirer l'appel depuis `chatStore` ne faisait alors
    // tomber aucun test, alors que c'est exactement le cablage qui manquait
    // avant ce correctif. Une garde qui verifie qu'une piece existe ne
    // verifie pas qu'elle est branchee.
    vi.resetModules();
    const magasinModule = await import('./backendStore');
    const { signalerSiPanne } = await import('./chatStore');
    const magasin = magasinModule.useBackend;
    magasin.setState({
      url: 'https://mon-pc.test', urlSecours: 'https://railway.test',
      enabled: true, status: 'online', serveurActif: 'principal',
    });

    signalerSiPanne(new TypeError('Failed to fetch'), true);
    await vi.waitFor(() => expect(magasin.getState().status).toBe('online'), { timeout: 15000 });

    expect(magasin.getState().serveurActif).toBe('secours');
    vi.doUnmock('../activity/remoteTransport');
  }, 20000);

  it('une annulation ne fait basculer personne', async () => {
    // « Stop » n'est pas une panne. Sans cette garde, chaque interruption
    // volontaire ferait changer de serveur.
    //
    // Premier essai de ce test : il importait `signalerSiPanne` et verifiait
    // qu'il etait `undefined` faute d'export. Ca ne mesurait rien du tout.
    // La fonction est donc exportee et appelee ici pour de vrai.
    vi.resetModules();
    const magasinModule = await import('./backendStore');
    const { signalerSiPanne } = await import('./chatStore');
    const magasin = magasinModule.useBackend;
    magasin.setState({
      url: 'https://mon-pc.test', enabled: true, status: 'online',
      serveurActif: 'principal',
    });

    const abandon = new DOMException('stop', 'AbortError');
    signalerSiPanne(abandon, true);

    expect(magasin.getState().status).toBe('online');
    expect(magasin.getState().serveurActif).toBe('principal');
  });

  it('un travail LOCAL qui echoue ne fait pas basculer', async () => {
    // Le montage video tourne sur l'appareil : sa panne ne dit rien du
    // serveur, et debrancher le PC pour ca serait absurde.
    vi.resetModules();
    const magasinModule = await import('./backendStore');
    const { signalerSiPanne } = await import('./chatStore');
    const magasin = magasinModule.useBackend;
    magasin.setState({ url: 'https://mon-pc.test', enabled: true, status: 'online' });

    signalerSiPanne(new Error('codec absent'), false);

    expect(magasin.getState().status).toBe('online');
  });

  it('sans serveur de secours, l\'echec reste un echec', async () => {
    // Rien n'est invente : pas de secours, pas de bascule.
    vi.doMock('../activity/remoteTransport', () => ({
      pingBackend: vi.fn().mockResolvedValue({ ok: false, latencyMs: 1, error: 'PC eteint' }),
    }));

    const magasin = await magasinFrais();
    magasin.setState({
      url: 'https://mon-pc.test', urlSecours: '', enabled: true, status: 'online',
    });

    magasin.getState().signalerEchec('Failed to fetch');
    await vi.waitFor(() => expect(magasin.getState().status).toBe('error'), { timeout: 15000 });

    expect(magasin.getState().serveurActif).toBeNull();
    vi.doUnmock('../activity/remoteTransport');
  }, 20000);
});

describe('la machine annonce son adresse', () => {
  beforeEach(() => localStorage.clear());

  /** L'annuaire repond, puis la machine annoncee repond. */
  function annuaireQuiConnaitLaMachine(adresseMachine: string) {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({ presente: true, adresse: adresseMachine }),
    })));
  }

  it('le telephone trouve la machine sans qu\'on colle une adresse', async () => {
    // **Le coeur du besoin** : son tunnel change de nom a chaque demarrage.
    // Sans ca, il recopiait une adresse plusieurs fois par semaine.
    annuaireQuiConnaitLaMachine('https://tunnel-du-jour.test');
    const ping = vi.fn(async (cfg: { url: string }) =>
      cfg.url.includes('tunnel-du-jour')
        ? { ok: true, latencyMs: 8, provider: 'ollama' }
        : { ok: false, latencyMs: 1, error: 'pas lui' });
    vi.doMock('../activity/remoteTransport', () => ({ pingBackend: ping }));

    const magasin = await magasinFrais();
    magasin.setState({
      url: '', urlSecours: 'https://railway.test', apiKeySecours: 'k', enabled: true,
    });
    await magasin.getState().test();

    expect(magasin.getState().status).toBe('online');
    expect(magasin.getState().urlAnnoncee).toBe('https://tunnel-du-jour.test');
    vi.doUnmock('../activity/remoteTransport');
    vi.unstubAllGlobals();
  });

  it('le chat parle a la machine annoncee, pas a l\'adresse de la veille', async () => {
    // **La garde qui compte.** Sans elle, la sonde reussissait sur la machine
    // du jour et chaque message partait vers l'adresse enregistree hier.
    vi.resetModules();
    const module = await import('./backendStore');
    module.useBackend.setState({
      url: 'https://tunnel-d-hier.test', apiKey: 'a',
      urlSecours: 'https://railway.test', apiKeySecours: 'b',
      enabled: true, serveurActif: 'principal',
      urlAnnoncee: 'https://tunnel-du-jour.test',
    });

    expect(module.activeRemoteCfg()?.url).toBe('https://tunnel-du-jour.test');
  });

  it('annuaire injoignable : on essaie quand meme ce qu\'on sait', async () => {
    // Ne pas savoir ou est la machine n'est pas une raison de ne rien tenter.
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('reseau'); }));
    vi.doMock('../activity/remoteTransport', () => ({
      pingBackend: vi.fn().mockResolvedValue({ ok: true, latencyMs: 20, provider: 'groq' }),
    }));

    const magasin = await magasinFrais();
    magasin.setState({ url: 'https://railway.test', enabled: true });
    await magasin.getState().test();

    expect(magasin.getState().status).toBe('online');
    expect(magasin.getState().urlAnnoncee).toBeNull();
    vi.doUnmock('../activity/remoteTransport');
    vi.unstubAllGlobals();
  });

  it('aucune machine annoncee : on retombe sur l\'adresse connue', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true, json: async () => ({ presente: false }),
    })));
    vi.doMock('../activity/remoteTransport', () => ({
      pingBackend: vi.fn().mockResolvedValue({ ok: true, latencyMs: 20, provider: 'groq' }),
    }));

    const magasin = await magasinFrais();
    magasin.setState({ url: 'https://railway.test', enabled: true });
    await magasin.getState().test();

    expect(magasin.getState().urlAnnoncee).toBeNull();
    expect(magasin.getState().status).toBe('online');
    vi.doUnmock('../activity/remoteTransport');
    vi.unstubAllGlobals();
  });
});
