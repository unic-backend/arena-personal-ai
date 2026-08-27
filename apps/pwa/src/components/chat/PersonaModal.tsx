import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  BookOpen,
  Briefcase,
  Check,
  Code2,
  ListOrdered,
  RotateCcw,
  Sparkles,
  User,
  UserCheck,
  Wand2,
  X,
  Zap,
} from 'lucide-react';
import {
  AssistantTone,
  ResponseFormatPreference,
  usePersona,
} from '../../lib/store/personaStore';
import { useI18n } from '../../lib/i18n';
import { cn } from '../../utils/cn';

interface PersonaPreset {
  id: string;
  name: string;
  nameFr: string;
  role: string;
  roleFr: string;
  tone: AssistantTone;
  format: ResponseFormatPreference;
  instructions: string;
  instructionsFr: string;
  icon: React.ReactNode;
}

const PRESETS: PersonaPreset[] = [
  {
    id: 'senior-dev',
    name: 'Lead Developer',
    nameFr: 'Développeur Senior',
    role: 'Staff Software Engineer',
    roleFr: 'Ingénieur Logiciel Senior',
    tone: 'expert',
    format: 'code_first',
    instructions: 'Always write clean, modern TypeScript. Focus on performance, architectural patterns, and avoid trivial boilerplates.',
    instructionsFr: 'Écris toujours du code TypeScript moderne et propre. Priorise la performance, l’architecture et évite le superflu.',
    icon: <Code2 size={13} className="text-cyan-400" />,
  },
  {
    id: 'concise-exec',
    name: 'Concise & Direct',
    nameFr: 'Style Ultra-Concis',
    role: 'Tech Executive / Founder',
    roleFr: 'Fondateur / Décideur Tech',
    tone: 'concise',
    format: 'bullet_heavy',
    instructions: 'Be extremely concise. Get straight to the key actionable takeaways without conversational fluff.',
    instructionsFr: 'Sois extrêmement concis. Va directement aux points clés et actions sans bavardage d’introduction.',
    icon: <Zap size={13} className="text-amber-400" />,
  },
  {
    id: 'pedagogical',
    name: 'Mentor & Tutor',
    nameFr: 'Mentor Pédagogique',
    role: 'Student / Lifelong Learner',
    roleFr: 'Apprenant / Développeur Curieux',
    tone: 'pedagogical',
    format: 'standard',
    instructions: 'Explain concepts step by step with intuitive analogies, best practices, and practical examples.',
    instructionsFr: 'Explique les concepts pas à pas avec des analogies intuitives, de bonnes pratiques et des exemples concrets.',
    icon: <BookOpen size={13} className="text-emerald-400" />,
  },
];

