/* Conversation mains libres (DEC-0164) : la logique qui decide sans navigateur. */
import { beforeEach, describe, expect, it } from 'vitest';

import type { ChatMessage } from '../store/chatStore';
import {
  DetecteurDeFinDeParole,
  REGLAGES_PAR_DEFAUT,
  detecterMotDeReveil,
  SILENCES_AVANT_ARRET,
  estOrdreDArret,
  niveauRms,
  reponseAPrononcer,
  useConversation,
} from './conversation';

function message(partiel: Partial<ChatMessage>): ChatMessage {
  return {
    id: partiel.id ?? 'm', role: partiel.role ?? 'assistant', text: partiel.text ?? '',
    live: partiel.live ?? '', status: partiel.status ?? 'done', activity: [],
    createdAt: 0, error: partiel.error,
  };
}

describe("l'ordre d'arret", () => {
  it.each(['Stop', 'stop.', 'Arrête', 'arrete !', "c'est tout", 'C’est tout', 'Merci Jarvis', 'au revoir', 'Merci Usman', 'Stop Usman'])(
    '« %s » arrete le mode', (phrase) => {
      expect(estOrdreDArret(phrase)).toBe(true);
    });

  it.each([
    'arrête la vidéo à 10 secondes', 'stop motion', 'quelle est la fin du film', '',
    // Finit par un mot d'arret, mais c'est une demande : la phrase ENTIERE compte.
    'comment dit-on stop', 'traduis au revoir',
  ])(
    '« %s » est une demande, pas un arret', (phrase) => {
      expect(estOrdreDArret(phrase)).toBe(false);
    });
});

describe('la fin de parole', () => {
  const { seuil, silenceMs, attenteMaxMs, dureeMaxMs } = REGLAGES_PAR_DEFAUT;

  it('une phrase suivie de silence se termine apres le delai de silence', () => {
    const d = new DetecteurDeFinDeParole();
    expect(d.observer(seuil * 3, 0)).toBe('parole');
    expect(d.observer(0, silenceMs - 100)).toBe('parole');
    expect(d.observer(0, silenceMs)).toBe('fin');
  });

  it("une courte pause au milieu de la phrase ne la coupe pas", () => {
    const d = new DetecteurDeFinDeParole();
    d.observer(seuil * 3, 0);
    d.observer(0, 800);
    expect(d.observer(seuil * 3, 1000)).toBe('parole');
    expect(d.observer(0, 1000 + silenceMs - 100)).toBe('parole');
  });

  it("personne ne parle : « rien », jamais une phrase vide envoyee a Whisper", () => {
    const d = new DetecteurDeFinDeParole();
    expect(d.observer(0, 0)).toBe('attente');
    expect(d.observer(seuil / 2, attenteMaxMs - 1)).toBe('attente');
    expect(d.observer(0, attenteMaxMs)).toBe('rien');
  });

  it('une phrase interminable est coupee a la duree maximale', () => {
    const d = new DetecteurDeFinDeParole();
    d.observer(seuil * 3, 0);
    expect(d.observer(seuil * 3, dureeMaxMs)).toBe('fin');
  });

  it('le niveau RMS mesure le son, pas son signe', () => {
    expect(niveauRms([])).toBe(0);
    expect(niveauRms([0.5, -0.5, 0.5, -0.5])).toBeCloseTo(0.5);
  });
});

describe('la reponse a prononcer', () => {
  const question = message({ id: 'q', role: 'user', text: 'Quelle heure ?' });

  it('attend que la reponse soit terminee', () => {
    const enCours = message({ id: 'r', status: 'streaming', live: 'Il est' });
    expect(reponseAPrononcer([question, enCours], 0)).toBeNull();
  });

  it('prononce la reponse terminee qui suit la question', () => {
    const faite = message({ id: 'r', status: 'done', text: 'Il est midi.' });
    expect(reponseAPrononcer([question, faite], 0)).toEqual({ id: 'r', texte: 'Il est midi.' });
  });

  it('ne prononce jamais une reponse plus ancienne que la question', () => {
    const ancienne = message({ id: 'a', status: 'done', text: 'Vieille reponse.' });
    expect(reponseAPrononcer([ancienne, question], 1)).toBeNull();
  });

  it('une reponse en erreur se prononce aussi : se taire ferait croire qu’il reflechit', () => {
    const echec = message({ id: 'r', status: 'error', error: 'Le modele ne repond pas.' });
    expect(reponseAPrononcer([question, echec], 0)).toEqual({ id: 'r', texte: 'Le modele ne repond pas.' });
  });
});

