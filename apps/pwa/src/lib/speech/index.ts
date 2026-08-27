/* ─────────────────────────────────────────────────────────────
   Speech Module for Usman:
   1. Speech-to-Text (Dictation / STT): Web Speech API (Chrome, Safari, Edge)
   2. Text-to-Speech (Audio readback / TTS): SpeechSynthesis API
   ───────────────────────────────────────────────────────────── */

import { create } from 'zustand';

/* ── Web Speech API Type Shims ── */
interface SpeechRecognitionEventLike extends Event {
  resultIndex: number;
  results: {
    length: number;
    item(index: number): {
      isFinal: boolean;
      length: number;
      item(index: number): { transcript: string; confidence: number };
      [index: number]: { transcript: string; confidence: number };
    };
    [index: number]: {
      isFinal: boolean;
      length: number;
      item(index: number): { transcript: string; confidence: number };
      [index: number]: { transcript: string; confidence: number };
    };
  };
}

interface SpeechRecognitionErrorEventLike extends Event {
  error: string;
  message?: string;
}

interface SpeechRecognitionLike extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  maxAlternatives: number;
  onstart: ((this: SpeechRecognitionLike, ev: Event) => any) | null;
  onresult: ((this: SpeechRecognitionLike, ev: SpeechRecognitionEventLike) => any) | null;
  onerror: ((this: SpeechRecognitionLike, ev: SpeechRecognitionErrorEventLike) => any) | null;
  onend: ((this: SpeechRecognitionLike, ev: Event) => any) | null;
  start(): void;
  stop(): void;
  abort(): void;
}

declare global {
  interface Window {
    SpeechRecognition?: new () => SpeechRecognitionLike;
    webkitSpeechRecognition?: new () => SpeechRecognitionLike;
  }
}

/* ─────────────────────────────────────────────────────────────
   1. Dictation (Speech-to-Text) Store & Controller
   ───────────────────────────────────────────────────────────── */

export function isSpeechRecognitionSupported(): boolean {
  return typeof window !== 'undefined' && Boolean(window.SpeechRecognition || window.webkitSpeechRecognition);
}

interface DictationState {
  isListening: boolean;
  isSupported: boolean;
  interimTranscript: string;
  error: string | null;
  startDictation(
    lang: string,
    onResult: (finalText: string, interimText: string) => void,
    onError?: (errCode: string) => void,
  ): void;
  stopDictation(): void;
}

let activeRecognition: SpeechRecognitionLike | null = null;

export const useDictation = create<DictationState>((set) => ({
  isListening: false,
  isSupported: isSpeechRecognitionSupported(),
  interimTranscript: '',
  error: null,

  startDictation: (lang, onResult, onError) => {
    if (!isSpeechRecognitionSupported()) {
      set({ error: 'unsupported', isListening: false });
      onError?.('unsupported');
      return;
    }

    // Stop existing instance if any
    if (activeRecognition) {
      try {
        activeRecognition.abort();
      } catch {
        /* ignore */
      }
      activeRecognition = null;
    }

    const SpeechRecClass = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecClass) return;

    try {
      const recognition = new SpeechRecClass();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = lang.startsWith('fr') ? 'fr-FR' : 'en-US';
      recognition.maxAlternatives = 1;

      recognition.onstart = () => {
        set({ isListening: true, error: null, interimTranscript: '' });
      };

      recognition.onresult = (ev: SpeechRecognitionEventLike) => {
        let finalChunk = '';
        let interimChunk = '';

        for (let i = ev.resultIndex; i < ev.results.length; ++i) {
          const res = ev.results[i];
          if (res.isFinal) {
            finalChunk += res[0].transcript;
          } else {
            interimChunk += res[0].transcript;
          }
        }

        set({ interimTranscript: interimChunk });
        onResult(finalChunk, interimChunk);
      };

      recognition.onerror = (ev: SpeechRecognitionErrorEventLike) => {
        // 'no-speech' is non-fatal in continuous mode
        if (ev.error === 'no-speech') {
          return;
        }
        set({ error: ev.error, isListening: false, interimTranscript: '' });
        onError?.(ev.error);
      };

      recognition.onend = () => {
        set({ isListening: false, interimTranscript: '' });
        activeRecognition = null;
      };

      activeRecognition = recognition;
      recognition.start();
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'failed_to_start';
      set({ error: msg, isListening: false });
      onError?.(msg);
    }
  },

  stopDictation: () => {
    if (activeRecognition) {
      try {
        activeRecognition.stop();
      } catch {
        /* ignore */
      }
      activeRecognition = null;
    }
    set({ isListening: false, interimTranscript: '' });
  },
}));

/* ─────────────────────────────────────────────────────────────
   2. Text-to-Speech (Audio Readback / Synthesis)
   ───────────────────────────────────────────────────────────── */

export function isSpeechSynthesisSupported(): boolean {
  return typeof window !== 'undefined' && 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window;
}

