/* ─────────────────────────────────────────────────────────────
   Conversation mains libres avec JARVIS (DEC-0164).

   Demande du proprietaire, 29/09/2026 : « Jarvis » — parler, entendre la
   reponse, parler de nouveau, sans toucher l'ecran. Tout ce qu'il fallait
   existait deja : la dictee (Whisper cote serveur, sinon le navigateur) et
   la lecture a voix haute. Ce module ne fait que les ENCHAINER :

     ecoute → (silence) → envoi → reflexion → parole → ecoute …

   La logique pure (fin de parole, ordre d'arret, reponse a prononcer) est
   ici, sans navigateur, pour etre testee. Le pilotage React vit dans
   `components/chat/PiloteConversation.tsx`.
   ───────────────────────────────────────────────────────────── */

import { create } from 'zustand';

import type { ChatMessage } from '../store/chatStore';

export type PhaseConversation = 'arret' | 'ecoute' | 'reflexion' | 'parole';

/** Ce que l'on dit pour sortir du mode — la phrase ENTIERE, pas un mot
 *  contenu : « arrete la video a 10 secondes » est une demande, pas un ordre
 *  d'arret. */
const ORDRE_D_ARRET = /^(stop|stoppe|arr[eê]te(z|s)?|arr[eê]te toi|termin[ée]|fin|au revoir|c'?est tout|merci jarvis|jarvis stop|stop jarvis)$/;

export function estOrdreDArret(texte: string): boolean {
  const phrase = texte
    .toLowerCase()
    .replace(/[’]/g, "'")
    .replace(/[.!?,;:]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  return ORDRE_D_ARRET.test(phrase);
}

/* ── Fin de parole ────────────────────────────────────────────
   Whisper transcrit APRES l'enregistrement : il faut donc decider seul
   quand la personne a fini. Mesure : le niveau sonore (RMS, 0 a 1) du
   micro, echantillonne regulierement. */

export interface ReglagesFinDeParole {
  /** Au-dessus : quelqu'un parle. */
  seuil: number;
  /** Silence apres de la parole qui clot la phrase. */
  silenceMs: number;
  /** Personne n'a parle depuis le debut : on abandonne l'ecoute. */
  attenteMaxMs: number;
  /** Une phrase ne dure pas plus : on coupe quoi qu'il arrive. */
  dureeMaxMs: number;
}

export const REGLAGES_PAR_DEFAUT: ReglagesFinDeParole = {
  seuil: 0.035,
  silenceMs: 1500,
  attenteMaxMs: 8000,
  dureeMaxMs: 30000,
};

/** `parole` : on continue d'ecouter ; `fin` : la phrase est finie ;
 *  `rien` : personne n'a parle, rien a transcrire. */
export type VerdictEcoute = 'attente' | 'parole' | 'fin' | 'rien';

export class DetecteurDeFinDeParole {
  private debut: number | null = null;
  private aParle = false;
  private dernierSon = 0;

  constructor(private readonly reglages: ReglagesFinDeParole = REGLAGES_PAR_DEFAUT) {}

  observer(niveau: number, instantMs: number): VerdictEcoute {
    if (this.debut === null) this.debut = instantMs;
    const ecoule = instantMs - this.debut;

    if (niveau >= this.reglages.seuil) {
      this.aParle = true;
      this.dernierSon = instantMs;
    }
    if (!this.aParle) {
      return ecoule >= this.reglages.attenteMaxMs ? 'rien' : 'attente';
    }
    if (ecoule >= this.reglages.dureeMaxMs) return 'fin';
    return instantMs - this.dernierSon >= this.reglages.silenceMs ? 'fin' : 'parole';
  }
}

/** Niveau RMS d'un echantillon audio temporel (valeurs de -1 a 1). */
export function niveauRms(echantillons: ArrayLike<number>): number {
  if (!echantillons.length) return 0;
  let somme = 0;
  for (let i = 0; i < echantillons.length; i += 1) somme += echantillons[i] * echantillons[i];
  return Math.sqrt(somme / echantillons.length);
}

/* ── La reponse a prononcer ───────────────────────────────── */

/** La reponse de JARVIS qui suit l'envoi, une fois TERMINEE — jamais un texte
 *  en cours d'ecriture, jamais une reponse plus ancienne que la question.
 *  `depuis` est le nombre de messages de la conversation au moment de
 *  l'envoi. Une reponse en erreur se prononce aussi : se taire laisserait
 *  croire qu'il reflechit encore. */
export function reponseAPrononcer(
  messages: ChatMessage[],
  depuis: number,
): { id: string; texte: string } | null {
  for (let i = messages.length - 1; i >= depuis; i -= 1) {
    const m = messages[i];
    if (m.role !== 'assistant') continue;
    if (m.status === 'done' || m.status === 'cancelled') {
      return { id: m.id, texte: m.text || m.live || '' };
    }
    if (m.status === 'error') {
      return { id: m.id, texte: m.error || m.text || '' };
    }
    return null; // encore en cours
  }
  return null;
}

/* ── L'etat partage ─────────────────────────────────────────── */

/** Silences consecutifs avant de quitter seul : un micro ouvert en boucle
 *  videait la batterie du telephone sans que personne ne parle. */
export const SILENCES_AVANT_ARRET = 3;

interface EtatConversation {
  phase: PhaseConversation;
  silences: number;
  /** Pourquoi le mode s'est arrete tout seul (micro refuse, transcription
   *  en echec) — affiche, jamais avale. */
  erreur: string | null;
  /** Nombre de messages au moment de l'envoi : la reponse attendue vient apres. */
  depuis: number;
  demarrer(): void;
  arreter(erreur?: string): void;
  ecouter(): void;
  reflechir(depuis: number): void;
  parler(): void;
  silence(): void;
}

export const useConversation = create<EtatConversation>((set, get) => ({
  phase: 'arret',
  silences: 0,
  erreur: null,
  depuis: 0,
  demarrer: () => set({ phase: 'parole', silences: 0, erreur: null }),
  arreter: (erreur) => set({ phase: 'arret', silences: 0, erreur: erreur ?? null }),
  ecouter: () => {
    if (get().phase !== 'arret') set({ phase: 'ecoute' });
  },
  reflechir: (depuis) => set({ phase: 'reflexion', depuis, silences: 0 }),
  parler: () => {
    if (get().phase !== 'arret') set({ phase: 'parole' });
  },
  silence: () => {
    const silences = get().silences + 1;
    set(silences >= SILENCES_AVANT_ARRET ? { phase: 'arret', silences: 0 } : { silences });
  },
}));
