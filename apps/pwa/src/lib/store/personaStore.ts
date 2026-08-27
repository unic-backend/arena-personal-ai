/* ─────────────────────────────────────────────────────────────
   Persona & Custom Instructions Store for Usman
   · Lets the user define their profile, role, preferred tone,
     and custom instructions injected into every AI request.
   ───────────────────────────────────────────────────────────── */

import { create } from 'zustand';

export type AssistantTone = 'balanced' | 'concise' | 'expert' | 'pedagogical';
export type ResponseFormatPreference = 'standard' | 'bullet_heavy' | 'code_first';

export interface PersonaProfile {
  userName: string;
  userRole: string;
  assistantTone: AssistantTone;
  responseFormat: ResponseFormatPreference;
  customInstructions: string;
}

const PERSONA_KEY = 'usman.persona.v1';

const DEFAULT_PERSONA: PersonaProfile = {
  userName: '',
  userRole: '',
  assistantTone: 'balanced',
  responseFormat: 'standard',
  customInstructions: '',
};

function loadPersona(): PersonaProfile {
  try {
    const raw = localStorage.getItem(PERSONA_KEY);
    if (raw) {
      return { ...DEFAULT_PERSONA, ...JSON.parse(raw) };
    }
  } catch {
    /* ignore */
  }
  return DEFAULT_PERSONA;
}

function persistPersona(data: PersonaProfile) {
  try {
    localStorage.setItem(PERSONA_KEY, JSON.stringify(data));
  } catch {
    /* ignore */
  }
}

interface PersonaState extends PersonaProfile {
  modalOpen: boolean;
  setModalOpen: (open: boolean) => void;
  updateProfile: (patch: Partial<PersonaProfile>) => void;
  resetProfile: () => void;
}

export const usePersona = create<PersonaState>((set, get) => ({
  ...loadPersona(),
  modalOpen: false,

  setModalOpen: (modalOpen) => set({ modalOpen }),

  updateProfile: (patch) => {
    const current = get();
    const updated: PersonaProfile = {
      userName: patch.userName !== undefined ? patch.userName : current.userName,
      userRole: patch.userRole !== undefined ? patch.userRole : current.userRole,
      assistantTone: patch.assistantTone !== undefined ? patch.assistantTone : current.assistantTone,
      responseFormat: patch.responseFormat !== undefined ? patch.responseFormat : current.responseFormat,
      customInstructions: patch.customInstructions !== undefined ? patch.customInstructions : current.customInstructions,
    };
    persistPersona(updated);
    set(updated);
  },

  resetProfile: () => {
    persistPersona(DEFAULT_PERSONA);
    set(DEFAULT_PERSONA);
  },
}));

/**
 * Builds a clean prompt snippet representing the user's custom instructions and persona
 */
export function buildPersonaPrompt(profile?: PersonaProfile): string {
  const p = profile ?? usePersona.getState();
  const directives: string[] = [];

  if (p.userName.trim()) {
    directives.push(`User Name: ${p.userName.trim()}`);
  }
  if (p.userRole.trim()) {
    directives.push(`User Role/Profession: ${p.userRole.trim()}`);
  }
  if (p.assistantTone === 'concise') {
    directives.push('Tone: Be extremely concise, direct, and avoid any conversational filler.');
  } else if (p.assistantTone === 'expert') {
    directives.push('Tone: Speak as a principal staff engineer / domain expert, rigorous and in-depth.');
  } else if (p.assistantTone === 'pedagogical') {
    directives.push('Tone: Pedagogical, clear, educational with intuitive real-world analogies.');
  }

  if (p.responseFormat === 'code_first') {
    directives.push('Format: Prioritize code snippets and solution first, with explanations after.');
  } else if (p.responseFormat === 'bullet_heavy') {
    directives.push('Format: Structure responses with bullet points and clear section headers.');
  }

  if (p.customInstructions.trim()) {
    directives.push(`User Custom Instructions:\n${p.customInstructions.trim()}`);
  }

  return directives.join('\n');
}
