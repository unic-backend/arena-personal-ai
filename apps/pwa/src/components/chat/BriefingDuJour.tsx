/* ─────────────────────────────────────────────────────────────
   Le briefing du matin, sur l'ecran d'accueil (DEC-0168).
   N'apparait que si le serveur en a compose un AUJOURD'HUI et qu'il
   n'a pas encore ete ferme. Chaque rubrique montre son etat : un agenda
   non branche ne se lit jamais « journee libre ».
   ───────────────────────────────────────────────────────────── */

import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { Sunrise, Volume2, VolumeX, X } from 'lucide-react';
import { useI18n } from '../../lib/i18n';
import { useSpeech, isSpeechSynthesisSupported } from '../../lib/speech';
import { useBackend } from '../../lib/store/backendStore';
import {
  briefingAMontrer,
  heureDeComposition,
  marquerVu,
  type BriefingDuJour as Briefing,
} from '../../lib/briefing';
import { MarkdownLite } from '../activity/StreamingResponse';

const ID_LECTURE = 'briefing-du-jour';

export function BriefingDuJour() {
  const { t } = useI18n();
  const statut = useBackend((s) => s.status);
  const { speak, stop, speakingMessageId } = useSpeech();
  const [briefing, setBriefing] = useState<Briefing | null>(null);

  // Interroge seulement quand le serveur repond : avant, la question
  // partirait dans le vide et la carte n'apparaitrait jamais.
  useEffect(() => {
    if (statut !== 'online') return;
    let actif = true;
    void briefingAMontrer().then((b) => { if (actif) setBriefing(b); });
    return () => { actif = false; };
  }, [statut]);

  if (!briefing) return null;

  const enLecture = speakingMessageId === ID_LECTURE;
  const heure = heureDeComposition(briefing.composeA);

  const fermer = () => {
    if (enLecture) stop();
    marquerVu(briefing.jour);
    setBriefing(null);
  };

  return (
    <motion.section
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
      className="mt-6 w-full max-w-xl rounded-2xl border border-accent-500/20 bg-accent-500/[0.04] p-4"
      aria-label={t('briefing.titre')}
    >
      <header className="mb-3 flex items-center gap-2">
        <Sunrise size={15} className="text-accent-400" />
        <h2 className="text-ui-body-sm font-medium text-zinc-200">{t('briefing.titre')}</h2>
        {heure && (
          <span className="font-mono text-ui-meta text-zinc-500">{t('briefing.compose', { heure })}</span>
        )}
        <div className="ml-auto flex items-center gap-1">
          {isSpeechSynthesisSupported() && briefing.texte && (
            <button
              type="button"
              onClick={() => (enLecture ? stop() : speak(ID_LECTURE, briefing.texte, 'fr'))}
              className="flex items-center gap-1 rounded-lg px-2 py-1 text-ui-meta text-accent-300 transition hover:bg-accent-500/10"
            >
              {enLecture ? <VolumeX size={13} /> : <Volume2 size={13} />}
              {enLecture ? t('briefing.arreter') : t('briefing.ecouter')}
            </button>
          )}
          <button
            type="button"
            onClick={fermer}
            title={t('briefing.fermer')}
            aria-label={t('briefing.fermer')}
            className="rounded-lg p-1 text-zinc-500 transition hover:bg-white/5 hover:text-zinc-300"
          >
            <X size={14} />
          </button>
        </div>
      </header>

      <div className="max-h-[45vh] space-y-3 overflow-y-auto pr-1">
        {briefing.rubriques.map((r) => (
          <div key={r.titre}>
            <div className="mb-0.5 flex items-baseline gap-2">
              <h3 className="text-ui-body-sm font-medium text-zinc-300">{r.titre}</h3>
              {r.etat !== 'OK' && (
                <span className="font-mono text-ui-meta text-amber-400/80">
                  {t(`briefing.etat.${r.etat}`)}
                </span>
              )}
            </div>
            <div className="text-ui-body-sm text-zinc-400">
              <MarkdownLite text={r.texte} />
            </div>
          </div>
        ))}
      </div>
    </motion.section>
  );
}
