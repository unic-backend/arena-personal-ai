# ARENA — état opérationnel

*Mesuré le 19/09/2026 sur `main` à `a7af403`, plus la branche
`claude/chemin-execution-bout-en-bout`. Chaque chiffre de ce fichier vient
d'une commande, jamais d'une lecture de code.*

**Ce fichier n'est pas un journal de décisions** — celui-là est
`docs/DECISIONS.md`. Il répond à une seule question : **qu'est-ce qui marche
vraiment aujourd'hui, et qu'est-ce qui n'a pas été vérifié ?**

---

## Comment ce fichier est mesuré

```
python scripts/orphelins.py              # modules atteints / orphelins
python scripts/doctor.py                 # dépendances et services réellement joignables
python -m pytest -q                      # la suite entière
ruff check .
```

---

## Ce qui est réellement opérationnel

Le chemin complet `chat → intention → agent → outil → résultat → preuve →
persistance → réponse` fonctionne et est couvert par des tests bout-en-bout.

| Élément | Mesure |
|---|---|
| Routers montés | **17 sur 17** (`apps/backend/main.py`) |
| Routes exposées | **64** (schéma OpenAPI, pas une liste écrite à la main) |
| Classes d'agents | **25 définies, 25 instanciées** dans `runtime.py` |
| Intentions aiguillées vers un agent | **26** (`dispatch_request`) |
| Connecteurs | **45**, tous derrière le registre (donc derrière les permissions) |
| Modules orphelins réels | **0** — 63 orphelins mesurés, tous des `__init__.py` ou des serveurs autonomes |

**Il n'y a pas de second orchestrateur.** `/api/video/projet` et l'intention
`VIDEO_PROJET` du chat appellent le **même** `VideoProductionAgent`, qui
délègue au **même** `core/execution/coordination.py`.

### État durable et reprise (nouveau, 19/09/2026)

`core/production/journal_projet.py`. Un projet de production porte désormais
`job_id`, `project_id`, et par étape : `status`, `created_at`, `updated_at`,
`input` (empreinte), `output`, `artifact`, `proof`, `error`, `retry_count`.
Six états, écrits, jamais déduits : `PENDING RUNNING SUCCEEDED FAILED
CANCELLED PAUSED`.

Écriture atomique après **chaque** changement. Au rechargement, un job resté
`RUNNING` devient `PAUSED` : rien ne tourne au démarrage.

| Route | Ce qu'elle fait |
|---|---|
| `POST /api/video/projet` | crée le projet, rend son `job_id` |
| `GET /api/video/projet/{job_id}` | l'état complet, étape par étape |
| `GET /api/video/projets` | ce qui attend une reprise |
| `POST /api/video/projet/{job_id}/reprendre` | continue sans rien refaire |
| `POST /api/video/projet/{job_id}/annuler` | définitif et idempotent |

**Une étape n'est sautée que sur trois preuves réunies** : statut `SUCCEEDED`,
entrée identique (empreinte), **et artefact encore présent sur le disque**. Un
fichier effacé entre-temps rend l'étape à refaire.

**Une étape tuée en cours n'est ni réussie ni échouée.** Elle est nommée dans
`a_verifier` et la réponse le dit en clair, au lieu de la rejouer en aveugle.

---

## Ce qui est testé mais jamais exécuté sur la machine cible

C'est la section qui compte le plus, et elle n'est pas courte.

| Capacité | État | Ce qui manque |
|---|---|---|
| Génération vidéo (WanGP) | `NOT_CONFIGURED` ici | le PC du propriétaire et sa RTX A2000 |
| Voix (VoiceStudio, CSM, VoxCPM) | `NOT_CONFIGURED` ici | `pip install "voxcpm>=2.0.3"` sur son PC |
| Génération d'image (HiDream, ComfyUI) | `NOT_CONFIGURED` ici | serveur local absent de cet environnement |
| Drift, Krillin, Xaar Kaname | `NOT_CONFIGURED` ici | programmes de bureau séparés |
| Ollama | joignable seulement chez lui | `ollama serve` |
| Anthropic (Claude Sonnet 5) | **ABSENT** | `ANTHROPIC_API_KEY` non posée |
| Groq / DeepInfra | **ABSENT** | clés non posées dans cet environnement |