export function PersonaModal() {
  const { modalOpen, setModalOpen, updateProfile, resetProfile } = usePersona();
  const persona = usePersona();
  const { t, locale } = useI18n();
  const fr = locale === 'fr';

  const [userName, setUserName] = useState(persona.userName);
  const [userRole, setUserRole] = useState(persona.userRole);
  const [assistantTone, setAssistantTone] = useState<AssistantTone>(persona.assistantTone);
  const [responseFormat, setResponseFormat] = useState<ResponseFormatPreference>(persona.responseFormat);
  const [customInstructions, setCustomInstructions] = useState(persona.customInstructions);
  const [savedBadge, setSavedBadge] = useState(false);

  // Sync state when modal opens
  useEffect(() => {
    if (modalOpen) {
      setUserName(persona.userName);
      setUserRole(persona.userRole);
      setAssistantTone(persona.assistantTone);
      setResponseFormat(persona.responseFormat);
      setCustomInstructions(persona.customInstructions);
      setSavedBadge(false);
    }
  }, [modalOpen, persona]);

  // Handle ESC key
  useEffect(() => {
    if (!modalOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setModalOpen(false);
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [modalOpen, setModalOpen]);

  const handleSave = () => {
    updateProfile({
      userName: userName.trim(),
      userRole: userRole.trim(),
      assistantTone,
      responseFormat,
      customInstructions: customInstructions.trim(),
    });
    setSavedBadge(true);
    setTimeout(() => {
      setSavedBadge(false);
      setModalOpen(false);
    }, 600);
  };

  const handleApplyPreset = (preset: PersonaPreset) => {
    setUserRole(fr ? preset.roleFr : preset.role);
    setAssistantTone(preset.tone);
    setResponseFormat(preset.format);
    setCustomInstructions(fr ? preset.instructionsFr : preset.instructions);
  };

  const handleReset = () => {
    resetProfile();
    setUserName('');
    setUserRole('');
    setAssistantTone('balanced');
    setResponseFormat('standard');
    setCustomInstructions('');
  };

  const toneOptions: Array<{ id: AssistantTone; label: string; desc: string }> = [
    {
      id: 'balanced',
      label: fr ? 'Équilibré' : 'Balanced',
      desc: fr ? 'Naturel, fluide et chaleureux' : 'Natural, clear and friendly',
    },
    {
      id: 'concise',
      label: fr ? 'Concis & Direct' : 'Concise',
      desc: fr ? 'Réponses courtes, directes et sans fioritures' : 'Brief, direct and minimal filler',
    },
    {
      id: 'expert',
      label: fr ? 'Expert & Technique' : 'Expert',
      desc: fr ? 'Niveau technique élevé, précis et rigoureux' : 'High technical rigor and depth',
    },
    {
      id: 'pedagogical',
      label: fr ? 'Pédagogique' : 'Pedagogical',
      desc: fr ? 'Explications pas à pas et analogies intuitives' : 'Step-by-step with analogies',
    },
  ];

  const formatOptions: Array<{ id: ResponseFormatPreference; label: string; icon: React.ReactNode }> = [
    {
      id: 'standard',
      label: fr ? 'Standard' : 'Standard',
      icon: <Sparkles size={11} />,
    },
    {
      id: 'code_first',
      label: fr ? 'Code d’abord' : 'Code First',
      icon: <Code2 size={11} />,
    },
    {
      id: 'bullet_heavy',
      label: fr ? 'Puces & Listes' : 'Bullet Heavy',
      icon: <ListOrdered size={11} />,
    },
  ];

  return (
    <AnimatePresence>
      {modalOpen && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[60] bg-black/75 backdrop-blur-sm"
            onClick={() => setModalOpen(false)}
          />

          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby="persona-modal-title"
            initial={{ opacity: 0, scale: 0.96, y: 16 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: 12 }}
            transition={{ type: 'spring', stiffness: 380, damping: 32 }}
            className="fixed inset-x-3 top-[4vh] z-[61] mx-auto flex max-h-[92vh] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-white/10 bg-ink-900 shadow-[0_40px_120px_-20px_rgba(0,0,0,0.9)] sm:top-[6vh]"
          >
            {/* Header */}
            <div className="flex items-center gap-2.5 border-b border-white/7 px-4 py-3">
              <span className="grid h-7 w-7 place-items-center rounded-lg border border-accent-500/30 bg-accent-500/10 text-accent-300">
                <UserCheck size={14} />
              </span>
              <div className="flex-1">
                <h2 id="persona-modal-title" className="text-[13.5px] font-medium text-zinc-100">
                  {t('persona.title')}
                </h2>
                <div className="font-mono text-[9px] text-zinc-400">
                  {t('persona.subtitle')}
                </div>
              </div>
              <button
                type="button"
                onClick={() => setModalOpen(false)}
                aria-label="Close"
                className="rounded-md p-1.5 text-zinc-500 transition hover:bg-white/5 hover:text-zinc-200"
              >
                <X size={15} />
              </button>
            </div>

            {/* Body */}
            <div className="flex-1 space-y-4 overflow-y-auto p-4 scroll-slim">
              {/* Quick Presets */}
              <div>
                <div className="mb-2 flex items-center justify-between px-0.5">
                  <span className="flex items-center gap-1 font-mono text-[9px] uppercase tracking-[0.18em] text-zinc-500">
                    <Wand2 size={10} className="text-accent-400" />
                    {t('persona.presets')}
                  </span>
                </div>
                <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-3">
                  {PRESETS.map((preset) => (
                    <button
                      key={preset.id}
                      type="button"
                      onClick={() => handleApplyPreset(preset)}
                      className="flex items-center gap-2 rounded-xl border border-white/8 bg-white/[0.02] p-2 text-left transition hover:border-accent-500/40 hover:bg-accent-500/[0.05] active:scale-95"
                    >
                      <span className="grid h-6 w-6 shrink-0 place-items-center rounded-md border border-white/8 bg-white/4">
                        {preset.icon}
                      </span>
                      <span className="min-w-0 flex-1 truncate text-[11px] font-medium text-zinc-200">
                        {fr ? preset.nameFr : preset.name}
                      </span>
                    </button>
                  ))}
                </div>
              </div>

              {/* User Identity */}
              <div className="space-y-2">
                <span className="font-mono text-[9px] uppercase tracking-[0.18em] text-zinc-500">
                  {t('persona.identity')}
                </span>
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                  <div className="relative flex items-center">
                    <User size={12} className="pointer-events-none absolute left-2.5 text-zinc-500" />
                    <input
                      type="text"
                      value={userName}
                      onChange={(e) => setUserName(e.target.value)}
                      placeholder={t('persona.namePh')}
                      className="w-full rounded-lg border border-white/8 bg-ink-950/60 py-1.5 pl-8 pr-2.5 text-[11.5px] text-zinc-200 outline-none placeholder:text-zinc-600 focus:border-accent-500/50"
                    />
                  </div>
                  <div className="relative flex items-center">
                    <Briefcase size={12} className="pointer-events-none absolute left-2.5 text-zinc-500" />
                    <input
                      type="text"
                      value={userRole}
                      onChange={(e) => setUserRole(e.target.value)}
                      placeholder={t('persona.rolePh')}
                      className="w-full rounded-lg border border-white/8 bg-ink-950/60 py-1.5 pl-8 pr-2.5 text-[11.5px] text-zinc-200 outline-none placeholder:text-zinc-600 focus:border-accent-500/50"
                    />
                  </div>
                </div>
              </div>

              {/* Preferred Tone */}
              <div>
                <span className="mb-2 block font-mono text-[9px] uppercase tracking-[0.18em] text-zinc-500">
                  {t('persona.tone')}
                </span>
                <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
                  {toneOptions.map((opt) => {
                    const isSelected = assistantTone === opt.id;
                    return (
                      <button
                        key={opt.id}
                        type="button"
                        onClick={() => setAssistantTone(opt.id)}
                        className={cn(
                          'flex items-center gap-2 rounded-xl border p-2.5 text-left transition active:scale-95',
                          isSelected
                            ? 'border-accent-500/40 bg-accent-500/10 text-zinc-100'
                            : 'border-white/8 bg-white/[0.02] text-zinc-400 hover:border-white/15 hover:text-zinc-200',
                        )}
                      >
                        <span
                          className={cn(
                            'h-2 w-2 rounded-full',
                            isSelected ? 'bg-accent-400 shadow-[0_0_8px_var(--glow)]' : 'bg-zinc-600',
                          )}
                        />
                        <div className="min-w-0 flex-1">
                          <div className="text-[11.5px] font-medium leading-tight">{opt.label}</div>
                          <div className="truncate text-[9px] text-zinc-500">{opt.desc}</div>
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Response Format Preference */}
              <div>
                <span className="mb-2 block font-mono text-[9px] uppercase tracking-[0.18em] text-zinc-500">
                  {t('persona.format')}
                </span>
                <div className="flex gap-1.5">
                  {formatOptions.map((opt) => {
                    const isSelected = responseFormat === opt.id;
                    return (
                      <button
                        key={opt.id}
                        type="button"
                        onClick={() => setResponseFormat(opt.id)}
                        className={cn(
                          'flex flex-1 items-center justify-center gap-1.5 rounded-lg border py-1.5 text-[10.5px] font-medium transition active:scale-95',
                          isSelected
                            ? 'border-accent-500/40 bg-accent-500/12 text-accent-300'
                            : 'border-white/8 bg-white/[0.02] text-zinc-400 hover:border-white/15 hover:text-zinc-200',
                        )}
                      >
                        {opt.icon}
                        <span>{opt.label}</span>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Custom Freeform Instructions */}
              <div>
                <div className="mb-1.5 flex items-center justify-between">
                  <span className="font-mono text-[9px] uppercase tracking-[0.18em] text-zinc-500">
                    {t('persona.instructions')}
                  </span>
                  <span className="font-mono text-[8.5px] text-zinc-600">
                    {customInstructions.length} / 1000
                  </span>
                </div>
                <textarea
                  value={customInstructions}
                  onChange={(e) => setCustomInstructions(e.target.value.slice(0, 1000))}
                  rows={4}
                  placeholder={t('persona.instructionsPh')}
                  className="w-full resize-none rounded-xl border border-white/8 bg-ink-950/60 p-2.5 text-[11.5px] leading-relaxed text-zinc-200 outline-none placeholder:text-zinc-600 focus:border-accent-500/50 scroll-slim"
                />
              </div>
            </div>

            {/* Footer */}
            <div className="flex items-center justify-between border-t border-white/7 px-4 py-3">
              <button
                type="button"
                onClick={handleReset}
                className="inline-flex items-center gap-1 text-[10.5px] text-zinc-500 transition hover:text-zinc-300"
              >
                <RotateCcw size={11} />
                {t('persona.reset')}
              </button>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setModalOpen(false)}
                  className="rounded-lg px-3 py-1.5 text-[11.5px] font-medium text-zinc-400 transition hover:bg-white/5 hover:text-zinc-200"
                >
                  {t('msg.cancel')}
                </button>
                <button
                  type="button"
                  onClick={handleSave}
                  className="inline-flex items-center gap-1.5 rounded-lg bg-accent-500 px-3.5 py-1.5 text-[11.5px] font-medium text-ink-950 transition hover:bg-accent-400 active:scale-95"
                >
                  {savedBadge ? <Check size={13} strokeWidth={2.5} /> : <Sparkles size={13} />}
                  {savedBadge ? t('msg.copied') : t('persona.save')}
                </button>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
