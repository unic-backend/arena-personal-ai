# Origines externes — ARENA

Ce que ce dépôt doit à d'autres projets, et à quel titre. Ce fichier existe
pour qu'aucune dette d'attribution ne repose sur la mémoire de quelqu'un.

---

## OpenCut — modèle de projet vidéo

`core/montage/projet.py` **suit le modèle de données** d'OpenCut classic
(`apps/web/src/timeline/types.ts`) : la séparation projet → pistes → éléments,
un type d'élément par type de piste, et le décalage de coupe porté par
l'élément plutôt que par le média.

- Projet : OpenCut — https://github.com/OpenCut-app/OpenCut
- Licence : **MIT**, « Copyright 2025-2026 OpenCut »

**Aucun code n'a été copié.** L'implémentation est écrite en Python contre
l'architecture d'ARENA (connecteurs, permissions, résultats vérifiés) ; c'est
la conception qui est reprise, pas le source. La licence MIT n'impose son avis
qu'aux copies substantielles — l'attribution est donnée ici parce qu'elle est
due intellectuellement, pas parce qu'un texte l'exige.

**Ce qui n'a PAS été repris, et pourquoi** : le moteur de rendu d'OpenCut est
natif navigateur (`CanvasRenderer`, WebCodecs, `mediabunny`) et n'a aucun
chemin sans interface. ARENA rend avec `ffmpeg`, derrière une frontière
remplaçable (`core/montage/rendu.py`). Détail mesuré →
`docs/audits/opencut_audit.md`.

**`mediabunny` (MPL-2.0) n'est pas utilisé.** Sa licence est un copyleft faible
au fichier, et le dépôt principal d'OpenCut laisse croire qu'elle est MIT. Si
elle entre un jour ici, ce sera telle quelle : modifier ses fichiers
obligerait à publier ces modifications.


---

## VoiceStudio — capacités audio, pilotées à distance

ARENA sait parler et transcrire en pilotant **VoiceStudio** par HTTP sur la
boucle locale (`core/connectors/audio_voix.py`).

- Projet : VoiceStudio — https://github.com/debpalash/VoiceStudio
- Licence : **AGPL-3.0-only**, « Copyright 2024-present Palash Debnath and
  VoiceStudio contributors »
- Version auditée : `0.5.1`, commit `a30b7166` (30/08/2026)

**Aucune ligne de VoiceStudio n'est présente dans ce dépôt**, et c'est une
décision juridique : `LICENSE` d'ARENA est « All rights reserved », l'AGPL
imposerait à toute œuvre dérivée d'être publiée sous AGPL. VoiceStudio tourne
comme **processus séparé**, dans son propre environnement, et n'est ni copié,
ni modifié, ni importé. Raisonnement complet →
`docs/audits/voicestudio_audit.md`.

Les modèles réellement utilisés à travers lui portent leurs propres licences :
`kittentts` 0.8.1 (Apache-2.0, KittenML), `faster-whisper` (MIT) et
`Systran/faster-whisper-base` (MIT). Aucun n'est redistribué ici.

### La licence d'un modèle n'est pas celle de son code (DEC-0069)

Vérifié le 07/09/2026 sur le fichier de licences de VoiceStudio (commit
`53ff367`) et sur le dépôt d'OmniVoice (commit `08be0b4`), tous deux lus, pas
supposés :

| | Licence | Ce qu'elle gouverne |
|---|---|---|
| Code d'OmniVoice | Apache-2.0 (son propre fichier de licence) | le programme |
| **Poids pré-entraînés d'OmniVoice** | **CC-BY-NC** | **l'audio produit** |
| Tokenizer audio (modèle tiers, dérivé de Higgs Audio v2) | termes Boson Higgs Audio 2 + Meta Llama | l'audio produit |
| Application VoiceStudio | AGPL-3.0-only | le service, jamais l'audio |

Le dépôt d'OmniVoice ne porte **qu'un** fichier de licence Apache-2.0, qui
couvre le code, et aucune mention de la licence des poids : le lire seul mène
à la conclusion fausse « Apache-2.0, donc libre pour le commerce ».

ARENA ne redistribue aucun de ces poids et n'en télécharge aucun. Son routeur
de voix (`core/audio/routage_tts.py`) refuse d'employer un modèle marqué non
commercial pour un travail commercial, et porte la source de chaque
affirmation de licence de sa table. Détail →
`docs/audits/omnivoice_licence_et_routage_2026-09-07.md`.


