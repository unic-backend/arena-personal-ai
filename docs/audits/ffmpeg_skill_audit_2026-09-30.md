# Audit de `kajisho5/ffmpeg-skill` — 30 septembre 2026

## Portée et provenance

Dépôt officiel audité : <https://github.com/kajisho5/ffmpeg-skill>, commit
`df5d2736b171473742b86789e5179bdfb0976373`, version npm 2.3.1. Fichiers lus :
README, SKILL, AGENTS, licence, décisions, contrat, références, 42 scripts,
gabarits, MCP, tests et évaluations. Licence : MIT. Les scripts n'utilisent que
la bibliothèque standard Python et les binaires système `ffmpeg`/`ffprobe ; le
paquet npm ne sert qu'à installer le skill. Whisper local, fontes et filtres
FFmpeg particuliers sont optionnels selon l'opération. Aucun binaire, média,
gabarit, jeu d'évaluation ou code source amont n'a été importé dans ARENA.

## Audit d'ARENA avant modification

Surfaces examinées : `tools/video`, `tools/audio`, `core/connectors`,
`core/production`, `core/montage`, agents vidéo/analyse/sous-titres/éditeur,
routeurs media et production, PWA, persistance/reprise, permissions, sécurité,
tests, CI, dépendances, skills et ADR/documentation vidéo.

ARENA possédait déjà :

- un unique `FFmpegTool` avec conversion, coupe, extraction audio et burn ASS/SRT ;
- recadrage vertical 9:16 avec fond flou et vérification ffprobe ;
- génération ASS dynamique et transcription ;
- une timeline structurée (`core/montage`) avec pistes vidéo/image/audio/texte,
  coupe, mix, overlays, rendu et contrôle de durée/dimensions ;
- analyse vidéo, sélection d'extraits, montage et orchestrateur de production ;
- upload borné en taille, noms sûrs, frontière `MEDIA_DIR`, permissions et débit ;
- journal durable des projets, reprise et vérification des artefacts ;
- routes et PWA vidéo existantes ;
- connecteurs spécialisés (KrillinAI, Drift, VectCut, Agnes, Hyperframes) ;
- tests réels FFmpeg marqués `integration` et CI installant FFmpeg.

L'audit a aussi identifié des incohérences : le probe était dupliqué et peu
riche ; les méthodes historiques de `FFmpegTool` validaient inégalement les
sorties ; il n'existait pas de contrat structuré commun `inspect → plan →
execute → verify`, de dry-run central, ni de profils de livraison locaux.

## Décision d'intégration

### Concepts retenus et adaptés

- probe structuré avant/après traitement ;
- opérations fermées et arguments `subprocess` sous forme de liste ;
- plan lisible et dry-run sans exécution ;
- délai maximal ;
- staging dans le répertoire de destination puis publication atomique ;
- refus d'écraser source ou sortie existante ;
- vérification des flux et des propriétés demandées ;
- erreurs structurées, notamment `NOT_CONFIGURED` ;
- profils YouTube, Shorts, Reels, TikTok, X, LinkedIn et Facebook.

Ces concepts ont été implémentés dans **le `FFmpegTool` existant**, pas dans un
second moteur. Le résultat structuré expose uniquement les mesures ffprobe :
durée, dimensions, fps, codecs, canaux, taille et contrôles de vérification.

### Capacités ajoutées

Le contrat structuré prend en charge : coupe précise, resize, fit pad/crop/fond
flou, rotation, miroir, reverse, vitesse (avec chaîne `atempo` sûre),
normalisation EBU R128, extraction audio et exports par profil. Les anciens
appels booléens restent compatibles et sont désormais re-sondés.

### Délibérément non importé

- scripts CLI/MCP et architecture Agent Skill : concurrenceraient agents,
  connecteurs et routeurs ARENA ;
- renderer de projet amont : `core/montage` et le journal ARENA existent déjà ;
- sous-titres/transcription amont : systèmes ARENA déjà en place ;
- assets, GIF, démos, évaluations et templates JSON ;
- wrappers de probe, sécurité, output lock et job system amont en tant que code ;
- stabilisation, HDR/Dolby Vision, LUT, scènes/highlights, silence intelligent,
  sync/multicam et captions avancées : utiles mais nécessitent des contrats et
  tests dédiés ; les annoncer maintenant serait trompeur ;
- dépendances ou services cloud : aucun ajouté.

Le code amont est sophistiqué mais fortement couplé à son état global CLI,
`argparse`, protocole JSON/MCP et composition entre scripts. Copier ce graphe
aurait créé précisément le second moteur interdit par la mission.

## Sécurité et limites

La nouvelle API exige `media_root` et résout entrée et sortie à l'intérieur de
cette racine (le routeur lui transmet `MEDIA_DIR`). Elle refuse les opérations
inconnues, les valeurs non finies/hors bornes, les filtergraphs libres,
l'écrasement de source et les sorties préexistantes. Elle n'utilise ni shell ni
texte naturel. Les temporaires sont supprimés sur succès, erreur, timeout,
sortie vide ou corrompue. Les méthodes historiques restent disponibles pour
leurs consommateurs internes ; elles ne constituent pas la frontière API.

Le moteur reste CPU/local et dépend des encodeurs/filtres de la build FFmpeg.
Il ne garantit pas Dolby Vision ou GPU. Les profils sont des profils techniques
ARENA, pas une promesse immuable sur les règles des plateformes. Les tests
réels sont sautés quand FFmpeg/ffprobe manquent.
