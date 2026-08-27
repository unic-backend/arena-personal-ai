import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { Command, Menu, PanelLeftClose, PanelRight, Share2, SquarePen } from 'lucide-react';
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
import { CommandPalette } from './components/chat/CommandPalette';
import { GlobalDropZone } from './components/chat/GlobalDropZone';
import { NetworkStatus } from './components/chat/NetworkStatus';
import { cn } from './utils/cn';

export default function App() {
  const { conversations, activeId, isRunning, send, cancel, newChat, rerunCommand, toggleLog } = useChat();
  const { t, locale } = useI18n();
  const { togglePalette } = useCommandPalette();
  const [mobileNav, setMobileNav] = useState(false);
  const [exportOpen, setExportOpen] = useState(false);

  useEffect(() => {
    document.documentElement.lang = locale;
    document.title = locale === 'fr'
      ? 'Usman — Atelier IA personnel'
      : 'Usman — Personal AI Workbench';
  }, [locale]);

  /* Revalidate a persisted remote backend instead of trusting stale state. */
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

  /* smart auto-scroll: follow the stream unless the user scrolled up */
  useEffect(() => {
    const el = scrollRef.current;
    if (el && pinned.current) el.scrollTop = el.scrollHeight;
  }, [messages, messages[messages.length - 1]?.live, messages[messages.length - 1]?.activity]);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    pinned.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
  };

  /* shortcuts: ⌘K/⌘/ open Command Palette · ⌘J event log · Escape closes mobile nav */
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
      {/* Skip to Main Content Link for Keyboard & Screen Reader Users */}
      <a href="#main-content" className="skip-link">
        {t('a11y.skipToContent')}
      </a>

      {/* desktop sidebar */}
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

      {/* mobile sidebar */}
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

      {/* main column */}
      <main id="main-content" tabIndex={-1} className="relative flex min-w-0 flex-1 flex-col outline-none">
        {/* ambience — tracks the accent color live */}
        <div className="ambient-glow pointer-events-none absolute inset-x-0 top-0 h-64" aria-hidden="true" />

        {/* header */}
        <header role="banner" className="relative z-10 flex items-center gap-2 border-b border-white/6 px-3 py-2.5 sm:px-4">
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
            <div className="min-w-0">
              <div className="truncate text-[13px] font-medium text-zinc-200">
                {conv?.title && hasMessages ? conv.title : t('header.newConversation')}
              </div>
            </div>
            <span
              className={cn(
                'hidden shrink-0 items-center gap-1.5 rounded-full border px-2 py-0.5 font-mono text-[9px] uppercase tracking-wider sm:inline-flex',
                isRunning
                  ? 'border-accent-500/30 bg-accent-500/10 text-accent-300'
                  : 'border-white/8 bg-white/[0.03] text-zinc-500',
              )}
            >
              <span className={cn('inline-block h-1 w-1 rounded-full', isRunning ? 'animate-pulse-dot bg-accent-400' : 'bg-emerald-400')} />
              {isRunning ? t('header.working') : t('header.idle')}
            </span>
          </div>

          <button
            type="button"
            onClick={togglePalette}
            className="flex items-center gap-1.5 rounded-lg border border-white/8 bg-white/[0.03] px-2 py-1 text-[11px] text-zinc-400 transition hover:border-white/15 hover:text-zinc-200"
            title={t('cmd.title')}
          >
            <Command size={12} className="text-accent-400" />
            <span className="hidden sm:inline font-mono text-[9.5px]">⌘K</span>
          </button>

          <button
            type="button"
            onClick={() => setExportOpen(true)}
            className="rounded-lg p-2 text-zinc-500 transition hover:bg-white/5 hover:text-zinc-200"
            title={t('export.title')}
            aria-label={t('export.title')}
          >
            <Share2 size={15} />
          </button>

          <button
            onClick={() => newChat()}
            className="rounded-lg p-2 text-zinc-500 transition hover:bg-white/5 hover:text-zinc-200"
            title={t('cmd.newChat')}
          >
            <SquarePen size={15} />
          </button>
          <button
            onClick={toggleLog}
            className="rounded-lg p-2 text-zinc-500 transition hover:bg-white/5 hover:text-zinc-200"
            title={t('header.eventStream')}
          >
            <PanelRight size={15} />
          </button>
        </header>
        <NetworkStatus />

        {/* conversation */}
        <div ref={scrollRef} onScroll={onScroll} className="relative z-0 flex-1 overflow-y-auto scroll-slim">
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

        {/* composer */}
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
      <ExportModal isOpen={exportOpen} onClose={() => setExportOpen(false)} />
      <CommandPalette />
      <GlobalDropZone />
    </div>
  );
}
