# MISSION EN COURS — Video : un vrai environnement de production

*Ouverte le 01/09/2026, demande directe du propriétaire : « ARENA VIDEO — FULL
AUDIT, INTEGRATION, ORCHESTRATION AND OPERATIONALIZATION ». La décision qui la
gouverne est **DEC-0037** (`docs/DECISIONS.md`) — à lire avant toute chose.
Elle **remplace** la mission « ARENA hybride » ci-dessous comme tâche active ;
cette dernière est conservée telle quelle, achevée, comme historique.*

Objectif : composer les capacités vidéo réelles qui existaient déjà chacune
séparément (WanGP, MoneyPrinterTurbo, le montage, VoiceStudio, la vision) sur
un même projet — dépendances, parallélisme, reprise après échec — au lieu
d'une liste de boutons. Le propriétaire a choisi de commencer par
**l'orchestrateur d'abord**, avant l'interface.

## Ce qui est déjà fait

`core/production/etat_projet.py`, `core/production/plan_video.py` et
`agents/video/production_agent.py` (`VideoProductionAgent` — compose vision,
WanGP, MoneyPrinterTurbo, VoiceStudio et montage via
`core/execution/coordination.py:executer_parallele()`) sont désormais
**atteints pour de vrai** : construit dans `apps/backend/runtime.py`, routé
par `POST /api/video/projet` (`apps/backend/routers/video_production.py`).
Aucun de ces trois modules ne dort plus — `python scripts/orphelins.py`
le mesure.

Une écriture (génération WanGP/MoneyPrinterTurbo, narration VoiceStudio)
reste soumise à la file de confirmation existante et ne s'exécute jamais
d'autorité (question posée explicitement au propriétaire le 01/09/2026,
réponse : « il attend ma confirmation a chaque etape d'ecriture »).

**Ce qui reste à faire** : aucune route n'est encore appelée depuis le chat
ou l'interface — `/api/video/projet` n'est atteignable aujourd'hui que par
un appel HTTP direct (curl, ou un futur frontend). Rien côté interface pour
l'instant, sur décision du propriétaire (01/09/2026).

---

> « Transform ARENA into a HYBRID AI INFERENCE SYSTEM using local Ollama + Groq
> + DeepInfra. Do NOT remove Ollama. Do NOT replace the local model. Do NOT
> hard-code ARENA to one provider. ARENA must intelligently choose. »

**C'est la tâche en cours.** Elle se livre **étape par étape**, chacune vérifiée
avant la suivante, comme il l'a demandé le 28/08 : « fais-le étape par étape,
sois sûr que ça marche avant de livrer ».

---

## Ce qui est déjà en place, et qui ne se refait pas

L'audit du 28/08 a trouvé que **quatre des vingt-huit points existaient déjà** :

| Ce que la mission demande | Ce qui existe |
|---|---|
| abstraction de fournisseur (§2) | `core/models/base.py` — `ModelProvider` |
| streaming (§13) | `OllamaProvider.generate_stream` + la passerelle PWA |
| détection de complexité (§7) | `core/execution/voies.py` — 4 voies et leurs budgets |
| télémétrie de latence (§6, §19) | `core/execution/mesures.py` + `GET /api/observability` |

Ils sont **réutilisés**, pas réécrits. Le point 21 de la mission le demande
explicitement : *« Do not introduce a huge framework just to support three
providers. »*

## Les étapes

### Étapes 1 à 3 — **faites le 28/08/2026**

**Étape 1 — la confidentialité et la configuration.** Quatre niveaux, et la
règle qui ne se négocie pas : **un secret ne sort jamais**. Le doute penche vers
sa machine. Le contexte joint monte le niveau, jamais l'inverse. La
configuration entre dans `apps/backend/config.py`, sans second système.

**Étape 2 — les deux fournisseurs distants.** Groq et DeepInfra parlent le même
protocole : une seule mécanique partagée, deux configurations. La clé part dans
l'en-tête et ne revient dans aucune erreur. Sans clé, le fournisseur est
**absent**, pas en panne.

**Étape 3 — l'aiguilleur.** Il pose quatre questions dans un ordre qui ne se
négocie pas : confidentialité → réglage → budget → santé. Puis le repli, chacun
essayé **une fois** : Groq → DeepInfra → Ollama. Un service qui tombe est mis au
frais deux minutes. Le repli n'a **pas** lieu après le premier mot — recommencer
ailleurs ferait lire deux débuts de réponse.

