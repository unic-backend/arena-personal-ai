/* ─────────────────────────────────────────────────────────────
   Video project modal — real POST /api/video/projet
   (apps/backend/routers/video_production.py, DEC-0037).

   AUTO (nothing selected) lets the server's VideoProductionAgent
   pick from the full closed capability list; selecting one or more
   chips switches to TEAM mode — the exact subset requested, never
   auto-expanded. Every status shown below the fold is read straight
   from the backend's response: no progress bar animates on its own,
   no step is marked done before the server said so.
   ───────────────────────────────────────────────────────────── */

import { useEffect } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  AlertTriangle, AudioLines, Ban, Check, Clapperboard, Eye, FileVideo2, Film,
  Image, ImagePlus, Languages, Loader2, Mic2, Paperclip, RectangleHorizontal,
  RectangleVertical, Scissors, Sparkles, Subtitles, UserRoundCog, Video, Wand2, X,
} from 'lucide-react';
import {
  CapaciteVideo, CAPACITES_VIDEO, EtapeProjetResultat, useVideoProject,
} from '../../lib/store/videoProjectStore';
import { useBackend } from '../../lib/store/backendStore';
import { useI18n } from '../../lib/i18n';
import { cn } from '../../utils/cn';

const ICONE_CAPACITE: Record<CapaciteVideo, typeof Eye> = {
  vision: Eye,
  transcription: Subtitles,
  wangp: Film,
  moneyprinter: Sparkles,
  narration: Mic2,
  xaar_kaname: UserRoundCog,
  montage: Scissors,
  krillin_subtitle: Languages,
  krillin_tts: AudioLines,
  krillin_render_horizontal: RectangleHorizontal,
  krillin_render_vertical: RectangleVertical,
  krillin_cover: Image,
  drift: Wand2,
  hidream_image: ImagePlus,
};

function labelCapacite(c: CapaciteVideo, fr: boolean): string {
  const labels: Record<CapaciteVideo, [string, string]> = {
    vision: ['Vision', 'Vision'],
    transcription: ['Transcription', 'Transcription'],
    wangp: ['Génération de scène', 'Scene generation'],
    moneyprinter: ['Production auto', 'Auto production'],
    xaar_kaname: ['Visage (Xaar Kaname)', 'Face (Xaar Kaname)'],
    narration: ['Narration', 'Narration'],
    montage: ['Montage', 'Editing'],
    krillin_subtitle: ['Sous-titres traduits (KrillinAI)', 'Translated subtitles (KrillinAI)'],
    krillin_tts: ['Doublage (KrillinAI)', 'Dubbing (KrillinAI)'],
    krillin_render_horizontal: ['Rendu horizontal (KrillinAI)', 'Horizontal render (KrillinAI)'],
    krillin_render_vertical: ['Rendu vertical (KrillinAI)', 'Vertical render (KrillinAI)'],
    krillin_cover: ['Couverture (KrillinAI)', 'Cover image (KrillinAI)'],
    drift: ['Montage IA (Drift)', 'AI editing (Drift)'],
    hidream_image: ['Image haute qualité (HiDream-I1)', 'High-quality image (HiDream-I1)'],
  };
  return fr ? labels[c][0] : labels[c][1];
}

