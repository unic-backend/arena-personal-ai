/* ─────────────────────────────────────────────────────────────
   Agent text catalogue — every event label and answer the
   backend emits, in English and French. The orchestrator picks
   the catalogue matching the detected conversation language, so
   the timeline itself speaks the user's language.
   ───────────────────────────────────────────────────────────── */

import type { Lang } from '../i18n';

export interface FixFacts {
  diagCount: number;
  fileCount: number;
  diags: Array<{ file: string; line: number; code: string; message: string }>;
  fixedFiles: Array<{ path: string; summary: string; added: number; removed: number }>;
  testPassed: number;
  testTotal: number;
  suites: number;
  buildLine: string;
  files: number;
  lines: string;
  depCount: number;
}

const EN = {
  think: {
    analyzing: 'Analyzing your request',
    understanding: 'Understanding the task and planning an execution pipeline',
    planning: 'Planning the task',
    planDesc: 'inspect → dependencies → build → diagnose → fix → verify',
    preparing: 'Preparing final response',
    preparingShort: 'Preparing response',
    organizing: 'Organizing the findings',
    synthesizing: 'Synthesizing the findings with citations',
    understandingReq: 'Understanding the request',
    readingMsg: 'Reading the message and identifying intent',
    composing: 'Composing the response',
    weaving: 'Weaving in the relevant findings with citations',
    structuring: 'Structuring the answer',
  },
  planSteps: ['Inspect repository', 'Check dependencies', 'Run build', 'Fix errors', 'Run tests', 'Rebuild'],

  units: { files: 'files', tests: 'tests', sources: 'sources' },

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

  fix: {
    scan: 'Inspecting repository',
    walk: 'Walking the project tree…',
    scanFile: (f: string) => `Scanning ${f}`,
    scanDone: (n: number, l: string) => `${n} files discovered · ${l} lines`,
    deps: 'Checking dependencies',
    parseManifest: 'parse manifest',
    depsDeclared: (n: number) => `${n} dependencies declared`,
    strictOn: 'strict mode enabled',
    strictOff: 'strict mode off',
    depsDone: (n: number) => `${n} dependencies · strict TS`,
    buildRun: 'Running build',
    buildDesc: 'Executing in project sandbox…',
    buildExit: (c: number) => `Exited with code ${c}`,
    exitOk: 'Exit code 0',
    investigate: 'Investigating build errors',
    invDesc: 'Mapping diagnostics to root causes…',
    invDone: (d: number, f: number) => `${d} type errors across ${f} files`,
    editing: 'Editing files',
    editDesc: 'Applying targeted patches…',
    fixDep: `added 'date-fns' to dependencies`,
    fixRet: 'formatDuration now honours its string return type',
    fixRename: (m: string) => `renamed import '${m}' → 'cn' to match the module's exports`,
    manual: 'manual review required — no safe automatic patch',
    filesModified: (n: number) => `${n} file${n === 1 ? '' : 's'} modified`,
    tests: 'Running tests',
    testsDiscover: 'Discovering test suites…',
    testsRun: (p: string) => `Running ${p}…`,
    testsDone: (p: number, s: number) => `${p} tests passed across ${s} suites`,
    testFailed: 'test run failed',
    rebuild: 'Running build again',
    rebuildDesc: 'Verifying the fix end-to-end…',
  },

  research: {
    identify: (q: string) => `Identifying the research question: “${q}”`,
    searching: 'Searching the web',
    searchingDesc: (q: string) => `Searching: “${q}”`,
    querying: 'Querying the index and ranking results…',
    found: (n: number) => `Found ${n} result${n === 1 ? '' : 's'}`,
    reading: 'Reading sources',
    opening: 'Opening the most relevant documents…',
    openedProg: (a: number, b: number) => `Opened ${a}/${b} sources…`,
    openedDone: (n: number) => `Opened ${n} sources · extracted key passages`,
    comparing: 'Comparing sources',
    comparingDesc: 'Cross-checking claims, dates and figures…',
    compared: (n: number, range: string) => `${n} sources analyzed · publication window ${range}`,
    heresWhat: (q: string) => `Here's what current sources say about **${q}**:`,
    keyFindings: '### Key findings',
    across: (n: number, doms: string, closing: string) =>
      `Across the ${n} sources (${doms}), the consistent picture is that ${closing}.`,
    none: (q: string) =>
      `I searched the index for **“${q}”** but the corpus returned no credible sources. I won't speculate — try rephrasing, or ask about AI reasoning models, agents, inference costs, context windows, coding evaluation, streaming architectures or agent UX, which the index covers well.`,
  },

  calc: {
    title: 'Calculating',
    desc: 'Evaluating with the exact arithmetic engine…',
    failTitle: 'Calculation failed',
    answer: (expr: string, pretty: string) =>
      `**${expr.trim()} = ${pretty}**\n\nEvaluated exactly with the built-in arithmetic engine — no rounding until the final display.`,
    fail: (expr: string, err: string) =>
      `I couldn't evaluate \`${expr.trim()}\` — ${err}. Supported operators: \`+ - * / % ^ ( )\`, constants \`pi\` and \`e\`.`,
  },

  code: {
    title: 'Code execution',
    failTitle: 'Code execution failed',
    running: (label: string) => `Running ${label} in the sandbox…`,
    noRunner: (lang: string) => `No runner registered for language "${lang}"`,
    noRunnerDesc: (lang: string, registered: string) => `No runner for "${lang}". Registered: ${registered}`,
    doneDesc: (n: number, ms: string) => `${n} output line${n === 1 ? '' : 's'} · ${ms}ms`,
    noRunnerAnswer: (labels: string, lang: string) =>
      `This runtime only has executors registered for **${labels}** — there's no **${lang}** runner attached, so I ran nothing. The interface will only ever show executions that actually happened.`,
    okAnswer: (label: string, n: number, ms: string, lines: string[]) =>
      [
        `Executed your ${label} in the sandbox — **${n} output line${n === 1 ? '' : 's'}** in ${ms}ms:`,
        '', '```', ...lines, '```', '',
        n ? 'Everything ran cleanly.' : 'The program ran cleanly but printed nothing.',
      ].join('\n'),
    errAnswer: (err: string, lines: string[]) =>
      [
        `Execution failed with \`${err}\`. Output captured before the exception:`,
        '', '```', ...(lines.length ? lines : ['(no output)']), '```', '',
        'Fix the throw site and send it again — the sandbox will re-run it fresh.',
      ].join('\n'),
  },

  command: {
    title: 'Running command',
    titleFailed: 'Command failed',
    desc: 'Executing in project sandbox…',
    retrying: 'Retrying command…',
    retryOk: 'Exit code 0 · retry successful',
    moreLines: (n: number) => `… ${n} more lines`,
    noteBuild: 'The production build type-checked and bundled successfully.',
    noteTest: 'The full suite passed — output above shows every discovered test file.',
    noteGeneric: 'Command output above is exactly what the sandbox returned.',
    okLead: (cmd: string) => `\`${cmd}\` completed with **exit code 0**:`,
    failLead: (cmd: string, code: number) => `\`${cmd}\` **failed with exit code ${code}**:`,
    diagNote: (n: number) =>
      `The compiler reported **${n} error${n === 1 ? '' : 's'}**. Ask me to "analyze my project and fix the build problems" and I'll run the full repair pipeline.`,
    retryNote: 'You can retry the command from the activity card, or ask me to investigate.',
  },

  chat: {
    gatherTitle: 'Gathering context',
    gatherDesc: 'Scanning indexed knowledge for relevant material…',
    found: (n: number) => `${n} relevant reference${n === 1 ? '' : 's'} found`,
    noneNeeded: 'no domain references needed',
    greeting: [
      `Hello — I'm **Usman**, an observable AI workbench. Every tool I run shows up live in the activity timeline above my answers, so you can watch me work instead of waiting on a spinner.`,
      '',
      'Try one of these to see the full execution pipeline:',
      '',
      '- "Analyze my project and fix the build problems" — repo scan, failing build, real edits, tests',
      '- "Search the web for the latest AI reasoning models" — retrieval, source reading, cited synthesis',
      '- "Run npm run build" — raw terminal execution with exit codes',
      '- "Compute (128 × 46 + 1024) ^ 2" — the exact arithmetic engine',
    ].join('\n'),
    caps: [
      'My runtime is wired to a set of real, inspectable tools. Nothing is simulated at the UI layer — if a card appears in the timeline, the operation genuinely executed against the workspace:',
      '',
      '- **Web Search + Browser** — query a document index, open sources, cite them',
      '- **Terminal** — `npm run build`, `npm test`, `ls`, `cat`, `grep`, `wc` in a real project tree',
      '- **File tools** — scan, read, edit; my edits persist across sessions',
      '- **Code Executor** — JavaScript / TypeScript in a sandbox with captured stdout',
      '- **Calculator** — exact expression evaluation',
      '',
      'Ask me to fix the build, research a topic, run a command, or execute code — and watch the timeline.',
    ].join('\n'),
    hitsIntro: 'Based on the references in my index:',
    strongest: (title: string, domain: string, excerpt: string) =>
      `The strongest single source here is "${title}" (${domain}), which notes that ${excerpt}. [1]`,
    deeperAsk: 'Want me to run a deeper, fully-cited research pass on this? Say "search the web for …" and I will open the underlying sources.',
    fallback: [
      `I read your message carefully. A candid note: this workbench runs on a **local execution runtime** rather than a general-purpose web model, so I won't improvise an answer I can't stand behind.`,
      '',
      `Here's what I can genuinely do, with every step visible in the timeline:`,
      '',
      '- **Repair the seeded project** — "analyze my project and fix the build problems"',
      '- **Research topics my index covers** — AI models, agents, inference costs, evals, agent UX, streaming architectures',
      '- **Run real commands** — "run npm test", "run ls src", "run grep TODO src"',
      '- **Execute code** — paste a JavaScript/TypeScript block and say "run this"',
      '- **Arithmetic** — "compute (2048 / 32) ^ 3"',
      '',
      'Which pipeline should I run?',
    ].join('\n'),
  },

  fixAnswer: (f: FixFacts) =>
    [
      `The build was failing because of **${f.diagCount} TypeScript errors across ${f.fileCount} files**. All of them are fixed now — tests and build are green.`,
      '',
      '### Root causes',
      ...f.diags.map((d) => `- \`${d.file}:${d.line}\` — ${d.message} (${d.code})`),
      '',
      '### What I changed',
      ...f.fixedFiles.map((x) => `- \`${x.path}\` — ${x.summary} *(+${x.added} / −${x.removed} lines)*`),
      '',
      '### Verification',
      `- \`npm test\` — **${f.testPassed}/${f.testTotal} tests passed** across ${f.suites} suites`,
      `- \`npm run build\` — ${f.buildLine.replace('✓ ', '')}`,
      '',
      'The repository state was persisted, so the project will build cleanly from now on.',
    ].join('\n'),

  fixGreenAnswer: (f: FixFacts) =>
    [
      `Good news — I inspected the project and **the build is already green**. Nothing needed fixing.`,
      '',
      '### What I checked',
      `- Repository scan — ${f.files} files, ${f.lines} lines`,
      `- Dependencies — ${f.depCount} declared, strict TypeScript enabled`,
      '- `npm run build` — exit code 0',
      `- \`npm test\` — **${f.testPassed}/${f.testTotal} tests passed**`,
      '',
      'If you break something on purpose, ask me to fix it again and watch the repair pipeline run.',
    ].join('\n'),
};

