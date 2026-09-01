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
