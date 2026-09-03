/* ─────────────────────────────────────────────────────────────
   Event labels for the work that runs on the device — video and
   attachments — in English and French, picked by the detected
   conversation language so the timeline speaks the user's.

   This catalogue held six more sections: prose for a build
   repair, a web search, a terminal, a calculator and a chat,
   none of which ever ran. On 03/09/2026 one of them reached the
   owner's phone as if it were his AI. Removed with the pipelines
   that read them.
   ───────────────────────────────────────────────────────────── */

import type { Lang } from '../i18n';

const EN = {
  think: {
    analyzing: 'Analyzing your request',
    preparingShort: 'Preparing response',
    readingMsg: 'Reading the message and identifying intent',
  },

  video: {
    probeTitle: 'Analyzing video',
    probeDesc: 'Reading container metadata…',
    probeDone: (dur: string, res: string) => `${dur} · ${res}`,
    framesTitle: 'Extracting thumbnails',
    framesDesc: 'Sampling frames across the timeline…',
    framesDone: (n: number) => `${n} thumbnails extracted`,
    trimTitle: 'Trimming clip',
    trimDesc: (a: string, b: string) => `Re-encoding ${a} → ${b} with MediaRecorder…`,
    trimDone: (size: string) => `Clip ready · ${size}`,
    trimFail: 'Trim failed',
    unsupported: 'captureStream + MediaRecorder are not supported in this browser',
    summaryTitle: 'Reading the timeline',
    summaryDesc: 'Composing the video report from the probe and extracted frames…',
    answerMeta: (name: string, lines: string[], trimNote?: string) =>
      [
        `I processed **${name}** entirely on-device — nothing was uploaded anywhere.`,
        '',
        ...lines,
        '',
        ...(trimNote ? [trimNote] : []),
      ].join('\n'),
    metaLines: (dur: string, res: string, size: string, codec: string, frames: number) => [
      `- **Duration** — \`${dur}\` · **Resolution** — \`${res}\``,
      `- **Size** — \`${size}\` · **Container** — \`${codec}\``,
      `- **${frames} thumbnails** sampled across the timeline (see the activity card)`,
    ],
    trimNoteOk: (a: string, b: string, size: string) =>
      `### Trimmed clip ready\nRe-encoded segment \`${a} → ${b}\` (${size}) — grab it from the **video card** above with the download button.`,
    trimNoteHint:
      'Tip: ask "trim from 0:05 to 0:20" (or « coupe de 0:05 à 0:20 ») and I will cut a downloadable clip with real re-encoding progress.',
  },
};

const FR = {
  think: {
    analyzing: 'Analyse de votre demande',
    preparingShort: 'Préparation de la réponse',
    readingMsg: 'Lecture du message et identification de l’intention',
  },

  video: {
    probeTitle: 'Analyse de la vidéo',
    probeDesc: 'Lecture des métadonnées du conteneur…',
    probeDone: (dur: string, res: string) => `${dur} · ${res}`,
    framesTitle: 'Extraction des vignettes',
    framesDesc: 'Échantillonnage d’images sur la timeline…',
    framesDone: (n: number) => `${n} vignettes extraites`,
    trimTitle: 'Découpe du clip',
    trimDesc: (a: string, b: string) => `Ré-encodage ${a} → ${b} via MediaRecorder…`,
    trimDone: (size: string) => `Clip prêt · ${size}`,
    trimFail: 'Échec de la découpe',
    unsupported: 'captureStream + MediaRecorder ne sont pas pris en charge par ce navigateur',
    summaryTitle: 'Lecture de la timeline',
    summaryDesc: 'Composition du rapport vidéo à partir de la sonde et des images extraites…',
    answerMeta: (name: string, lines: string[], trimNote?: string) =>
      [
        `J’ai traité **${name}** entièrement sur votre appareil — rien n’a été envoyé ailleurs.`,
        '',
        ...lines,
        '',
        ...(trimNote ? [trimNote] : []),
      ].join('\n'),
    metaLines: (dur: string, res: string, size: string, codec: string, frames: number) => [
      `- **Durée** — \`${dur}\` · **Résolution** — \`${res}\``,
      `- **Taille** — \`${size}\` · **Conteneur** — \`${codec}\``,
      `- **${frames} vignettes** échantillonnées sur la timeline (voir la carte d’activité)`,
    ],
    trimNoteOk: (a: string, b: string, size: string) =>
      `### Clip découpé prêt\nSegment ré-encodé \`${a} → ${b}\` (${size}) — récupérez-le depuis la **carte vidéo** ci-dessus avec le bouton de téléchargement.`,
    trimNoteHint:
      'Astuce : demandez « coupe de 0:05 à 0:20 » et je créerai un clip téléchargeable avec une vraie progression de ré-encodage.',
  },
};

export type AgentDict = typeof EN;

export const agentStrings = (lang: Lang): AgentDict => (lang === 'fr' ? (FR as AgentDict) : EN);