function EtapeRow({ etape, fr }: { etape: EtapeProjetResultat; fr: boolean }) {
  const icone = (() => {
    switch (etape.etat) {
      case 'RUNNING':
        return <Loader2 size={12} className="animate-spin text-accent-400" />;
      case 'DONE':
        return (
          <span className="grid h-4 w-4 place-items-center rounded-full bg-emerald-400/12 text-emerald-400">
            <Check size={9} strokeWidth={3.2} />
          </span>
        );
      case 'FAILED':
        return (
          <span className="grid h-4 w-4 place-items-center rounded-full bg-red-400/12 text-red-400">
            <X size={9} strokeWidth={3.2} />
          </span>
        );
      case 'SKIPPED':
        return (
          <span className="grid h-4 w-4 place-items-center rounded-full bg-zinc-500/15 text-zinc-500">
            <Ban size={8} strokeWidth={2.6} />
          </span>
        );
      case 'NOT_REACHED':
        return <span className="h-4 w-4 rounded-full border border-dashed border-zinc-700" />;
      default:
        return <span className="h-4 w-4 rounded-full border border-zinc-700" />;
    }
  })();

  return (
    <div className="flex items-start gap-2.5 py-1.5">
      <span className="mt-[1px] shrink-0">{icone}</span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5">
          <span className="truncate text-[12px] font-medium text-zinc-200">{etape.etape}</span>
          {etape.tentatives > 1 && (
            <span className="shrink-0 font-mono text-[9px] text-zinc-600">
              ×{etape.tentatives}
            </span>
          )}
        </div>
        {etape.raison && (
          <div className="truncate text-[10.5px] text-zinc-500">{etape.raison}</div>
        )}
      </div>
      <span className="shrink-0 font-mono text-[9px] uppercase tracking-wide text-zinc-600">
        {fr
          ? { PENDING: 'attente', RUNNING: 'en cours', DONE: 'fait', FAILED: 'échec',
              SKIPPED: 'ignorée', NOT_REACHED: 'jamais lancée' }[etape.etat]
          : etape.etat.toLowerCase()}
      </span>
    </div>
  );
}

