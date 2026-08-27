import { useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  Brain,
  Check,
  Database,
  Pencil,
  Plus,
  RotateCcw,
  Search,
  Trash2,
  X,
} from 'lucide-react';
import {
  MemoryCategory,
  MemoryItem,
  useMemory,
} from '../../lib/memory/memoryStore';
import { useI18n } from '../../lib/i18n';
import { cn } from '../../utils/cn';

export function MemoryModal() {
  const {
    memories,
    modalOpen,
    setModalOpen,
    addMemory,
    updateMemory,
    toggleMemory,
    deleteMemory,
    clearAllMemories,
    resetToDefaults,
  } = useMemory();
  const { t, locale } = useI18n();
  const fr = locale === 'fr';

  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<MemoryCategory | 'all'>('all');
  const [newContent, setNewContent] = useState('');
  const [newCategory, setNewCategory] = useState<MemoryCategory>('preference');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editContent, setEditContent] = useState('');
  const [editCat, setEditCat] = useState<MemoryCategory>('preference');
  const [confirmClear, setConfirmClear] = useState(false);

  const newContentRef = useRef<HTMLInputElement>(null);

  // Close on ESC
  useEffect(() => {
    if (!modalOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setModalOpen(false);
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [modalOpen, setModalOpen]);

  const categories: Array<{ id: MemoryCategory; label: string; color: string }> = [
    { id: 'preference', label: t('memory.preference'), color: 'text-amber-400 bg-amber-500/10 border-amber-500/25' },
    { id: 'project', label: t('memory.project'), color: 'text-sky-400 bg-sky-500/10 border-sky-500/25' },
    { id: 'fact', label: t('memory.fact'), color: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/25' },
    { id: 'instruction', label: t('memory.instruction'), color: 'text-purple-400 bg-purple-500/10 border-purple-500/25' },
  ];

  const filteredMemories = useMemo(() => {
    return memories.filter((m) => {
      const matchCat = selectedCategory === 'all' || m.category === selectedCategory;
      const matchSearch = !searchQuery.trim() || m.content.toLowerCase().includes(searchQuery.toLowerCase().trim());
      return matchCat && matchSearch;
    });
  }, [memories, selectedCategory, searchQuery]);

  const handleAdd = () => {
    if (!newContent.trim()) return;
    addMemory(newContent.trim(), newCategory);
    setNewContent('');
  };

  const handleStartEdit = (m: MemoryItem) => {
    setEditingId(m.id);
    setEditContent(m.content);
    setEditCat(m.category);
  };

  const handleSaveEdit = (id: string) => {
    if (editContent.trim()) {
      updateMemory(id, editContent.trim(), editCat);
    }
    setEditingId(null);
  };

  const activeCount = memories.filter((m) => m.enabled).length;

  return (
    <AnimatePresence>
      {modalOpen && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[65] bg-black/75 backdrop-blur-sm"
            onClick={() => setModalOpen(false)}
          />

          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby="memory-modal-title"
            initial={{ opacity: 0, scale: 0.96, y: 16 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: 12 }}
            transition={{ type: 'spring', stiffness: 380, damping: 32 }}
            className="fixed inset-x-3 top-[4vh] z-[66] mx-auto flex max-h-[92vh] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-white/10 bg-ink-900 shadow-[0_40px_120px_-20px_rgba(0,0,0,0.9)] sm:top-[7vh]"
          >
            {/* Header */}
            <div className="flex items-center gap-2.5 border-b border-white/7 px-4 py-3">
              <span className="grid h-7 w-7 place-items-center rounded-lg border border-accent-500/30 bg-accent-500/10 text-accent-300">
                <Brain size={14} />
              </span>
              <div className="flex-1 min-w-0">
                <h2 id="memory-modal-title" className="text-[13.5px] font-medium text-zinc-100 truncate">
                  {t('memory.title')}
                </h2>
                <div className="font-mono text-[9px] text-zinc-400 truncate">
                  {t('memory.activeCount', { n: activeCount })}
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
            <div className="flex-1 space-y-3.5 overflow-y-auto p-4 scroll-slim">
              {/* Add New Memory Input Box */}
              <div className="rounded-xl border border-white/8 bg-white/[0.025] p-3 space-y-2">
                <div className="flex items-center gap-1.5">
                  <input
                    ref={newContentRef}
                    type="text"
                    value={newContent}
                    onChange={(e) => setNewContent(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
                    placeholder={t('memory.addPh')}
                    className="w-full min-w-0 rounded-lg border border-white/10 bg-ink-950 px-2.5 py-1.5 text-[11.5px] text-zinc-100 outline-none placeholder:text-zinc-600 focus:border-accent-500/50"
                  />
                  <button
                    type="button"
                    onClick={handleAdd}
                    disabled={!newContent.trim()}
                    className="inline-flex items-center gap-1 shrink-0 rounded-lg bg-accent-500 px-3 py-1.5 text-[11px] font-medium text-ink-950 transition hover:bg-accent-400 disabled:opacity-40"
                  >
                    <Plus size={12} strokeWidth={2.5} />
                    <span>{t('memory.addBtn')}</span>
                  </button>
                </div>

                <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
                  <span className="font-mono text-[8.5px] uppercase tracking-wider text-zinc-600">
                    {t('memory.category')} :
                  </span>
                  {categories.map((c) => (
                    <button
                      key={c.id}
                      type="button"
                      onClick={() => setNewCategory(c.id)}
                      className={cn(
                        'rounded-md border px-2 py-0.5 font-mono text-[9px] transition active:scale-95',
                        newCategory === c.id
                          ? 'border-accent-500/40 bg-accent-500/15 text-accent-300'
                          : 'border-white/6 bg-white/[0.02] text-zinc-500 hover:text-zinc-300',
                      )}
                    >
                      {c.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Category Filter Tabs & Search */}
              <div className="flex items-center gap-2">
                <div className="relative flex-1">
                  <Search size={11} className="pointer-events-none absolute left-2 text-zinc-500" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder={fr ? 'Filtrer les faits…' : 'Filter memories…'}
                    className="w-full rounded-lg border border-white/8 bg-ink-950/60 py-1 pl-6 pr-2 text-[10.5px] text-zinc-200 outline-none placeholder:text-zinc-600 focus:border-accent-500/40"
                  />
                </div>

                <div className="flex items-center gap-1 overflow-x-auto scroll-slim">
                  <button
                    type="button"
                    onClick={() => setSelectedCategory('all')}
                    className={cn(
                      'rounded-lg px-2 py-1 font-mono text-[9.5px] transition',
                      selectedCategory === 'all'
                        ? 'bg-white/10 text-zinc-100'
                        : 'text-zinc-500 hover:text-zinc-300',
                    )}
                  >
                    {fr ? 'Tous' : 'All'}
                  </button>
                  {categories.map((c) => (
                    <button
                      key={c.id}
                      type="button"
                      onClick={() => setSelectedCategory(c.id)}
                      className={cn(
                        'rounded-lg px-2 py-1 font-mono text-[9.5px] transition',
                        selectedCategory === c.id
                          ? 'bg-accent-500/15 text-accent-300'
                          : 'text-zinc-500 hover:text-zinc-300',
                      )}
                    >
                      {c.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Memory Items List */}
              <div className="space-y-1.5">
                {filteredMemories.length === 0 ? (
                  <div className="rounded-xl border border-white/6 bg-white/[0.01] p-6 text-center">
                    <Database size={20} className="mx-auto mb-2 text-zinc-600" />
                    <p className="text-[11px] text-zinc-500">{t('memory.empty')}</p>
                  </div>
                ) : (
                  filteredMemories.map((item) => {
                    const isEditing = editingId === item.id;
                    const catObj = categories.find((c) => c.id === item.category);

                    if (isEditing) {
                      return (
                        <div
                          key={item.id}
                          className="rounded-xl border border-accent-500/40 bg-ink-850 p-2.5 space-y-2"
                        >
                          <input
                            type="text"
                            value={editContent}
                            onChange={(e) => setEditContent(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') handleSaveEdit(item.id);
                              if (e.key === 'Escape') setEditingId(null);
                            }}
                            className="w-full rounded bg-ink-950 px-2 py-1 text-[11.5px] text-zinc-100 outline-none ring-1 ring-accent-500/50"
                          />
                          <div className="flex items-center justify-between">
                            <div className="flex gap-1">
                              {categories.map((c) => (
                                <button
                                  key={c.id}
                                  type="button"
                                  onClick={() => setEditCat(c.id)}
                                  className={cn(
                                    'rounded px-1.5 py-0.2 font-mono text-[8.5px]',
                                    editCat === c.id
                                      ? 'bg-accent-500/20 text-accent-300'
                                      : 'text-zinc-600 hover:text-zinc-400',
                                  )}
                                >
                                  {c.label}
                                </button>
                              ))}
                            </div>
                            <div className="flex items-center gap-1.5">
                              <button
                                type="button"
                                onClick={() => setEditingId(null)}
                                className="rounded px-2 py-0.5 text-[10px] text-zinc-400 hover:text-zinc-200"
                              >
                                {t('msg.cancel')}
                              </button>
                              <button
                                type="button"
                                onClick={() => handleSaveEdit(item.id)}
                                className="rounded bg-accent-500 px-2 py-0.5 text-[10px] font-medium text-ink-950 hover:bg-accent-400"
                              >
                                <Check size={11} className="inline mr-0.5" />
                                {fr ? 'Valider' : 'Save'}
                              </button>
                            </div>
                          </div>
                        </div>
                      );
                    }

                    return (
                      <motion.div
                        key={item.id}
                        layout="position"
                        initial={{ opacity: 0, y: 4 }}
                        animate={{ opacity: 1, y: 0 }}
                        className={cn(
                          'group flex items-start gap-2.5 rounded-xl border p-2.5 transition-colors',
                          item.enabled
                            ? 'border-white/8 bg-white/[0.025] hover:border-white/15'
                            : 'border-white/4 bg-white/[0.005] opacity-50',
                        )}
                      >
                        {/* Toggle enabled / disabled switch */}
                        <button
                          type="button"
                          onClick={() => toggleMemory(item.id)}
                          title={item.enabled ? (fr ? 'Actif' : 'Active') : (fr ? 'Désactivé' : 'Disabled')}
                          className={cn(
                            'relative mt-0.5 h-[16px] w-[28px] shrink-0 rounded-full transition-colors',
                            item.enabled ? 'bg-accent-500' : 'bg-white/10',
                          )}
                        >
                          <span
                            className={cn(
                              'absolute top-[1.5px] h-[13px] w-[13px] rounded-full bg-white transition-all',
                              item.enabled ? 'left-[13.5px]' : 'left-[1.5px] opacity-60',
                            )}
                          />
                        </button>

                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-1.5 mb-0.5">
                            <span
                              className={cn(
                                'inline-block rounded border px-1.5 py-0.2 font-mono text-[8px] font-medium uppercase tracking-wider',
                                catObj?.color || 'text-zinc-400 bg-white/5 border-white/10',
                              )}
                            >
                              {catObj?.label || item.category}
                            </span>
                            <span className="font-mono text-[8px] text-zinc-600">
                              {new Date(item.updatedAt || item.createdAt).toLocaleDateString(
                                locale === 'fr' ? 'fr-FR' : 'en-US',
                                { month: 'short', day: 'numeric' },
                              )}
                            </span>
                          </div>
                          <p className="text-[11.5px] leading-relaxed text-zinc-200 break-words">
                            {item.content}
                          </p>
                        </div>

                        {/* Action buttons on hover */}
                        <div className="flex shrink-0 items-center gap-0.5 opacity-80 transition-opacity sm:opacity-0 sm:group-hover:opacity-100">
                          <button
                            type="button"
                            onClick={() => handleStartEdit(item)}
                            className="rounded p-1 text-zinc-500 transition hover:bg-white/10 hover:text-zinc-200"
                            title={t('sidebar.rename')}
                          >
                            <Pencil size={11} />
                          </button>
                          <button
                            type="button"
                            onClick={() => deleteMemory(item.id)}
                            className="rounded p-1 text-zinc-500 transition hover:bg-red-400/10 hover:text-red-300"
                            title={t('sidebar.delete')}
                          >
                            <Trash2 size={11} />
                          </button>
                        </div>
                      </motion.div>
                    );
                  })
                )}
              </div>
            </div>

            {/* Footer */}
            <div className="flex items-center justify-between border-t border-white/7 px-4 py-2.5 bg-ink-950/40">
              {confirmClear ? (
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-red-300">{t('memory.clearConfirm')}</span>
                  <button
                    type="button"
                    onClick={() => {
                      clearAllMemories();
                      setConfirmClear(false);
                    }}
                    className="rounded bg-red-400/20 px-2 py-0.5 text-[9.5px] font-medium text-red-300 hover:bg-red-400/30"
                  >
                    {t('sidebar.delete')}
                  </button>
                  <button
                    type="button"
                    onClick={() => setConfirmClear(false)}
                    className="text-[9.5px] text-zinc-400 hover:text-zinc-200"
                  >
                    {t('msg.cancel')}
                  </button>
                </div>
              ) : (
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={resetToDefaults}
                    className="inline-flex items-center gap-1 text-[10px] text-zinc-500 transition hover:text-zinc-300"
                  >
                    <RotateCcw size={10} />
                    {t('memory.resetDefaults')}
                  </button>
                  {memories.length > 0 && (
                    <button
                      type="button"
                      onClick={() => setConfirmClear(true)}
                      className="inline-flex items-center gap-1 text-[10px] text-zinc-600 transition hover:text-red-400"
                    >
                      <Trash2 size={10} />
                      {t('memory.clearAll')}
                    </button>
                  )}
                </div>
              )}

              <button
                type="button"
                onClick={() => setModalOpen(false)}
                className="rounded-lg bg-white/5 px-3 py-1 text-[11px] font-medium text-zinc-300 transition hover:bg-white/10"
              >
                {fr ? 'Fermer' : 'Done'}
              </button>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
