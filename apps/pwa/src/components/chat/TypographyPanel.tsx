import { useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { AlignJustify, ChevronRight, RotateCcw, Type } from 'lucide-react';
import {
  FontFamily, TextSize, TextWeight, useTypography,
} from '../../lib/typography';
import { useI18n } from '../../lib/i18n';
import { cn } from '../../utils/cn';

function Choice<T extends string>({
  value,
  active,
  label,
  className,
  onPick,
}: {
  value: T;
  active: boolean;
  label: string;
  className?: string;
  onPick(value: T): void;
}) {
  return (
    <button
      type="button"
      onClick={() => onPick(value)}
      className={cn(
        'min-w-0 flex-1 rounded-md border px-1.5 py-1.5 text-[10px] transition active:scale-95',
        active
          ? 'border-accent-500/35 bg-accent-500/12 text-accent-300'
          : 'border-white/7 bg-white/[0.02] text-zinc-500 hover:text-zinc-300',
        className,
      )}
    >
      {label}
    </button>
  );
}

export function TypographyPanel() {
  const [open, setOpen] = useState(false);
  const { t } = useI18n();
  const {
    family, size, weight, relaxed,
    setFamily, setSize, setWeight, setRelaxed, reset,
  } = useTypography();

  return (
    <div className="rounded-lg border border-white/8 bg-white/[0.02]">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-2.5 py-2 text-left transition hover:bg-white/[0.03]"
      >
        <motion.span animate={{ rotate: open ? 90 : 0 }} transition={{ duration: 0.16 }}>
          <ChevronRight size={11} className="text-zinc-600" />
        </motion.span>
        <Type size={11} className="text-accent-300" />
        <span className="flex-1 font-mono text-[9px] uppercase tracking-[0.14em] text-zinc-500">
          {t('type.title')}
        </span>
        <span className="font-serif text-[12px] text-zinc-500">Aa</span>
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.22, ease: [0.22, 0.9, 0.3, 1] }}
            className="overflow-hidden"
          >
            <div className="space-y-2.5 border-t border-white/5 p-2.5">
              <div>
                <div className="mb-1 font-mono text-[8.5px] uppercase tracking-wider text-zinc-600">{t('type.font')}</div>
                <div className="flex gap-1">
                  <Choice<FontFamily> value="sans" active={family === 'sans'} label={t('type.sans')} onPick={setFamily} className="font-sans" />
                  <Choice<FontFamily> value="serif" active={family === 'serif'} label={t('type.serif')} onPick={setFamily} className="font-serif text-[12px]" />
                  <Choice<FontFamily> value="mono" active={family === 'mono'} label={t('type.mono')} onPick={setFamily} className="font-mono text-[9px]" />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <div className="mb-1 font-mono text-[8.5px] uppercase tracking-wider text-zinc-600">{t('type.size')}</div>
                  <div className="flex gap-1">
                    <Choice<TextSize> value="compact" active={size === 'compact'} label="S" onPick={setSize} />
                    <Choice<TextSize> value="comfortable" active={size === 'comfortable'} label="M" onPick={setSize} />
                    <Choice<TextSize> value="large" active={size === 'large'} label="L" onPick={setSize} />
                  </div>
                </div>
                <div>
                  <div className="mb-1 font-mono text-[8.5px] uppercase tracking-wider text-zinc-600">{t('type.weight')}</div>
                  <div className="flex gap-1">
                    <Choice<TextWeight> value="regular" active={weight === 'regular'} label="400" onPick={setWeight} />
                    <Choice<TextWeight> value="medium" active={weight === 'medium'} label="500" onPick={setWeight} />
                    <Choice<TextWeight> value="bold" active={weight === 'bold'} label="600" onPick={setWeight} />
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => setRelaxed(!relaxed)}
                  className={cn(
                    'flex flex-1 items-center justify-center gap-1.5 rounded-md border px-2 py-1.5 text-[9.5px] transition',
                    relaxed ? 'border-accent-500/30 bg-accent-500/10 text-accent-300' : 'border-white/7 text-zinc-500',
                  )}
                >
                  <AlignJustify size={10} />
                  {t('type.leading')}
                </button>
                <button
                  type="button"
                  onClick={reset}
                  title={t('type.reset')}
                  className="grid h-7 w-7 place-items-center rounded-md border border-white/7 text-zinc-600 transition hover:text-zinc-300 active:scale-95"
                >
                  <RotateCcw size={10} />
                </button>
              </div>

              <div className="reading-text rounded-md border border-white/6 bg-ink-950/60 px-2.5 py-2 text-zinc-400">
                {t('type.preview')} <strong className="text-zinc-100">{t('type.previewBold')}</strong>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}