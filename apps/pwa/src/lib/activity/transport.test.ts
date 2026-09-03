/* ─────────────────────────────────────────────────────────────
   Ce que le chat fait quand le serveur ne repond pas.

   **Mesure du 03/09/2026, 01:36.** Le proprietaire ecrit « Bonjour ».
   Son serveur etait decroche, et une demo integree au navigateur lui a
   repondu — signee *Usman* — en promettant « execution terminal
   reelle » sur un projet invente. Rien a l'ecran ne la distinguait de
   son IA.

   Des tests Python gardaient deja cette regle en LISANT ce fichier.
   Ceux-ci l'EXECUTENT : ils appellent le transport et regardent ce
   qu'il rend. La difference n'est pas theorique — une garde qui lit du
   texte voit une forme, pas un comportement.
   ───────────────────────────────────────────────────────────── */
import { beforeEach, describe, expect, it } from 'vitest';

import { choisirTransport, localTransport, offlineTransport } from './transport';
import { useBackend } from '../store/backendStore';

async function collecter(gen: AsyncGenerator<unknown>) {
  const morceaux: unknown[] = [];
  for await (const morceau of gen) morceaux.push(morceau);
  return morceaux;
}

describe('choisirTransport', () => {
  it('sans serveur, ne rend jamais la voie sur appareil', () => {
    expect(choisirTransport(null)).toBe(offlineTransport);
  });

  it('sur appareil (video), reste local meme sans serveur', () => {
    // Le montage video tourne vraiment ici : le retirer avec la demo
    // aurait emporte une capacite reelle.
    expect(choisirTransport(null, true)).toBe(localTransport);
  });

  it('avec un serveur, ne passe pas par la voie sur appareil', () => {
    const transport = choisirTransport({ url: 'https://exemple.test' });
    expect(transport).not.toBe(localTransport);
    expect(transport).not.toBe(offlineTransport);
  });
});

describe('offlineTransport', () => {
  beforeEach(() => {
    localStorage.clear();
    useBackend.setState({ url: '', apiKey: '', enabled: false, status: 'local', error: undefined });
  });

  it('ne produit AUCUN texte', async () => {
    // Le coeur du correctif : il refuse. Rendre ne serait-ce qu'un
    // jeton remettrait quelque chose a la place du serveur.
    await expect(collecter(offlineTransport.run(
      { text: 'Bonjour' } as never, {} as never, new AbortController().signal,
    ))).rejects.toThrow();
  });

  it('distingue « aucun serveur enregistre » de « serveur muet »', async () => {
    const sansServeur = offlineTransport.run(
      { text: 'x' } as never, {} as never, new AbortController().signal);
    await expect(collecter(sansServeur)).rejects.toThrow('BACKEND_ABSENT');

    useBackend.setState({ url: 'https://exemple.test', error: 'timeout' });
    const muet = offlineTransport.run(
      { text: 'x' } as never, {} as never, new AbortController().signal);
    await expect(collecter(muet)).rejects.toThrow('BACKEND_OFFLINE::timeout');
  });

  it('porte la raison mesuree, pas un message generique', async () => {
    useBackend.setState({ url: 'https://exemple.test', error: 'HTTP 502' });
    const flux = offlineTransport.run(
      { text: 'x' } as never, {} as never, new AbortController().signal);

    await expect(collecter(flux)).rejects.toThrow(/502/);
  });
});
