import { useMemo, useRef, useState } from 'react';
import {
  Brain,
  Check,
  Command,
  Globe,
  MessageSquare,
  Monitor,
  Moon,
  Pencil,
  Pin,
  PinOff,
  Plug,
  Plus,
  RotateCcw,
  Search,
  Share2,
  Sun,
  TerminalSquare,
  Trash2,
  UserCheck,
  X,
} from 'lucide-react';
import { useCommandPalette } from '../../lib/commands/commandStore';
import { TOOL_REGISTRY } from '../../lib/agent/tools';
import { CONNECTOR_CATALOG } from '../../lib/connectors/catalog';
import { ToolExecutionCard } from '../activity/ToolExecutionCard';
import { BackendPanel } from './BackendPanel';
import { TypographyPanel } from './TypographyPanel';
import { PWAInstall } from './PWAInstall';
import { useConnectors } from '../../lib/store/connectorStore';
import { usePersona } from '../../lib/store/personaStore';
import { useMemory } from '../../lib/memory/memoryStore';
import { useExport } from '../../lib/store/exportStore';
import { Conversation, useChat } from '../../lib/store/chatStore';
import { useI18n, Lang } from '../../lib/i18n';
import { useTheme, ACCENTS } from '../../lib/theme';
import { cn } from '../../utils/cn';

export function Logo({ size = 26 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" className="text-accent-500">
      <circle cx="16" cy="16" r="12.5" fill="none" stroke="currentColor" strokeWidth="2.4" />
      <circle cx="16" cy="16" r="4.6" fill="currentColor" />
      <circle cx="26.7" cy="16" r="2" fill="currentColor" opacity="0.55" />
    </svg>
  );
}

function ThemeSwatches() {
  const { accent, setAccent, colorMode, setColorMode } = useTheme();
  const { t, locale } = useI18n();

  return (
    <div className="space-y-1.5 rounded-lg border border-white/8 p-2">
      {/* Accent Colors */}
      <div className="flex items-center justify-between gap-1">
        <span className="font-mono text-[9px] uppercase tracking-[0.14em] text-zinc-500">
          {t('theme.label')}
        </span>
        <div className="flex items-center gap-1.5">
          {ACCENTS.map((a) => (
            <button
              key={a.id}
              type="button"
              onClick={() => setAccent(a.id)}
              title={locale === 'fr' ? a.labelFr : a.label}
              className={cn(
                'h-3.5 w-3.5 rounded-full transition active:scale-90',
                accent.id === a.id
                  ? 'scale-125 ring-2 ring-white/80 ring-offset-1 ring-offset-ink-900'
                  : 'opacity-65 hover:scale-115 hover:opacity-100',
              )}
              style={{ background: `linear-gradient(135deg, ${a.c400}, ${a.c600})` }}
            />
          ))}
        </div>
      </div>

      {/* Color Mode: Dark / Light / System */}
      <div className="flex items-center justify-between gap-2 border-t border-white/6 pt-1.5">
        <span className="font-mono text-[9px] uppercase tracking-[0.14em] text-zinc-500">
          {t('theme.mode')}
        </span>
        <div className="flex items-center gap-0.5 rounded-md border border-white/6 bg-white/[0.02] p-0.5">
          <button
            type="button"
            onClick={() => setColorMode('dark')}
            title={t('theme.dark')}
            className={cn(
              'flex items-center gap-1 rounded px-1.5 py-0.5 text-[9px] font-mono transition',
              colorMode === 'dark' ? 'bg-white/10 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300',
            )}
          >
            <Moon size={9} />
            <span className="hidden sm:inline">{t('theme.dark')}</span>
          </button>
          <button
            type="button"
            onClick={() => setColorMode('light')}
            title={t('theme.light')}
            className={cn(
              'flex items-center gap-1 rounded px-1.5 py-0.5 text-[9px] font-mono transition',
              colorMode === 'light' ? 'bg-accent-500/20 text-accent-300' : 'text-zinc-500 hover:text-zinc-300',
            )}
          >
            <Sun size={9} />
            <span className="hidden sm:inline">{t('theme.light')}</span>
          </button>
          <button
            type="button"
            onClick={() => setColorMode('system')}
            title={t('theme.system')}
            className={cn(
              'flex items-center gap-1 rounded px-1.5 py-0.5 text-[9px] font-mono transition',
              colorMode === 'system' ? 'bg-white/10 text-zinc-100' : 'text-zinc-500 hover:text-zinc-300',
            )}
          >
            <Monitor size={9} />
          </button>
        </div>
      </div>
    </div>
  );
}

