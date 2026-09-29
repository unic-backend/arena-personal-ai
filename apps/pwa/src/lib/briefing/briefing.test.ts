/* Le briefing du matin vient a lui (DEC-0168) : ce que l'application
   accepte d'afficher, et quand elle cesse de le montrer. */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { briefingDepuis, dejaVu, heureDeComposition, marquerVu } from '.';

const PRET = {
  pret: true,
  jour: '2026-09-29',
  compose_a: '2026-09-29T07:00',
  texte: '**Briefing du lundi 29 septembre**',
  rubriques: [
    { titre: 'Agenda', etat: 'NON_CONFIGURE', texte: 'Identifiants Google absents.' },
    { titre: 'Meteo', etat: 'OK', texte: 'Soleil [1].' },
  ],
};

async function brancher() {
  vi.resetModules();
  localStorage.setItem('usman.backend.v1', JSON.stringify({
    url: 'https://sa-machine.test', apiKey: 'k', enabled: true, urlSecours: '', apiKeySecours: '',
  }));
  const { useBackend } = await import('../store/backendStore');
  useBackend.setState({ status: 'online', serveurActif: 'principal' });
  return useBackend;
}

describe('la reponse du serveur', () => {
  it('un briefing pret se lit rubrique par rubrique, etat compris', () => {
    const b = briefingDepuis(PRET);
    expect(b?.jour).toBe('2026-09-29');
    expect(b?.rubriques.map((r) => r.etat)).toEqual(['NON_CONFIGURE', 'OK']);
  });

  it.each([
    ['rien de compose', { pret: false }],
    ['pas un objet', 'oups'],
    ['une rubrique sans etat connu', { ...PRET, rubriques: [{ titre: 'Agenda', etat: 'VIDE', texte: '' }] }],
    ['une rubrique sans texte', { ...PRET, rubriques: [{ titre: 'Agenda', etat: 'OK' }] }],
  ])('%s : rien ne s’affiche, jamais un briefing a moitie lu', (_, corps) => {
    expect(briefingDepuis(corps)).toBeNull();
  });

  it("l'heure de composition se lit sans fuseau ni locale", () => {
    expect(heureDeComposition('2026-09-29T07:00')).toBe('07:00');
    expect(heureDeComposition('')).toBe('');
  });
});

describe('une fois ferme', () => {
  beforeEach(() => localStorage.clear());

  it('il ne revient pas le meme jour, et revient le lendemain', () => {
    expect(dejaVu('2026-09-29')).toBe(false);
    marquerVu('2026-09-29');
    expect(dejaVu('2026-09-29')).toBe(true);
    expect(dejaVu('2026-09-30')).toBe(false);
  });
});

describe('ce que l’application demande au serveur', () => {
  beforeEach(() => localStorage.clear());

  it('seulement le briefing deja pret — jamais d’en composer un', async () => {
    await brancher();
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify(PRET)));
    vi.stubGlobal('fetch', fetch);

    const { briefingAMontrer } = await import('.');
    const b = await briefingAMontrer();

    expect(b?.rubriques).toHaveLength(2);
    expect(String(fetch.mock.calls[0][0])).toMatch(/\/api\/briefing\?seulement_pret=true$/);
  });

  it('un briefing deja ferme aujourd’hui ne se remontre pas', async () => {
    await brancher();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(PRET))));
    const { briefingAMontrer, marquerVu: vu } = await import('.');
    vu('2026-09-29');
    expect(await briefingAMontrer()).toBeNull();
  });

  it('un serveur injoignable : rien a l’ecran, mais le panneau apprend la panne', async () => {
    const magasin = await brancher();
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    const { briefingAMontrer } = await import('.');

    expect(await briefingAMontrer()).toBeNull();
    expect(magasin.getState().status).not.toBe('online');
  });
});
