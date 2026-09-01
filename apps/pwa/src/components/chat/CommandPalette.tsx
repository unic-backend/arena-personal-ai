import { useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  Brain,
  Clapperboard,
  Command,
  Globe,
  Languages,
  MessageSquare,
  Monitor,
  Moon,
  Plug,
  Plus,
  RotateCcw,
  Search,
  Share2,
  Smartphone,
  Sun,
  TerminalSquare,
  Trash2,
  UserCheck,
  X,
} from 'lucide-react';
import { useCommandPalette } from '../../lib/commands/commandStore';
import { useChat } from '../../lib/store/chatStore';
import { useConnectors } from '../../lib/store/connectorStore';
import { useVideoProject } from '../../lib/store/videoProjectStore';
import { usePersona } from '../../lib/store/personaStore';
import { useMemory } from '../../lib/memory/memoryStore';
import { useExport } from '../../lib/store/exportStore';
import { ACCENTS, useTheme } from '../../lib/theme';
import { useI18n } from '../../lib/i18n';
import { usePWA } from '../../lib/pwa';
import { cn } from '../../utils/cn';

interface PaletteItem {
  id: string;
  category: 'actions' | 'conversations' | 'theme' | 'language';
  title: string;
  subtitle?: string;
  icon: React.ReactNode;
  shortcut?: string;
  badge?: string;
  onSelect: () => void;
}

