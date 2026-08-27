import { motion } from 'framer-motion';
import { Search, Hammer, TerminalSquare, Braces } from 'lucide-react';
import { useI18n } from '../../lib/i18n';
import { TOOL_REGISTRY } from '../../lib/agent/tools';
import { Logo } from './Sidebar';

const BENCH_PROMPT = 'Run this code:\n```js\nconst t0 = performance.now()\nlet primes = 0\nfor (let n = 2; n < 20000; n++) {\n  let p = true\n  for (let d = 2; d * d <= n; d++) if (n % d === 0) { p = false; break }\n  if (p) primes++\n}\nconsole.log("primes < 20000:", primes)\nconsole.log("elapsed:", (performance.now() - t0).toFixed(1) + "ms")\n```';

export function EmptyState({ onPick }: { onPick: (prompt: string) => void }) {
  const { t, locale } = useI18n();

  const suggestions = [
    { icon: <Hammer size={15} />, title: t('empty.s1.title'), sub: t('empty.s1.sub'), prompt: t('empty.s1.prompt') },
    { icon: <Search size={15} />, title: t('empty.s2.title'), sub: t('empty.s2.sub'), prompt: t('empty.s2.prompt') },
    { icon: <TerminalSquare size={15} />, title: t('empty.s3.title'), sub: t('empty.s3.sub'), prompt: t('empty.s3.prompt') },
    {
      icon: <Braces size={15} />,
      title: t('empty.s4.title'),
      sub: t('empty.s4.sub'),
      prompt: locale === 'fr' ? BENCH_PROMPT.replace('Run this code:', 'Exécute ce code :') : BENCH_PROMPT,
    },
  ];

  return (
    <div className="flex h-full flex-col items-center justify-center px-5 pb-6">
      <motion.div
        initial={{ opacity: 0, scale: 0.92 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.5, ease: [0.22, 0.9, 0.3, 1] }}
        className="floaty relative"
      >
        {/* breathing halo */}
        <motion.div
          className="absolute inset-0 -z-10 scale-[2.6] rounded-full bg-accent-500/10 blur-3xl"
          animate={{ opacity: [0.55, 1, 0.55], scale: [2.2, 2.8, 2.2] }}
          transition={{ duration: 5, repeat: Infinity, ease: 'easeInOut' }}
        />
        {/* orbiting rings */}
        <div className="orbit-ring absolute -inset-4 -z-10 rounded-full border border-accent-500/15">
          <span className="absolute -top-[3px] left-1/2 h-1.5 w-1.5 -translate-x-1/2 rounded-full bg-accent-500/80 shadow-[0_0_8px_var(--glow)]" />
        </div>
        <div className="orbit-ring-rev absolute -inset-8 -z-10 rounded-full border border-dashed border-white/8">
          <span className="absolute top-1/2 -right-[2px] h-1 w-1 -translate-y-1/2 rounded-full bg-accent-400/60" />
        </div>
        <Logo size={46} />
      </motion.div>

      <motion.h1
        key={locale}
        initial={{ opacity: 0, y: 14 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.08, duration: 0.55, ease: [0.22, 0.9, 0.3, 1] }}
        className="mt-6 text-center font-serif text-[34px] leading-[1.05] text-zinc-100 sm:text-[44px]"
      >
        {t('empty.title.a')} <em className="italic text-accent-400">{t('empty.title.b')}</em>
      </motion.h1>

      <motion.p
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.16, duration: 0.5 }}
        className="mt-3 max-w-md text-center text-[13px] leading-relaxed text-zinc-500"
      >
        {t('empty.sub')}
      </motion.p>

      <div className="mt-8 grid w-full max-w-2xl grid-cols-1 gap-2.5 sm:grid-cols-2">
        {suggestions.map((s, i) => (
          <motion.button
            key={`${locale}-${i}`}
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.22 + i * 0.06, duration: 0.45, ease: [0.22, 0.9, 0.3, 1] }}
            onClick={() => onPick(s.prompt)}
            className="group rounded-xl border border-white/8 bg-white/[0.02] p-3.5 text-left transition hover:border-accent-500/35 hover:bg-accent-500/[0.04] active:scale-[0.99]"
          >
            <div className="flex items-center gap-2 text-accent-300/90">
              {s.icon}
              <span className="text-[12.5px] font-medium leading-snug text-zinc-200">{s.title}</span>
            </div>
            <p className="mt-1.5 font-mono text-[9.5px] leading-relaxed text-zinc-600 group-hover:text-zinc-500">
              {s.sub}
            </p>
          </motion.button>
        ))}
      </div>

      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.55 }}
        className="mt-7 flex items-center gap-2 font-mono text-[9.5px] uppercase tracking-[0.2em] text-zinc-700"
      >
        <span className="inline-block h-1 w-1 rounded-full bg-emerald-400/80" />
        {t('empty.badge', { n: TOOL_REGISTRY.length })}
      </motion.div>
    </div>
  );
}
