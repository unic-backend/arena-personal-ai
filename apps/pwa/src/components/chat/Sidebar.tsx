/* ─────────────────────────────────────────────────────────────
   Barre latérale — l'essentiel, rien de plus.
   Nouvelle conversation, capacités, recherche, historique, et
   Réglages tout en bas. Pas de suppression globale : une erreur
   de clic ne doit jamais pouvoir tout effacer.
   ───────────────────────────────────────────────────────────── */

import { useMemo, useRef, useState } from 'react';
import {
  Check,
  MessageSquare,
  Pencil,
  Pin,
  PinOff,
  Plus,
  Search,
  Settings,
  Sparkles,
  Trash2,
  X,
} from 'lucide-react';
import { Conversation, useChat } from '../../lib/store/chatStore';
import { CAPACITES, useCapacite } from '../../lib/capacites';
import { useI18n } from '../../lib/i18n';
import { useSettings } from './SettingsModal';
import { cn } from '../../utils/cn';

export function Logo({ size = 26, className }: { size?: number; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" className={cn('text-accent-500', className)}>
      <circle cx="16" cy="16" r="12.5" fill="none" stroke="currentColor" strokeWidth="2.4" />
      <circle cx="16" cy="16" r="4.6" fill="currentColor" />
      <circle cx="26.7" cy="16" r="2" fill="currentColor" opacity="0.55" />
    </svg>
  );
}

/* ── Regroupement par date ── */
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
    newChat,
  } = useChat();
  const { t, locale } = useI18n();
  const { openSettings } = useSettings();
  const { active: capaciteActive, choisir, effacer } = useCapacite();

  const [searchQuery, setSearchQuery] = useState('');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');
  const editInputRef = useRef<HTMLInputElement>(null);

  /* Chaque espace a sa propre liste : une conversation nee dans « Usman
     Coder » ne se voit pas dans « UniC Plaquiste », ni dans l'espace
     general. `espace` absent (conversations d'avant ce changement) compte
     comme l'espace general, au meme titre que `null`. */
  const conversationsDeLEspace = useMemo(
    () => conversations.filter((c) => (c.espace ?? null) === capaciteActive),
    [conversations, capaciteActive],
  );

  /* Recherche sur le titre et sur le contenu des messages, DANS l'espace actif. */
  const filteredConversations = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return conversationsDeLEspace;
    return conversationsDeLEspace.filter((c) => {
      const matchTitle = (c.title || '').toLowerCase().includes(q);
      const matchMsg = c.messages.some((m) => (m.text || '').toLowerCase().includes(q));
      return matchTitle || matchMsg;
    });
  }, [conversationsDeLEspace, searchQuery]);

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
            title={locale === 'fr' ? 'Enregistrer' : 'Save'}
          >
            <Check size={12} />
          </button>
          <button
            type="button"
            onClick={handleCancelRename}
            className="grid h-6 w-6 shrink-0 place-items-center rounded text-zinc-400 hover:bg-white/10 hover:text-zinc-200"
            title={t('msg.cancel')}
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
          className={cn('shrink-0', c.pinned || isActive ? 'text-accent-400' : 'text-zinc-600')}
        />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1">
            <span className="truncate text-[12px]">{c.title || t('sidebar.untitled')}</span>
            {c.pinned && <Pin size={9} className="shrink-0 text-accent-400" />}
          </div>
        </div>

        {/* Actions : visibles au survol sur ordinateur, toujours sur mobile. */}
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
        <div className="px-1.5 py-1 font-mono text-[9px] uppercase tracking-[0.14em] text-zinc-600">{title}</div>
        {list.map(renderConversationItem)}
      </div>
    );
  };

  return (
    <div className="flex h-full w-full flex-col bg-ink-900">
      {/* marque */}
      <div className="flex items-center gap-2.5 px-4 pb-3 pt-4">
        <Logo />
        <div className="min-w-0 flex-1">
          <div className="font-serif text-[17px] leading-none text-zinc-100">Usman</div>
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

      <div className="px-3">
        <button
          onClick={() => {
            // Reste dans l'espace ouvert : une nouvelle conversation depuis
            // « Usman Coder » doit rester une conversation Coder, pas
            // repartir sur l'espace general.
            newChat();
            onClose?.();
          }}
          className="flex w-full items-center gap-2 rounded-xl border border-white/8 bg-white/[0.03] px-3 py-2.5 text-[12.5px] font-medium text-zinc-200 transition hover:border-white/15 hover:bg-white/[0.06] active:scale-[0.99]"
        >
          <Plus size={14} className="text-accent-400" />
          {t('sidebar.new')}
        </button>
      </div>

      {/* espaces — Usman general, puis une capacite par espace specialise.
          Chacun a sa propre liste de conversations juste en dessous : changer
          d'espace change ce qui s'affiche, pas seulement les suggestions. */}
      <div className="mt-2 space-y-0.5 px-3">
        <button
          type="button"
          onClick={() => {
            effacer();
            newChat();
            onClose?.();
          }}
          className={cn(
            'flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[12px] transition active:scale-[0.99]',
            capaciteActive === null
              ? 'bg-accent-500/10 text-accent-200'
              : 'text-zinc-400 hover:bg-white/[0.04] hover:text-zinc-200',
          )}
        >
          <Sparkles size={14} className={capaciteActive === null ? 'text-accent-400' : 'text-zinc-500'} />
          Usman
        </button>
        {CAPACITES.map((cap) => {
          const Icone = cap.icone;
          const choisie = capaciteActive === cap.id;
          return (
            <button
              key={cap.id}
              type="button"
              onClick={() => {
                choisir(cap.id);
                newChat();
                onClose?.();
              }}
              className={cn(
                'flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[12px] transition active:scale-[0.99]',
                choisie
                  ? 'bg-accent-500/10 text-accent-200'
                  : 'text-zinc-400 hover:bg-white/[0.04] hover:text-zinc-200',
              )}
            >
              <Icone size={14} className={choisie ? 'text-accent-400' : 'text-zinc-500'} />
              {locale === 'fr' ? cap.nomFr : cap.nomEn}
            </button>
          );
        })}
      </div>

      {/* recherche — sur l'espace actif uniquement */}
      {conversationsDeLEspace.length > 0 && (
        <div className="mt-3 border-t border-white/6 px-3 pt-3">
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

      {/* historique */}
      <div className="scroll-slim mt-2.5 flex-1 overflow-y-auto px-3">
        {conversationsDeLEspace.length === 0 ? (
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
          </div>
        )}
      </div>

      {/* réglages — dernière ligne, comme sur Gemini */}
      <div className="border-t border-white/6 px-3 py-2.5">
        <button
          type="button"
          onClick={() => {
            openSettings();
            onClose?.();
          }}
          className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 text-[12.5px] text-zinc-400 transition hover:bg-white/[0.05] hover:text-zinc-100 active:scale-[0.99]"
        >
          <Settings size={15} className="text-zinc-500" />
          {locale === 'fr' ? 'Réglages' : 'Settings'}
        </button>
      </div>
    </div>
  );
}