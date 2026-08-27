import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  Check,
  Download,
  FileCode2,
  FileDown,
  FileText,
  FileUp,
  FolderArchive,
  Loader2,
  Share2,
  Upload,
  X,
} from 'lucide-react';
import { useChat } from '../../lib/store/chatStore';
import { useExport } from '../../lib/store/exportStore';
import { useI18n } from '../../lib/i18n';
import {
  downloadAllBackup,
  downloadConversationJson,
  downloadConversationMarkdown,
  downloadConversationText,
  parseAndValidateBackup,
  shareConversation,
} from '../../lib/export';
import { cn } from '../../utils/cn';

interface ExportModalProps {
  isOpen?: boolean;
  onClose?: () => void;
}

export function ExportModal({ isOpen: controlledOpen, onClose: controlledClose }: ExportModalProps = {}) {
  const { conversations, activeId, importConversations } = useChat();
  const { isOpen: storeOpen, closeExport } = useExport();
  const { t } = useI18n();

  const isOpen = controlledOpen !== undefined ? controlledOpen : storeOpen;
  const handleClose = controlledClose || closeExport;

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);
  const [isImporting, setIsImporting] = useState(false);

  const currentConv = conversations.find((c) => c.id === activeId) ?? null;
  const hasCurrent = Boolean(currentConv && currentConv.messages.length > 0);

  // Close on ESC
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') handleClose();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, handleClose]);

  // Reset feedback on open
  useEffect(() => {
    if (isOpen) setFeedback(null);
  }, [isOpen]);

  const showNotification = (message: string, type: 'success' | 'error' = 'success') => {
    setFeedback({ type, message });
    setTimeout(() => setFeedback(null), 3500);
  };

  const handleShare = async () => {
    if (!currentConv) return;
    const res = await shareConversation(currentConv);
    if (res.shared) {
      showNotification(res.method === 'native' ? t('export.sharedNative') : t('export.copiedClipboard'));
    }
  };

  const handleImportFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setIsImporting(true);

    try {
      const text = await file.text();
      const result = parseAndValidateBackup(text);

      if (result.valid && result.conversations) {
        const count = importConversations(result.conversations, 'merge');
        showNotification(t('export.importSuccess', { n: count }), 'success');
      } else {
        showNotification(t('export.importError', { error: result.error || 'Format invalide' }), 'error');
      }
    } catch (err) {
      showNotification(t('export.importError', { error: (err as Error).message }), 'error');
    } finally {
      setIsImporting(false);
      e.target.value = '';
    }
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[65] bg-black/75 backdrop-blur-sm"
            onClick={handleClose}
          />

          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby="export-modal-title"
            initial={{ opacity: 0, scale: 0.96, y: 16 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: 12 }}
            transition={{ type: 'spring', stiffness: 380, damping: 32 }}
            className="fixed inset-x-3 top-[4vh] z-[66] mx-auto flex max-h-[92vh] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-white/10 bg-ink-900 shadow-[0_40px_120px_-20px_rgba(0,0,0,0.9)] sm:top-[7vh]"
          >
            {/* Header */}
            <div className="flex items-center gap-2.5 border-b border-white/7 px-4 py-3">
              <span className="grid h-7 w-7 place-items-center rounded-lg border border-accent-500/30 bg-accent-500/10 text-accent-300">
                <Share2 size={13} />
              </span>
              <div className="flex-1 min-w-0">
                <h2 id="export-modal-title" className="text-[13.5px] font-medium text-zinc-100 truncate">
                  {t('export.title')}
                </h2>
                <div className="font-mono text-[9px] text-zinc-400 truncate">
                  {t('export.subtitle')}
                </div>
              </div>
              <button
                type="button"
                onClick={handleClose}
                aria-label="Close"
                className="rounded-md p-1.5 text-zinc-500 transition hover:bg-white/5 hover:text-zinc-200"
              >
                <X size={15} />
              </button>
            </div>

            {/* Notification Banner */}
            <AnimatePresence>
              {feedback && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  className={cn(
                    'border-b px-4 py-2 text-[11px] font-medium flex items-center gap-2',
                    feedback.type === 'success'
                      ? 'border-emerald-500/20 bg-emerald-500/10 text-emerald-300'
                      : 'border-red-500/20 bg-red-500/10 text-red-300',
                  )}
                >
                  {feedback.type === 'success' ? <Check size={12} /> : <X size={12} />}
                  <span>{feedback.message}</span>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Body */}
            <div className="flex-1 space-y-4 overflow-y-auto p-4 scroll-slim">
              {/* Section 1: Active Conversation */}
              <section className="space-y-1.5">
                <div className="flex items-center justify-between px-1">
                  <span className="font-mono text-[9px] uppercase tracking-[0.18em] text-zinc-500">
                    {t('export.currentSection')}
                  </span>
                  {hasCurrent && (
                    <span className="truncate max-w-[200px] font-mono text-[9px] text-accent-400">
                      {currentConv?.title}
                    </span>
                  )}
                </div>

                {hasCurrent ? (
                  <div className="grid grid-cols-1 gap-1.5">
                    {/* Share / Copy Action */}
                    <button
                      type="button"
                      onClick={handleShare}
                      className="flex items-center gap-3 rounded-xl border border-accent-500/30 bg-accent-500/[0.06] p-2.5 text-left transition hover:border-accent-500/50 hover:bg-accent-500/10 active:scale-[0.99]"
                    >
                      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-accent-500/30 bg-accent-500/15 text-accent-300">
                        <Share2 size={14} />
                      </span>
                      <div className="flex-1 min-w-0">
                        <div className="text-[12px] font-medium text-zinc-100">{t('export.shareBtn')}</div>
                        <div className="truncate text-[10px] text-zinc-400">{t('export.shareDesc')}</div>
                      </div>
                    </button>

                    {/* Download Markdown */}
                    <button
                      type="button"
                      onClick={() => currentConv && downloadConversationMarkdown(currentConv)}
                      className="flex items-center gap-3 rounded-xl border border-white/8 bg-white/[0.02] p-2.5 text-left transition hover:border-white/15 hover:bg-white/[0.05] active:scale-[0.99]"
                    >
                      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-white/8 bg-white/4 text-indigo-300">
                        <FileText size={14} />
                      </span>
                      <div className="flex-1 min-w-0">
                        <div className="text-[12px] font-medium text-zinc-200">{t('export.markdown')}</div>
                        <div className="truncate text-[10px] text-zinc-500">{t('export.markdownDesc')}</div>
                      </div>
                      <Download size={13} className="shrink-0 text-zinc-500" />
                    </button>

                    {/* Download Plain Text */}
                    <button
                      type="button"
                      onClick={() => currentConv && downloadConversationText(currentConv)}
                      className="flex items-center gap-3 rounded-xl border border-white/8 bg-white/[0.02] p-2.5 text-left transition hover:border-white/15 hover:bg-white/[0.05] active:scale-[0.99]"
                    >
                      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-white/8 bg-white/4 text-sky-300">
                        <FileDown size={14} />
                      </span>
                      <div className="flex-1 min-w-0">
                        <div className="text-[12px] font-medium text-zinc-200">{t('export.plainText')}</div>
                        <div className="truncate text-[10px] text-zinc-500">{t('export.plainTextDesc')}</div>
                      </div>
                      <Download size={13} className="shrink-0 text-zinc-500" />
                    </button>

                    {/* Download Single JSON */}
                    <button
                      type="button"
                      onClick={() => currentConv && downloadConversationJson(currentConv)}
                      className="flex items-center gap-3 rounded-xl border border-white/8 bg-white/[0.02] p-2.5 text-left transition hover:border-white/15 hover:bg-white/[0.05] active:scale-[0.99]"
                    >
                      <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-white/8 bg-white/4 text-amber-300">
                        <FileCode2 size={14} />
                      </span>
                      <div className="flex-1 min-w-0">
                        <div className="text-[12px] font-medium text-zinc-200">{t('export.singleJson')}</div>
                        <div className="truncate text-[10px] text-zinc-500">{t('export.singleJsonDesc')}</div>
                      </div>
                      <Download size={13} className="shrink-0 text-zinc-500" />
                    </button>
                  </div>
                ) : (
                  <p className="rounded-xl border border-white/6 bg-white/[0.01] p-3 text-[11px] text-zinc-500">
                    {t('sidebar.empty')}
                  </p>
                )}
              </section>

              {/* Section 2: Full Workspace Backup & Restore */}
              <section className="space-y-1.5 pt-2 border-t border-white/6">
                <div className="px-1 font-mono text-[9px] uppercase tracking-[0.18em] text-zinc-500">
                  {t('export.backupSection')}
                </div>

                <div className="grid grid-cols-1 gap-1.5">
                  {/* Export All Backup */}
                  <button
                    type="button"
                    onClick={() => downloadAllBackup(conversations)}
                    disabled={conversations.length === 0}
                    className="flex items-center gap-3 rounded-xl border border-white/8 bg-white/[0.02] p-2.5 text-left transition hover:border-white/15 hover:bg-white/[0.05] disabled:opacity-40 active:scale-[0.99]"
                  >
                    <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-emerald-500/30 bg-emerald-500/10 text-emerald-400">
                      <FolderArchive size={14} />
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="text-[12px] font-medium text-zinc-200">{t('export.downloadAll')}</div>
                      <div className="truncate text-[10px] text-zinc-500">
                        {t('export.downloadAllDesc', { n: conversations.length })}
                      </div>
                    </div>
                    <Download size={13} className="shrink-0 text-zinc-500" />
                  </button>

                  {/* Restore Backup File */}
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".json,application/json"
                    className="hidden"
                    onChange={handleImportFile}
                  />
                  <button
                    type="button"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={isImporting}
                    className="flex items-center gap-3 rounded-xl border border-white/8 bg-white/[0.02] p-2.5 text-left transition hover:border-white/15 hover:bg-white/[0.05] disabled:opacity-40 active:scale-[0.99]"
                  >
                    <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg border border-sky-500/30 bg-sky-500/10 text-sky-400">
                      {isImporting ? <Loader2 size={14} className="animate-spin" /> : <FileUp size={14} />}
                    </span>
                    <div className="flex-1 min-w-0">
                      <div className="text-[12px] font-medium text-zinc-200">{t('export.importBtn')}</div>
                      <div className="truncate text-[10px] text-zinc-500">{t('export.importDesc')}</div>
                    </div>
                    <Upload size={13} className="shrink-0 text-zinc-500" />
                  </button>
                </div>
              </section>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