Il est branché dans `apps/backend/runtime.py` **à la place** des deux
fournisseurs : `fast_provider` et `deep_provider` désignent maintenant un
aiguilleur. Comme il implémente `ModelProvider`, **aucun agent, aucun routeur,
aucun test n'a eu à changer** — c'est ce que l'abstraction existante permettait.

Mesure sur la machine de l'assistant : mode `HYBRIDE`, aucun service distant
configuré (pas de clé), l'aiguilleur retombe sur Ollama. C'est le comportement
attendu, pas un échec.

**Aucun module de cette mission ne dort** : `python scripts/orphelins.py` →
116 modules, 88 atteints, aucun module réel endormi.

### Étape 4 — l'intégration réelle et la mesure — **faite le 28/08/2026**

**L'interface dit qui a répondu.** Elle annonçait « arena » quel que soit le
moteur ; depuis DEC-0009 la réponse peut venir du réseau, et le lui cacher
serait lui mentir sur ce qui a vu sa phrase. Le méta final porte maintenant le
fournisseur, le modèle, et **la raison du choix**.

**Le diagnostic porte une ligne « Inference (hybride) »** : son mode, et quels
services distants sont réellement configurés.

**Le banc d'essai existe** : `python scripts/comparer_fournisseurs.py`. Trois
scènes identiques pour tous, le temps jusqu'au **premier mot** d'abord, et la
médiane sur plusieurs passages.

Ce qu'il rend sur la machine de l'assistant, lancé le 28/08/2026 :

```
ollama       qwen3.5:9b                         ABSENT
groq         llama-3.3-70b-versatile            ABSENT
deepinfra    meta-llama/Llama-3.3-70B-Instruct  ABSENT

0 fournisseur(s) mesure(s), 3 absent(s).
Moins de deux fournisseurs : AUCUNE comparaison n'est possible. Ne rien conclure.
```

**Aucun chiffre de vitesse n'est donc annoncé nulle part dans ce dépôt**, et
c'est le point 24 de la mission. La comparaison attend son PC et ses clés.

---

## Ce qui reste, et qui n'est qu'à lui

| Pour que… | il faut |
|---|---|
| Groq réponde | `GROQ_API_KEY` dans `.env` (console.groq.com) |
| DeepInfra réponde | `DEEPINFRA_API_KEY` dans `.env` |
| tout redevienne local | `AI_LOCAL_ONLY=true` — une seule ligne |
| la comparaison existe | `python scripts/comparer_fournisseurs.py` sur son PC |

## Réseaux sociaux — intégré le 28/08/2026 (DEC-0010)

17 compétences de `charlie947/social-media-skills` inspectées. **Leur méthode
est extraite, leurs fichiers ne sont pas copiés** : leurs règles chiffrées
deviennent du code qui compte, leur voix devient des souvenirs, leur matrice
devient une combinatoire.

| Capacité | État |
|---|---|
| `social.post_writer`, `social.accroches`, `social.profil` | **opérationnelles** (modèle + voix + relecture) |
| `social.idees`, `social.verifier` | **opérationnelles sans modèle** — calcul et comptage |
| `social.voix` | **opérationnelle** — sa voix vit dans la mémoire personnelle |
| `social.recherche_niche` | INDISPONIBLE — recherche web non branchée sur cet agent |
| `social.analytics`, `social.visuel`, `social.reels` | CONFIGURATION_REQUISE — compte connecté, image, Apify/Gemini |

Publier passe par le connecteur, donc par la confirmation **et** le
coupe-circuit `PUBLISH` — qui vaut `false` dans `config/permissions.yaml` :
**rien ne peut partir tant qu'il ne le met pas à `true` lui-même.**

## Coordination des tâches — écrite le 28/08/2026 (DEC-0011)

`core/execution/coordination.py` : une tâche à plusieurs étapes qui **garde son
état** quand une étape tombe. Six règles, dont trois qui portent tout :

- **une étape facultative qui échoue n'arrête pas la tâche** — c'est ce qui
  permet à un calcul impossible de ne pas emporter la réponse ;
- **la reprise est bornée**, avec une attente croissante : retenter sans fin
  transforme une panne en boucle ;
