import { memo, useEffect, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import {
  Check, ChevronLeft, ChevronRight, Clapperboard, Copy, FileText, Headphones, Image as ImageIcon,
  Pause, Pencil, Play, RotateCw, ShieldCheck, Square, Volume2, X,
} from 'lucide-react';
import type { ChatMessage as Msg } from '../../lib/store/chatStore';
import type { AttachmentSummary } from '../../lib/attachments';
import { annulerAction, confirmerAction } from '../../lib/actions/confirmer';
import { formatDuration } from '../../lib/activity/types';
import { fmtBytes, fmtTime } from '../../lib/agent/video';
import { AIActivity } from '../activity/ActivityTimeline';
import { MarkdownLite, StreamingResponse } from '../activity/StreamingResponse';
import { DomainMark } from '../activity/StatusIcon';
import { useI18n } from '../../lib/i18n';
import { useSpeech, isSpeechSynthesisSupported } from '../../lib/speech';
import { useChat } from '../../lib/store/chatStore';
import { triggerHaptic } from '../../lib/theme';
import type { ItemCtx } from '../activity/ActivityItem';
import { cn } from '../../utils/cn';

/* Ce qui attend un accord, avec de quoi le donner.
 *
 * Avant le 02/09/2026, rien ici : le serveur preparait le document, affichait
 * un identifiant de 32 caracteres dans le texte, et aucun element de
 * l'interface n'appelait `/api/actions/{id}/confirm`. Le proprietaire ne
 * pouvait donc obtenir aucun PDF, quoi qu'il ecrive.
 *
 * Le bouton nomme ce qu'il valide : c'est ce qui le rend sur la ou une phrase
 * ne suffit pas (envoi d'un mail, publication, suppression). */
function ActionsEnAttente({ msg }: { msg: Msg }) {
  const { t } = useI18n();
  const [etat, setEtat] = useState<Record<string, string>>({});
  const [documents, setDocuments] = useState<Record<string, string>>({});
  const [enCours, setEnCours] = useState<string | null>(null);
  const attente = msg.meta?.en_attente ?? [];
  if (!attente.length) return null;

  const agir = async (id: string, quoi: 'confirmer' | 'annuler') => {
    setEnCours(id);
    triggerHaptic('medium');
    const r = quoi === 'confirmer' ? await confirmerAction(id) : await annulerAction(id);
    setEtat((e) => ({ ...e, [id]: r.message }));
    if (r.document) setDocuments((d) => ({ ...d, [id]: r.document! }));
    setEnCours(null);
    triggerHaptic(r.ok ? 'success' : 'warning');
  };

  return (
    <div className="space-y-2 pt-1">
      {attente.map((a) => (
        <div
          key={a.id}
          className="rounded-lg border border-accent-500/25 bg-accent-500/[0.06] px-3 py-2.5"
        >
          <div className="flex items-start gap-2">
            <ShieldCheck size={13} className="mt-0.5 shrink-0 text-accent-300" />
            <div className="min-w-0 flex-1">
              <div className="text-[12px] text-zinc-200">{a.action}</div>
              <div className="truncate text-[11px] text-zinc-500">{a.cible}</div>
            </div>
            <span className="shrink-0 rounded px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-zinc-500">
              {a.risque}
            </span>
          </div>

          {etat[a.id] ? (
            <div className="space-y-2 pt-2">
              <div className="text-[11.5px] text-zinc-300">{etat[a.id]}</div>
              {/* Le document produit s'ouvre depuis le telephone. Sans ce lien
                  le PDF existe sur le disque du serveur et nulle part
                  ailleurs — c'est exactement ce qui manquait avant le
                  02/09/2026. */}
              {documents[a.id] && (
                <a
                  href={documents[a.id]}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 rounded-md bg-white/[0.06] px-3 py-1.5 text-[11.5px] text-zinc-200 transition hover:bg-white/10"
                >
                  <FileText size={12} />
                  {t('action.openDocument')}
                </a>
              )}
            </div>
          ) : (
            <div className="flex gap-2 pt-2.5">
              <button
                type="button"
                onClick={() => agir(a.id, 'confirmer')}
                disabled={enCours === a.id}
                className="rounded-md bg-accent-500/90 px-3 py-1.5 text-[11.5px] font-medium text-ink-950 transition hover:bg-accent-400 disabled:opacity-50"
              >
                {t('action.confirm')}
              </button>
              <button
                type="button"
                onClick={() => agir(a.id, 'annuler')}
                disabled={enCours === a.id}
                className="rounded-md border border-white/10 px-3 py-1.5 text-[11.5px] text-zinc-400 transition hover:bg-white/5 hover:text-zinc-200 disabled:opacity-50"
              >
                {t('action.cancel')}
              </button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

function SourcesStrip({ msg }: { msg: Msg }) {
  const sources = msg.meta?.sources;
  const { t } = useI18n();
  if (!sources?.length) return null;
  return (
    <div className="mt-3 flex flex-wrap items-center gap-1.5">
      <span className="mr-1 font-mono text-[9.5px] uppercase tracking-widest text-zinc-600">{t('msg.sources')}</span>
      {sources.map((s, i) => (
        <span
          key={i}
          title={`${s.title}${s.date ? ` · ${s.date}` : ''}`}
          className="inline-flex items-center gap-1.5 rounded-full border border-white/8 bg-white/[0.03] py-1 pl-1.5 pr-2.5 text-[10.5px] text-zinc-400 transition hover:border-white/15 hover:text-zinc-200"
        >
          <DomainMark domain={s.domain} className="!h-[14px] !w-[14px] text-[8px]" />
          {s.domain}
        </span>
      ))}
    </div>
  );
}

function AttachmentGlyph({ kind }: { kind: AttachmentSummary['kind'] }) {
  if (kind === 'image') return <ImageIcon size={12} />;
  if (kind === 'audio') return <Headphones size={12} />;
  if (kind === 'video') return <Clapperboard size={12} />;
  return <FileText size={12} />;
}

function UserAttachments({ msg }: { msg: Msg }) {
  const legacy: AttachmentSummary[] = msg.meta?.video
    ? [{ id: 'legacy-video', name: msg.meta.video.name, size: msg.meta.video.size, type: msg.meta.video.type, kind: 'video' }]
    : [];
  const attachments = msg.meta?.attachments ?? legacy;
  if (!attachments.length) return null;
  return (
    <div className="flex max-w-[92%] flex-wrap justify-end gap-1.5 sm:max-w-[78%]">
      {attachments.map((item) => (
        <div
          key={item.id}
          className="flex min-w-0 items-center gap-2 rounded-xl border border-accent-500/20 bg-accent-500/[0.06] py-1.5 pl-1.5 pr-2.5"
        >
          {item.preview ? (
            <img src={item.preview} alt="" className="h-8 w-8 shrink-0 rounded-lg object-cover" />
          ) : (
            <span className="grid h-7 w-7 shrink-0 place-items-center rounded-lg bg-accent-500/10 text-accent-300">
              <AttachmentGlyph kind={item.kind} />
            </span>
          )}
          <span className="min-w-0">
            <span className="block max-w-[180px] truncate font-mono text-[9.5px] text-zinc-300">{item.name}</span>
            <span className="block font-mono text-[8px] text-zinc-600">
              {fmtBytes(item.size)}
              {item.metadata?.duration ? ` · ${fmtTime(Number(item.metadata.duration))}` : ''}
            </span>
          </span>
        </div>
      ))}
    </div>
  );
}

function VariantNavigator({
  currentIndex,
  total,
  onPrev,
  onNext,
}: {
  currentIndex: number;
  total: number;
  onPrev: () => void;
  onNext: () => void;
}) {
  const { t } = useI18n();
  if (total <= 1) return null;
  return (
    <div
      className="inline-flex items-center gap-1 rounded-md border border-white/8 bg-white/[0.03] px-1.5 py-0.5 font-mono text-[9.5px] text-zinc-400"
      title={t('msg.variants', { cur: currentIndex + 1, total })}
    >
      <button
        type="button"
        onClick={onPrev}
        disabled={currentIndex <= 0}
        className="rounded p-0.5 text-zinc-400 transition hover:bg-white/10 hover:text-zinc-100 disabled:opacity-30 disabled:hover:bg-transparent"
        aria-label="Previous variant"
      >
        <ChevronLeft size={10} />
      </button>
      <span className="px-0.5">
        {currentIndex + 1} / {total}
      </span>
      <button
        type="button"
        onClick={onNext}
        disabled={currentIndex >= total - 1}
        className="rounded p-0.5 text-zinc-400 transition hover:bg-white/10 hover:text-zinc-100 disabled:opacity-30 disabled:hover:bg-transparent"
        aria-label="Next variant"
      >
        <ChevronRight size={10} />
      </button>
    </div>
  );
}

export const ChatMessage = memo(function ChatMessage({
  msg,
  conversationId,
  onRetryCommand,
}: {
  msg: Msg;
  conversationId: string;
  onRetryCommand: (messageId: string, nodeId: string) => void;
}) {
  const [copied, setCopied] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [editText, setEditText] = useState(msg.text);
  const editAreaRef = useRef<HTMLTextAreaElement>(null);

  const { t, locale } = useI18n();
  const { isRunning, editUserMessage, regenerateAssistant, switchVariant } = useChat();
  const {
    speakingMessageId, isPaused, rate, speak, stop: stopSpeech, setRate,
  } = useSpeech();

  const isSpeakingThis = speakingMessageId === msg.id;
  const isAudioAvailable = isSpeechSynthesisSupported();

  const variants = msg.variants ?? [];
  const variantIndex = msg.variantIndex ?? (variants.length > 0 ? variants.length - 1 : 0);
  const hasVariants = variants.length > 1;

  // Auto-resize edit textarea
  useEffect(() => {
    if (isEditing && editAreaRef.current) {
      editAreaRef.current.style.height = '0px';
      editAreaRef.current.style.height = `${Math.min(editAreaRef.current.scrollHeight, 240)}px`;
    }
  }, [isEditing, editText]);

  const handleStartEdit = () => {
    if (isRunning) return;
    setEditText(msg.text);
    setIsEditing(true);
    setTimeout(() => {
      editAreaRef.current?.focus();
      editAreaRef.current?.setSelectionRange(msg.text.length, msg.text.length);
    }, 50);
  };

  const handleCancelEdit = () => {
    setIsEditing(false);
    setEditText(msg.text);
  };

  const handleSaveEdit = () => {
    if (!editText.trim() || isRunning) return;
    setIsEditing(false);
    void editUserMessage(msg.id, editText.trim());
  };

  // Meme geste que sur la reponse d'Usman (copy(), plus bas) — mais son propre
  // texte, jamais `bodyText` : celui-ci n'existe que pour une bulle assistant.
  const copyUserText = async () => {
    try {
      await navigator.clipboard.writeText(msg.text);
      triggerHaptic('success');
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch { /* noop */ }
  };

  if (msg.role === 'user') {
    return (
      <motion.div
        role="article"
        aria-label={t('a11y.userMessage')}
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.25 }}
        className="group/user flex flex-col items-end gap-1.5"
      >
        <UserAttachments msg={msg} />

        {isEditing ? (
          <div className="w-full max-w-[95%] sm:max-w-[85%] rounded-2xl border border-accent-500/40 bg-ink-850 p-3 shadow-xl backdrop-blur">
            <textarea
              ref={editAreaRef}
              value={editText}
              onChange={(e) => setEditText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Escape') {
                  e.preventDefault();
                  handleCancelEdit();
                } else if (e.key === 'Enter' && (e.ctrlKey || e.metaKey || !e.shiftKey)) {
                  e.preventDefault();
                  handleSaveEdit();
                }
              }}
              rows={2}
              className="writing-text w-full resize-none bg-transparent text-[13.5px] leading-relaxed text-zinc-100 outline-none placeholder:text-zinc-600 scroll-slim"
            />
            <div className="mt-2.5 flex items-center justify-end gap-2 border-t border-white/6 pt-2">
              <button
                type="button"
                onClick={handleCancelEdit}
                className="inline-flex items-center gap-1 rounded-lg border border-white/8 px-2.5 py-1 text-[11px] font-medium text-zinc-400 transition hover:bg-white/5 hover:text-zinc-200"
              >
                <X size={12} />
                {t('msg.cancel')}
              </button>
              <button
                type="button"
                onClick={handleSaveEdit}
                disabled={!editText.trim() || isRunning}
                className="inline-flex items-center gap-1.5 rounded-lg bg-accent-500 px-3 py-1 text-[11px] font-medium text-ink-950 transition hover:bg-accent-400 disabled:opacity-40"
              >
                <Check size={12} strokeWidth={2.5} />
                {t('msg.saveSubmit')}
              </button>
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-1.5 max-w-full">
            {/* User message controls on hover/mobile */}
            <div className="flex items-center gap-1 opacity-80 transition-opacity sm:opacity-0 sm:group-hover/user:opacity-100">
              {hasVariants && (
                <VariantNavigator
                  currentIndex={variantIndex}
                  total={variants.length}
                  onPrev={() => switchVariant(msg.id, variantIndex - 1)}
                  onNext={() => switchVariant(msg.id, variantIndex + 1)}
                />
              )}
              <button
                type="button"
                onClick={handleStartEdit}
                disabled={isRunning}
                title={t('msg.edit')}
                className="grid h-6 w-6 place-items-center rounded-md text-zinc-500 transition hover:bg-white/5 hover:text-zinc-200 disabled:opacity-40"
              >
                <Pencil size={11} />
              </button>
              <button
                type="button"
                onClick={copyUserText}
                title={copied ? t('msg.copied') : t('msg.copy')}
                className="grid h-6 w-6 place-items-center rounded-md text-zinc-500 transition hover:bg-white/5 hover:text-zinc-200"
              >
                {copied ? <Check size={11} className="text-emerald-400" /> : <Copy size={11} />}
              </button>
            </div>

            {msg.text && (
              <div className="user-rich max-w-[90%] rounded-2xl rounded-br-md border border-white/8 bg-ink-800 px-4 py-2.5 text-zinc-100 sm:max-w-[75%]">
                <MarkdownLite text={msg.text} />
              </div>
            )}
          </div>
        )}
      </motion.div>
    );
  }

  const ctx: ItemCtx = { conversationId, messageId: msg.id, onRetryCommand };
  const working = msg.status === 'working' || msg.status === 'streaming';
  const showActivity = msg.activity.length > 0 || working;
  const bodyText = msg.status === 'done' || msg.status === 'cancelled' ? (msg.text || msg.live) : msg.live;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(bodyText);
      triggerHaptic('success');
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch { /* noop */ }
  };

  const handleToggleSpeak = () => {
    if (!bodyText) return;
    triggerHaptic('light');
    speak(msg.id, bodyText, locale);
  };

  const cycleRate = () => {
    triggerHaptic('light');
    const nextRate = rate === 1.05 ? 1.25 : rate === 1.25 ? 1.5 : 1.05;
    setRate(nextRate);
  };

  const handleRegenerate = () => {
    if (isRunning) return;
    triggerHaptic('medium');
    void regenerateAssistant(msg.id);
  };

  return (
    <motion.div
      role="article"
      aria-label={t('a11y.assistantMessage')}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className={cn(
        'group/msg relative rounded-2xl transition-colors duration-300',
        isSpeakingThis && 'bg-accent-500/[0.02] p-2 sm:p-3 -m-2 sm:-m-3 border border-accent-500/20 shadow-[0_0_30px_-15px_var(--glow)]',
      )}
    >
      <div className="mb-1.5 flex items-center gap-2">
        <span className="grid h-5 w-5 place-items-center">
          <svg width="15" height="15" viewBox="0 0 32 32" className="text-accent-500">
            <circle cx="16" cy="16" r="12.5" fill="none" stroke="currentColor" strokeWidth="2.2" opacity={working ? 1 : 0.45} />
            <circle cx="16" cy="16" r="4.5" fill="currentColor" opacity={working ? 1 : 0.6}>
              {working && <animate attributeName="r" values="4.5;6;4.5" dur="1.6s" repeatCount="indefinite" />}
            </circle>
          </svg>
        </span>
        <span className="text-[11px] font-medium tracking-wide text-zinc-500">Usman</span>
        {msg.meta?.durationMs !== undefined && msg.status === 'done' && (
          <span className="font-mono text-[9.5px] text-zinc-700">{formatDuration(msg.meta.durationMs)}</span>
        )}

        {/* Live speech indicator on message header */}
        {isSpeakingThis && (
          <span className="inline-flex items-center gap-1 rounded-full bg-accent-500/15 px-2 py-0.5 font-mono text-[9px] text-accent-300">
            <span className="flex items-center gap-0.5">
              {[40, 90, 60].map((h, i) => (
                <span
                  key={i}
                  className="w-[1.5px] rounded-full bg-accent-400"
                  style={{
                    height: isPaused ? '4px' : `${h * 0.1}px`,
                    animation: isPaused ? 'none' : `soundwave 0.7s ease-in-out infinite alternate ${i * 0.15}s`,
                  }}
                />
              ))}
            </span>
            {isPaused ? t('msg.pauseAudio') : t('msg.speaking')}
          </span>
        )}

        {/* Variants Navigator for Assistant */}
        {hasVariants && !working && (
          <VariantNavigator
            currentIndex={variantIndex}
            total={variants.length}
            onPrev={() => switchVariant(msg.id, variantIndex - 1)}
            onNext={() => switchVariant(msg.id, variantIndex + 1)}
          />
        )}
      </div>

      <div className="space-y-3 pl-7">
        {/* activity first — the response arrives beneath it (continuous transition) */}
        {showActivity && (
          <AIActivity nodes={msg.activity} ctx={ctx} live={working} startedAt={msg.createdAt} />
        )}

        {(bodyText || msg.status === 'streaming') && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.4 }}
            role="region"
            aria-live={working ? 'polite' : 'off'}
            aria-busy={working}
          >
            <StreamingResponse
              text={bodyText}
              streaming={msg.status === 'streaming'}
              sources={msg.meta?.sources}
            />
          </motion.div>
        )}

        {msg.status === 'error' && (
          <div className="rounded-lg border border-red-400/20 bg-red-400/[0.06] px-3 py-2 text-[12px] text-red-200">
            {t('msg.error')} : {msg.error}
          </div>
        )}

        <SourcesStrip msg={msg} />

        <ActionsEnAttente msg={msg} />

        {msg.status === 'done' && bodyText && (
          <div className="flex flex-wrap items-center gap-1 pt-1 opacity-90 transition-opacity sm:opacity-0 sm:group-hover/msg:opacity-100">
            {/* Copy button */}
            <button
              onClick={copy}
              className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[10.5px] text-zinc-500 transition hover:bg-white/5 hover:text-zinc-300"
              title={copied ? t('msg.copied') : t('msg.copy')}
            >
              {copied ? <Check size={11} className="text-emerald-400" /> : <Copy size={11} />}
              {copied ? t('msg.copied') : t('msg.copy')}
            </button>

            {/* Regenerate button */}
            <button
              onClick={handleRegenerate}
              disabled={isRunning}
              className="inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[10.5px] text-zinc-500 transition hover:bg-white/5 hover:text-zinc-300 disabled:opacity-40"
              title={t('msg.regenerate')}
            >
              <RotateCw size={11} />
              <span>{t('msg.regenerate')}</span>
            </button>

            {/* Audio Speech Readback button */}
            {isAudioAvailable && (
              <>
                <button
                  onClick={handleToggleSpeak}
                  className={cn(
                    'inline-flex items-center gap-1.5 rounded-md px-2 py-1 text-[10.5px] transition',
                    isSpeakingThis
                      ? 'bg-accent-500/15 text-accent-300 hover:bg-accent-500/25'
                      : 'text-zinc-500 hover:bg-white/5 hover:text-zinc-300',
                  )}
                  title={isSpeakingThis ? (isPaused ? t('msg.resumeAudio') : t('msg.pauseAudio')) : t('msg.speak')}
                >
                  {isSpeakingThis ? (
                    isPaused ? <Play size={11} className="text-accent-300" /> : <Pause size={11} className="text-accent-300" />
                  ) : (
                    <Volume2 size={11} />
                  )}
                  <span>{isSpeakingThis ? (isPaused ? t('msg.resumeAudio') : t('msg.pauseAudio')) : t('msg.speak')}</span>
                </button>

                {/* Additional controls when active: Stop & Speed rate */}
                {isSpeakingThis && (
                  <>
                    <button
                      onClick={stopSpeech}
                      className="inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-[10.5px] text-zinc-500 transition hover:bg-red-400/10 hover:text-red-300"
                      title={t('msg.stopAudio')}
                    >
                      <Square size={10} fill="currentColor" />
                    </button>
                    <button
                      onClick={cycleRate}
                      className="inline-flex items-center rounded-md px-1.5 py-1 font-mono text-[9px] text-zinc-400 transition hover:bg-white/5 hover:text-zinc-200"
                      title={t('msg.speedAudio', { x: `${rate}x` })}
                    >
                      {rate === 1.05 ? '1.0x' : `${rate}x`}
                    </button>
                  </>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </motion.div>
  );
});
