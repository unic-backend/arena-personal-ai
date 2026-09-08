# Audit opérationnel profond — 07/09/2026

*Toutes les valeurs de ce document ont été **mesurées dans la session qui
l'écrit**. Ce qui n'a pas pu l'être porte `UNKNOWN` et dit pourquoi.*

| | |
|---|---|
| Commit audité | `ad9ae30` (fusion de la PR #171) |
| Machine | conteneur cloud de l'assistant — **pas le PC du propriétaire** |
| Python | 3.11.15 |
| Processeurs / RAM | 4 cœurs / 15 Go |
| GPU | **aucun** (`nvidia-smi` absent) |
| Disque | 20 Go libres sur 252 |

**La limite qui conditionne tout le reste** : Ollama, ffmpeg, Tesseract,
Docker et tous les moteurs externes (VoiceStudio, WanGP, MoneyPrinterTurbo,
OpenTakeoff, Xaar Kaname, Faceplugin) sont **absents de cette machine**. Ce
qui en dépend n'est donc pas jugé « cassé » : il est jugé sur sa capacité à
le **dire honnêtement** plutôt qu'à inventer un résultat. Les mesures qui
exigent son PC sont marquées `ATTEND SON PC`.

---

## 1. Ce qui a été trouvé — résumé

| # | Défaut | Gravité | État |
|---|---|---|---|
| 1 | **6 connecteurs sur 29 injoignables** — enregistrés, testés, diagnostiqués, appelés par rien | HAUTE | 1 corrigé, 5 documentés + garde-fou |
| 2 | Quatre agents lèvent une exception brute quand aucun modèle ne répond | BASSE | Observé, non corrigé (voir §6) |

Et **trois fois de suite**, un test écrit pendant cet audit est passé au vert
sur un sabotage réel avant d'être corrigé (§5). C'est le résultat le plus
utile de la journée, et il ne concerne pas le code d'ARENA mais la manière de
le vérifier.

---

## 2. Cartographie mesurée

| Composant | Compte | Mesure |
|---|---|---|
| Intentions déclarées | 25 | `INTENTIONS` de l'orchestrateur |
| Intentions aiguillées | 24 + `CHAT` (repli) | `chat.py` |
| Intentions atteignables par mots-clés | 25 | seul classificateur sans Ollama |
| Agents instanciés | 23 | `runtime.py` |
| Agents atteignables | **23 / 23** | passerelles + `media.py` + STUDIO |
| Connecteurs enregistrés | 29 | registre réel |
| Connecteurs appelés par du code | **24 / 29** | analyse AST (§3) |
| Modules | 210, dont 167 atteints | `scripts/orphelins.py` |
| Vérifications du diagnostic | 28 (6 `[OK]` ici) | `scripts/doctor.py` |
| Tests | **4030 passés, 25 sautés** | `pytest tests/ -q` |

**Aucune intention orpheline, aucun agent injoignable, aucun module réel
endormi.** Le défaut est ailleurs.

---

## 3. Défaut n°1 — six connecteurs que rien n'atteint

`scripts/orphelins.py` ne pouvait pas les voir : leur fichier **est** importé
par `runtime.py`, donc jamais orphelin — alors qu'aucun appelant ne les
exécute jamais. C'est le même défaut que DEC-0061 (OpenViking) et DEC-0066
(clonage vocal), une troisième fois, et cette fois à l'échelle.

| Connecteur | Appelant réel | Verdict |
|---|---|---|
| `gitingest` | *aucun* → **`repo_engineer_agent.py:43`** | **CORRIGÉ** |
| `formbricks` | aucun | dormant, documenté |
| `galsen` | aucun | dormant, documenté |
| `graphify` | aucun | dormant, documenté |
| `txtai_search` | aucun | dormant, documenté |
| `workflow_guide` | aucun | dormant, documenté |

**Ce qui a été corrigé** : `RepoEngineerAgent` — l'agent qui analyse des
architectures — le faisait avec **30 lignes d'arborescence tronquée**,
pendant que `gitingest` (« transforme un dépôt en résumé, arbre et contenu »)
dormait. Il l'appelle désormais, avec repli honnête sur l'arborescence quand
la bibliothèque est absente, et le prompt **dit** ce qu'il a réellement lu
(`source : gitingest` ou `source : arborescence`).

**Ce qui n'a pas été corrigé, et pourquoi** : brancher les cinq autres
demande de choisir *où*, et ce choix appartient au propriétaire — un
connecteur de sondages ou de données publiques n'a pas d'emplacement évident.
Les câbler au jugé aurait créé des chemins que personne n'emprunte, c'est-à-dire
le même défaut sous une autre forme.

**Ce qui empêche la récidive** : `tests/test_connecteurs_dormants.py` mesure,
pour chaque connecteur enregistré, s'il est nommé en argument d'un appel
réel. Il échoue **dans les deux sens** — un connecteur neuf qui s'endort sans
être déclaré, et un dormant réveillé qu'on aurait oublié de sortir de la
liste. Chaque entrée porte sa raison, et un test vérifie qu'elle en porte une.

---

## 4. Ce qui a été testé, et ce que ça a donné

### Chaînes critiques

| Chaîne | Résultat mesuré |
|---|---|
| **A.** utilisateur → routeur → modèle → réponse | `HTTP 200`, `status=error`, « ❌ Ollama hors-ligne. » — dégradation honnête, aucune invention |
| **F.** action sensible → confirmation → exécution | `audio_voix.document` → `CONFIRMATION`/MEDIUM ; `cloner` → `CONFIRMATION`/HIGH ; `lean_formel.verifier` → `DENIED` (coupe-circuit) ; `email.settings` → `DENIED` |
| **Mémoire** : écrire → retrouver | `set_fact`/`get_fact` OK ; historique OK ; **fait absent → `None`**, jamais inventé |
| **Vérification formelle** (DEC-0067) | preuve valide → `VERIFIE` ; fausse → `REJETE` ; **trouée (`sorry`) → `REJETE` malgré le code de sortie 0** |
| **Authentification** | sans clé et mauvaise clé → `401`, aucune fuite |

### Agents exécutés réellement (Ollama absent)

Dix agents lancés sur une vraie phrase. Six se dégradent proprement
(`warning`/`error` avec la raison exacte : moteur absent, image manquante,
Gmail non connecté, coupe-circuit). Quatre lèvent une `RuntimeError` brute
— voir §6.

### Moteurs vidéo et audio — santé mesurée

`wan2gp`, `moneyprinter`, `krillinai`, `drift`, `xaar_kaname`, `audio`
répondent tous `NOT_CONFIGURED` **en nommant ce qui manque**. `montage`
répond `OPERATIONAL` en précisant lui-même que ffmpeg est absent, et un
rendu réel tenté sans ffmpeg rend `FAILED` — **aucun faux succès**.

`ATTEND SON PC` : la chaîne vidéo complète (ingestion → transcription →
narration → montage → export → `ffprobe` sur le fichier final) ne peut pas
être jouée ici. Elle l'a été le 01/09/2026 sur une machine où VoiceStudio
tournait (`docs/audits/voicestudio_audit.md`, §4 : MP4 `h264` 1080×1920 +
`aac`, amplitude 25892 vérifiée dans le fichier final).

### Sécurité

| Contrôle | Résultat |
|---|---|
| Secrets en dur dans le code | **aucun** |
| `shell=True` | **aucun** (une seule mention, dans un commentaire qui l'interdit) |
| Exceptions avalées | 4 `except: pass`, **toutes typées et légitimes** (normalisation de chemin, durée illisible, arrêt, nettoyage de fichier temporaire) |
| `TODO`/`FIXME`/placeholder/simulation en production | **aucun** |

---

## 5. Le vrai résultat de cet audit : trois tests verts sur du code sabordé

Le garde-fou du §3 a dû être réécrit **trois fois**, parce que chaque version
passait sur un sabotage réel :

1. **Par `grep`** — comptait les **commentaires**. Débrancher l'appel laissait
   le test vert : le mot restait dans la docstring juste au-dessus.
2. **Par AST, égalité exacte** — comptait une **étiquette d'affichage**
   (`return vu, "gitingest"`), qui n'appelle rien.
3. **Par AST, premier argument du registre** — déclarait mort
   `claude_context`, qui est bien appelé, mais **via une fonction
   intermédiaire**. Un faux « dormant » sur une capacité vivante aurait été
   pire que pas de garde-fou du tout.

La règle qui tient les trois : **le nom exact en argument d'un appel**.

C'est la troisième fois en deux jours qu'un test de ce dépôt passe pour la
mauvaise raison (filtre `supports_cloning`, sonde du navigateur, ici). Le
point commun : **le test remplaçait ou contournait ce qu'il prétendait
vérifier**. Seul le sabotage l'a montré, à chaque fois.

---

## 6. Défaut n°2 — quatre agents lèvent au lieu de rapporter

`plaquiste`, `coder`, `repo_engineer` et `swe` lèvent
`RuntimeError: Aucun fournisseur n'a pu repondre` quand aucun modèle ne
répond, là où `audio`, `email`, `vision`, `social`, `browser` et `formel`
rendent un statut avec la raison.

**Pourquoi ce n'est pas corrigé** : les deux points d'entrée réels s'en
protègent déjà, vérifié en exécution — `/api/chat` teste
`fast_provider.is_available()` avant tout et enveloppe le reste ;
`/agent/stream` passe par `chronometrer`, dont le code dit explicitement
qu'il attrape l'exception et la rend visible (défaut déjà corrigé le
31/08/2026). Le propriétaire reçoit donc un message propre, jamais une
erreur 500.

C'est une **incohérence de robustesse**, pas une panne visible. La corriger
touche quatre agents pour un gain nul sur les chemins réels : ce serait
élargir le risque sans mesurer de bénéfice. Signalée ici, pas maquillée.

---

## 7. Performances mesurées

| | |
|---|---|
| Import complet du runtime | 0,66 s |
| Vérification d'une preuve Lean | 0,97 s (970 ms côté Lean) |
| Sonde de santé Lean | 0,06 s |
| Suite de tests complète | 4030 tests en 148 s |

Aucun ralentissement anormal. `ATTEND SON PC` pour tout ce qui touche au GPU,
à la VRAM et aux temps d'inférence réels.

---

## 8. Verdict

**HEALTHY_WITH_WARNINGS.**

| | |
|---|---|
| Agents | **23 / 23** atteignables |
| Intentions | **25 / 25** aiguillées ou explicitement en repli |
| Connecteurs | **24 / 29** appelables — 5 dormants, documentés et gardés |
| Modules | 210, **aucun module réel endormi** |
| Chaînes critiques testables ici | **5 / 5** réussies |
| Tests | 4030 passés, 25 sautés, 0 échec |
| Défauts trouvés | 1 haut (corrigé + garde-fou), 1 bas (documenté) |

**Ce qui est réellement opérationnel aujourd'hui, sur cette machine** : le
routage, les permissions et confirmations, la mémoire, la vérification
formelle (Lean), l'authentification, et la dégradation honnête de tout ce qui
dépend d'un moteur absent.

**Ce qui attend son PC** : Ollama et les modèles, la chaîne vidéo de bout en
bout, la voix, le GPU. Rien de tout cela n'est déclaré opérationnel ici — et
`python scripts/doctor.py` le lui dira ligne par ligne, sur sa machine.

**Ce qui reste à décider par lui** : où brancher les cinq connecteurs
dormants, ou s'il faut les retirer. Tant qu'ils sont dans
`DORMANTS_CONNUS`, ils ne peuvent plus se faire passer pour vivants.