- **la vérification est une étape**, pas une supposition — sans contrôle
  déclaré, `verifiee` reste `None`, jamais `True`.

Branché sur le moteur de raisonnement, qui enchaînait ses trois étapes en ligne
droite. **Son contrat n'a pas changé** : ses tests passent sans modification.

Mesuré, Docker absent : `plan DONE → calcul SKIPPED (refus du bac à sable) →
synthese DONE`, tâche **aboutie**. Avant, l'échec du calcul laissait la chaîne
dans le flou.

## Ce qui n'est PAS dans la mission

- retirer Ollama, ou le remplacer — **interdit explicitement** ;
- rendre le cloud obligatoire : `AI_LOCAL_ONLY=true` doit toujours suffire ;
- écrire une clé dans le dépôt ;
- annoncer une vitesse qui n'a pas été chronométrée ici.

---

---

# ARCHIVE — mission « réveiller ce qui dort » (terminée le 28/08/2026)

*Ouverte et close le 28/08/2026. Mesures de ce fichier prises sur la branche de
la dernière phase, avec `python scripts/orphelins.py`.*

> « regarde toutes les fonctionnalités qui sont intégrées dans le projet, si
> elles existent et exécutent et font de réel travail. Tout doit fonctionner,
> pas dormir là-bas. Tu les places sur les modèles adaptés : celles pour la
> vidéo, celles pour le code, celles pour le chat, celles pour les documents
> UniC Plaquiste. »

**Cette mission est terminée — le 28/08/2026.** Les neuf modules réels tournent
tous depuis un chemin de réponse réel. Le compteur d'orphelins ne contient plus
un seul module à réveiller. Rien de nouveau n'a été intégré : la mission n'a
fait que rendre vivant ce qui existait déjà.

**Le propriétaire donne la suite lui-même.** Deux questions ci-dessous attendent
sa réponse, et elles ne se tranchent pas sans lui.

---

## Ce que « réveillé » veut dire ici

Un module n'est pas réveillé parce qu'il importe, ni parce que ses tests
passent. Il l'est quand **une phrase du propriétaire le fait tourner**.

Cinq conditions, toutes obligatoires, pour chaque module :

1. Un chemin de réponse réel l'atteint — depuis `apps/backend/runtime.py`,
   la passerelle PWA, ou l'agent concerné. Pas depuis un script.
2. Il est branché sur **le bon agent** : la vidéo à la vidéo, le code au code,
   les documents au métier. Un module branché au mauvais endroit ne compte pas.
3. Un test tient le branchement, et **un sabotage le prouve** : on casse la
   garantie, on montre qu'un test précis tombe, on restaure.
4. `python -m ruff check .` et `python -m pytest tests/ -q` passent, lancés
   **dans le message qui l'annonce**.
5. `python scripts/orphelins.py` montre le module **disparu de la liste**.
   C'est la seule preuve qui ne se raconte pas.

Une capacité qui ne peut pas tourner sur la machine de l'assistant (Ollama,
WanGP, recherche web) se rapporte `NOT_CONFIGURED` **avec ce qui manque et la
commande qui l'obtient**. Elle ne se simule pas, et elle ne se déclare pas
terminée.

---

## L'état mesuré aujourd'hui

```
python scripts/orphelins.py
→ Modules totaux : 104  |  atteints : 77  |  orphelins : 27
```

**Les 27 restants ne sont pas des chantiers, et il n'y en a plus aucun à
réveiller.** La liste complète, décomposée :

| Ce que c'est | Combien | Pourquoi ça reste |
|---|---|---|
| `__init__.py` vides | 23 | marqueurs de paquet : il n'y a rien dedans à brancher |
| `apps/pwa/server/*` | 4 | un **second serveur FastAPI**, question ouverte au propriétaire |
| **modules réels endormis** | **0** | c'était la mission |

```
python scripts/orphelins.py  →  aucune ligne
```

---

## Ce qui a été fait, dans l'ordre où il a été fait

**Une phase = un module (ou une paire) = une pull request.** L'ordre a suivi ce
que le propriétaire ressent, pas ce qui était facile.

### Le métier — PR #12 et #13

- `calcul_materiaux` : 234 plaques, 288 montants, 54 rails redonnés à
  l'identique du devis `UC-2026-0804-FG2`.
- `devis_pdf` : un vrai PDF de 3720 octets écrit sur le disque, son chemin est
  la preuve.

