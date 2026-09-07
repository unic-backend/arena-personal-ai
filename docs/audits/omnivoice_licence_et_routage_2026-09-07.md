# OmniVoice — audit d'intégration et défaut de licence (07/09/2026)

*Chaque valeur de ce document a été **mesurée dans la session qui l'écrit**.
Ce qui n'a pas pu l'être porte `UNKNOWN` et dit pourquoi.*

| | |
|---|---|
| Sources lues | dépôt k2-fsa/OmniVoice (commit `08be0b4`) et VoiceStudio (commit `53ff367`), clonés et lus |
| Machine | conteneur cloud de l'assistant — **pas son PC** |
| GPU | **aucun** (`nvidia-smi` absent) · `torch` non installé · `ffprobe` absent |
| VoiceStudio | **absent** de cette machine |
| huggingface.co | **bloqué** (mesuré : `curl` code 000, WebFetch `EGRESS_BLOCKED`) |

---

## 1. Le défaut trouvé, en une phrase

**Le moteur par défaut d'ARENA allait devenir un modèle dont la licence
interdit l'usage commercial, en silence, sur les vidéos d'une entreprise.**

Trois faits mesurés, qui ne se recoupent qu'une fois mis côte à côte :

1. Le registre TTS de VoiceStudio est un dictionnaire **ordonné** dont
   `omnivoice` est la **première** entrée, et son énumération suit cet ordre
   (fichier `tts_backend.py`, ligne 2260, commit `53ff367`).
2. ARENA prenait `disponibles[0]` — *« le premier que le service déclare
   disponible »*.
3. Les **poids** d'OmniVoice sont **CC-BY-NC**. Son dépôt ne porte qu'un
   `LICENSE` Apache-2.0, qui couvre le **code**, et **aucune mention** de la
   licence des poids.

Et le déclencheur était écrit par ARENA elle-même : `docs/COMMANDES_PC.md`
lui disait, depuis DEC-0065, de faire `git pull && uv sync` chez VoiceStudio
— exactement la commande qui rend le paquet présent, donc le moteur
disponible, donc premier.

---

## 2. La licence : ce qui a été vérifié, et où

DEC-0065 avait laissé ce point `UNKNOWN` faute d'atteindre Hugging Face. Il
l'est resté ici — mais une **source primaire atteignable** existe, et elle
tranche. Le fichier `LICENSE-NOTICE.md` de VoiceStudio, lu sur cette machine :

> *« Downloaded model weights are not relicensed by VoiceStudio. The default
> k2-fsa/OmniVoice model card identifies its code as Apache-2.0 and pretrained
> weights as CC-BY-NC. Its audio tokenizer LICENSE contains separate Boson
> Higgs Audio 2 and Meta Llama community terms. »*

Son `README.md` porte la même chose dans une colonne « License » par moteur,
et c'est de ce tableau que vient la table de `core/audio/routage_tts.py`.

**Trois licences, pas une**, et c'est le piège :

| Objet | Licence | Ce qu'elle gouverne |
|---|---|---|
| Code OmniVoice | Apache-2.0 (vérifié dans son `LICENSE`) | le programme |
| **Poids pré-entraînés** | **CC-BY-NC** | **l'audio produit** ← celle qui compte |
| Tokenizer audio (`eustlb/higgs-audio-v2-tokenizer`, tiers) | termes Boson Higgs Audio 2 + Meta Llama | l'audio produit aussi |
| Application VoiceStudio | AGPL-3.0 | le service, jamais l'audio |

Lire le seul dépôt d'OmniVoice menait donc à la conclusion fausse
— « Apache-2.0, donc libre pour le commerce » — que la mission demandait
explicitement de ne pas tirer.

`UNKNOWN` assumé : la fiche Hugging Face elle-même n'a pas été lue ici. Deux
sources indépendantes la citent (VoiceStudio, et le propriétaire dans sa
mission) ; aucune n'est la fiche.

---

## 3. Le correctif : un seul routeur, qui connaît les licences

`core/audio/routage_tts.py`. Parler **et** cloner y passent tous les deux —
c'est le « un seul routeur TTS » que la mission demande, et il n'y en avait
pas : le connecteur portait deux fonctions de choix distinctes.

**Sa règle de partage, qui est le cœur du module :**

- **Ce que la machine sait mesurer, on le lui demande** à chaque appel :
  disponibilité, `supports_cloning`, `effective_device`, `routing_status`.
- **Ce qu'aucune API n'expose, et seulement cela, vit dans la table** : la
  licence des poids et le support de `instruct`. Chaque entrée porte sa
  source et sa date ; un test vérifie qu'elle en porte une.

**Ce qu'il fait :**

