import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  FileText,
  Headphones,
  Image as ImageIcon,
  Paperclip,
  UploadCloud,
  Video,
} from 'lucide-react';
import { useChat } from '../../lib/store/chatStore';
import { useI18n } from '../../lib/i18n';

export function GlobalDropZone() {
  const [isDragging, setIsDragging] = useState(false);
  const { addPendingFiles } = useChat();
  const { t } = useI18n();

  useEffect(() => {
    let dragCounter = 0;

    const handleDragEnter = (e: DragEvent) => {
      e.preventDefault();
      // Check if dragging files
      if (e.dataTransfer && Array.from(e.dataTransfer.types).includes('Files')) {
        dragCounter++;
        setIsDragging(true);
      }
    };

    const handleDragOver = (e: DragEvent) => {
      e.preventDefault();
      if (e.dataTransfer) {
        e.dataTransfer.dropEffect = 'copy';
      }
    };

    const handleDragLeave = (e: DragEvent) => {
      e.preventDefault();
      dragCounter--;
      if (dragCounter <= 0) {
        dragCounter = 0;
        setIsDragging(false);
      }
    };

    const handleDrop = (e: DragEvent) => {
      e.preventDefault();
      dragCounter = 0;
      setIsDragging(false);

      if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        const files = Array.from(e.dataTransfer.files);
        void addPendingFiles(files);
      }
    };

    window.addEventListener('dragenter', handleDragEnter);
    window.addEventListener('dragover', handleDragOver);
    window.addEventListener('dragleave', handleDragLeave);
    window.addEventListener('drop', handleDrop);

    return () => {
      window.removeEventListener('dragenter', handleDragEnter);
      window.removeEventListener('dragover', handleDragOver);
      window.removeEventListener('dragleave', handleDragLeave);
      window.removeEventListener('drop', handleDrop);
    };
  }, [addPendingFiles]);

  return (
    <AnimatePresence>
      {isDragging && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
          className="fixed inset-0 z-[100] pointer-events-none flex items-center justify-center bg-black/80 backdrop-blur-md p-6"
        >
          <motion.div
            initial={{ scale: 0.94, y: 12 }}
            animate={{ scale: 1, y: 0 }}
            exit={{ scale: 0.95, y: 8 }}
            transition={{ type: 'spring', stiffness: 420, damping: 30 }}
            className="flex flex-col items-center justify-center max-w-lg w-full rounded-3xl border-2 border-dashed border-accent-500/70 bg-ink-900/90 p-8 sm:p-10 text-center shadow-[0_0_60px_-15px_var(--glow)]"
          >
            {/* Animated Pulse Icon */}
            <div className="relative mb-5 grid h-16 w-16 place-items-center rounded-2xl border border-accent-500/40 bg-accent-500/15 text-accent-300 shadow-[0_0_30px_-5px_var(--glow)]">
              <UploadCloud size={32} className="animate-bounce" />
            </div>

            <h2 className="text-[17px] sm:text-[19px] font-medium text-zinc-100 mb-2">
              {t('drop.title')}
            </h2>

            <p className="text-[12px] sm:text-[13px] text-zinc-400 max-w-sm mb-6 leading-relaxed">
              {t('drop.subtitle')}
            </p>

            {/* Formats Icons Strip */}
            <div className="flex flex-wrap items-center justify-center gap-2 font-mono text-[10px] text-zinc-400">
              <span className="inline-flex items-center gap-1 rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-emerald-300">
                <ImageIcon size={11} /> Images
              </span>
              <span className="inline-flex items-center gap-1 rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-sky-300">
                <FileText size={11} /> PDF & Docs
              </span>
              <span className="inline-flex items-center gap-1 rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-purple-300">
                <Headphones size={11} /> Audio
              </span>
              <span className="inline-flex items-center gap-1 rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-rose-300">
                <Video size={11} /> Vidéos
              </span>
              <span className="inline-flex items-center gap-1 rounded-lg border border-white/10 bg-white/5 px-2 py-1 text-amber-300">
                <Paperclip size={11} /> Code
              </span>
            </div>

            <div className="mt-5 font-mono text-[10px] text-accent-400">
              {t('drop.hint')}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