export function CommandPalette() {
  const { isOpen, search, closePalette, setSearch } = useCommandPalette();
  const { conversations, selectConversation, newChat, resetWorkspace, toggleLog, clearAllConversations } = useChat();
  const { setModalOpen: setConnectorsModalOpen } = useConnectors();
  const { setModalOpen: setVideoProjectOpen } = useVideoProject();
  const { setAccent, accent, colorMode, setColorMode } = useTheme();
  const { locale, setLocale, t } = useI18n();
  const { installable, install } = usePWA();

  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Focus input when opened
  useEffect(() => {
    if (isOpen) {
      setSelectedIndex(0);
      setTimeout(() => inputRef.current?.focus(), 40);
    }
  }, [isOpen]);

  const allItems: PaletteItem[] = useMemo(() => {
    const list: PaletteItem[] = [];

    // 1. Core Actions
    list.push({
      id: 'action-new-chat',
      category: 'actions',
      title: t('cmd.newChat'),
      subtitle: t('brand.sub'),
      icon: <Plus size={14} className="text-accent-400" />,
      shortcut: '⌘K',
      onSelect: () => {
        newChat();
        closePalette();
      },
    });

    list.push({
      id: 'action-persona',
      category: 'actions',
      title: t('cmd.openPersona'),
      subtitle: 'Custom instructions, user profile & voice tone',
      icon: <UserCheck size={14} className="text-accent-400" />,
      onSelect: () => {
        closePalette();
        usePersona.getState().setModalOpen(true);
      },
    });

    list.push({
      id: 'action-memory',
      category: 'actions',
      title: t('cmd.openMemory'),
      subtitle: 'Transparent facts and persistent preferences',
      icon: <Brain size={14} className="text-purple-400" />,
      onSelect: () => {
        closePalette();
        useMemory.getState().setModalOpen(true);
      },
    });

    list.push({
      id: 'action-connectors',
      category: 'actions',
      title: t('cmd.openConnectors'),
      subtitle: 'Gmail, GitHub, Google Drive, Notion, Slack...',
      icon: <Plug size={14} className="text-accent-300" />,
      onSelect: () => {
        closePalette();
        setConnectorsModalOpen(true);
      },
    });

    list.push({
      id: 'action-video-project',
      category: 'actions',
      title: t('vidproj.title'),
      subtitle: 'Vision, WanGP, MoneyPrinterTurbo, VoiceStudio, montage',
      icon: <Clapperboard size={14} className="text-accent-300" />,
      onSelect: () => {
        closePalette();
        setVideoProjectOpen(true);
      },
    });

    list.push({
      id: 'action-export',
      category: 'actions',
      title: t('cmd.export'),
      subtitle: 'Markdown (.md), JSON backup, Plain Text (.txt), Share',
      icon: <Share2 size={14} className="text-sky-400" />,
      onSelect: () => {
        closePalette();
        useExport.getState().openExport();
      },
    });

    list.push({
      id: 'action-event-log',
      category: 'actions',
      title: t('cmd.openLog'),
      subtitle: 'SSE stream frames inspector',
      icon: <TerminalSquare size={14} className="text-emerald-400" />,
      shortcut: '⌘J',
      onSelect: () => {
        closePalette();
        toggleLog();
      },
    });

    list.push({
      id: 'action-reset-repo',
      category: 'actions',
      title: t('cmd.resetRepo'),
      subtitle: 'Virtual testbed codebase',
      icon: <RotateCcw size={14} className="text-amber-400" />,
      onSelect: () => {
        resetWorkspace();
        closePalette();
      },
    });

    if (installable) {
      list.push({
        id: 'action-install-pwa',
        category: 'actions',
        title: t('cmd.installPwa'),
        subtitle: 'Standalone application mode',
        icon: <Smartphone size={14} className="text-sky-400" />,
        onSelect: () => {
          closePalette();
          void install();
        },
      });
    }

    if (conversations.length > 0) {
      list.push({
        id: 'action-clear-all',
        category: 'actions',
        title: t('cmd.clearHistory'),
        subtitle: `${conversations.length} items`,
        icon: <Trash2 size={14} className="text-red-400" />,
        onSelect: () => {
          closePalette();
          if (window.confirm(t('sidebar.clearAllConfirm'))) {
            clearAllConversations();
          }
        },
      });
    }

    // 2. Appearance & Accent Colors
    list.push({
      id: 'theme-mode-dark',
      category: 'theme',
      title: `${t('theme.mode')} · ${t('theme.dark')}`,
      subtitle: 'Dark appearance',
      icon: <Moon size={14} className="text-zinc-400" />,
      badge: colorMode === 'dark' ? 'Active' : undefined,
      onSelect: () => {
        setColorMode('dark');
        closePalette();
      },
    });

    list.push({
      id: 'theme-mode-light',
      category: 'theme',
      title: `${t('theme.mode')} · ${t('theme.light')}`,
      subtitle: 'Light appearance',
      icon: <Sun size={14} className="text-amber-300" />,
      badge: colorMode === 'light' ? 'Active' : undefined,
      onSelect: () => {
        setColorMode('light');
        closePalette();
      },
    });

    list.push({
      id: 'theme-mode-system',
      category: 'theme',
      title: `${t('theme.mode')} · ${t('theme.system')}`,
      subtitle: 'Match OS system preference',
      icon: <Monitor size={14} className="text-sky-300" />,
      badge: colorMode === 'system' ? 'Active' : undefined,
      onSelect: () => {
        setColorMode('system');
        closePalette();
      },
    });

    ACCENTS.forEach((item) => {
      const isCurrent = accent.id === item.id;
      list.push({
        id: `theme-${item.id}`,
        category: 'theme',
        title: t('cmd.switchTheme', { name: locale === 'fr' ? item.labelFr : item.label }),
        subtitle: item.swatch,
        icon: (
          <span
            className="inline-block h-3.5 w-3.5 rounded-full border border-white/20"
            style={{ backgroundColor: item.swatch }}
          />
        ),
        badge: isCurrent ? 'Active' : undefined,
        onSelect: () => {
          setAccent(item.id);
          closePalette();
        },
      });
    });

    // 3. Languages
    list.push({
      id: 'lang-fr',
      category: 'language',
      title: t('cmd.switchLang', { lang: 'Français' }),
      subtitle: 'French UI & assistant responses',
      icon: <Languages size={14} className="text-indigo-300" />,
      badge: locale === 'fr' ? 'Active' : undefined,
      onSelect: () => {
        setLocale('fr');
        closePalette();
      },
    });

    list.push({
      id: 'lang-en',
      category: 'language',
      title: t('cmd.switchLang', { lang: 'English' }),
      subtitle: 'English UI & assistant responses',
      icon: <Globe size={14} className="text-blue-300" />,
      badge: locale === 'en' ? 'Active' : undefined,
      onSelect: () => {
        setLocale('en');
        closePalette();
      },
    });

    // 4. Conversations jump list
    conversations.forEach((conv) => {
      list.push({
        id: `conv-${conv.id}`,
        category: 'conversations',
        title: conv.title || t('sidebar.untitled'),
        subtitle: `${conv.messages.length} ${t('sidebar.msgs')}`,
        icon: <MessageSquare size={14} className={conv.pinned ? 'text-accent-400' : 'text-zinc-500'} />,
        badge: conv.pinned ? t('sidebar.pinned') : undefined,
        onSelect: () => {
          selectConversation(conv.id);
          closePalette();
        },
      });
    });

    return list;
  }, [
    conversations,
    accent.id,
    locale,
    installable,
    t,
    newChat,
    closePalette,
    setConnectorsModalOpen,
    toggleLog,
    resetWorkspace,
    install,
    clearAllConversations,
    setAccent,
    setLocale,
    selectConversation,
  ]);

  // Filter items matching query
  const filteredItems = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return allItems;
    return allItems.filter((item) => {
      const matchTitle = item.title.toLowerCase().includes(q);
      const matchSubtitle = (item.subtitle || '').toLowerCase().includes(q);
      const matchCategory = item.category.toLowerCase().includes(q);
      return matchTitle || matchSubtitle || matchCategory;
    });
  }, [allItems, search]);

  // Ensure selectedIndex is within bounds
  useEffect(() => {
    setSelectedIndex(0);
  }, [filteredItems.length]);

  // Keyboard navigation
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      closePalette();
      return;
    }

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev + 1 < filteredItems.length ? prev + 1 : 0));
      return;
    }

    if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex((prev) => (prev - 1 >= 0 ? prev - 1 : Math.max(0, filteredItems.length - 1)));
      return;
    }

    if (e.key === 'Enter') {
      e.preventDefault();
      const selected = filteredItems[selectedIndex];
      if (selected) {
        selected.onSelect();
      }
    }
  };

  // Scroll active item into view
  useEffect(() => {
    const listEl = listRef.current;
    if (!listEl) return;
    const activeEl = listEl.querySelector(`[data-index="${selectedIndex}"]`) as HTMLElement;
    if (activeEl) {
      activeEl.scrollIntoView({ block: 'nearest' });
    }
  }, [selectedIndex]);

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[70] bg-black/75 backdrop-blur-sm"
            onClick={closePalette}
          />

          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label={t('cmd.title')}
            initial={{ opacity: 0, scale: 0.97, y: -16 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.98, y: -10 }}
            transition={{ type: 'spring', stiffness: 420, damping: 34 }}
            className="fixed inset-x-3.5 top-[7vh] z-[71] mx-auto flex max-h-[80vh] w-full max-w-xl flex-col overflow-hidden rounded-2xl border border-white/12 bg-ink-900 shadow-[0_30px_90px_rgba(0,0,0,0.85)] sm:top-[12vh]"
            onKeyDown={handleKeyDown}
          >
            {/* Search Input Bar */}
            <div className="relative flex items-center border-b border-white/8 px-4 py-3">
              <Search size={16} className="shrink-0 text-accent-400" />
              <input
                ref={inputRef}
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder={t('cmd.placeholder')}
                className="w-full min-w-0 bg-transparent px-3 text-[13.5px] text-zinc-100 outline-none placeholder:text-zinc-500"
              />
              <button
                type="button"
                onClick={closePalette}
                className="grid h-6 w-6 shrink-0 place-items-center rounded-md text-zinc-500 hover:bg-white/5 hover:text-zinc-200"
                aria-label="Close"
              >
                <X size={14} />
              </button>
            </div>

            {/* List of actions & conversations */}
            <div ref={listRef} className="flex-1 space-y-1 overflow-y-auto p-2 scroll-slim">
              {filteredItems.length === 0 ? (
                <div className="py-8 text-center">
                  <Command size={22} className="mx-auto mb-2 text-zinc-600" />
                  <p className="text-[12px] text-zinc-500">{t('cmd.noResults')}</p>
                </div>
              ) : (
                filteredItems.map((item, idx) => {
                  const isSelected = idx === selectedIndex;
                  return (
                    <div
                      key={item.id}
                      data-index={idx}
                      onClick={item.onSelect}
                      onMouseEnter={() => setSelectedIndex(idx)}
                      className={cn(
                        'flex cursor-pointer items-center gap-2.5 rounded-xl px-3 py-2 text-left transition-colors',
                        isSelected ? 'bg-accent-500/15 text-zinc-100' : 'text-zinc-300 hover:bg-white/[0.04]',
                      )}
                    >
                      <span
                        className={cn(
                          'grid h-7 w-7 shrink-0 place-items-center rounded-lg border',
                          isSelected
                            ? 'border-accent-500/30 bg-accent-500/15 text-accent-300'
                            : 'border-white/8 bg-white/[0.03] text-zinc-400',
                        )}
                      >
                        {item.icon}
                      </span>

                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5">
                          <span className="truncate text-[12.5px] font-medium leading-snug">{item.title}</span>
                          {item.badge && (
                            <span className="rounded bg-accent-500/15 px-1.5 py-0.2 font-mono text-[8.5px] font-semibold text-accent-300">
                              {item.badge}
                            </span>
                          )}
                        </div>
                        {item.subtitle && (
                          <div className="truncate font-mono text-[9.5px] text-zinc-500">{item.subtitle}</div>
                        )}
                      </div>

                      {item.shortcut && (
                        <kbd className="hidden rounded border border-white/10 bg-white/5 px-1.5 py-0.5 font-mono text-[9.5px] text-zinc-400 sm:inline-block">
                          {item.shortcut}
                        </kbd>
                      )}
                    </div>
                  );
                })
              )}
            </div>

            {/* Footer keyboard navigation helper */}
            <div className="flex items-center justify-between border-t border-white/8 bg-ink-950/60 px-4 py-2 text-[10px] text-zinc-500">
              <div className="flex items-center gap-3">
                <span>
                  <kbd className="rounded border border-white/10 bg-white/5 px-1 font-mono text-[9px]">↑</kbd>{' '}
                  <kbd className="rounded border border-white/10 bg-white/5 px-1 font-mono text-[9px]">↓</kbd> Naviguer
                </span>
                <span>
                  <kbd className="rounded border border-white/10 bg-white/5 px-1 font-mono text-[9px]">↵</kbd>{' '}
                  {t('cmd.enter')}
                </span>
              </div>
              <div>
                <kbd className="rounded border border-white/10 bg-white/5 px-1 font-mono text-[9px]">Esc</kbd>{' '}
                {t('cmd.esc')}
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