/**
 * Strips markdown, code blocks, URLs, citations and emojis to create natural speech text.
 */
export function cleanTextForSpeech(markdown: string): string {
  if (!markdown) return '';
  return (
    markdown
      // Remove code blocks completely or replace with verbal cue
      .replace(/```[\s\S]*?```/g, '')
      // Remove inline code
      .replace(/`([^`]+)`/g, '$1')
      // Remove citation badges like [1], [2]
      .replace(/\[\d+\]/g, '')
      // Remove markdown links [text](url) -> text
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
      // Remove bold / italic / strike
      .replace(/[*_~]{1,3}(.*?)[*_~]{1,3}/g, '$1')
      // Remove markdown headings #, ##, ###
      .replace(/^#{1,6}\s+/gm, '')
      // Remove blockquotes >
      .replace(/^>\s+/gm, '')
      // Remove bullet points
      .replace(/^[-*+]\s+/gm, '')
      // Remove numbered lists
      .replace(/^\d+\.\s+/gm, '')
      // Remove horizontal rules
      .replace(/^[-*_]{3,}\s*$/gm, '')
      // Normalize whitespace
      .replace(/\n{2,}/g, '. ')
      .replace(/\n/g, ' ')
      .replace(/\s+/g, ' ')
      .trim()
  );
}

function findBestVoice(lang: string): SpeechSynthesisVoice | null {
  if (!isSpeechSynthesisSupported()) return null;
  const voices = window.speechSynthesis.getVoices();
  if (!voices.length) return null;

  const targetPrefix = lang.startsWith('fr') ? 'fr' : 'en';

  // 1. Look for natural/premium voices
  const premiumMatch = voices.find(
    (v) =>
      v.lang.toLowerCase().startsWith(targetPrefix) &&
      (v.name.includes('Natural') || v.name.includes('Premium') || v.name.includes('Enhanced') || v.name.includes('Google') || v.name.includes('Siri') || v.name.includes('Neural')),
  );
  if (premiumMatch) return premiumMatch;

  // 2. Look for any matching voice
  const langMatch = voices.find((v) => v.lang.toLowerCase().startsWith(targetPrefix));
  if (langMatch) return langMatch;

  // 3. Fallback to default voice
  return voices.find((v) => v.default) || voices[0] || null;
}

interface SpeechState {
  speakingMessageId: string | null;
  isPaused: boolean;
  isSupported: boolean;
  rate: number; // 0.8 to 1.5
  speak(messageId: string, text: string, lang: string): void;
  pause(): void;
  resume(): void;
  stop(): void;
  setRate(rate: number): void;
}

export const useSpeech = create<SpeechState>((set, get) => ({
  speakingMessageId: null,
  isPaused: false,
  isSupported: isSpeechSynthesisSupported(),
  rate: 1.05,

  speak: (messageId: string, rawText: string, lang: string) => {
    if (!isSpeechSynthesisSupported()) return;

    const synth = window.speechSynthesis;

    // If currently speaking this exact message, toggle pause/resume
    if (get().speakingMessageId === messageId) {
      if (get().isPaused) {
        synth.resume();
        set({ isPaused: false });
      } else {
        synth.pause();
        set({ isPaused: true });
      }
      return;
    }

    // Cancel any previous speech
    synth.cancel();

    const spokenText = cleanTextForSpeech(rawText);
    if (!spokenText) return;

    const utterance = new SpeechSynthesisUtterance(spokenText);
    utterance.lang = lang.startsWith('fr') ? 'fr-FR' : 'en-US';
    utterance.rate = get().rate;
    utterance.pitch = 1.0;

    // Pre-load voices if needed
    const voice = findBestVoice(lang);
    if (voice) {
      utterance.voice = voice;
    }

    utterance.onstart = () => {
      set({ speakingMessageId: messageId, isPaused: false });
    };

    utterance.onpause = () => {
      set({ isPaused: true });
    };

    utterance.onresume = () => {
      set({ isPaused: false });
    };

    utterance.onend = () => {
      set({ speakingMessageId: null, isPaused: false });
    };

    utterance.onerror = (e) => {
      // 'interrupted' or 'canceled' are standard when switching messages
      if (e.error !== 'interrupted' && e.error !== 'canceled') {
        console.warn('SpeechSynthesis error:', e.error);
      }
      set({ speakingMessageId: null, isPaused: false });
    };

    synth.speak(utterance);
  },

  pause: () => {
    if (!isSpeechSynthesisSupported()) return;
    window.speechSynthesis.pause();
    set({ isPaused: true });
  },

  resume: () => {
    if (!isSpeechSynthesisSupported()) return;
    window.speechSynthesis.resume();
    set({ isPaused: false });
  },

  stop: () => {
    if (!isSpeechSynthesisSupported()) return;
    window.speechSynthesis.cancel();
    set({ speakingMessageId: null, isPaused: false });
  },

  setRate: (rate: number) => {
    set({ rate: Math.max(0.75, Math.min(2.0, rate)) });
  },
}));