### La vidéo et les documents — PR #15

- `suivi_video` + `travaux` sur **l'agent vidéo** : « où en est ma vidéo ? »
  ouvre un suivi en fond, le chat ne l'attend pas. L'identifiant vient du
  journal des actions, jamais de la phrase. Sans WanGP : `NOT_CONFIGURED` avec
  la commande de lancement.
- `indexer` + `inventory` sur **le chemin documentaire** : « indexe mes
  documents » indexe, « d'après mes documents… » interroge. L'indexation tourne
  hors de la boucle du serveur et ne reprend pas un fichier inchangé.

### La mémoire du chat — PR #16

- `semantique` : « combien de panneaux » ramène « 234 plaques BA13 », que le
  lexical seul rendait vide. L'index des vecteurs vit dans le câblage et dure.
  Sans Ollama : `MODE_LEXICAL`, dit dans le journal. Le seuil `0.45` n'a pas été
  touché — il a été mesuré avec `bge-m3`.
- `consolidation` : une phrase retenue deux fois prend une ligne, « vu 2 fois ».
  Rien n'est effacé en mémoire, une supposition ne rejoint jamais un fait.

### Le coût d'une réponse, et le raisonnement — PR en cours

- `voies` : l'orchestrateur consulte la voie juste après le classement ; le
  budget mémoire du prompt en découle. Une intention inconnue prend `LEGERE`.
- `mesures` : chaque tour est chronométré face à la cible de sa voie.
  `GET /api/observability` rend le tableau, **avec** les voies que personne n'a
  empruntées, marquées `UNKNOWN`. Un tour interrompu n'entre pas avec la durée
  de son échec.
- `reasoning_engine` : la question de la phase E est tranchée **dans le sens du
  branchement**, pas de la suppression. Ce qu'il fait de mieux que l'existant se
  dit en une phrase : `DEEP_REASONING` recevait une passe du modèle rapide et un
  chiffre sorti de sa tête ; il reçoit maintenant un plan, un calcul
  **réellement exécuté** en bac à sable, et une rédaction faite à partir du
  résultat obtenu. Quand le bac à sable refuse, la réponse le dit au lieu de
  présenter un résultat élégant que rien n'a vérifié. `/health` annonçait
  « ReasoningEngine » parmi les agents actifs : l'annonce est enfin vraie.

**Aucune suppression n'a été décidée.** Elle se demande au propriétaire.

---

## Réseaux sociaux — intégré le 28/08/2026 (DEC-0010)

17 compétences de `charlie947/social-media-skills` inspectées. **Leur méthode
est extraite, leurs fichiers ne sont pas copiés** : leurs règles chiffrées
deviennent du code qui compte, leur voix devient des souvenirs, leur matrice
devient une combinatoire.

| Capacité | État |
|---|---|
| `social.post_writer`, `social.accroches`, `social.profil` | **opérationnelles** (modèle + voix + relecture) |
| `social.idees`, `social.verifier` | **opérationnelles sans modèle** — calcul et comptage |
| `social.voix` | **opérationnelle** — sa voix vit dans la mémoire personnelle |
| `social.recherche_niche` | INDISPONIBLE — recherche web non branchée sur cet agent |
| `social.analytics`, `social.visuel`, `social.reels` | CONFIGURATION_REQUISE — compte connecté, image, Apify/Gemini |

Publier passe par le connecteur, donc par la confirmation **et** le
coupe-circuit `PUBLISH` — qui vaut `false` dans `config/permissions.yaml` :
**rien ne peut partir tant qu'il ne le met pas à `true` lui-même.**

## Coordination des tâches — écrite le 28/08/2026 (DEC-0011)

`core/execution/coordination.py` : une tâche à plusieurs étapes qui **garde son
état** quand une étape tombe. Six règles, dont trois qui portent tout :

- **une étape facultative qui échoue n'arrête pas la tâche** — c'est ce qui
  permet à un calcul impossible de ne pas emporter la réponse ;
- **la reprise est bornée**, avec une attente croissante : retenter sans fin
  transforme une panne en boucle ;
- **la vérification est une étape**, pas une supposition — sans contrôle
  déclaré, `verifiee` reste `None`, jamais `True`.

Branché sur le moteur de raisonnement, qui enchaînait ses trois étapes en ligne
droite. **Son contrat n'a pas changé** : ses tests passent sans modification.