function LangToggle() {
  const { locale, setLocale, t } = useI18n();
  const opt = (l: Lang, label: string) => (
    <button
      key={l}
      onClick={() => setLocale(l)}
      className={cn(
        'flex-1 rounded-md px-2 py-1 font-mono text-[10px] transition',
        locale === l ? 'lang-active bg-accent-500/20 text-accent-300' : 'text-zinc-500 hover:text-zinc-300',
      )}
    >
      {label}
    </button>
  );
  return (
    <div className="flex items-center gap-2 rounded-lg border border-white/8 px-2 py-1">
      <Globe size={11} className="shrink-0 text-zinc-500" />
      <span className="sr-only">{t('sidebar.lang')}</span>
      <div className="flex flex-1 gap-0.5">
        {opt('en', 'EN')}
        {opt('fr', 'FR')}
      </div>
    </div>
  );
}

function ConnectorsButton({ onPick }: { onPick?: () => void }) {
  const { t } = useI18n();
  const { setModalOpen, connectors } = useConnectors();
  const n = Object.values(connectors).filter((s) => s.status === 'connected').length;
  return (
    <button
      onClick={() => {
        setModalOpen(true);
        onPick?.();
      }}
      className="flex w-full items-center gap-2 rounded-xl border border-white/8 px-3 py-2 text-[12px] text-zinc-400 transition hover:border-white/15 hover:text-zinc-200 active:scale-[0.99]"
    >
      <Plug size={13} className={n > 0 ? 'text-accent-400' : 'text-zinc-500'} />
      {t('conn.open')}
      <span
        className={cn(
          'ml-auto rounded-full px-1.5 py-0.5 font-mono text-[9px]',
          n > 0 ? 'bg-accent-500/15 text-accent-300' : 'bg-white/5 text-zinc-600',
        )}
      >
        {n}/{CONNECTOR_CATALOG.length}
      </span>
    </button>
  );
}

function PersonaButton({ onPick }: { onPick?: () => void }) {
  const { t } = useI18n();
  const { setModalOpen, userName, userRole, customInstructions } = usePersona();
  const hasCustom = Boolean(userName.trim() || userRole.trim() || customInstructions.trim());

  return (
    <button
      type="button"
      onClick={() => {
        setModalOpen(true);
        onPick?.();
      }}
      className={cn(
        'flex w-full items-center gap-2 rounded-lg border px-2.5 py-2 text-left transition active:scale-[0.99]',
        hasCustom
          ? 'border-accent-500/30 bg-accent-500/[0.04] text-zinc-200 hover:border-accent-500/50'
          : 'border-white/8 bg-white/[0.02] text-zinc-400 hover:border-white/15 hover:text-zinc-200',
      )}
    >
      <UserCheck size={13} className={hasCustom ? 'text-accent-400' : 'text-zinc-500'} />
      <span className="flex-1 truncate font-mono text-[9px] uppercase tracking-[0.14em]">
        {t('sidebar.persona')}
      </span>
      {userName.trim() ? (
        <span className="truncate font-mono text-[9px] text-accent-300">
          {userName.trim().slice(0, 12)}
        </span>
      ) : hasCustom ? (
        <span className="h-1.5 w-1.5 rounded-full bg-accent-400" />
      ) : null}
    </button>
  );
}

