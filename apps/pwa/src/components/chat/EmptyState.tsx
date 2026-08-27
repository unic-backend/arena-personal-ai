/* ─────────────────────────────────────────────────────────────
   Écran d'accueil — le logo qui tourne, une salutation.
   Si une capacité est choisie dans le menu, ses phrases de départ
   s'affichent ici : ce sont de vraies phrases, envoyées telles
   quelles. Aucune promesse n'est faite sur ce qu'ARENA sait faire.
   ───────────────────────────────────────────────────────────── */

import { motion } from 'framer-motion';
import { useI18n } from '../../lib/i18n';
import { usePersona } from '../../lib/store/personaStore';
import { capaciteActive, useCapacite } from '../../lib/capacites';
import { Logo } from './Sidebar';

/* Salutation selon l'heure locale de l'appareil. */
function salutation(locale: string): string {
  const h = new Date().getHours();
  if (locale === 'fr') {
    if (h < 5) return 'Bonne nuit';
    if (h < 18) return 'Bonjour';
    return 'Bonsoir';
  }
  if (h < 5) return 'Good night';
  if (h < 12) return 'Good morning';
  if (h < 18) return 'Good afternoon';
  return 'Good evening';
}

export function EmptyState({ onPick }: { onPick: (prompt: string) => void }) {
  const { locale } = useI18n();
  const { userName } = usePersona();
  const { active } = useCapacite();

  const capacite = capaciteActive(active);
  const nom = userName.trim();
  const phrase = nom ? `${salutation(locale)}, ${nom}` : salutation(locale);
  const exemples = capacite ? (locale === 'fr' ? capacite.exemplesFr : capacite.exemplesEn) : [];

  return (
    <div className="flex h-full flex-col items-center justify-center px-5 pb-10">
      <motion.div
        initial={{ opacity: 0, scale: 0.92 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.5, ease: [0.22, 0.9, 0.3, 1] }}
        className="floaty relative"
      >
        {/* halo qui respire */}
        <motion.div
          className="absolute inset-0 -z-10 scale-[2.6] rounded-full bg-accent-500/10 blur-3xl"
          animate={{ opacity: [0.55, 1, 0.55], scale: [2.2, 2.8, 2.2] }}
          transition={{ duration: 5, repeat: Infinity, ease: 'easeInOut' }}
        />
        {/* anneaux en orbite — la planète autour du point central */}
        <div className="orbit-ring absolute -inset-4 -z-10 rounded-full border border-accent-500/15">
          <span className="absolute -top-[3px] left-1/2 h-1.5 w-1.5 -translate-x-1/2 rounded-full bg-accent-500/80 shadow-[0_0_8px_var(--glow)]" />
        </div>
        <div className="orbit-ring-rev absolute -inset-8 -z-10 rounded-full border border-dashed border-white/8">
          <span className="absolute -right-[2px] top-1/2 h-1 w-1 -translate-y-1/2 rounded-full bg-accent-400/60" />
        </div>
        <Logo size={44} />
      </motion.div>

      <motion.h1
        key={`${locale}-${phrase}`}
        initial={{ opacity: 0, y: 12 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1, duration: 0.5, ease: [0.22, 0.9, 0.3, 1] }}
        className="mt-7 text-center font-serif text-[30px] leading-tight text-zinc-200 sm:text-[36px]"
      >
        {phrase}
      </motion.h1>

      {capacite && (
        <motion.div
          key={capacite.id}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35 }}
          className="mt-6 w-full max-w-xl"
        >
          <div className="mb-2 flex items-center justify-center gap-1.5 font-mono text-[9.5px] uppercase tracking-[0.18em] text-zinc-600">
            <capacite.icone size={11} className="text-accent-400" />
            {locale === 'fr' ? capacite.nomFr : capacite.nomEn}
          </div>
          <div className="space-y-1.5">
            {exemples.map((ex) => (
              <button
                key={ex}
                type="button"
                onClick={() => onPick(ex)}
                className="w-full rounded-xl border border-white/8 bg-white/[0.02] px-3.5 py-2.5 text-left text-[12.5px] text-zinc-400 transition hover:border-accent-500/35 hover:bg-accent-500/[0.04] hover:text-zinc-200 active:scale-[0.99]"
              >
                {ex}
              </button>
            ))}
          </div>
        </motion.div>
      )}
    </div>
  );
}