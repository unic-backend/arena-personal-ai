import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Menu, PanelLeftClose } from 'lucide-react';
import { useChat } from './lib/store/chatStore';
import { useI18n } from './lib/i18n';
import { useBackend } from './lib/store/backendStore';
import { useCommandPalette } from './lib/commands/commandStore';
import { Sidebar, Logo } from './components/chat/Sidebar';
import { ChatMessage } from './components/chat/ChatMessage';
import { Composer } from './components/chat/Composer';
import { EmptyState } from './components/chat/EmptyState';
import { EventLogDrawer } from './components/chat/EventLogDrawer';
import { ConnectorsModal } from './components/chat/ConnectorsModal';
import { PersonaModal } from './components/chat/PersonaModal';
import { MemoryModal } from './components/chat/MemoryModal';
import { ExportModal } from './components/chat/ExportModal';
import { SettingsModal } from './components/chat/SettingsModal';
import { CommandPalette } from './components/chat/CommandPalette';
import { GlobalDropZone } from './components/chat/GlobalDropZone';
import { NetworkStatus } from './components/chat/NetworkStatus';
import { cn } from './utils/cn';

export default function App() {
  const { conversations, activeId, isRunning, send, cancel, rerunCommand, toggleLog } = useChat();
  const { t, locale } = useI18n();
  const { togglePalette } = useCommandPalette();
  const [mobileNav, setMobileNav] = useState(false);

  useEffect(() => {
    document.documentElement.lang = locale;
    document.title = locale === 'fr'
      ? 'Usman — Atelier IA personnel'
      : 'Usman — Personal AI Workbench';
  }, [locale]);

  /* Revalide un backend distant mémorisé au lieu de croire un état périmé. */
  useEffect(() => {
    const backend = useBackend.getState();
    if (backend.enabled && backend.status === 'local') void backend.test();
  }, []);
  const [desktopNav, setDesktopNav] = useState(true);
  const scrollRef = useRef<HTMLDivElement>(null);
  const pinned = useRef(true);

  const conv = conversations.find((c) => c.id === activeId) ?? null;
  const messages = conv?.messages ?? [];
  const hasMessages = messages.length > 0;

  /* Défilement automatique : suit le flux sauf si l'utilisateur est remonté. */
  useEffect(() => {
    const el = scrollRef.current;
    if (el && pinned.current) el.scrollTop = el.scrollHeight;
  }, [messages, messages[messages.length - 1]?.live, messages[messages.length - 1]?.activity]);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
  };

  /* Raccourcis : ⌘K palette · ⌘J journal · Échap ferme le menu mobile. */
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && mobileNav) {
        setMobileNav(false);
        return;
      }
      if (!(e.metaKey || e.ctrlKey)) return;
      if (e.key.toLowerCase() === 'k' || e.key === '/') {
        e.preventDefault();
        togglePalette();
      } else if (e.key.toLowerCase() === 'j') {
        e.preventDefault();
        toggleLog();
      }
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [togglePalette, toggleLog, mobileNav]);

  return (
    <div className="grain flex h-full overflow-hidden bg-ink-950">
      <a href="#main-content" className="skip-link">
        {t('a11y.skipToContent')}
      </a>

      {/* barre latérale — ordinateur */}
      <AnimatePresence>
        {desktopNav && (
          <motion.aside
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 276, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: [0.22, 0.9, 0.3, 1] }}
            className="hidden h-full shrink-0 overflow-hidden border-r border-white/6 md:block"
          >
            <Sidebar />
          </motion.aside>
        )}
      </AnimatePresence>

      {/* barre latérale — mobile */}
      <AnimatePresence>
        {mobileNav && (
          <>
            <motion.div
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
              className="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm md:hidden"
              onClick={() => setMobileNav(false)}
            />
            <motion.aside
              initial={{ x: -300 }} animate={{ x: 0 }} exit={{ x: -300 }}
              transition={{ type: 'spring', stiffness: 320, damping: 32 }}
              className="fixed bottom-0 left-0 top-0 z-50 w-[276px] border-r border-white/8 md:hidden"
            >
              <Sidebar onClose={() => setMobileNav(false)} />
            </motion.aside>
          </>
        )}
      </AnimatePresence>

      {/* colonne principale */}
      <main id="main-content" tabIndex={-1} className="relative flex min-w-0 flex-1 flex-col outline-none">
        <div className="ambient-glow pointer-events-none absolute inset-x-0 top-0 h-64" aria-hidden="true" />

        {/* en-tête */}
        <header role="banner" className="relative z-10 flex items-center gap-2 px-3 py-2.5 sm:px-4">
          <button
            type="button"
            onClick={() => setMobileNav(true)}
            className="rounded-lg p-2 text-zinc-500 transition hover:bg-white/5 hover:text-zinc-200 md:hidden"
            aria-label={t('a11y.openSidebar')}
            aria-expanded={mobileNav}
          >
            <Menu size={16} />
          </button>
          <button
            type="button"
            onClick={() => setDesktopNav((v) => !v)}
            className="hidden rounded-lg p-2 text-zinc-500 transition hover:bg-white/5 hover:text-zinc-200 md:block"
            title={t('header.sidebar')}
            aria-label={desktopNav ? t('a11y.closeSidebar') : t('a11y.openSidebar')}
            aria-expanded={desktopNav}
          >
            <PanelLeftClose size={15} className={cn(!desktopNav && 'rotate-180', 'transition-transform')} />
          </button>

          <div className="flex min-w-0 flex-1 items-center gap-2.5">
            {!desktopNav && <span className="hidden lg:block"><Logo size={20} /></span>}
            <div className="min-w-0 truncate text-[13px] text-zinc-400">
              {conv?.title && hasMessages ? conv.title : ''}
            </div>
            {/* Le badge n'apparaît que pendant le travail : rien à annoncer au repos. */}
            {isRunning && (
              <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-accent-500/30 bg-accent-500/10 px-2 py-0.5 font-mono text-[9px] uppercase tracking-wider text-accent-300">
                <span className="inline-block h-1 w-1 animate-pulse-dot rounded-full bg-accent-400" />
                {t('header.working')}
              </span>
            )}
          </div>

        </header>
        <NetworkStatus />

        {/* conversation */}
        <div ref={scrollRef} onScroll={onScroll} className="scroll-slim relative z-0 flex-1 overflow-y-auto">
          {hasMessages ? (
            <div className="mx-auto w-full max-w-3xl space-y-7 px-4 py-6 sm:px-6 sm:py-8">
              {messages.map((m) => (
                <ChatMessage
                  key={m.id}
                  msg={m}
                  conversationId={conv!.id}
                  onRetryCommand={(messageId, nodeId) => rerunCommand(conv!.id, messageId, nodeId)}
                />
              ))}
              <div className="h-2" />
            </div>
          ) : (
            <EmptyState onPick={(p) => send(p)} />
          )}
        </div>

        {/* zone de saisie */}
        <div className="safe-b relative z-10 px-3 pt-1 sm:px-6">
          <div className="mx-auto w-full max-w-3xl">
            <Composer running={isRunning} onSend={(t) => send(t)} onStop={cancel} />
          </div>
        </div>
      </main>

      <EventLogDrawer />
      <ConnectorsModal />
      <PersonaModal />
      <MemoryModal />
      <ExportModal />
      <SettingsModal />
      <CommandPalette />
      <GlobalDropZone />
    </div>
  );
}