function MemoryButton({ onPick }: { onPick?: () => void }) {
  const { t } = useI18n();
  const { setModalOpen, memories } = useMemory();
  const activeCount = memories.filter((m) => m.enabled).length;

  return (
    <button
      type="button"
      onClick={() => {
        setModalOpen(true);
        onPick?.();
      }}
      className={cn(
        'flex w-full items-center gap-2 rounded-lg border px-2.5 py-2 text-left transition active:scale-[0.99]',
        activeCount > 0
          ? 'border-accent-500/30 bg-accent-500/[0.04] text-zinc-200 hover:border-accent-500/50'
          : 'border-white/8 bg-white/[0.02] text-zinc-400 hover:border-white/15 hover:text-zinc-200',
      )}
    >
      <Brain size={13} className={activeCount > 0 ? 'text-accent-400' : 'text-zinc-500'} />
      <span className="flex-1 truncate font-mono text-[9px] uppercase tracking-[0.14em]">
        {t('sidebar.memory')}
      </span>
      <span className="rounded-full bg-white/5 px-1.5 py-0.2 font-mono text-[8.5px] text-zinc-400">
        {activeCount}
      </span>
    </button>
  );
}

/* ── Date Grouping Helper ── */
interface GroupedConversations {
  pinned: Conversation[];
  today: Conversation[];
  yesterday: Conversation[];
  last7Days: Conversation[];
  last30Days: Conversation[];
  older: Conversation[];
}

function groupConversations(list: Conversation[]): GroupedConversations {
  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const startOfYesterday = startOfToday - 86400000;
  const startOf7Days = startOfToday - 6 * 86400000;
  const startOf30Days = startOfToday - 29 * 86400000;

  const groups: GroupedConversations = {
    pinned: [],
    today: [],
    yesterday: [],
    last7Days: [],
    last30Days: [],
    older: [],
  };

  list.forEach((c) => {
    if (c.pinned) {
      groups.pinned.push(c);
      return;
    }
    const t = c.updatedAt || c.createdAt;
    if (t >= startOfToday) {
      groups.today.push(c);
    } else if (t >= startOfYesterday) {
      groups.yesterday.push(c);
    } else if (t >= startOf7Days) {
      groups.last7Days.push(c);
    } else if (t >= startOf30Days) {
      groups.last30Days.push(c);
    } else {
      groups.older.push(c);
    }
  });

  return groups;
}