**73 points du code rapportent explicitement `NOT_CONFIGURED`** au lieu de
simuler un succès. C'est la règle qui tient : une capacité absente rapporte son
état, elle ne rend jamais un résultat plausible.

**Aucun fournisseur de modèle n'a été mesuré depuis cet environnement.**
`scripts/comparer_fournisseurs.py` existe pour ça et rapporte `ABSENT` pour
chacun aujourd'hui — pas un zéro, pas une estimation. Toute annonce de vitesse
sans ce script qui tourne serait une invention.

---

## Sécurité

| Point | État |
|---|---|
| Secrets dans l'arbre courant | aucun (scan CI à chaque commit) |
| Secrets dans l'historique | **7 constats réels**, documentés un par un dans `.gitleaksignore` |
| Clés de fournisseur externe dans l'historique | **aucune** — vérifié motif par motif |
| 4 secrets LibreChat/Open WebUI | morts : les deux services sont retirés (DEC-0007) |
| 2 clés de l'API locale d'ARENA | **exposées publiquement**, remplacées par `USMAN_API_KEY` |
| Rotation de `USMAN_API_KEY` | **déclarée par le propriétaire, jamais mesurée ici** |

**Le seul point de sécurité encore ouvert, et il ne peut être fermé que par
lui** : si `USMAN_API_KEY` n'a pas réellement été changée, elle est lisible
dans l'historique public. Aucun test ne peut le vérifier depuis le dépôt.

---

## Dette technique critique

1. **`core/execution/travaux.py` est en mémoire pure.** La file de travaux de
   fond (indexation, suivi de génération) perd tout à un redémarrage. Le
   journal livré aujourd'hui couvre les projets de production, **pas** cette
   file. C'est le même manque, au même endroit, pour une autre famille de
   travaux.
2. **`AI_DAILY_BUDGET` est `NON_VERIFIABLE`.** Aucun tarif n'est saisi dans
   `TARIFS` (`core/models/usage.py`), et en saisir un seul ferait passer TOUS
   les fournisseurs pour « mesurés ». Le plafond qui tient est
   `AI_MAX_CLOUD_REQUESTS_PER_DAY`. Le chiffrage par fournisseur reste à faire.
3. **La sonde `faceplugin` coûte ~3 s par réponse.** Un cache court la
   supprimerait, au prix d'afficher un état qui n'est plus « maintenant ».
4. **Le tag `v0.1.0` n'a jamais été poussé** : son test est rouge en CI et sur
   `main` à l'identique. Ce n'est pas une régression, et ce n'est pas à
   « réparer » sans décision.

---

## Bugs connus

Aucun bug ouvert et reproductible à cette date. Les trois défauts trouvés
pendant ce travail ont été corrigés et sont figés par un test :

| Défaut | Correction |
|---|---|
| Une étape `PENDING` au redémarrage était annoncée « à vérifier » — ce qui noyait l'avertissement réel | seules les étapes `RUNNING` le sont |
| Un job `FAILED` n'était pas reprenable — or c'est le cas le plus utile (il répare la cause et continue) | `FAILED` rejoint `PAUSED` comme reprenable |
| « Aucun artefact » et « artefact annoncé introuvable » étaient confondus : une étape qui n'avait rien livré se sautait à la reprise | champ `artefact_attendu`, les deux cas sont séparés |

---

## Prochain jalon opérationnel

**Porter le même état durable sur `core/execution/travaux.py`.** C'est le
dernier endroit où un travail long disparaît à un redémarrage. Le modèle est
écrit, testé et en service ; il reste à le brancher sur la file de fond, comme
il vient de l'être sur la production vidéo.
