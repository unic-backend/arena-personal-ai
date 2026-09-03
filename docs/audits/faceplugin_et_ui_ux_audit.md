# Faceplugin et UI/UX Pro Max — deux capacités, deux régimes de licence

*Intégrés le 03/09/2026. Mesures faites sur les dépôts officiels ce jour-là.*

Deux moteurs externes rejoignent ARENA. Ils suivent la même architecture — la
seule qui existe ici pour un moteur externe — mais **pour deux raisons
opposées**, et c'est le point qui mérite d'être écrit.

---

## Faceplugin — analyse de visages

| | |
|---|---|
| **Capacité** | `faceplugin` — service `biometrie_visage` |
| **Rôle** | Compter et situer les visages, placer leurs repères, extraire un gabarit, comparer deux visages |
| **Dépôt** | `github.com/Faceplugin-ltd/Open-Source-Face-Recognition-SDK` |
| **Licence** | **aucune** — voir ci-dessous |
| **Dépendances** | torch 2.4.1, torchvision, opencv, numpy, pillow (≈ 1,1 Go dans SON environnement) |
| **Installation** | `scripts/installer_faceplugin.ps1` |
| **Emplacement** | `tools/vision/faceplugin/` — hors du dépôt |

### La licence, et pourquoi elle décide de tout

**Le dépôt ne contient aucun fichier `LICENSE`.** Son README affiche un badge
« License: Open Source » et la phrase « Completely Free: Open source with no
licensing fees ». Ni l'un ni l'autre ne concède quoi que ce soit en droit : un
badge n'est pas une licence, et « gratuit » ne dit rien du droit de copier ou
de redistribuer.

Sans licence explicite, le régime par défaut est **tous droits réservés**.
Faire entrer ce source dans un dépôt public (DEC-0039) serait indéfendable. Le
moteur reste donc dehors, comme VoiceStudio (DEC-0027) et Xaar Kaname, et
ARENA lui parle par un **processus séparé**.

### Ce qu'il sait faire, et rien de plus

L'API réelle, relevée dans son `run.py` :

```
GetImageInfo(image, faceMaxCount) -> count, bboxes, bscores, landmarks, alignimgs, features
get_similarity(feat1, feat2)      -> (sum(f1 * f2) + 1) * 50
```

Quatre capacités en découlent, et aucune fonction n'est inventée :

| Capacité | Action | Ce qu'elle rend |
|---|---|---|
| `detecter` | `read` | nombre, boîtes, scores |
| `reperes` | `read` | 68 points par visage (136 valeurs) |
| `caracteristiques` | `biometrie` | vecteur de 256 dimensions |
| `comparer` | `biometrie` | score 0–100 |

### Biométrie : ce qui est verrouillé

**La frontière est l'identité.** Compter des visages et placer des repères ne
disent pas *qui* : ce sont des lectures. Extraire un gabarit et comparer deux
visages produisent une donnée qui identifie une personne — ces deux-là
demandent l'accord du propriétaire à chaque appel
(`config/permissions_services.yaml`, `biometrie_visage.biometrie:
CONFIRMATION`, risque `HIGH`).

Quatre garanties, tenues par la structure et pas par une intention :

- **Aucune base de visages**, et rien pour en constituer une. `comparer` exige
  les deux images dans le même appel : il n'y a rien à interroger.
- **Aucun enregistrement biométrique implicite** : rien n'est écrit sur le
  disque, le gabarit ne vit que dans la réponse.
- **`detecter` ne ramène jamais de caractéristiques**, même si le moteur les a
  calculées dans la même passe. Les faire voyager « au cas où » ferait
  circuler de la biométrie à chaque comptage.
- **Rien en arrière-plan** : chaque capacité est déclenchée par une demande.

### Limites mesurées

- Un visage sans licence ne s'utilise pas commercialement sans vérifier auprès
  de l'éditeur. Le dépôt propose un SDK commercial séparé.
- Le moteur tourne sur processeur ici ; le SDK n'expose pas de bascule GPU
  dans cette version, donc **il n'entre pas dans le mécanisme de verrouillage
  GPU** — il n'y aurait rien à verrouiller.
- Le SDK écrit `priors nums:4420` sur la sortie standard. Le pont d'ARENA
  préfixe donc sa réponse d'un marqueur : sans lui, ce bavardage était lu
  comme du JSON cassé et une mesure réussie se rapportait en panne.

### Exemple

```
« analyse ces visages »            -> detecter, sans confirmation
« compare ces deux visages »       -> comparer, confirmation demandée
```

---

## UI/UX Pro Max — intelligence de design

| | |
|---|---|
| **Capacité** | `ui_ux_pro_max` — service `design_ui` |
| **Rôle** | Chercher styles, palettes, typographies, règles UX ; composer un design system |
| **Dépôt** | `github.com/nextlevelbuilder/ui-ux-pro-max-skill` |
| **Licence** | **MIT** — Copyright (c) 2024 Next Level Builder |
| **Dépendances** | aucune (Python pur, bibliothèque standard) |
| **Installation** | `scripts/installer_ui_ux_pro_max.ps1` |
| **Emplacement** | `tools/design/ui_ux_pro_max/` — hors du dépôt |

### Pourquoi il reste dehors alors que MIT l'autoriserait

Rien n'interdirait de le versionner. Il reste dehors **par convention** : tout
moteur externe vit à côté d'ARENA ici, et une seule règle vaut mieux que deux
règles selon la licence — c'est la seconde qu'on oublie d'appliquer. Sa notice
MIT voyage avec son code, dans son propre `LICENSE`, jamais séparée de lui.

### Ce qu'il expose

Son moteur de recherche n'est **pas réécrit** : `search.py --json` est appelé
tel quel. Dupliquer son classement BM25 dans ARENA ferait deux résultats
possibles pour la même question.

- `chercher` — 12 domaines : `style`, `color`, `chart`, `landing`, `product`,
  `ux`, `typography`, `icons`, `gsap`, `react`, `web`, `google-fonts`
- `design_system` — un système complet (style, couleurs, typographie, motifs)

### Lecture seule, délibérément

Le moteur sait persister un design system sur le disque (`--persist`). **Cette
option n'est pas exposée.** Une capacité de raisonnement qui demanderait des
droits d'écriture « au cas où » élargirait les permissions sans usage. C'est
aussi une capacité CPU : elle n'entre pas dans le groupe GPU.

### Limites mesurées

- **Ses données sont en anglais.** « accessibilité formulaire » rend zéro
  résultat là où « form validation » en rend deux. Le connecteur le dit dans
  sa réponse au lieu de laisser un zéro muet passer pour « il n'existe rien
  sur ce sujet ».
- Le seuil BM25 refuse les requêtes trop éloignées d'un domaine — c'est
  voulu : mieux vaut zéro résultat qu'un résultat hors sujet.

### Exemple

```
« quelle palette pour cette application ? »  -> chercher
« génère un design system »                  -> design_system
```

---

## Ce que le dépôt porte, et ce qu'il ne porte pas

Pour chacun : le connecteur, ses tests, son installeur — et pour Faceplugin un
**pont** (`core/connectors/ponts/faceplugin_pont.py`), du code ARENA qui
importe le SDK à l'exécution sans en copier une ligne.

Jamais le moteur. `tests/test_moteurs_externes_restent_dehors.py` le mesure
pour les sept moteurs externes au lieu de le croire sur parole.