export function Sidebar({ onClose }: { onClose?: () => void }) {
  const {
    conversations,
    activeId,
    selectConversation,
    deleteConversation,
    renameConversation,
    togglePinConversation,
    clearAllConversations,
    newChat,
    resetWorkspace,
    toggleLog,
    logOpen,
  } = useChat();
  const { t } = useI18n();

  const [searchQuery, setSearchQuery] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const [confirmClear, setConfirmClear] = useState(false);
  const editInputRef = useRef<HTMLInputElement>(null);

  // Filter conversations by title or message contents
  const filteredConversations = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return conversations;
    return conversations.filter((c) => {
      const matchTitle = (c.title || '').toLowerCase().includes(q);
      const matchMsg = c.messages.some((m) => (m.text || '').toLowerCase().includes(q));
      return matchTitle || matchMsg;
    });
  }, [conversations, searchQuery]);

  const groups = useMemo(() => groupConversations(filteredConversations), [filteredConversations]);

  const handleStartRename = (c: Conversation) => {
    setEditingId(c.id);
    setEditTitle(c.title || '');
    setTimeout(() => {
      editInputRef.current?.focus();
      editInputRef.current?.select();
    }, 50);
  };

  const handleSaveRename = (id: string) => {
    if (editTitle.trim()) {
      renameConversation(id, editTitle.trim());
    }
    setEditingId(null);
    setEditTitle('');
  };

  const handleCancelRename = () => {
    setEditingId(null);
    setEditTitle('');
  };

  const renderConversationItem = (c: Conversation) => {
    const isEditing = editingId === c.id;
    const isActive = activeId === c.id;

    if (isEditing) {
      return (
        <div key={c.id} className="flex items-center gap-1 rounded-lg bg-white/[0.08] p-1.5">
          <input
            ref={editInputRef}
            value={editTitle}
            onChange={(e) => setEditTitle(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleSaveRename(c.id);
              if (e.key === 'Escape') handleCancelRename();
            }}
            className="w-full min-w-0 rounded bg-ink-950 px-2 py-1 text-[11.5px] text-zinc-100 outline-none ring-1 ring-accent-500/50"
          />
          <button
            type="button"
            onClick={() => handleSaveRename(c.id)}
            className="grid h-6 w-6 shrink-0 place-items-center rounded text-emerald-400 hover:bg-emerald-400/20"
            title="Save"
          >
            <Check size={12} />
          </button>
          <button
            type="button"
            onClick={handleCancelRename}
            className="grid h-6 w-6 shrink-0 place-items-center rounded text-zinc-400 hover:bg-white/10 hover:text-zinc-200"
            title="Cancel"
          >
            <X size={12} />
          </button>
        </div>
      );
    }

    return (
      <div
        key={c.id}
        className={cn(
          'group flex cursor-pointer items-center gap-2 rounded-lg px-2 py-1.5 transition',
          isActive ? 'bg-white/[0.08] text-zinc-100' : 'text-zinc-400 hover:bg-white/[0.03] hover:text-zinc-200',
        )}
        onClick={() => {
          selectConversation(c.id);
          onClose?.();
        }}
      >
        <MessageSquare
          size={12}
          className={cn('shrink-0', c.pinned ? 'text-accent-400' : isActive ? 'text-accent-400' : 'text-zinc-600')}
        />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1">
            <span className="truncate text-[12px]">{c.title || t('sidebar.untitled')}</span>
            {c.pinned && <Pin size={9} className="shrink-0 text-accent-400" />}
          </div>
          {c.messages.length > 0 && (
            <div className="mt-0.5 truncate font-mono text-[9px] text-zinc-600">
              {c.messages.length} {t('sidebar.msgs')}
            </div>
          )}
        </div>

        {/* Hover / mobile action buttons */}
        <div className="flex shrink-0 items-center gap-0.5 opacity-80 transition-opacity sm:opacity-0 sm:group-hover:opacity-100">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              togglePinConversation(c.id);
            }}
            className={cn(
              'rounded p-1 text-zinc-500 transition hover:bg-white/10 hover:text-zinc-200',
              c.pinned && 'text-accent-400',
            )}
            title={c.pinned ? t('sidebar.unpin') : t('sidebar.pin')}
          >
            {c.pinned ? <PinOff size={11} /> : <Pin size={11} />}
          </button>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              handleStartRename(c);
            }}
            className="rounded p-1 text-zinc-500 transition hover:bg-white/10 hover:text-zinc-200"
            title={t('sidebar.rename')}
          >
            <Pencil size={11} />
          </button>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              deleteConversation(c.id);
            }}
            className="rounded p-1 text-zinc-500 transition hover:bg-red-400/10 hover:text-red-300"
            title={t('sidebar.delete')}
          >
            <Trash2 size={11} />
          </button>
        </div>
      </div>
    );
  };

  const renderGroup = (title: string, list: Conversation[]) => {
    if (!list.length) return null;
    return (
      <div key={title} className="space-y-0.5">
        <div className="flex items-center justify-between px-1.5 py-1 font-mono text-[9px] uppercase tracking-[0.14em] text-zinc-600">
          <span>{title}</span>
          <span className="text-[8.5px] opacity-75">{list.length}</span>
        </div>
        {list.map(renderConversationItem)}
      </div>
    );
  };

  return (
    <div className="flex h-full w-full flex-col bg-ink-900">
      {/* brand */}
      <div className="flex items-center gap-2.5 px-4 pb-3 pt-4">
        <Logo />
        <div className="min-w-0 flex-1">
          <div className="font-serif text-[17px] leading-none text-zinc-100">Usman</div>
          <div className="mt-1 font-mono text-[8.5px] uppercase tracking-[0.22em] text-zinc-600">{t('brand.sub')}</div>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="rounded-md p-1.5 text-zinc-500 transition hover:bg-white/5 hover:text-zinc-300 md:hidden"
          >
            <X size={15} />
          </button>
        )}
      </div>

      <div className="space-y-1.5 px-3">
        <button
          onClick={() => {
            newChat();
            onClose?.();
          }}
          className="flex w-full items-center gap-2 rounded-xl border border-white/8 bg-white/[0.03] px-3 py-2.5 text-[12.5px] font-medium text-zinc-200 transition hover:border-white/15 hover:bg-white/[0.06] active:scale-[0.99]"
        >
          <Plus size={14} className="text-accent-400" />
          {t('sidebar.new')}
        </button>
        <div className="flex gap-1.5">
          <div className="flex-1">
            <ConnectorsButton onPick={onClose} />
          </div>
          <button
            type="button"
            onClick={() => {
              useCommandPalette.getState().openPalette();
              onClose?.();
            }}
            className="flex items-center justify-center gap-1 rounded-xl border border-white/8 bg-white/[0.02] px-2.5 text-zinc-400 transition hover:border-white/15 hover:text-zinc-200"
            title={`${t('cmd.title')} (⌘K)`}
          >
            <Command size={13} className="text-accent-400" />
          </button>
        </div>
      </div>

      {/* search input */}
      {conversations.length > 0 && (
        <div className="mt-3 px-3">
          <div className="relative flex items-center">
            <Search size={12} className="pointer-events-none absolute left-2.5 text-zinc-500" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={t('sidebar.searchPh')}
              className="w-full rounded-lg border border-white/8 bg-ink-950/60 py-1.5 pl-7 pr-7 text-[11px] text-zinc-200 outline-none placeholder:text-zinc-600 focus:border-accent-500/40"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery('')}
                className="absolute right-2 grid h-4 w-4 place-items-center rounded text-zinc-500 hover:text-zinc-200"
                title={t('sidebar.clearSearch')}
              >
                <X size={11} />
              </button>
            )}
          </div>
        </div>
      )}

      {/* conversations history */}
      <div className="mt-2.5 flex-1 overflow-y-auto px-3 scroll-slim">
        {conversations.length === 0 ? (
          <p className="px-1 py-3 text-[11px] leading-relaxed text-zinc-600">{t('sidebar.empty')}</p>
        ) : filteredConversations.length === 0 ? (
          <div className="px-1 py-4 text-center">
            <p className="text-[11px] text-zinc-500">{t('sidebar.noSearchResults', { query: searchQuery })}</p>
            <button
              type="button"
              onClick={() => setSearchQuery('')}
              className="mt-2 text-[10.5px] text-accent-400 hover:underline"
            >
              {t('sidebar.clearSearch')}
            </button>
          </div>
        ) : (
          <div className="space-y-3 pb-2">
            {renderGroup(t('sidebar.pinned'), groups.pinned)}
            {renderGroup(t('sidebar.today'), groups.today)}
            {renderGroup(t('sidebar.yesterday'), groups.yesterday)}
            {renderGroup(t('sidebar.last7Days'), groups.last7Days)}
            {renderGroup(t('sidebar.last30Days'), groups.last30Days)}
            {renderGroup(t('sidebar.older'), groups.older)}

            {/* Clear all history option */}
            {!searchQuery && conversations.length > 2 && (
              <div className="pt-2">
                {confirmClear ? (
                  <div className="rounded-lg border border-red-400/20 bg-red-400/[0.06] p-2 text-center">
                    <p className="text-[10px] text-red-200">{t('sidebar.clearAllConfirm')}</p>
                    <div className="mt-2 flex justify-center gap-2">
                      <button
                        type="button"
                        onClick={() => setConfirmClear(false)}
                        className="rounded px-2 py-1 text-[9.5px] text-zinc-400 hover:text-zinc-200"
                      >
                        {t('msg.cancel')}
                      </button>
                      <button
                        type="button"
                        onClick={() => {
                          clearAllConversations();
                          setConfirmClear(false);
                        }}
                        className="rounded bg-red-400/20 px-2 py-1 text-[9.5px] font-medium text-red-300 hover:bg-red-400/30"
                      >
                        {t('sidebar.delete')}
                      </button>
                    </div>
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={() => setConfirmClear(true)}
                    className="flex w-full items-center justify-center gap-1.5 rounded-lg py-1.5 font-mono text-[9.5px] text-zinc-600 transition hover:text-red-400/80"
                  >
                    <Trash2 size={10} />
                    {t('sidebar.clearAll')}
                  </button>
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* runtime panel — rendered from the backend tool registry */}
      <div className="border-t border-white/6 px-3 pb-3 pt-3">
        <div className="mb-2 flex items-center justify-between px-1">
          <span className="font-mono text-[9px] uppercase tracking-[0.18em] text-zinc-600">
            {t('sidebar.runtime')} · {TOOL_REGISTRY.filter((x) => x.status === 'online').length}/{TOOL_REGISTRY.length}{' '}
            {t('sidebar.toolsOnline')}
          </span>
          <span
            className="inline-block h-1.5 w-1.5 animate-pulse-dot rounded-full bg-emerald-400"
            title={t('sidebar.backend')}
          />
        </div>
        <div className="max-h-56 space-y-1.5 overflow-y-auto scroll-slim">
          {TOOL_REGISTRY.map((tool, i) => (
            <ToolExecutionCard key={tool.id} tool={tool} index={i} />
          ))}
        </div>
        <div className="mt-2.5 grid grid-cols-3 gap-1.5">
          <button
            onClick={resetWorkspace}
            className="flex items-center justify-center gap-1 rounded-lg border border-white/8 px-1.5 py-1.5 text-[10px] text-zinc-400 transition hover:border-white/15 hover:text-zinc-200"
            title={t('sidebar.resetTitle')}
          >
            <RotateCcw size={11} />
            <span className="truncate">{t('sidebar.reset')}</span>
          </button>
          <button
            type="button"
            onClick={() => {
              useExport.getState().openExport();
              onClose?.();
            }}
            className="flex items-center justify-center gap-1 rounded-lg border border-white/8 px-1.5 py-1.5 text-[10px] text-zinc-400 transition hover:border-white/15 hover:text-zinc-200"
            title={t('export.title')}
          >
            <Share2 size={11} className="text-accent-400" />
            <span className="truncate">{t('export.shareHeader')}</span>
          </button>
          <button
            onClick={toggleLog}
            className={cn(
              'flex items-center justify-center gap-1 rounded-lg border px-1.5 py-1.5 text-[10px] transition',
              logOpen
                ? 'border-accent-500/40 bg-accent-500/10 text-accent-300'
                : 'border-white/8 text-zinc-400 hover:border-white/15 hover:text-zinc-200',
            )}
          >
            <TerminalSquare size={11} />
            <span className="truncate">{t('sidebar.eventLog')}</span>
          </button>
        </div>
        <div className="mt-1.5 space-y-1.5">
          <PWAInstall />
          <PersonaButton onPick={onClose} />
          <MemoryButton onPick={onClose} />
          <BackendPanel />
          <TypographyPanel />
          <ThemeSwatches />
          <LangToggle />
        </div>
      </div>
    </div>
  );
}
