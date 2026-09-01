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