export type AgentDict = typeof EN;

const FR: AgentDict = {
  think: {
    analyzing: 'Analyse de votre demande',
    understanding: 'Compréhension de la tâche et planification de l’exécution',
    planning: 'Planification de la tâche',
    planDesc: 'inspection → dépendances → build → diagnostic → correction → vérification',
    preparing: 'Préparation de la réponse finale',
    preparingShort: 'Préparation de la réponse',
    organizing: 'Organisation des résultats',
    synthesizing: 'Synthèse des résultats avec citations',
    understandingReq: 'Compréhension de la demande',
    readingMsg: 'Lecture du message et identification de l’intention',
    composing: 'Rédaction de la réponse',
    weaving: 'Intégration des résultats pertinents avec citations',
    structuring: 'Structuration de la réponse',
  },
  planSteps: ['Inspecter le dépôt', 'Vérifier les dépendances', 'Lancer le build', 'Corriger les erreurs', 'Lancer les tests', 'Relancer le build'],

  units: { files: 'fichiers', tests: 'tests', sources: 'sources' },

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

  fix: {
    scan: 'Inspection du dépôt',
    walk: 'Parcours de l’arborescence du projet…',
    scanFile: (f) => `Analyse de ${f}`,
    scanDone: (n, l) => `${n} fichiers découverts · ${l} lignes`,
    deps: 'Vérification des dépendances',
    parseManifest: 'analyse du manifeste',
    depsDeclared: (n) => `${n} dépendances déclarées`,
    strictOn: 'mode strict activé',
    strictOff: 'mode strict désactivé',
    depsDone: (n) => `${n} dépendances · TS strict`,
    buildRun: 'Exécution du build',
    buildDesc: 'Exécution dans le bac à sable du projet…',
    buildExit: (c) => `Arrêt avec le code ${c}`,
    exitOk: 'Code de sortie 0',
    investigate: 'Analyse des erreurs de build',
    invDesc: 'Correspondance entre diagnostics et causes racines…',
    invDone: (d, f) => `${d} erreurs de type dans ${f} fichiers`,
    editing: 'Modification des fichiers',
    editDesc: 'Application de correctifs ciblés…',
    fixDep: `ajout de 'date-fns' aux dépendances`,
    fixRet: 'formatDuration respecte désormais son type de retour string',
    fixRename: (m) => `renommage de l’import '${m}' en 'cn' pour correspondre aux exports du module`,
    manual: 'revue manuelle requise — aucun correctif automatique sûr',
    filesModified: (n) => `${n} fichier${n === 1 ? '' : 's'} modifié${n === 1 ? '' : 's'}`,
    tests: 'Exécution des tests',
    testsDiscover: 'Découverte des suites de tests…',
    testsRun: (p) => `Exécution de ${p}…`,
    testsDone: (p, s) => `${p} tests réussis dans ${s} suites`,
    testFailed: 'échec de la campagne de tests',
    rebuild: 'Nouvelle exécution du build',
    rebuildDesc: 'Vérification complète du correctif…',
  },

  research: {
    identify: (q) => `Identification de la question de recherche : « ${q} »`,
    searching: 'Recherche sur le web',
    searchingDesc: (q) => `Recherche : « ${q} »`,
    querying: 'Interrogation de l’index et classement des résultats…',
    found: (n) => `${n} résultat${n === 1 ? '' : 's'} trouvé${n === 1 ? '' : 's'}`,
    reading: 'Lecture des sources',
    opening: 'Ouverture des documents les plus pertinents…',
    openedProg: (a, b) => `${a}/${b} sources ouvertes…`,
    openedDone: (n) => `${n} sources ouvertes · passages clés extraits`,
    comparing: 'Comparaison des sources',
    comparingDesc: 'Recoupement des affirmations, dates et chiffres…',
    compared: (n, range) => `${n} sources analysées · fenêtre de publication ${range}`,
    heresWhat: (q) => `Voici ce que disent les sources actuelles à propos de **${q}** :`,
    keyFindings: '### Principaux résultats',
    across: (n, doms, closing) =>
      `À travers les ${n} sources (${doms}), le constat qui se dégage est que ${closing}.`,
    none: (q) =>
      `J’ai interrogé l’index pour **« ${q} »**, mais le corpus n’a renvoyé aucune source crédible. Je ne vais pas spéculer — reformulez, ou interrogez-moi sur les modèles de raisonnement IA, les agents, les coûts d’inférence, les fenêtres de contexte, l’évaluation du code, les architectures de streaming ou l’UX des agents, que l’index couvre bien.`,
  },

  calc: {
    title: 'Calcul en cours',
    desc: 'Évaluation avec le moteur arithmétique exact…',
    failTitle: 'Échec du calcul',
    answer: (expr, pretty) =>
      `**${expr.trim()} = ${pretty}**\n\nÉvalué exactement avec le moteur arithmétique intégré — aucun arrondi avant l’affichage final.`,
    fail: (expr, err) =>
      `Impossible d’évaluer \`${expr.trim()}\` — ${err}. Opérateurs pris en charge : \`+ - * / % ^ ( )\`, constantes \`pi\` et \`e\`.`,
  },

  code: {
    title: 'Exécution de code',
    failTitle: 'Échec de l’exécution du code',
    running: (label) => `Exécution ${label} dans le bac à sable…`,
    noRunner: (lang) => `Aucun exécuteur enregistré pour le langage « ${lang} »`,
    noRunnerDesc: (lang, registered) => `Pas d’exécuteur pour « ${lang} ». Enregistrés : ${registered}`,
    doneDesc: (n, ms) => `${n} ligne${n === 1 ? '' : 's'} de sortie · ${ms}ms`,
    noRunnerAnswer: (labels, lang) =>
      `Ce moteur n’a d’exécuteurs enregistrés que pour **${labels}** — aucun exécuteur **${lang}** n’est attaché, donc rien n’a été lancé. L’interface n’affichera toujours que des exécutions réellement effectuées.`,
    okAnswer: (label, n, ms, lines) =>
      [
        `Votre ${label} a été exécuté dans le bac à sable — **${n} ligne${n === 1 ? '' : 's'} de sortie** en ${ms}ms :`,
        '', '```', ...lines, '```', '',
        n ? 'Tout s’est exécuté proprement.' : 'Le programme s’est exécuté proprement mais n’a rien affiché.',
      ].join('\n'),
    errAnswer: (err, lines) =>
      [
        `L’exécution a échoué avec \`${err}\`. Sortie capturée avant l’exception :`,
        '', '```', ...(lines.length ? lines : ['(aucune sortie)']), '```', '',
        'Corrigez le point de déclenchement et renvoyez le code — le bac à sable le relancera à neuf.',
      ].join('\n'),
  },

  command: {
    title: 'Exécution de la commande',
    titleFailed: 'Échec de la commande',
    desc: 'Exécution dans le bac à sable du projet…',
    retrying: 'Nouvelle tentative…',
    retryOk: 'Code de sortie 0 · nouvelle tentative réussie',
    moreLines: (n) => `… ${n} lignes supplémentaires`,
    noteBuild: 'Le build de production a été typé et bundlé avec succès.',
    noteTest: 'Toute la suite est passée — la sortie ci-dessus liste chaque fichier de test découvert.',
    noteGeneric: 'La sortie ci-dessus est exactement ce que le bac à sable a renvoyé.',
    okLead: (cmd) => `\`${cmd}\` terminée avec le **code de sortie 0** :`,
    failLead: (cmd, code) => `\`${cmd}\` **a échoué avec le code ${code}** :`,
    diagNote: (n) =>
      `Le compilateur a rapporté **${n} erreur${n === 1 ? '' : 's'}**. Demandez-moi d’« analyser mon projet et corriger les problèmes de build » et je lancerai toute la chaîne de réparation.`,
    retryNote: 'Vous pouvez relancer la commande depuis la carte d’activité, ou me demander d’enquêter.',
  },

  chat: {
    gatherTitle: 'Collecte du contexte',
    gatherDesc: 'Analyse des connaissances indexées à la recherche d’éléments pertinents…',
    found: (n) => `${n} référence${n === 1 ? '' : 's'} pertinente${n === 1 ? '' : 's'} trouvée${n === 1 ? '' : 's'}`,
    noneNeeded: 'aucune référence de domaine nécessaire',
    greeting: [
      `Bonjour — je suis **Usman**, un atelier IA observable. Chaque outil que j’exécute apparaît en direct dans la chronologie d’activité au-dessus de mes réponses : vous me voyez travailler au lieu d’attendre devant un spinner.`,
      '',
      'Essayez l’une de ces demandes pour voir toute la chaîne d’exécution :',
      '',
      '- « Analyse mon projet et corrige les problèmes de build » — scan du dépôt, build en échec, vraies corrections, tests',
      '- « Recherche sur le web : les derniers modèles de raisonnement IA » — recherche, lecture des sources, synthèse citée',
      '- « Exécute npm run build » — exécution terminal réelle avec codes de sortie',
      '- « Calcule (128 × 46 + 1024) ^ 2 » — le moteur arithmétique exact',
    ].join('\n'),
    caps: [
      'Mon moteur est relié à un ensemble d’outils réels et inspectables. Rien n’est simulé côté interface — si une carte apparaît dans la chronologie, l’opération s’est réellement exécutée sur l’espace de travail :',
      '',
      '- **Recherche web + navigateur** — interroger un index documentaire, ouvrir les sources, les citer',
      '- **Terminal** — `npm run build`, `npm test`, `ls`, `cat`, `grep`, `wc` dans une vraie arborescence projet',
      '- **Outils fichiers** — scanner, lire, modifier ; mes corrections persistent entre les sessions',
      '- **Exécuteur de code** — JavaScript / TypeScript en bac à sable avec stdout capturé',
      '- **Calculatrice** — évaluation arithmétique exacte',
      '',
      'Demandez-moi de réparer le build, de rechercher un sujet, d’exécuter une commande ou du code — et regardez la chronologie.',
    ].join('\n'),
    hitsIntro: 'D’après les références de mon index :',
    strongest: (title, domain, excerpt) =>
      `La source la plus solide ici est « ${title} » (${domain}), qui indique que ${excerpt}. [1]`,
    deeperAsk: 'Voulez-vous une recherche plus approfondie, entièrement citée ? Dites « recherche sur le web : … » et j’ouvrirai les sources sous-jacentes.',
    fallback: [
      `J’ai lu votre message attentivement. En toute transparence : cet atelier fonctionne sur un **moteur d’exécution local** plutôt que sur un modèle web généraliste — je ne vais donc pas improviser une réponse que je ne peux pas assumer.`,
      '',
      'Voici ce que je peux réellement faire, chaque étape étant visible dans la chronologie :',
      '',
      '- **Réparer le projet fourni** — « analyse mon projet et corrige les problèmes de build »',
      '- **Rechercher les sujets couverts par mon index** — modèles IA, agents, coûts d’inférence, évaluations, UX des agents, architectures de streaming',
      '- **Exécuter de vraies commandes** — « exécute npm test », « exécute ls src », « exécute grep TODO src »',
      '- **Exécuter du code** — collez un bloc JavaScript/TypeScript et dites « exécute ce code »',
      '- **Arithmétique** — « calcule (2048 / 32) ^ 3 »',
      '',
      'Quelle chaîne dois-je lancer ?',
    ].join('\n'),
  },

  fixAnswer: (f) =>
    [
      `Le build échouait à cause de **${f.diagCount} erreurs TypeScript dans ${f.fileCount} fichiers**. Tout est corrigé — tests et build sont au vert.`,
      '',
      '### Causes racines',
      ...f.diags.map((d) => `- \`${d.file}:${d.line}\` — ${d.message} (${d.code})`),
      '',
      '### Modifications apportées',
      ...f.fixedFiles.map((x) => `- \`${x.path}\` — ${x.summary} *(+${x.added} / −${x.removed} lignes)*`),
      '',
      '### Vérification',
      `- \`npm test\` — **${f.testPassed}/${f.testTotal} tests réussis** dans ${f.suites} suites`,
      `- \`npm run build\` — ${f.buildLine.replace('✓ ', '')}`,
      '',
      'L’état du dépôt a été persisté : le projet compilera proprement désormais.',
    ].join('\n'),

  fixGreenAnswer: (f) =>
    [
      `Bonne nouvelle — j’ai inspecté le projet et **le build est déjà au vert**. Rien à corriger.`,
      '',
      '### Ce que j’ai vérifié',
      `- Scan du dépôt — ${f.files} fichiers, ${f.lines} lignes`,
      `- Dépendances — ${f.depCount} déclarées, TypeScript strict activé`,
      '- `npm run build` — code de sortie 0',
      `- \`npm test\` — **${f.testPassed}/${f.testTotal} tests réussis**`,
      '',
      'Si vous cassez quelque chose exprès, redemandez-moi de réparer et regardez la chaîne de réparation tourner.',
    ].join('\n'),
};

export function agentStrings(lang: Lang): AgentDict {
  return lang === 'fr' ? FR : EN;
}