---

## Agency Agents — taxonomie et listes de contrôle par métier

`core/specialistes/catalogue.py` reprend la **méthode** de plusieurs métiers
telle que ce dépôt la formule : les taxonomies de spécialités, les listes de
contrôle par domaine (STRIDE et OWASP pour la sécurité, la pyramide de tests,
les contrôles de référencement local), et l'idée qu'un spécialiste porte sa
propre définition de « fini ».

- Projet : Agency Agents — https://github.com/msitarzewski/agency-agents
- Licence : **MIT**, « Copyright (c) 2025 AgentLand Contributors »
- Version auditée : commit `3c958888` (26/08/2026)

**Aucune de ses 319 définitions n'a été copiée.** Ce sont des prompts de rôle
d'environ 230 lignes chacun (« tu es X, stratégique et rigoureux ») ; ARENA
reste UNE intelligence et n'avait aucun besoin de 319 personnalités. Ce qui a
été repris est la substance : les étapes et les contrôles, réécrits en
français, réduits à ce qui se vérifie, et reliés à des chemins d'exécution qui
existaient déjà dans ARENA.

Raisonnement complet → `docs/DECISIONS.md`, DEC-0028.

---

## Lean 4 et le dépôt Fermat — la vérification formelle

`core/connectors/lean_formel.py` pilote **Lean 4** comme processus séparé.

- Moteur : Lean 4 — https://github.com/leanprover/lean4
- Licence : **Apache-2.0**
- Version installée : `v4.33.1` — celle qu'épingle le `lean-toolchain` du
  dépôt Fermat ci-dessous, pour que ce qui est vérifié ici le soit avec le
  même compilateur.
- **Aucune ligne de Lean n'est copiée dans ce dépôt.** Le toolchain vit hors
  du dépôt (2,9 Go), et sa licence voyage avec lui.

De `anthropics/fermats-last-theorem` (Apache-2.0, « Copyright 2026 Anthropic,
PBC », étudié le 07/09/2026), ARENA reprend **une discipline, pas du code** :
son `FinalCheck.lean` n'accepte son théorème qu'après avoir imprimé la liste
de ses axiomes et l'avoir comparée aux trois axiomes de la logique de Lean.

C'est ce contrôle-là qui est ici, et il est nécessaire : une preuve trouée
(`sorry`) **compile avec le code de sortie 0**. Sans lire les axiomes, ARENA
aurait déclaré vérifiée une démonstration vide.

**Ce qui n'a PAS été repris** : la formalisation de Fermat elle-même (des
milliers de fichiers Lean), Mathlib, le comparateur, et l'environnement de
compilation d'Anthropic (96 tâches parallèles, ~153 Go de RAM). Rien de tout
cela n'a d'usage sur la machine du propriétaire, et rien n'en a été copié.

Raisonnement complet → `docs/DECISIONS.md`, DEC-0067.

---

## Pascal Editor — le moteur d'architecture 3D, piloté à distance

ARENA sait construire un bâtiment en pilotant **Pascal Editor** par MCP sur
l'entrée/sortie standard d'un processus séparé
(`core/architecture/backend_pascal.py`).

- Projet : Pascal Editor — https://github.com/pascalorg/editor
- Licence : **MIT**, « Copyright (c) 2026 Pascal Group Inc. »
- Version auditée : dépôt au commit `505013b` ; paquets installés
  `@pascal-app/mcp` 1.0.0-beta.6 et `@pascal-app/core` 1.0.0-beta.5, tous
  deux `"license": "MIT"` dans leurs manifestes (lus le 07/09/2026)

**Aucune ligne de Pascal n'est présente dans ce dépôt.** MIT n'aurait rien
interdit : il reste dehors parce que son arbre npm pèse 205 Mo et qu'ARENA
est un projet Python. Ce que le dépôt porte est à lui : la capacité
(`core/architecture/`), son connecteur, ses tests, et la liste épinglée de ce
qu'il faut installer (`core/architecture/paquets.json`).

Le serveur MCP tourne **sans navigateur, sans WebGPU, sans React et sans base
de données** — vérifié dans son README et mesuré ici. Il exige **Bun** : son
paquet publié importe ses modules sans extension, ce que Node refuse
(DEC-0070). Bun est sous licence MIT.

`architecture_3d` est une capacité d'ARENA ; **Pascal en est une
implémentation**, remplaçable sans toucher aux appelants.