describe('le mot de reveil (DEC-0165)', () => {
  it.each([
    ['Jarvis', ''],
    ['Jarvis, quel temps fait-il ?', 'quel temps fait-il ?'],
    ['jarvis quelle heure est-il', 'quelle heure est-il'],
    ['Dis Jarvis, lance la musique', 'lance la musique'],
    ['Ok Jarvis', ''],
    ['Djarvis, bonjour', 'bonjour'],
    ['Jar vis, quelle date', 'quelle date'],
    ['Jervis !', ''],
    // DEC-0189 : « hey Usman », et les formes qu'une transcription francaise en donne
    ['Hey Usman, lis mes mails', 'lis mes mails'],
    ['Usman', ''],
    ['Ok Usman quelle heure est-il', 'quelle heure est-il'],
    ['Ousmane, mon briefing', 'mon briefing'],
    ['Hé Ousmane !', ''],
    ['Osman, bonjour', 'bonjour'],
    ['Ous mane, quelle date', 'quelle date'],
  ])('« %s » le reveille, et la demande est « %s »', (phrase, reste) => {
    expect(detecterMotDeReveil(phrase)).toEqual({ entendu: true, reste });
  });

  it.each([
    "J'ai vu Jarvis au cinema hier",   // le nom, mais pas en tete : une conversation
    "J'ai appele Ousmane ce matin",
    'Oui, mais demain',
    'Usine de Thiès',
    'quel temps fait-il',
    'Java est un langage',
    '',
  ])('« %s » ne le reveille pas', (phrase) => {
    expect(detecterMotDeReveil(phrase).entendu).toBe(false);
  });
});

describe("l'etat de la conversation", () => {
  beforeEach(() => useConversation.getState().couper());

  it(`s'arrete seul apres ${SILENCES_AVANT_ARRET} silences consecutifs`, () => {
    const etat = useConversation.getState();
    etat.demarrer();
    etat.ecouter();
    for (let i = 1; i < SILENCES_AVANT_ARRET; i += 1) {
      useConversation.getState().silence();
      expect(useConversation.getState().phase).toBe('ecoute');
    }
    useConversation.getState().silence();
    expect(useConversation.getState().phase).toBe('arret');
  });

  it('une question envoyee remet le compteur de silences a zero', () => {
    const etat = useConversation.getState();
    etat.demarrer();
    etat.ecouter();
    etat.silence();
    etat.reflechir(4);
    expect(useConversation.getState()).toMatchObject({ phase: 'reflexion', silences: 0, depuis: 4 });
  });

  it("la veille parle d'abord, et n'ouvre le micro qu'apres — jamais pendant « Jarvis »", () => {
    const etat = useConversation.getState();
    etat.activerVeille();
    expect(useConversation.getState()).toMatchObject({ phase: 'parole', reveil: true });
    useConversation.getState().finDeParole();
    expect(useConversation.getState().phase).toBe('veille');
  });

  it("avec la veille allumee, une conversation finie retourne en veille", () => {
    const etat = useConversation.getState();
    etat.activerVeille();
    etat.finDeParole();
    etat.parler();          // « Oui ? »
    etat.finDeParole();
    expect(useConversation.getState().phase).toBe('ecoute');
    for (let i = 0; i < SILENCES_AVANT_ARRET; i += 1) useConversation.getState().silence();
    expect(useConversation.getState()).toMatchObject({ phase: 'veille', reveil: true });
  });

  it('« stop » dit au revoir PUIS retourne en veille, ou s\'arrete sans veille', () => {
    const etat = useConversation.getState();
    etat.activerVeille();
    etat.finDeParole();
    etat.ecouter();
    etat.conclure();
    expect(useConversation.getState().phase).toBe('parole');
    useConversation.getState().finDeParole();
    expect(useConversation.getState().phase).toBe('veille');

    useConversation.getState().couper();
    useConversation.getState().demarrer();
    useConversation.getState().finDeParole();
    useConversation.getState().conclure();
    useConversation.getState().finDeParole();
    expect(useConversation.getState().phase).toBe('arret');
  });

  it('une erreur de micro eteint tout, veille comprise : pas de boucle muette', () => {
    const etat = useConversation.getState();
    etat.activerVeille();
    etat.arreter('not-allowed');
    expect(useConversation.getState()).toMatchObject({ phase: 'arret', reveil: false });
  });

  it('une fois arretee, rien ne la relance en douce', () => {
    const etat = useConversation.getState();
    etat.arreter('not-allowed');
    etat.ecouter();
    etat.parler();
    expect(useConversation.getState()).toMatchObject({ phase: 'arret', erreur: 'not-allowed' });
  });
});