Mesuré, Docker absent : `plan DONE → calcul SKIPPED (refus du bac à sable) →
synthese DONE`, tâche **aboutie**. Avant, l'échec du calcul laissait la chaîne
dans le flou.

## Ce qui n'est PAS dans la mission

- Les 22 `__init__.py` vides. Ce sont des marqueurs de paquet.
- `apps/pwa/server/{main,providers,oauth,attachments}.py` — **un second
  serveur FastAPI**, avec sa propre gestion de `.env` et de fournisseurs,
  visiblement remplacé par `apps/backend/`. Le supprimer effacerait 482 lignes.
  **Question au propriétaire, pas une tâche.**
- Toute nouvelle fonctionnalité. Cette mission ne fait que rendre vivant ce qui
  existe déjà. Une amélioration repérée en chemin s'écrit
  `SUGGESTION — NON IMPLÉMENTÉE` et ne devient jamais une tâche toute seule.

---

## Les questions ouvertes pour le propriétaire

1. ~~**La rotation de clé a-t-elle bien eu lieu ?**~~ **Répondu le 28/08/2026.**
   Il a changé la clé d'ARENA une fois ; les quatre autres n'ont jamais été
   touchées. Elles servaient à LibreChat et Open WebUI, qu'il n'utilise plus :
   les deux clients sont **retirés du dépôt** (DEC-0007), donc ces quatre
   valeurs n'ouvrent plus rien. Reste `USMAN_API_KEY`, la seule vivante — à
   changer s'il n'est pas certain de l'avoir fait
   (`documents/RUNBOOK_PURGE_SECRETS.md`, étape 1).
2. ~~**Le dépôt est public.**~~ Passé en privé le 28/08/2026 (sa décision),
   **repassé en public le 06/09/2026 — sa décision aussi.** Vérifié par
   l'API GitHub : `"visibility": "public"`. L'historique contenant les six
   secrets (cinq clés + la sixième non détaillée ici) redevient donc
   lisible par n'importe qui — la purge (`documents/RUNBOOK_PURGE_SECRETS.md`)
   reste **jamais autorisée**, c'est sa décision. Il a dit changer
   `USMAN_API_KEY` lui-même à ce moment-là : **non vérifié par une mesure**,
   à confirmer avant de l'écrire ailleurs comme fait.

   **Mesure du 12/09/2026 — ce que l'historique public expose exactement.**
   gitleaks 8.28.0 (la version épinglée de la CI), `--redact`, sur les 693
   commits : **7 constats, 6 lignes, 3 commits, tous du 25/08/2026**, tous
   dans `docker-compose.yml` et `librechat.yaml` — les fichiers retirés par
   DEC-0007.

   | Secret | Longueur | État |
   |---|---|---|
   | `CREDS_KEY` | 64 | interne LibreChat → **mort**, service retiré |
   | `JWT_SECRET` | 63 | idem |
   | `JWT_REFRESH_SECRET` | 61 | idem |
   | `WEBUI_SECRET_KEY` | 22 | interne Open WebUI → **mort** |
   | `OPENAI_API_KEY` | **15** | **pas une clé OpenAI** : trop courte, aucun préfixe `sk-`. C'est une clé de l'API LOCALE d'ARENA (LibreChat parlait le protocole OpenAI à `host.docker.internal:8000`) |
   | `apiKey` (librechat.yaml) | 15 | clé de l'API locale aussi, **valeur différente** de la précédente |

   **Aucune clé de fournisseur externe dans l'historique.** Les motifs `sk-`,
   `sk-ant-`, `ghp_`, `gho_`, `AKIA`, `AIza` et `xoxb-` ne correspondent que
   dans `tests/core/test_confidentialite.py` et `tests/test_scanner_secrets.py`,
   sur des valeurs inventées qui se nomment elles-mêmes, chacune marquée
   `# scanner-secrets: ignore` — lues une par une. Le scan refait **sans
   aucune exclusion du projet** donne 16 constats au lieu de 7 : les 12 en
   plus sont ces mêmes fixtures. Les exclusions ne cachent donc rien.

   **Conclusion : la purge reste inutile, et pour une raison mesurée.** Les
   deux seules valeurs qui comptent gardent `/api/*` sur sa machine. Les
   changer rend l'exposition inoffensive, sans casser un seul clone ni un
   seul SHA cité dans ces documents. La purge reste **jamais autorisée**.

   Depuis cette mesure, la CI scanne **l'historique entier** à chaque
   exécution (`.gitleaksignore` référence les sept constats connus par
   empreinte) : tout secret ajouté ailleurs dans l'histoire fait désormais
   échouer le contrôle. Le commentaire de la CI disait que l'historique
   « sera scannable en entier une fois T-01 exécutée » — attendre une purge
   jamais autorisée pour scanner, c'était ne jamais scanner.
   ~~**Rouvre-t-on le chapitre 8 (connecteur e-mail) ?**~~ **Oui, le
   28/08/2026 — et il est terminé le jour même.** 8.1 : lire et chercher son
   courrier. 8.2 : trier, extraire, rédiger, et **envoyer derrière
   confirmation**. Les identifiants Google vivent dans `.env`, jamais dans le
   dépôt.
