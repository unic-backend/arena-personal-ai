/* ─────────────────────────────────────────────────────────────
   Pilote de la conversation mains libres (DEC-0164).

   N'affiche rien : il enchaine les briques existantes selon la phase de
   `useConversation` — ecoute (dictee a fin automatique), reflexion (la
   question est partie, on attend la reponse TERMINEE), parole (lecture a
   voix haute), puis de nouveau ecoute.
   ───────────────────────────────────────────────────────────── */

import { useEffect, useRef, useState } from 'react';

import { useI18n } from '../../lib/i18n';
import { isSpeechSynthesisSupported, useDictation, useSpeech } from '../../lib/speech';
import { estOrdreDArret, reponseAPrononcer, useConversation } from '../../lib/speech/conversation';
import type { ChatMessage } from '../../lib/store/chatStore';

/** Une lecture qui n'a pas commence dans ce delai ne commencera pas
 *  (voix absente, synthese bloquee) : on reprend l'ecoute plutot que rester muet. */
const DEMARRAGE_PAROLE_MAX_MS = 5000;

export function PiloteConversation({
  messages,
  running,
  send,
}: {
  messages: ChatMessage[];
  running: boolean;
  send: (texte: string) => void;
}) {
  const { phase, depuis, ecouter, reflechir, parler, arreter, silence } = useConversation();
  const { startDictation, isListening, isTranscribing } = useDictation();
  const { speak, speakingMessageId } = useSpeech();
  const { t, locale } = useI18n();
  const [tour, setTour] = useState(0);
  const ecouteLancee = useRef(false);
  const aCommenceAParler = useRef(false);
  const messagesRef = useRef(messages);
  messagesRef.current = messages;

  // Ecoute : une phrase, puis la dictee s'arrete seule au silence.
  useEffect(() => {
    if (phase !== 'ecoute') {
      ecouteLancee.current = false;
      return;
    }
    if (ecouteLancee.current || isListening || isTranscribing) return;
    ecouteLancee.current = true;

    const reprendre = () => {
      ecouteLancee.current = false;
      setTour((n) => n + 1);
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
          silence();
          reprendre();
          return;
        }
        if (estOrdreDArret(texte)) {
          arreter();
          speak('jarvis-au-revoir', t('conversation.aurevoir'), locale);
          return;
        }
        reflechir(messagesRef.current.length);
        send(texte);
      },
      (code) => {
        if (code === 'no-speech') {
          silence();
          reprendre();
          return;
        }
        arreter(code);
      },
      { finAutomatique: true },
    );
  }, [phase, tour, isListening, isTranscribing, locale, startDictation, speak, t,
      arreter, reflechir, silence, send]);

  // Reflexion : on attend la reponse TERMINEE, puis on la lit.
  useEffect(() => {
    if (phase !== 'reflexion' || running) return;
    const reponse = reponseAPrononcer(messages, depuis);
    if (!reponse) return;
    aCommenceAParler.current = false;
    parler();
    speak(reponse.id, reponse.texte || t('conversation.sansReponse'), locale);
  }, [phase, running, messages, depuis, parler, speak, t, locale]);

  // Parole : quand la lecture s'acheve, on ecoute de nouveau.
  useEffect(() => {
    if (phase !== 'parole') return;
    if (!isSpeechSynthesisSupported()) {
      ecouter();
      return;
    }
    if (speakingMessageId) {
      aCommenceAParler.current = true;
      return;
    }
    if (aCommenceAParler.current) {
      aCommenceAParler.current = false;
      ecouter();
      return;
    }
    const secours = window.setTimeout(() => {
      if (!aCommenceAParler.current) ecouter();
    }, DEMARRAGE_PAROLE_MAX_MS);
    return () => window.clearTimeout(secours);
  }, [phase, speakingMessageId, ecouter]);

  return null;
}
