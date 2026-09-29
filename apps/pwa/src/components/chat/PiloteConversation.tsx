/* ─────────────────────────────────────────────────────────────
   Pilote de la conversation mains libres (DEC-0164).

   N'affiche rien : il enchaine les briques existantes selon la phase de
   `useConversation` — ecoute (dictee a fin automatique), reflexion (la
   question est partie, on attend la reponse TERMINEE), parole (lecture a
   voix haute), puis de nouveau ecoute. En veille (DEC-0165), il attend
   « Jarvis » avant d'entrer dans ce cycle.
   ───────────────────────────────────────────────────────────── */

import { useEffect, useRef, useState } from 'react';

import { useI18n } from '../../lib/i18n';
import { isSpeechSynthesisSupported, useDictation, useSpeech } from '../../lib/speech';
import {
  detecterMotDeReveil, estOrdreDArret, reponseAPrononcer, useConversation,
} from '../../lib/speech/conversation';
import type { ChatMessage } from '../../lib/store/chatStore';

/** Une lecture qui n'a pas commence dans ce delai ne commencera pas
 *  (voix absente, synthese bloquee) : on reprend l'ecoute plutot que rester muet. */
const DEMARRAGE_PAROLE_MAX_MS = 5000;

/** En veille, erreurs passageres toleree d'affilee avant de tout eteindre. */
const ERREURS_EN_VEILLE_MAX = 5;
const PAUSE_APRES_ERREUR_MS = 2000;

export function PiloteConversation({
  messages,
  running,
  send,
}: {
  messages: ChatMessage[];
  running: boolean;
  send: (texte: string) => void;
}) {
  const {
    phase, reveil, depuis, finDeParole, conclure, reflechir, parler, arreter, silence,
  } = useConversation();
  const erreursEnVeille = useRef(0);
  const { startDictation, isListening, isTranscribing } = useDictation();
  const { speak, speakingMessageId } = useSpeech();
  const { t, locale } = useI18n();
  const [tour, setTour] = useState(0);
  const ecouteLancee = useRef(false);
  const aCommenceAParler = useRef(false);
  const messagesRef = useRef(messages);
  messagesRef.current = messages;

  // Veille : tant qu'elle est allumee, l'ecran reste allume — un telephone
  // qui se verrouille coupe le micro du navigateur, et la veille n'entendrait
  // plus rien sans que rien ne le dise (DEC-0165).
  useEffect(() => {
    const nav = navigator as Navigator & {
      wakeLock?: { request(type: 'screen'): Promise<{ release(): Promise<void> }> };
    };
    if (!reveil || !nav.wakeLock) return;
    let verrou: { release(): Promise<void> } | null = null;
    let fini = false;
    const demander = async () => {
      try {
        verrou = await nav.wakeLock!.request('screen');
      } catch {
        /* refuse (batterie faible, onglet cache) : la veille continue sans */
      }
    };
    const surVisible = () => {
      if (!fini && document.visibilityState === 'visible') void demander();
    };
    void demander();
    document.addEventListener('visibilitychange', surVisible);
    return () => {
      fini = true;
      document.removeEventListener('visibilitychange', surVisible);
      void verrou?.release().catch(() => undefined);
    };
  }, [reveil]);

  // Ecoute (une phrase, puis la dictee s'arrete seule au silence), ou veille
  // (chaque phrase est ecoutee, seules celles qui commencent par « Jarvis »
  // comptent).
  useEffect(() => {
    if (phase !== 'ecoute' && phase !== 'veille') {
      ecouteLancee.current = false;
      return;
    }
    if (ecouteLancee.current || isListening || isTranscribing) return;
    ecouteLancee.current = true;
    const enVeille = phase === 'veille';

    const reprendre = () => {
      ecouteLancee.current = false;
      setTour((n) => n + 1);
    };
    const repondreOui = () => {
      aCommenceAParler.current = false;
      parler();
      speak('jarvis-oui', t('conversation.oui'), locale);
    };

    startDictation(
      locale,
      (finale, intermediaire) => {
        const texte = finale.trim();
        if (!texte) {
          // Resultat intermediaire du navigateur : la phrase continue.
          if (intermediaire.trim()) return;
          // Whisper n'a rien entendu d'utile : c'est un silence, pas une
          // attente sans fin sur un micro deja ferme.
          if (!enVeille) silence();
          reprendre();
          return;
        }
        if (enVeille) {
          const { entendu, reste } = detecterMotDeReveil(texte);
          // Une phrase sans « Jarvis » ne le concerne pas : rien n'est envoye.
          if (!entendu || estOrdreDArret(reste)) {
            reprendre();
            return;
          }
          erreursEnVeille.current = 0;
          if (!reste) {
            repondreOui();
            return;
          }
          reflechir(messagesRef.current.length);
          send(reste);
          return;
        }
        if (estOrdreDArret(texte)) {
          aCommenceAParler.current = false;
          conclure();
          speak('jarvis-au-revoir', t('conversation.aurevoir'), locale);
          return;
        }
        reflechir(messagesRef.current.length);
        send(texte);
      },
      (code) => {
        if (code === 'no-speech') {
          if (!enVeille) silence();
          reprendre();
          return;
        }
        // En veille, une panne passagere (onglet cache, transcription en
        // echec) ne doit pas tout eteindre : on reessaie, sans boucler.
        const definitif = code === 'not-allowed' || code === 'permission-denied';
        if (enVeille && !definitif && erreursEnVeille.current < ERREURS_EN_VEILLE_MAX) {
          erreursEnVeille.current += 1;
          window.setTimeout(reprendre, PAUSE_APRES_ERREUR_MS);
          return;
        }
        erreursEnVeille.current = 0;
        arreter(code);
      },
      { finAutomatique: true },
    );
  }, [phase, tour, isListening, isTranscribing, locale, startDictation, speak, t,
      arreter, conclure, reflechir, silence, send, parler]);

  // Reflexion : on attend la reponse TERMINEE, puis on la lit.
  useEffect(() => {
    if (phase !== 'reflexion' || running) return;
    const reponse = reponseAPrononcer(messages, depuis);
    if (!reponse) return;
    aCommenceAParler.current = false;
    parler();
    speak(reponse.id, reponse.texte || t('conversation.sansReponse'), locale);
  }, [phase, running, messages, depuis, parler, speak, t, locale]);

  // Parole : quand la lecture s'acheve, on ecoute de nouveau (ou on retourne
  // en veille apres l'annonce de la veille).
  useEffect(() => {
    if (phase !== 'parole') return;
    if (!isSpeechSynthesisSupported()) {
      finDeParole();
      return;
    }
    if (speakingMessageId) {
      aCommenceAParler.current = true;
      return;
    }
    if (aCommenceAParler.current) {
      aCommenceAParler.current = false;
      finDeParole();
      return;
    }
    const secours = window.setTimeout(() => {
      if (!aCommenceAParler.current) finDeParole();
    }, DEMARRAGE_PAROLE_MAX_MS);
    return () => window.clearTimeout(secours);
  }, [phase, speakingMessageId, finDeParole]);

  return null;
}
