/* ─────────────────────────────────────────────────────────────
   Réglages — tout ce qui n'a pas sa place sur la façade.
   La barre latérale ne garde que l'essentiel ; persona, mémoire,
   backend, apparence, langue et entretien vivent ici.
   ───────────────────────────────────────────────────────────── */

import { useEffect } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { create } from 'zustand';
import {
  Brain,
  Globe,
  Monitor,
  Moon,
  Plug,
  Share2,
  Sun,
  TerminalSquare,
  UserCheck,
  X,
} from 'lucide-react';
import { useTheme, ACCENTS } from '../../lib/theme';
import { useI18n, Lang } from '../../lib/i18n';
import { usePersona } from '../../lib/store/personaStore';
import { useMemory } from '../../lib/memory/memoryStore';
import { useConnectors } from '../../lib/store/connectorStore';
import { useExport } from '../../lib/store/exportStore';
import { useChat } from '../../lib/store/chatStore';
import { CONNECTOR_CATALOG } from '../../lib/connectors/catalog';
import { BackendPanel } from './BackendPanel';
import { TypographyPanel } from './TypographyPanel';
import { PWAInstall } from './PWAInstall';
import { cn } from '../../utils/cn';

/* ── ouverture/fermeture, pilotée depuis la barre latérale ── */

interface SettingsState {
  open: boolean;
  openSettings: () => void;
  closeSettings: () => void;
}

export const useSettings = create<SettingsState>((set) => ({
  open: false,
  openSettings: () => set({ open: true }),
  closeSettings: () => set({ open: false }),
}));

/* ── libellés : deux langues, pas de clé à ajouter au catalogue ── */

const L = {
  fr: {
    title: 'Réglages',
    close: 'Fermer',
    sectionYou: 'Toi et la mémoire',
    sectionBackend: 'Connexion',
    sectionLook: 'Apparence',
    sectionApp: 'Application',
    persona: 'Ton profil',
    personaSub: 'Nom, rôle, ton des réponses',
    memory: 'Mémoire',
    memorySub: 'Ce que ton IA retient de toi',
    connectors: 'Connecteurs',
    connectorsSub: 'Aucun connecteur n\'agit encore',
    theme: 'Couleur',
    mode: 'Affichage',
    dark: 'Sombre',
    light: 'Clair',
    system: 'Système',
    lang: 'Langue',
    log: 'Journal des événements',
    logSub: 'Voir ce que fait ton IA, étape par étape',
    share: 'Exporter la conversation',
    shareSub: 'Markdown, JSON ou texte',
    reset: 'Réinitialiser l\'espace de travail',
    resetSub: 'Efface les fichiers de travail, garde les conversations',
    active: 'actifs',
  },
  en: {
    title: 'Settings',
    close: 'Close',
    sectionYou: 'You and memory',
    sectionBackend: 'Connection',
    sectionLook: 'Appearance',
    sectionApp: 'Application',
    persona: 'Your profile',
    personaSub: 'Name, role, answer tone',
    memory: 'Memory',
    memorySub: 'What your AI remembers about you',
    connectors: 'Connectors',
    connectorsSub: 'No connector acts yet',
    theme: 'Colour',
    mode: 'Display',
    dark: 'Dark',
    light: 'Light',
    system: 'System',
    lang: 'Language',
    log: 'Event log',
    logSub: 'See what your AI does, step by step',
    share: 'Export conversation',
    shareSub: 'Markdown, JSON or plain text',
    reset: 'Reset workspace',
    resetSub: 'Clears working files, keeps conversations',
    active: 'active',
  },
};

/* ── une ligne cliquable : icône, titre, sous-titre, valeur à droite ── */

function Row({
  icon,
  title,
  sub,
  right,
  onClick,
  danger,
}: {
  icon: React.ReactNode;
  title: string;
  sub?: string;
  right?: React.ReactNode;
  onClick: () => void;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'flex w-full items-center gap-3 rounded-xl border border-white/8 bg-white/[0.02] px-3 py-2.5 text-left transition active:scale-[0.99]',
        danger
          ? 'text-zinc-400 hover:border-red-400/30 hover:bg-red-400/[0.05] hover:text-red-200'
          : 'text-zinc-300 hover:border-white/15 hover:bg-white/[0.05] hover:text-zinc-100',
      )}
    >
      <span className={cn('shrink-0', danger ? 'text-zinc-500' : 'text-accent-400')}>{icon}</span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[12.5px] font-medium">{title}</span>
        {sub && <span className="mt-0.5 block truncate text-[10.5px] text-zinc-600">{sub}</span>}
      </span>
      {right}
    </button>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <div className="px-1 font-mono text-[9px] uppercase tracking-[0.18em] text-zinc-600">{title}</div>
      {children}
    </div>
  );
}