export function VideoProjectModal() {
  const { t, locale } = useI18n();
  const fr = locale === 'fr';
  const backend = useBackend();
  const {
    modalOpen, setModalOpen, objectif, setObjectif,
    capacitesChoisies, toggleCapacite, disponibilite, chargerDisponibilite,
    references, addReferenceFiles, removeReference,
    submitting, result, error, submit, reset,
  } = useVideoProject();

  useEffect(() => {
    if (!modalOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setModalOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [modalOpen, setModalOpen]);

  const close = () => {
    setModalOpen(false);
    reset();
  };

  const mode = capacitesChoisies.size > 0 ? 'team' : 'auto';

  /* Ce que la machine branchee sait faire, demande a chaque ouverture : un
     PC qu'on allume entre deux ouvertures doit changer l'affichage. */
  useEffect(() => {
    if (modalOpen) void chargerDisponibilite();
  }, [modalOpen, chargerDisponibilite]);

  const indisponibles = (CAPACITES_VIDEO
    .map((c) => [c, disponibilite?.[c]] as const)
    .filter(([, etat]) => etat?.disponible === false)) as Array<
      [CapaciteVideo, { disponible: boolean; raison: string }]>;
  const etapes = result?.projet?.resultat?.etapes ?? [];

  return (
    <AnimatePresence>
      {modalOpen && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[60] bg-black/70 backdrop-blur-sm"
            onClick={close}
          />
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby="video-project-modal-title"
            initial={{ opacity: 0, scale: 0.96, y: 16 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: 12 }}
            transition={{ type: 'spring', stiffness: 380, damping: 32 }}
            className="fixed inset-x-3 top-[4vh] z-[61] mx-auto flex max-h-[92vh] w-full max-w-lg flex-col overflow-hidden rounded-2xl border border-white/10 bg-ink-900 shadow-[0_40px_120px_-20px_rgba(0,0,0,0.9)] sm:top-[6vh]"
          >
            <div className="flex items-center gap-2.5 border-b border-white/7 px-4 py-3">
              <span className="grid h-7 w-7 place-items-center rounded-lg border border-accent-500/30 bg-accent-500/10 text-accent-300">
                <Clapperboard size={13} />
              </span>
              <div className="flex-1">
                <h2 id="video-project-modal-title" className="text-[13.5px] font-medium text-zinc-100">
                  {t('vidproj.title')}
                </h2>
                <div className="font-mono text-[9px] text-zinc-400">
                  {backend.enabled ? t('vidproj.routed') : t('vidproj.localOnly')}
                </div>
              </div>
              <button
                type="button"
                onClick={close}
                aria-label="Close"
                className="rounded-md p-1.5 text-zinc-500 transition hover:bg-white/5 hover:text-zinc-200"
              >
                <X size={15} />
              </button>
            </div>

            <div className="flex-1 space-y-4 overflow-y-auto p-4 scroll-slim">
              {!backend.enabled ? (
                <div className="rounded-xl border border-amber-500/20 bg-amber-500/[0.05] p-3 text-[11.5px] leading-relaxed text-amber-200/90">
                  <AlertTriangle size={13} className="mb-1 inline-block" /> {t('vidproj.needBackend')}
                </div>
              ) : (
                <>
                  <div>
                    <label htmlFor="vidproj-objectif" className="mb-1.5 block text-[10.5px] font-medium text-zinc-400">
                      {t('vidproj.objectifLabel')}
                    </label>
                    <textarea
                      id="vidproj-objectif"
                      value={objectif}
                      onChange={(e) => setObjectif(e.target.value)}
                      placeholder={t('vidproj.objectifPh')}
                      rows={3}
                      className="w-full resize-none rounded-xl border border-white/8 bg-white/[0.02] px-3 py-2.5 text-[12.5px] text-zinc-100 placeholder:text-zinc-600 focus:border-accent-500/40 focus:outline-none"
                    />
                  </div>

                  <div>
                    <div className="mb-1.5 flex items-center justify-between">
                      <span className="text-[10.5px] font-medium text-zinc-400">{t('vidproj.referencesLabel')}</span>
                      <label className="inline-flex cursor-pointer items-center gap-1 text-[10.5px] font-medium text-accent-300 hover:text-accent-200">
                        <Paperclip size={11} />
                        {t('vidproj.addReference')}
                        <input
                          type="file"
                          // Doit rester le miroir exact de ce que le serveur accepte
                          // (apps/backend/config.py:EXTENSIONS_MEDIA_AUTORISEES) — image
                          // comprise depuis le 02/09/2026, pour que « vision » reçoive
                          // enfin la photo qu'elle lit.
                          accept="image/*,video/*,audio/*"
                          multiple
                          className="hidden"
                          onChange={(e) => {
                            if (e.target.files?.length) void addReferenceFiles(e.target.files);
                            e.target.value = '';
                          }}
                        />
                      </label>
                    </div>
                    {references.length > 0 ? (
                      <div className="flex flex-wrap gap-1.5">
                        {references.map((r) => (
                          <span
                            key={r.id}
                            title={r.status === 'failed' ? r.error : r.name}
                            className={cn(
                              'inline-flex items-center gap-1.5 rounded-lg border px-2 py-1 text-[10.5px]',
                              r.status === 'failed'
                                ? 'border-red-500/25 bg-red-500/[0.05] text-red-300'
                                : 'border-white/10 bg-white/[0.03] text-zinc-300',
                            )}
                          >
                            {r.status === 'uploading' && <Loader2 size={10} className="animate-spin" />}
                            <span className="max-w-[140px] truncate">{r.name}</span>
                            <button
                              type="button"
                              onClick={() => removeReference(r.id)}
                              aria-label="Remove"
                              className="text-zinc-500 transition hover:text-zinc-200"
                            >
                              <X size={10} />
                            </button>
                          </span>
                        ))}
                      </div>
                    ) : (
                      <p className="text-[9.5px] leading-relaxed text-zinc-600">{t('vidproj.referencesHint')}</p>
                    )}
                  </div>

                  <div>
                    <div className="mb-1.5 flex items-center justify-between">
                      <span className="text-[10.5px] font-medium text-zinc-400">{t('vidproj.modeLabel')}</span>
                      <span className="font-mono text-[9px] uppercase tracking-wide text-zinc-600">
                        {mode === 'auto' ? t('vidproj.modeAuto') : t('vidproj.modeTeam')}
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {CAPACITES_VIDEO.map((c) => {
                        const Icon = ICONE_CAPACITE[c];
                        const selected = capacitesChoisies.has(c);
                        // `null` = le serveur n'a pas repondu : on n'affiche
                        // aucun verdict plutot qu'un faux. Une capacite connue
                        // indisponible porte toujours sa raison.
                        const etat = disponibilite?.[c];
                        const indisponible = etat?.disponible === false;
                        return (
                          <button
                            key={c}
                            type="button"
                            onClick={() => toggleCapacite(c)}
                            disabled={indisponible}
                            title={indisponible ? etat?.raison : undefined}
                            className={cn(
                              'inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] font-medium transition active:scale-95',
                              indisponible
                                ? 'cursor-not-allowed border-white/5 bg-white/[0.01] text-zinc-600 line-through decoration-zinc-700'
                                : selected
                                  ? 'border-accent-500/40 bg-accent-500/10 text-accent-300'
                                  : 'border-white/8 bg-white/[0.02] text-zinc-400 hover:border-white/15 hover:text-zinc-200',
                            )}
                          >
                            <Icon size={12} />
                            {labelCapacite(c, fr)}
                          </button>
                        );
                      })}
                    </div>
                    {indisponibles.length > 0 && (
                      /* Un telephone n'a pas de survol : la raison doit etre
                         lue sans y toucher, sinon elle n'existe pas. */
                      <ul className="mt-2 space-y-1 border-l border-amber-500/25 pl-2.5">
                        {indisponibles.map(([nom, etat]) => (
                          <li key={nom} className="text-[9.5px] leading-relaxed text-zinc-500">
                            <span className="text-zinc-400">{labelCapacite(nom, fr)}</span>
                            {' — '}{etat.raison}
                          </li>
                        ))}
                      </ul>
                    )}
                    <p className="mt-1.5 text-[9.5px] leading-relaxed text-zinc-600">
                      {mode === 'auto' ? t('vidproj.modeAutoHint') : t('vidproj.modeTeamHint')}
                    </p>
                  </div>

                  <button
                    type="button"
                    disabled={submitting || !objectif.trim() || references.some((r) => r.status === 'uploading')}
                    onClick={() => void submit()}
                    className="flex w-full items-center justify-center gap-2 rounded-xl border border-accent-500/30 bg-accent-500/10 px-3 py-2.5 text-[12.5px] font-medium text-accent-300 transition hover:bg-accent-500/15 active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {submitting ? <Loader2 size={13} className="animate-spin" /> : <Video size={13} />}
                    {submitting ? t('vidproj.submitting') : t('vidproj.submit')}
                  </button>

                  {error && (
                    <div className="rounded-xl border border-red-500/20 bg-red-500/[0.05] p-3 text-[11.5px] text-red-300">
                      {error === 'no-backend' ? t('vidproj.needBackend') : error}
                    </div>
                  )}

                  {result && (
                    <div
                      className={cn(
                        'rounded-xl border p-3',
                        result.status === 'success'
                          ? 'border-emerald-500/20 bg-emerald-500/[0.04]'
                          : result.status === 'warning'
                            ? 'border-amber-500/20 bg-amber-500/[0.04]'
                            : 'border-red-500/20 bg-red-500/[0.04]',
                      )}
                    >
                      <p className="whitespace-pre-wrap text-[12px] leading-relaxed text-zinc-200">
                        {result.response}
                      </p>
                      {result.projet?.artefact_final && (
                        <div className="mt-2 flex items-center gap-1.5 font-mono text-[10px] text-emerald-300">
                          <FileVideo2 size={11} /> {result.projet.artefact_final}
                        </div>
                      )}
                      {etapes.length > 0 && (
                        <div className="mt-2.5 divide-y divide-white/5 border-t border-white/5 pt-1">
                          {etapes.map((e) => (
                            <EtapeRow key={e.etape} etape={e} fr={fr} />
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </>
              )}
            </div>

            <div className="border-t border-white/7 px-4 py-2.5">
              <p className="text-[9.5px] leading-relaxed text-zinc-600">{t('vidproj.footer')}</p>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