3. ~~**`apps/pwa/server/` : on le garde ou on le supprime ?**~~ **Répondu le
   29/08/2026, depuis son téléphone — supprimé.** Les 4 fichiers (482 lignes)
   n'étaient référencés nulle part (`grep` sur tout le dépôt, hors documents),
   aucun test n'en dépendait, et c'était déjà l'analyse ci-dessus : un second
   serveur, visiblement remplacé par `apps/backend/`.

Aucune ne se tranche sans lui.

---

## Ce qui est déjà fait dans cette mission

| Date | Module réveillé | Preuve |
|---|---|---|
| 28/08/2026 | `agents/plaquiste/calcul_materiaux` | PR #12 — 234 plaques, 288 montants, 54 rails redonnés à l'identique du devis `UC-2026-0804-FG2` |
| 28/08/2026 | `agents/plaquiste/devis_pdf` | PR #13 — un vrai PDF de 3720 octets écrit sur le disque, son chemin est la preuve |
| 28/08/2026 | `core/execution/travaux` + `core/connectors/suivi_video` | « où en est ma vidéo ? » ouvre un suivi en fond sur l'agent vidéo ; le tour de chat se termine avant lui |
| 28/08/2026 | `tools/documents/indexer` + `tools/documents/inventory` | « indexe mes documents » lit, insère, et ne réindexe pas un fichier qui n'a pas bougé |
| 28/08/2026 | `core/memory/semantique` | « combien de panneaux » ramène « 234 plaques BA13 », que la récupération lexicale rendait vide — mesuré dans le même test |
| 28/08/2026 | `core/memory/consolidation` | une phrase retenue deux fois n'occupe plus qu'une ligne du prompt, avec son compte ; les deux souvenirs sont toujours en mémoire |

| 28/08/2026 | `core/execution/voies` | la voie de l'intention voyage avec la réponse, et le budget mémoire du prompt en découle : deux intentions, deux enveloppes |

| 28/08/2026 | `core/execution/mesures` | chaque tour est chronométré face à la cible de sa voie ; `/api/observability` montre aussi ce qui n'a pas été mesuré |

| 28/08/2026 | `core/reasoning/reasoning_engine` | `DEEP_REASONING` planifie, exécute le calcul en bac à sable, puis rédige — et dit quand le calcul n'a pas eu lieu |

Atteints : **64 → 68 → 72 → 73 → 74 → 75 → 76 → 77**. Modules réels endormis :
**9 → 0**. Le compteur est la mesure, pas le récit.

---

## Comment livrer chaque phase

Il ne lance pas les tests : **la pull request est le seul endroit où il voit ce
qui entre.** Une PR par module, et dedans, dans cet ordre :

1. ce qui dormait, et ce que ça lui coûtait concrètement ;
2. ce qui est branché, où, et sur quel agent ;
3. la sortie **réelle** de `ruff` et de `pytest` ;
4. le sabotage : ce qui a été cassé, quel test est tombé, restauré ;
5. `python scripts/orphelins.py` avant / après.

Puis on s'arrête et on attend son « continuer ». Une phase par tour, jamais
deux — `docs/REGLES_DE_TRAVAIL.md`.

**Les 9 modules sont réveillés.** La mission est finie, compteur à l'appui :
`python scripts/orphelins.py` ne nomme plus aucun module. La suite lui
appartient — il a dit qu'il donnerait la tâche suivante lui-même.
