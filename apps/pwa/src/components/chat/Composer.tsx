import { useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  AlertCircle, ArrowUp, FileText, Headphones, Image as ImageIcon,
  Loader2, Mic, Paperclip, Radio, Square, Type, Video, X,
} from 'lucide-react';
import { useI18n } from '../../lib/i18n';
import { useChat } from '../../lib/store/chatStore';
import { AttachmentKind } from '../../lib/attachments';
import { fmtBytes, fmtTime } from '../../lib/agent/video';
import { useDictation, useSpeech } from '../../lib/speech';
import { triggerHaptic } from '../../lib/theme';
import { applyTextFormat, FormatAction, TextFormattingBar } from './TextFormattingBar';
import { cn } from '../../utils/cn';

function AttachmentGlyph({ kind }: { kind: AttachmentKind }) {
  if (kind === 'image') return <ImageIcon size={13} />;
  if (kind === 'audio') return <Headphones size={13} />;
  if (kind === 'video') return <Video size={13} />;
  return <FileText size={13} />;
}

export function Composer({
  running,
  onSend,
  onStop,
}: {
  running: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
}) {
  const [value, setValue] = useState('');
  const [formattingOpen, setFormattingOpen] = useState(false);
  const [dictationNotice, setDictationNotice] = useState<string | null>(null);
  const ref = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const { t, locale } = useI18n();
  const {
    pendingAttachments, attachmentError, addPendingFiles, removePendingAttachment,
    revealActif, sauterReveal,
  } = useChat();
  const {
    isListening, isSupported: micSupported, isTranscribing, interimTranscript, startDictation, stopDictation,
  } = useDictation();
  const { stop: stopSpeech } = useSpeech();

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = '0px';
    el.style.height = Math.min(el.scrollHeight, 180) + 'px';
  }, [value, interimTranscript]);

  const attachmentsReady = pendingAttachments.every((item) => item.status === 'ready');
  const canSend = (!!value.trim() || !!interimTranscript.trim() || pendingAttachments.length > 0) && attachmentsReady;

  const toggleDictation = () => {
    if (!micSupported) {
      setDictationNotice(t('composer.micUnsupported'));
      setTimeout(() => setDictationNotice(null), 5000);
      return;
    }

    if (isListening) {
      triggerHaptic('light');
      stopDictation();
      return;
    }

    triggerHaptic('medium');
    // Silence any active readback when user starts speaking
    stopSpeech();
    setDictationNotice(null);

    startDictation(
      locale,
      (finalChunk) => {
        if (finalChunk.trim()) {
          setValue((prev) => {
            const separator = prev.trim().length > 0 && !prev.endsWith(' ') && !prev.endsWith('\n') ? ' ' : '';
            return prev + separator + finalChunk.trim();
          });
        }
      },
      (errCode) => {
        if (errCode === 'not-allowed' || errCode === 'permission-denied') {
          setDictationNotice(t('composer.micDenied'));
        } else if (errCode === 'transcription-failed') {
          setDictationNotice(t('composer.micTranscriptionFailed'));
        } else if (errCode !== 'no-speech') {
          setDictationNotice(t('composer.micUnsupported'));
        }
        setTimeout(() => setDictationNotice(null), 5000);
      },
    );
  };

  const submit = () => {
    if (running || !canSend) return;
    triggerHaptic('light');
    if (isListening) stopDictation();
    const finalContent = (value + (interimTranscript ? ` ${interimTranscript}` : '')).trim();
    onSend(finalContent);
    setValue('');
  };

  const format = (action: FormatAction) => {
    const el = ref.current;
    if (!el) return;
    triggerHaptic('light');
    const result = applyTextFormat(action, el, value);
    setValue(result.value);
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(result.start, result.end);
    });
  };

  return (
    <div className="relative">
      <div
        className={cn(
          'rounded-2xl border bg-ink-850/90 shadow-[0_8px_40px_-12px_rgba(0,0,0,0.7)] backdrop-blur transition-colors',
          isListening ? 'border-accent-500/60 shadow-[0_0_30px_-8px_var(--glow)]' : running ? 'border-accent-500/30' : 'border-white/10 focus-within:border-white/20',
        )}
      >
        {/* attached media */}
        <AnimatePresence initial={false}>
          {pendingAttachments.length > 0 && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.2 }}
              className="overflow-hidden"
            >
              <div className="flex gap-2 overflow-x-auto border-b border-white/6 p-2.5 scroll-slim">
                {pendingAttachments.map((item) => (
                  <div
                    key={item.id}
                    className={cn(
                      'relative flex min-w-[180px] max-w-[230px] shrink-0 items-center gap-2 rounded-xl border px-2.5 py-2',
                      item.status === 'failed'
                        ? 'border-red-400/25 bg-red-400/[0.05]'
                        : 'border-white/8 bg-white/[0.025]',
                    )}
                  >
                    {item.preview ? (
                      <img src={item.preview} alt="" className="h-9 w-9 shrink-0 rounded-lg object-cover" />
                    ) : (
                      <span className={cn(
                        'grid h-9 w-9 shrink-0 place-items-center rounded-lg border',
                        item.status === 'failed'
                          ? 'border-red-400/20 bg-red-400/10 text-red-300'
                          : 'border-accent-500/25 bg-accent-500/10 text-accent-300',
                      )}>
                        {item.status === 'processing' ? <Loader2 size={13} className="animate-spin" /> : <AttachmentGlyph kind={item.kind} />}
                      </span>
                    )}
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-[10.5px] font-medium text-zinc-200">{item.name}</div>
                      <div className={cn('truncate font-mono text-[8.5px]', item.status === 'failed' ? 'text-red-300/80' : 'text-zinc-600')}>
                        {item.status === 'processing'
                          ? t('composer.inspecting')
                          : item.status === 'failed'
                            ? item.error
                            : `${fmtBytes(item.size)}${item.metadata?.duration ? ` · ${fmtTime(Number(item.metadata.duration))}` : ''}`}
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => removePendingAttachment(item.id)}
                      className="grid h-6 w-6 shrink-0 place-items-center rounded-md text-zinc-600 transition hover:bg-white/6 hover:text-zinc-200"
                      aria-label={t('composer.removeAttachment')}
                    >
                      <X size={11} />
                    </button>
                  </div>
                ))}
              </div>
              {attachmentError && (
                <div className="flex items-center gap-1.5 border-b border-red-400/10 bg-red-400/[0.04] px-3 py-1.5 text-[9.5px] text-red-300/85">
                  <AlertCircle size={10} /> {attachmentError}
                </div>
              )}
            </motion.div>
          )}
        </AnimatePresence>

        {/* Live dictation active banner */}
        <AnimatePresence initial={false}>
          {isListening && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.18 }}
              className="overflow-hidden"
            >
              <div className="flex items-center justify-between border-b border-accent-500/20 bg-accent-500/[0.08] px-3.5 py-1.5">
                <div className="flex items-center gap-2">
                  <span className="relative flex h-2 w-2">
                    <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent-400 opacity-75" />
                    <span className="relative inline-flex h-2 w-2 rounded-full bg-accent-500" />
                  </span>
                  <span className="font-mono text-[10px] font-medium text-accent-300">
                    {t('composer.micActive')}
                  </span>
                  {/* Live animated waveform visualizer */}
                  <div className="flex items-center gap-0.5 pl-1">
                    {[40, 80, 50, 100, 60, 90, 45].map((h, i) => (
                      <span
                        key={i}
                        className="w-[2px] rounded-full bg-accent-400/80"
                        style={{
                          height: `${Math.max(4, h * 0.14)}px`,
                          animation: `soundwave 0.8s ease-in-out infinite alternate ${i * 0.12}s`,
                        }}
                      />
                    ))}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={stopDictation}
                  className="inline-flex items-center gap-1 rounded border border-accent-500/30 bg-accent-500/20 px-1.5 py-0.5 text-[9.5px] font-medium text-accent-200 transition hover:bg-accent-500/30"
                >
                  <Square size={8} fill="currentColor" /> {t('composer.micStop')}
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Transcription en cours — entre l'arret de l'enregistrement et le
            texte final du serveur (Whisper) ; pas d'"interim" possible ici. */}
        <AnimatePresence initial={false}>
          {isTranscribing && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.18 }}
              className="overflow-hidden"
            >
              <div className="flex items-center gap-2 border-b border-accent-500/20 bg-accent-500/[0.08] px-3.5 py-1.5">
                <Loader2 size={11} className="animate-spin text-accent-400" />
                <span className="font-mono text-[10px] font-medium text-accent-300">
                  {t('composer.micTranscribing')}
                </span>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Notice for mic permission / unsupported browser */}
        <AnimatePresence initial={false}>
          {dictationNotice && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.18 }}
              className="overflow-hidden"
            >
              <div className="flex items-center gap-2 border-b border-amber-400/20 bg-amber-400/[0.08] px-3.5 py-2 text-[10.5px] text-amber-200">
                <AlertCircle size={12} className="shrink-0 text-amber-400" />
                <span className="flex-1">{dictationNotice}</span>
                <button
                  type="button"
                  onClick={() => setDictationNotice(null)}
                  className="rounded p-0.5 text-amber-400 hover:bg-amber-400/20"
                >
                  <X size={12} />
                </button>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Formatting bar */}
        <AnimatePresence initial={false}>
          {formattingOpen && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: 'auto', opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.18 }}
              className="overflow-hidden"
            >
              <TextFormattingBar textarea={ref} value={value} setValue={setValue} />
            </motion.div>
          )}
        </AnimatePresence>

        <div className="flex items-end gap-1 p-2 pl-2.5 sm:gap-2 sm:pl-3">
          <input
            ref={fileRef}
            type="file"
            multiple
            accept="image/*,audio/*,video/*,application/pdf,.docx,.txt,.md,.csv,.json,.xml,.html,.yaml,.yml,.log,.js,.jsx,.ts,.tsx,.py,.css,.sql"
            className="hidden"
            onChange={(event) => {
              void addPendingFiles(Array.from(event.target.files ?? []));
              event.target.value = '';
            }}
          />
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            disabled={running}
            title={t('composer.attach')}
            className="grid h-9 w-9 shrink-0 place-items-center rounded-xl text-zinc-500 transition hover:bg-white/5 hover:text-accent-300 disabled:opacity-40 active:scale-95"
          >
            <Paperclip size={16} />
          </button>
          <button
            type="button"
            onClick={() => setFormattingOpen((open) => !open)}
            title={t('type.title')}
            className={cn(
              'grid h-9 w-9 shrink-0 place-items-center rounded-xl transition active:scale-95',
              formattingOpen ? 'bg-accent-500/12 text-accent-300' : 'text-zinc-500 hover:bg-white/5 hover:text-zinc-200',
            )}
          >
            <Type size={15} />
          </button>
          {/* Microphone Dictation Button */}
          <button
            type="button"
            onClick={toggleDictation}
            disabled={running || isTranscribing}
            title={isListening ? t('composer.micStop') : t('composer.mic')}
            className={cn(
              'relative grid h-9 w-9 shrink-0 place-items-center rounded-xl transition active:scale-95 disabled:opacity-40',
              isListening
                ? 'bg-accent-500 text-ink-950 shadow-[0_0_15px_var(--glow)]'
                : 'text-zinc-500 hover:bg-white/5 hover:text-accent-300',
            )}
          >
            {isTranscribing ? (
              <Loader2 size={16} className="animate-spin" />
            ) : isListening ? (
              <Radio size={16} className="animate-pulse" />
            ) : (
              <Mic size={16} />
            )}
          </button>

          <div className="relative min-w-0 flex-1">
            <textarea
              ref={ref}
              value={value}
              rows={1}
              onChange={(event) => setValue(event.target.value)}
              onKeyDown={(event) => {
                if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'b') {
                  event.preventDefault(); format('bold'); return;
                }
                if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'i') {
                  event.preventDefault(); format('italic'); return;
                }
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault(); submit();
                }
              }}
              placeholder={running ? t('composer.running') : isListening ? t('composer.micActive') : t('composer.placeholder')}
              className="writing-text max-h-[180px] w-full resize-none bg-transparent py-2 text-[16px] leading-relaxed text-zinc-100 outline-none placeholder:text-zinc-600 scroll-slim md:text-[13.5px]"
            />
            {/* Interim live speech transcript preview indicator */}
            {isListening && interimTranscript && (
              <div className="pointer-events-none mt-[-4px] pb-1.5 font-mono text-[11px] italic text-accent-300/80">
                {interimTranscript}
              </div>
            )}
          </div>

          {running || revealActif ? (
            <button
              onClick={() => {
                // Le reseau peut deja avoir tout envoye (agent specialise) :
                // l'y a rien a annuler, juste finir d'afficher ce qui est
                // arrive. `onStop` sur un flux deja termine ne fait rien de
                // plus qu'un `abort()` sans effet — les deux sont surs a
                // appeler ensemble, dans tous les cas.
                onStop();
                sauterReveal();
              }}
              title={t('composer.stop')}
              className="grid h-9 w-9 shrink-0 place-items-center rounded-xl border border-accent-500/40 bg-accent-500/15 text-accent-300 transition hover:bg-accent-500/25 active:scale-95"
            >
              <Square size={13} fill="currentColor" />
            </button>
          ) : (
            <button
              onClick={submit}
              disabled={!canSend}
              title={t('composer.send')}
              className={cn(
                'grid h-9 w-9 shrink-0 place-items-center rounded-xl transition active:scale-95',
                canSend ? 'bg-accent-500 text-ink-950 hover:bg-accent-400' : 'cursor-not-allowed bg-white/5 text-zinc-600',
              )}
            >
              <ArrowUp size={16} strokeWidth={2.4} />
            </button>
          )}
        </div>
      </div>
      <div className="mt-2 hidden items-center justify-center gap-3 text-[10px] text-zinc-600 sm:flex">
        <span><kbd className="rounded border border-white/10 bg-white/5 px-1 font-mono text-[9px]">Enter</kbd> {t('composer.enter')}</span>
        <span className="text-zinc-700">·</span>
        <span><kbd className="rounded border border-white/10 bg-white/5 px-1 font-mono text-[9px]">Shift+Enter</kbd> {t('composer.shiftEnter')}</span>
        <span className="text-zinc-700">·</span>
        <span>{t('composer.trust')}</span>
      </div>
    </div>
  );
}