export function SettingsModal() {
  const { open, closeSettings } = useSettings();
  const { locale, setLocale } = useI18n();
  const l = L[locale];

  const { accent, setAccent, colorMode, setColorMode } = useTheme();
  const { setModalOpen: openPersona, userName } = usePersona();
  const { setModalOpen: openMemoryModal, memories } = useMemory();
  const { setModalOpen: openConnectors, connectors } = useConnectors();
  const { toggleLog } = useChat();

  const activeMemories = memories.filter((m) => m.enabled).length;
  const activeConnectors = Object.values(connectors).filter((s) => s.status === 'connected').length;

  /* Échap ferme la fenêtre — même geste que les autres modales. */
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeSettings();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, closeSettings]);

  /* Ouvrir une sous-fenêtre ferme les réglages : jamais deux modales empilées. */
  const openAndClose = (fn: () => void) => () => {
    closeSettings();
    fn();
  };

  const langButton = (code: Lang, label: string) => (
    <button
      key={code}
      type="button"
      onClick={() => setLocale(code)}
      className={cn(
        'flex-1 rounded-md px-2 py-1 font-mono text-[10px] transition',
        locale === code ? 'bg-accent-500/20 text-accent-300' : 'text-zinc-500 hover:text-zinc-300',
      )}
    >
      {label}
    </button>
  );

  const modeButton = (mode: 'dark' | 'light' | 'system', icon: React.ReactNode, label: string) => (
    <button
      type="button"
      onClick={() => setColorMode(mode)}
      title={label}
      className={cn(
        'flex flex-1 items-center justify-center gap-1 rounded px-1.5 py-1 font-mono text-[9.5px] transition',
        colorMode === mode ? 'bg-white/10 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300',
      )}
    >
      {icon}
      <span className="hidden sm:inline">{label}</span>
    </button>
  );

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[60] bg-black/60 backdrop-blur-sm"
            onClick={closeSettings}
          />
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label={l.title}
            initial={{ opacity: 0, y: 18, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 18, scale: 0.98 }}
            transition={{ duration: 0.22, ease: [0.22, 0.9, 0.3, 1] }}
            className="fixed inset-x-0 bottom-0 z-[61] mx-auto flex max-h-[88vh] w-full max-w-lg flex-col rounded-t-2xl border border-white/10 bg-ink-900 sm:inset-y-auto sm:top-1/2 sm:-translate-y-1/2 sm:rounded-2xl"
          >
            <div className="flex items-center justify-between border-b border-white/6 px-4 py-3">
              <span className="font-serif text-[16px] text-zinc-100">{l.title}</span>
              <button
                type="button"
                onClick={closeSettings}
                aria-label={l.close}
                className="rounded-md p-1.5 text-zinc-500 transition hover:bg-white/5 hover:text-zinc-200"
              >
                <X size={15} />
              </button>
            </div>

            <div className="scroll-slim space-y-4 overflow-y-auto px-4 py-4">
              <Section title={l.sectionYou}>
                <Row
                  icon={<UserCheck size={14} />}
                  title={l.persona}
                  sub={l.personaSub}
                  onClick={openAndClose(() => openPersona(true))}
                  right={
                    userName.trim() ? (
                      <span className="font-mono text-[9.5px] text-accent-300">{userName.trim().slice(0, 14)}</span>
                    ) : undefined
                  }
                />
                <Row
                  icon={<Brain size={14} />}
                  title={l.memory}
                  sub={l.memorySub}
                  onClick={openAndClose(() => openMemoryModal(true))}
                  right={
                    <span className="rounded-full bg-white/5 px-1.5 py-0.5 font-mono text-[9px] text-zinc-400">
                      {activeMemories}
                    </span>
                  }
                />
              </Section>

              <Section title={l.sectionBackend}>
                <BackendPanel />
                <Row
                  icon={<Plug size={14} />}
                  title={l.connectors}
                  sub={l.connectorsSub}
                  onClick={openAndClose(() => openConnectors(true))}
                  right={
                    <span className="rounded-full bg-white/5 px-1.5 py-0.5 font-mono text-[9px] text-zinc-500">
                      {activeConnectors}/{CONNECTOR_CATALOG.length}
                    </span>
                  }
                />
              </Section>

              <Section title={l.sectionLook}>
                <div className="flex items-center justify-between gap-2 rounded-xl border border-white/8 px-3 py-2.5">
                  <span className="font-mono text-[9.5px] uppercase tracking-[0.14em] text-zinc-500">{l.theme}</span>
                  <div className="flex items-center gap-1.5">
                    {ACCENTS.map((a) => (
                      <button
                        key={a.id}
                        type="button"
                        onClick={() => setAccent(a.id)}
                        title={locale === 'fr' ? a.labelFr : a.label}
                        className={cn(
                          'h-4 w-4 rounded-full transition active:scale-90',
                          accent.id === a.id
                            ? 'scale-125 ring-2 ring-white/80 ring-offset-1 ring-offset-ink-900'
                            : 'opacity-65 hover:opacity-100',
                        )}
                        style={{ background: `linear-gradient(135deg, ${a.c400}, ${a.c600})` }}
                      />
                    ))}
                  </div>
                </div>

                <div className="flex items-center justify-between gap-2 rounded-xl border border-white/8 px-3 py-2.5">
                  <span className="font-mono text-[9.5px] uppercase tracking-[0.14em] text-zinc-500">{l.mode}</span>
                  <div className="flex items-center gap-0.5 rounded-md border border-white/6 bg-white/[0.02] p-0.5">
                    {modeButton('dark', <Moon size={10} />, l.dark)}
                    {modeButton('light', <Sun size={10} />, l.light)}
                    {modeButton('system', <Monitor size={10} />, l.system)}
                  </div>
                </div>

                <TypographyPanel />

                <div className="flex items-center gap-2 rounded-xl border border-white/8 px-3 py-2">
                  <Globe size={13} className="shrink-0 text-zinc-500" />
                  <span className="flex-1 font-mono text-[9.5px] uppercase tracking-[0.14em] text-zinc-500">
                    {l.lang}
                  </span>
                  <div className="flex w-24 gap-0.5">
                    {langButton('fr', 'FR')}
                    {langButton('en', 'EN')}
                  </div>
                </div>
              </Section>

              <Section title={l.sectionApp}>
                <PWAInstall />
                <Row
                  icon={<TerminalSquare size={14} />}
                  title={l.log}
                  sub={l.logSub}
                  onClick={openAndClose(toggleLog)}
                />
                <Row
                  icon={<Share2 size={14} />}
                  title={l.share}
                  sub={l.shareSub}
                  onClick={openAndClose(() => useExport.getState().openExport())}
                />
              </Section>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}