| Situation | Avant | Maintenant |
|---|---|---|
| `omnivoice` seul disponible, travail d'UniC | il parle | **refus** nommant la licence, **aucun fichier écrit**, et le message dit les deux sorties possibles |
| `omnivoice` + `cosyvoice` | `omnivoice` (premier) | `cosyvoice` (licence établie) |
| `omnivoice` nommé explicitement | il parle | **refus** — nommer un moteur n'ouvre aucune porte |
| Usage `recherche` déclaré | (n'existait pas) | `omnivoice` parle : la licence interdit le commerce, pas l'essai |
| Licence inconnue vs licence établie | premier arrivé | l'établie d'abord ; l'inconnue reste utilisable faute de mieux, et le dit |
| Deux moteurs également licenciés | premier arrivé | celui qui est **réellement accéléré** (`routing_status`) |

**L'usage par défaut est commercial.** Se tromper dans ce sens coûte une gêne
(déclarer `usage="recherche"`) ; dans l'autre, des vidéos commerciales faites
avec un modèle qui l'interdit, sans que rien ne le dise.

Un `usage` mal orthographié est **refusé**, jamais ramené au défaut : le
ramener silencieusement choisirait à sa place, et dans le seul sens qui coûte.

---

## 4. La matrice demandée — ce qu'OmniVoice sait faire *et* ce qu'ARENA expose

`OPERATIONNEL` n'est écrit que là où une mesure existe. Rien ici n'a pu être
mesuré sur un vrai moteur : **aucun `OPERATIONNEL` n'est donc affirmé sur
l'audio**, et c'est le résultat correct, pas un manque de travail.

| Capacité annoncée par OmniVoice | Exposée par ARENA ? | Statut ici | Pourquoi |
|---|---|---|---|
| Synthèse multilingue (« over 600 languages », son `README.md`) | oui — `langue` transmis | **NON MESURÉ** | aucun moteur sur cette machine. Le nombre 600 est **repris, pas vérifié** |
| Voice cloning | oui — capacité `cloner`, risque HIGH, autorisation exigée dans le code | **NON MESURÉ** | idem |
| Voice design (`instruct`) | oui — transmis tel quel, et le routeur choisit désormais un moteur qui l'honore | **NON MESURÉ** | idem |
| Genre, âge, hauteur, accent, dialecte | **PARTIEL** | — | ce sont des mots **dans** `instruct`, pas des paramètres validés. ARENA ne peut ni vérifier ni garantir qu'ils sont honorés |
| Chuchotement, symboles non verbaux | **PARTIEL** | — | même chose : du texte libre dans `instruct` |
| Correction de prononciation | **DORMANT** | — | aucun champ d'ARENA ne l'atteint |
| Génération rapide (RTF) | non exposée comme réglage | **NON MESURÉ** | `scripts/verifier_voix.py` la mesure sur sa machine |
| API Python | oui, via le connecteur | **OPERATIONNEL** | 51 tests |
| CLI | **absente, et c'est voulu** | — | ARENA n'a pas de CLI vocale ; en ajouter une ferait un second chemin |
| Appareil réellement utilisé | **oui, désormais** | **OPERATIONNEL** | `effective_device` et `routing_status` lus et rapportés — ARENA les recevait et les jetait |

### Langues

**Aucune langue n'est déclarée opérationnelle.** `scripts/verifier_voix.py`
mesure français, anglais et **wolof** sur sa machine, une ligne par langue,
avec la durée, la cadence, l'amplitude et le RTF réels. Le wolof y est parce
que c'est la langue de ses chantiers — **pas** parce qu'on suppose qu'il
marche : c'est précisément ce que la commande sert à savoir.

---

## 5. Anti-duplication : ce qui n'a pas été créé

| Tentation | Ce qui a été fait |
|---|---|
| Cloner OmniVoice dans ARENA | **non.** Un test le tient déjà (`tests/test_moteurs_externes_restent_dehors.py`) |
| Télécharger les poids | **non.** Rien ne le justifie tant que la licence bloque l'usage principal |
| Un second système TTS | **non.** Le connecteur existant a été *rétréci* : deux fonctions de choix sont devenues une |
| Un second chemin pour la vidéo | **non.** La narration passe déjà par cet agent, donc par ce routeur — vérifié par un test, pas affirmé |

**KrillinAI garde son propre TTS** (doublage d'une vidéo existante, DEC-0049),
et c'est une frontière assumée, pas un oubli : il ne synthétise jamais de
novo et n'accepte aucun clonage. Deux processus externes, une seule voie de
*synthèse* côté ARENA.

---

## 6. Ce qui attend sa machine

```
python scripts/doctor.py            # dit maintenant si un moteur est écarté pour licence
python scripts/verifier_voix.py     # la chaîne réelle, mesurée, langue par langue
```

`verifier_voix.py` passe **par ARENA** (le connecteur et son routeur), jamais
par VoiceStudio en direct — sinon il mesurerait VoiceStudio. Il vérifie
physiquement chaque fichier produit : existence, taille, durée, cadence,
lisibilité, **et amplitude**. Un WAV de la bonne durée et parfaitement
silencieux est un échec, et seule l'amplitude l'attrape.

Lancé ici, il rend `NOT_CONFIGURED` et s'arrête. C'est le bon résultat.

`UNKNOWN` sur cette machine, et qui le reste : temps de chargement du modèle,
RTF réel, VRAM, RAM, repli GPU→CPU sous contrainte, qualité audio, langues,
clonage, voice design, doublage vidéo bout en bout.

---

## 7. Ce qui reste à décider par lui

1. **Installer un moteur à licence permissive** côté VoiceStudio —
   `cosyvoice` (Apache-2.0, clonage *et* `instruct`) est le remplaçant le plus
   proche d'OmniVoice pour un usage commercial. Sans lui, ARENA refusera de
   parler pour UniC dès qu'OmniVoice sera le seul installé.
2. **Ou vérifier lui-même la fiche Hugging Face** depuis sa machine : si les
   poids y étaient re-licenciés, une ligne de la table suffirait à rouvrir la
   porte — avec sa source et sa date, comme les autres.
3. **Ou acheter une licence commerciale** auprès des auteurs, si elle existe.

Ce qui ne se négocie pas : tant que la mesure dit CC-BY-NC, ARENA ne s'en
sert pas pour son commerce, et ne le contourne pas.
