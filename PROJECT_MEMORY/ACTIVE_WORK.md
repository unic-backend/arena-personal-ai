# TRAVAIL EN COURS

*Mise à jour : 2026-09-13, travail de nuit (DEC-0099 → DEC-0104).*

## En cours

**Rien n'est en cours.** Le propriétaire a autorisé un travail de nuit sans
interruption (« tu dois enchaîner tout ce qui reste sans attendre rien de
moi »). Ce qui restait a été fait. **Aucune fusion dans `main` n'a été faite :
c'est sa décision** (`docs/REGLES_DE_TRAVAIL.md` : tout passe par une pull
request qu'il fusionne lui-même).

### Ce qui a été fusionné par lui pendant la nuit

| PR | DEC | Ce qu'elle apporte |
|---|---|---|
| #211 | — | la boucle agentique greffée sur l'Executive Brain (seconde chance, budgets `TOURS_MAX`/`SECONDES_MAX`) |
| #212 | DEC-0099 | `TypeSouvenir.DECISION` et `ERREUR`, détection de contradiction qui **enregistre et n'arbitre jamais** |
| #213 | DEC-0100 | un identifiant du premier octet HTTP à la dernière action (`X-Request-ID`) |

### Ce qui attend sa décision de fusion — cinq PR, deux empilements

| PR | Branche | Base | Ce qu'elle répare |
|---|---|---|---|
| #214 | `claude/routeur-statistiques` | `main` | ce que chaque type de tâche coûte vraiment — mesuré, `None` quand rien n'a tourné |
| #215 | `claude/page-piegee-executif` | `main` | la frontière de confiance **gardée** sur les deux entrées du chemin exécutif (aucun code de production changé) |
| #216 | `claude/plans-observables` | **#214** | un plan dit ce qu'il a fait et pourquoi il s'est arrêté (`/api/plans`) |
| #217 | `claude/memoire-validite` | `main` | DEC-0103 — `valide_depuis` : depuis quand un souvenir est vrai |
| #218 | `claude/memoire-sources` | **#217** | DEC-0104 — une source qui se répète n'est pas une source de plus |

**L'ordre compte** : #216 repose sur #214, #218 repose sur #217. Fusionner la
base avant l'empilée, sinon la seconde emporte le diff de la première.

CI mesurée le 13/09/2026 : #214, #215 et #216 **vertes sur les six checks**.
#217 et #218 étaient encore en cours d'exécution au moment d'écrire ceci — à
vérifier avant de fusionner, jamais à supposer.

### Les deux défauts réels trouvés cette nuit

Aucun des deux n'était dans la liste de l'audit : ils sont apparus **en
faisant** le travail que l'audit demandait.

1. **`confirmer()` promettait sans vérifier.** Sa docstring disait « elle exige
   une source nouvelle ». Elle ne le vérifiait pas : trois appels avec le même
   document promouvaient une inférence en **fait**, et ARENA répondait ensuite
   un tarif avec l'assurance d'un fait corroboré qu'une seule voix avait dit.
   Mesuré avant correction, corrigé dans #218.
2. **Trois références pointaient vers un projet qui n'est pas celui-ci.**
   `core/live_context/` et `src/live_context/` étaient cités dans DEC-0099,
   `core/memory/contradiction.py` et `apps/backend/prompts.py`. Ces chemins
   n'existent pas ici. Les règles qu'ils nommaient sont bonnes, l'attribution
   était fausse. Corrigées en place, jamais effacées.

### Ce qui a été refusé, et pourquoi

**`confidence` n'est pas implémenté.** C'était le troisième manque nommé par
DEC-0099. Un flottant `0.82` à côté d'un souvenir serait lu comme une mesure ;
rien ici ne le mesure, il serait dérivé d'une pondération choisie par
l'assistant puis cité comme un fait. Ce qu'un lecteur veut savoir existe déjà
et **est mesuré** : `nature`, `nombre_de_sources`, `est_en_vigueur()`, et le
rapport de contradictions.

**Ce qui rouvrirait la question :** que le propriétaire décide d'une pondération
et la nomme. Un score est un jugement produit — ce n'est pas à l'assistant de le
fixer.

### La liste de l'audit PHASE 0 est épuisée

`docs/audits/audit_phase0_2026-09-12.md`, tableau des priorités : les deux P0 et
les quatre P1 sont livrés. Il reste **un P2 : le banc d'essai des modèles
locaux**, qui exige sa machine — aucun modèle n'a jamais tourné ici.

### État mesuré au moment d'écrire

**Sur la tête de la pile** (`claude/memoire-sources`, PR #218, qui contient tout
le travail de la nuit) :

```
python -m pytest -q  → 5631 passed, 31 skipped, 52 deselected
ruff check core tests apps agents scripts → All checks passed!
python scripts/orphelins.py → 304 modules, 243 atteints, 0 orphelin réel
```

**Sur `main` tel qu'il est** (avant toute fusion des cinq PR ouvertes) :

```
python -m pytest -q  → 5606 passed, 31 skipped, 52 deselected
ruff check core tests apps agents scripts → All checks passed!
```

L'écart de 25 tests, ce sont les tests que les PR ouvertes apportent.

---

## Chunk précédent : 12/09/2026 — historique public, CI sur `main`, inventaire

**Une PR attend sa décision de fusion : ce que l'historique public expose,
et la CI qui le scanne.** Branche `claude/scan-histoire-et-depot-public`.

Mesure du 12/09/2026 sur les 693 commits : **7 constats, 6 secrets, 3
commits, tous du 25/08/2026**, tous dans les fichiers LibreChat/Open WebUI
retirés par DEC-0007. **Aucune clé de fournisseur externe.** Quatre secrets
sont internes à ces deux services, donc morts ; les deux autres (15
caractères chacun, valeurs différentes) sont des clés de l'API **locale**
d'ARENA — `OPENAI_API_KEY` n'en était pas une, trop courte et sans préfixe
`sk-`. **Une seule action réelle : changer `USMAN_API_KEY`.** Détail complet
dans `docs/CURRENT_TASK.md`.

La CI scanne maintenant l'historique entier, trou prouvé par sabotage : un
secret ajouté puis retiré passe le scan des fichiers courants et échoue au
scan de l'histoire.

La PR de la branche par défaut (`claude/ci-branche-main`) est
**fusionnée** ; le commit de fusion sur `main` a déclenché 6 checks, ce qui
prouve que les déclencheurs fonctionnent.

Il a renommé `master` → `main` le 12/09/2026 (son dépôt est **public** et les
outils tiers, qui supposent `main`, répondaient 404 — mesuré). Le dépôt
écrivait `master` en dur : **plus aucun check ne tournait** sur `main` ni sur
une PR la visant, et le scan différentiel de secrets comparait à
`origin/master`, donc tombait dans son repli « étape ignorée » et **ne
scannait plus rien sans échouer**. Corrigé, base lue sur l'événement GitHub,
échec bruyant si elle manque, 4 tests qui gardent la classe.

**Deux choses à savoir pour la suite :**
- les documents affirment encore « le dépôt est **privé** depuis le
  28/08/2026 » (`DECISIONS.md`, `CHANGELOG.md`, `docs/CURRENT_TASK.md`). Il
  est **public** (`private: false`, mesuré). `.env` est ignoré et n'a jamais
  été versionné, le *Secret scan* est vert — mais la note « purge de
  l'historique jamais autorisée, le dépôt est privé » repose sur une prémisse
  qui a changé. **Sa décision.**
- un clone de ce dépôt peut arriver configuré pour ne suivre QUE `master`
  (`remote.origin.fetch` mono-branche). Vérifier
  `git config --get-all remote.origin.fetch` avant tout inventaire de
  branches : sinon les références locales sont périmées et l'inventaire est
  faux (c'est arrivé dans cette session).

PR #204 (DEC-0098), l'index de tri de la mémoire, est **fusionnée**.

Tout le reste est **fusionné** dans `master` par le propriétaire le
12/09/2026 : PR #196 (DEC-0094, gitgui second passage — CI avait trouvé une
vraie régression, `continuer_operation()` sans éditeur configuré, corrigée
par `-c core.editor=true`, puis le conflit `Pillow`/`psutil` avec
`browser-use` cherry-pické depuis DEC-0095), PR #197 (DEC-0095), PR #199
(diagnostic des douze étapes), PR #202 (DEC-0096) et PR #203 (DEC-0097).
Détail de chacune plus bas.

### Inventaire du travail inachevé, mesuré le 12/09/2026

Fait à sa demande (« regarde aussi s'il y a du travail non terminé, bloqué
ou arrêté »). Le résultat tient en une ligne : **il n'y avait qu'un seul
travail inachevé côté dépôt**, l'index de tri, et il est fait.

| Cherché | Mesuré |
|---|---|
| `TODO`/`FIXME` dans notre code | **0** (les 3661 trouvés sont dans des dépendances tierces vendorisées) |
| PR ouvertes | aucune |
| tests sautés (31) | 25 identifiés : Pascal (11), Lean (8), krillinai (4), browser-use (1), graphify (1) — tous « outil absent de CETTE machine » |
| tests désélectionnés (52) | tous `integration` : Ollama, Docker, réseau ou Chromium |
| `doctor.py` | 18 capacités indisponibles, **toutes** chez lui |
| connecteurs dormants | 1, `txtai_search`, bloqué par DEC-0051 — sa décision |

**Deux branches non fusionnées, et ce qu'il faut en faire :**

- `claude/hidream-i1-image-generation` — **morte.** Son unique commit
  ajoutait `psutil` à la liste d'installation du CI, que `master` a déjà
  (avec `cryptography` et `mcp` en plus). HiDream lui-même est dans
  `master` (`production_agent.py`, ses routes, ses tests). Rien à
  récupérer.
- `saer-video-wip` — **à ne pas fusionner.** Son travail vidéo d'août est
  **déjà dans `master`** (`c8132c9 feat(video): take Saer's subtitle,
  burn-in and transcription work`). Ce qui reste dans la branche, c'est
  `librechat.yaml` et LibreChat dans `docker-compose.yml` — supprimés par
  DEC-0007 après la fuite de 4 clés. La fusionner les remettrait.

Supprimer une branche reste **sa** décision : rien n'a été supprimé.

## DEC-0098 — toute lecture de la memoire construisait un TEMP B-TREE (12/09/2026)

Quatre index existaient, tous sur des colonnes de `WHERE`. Aucun ne servait
`ORDER BY importance DESC, cree_le DESC` — que TOUTE lecture execute, donc
deux fois par question. Mesure par `souvenirs(limite=500)` sur 50 000
souvenirs :

```
sans l'index : 20,56 ms   plan : idx_souvenirs_etat + USE TEMP B-TREE FOR ORDER BY
avec l'index :  5,05 ms   plan : idx_souvenirs_tri
```

Un seul index composite ajoute dans le meme bloc que les quatre autres
(`CREATE INDEX IF NOT EXISTS`, donc il s'ajoute aussi a une base deja en
service). Zone verrouillee sur « une migration qui n'efface rien » :
conditions 3, 4 et 6 de `LOCKED_ZONES.md`, et un index ne peut pas perdre
une ligne — un test ouvre une base a l'ANCIEN format et verifie que le
souvenir qui s'y trouvait survit.

**Deux affirmations de l'assistant, fausses, corrigees avant le commit :**
le `DESC` de l'index n'est PAS necessaire (0,49 contre 0,50 ms, aucun TEMP
B-TREE des deux cotes — le test qui l'affirmait est remplace par sa
contre-mesure), et une premiere serie de mesures comparait `'ACTIF'` a
`Etat.ACTIF.value` qui vaut `'ACTIVE'` : zero ligne d'un cote, donc un
« gain x111 » sans aucun sens. Refaite.

## DEC-0097 — un souvenir sensible etait introuvable par mot-cle (12/09/2026)

Suite directe de DEC-0096 : le dechiffrement devenu gratuit, le second
defaut trouve dans la meme lecture de `core/memory/` devenait reparable.
Mesure avant d'ecrire une ligne :

```
[le souvenir existe bien]                     True
['quel est le code du portail Fast Group ?']  retrouve : False
['code portail chantier']                     retrouve : False
['4821']                                      retrouve : False
```

« Le code du portail du chantier Fast Group est 4821. », marque
`sensible=True`, 400 jours, importance 0,02 : il existait, **aucune
question ne pouvait l'atteindre**. Cause : le complement par mots-cles
filtre en SQL et exclut `sensible = 0` — a raison, un `LIKE` ne trouve
rien dans du chiffre. Hors de la fenetre importance/recence, un souvenir
sensible n'etait donc plus joignable du tout.

**Trois corrections, dans cet ordre de dependance :**

| Correction | Ou | Mesure |
|---|---|---|
| une TROISIEME fenetre bornee qui dechiffre puis filtre | `core/memory/recuperation.py::sensibles_correspondants` | les trois questions ci-dessus repondent `True`, latence inchangee (15,9 ms contre 15,5) |
| le sel d'ecriture conserve entre deux processus (`vault_salt`, 0600) | `core/memory/chiffrement.py`, `Coffre(chemin_sel=...)` | 500 sensibles ecrits au fil de 100 sessions : **26,7 s → 285 ms** a la premiere question |
| le coffre branche dans le backend | `apps/backend/runtime.py` | `/api/memory` avec `sensible: true` : **422 toujours → 200**, et du chiffre sur le disque |

La troisieme n'est pas un ajout de confort : `/api/memory` **declarait**
`sensible: true` dans son schema et le refusait TOUJOURS en 422, parce que
le backend construisait `MemoirePersonnelle` sans coffre. Le chiffrement au
repos de DEC-0090 n'etait joignable que par le serveur MCP — jamais depuis
son telephone. Le refus etait honnete (jamais un faux succes, jamais un
souvenir en clair sous couvert de securite) : c'est la capacite qui
manquait. Sans `USMAN_MEMORY_VAULT_PASSPHRASE`, rien ne change.

Le cout de la troisieme fenetre ne suit **pas** le nombre de lignes mais le
nombre de **sels distincts** a deriver — c'est pour cela que la deuxieme
correction existe, et c'est ce qui la rend necessaire plutot
qu'optionnelle.

**Un test qui affirmait l'inverse, reecrit et non supprime.**
`test_un_souvenir_sensible_hors_fenetre_reste_hors_de_portee` gardait cette
limite quand elle etait reelle ; il devient
`test_un_souvenir_sensible_hors_fenetre_est_maintenant_retrouve`, meme
scenario, assertion inversee, raison ecrite dedans. Le test voisin qui
garde la limite du mot trop partage reste intact : celle-la existe
toujours.

**Quatre sabotages, quatre tests qui tombent** : troisieme fenetre
debranchee (1), garde des messages d'echec retiree (1), sel conserve ignore
(2), coffre debranche du runtime (1). Tous restaures.

## DEC-0096 — la memoire chiffree coutait 275 ms par souvenir relu (12/09/2026)

Trouve en cherchant quoi ameliorer dans la memoire, et **mesure avant
d'ecrire quoi que ce soit** :

```
500 souvenirs sensibles, relus       : 133 590 ms  (2 min 14)
une derivation PBKDF2 (600 000 iter.):      275 ms
nonce different par message          : True
sel aussi different par message      : True   <- la cause
```

`chiffrer()` tirait un **sel** neuf a chaque message, donc `dechiffrer()`
repayait les 600 000 iterations **par souvenir**. Le nonce — la seule
unicite qu'AES-GCM exige reellement — etait deja tire au hasard par
message : le sel par message n'achetait aucune securite et coutait 275 ms
a chaque lecture. Effet pratique : plus il enregistre de souvenirs
sensibles, plus ARENA devient lente, precisement sur les donnees qui
valent d'etre protegees.

Deux changements, aucun ne touche au format d'enveloppe
(`core/memory/chiffrement.py`) :

- un cache borne de cles derivees, par sel (`CLES_GARDEES = 256`) ;
- un sel partage par lot d'ecritures (`MESSAGES_PAR_SEL = 65 536`), la
  forme ordinaire d'un conteneur chiffre : un sel en en-tete, puis un
  nonce neuf par message.

Mesure apres (re-mesuree le 12/09/2026 apres coup, machine au repos) :

```
500 ecritures sensibles   :   270,6 ms   (contre 138 s)
relecture des 500         :     3,6 ms   (contre 133 590 ms)
nonces distincts sur 500  :   500
sels distincts sur 500    :     1        <- une seule derivation payee
```

500 dechiffrements coutent donc **une** derivation au lieu de 500 — asserte
par un test qui compte les appels, pas estime a l'oeil.

**Pourquoi ce n'est pas un troc securite/vitesse**, chaque point garde par
un test de `tests/core/test_memoire_chiffrement.py` :

- le nonce reste `os.urandom` par message — verifie sur 50 enveloppes ;
- le sel reste aleatoire (jamais une constante) et tourne par lot, donc
  une cle ne couvre jamais un nombre illimite de messages et la marge
  d'anniversaire du nonce 96 bits reste intacte ;
- une mauvaise phrase secrete est toujours refusee — le cache est indexe
  par sel et derive de la phrase de l'instance, il ne peut pas servir de
  porte derobee ;
- `dechiffrer()` n'est pas touche : il lit toujours le sel dans
  l'enveloppe, donc **tout souvenir deja ecrit reste lisible**. Prouve par
  un test qui reconstruit a la main l'ANCIEN format (un sel par message)
  et le dechiffre.

`PROJECT_MEMORY/LOCKED_ZONES.md` verrouille `core/memory/personnelle.py`
(schema SQLite + migration qui n'effacera jamais) ; ce changement ne
touche ni le schema, ni la migration, ni les donnees stockees.

**Quatre affirmations du depot devenues fausses**, corrigees sur place
plutot que laissees a tromper le prochain lecteur : le commentaire « sel et
nonce tires au hasard a chaque appel » dans le test, celui de `TAILLE_SEL`
(« un sel par chiffrement, jamais partage entre deux souvenirs »), le
docstring de `Coffre` (« le sel differe a chaque appel ») et — la plus
importante — la premise du docstring du module, « la derivation de cle ne
tourne jamais sur un chemin chaud ». Cette phrase etait fausse, et c'est
elle qui a autorise le defaut : elle vient d'etre remplacee par la mesure
qui la contredit.

### Deux defauts de memoire trouves ici — un corrige depuis, un ouvert

1. ~~Un souvenir sensible est introuvable par mot-cle.~~ **Corrige par
   DEC-0097**, juste au-dessus.
2. **Ouvert : `ORDER BY importance DESC, cree_le DESC` passe par un TEMP
   B-TREE** (aucun index composite), et la requete par mots-cles classe par
   importance et non par pertinence lexicale — un mot partage par plus de
   `limite_lecture` souvenirs peut donc cacher une correspondance peu
   importante. Le test
   `test_limite_reelle_un_mot_partage_par_trop_de_souvenirs_peut_encore_manquer`
   garde cette limite : elle est mesuree, pas cachee.

## Quatre des cinq connecteurs dormants reveilles — le cinquieme refuse par sa propre decision (12/09/2026)

Demande directe du proprietaire (« reveil les 5 »), apres la mesure
« qu'est-ce qui dort encore ? ». **Quatre sont reveilles ; le cinquieme,
`txtai_search`, est reste dormant parce que DEC-0051 l'interdit** — sa
propre decision anterieure, qu'il ne pouvait pas avoir en tete. Detail
plus bas.

Aucune architecture neuve : chacun est tombe sur un chemin qui existait
deja et avait deja une raison de le vouloir.

| Connecteur | Reveille sur | Ligne d'appel |
|---|---|---|
| `graphify` | repli de la source `codebase` (l'en-tete du module l'annoncait depuis le 06/09/2026 sans que rien ne l'appelle) | `core/context/recherche_unifiee.py:150` |
| `galsen` | la donnee officielle AVANT le web, sur `FRESH_INFO` | `apps/backend/routers/chat.py:425` |
| `workflow_guide` | mode operatoire ecrit par `PlaquisteAgent`, meme motif que le devis (URL rendue pour son telephone) | `agents/plaquiste/plaquiste_agent.py:889` |
| `formbricks` | retours clients lus par `PlaquisteAgent` (lecture seule : `lister`) | `agents/plaquiste/plaquiste_agent.py:915` |

**La regle tenue partout : rien ne s'invente.** Sans etapes dictees, aucun
guide n'est ecrit et il l'apprend (meme discipline que « je ne devine pas
le destinataire d'un devis ») ; un dossier de documents vide garde l'echec
reel de LightRAG ; une API senegalaise muette laisse le web repondre ;
`formbricks` sans `FORMBRICKS_BASE_URL` rapporte son indisponibilite.
`graphify` garde une provenance distincte (`codebase_graphe`) : un graphe
construit avant-hier n'est pas une lecture du code d'hier.

**Pourquoi `txtai_search` n'a pas ete reveille.** Le branchement etait
ecrit (repli de LightRAG sur `RAG_DOCS`, alimente par ses vrais documents)
et ses quatre tests passaient — puis la suite complete a fait tomber
`tests/core/test_connecteur_txtai_search.py::TestPasDeRoutageAutomatique`,
un test EXISTANT qui garde DEC-0051 : « n'utilise txtai que lorsque son
avantage est demontre », donc « aucune branche d'aiguillage automatique ».
Le banc de comparaison qui demontrerait cet avantage exige des embeddings
reels — Ollama, absent de ce conteneur. Le branchement a ete RETIRE, le
test n'a pas ete touche, et la raison exacte est desormais ecrite dans
`DORMANTS_CONNUS`. Pour le lever : un banc pertinence/latence sur sa
machine, Ollama lance, contre `lightrag`/`semantique` — puis sa decision.

Reste hors de portee d'ici, et ce n'est pas du sommeil : 25 des 40
connecteurs sont `NOT_CONFIGURED` sur cette machine (cle ou service absent)
et les quatre modeles Ollama repondent `False` — ils vivent chez lui.

## Diagnostic des douze etapes de DEC-0095 (12/09/2026, PR #199, fusionnee)

Le proprietaire a demande de rediagnostiquer les douze reparations **une par
une**, et de corriger mes propres erreurs. **Huit** etapes ont tenu sans
retouche (1, 2, 3, 4, 8, 9, 11, 12) ; **quatre portaient un vrai trou**, tous corriges,
chacun prouve en echec avant / succes apres :

| Etape | Trou trouve en diagnostic | Mesure avant correctif |
|---|---|---|
| 5 idempotence | une ANNULATION (client deconnecte) traverse `chronometrer` sans produire de trame ; `trames vides` etait lu comme « rien ne s'est passe » et le `run_id` oublie | **2 executions pour une seule demande** |
| 6 video | seul le rendu de repli etait verifie : un `clip_path` fourni et existant court-circuitait tout controle ; `subtitle_srt` annonce sans fichier | un extrait de **2 octets** annonce `status: success` |
| 7 liens | `{nom:path}` a rendu un SYMLINK imbrique atteignable pour la premiere fois ; `resolve()` protegeait deja, rien ne l'epinglait | sabotage `resolve()`->`absolute()` : `/etc/passwd` servi en **200** |
| 10 quotas | plafond lu avant l'appel, compte apres la reponse ; et `AI_MAX_COST_PER_REQUEST` declare dans `config.py` + `.env.example`, lu par **zero** ligne | **10 requetes paralleles** passaient un plafond de **3** |

Corrections : drapeau `agent_lance` + trois cas dans le `finally`
(`pwa_gateway.py`) ; verification `ffprobe` du clip fourni et
`_srt_si_reel()` (`media.py`) ; tests symlink + traversees encodees ;
reservation de quota (`reserver_une_place`/`liberer_une_place`, comptee par
`verdict()`) sur `generate` ET le flux, plus trois etats honnetes pour le
plafond par requete (`DESACTIVE` / `NON_VERIFIABLE` / `MESURE_APRES_COUP`) —
il vaut `NON_VERIFIABLE` aujourd'hui, faute de tarif configure.

Au passage, CI rouge sur #199 : `test_scripts_powershell.py` attendait un
delai FIXE de 4 s que `pwsh` demarre et poste. Cause racine reproduite en
abaissant ce delai a 0,15 s ; le test attend desormais la condition (le POST
recu), et tourne plus vite (3,2 s au lieu de 7 s).

**Trois faux positifs de mon propre diagnostic**, signales pour ne pas laisser
croire a des regressions : l'inventaire des medias (mauvais module importe
dans mon script), la surface de l'API (`app.routes` contient des `Mount`), et
le compte des verifications de `doctor.py` (le test compte les appels
`mesurer("`, pas les fonctions `verifier_*` — 30 est exact).

## Dernier chunk : DEC-0095 — douze défauts confirmés d'un audit externe, réparés un par un (PR #197)

Mission reçue avec consigne explicite : revérifier CHAQUE constat de
l'audit (commit `f7f0478`) contre le code actuel avant de le corriger, ne
rien croire sur parole. Onze des douze étaient encore exacts ; le
douzième (connecteurs dormants) était déjà réparé avant l'audit
(`tests/test_connecteurs_dormants.py`, DEC-0068) — revérifié, toujours
exact, laissé tel quel. Décisions et coûts détaillés : `docs/DECISIONS.md`,
DEC-0095. Résumé d'une ligne par étape :

1. Dépendances/CI — conflit `Pillow`/`psutil` réel avec `browser-use`,
   outils natifs manquants en CI (weasyprint/cairosvg/libreoffice/ffmpeg).
2. Huit intentions de chat gérées par `dispatch_request` mais absentes
   d'`AGENTS_SPECIALISES` — reconnues, jamais exécutées.
3. `conversation_id` stable séparé de `run_id` (par exécution) — chaque
   message ouvrait une session mémoire vierge.
4. Repli `test_video.mp4` retiré — une analyse sans fichier fourni
   analysait un fichier de test comme s'il était réel.
5. Idempotence par `run_id` (`JournalExecutions`, 256 entrées, mémoire
   process) contre la reconnexion qui rejoue une action déjà exécutée.
6. Fausse réussite vidéo — sortie ffmpeg jamais vérifiée par `ffprobe`
   avant d'annoncer un montage prêt.
7. `/media/rendered/{nom}` → `{nom:path}` — les sorties dans un
   sous-dossier réel étaient un 404 malgré une URL correcte.
8. Collisions d'upload — `open(..., "wb")` écrasait un fichier existant ;
   `"xb"` + suffixe numérique, testé avec de vrais threads concurrents.
9. Mémoire long terme bornée — `souvenirs()`/`recuperer_semantique()` ne
   regardaient jamais au-delà de la fenêtre importance/récence (500) ;
   complément SQL borné (`candidats_bornes`), limite résiduelle mesurée et
   documentée plutôt que cachée.
10. Quota cloud contourné par un fournisseur imposé (`AI_DEFAULT_PROVIDER`)
    — vérifié maintenant sur CHAQUE chemin ; `CompteurUsage` persiste
    désormais en SQLite (survit à un redémarrage).
11. CORS incomplet — `DELETE` et les en-têtes réels du client
    (`X-Usman-Run-ID`, `Last-Event-ID`) manquaient ; un vrai préflight
    tombait en `400` avant même que la requête ne parte.
12. `docs/RAPPORT_TRAVAIL.txt` (cliché du 25/08/2026, « 12 agents
    d'élite », « fonctionne à 100% ») lu comme une mesure du jour —
    bandeau d'avertissement ajouté, fichier gardé (jamais de purge).

Chaque étape porte son test de régression, confirmé en échec avant
correction et en succès après (`git stash`, jamais supposé). `ruff check .`
propre sur tout le dépôt. Suite Python complète après fusion : **5366
passed, 31 skipped, 52 deselected, 0 failed** (682.82s, mesuré le
12/09/2026). Non vérifiable depuis cet environnement : Ollama réel
(génération/embeddings), persistance réelle de `CompteurUsage` après un
vrai redémarrage sur la machine du propriétaire (seule une simulation l'a
été ici). 12 commits sur `claude/audit-repairs-f7f0478`, PR #197 fusionnée.

## Chunk précédent : DEC-0094 — gitgui, second passage : opérations git mutantes sûres à rejouer

Mission reçue : approfondir DEC-0093 avec ce que la lecture seule ne
couvrait pas — les opérations qui MUTENT le dépôt (stage, commit, branche,
réseau, fusion, conflit), sûres à rejouer (idempotence par identifiant,
section 7 du SPEC.md du dépôt amont gitgui et son `src/agent.rs`, jamais son code copié),
protégées contre une mutation sur un dépôt qui a changé sans qu'on le sache
(précondition de HEAD), vérifiant ce qu'elles ont réellement fait
(postcondition). Audit complet : `docs/audits/gitgui_audit.md`, section
« Second passage ».

`tools/atelier/git_ops.py` (nouveau) : `JournalOperationsGit` (idempotence,
plafonné à 256 comme gitgui), `ErreurPreconditionGit` (refuse AVANT de
muter si le HEAD a changé), `TypeErreurGit` (13 catégories classées par
motif), 18 opérations (`stager`/`desindexer`/`commettre`,
branches/checkout, réseau — `pousser` n'expose AUCUN `force` nu, seul
`force_avec_bail` existe —, fusion/rebase/cherry-pick/revert, tag, stash,
`lire_conflit` à trois côtés, continue/abort détectés jamais devinés).
Câblé jusqu'à 18 nouvelles actions Dioumtoukay.

**Vulnérabilité trouvée en écrivant le module, corrigée avant de
continuer** : un nom de branche `"-D"` passé nu à `git branch <nom>
<depuis>` executait RÉELLEMENT `git branch -D <depuis>` — suppression
forcée de la branche que `depuis` désignait, l'inverse de « créer une
branche ». Mesuré dans un dépôt de test (branche protégée réellement
disparue) avant le correctif : refus de toute référence commençant par `-`
avant de construire la commande, sur chaque paramètre atteignant git comme
référence nue.

Rejeté et documenté (`docs/DECISIONS.md`, DEC-0094) : socket Unix (aucune
frontière de process à traverser, Dioumtoukay/`Atelier` dans le même
process Python), `reset --hard`/`clean -fd`/réécriture d'historique
partagé (hors de la liste d'opérations de la mission, DEC-0038 reste la
seule porte via `Atelier.git()`), une confirmation nouvelle sur les
opérations destructrices (contredirait DEC-0038).

**63 tests nouveaux** : `test_git_ops.py` (47, dont un vrai conflit de
fusion résolu de bout en bout, un vrai rejet non-fast-forward, un vrai
`--force-with-lease` qui refuse tant que le bail est périmé, et 5 tests de
régression sur l'injection par option) ; `test_atelier_git_ops.py` (10,
dont l'idempotence partagée sur la durée de vie d'un `Atelier`) ;
`test_dioumtoukay_git_ops.py` (6, dont un identifiant répété sur DEUX
instances d'agent successives).

## Chunk précédent : DEC-0093 — gitgui audité : état git structuré, checkpoint/restauration pour Dioumtoukay

Mission reçue : étudier `antonellof/gitgui` (MIT, commit `7b08381`) et ne
retenir QUE ce qui rend les agents de codage d'ARENA plus sûrs/autonomes/
transparents sur git — jamais son interface (`iced`/`tiny-skia`/Kitty),
jamais `git2`/libgit2 comme dépendance. Audit complet :
`docs/audits/gitgui_audit.md`.

Nouveau module **`tools/atelier/git_etat.py`** — état structuré
(`EtatGit`/`EtatFichier`/`StatutFichier`/`EtatOperation`, parsing de `git
status --porcelain=v2 --branch`, format stable, aucune dépendance ajoutée),
diff structuré par fichier (`lire_diff()`), et le mécanisme central demandé
par la mission — absent de gitgui lui-même — **checkpoint/restauration**
(`creer_checkpoint()`/`restaurer_checkpoint()`) : granularité FICHIER, un
fichier déjà en désordre au moment du checkpoint n'est jamais touché par une
restauration, même modifié ensuite par l'agent. Câblé dans `Atelier`
(`git_statut`, `git_diff`, `git_checkpoint`, `git_restaurer`) et
`DioumtoukayAgent` (quatre nouvelles `ACTIONS`) — en AJOUT PUR, aucune garde
posée sur `Atelier.git()`/`executer()` : DEC-0038 reste entier. Les branches
protégées (`main`/`master`) sont un champ informatif
(`EtatGit.branche_protegee()`), jamais un refus.

Rejeté et documenté (`docs/audits/gitgui_audit.md`) : toute l'interface
graphique, le thread worker + canal `mpsc` (résout un problème d'UI
qu'ARENA n'a pas), `git2`/libgit2 comme dépendance, stage par hunk/ligne
(aucun besoin agent actuel), rebase interactif/autosquash (irait contre la
demande de refuser le destructeur par défaut), suggestion de message de
commit par LLM (doublon — Dioumtoukay écrit déjà ses commits), publication
GitHub et graphe de commits (doublons ou bénéfice purement visuel).

**34 tests nouveaux, sur de vrais dépôts git** (jamais un raccourci qui
contournerait le parsing réel — vrai `git init`, vrai `git merge` en
conflit, vrai `git rebase` interrompu) : `tests/tools/test_git_etat.py`
(22), `tests/tools/test_atelier_git.py` (7, dont le test qui prouve qu'un
fichier déjà dirty au checkpoint n'est jamais touché), `tests/agents/
test_dioumtoukay_git.py` (5, via la boucle complète de l'agent, jamais un
appel direct qui contournerait le parsing des actions). `ruff check` propre
sur les fichiers touchés. Suite complète : **5256 passed, 31 skipped, 48
deselected, 0 failed** (487.70s, mesuré le 11/09/2026) — exactement +34 sur
la mesure DEC-0091 (5222).

Développé sur une branche fraîche (`claude/gitgui-git-state`, issue
d'`origin/master`) plutôt que sur la branche CASE encore ouverte — éviter de
mélanger deux missions indépendantes dans une seule PR.
## Chunk précédent : DEC-0092 — Case audité et connecté : un ordinateur Linux isolé, jamais un second cerveau

`case-computers/case` audité (dual AGPL/MIT par dossier, commit `133082b`)
— rapport complet `docs/audits/case_audit.md`. `core/connectors/
case_computer.py` (nouveau) : client REST vers l'API de `cased`, 11
capacités (lister/creer/etat/dormir/reveiller/executer_commande/
lire_fichier/ecrire_fichier/naviguer/capture_ecran/detruire), aucune ligne
AGPL copiée. Câblé dans `DioumtoukayAgent` (onze actions `ordinateur_*`) et
dans le registre de connecteurs (`apps/backend/runtime.py` — expose
`/connectors/case/...` automatiquement, aucun routeur neuf).

**Déploiement local réellement fait** (pas seulement conçu) : le
control-plane (`cased`) a tourné pour de vrai dans cette session (Docker
réel, ~215 Mo, `/var/run/docker.sock` monté) — auth réelle (401/200), santé
réelle (`docker:true`), création réellement tentée et honnêtement refusée
(`ImageNotFound`, aucune image de bureau construite — contrainte disque
mesurée : 1,1 Go disponibles dans cette session). Le client MCP DÉJÀ présent
d'ARENA (`core/mcp/transport.py`, zéro ligne neuve) a listé les 25 outils
réels du serveur MCP de Case.

Rejeté et documenté (`docs/DECISIONS.md`, DEC-0092) : l'agent Drive de Case
comme cerveau, MCP comme seul chemin (wake/destroy absents de sa surface),
duplication d'Agent-Reach/Fuji/Lightpanda, VPS (préparé, pas tenté).

**38 tests nouveaux** (34 déterministes + 4 `integration`, tous verts) :
`test_connecteur_case_computer.py` (28, dont 3 contre l'instance Case
réelle), `test_dioumtoukay_case.py` (10, dont 1 faisant tourner la boucle
ENTIÈRE de Dioumtoukay contre le vrai `cased` — mission §52).

## Chunk précédent : DEC-0091 — Trans4mers audité : crash recovery et concurrence pour Dioumtoukay, aucun second runtime

`abhayzangir1/trans4mer` audité (MIT, commit `d0940a9`) — rapport complet
`docs/audits/trans4mer_audit.md`. Dioumtoukay/Atelier restent le runtime
canonique (DEC-0038 : aucune confirmation, aucun chemin interdit, non
re-litigé). Trois manques réels comblés :

1. **Amorce/confirmation** (`core/execution/reprise.py` :
   `Etape.confirmee`, `amorcer()`/`confirmer()`) — une action est
   maintenant journalisée AVANT de tourner, pas après ; une étape jamais
   confirmée (crash en plein vol) est rapportée ÉTAT INCONNU à la reprise,
   jamais un succès ni un échec supposé.
2. **Verrou par fichier** (`tools/atelier/verrous.py`, nouveau) — deux
   tâches qui écrivent le même fichier en même temps (le câblage réel :
   un seul `Atelier` partagé, une boucle `async`) sont sérialisées, jamais
   refusées — un mutex, pas une porte d'autorisation.
3. **Worktrees isolés** (`Atelier.isoler()`/`nettoyer_worktree()`) — `git
   worktree add`/`remove` en shell nu, `.gitignore` protégé, jamais de
   suppression forcée d'un travail non commité.

Rejeté et documenté (`docs/DECISIONS.md`, DEC-0091) : porte d'approbation
humaine et bac à sable de chemins (contrediraient DEC-0038), CQRS complet,
PTY, navigateur/mémoire/RAG/MCP (déjà couverts ailleurs, aucun doublon).

**16 tests nouveaux, chacun avec un sabotage réel** : `test_reprise_amorce.py`
(6, dont un test qui fixe le comportement de l'ANCIEN chemin pour prouver le
manque) ; `test_atelier_concurrence.py` (3, deux VRAIS threads synchronisés
par `threading.Barrier`, verrou neutralisé pour prouver qu'il protégeait
vraiment) ; `test_atelier_worktree.py` (7, vrai dépôt git, vrai `git
worktree`, un fichier non commité qui survit à un nettoyage refusé).

## Chunk précédent : DEC-0090 — Mémoire canonique enrichie (AI Memory Vault audité)

`ai-encryption-tool/ai` audité (MIT, commit `5e6d218c`) — rapport complet
`docs/audits/ai_memory_vault_audit.md`. Aucun second système de mémoire :
tout étend `core/memory/personnelle.py` (`MemoirePersonnelle`), déjà actif
et plus riche que leur modèle (provenance `Nature` FAIT/PREFERENCE/
INFERENCE/CONTEXTE_TEMPORAIRE).

Construit : gouvernance (`Etat` ACTIF/REJETE/ARCHIVE, `rejeter`/`archiver`/
`reactiver`/`supprimer`, migration auto d'une base pré-existante) ;
chiffrement au repos (`core/memory/chiffrement.py`, AES-256-GCM +
PBKDF2-HMAC-SHA256 600k itérations, `Coffre`) ; import ChatGPT/Claude/texte
(`core/memory/import_conversations.py`, toujours `Nature.INFERENCE`,
injection de prompt vérifiée inerte) ; premier serveur MCP d'ARENA
(`core/mcp/memory_server.py`, 6 outils, testé via un vrai sous-processus
stdio) ; API HTTP (`apps/backend/routers/memory.py`).

**Régression trouvée par la suite complète** : `core.mcp.memory_server`
remontait comme orphelin (un serveur MCP est lancé par son client, jamais
importé par ARENA) — ajouté à `SERVICE_LANCE_PAR_LE_PROPRIETAIRE` dans
`scripts/orphelins.py`, compteur de `CLAUDE.md` mis à jour (296/236).

Isolation de projet et efficacité en tokens mesurées (pas supposées) :
réduction **> 90 %** des caractères envoyés sur un cas réel.

## Chunk précédent : DEC-0089 — Tunnet audité, refusé (rien à câbler)

Demandé via un commentaire Reddit. Dépôt réel cloné et lu : ce n'est pas
le petit outil de connexion décrit, mais un produit complet de mise en
réseau maillée (19 crates Rust, licence éclatée AGPL/MPL/Apache,
`Status: In development`). `scripts/lancer_arena.ps1` fait déjà ce que le
besoin décrit (serveur + Tunnel Cloudflare + QR code) — rien câblé, pour
ne pas dupliquer une capacité qui existe et fonctionne.

## Chunk précédent : DEC-0088 — les cinq workflows ComfyUI restants

`image_to_image`, `upscale`, `controlnet_image`, `character_image`,
`image_to_video` — implémentés contre le vrai code source ComfyUI
(`nodes.py`, `comfy_extras/`), promus `STABLE` au même niveau de preuve
que `text_to_image`. Image de référence jamais sur le disque d'ARENA
(`image_base64`, mêmes octets en mémoire que les pièces jointes du chat,
DEC-0019) — `_televerser_images` decode+televerse a ComfyUI juste avant
l'envoi. `verification_modeles` (nouveau) généralise le controle
« modele installe ? » au-dela de `ckpt_name`.

**Sabotage réel** : `_verifier_modeles` neutralisée → 3 tests échouent
(ControlNet absent accepté). Restaurée → 85 tests repassent. 27 tests
nouveaux, régression ciblée 262 passed. Un artefact de manipulation
d'outil (`</new_string>` littéral) trouvé et corrigé à la fin de l'entrée
DEC-0087 dans `docs/DECISIONS.md`. Restart test réel : les six workflows
rendus `STABLE` par `/api/image/workflows`.

**Deux régressions réelles trouvées par la suite complète, pas par les
tests ciblés** : `tests/test_documentation.py` a détecté que l'entrée
DEC-0088 citait deux chemins amont ComfyUI non vendorés avec leur chemin
complet — corrigé une première fois, puis le paragraphe DÉCRIVANT ce
correctif a lui-même recité le motif fautif, cassant le test une seconde
fois. Corrigé à son tour, revérifié (18 passed). Suite complète finale :
**5094 passed, 31 skipped, 48 deselected, 0 failed** (408.91s).

## Chunk précédent : DEC-0087 — ComfyUI comme moteur d'exécution alternatif

`core/production/comfyui_workflows.py` (registre CONTRÔLÉ de workflows —
un seul `STABLE`, `text_to_image`), `core/production/comfyui_strategie.py`
(décision matérielle à six issues, reconnaît le déchargement automatique
de ComfyUI), `core/connectors/comfyui.py` (connecteur HTTP direct — aucun
worker écrit, contrairement à HiDream : ComfyUI est déjà un serveur
complet), `core/production/image_backend_router.py` (choix DIRECT/COMFYUI,
défaut inchangé : `hidream` en premier, repli seulement sur
`NOT_CONFIGURED`). `agents/video/production_agent.py::_soumettre_image`
unifie `generer_image` et l'étape de graphe `hidream_image` sur le même
choix de backend.

**Sabotage réel** : la défense anti-traversée de chemin (`_chemin_contenu`)
retirée → un fichier hors du dossier de sortie attendu est confirmé comme
un succès. Restaurée → refusé, 27 tests repassent. 73 tests nouveaux,
régression ciblée 258 passed. `scripts/orphelins.py` : 292 modules, 233
atteints (+4/+4). Restart test réel : `backend=comfyui` route bien vers
ComfyUI, l'appel par défaut route toujours vers `hidream` (DEC-0085
inchangé) — aucun serveur ComfyUI n'a tourné ici (pas de GPU dans cet
environnement de développement), `NOT_CONFIGURED` honnête à chaque appel.

**Régression réelle trouvée par la suite complète** (pas par les tests
ciblés) : `tests/test_connecteurs_dormants.py` a détecté `comfyui` comme
connecteur sans appelant visible en analyse statique (le nom ne circulait
que dans un tuple). Corrigé en nommant la constante
(`BACKEND_COMFYUI = "comfyui"`), jamais ajouté à `DORMANTS_CONNUS` — le
connecteur EST joignable. Revérifié : 8 passed.

## Dernier chunk documenté avant celui-ci : DEC-0086 — Executive Intelligence

`core/executive/` (dix modules) : décision d'affaires multi-spécialiste,
`OpenExecutive` audité (SenteLabsAI, Apache-2.0), désaccord préservé entre
rôles, calcul déterministe (marge/échéancier/faisabilité). 166 tests, suite
complète mesurée alors : 4991 passed, 0 failed. Détail complet :
`docs/DECISIONS.md`, DEC-0086 ; PR ouverte séparément pour la mise à jour
de ce fichier de mémoire lui-même (`claude/active-work-post-dec-0086`) —
vérifier si elle a fusionné ; si non, son contenu est repris ci-dessus.

## ⚠️ L'historique détaillé entre DEC-0024 et DEC-0085 n'a pas été relu ici

Plus de 150 PR sont passées entre ce chunk et le précédent point vraiment
à jour de ce fichier (DEC-0024, connecteurs Gmail réels — voir
`docs/audits/connecteurs_audit.md`). Le relire correctement exige de
reparcourir chaque PR fusionnée depuis, hors périmètre d'une seule
session. Pour tout le
reste, `docs/DECISIONS.md` (toutes les entrées) reste la source exacte ; ce
fichier est un index, pas l'autorité.

## État à l'instant (2026-08-29 — voir l'avertissement ci-dessus)

| | |
|---|---|
| Branche | `claude/arena-personal-ai-integration-grp0ey` (repartie de `master` à chaque PR fusionnée en cours de session — voir CHANGELOG.md) |
| `master` | PR #26 à #34 fusionnées (DEC-0019, Qwen3-VL) ; DEC-0020 (diagnostic/réparation) prête à pousser |
| Tests | **2011** hors ligne au vert, 21 `integration` désélectionnés (+5 depuis DEC-0020) |
| Lint | `ruff` propre |
| Orphelins | 132 modules, 104 atteints, 28 orphelins — **tous** `__init__.py` vides. Aucun module réel endormi (`apps/pwa/server/` supprimé le 29/08/2026) |

## Dernier chunk : DEC-0020 — diagnostic et réparation, pas de nouvelle capacité

Mission demandée le 29/08/2026 : auditer la dette technique laissée par les
missions précédentes (silences avalés, fuites de ressources, frontières
entre composants, sécurité) et **réparer**, pas ajouter. Détail complet :
`docs/DECISIONS.md` DEC-0020.

Trois défauts confirmés et corrigés, chacun sabote-puis-restauré :
1. `agents/plaquiste/plaquiste_agent.py` — un chemin de plan pouvait
   désigner un fichier du dépôt d'ARENA lui-même (`.env`,
   `config/metier.yaml`) avant d'atteindre OpenTakeoff. Corrigé par
   `chemin_hors_du_depot()`, un contrôle de contention.
2. `core/execution/travaux.py` — l'historique des travaux **finis**
   grossissait sans fin (seul le parallélisme était borné). Corrigé par
   `TRAVAUX_TERMINES_GARDES = 200` + `_purger_les_anciens()`.
3. `core/models/ollama_provider.py` — une ligne de flux Ollama illisible
   disparaissait sans aucune trace (`except Exception: pass`). Corrigé par
   un `logger.debug()`.

Le reste de l'audit (≈50 `except Exception` du dépôt relus un par un,
cycle de vie httpx/MCP, TODO/FIXME/XXX, `shell=True`/`eval`/`exec`/
`pickle`, l'intégration Qwen3-VL relue au niveau du code) n'a rien trouvé
de plus — déjà correct. **Ne pas rouvrir ces composants "pour être sûr"** :
c'est exactement ce que la règle du projet interdit.

## Ce qui s'est fermé avant (PR #26 → #33)

| PR | Ce qui change | Statut |
|---|---|---|
| **#27** | `core/guardian/` — DÉCOUVRE et RAPPORTE (jamais MODIFIE), DEC-0014 | **FERMÉ** — 25 tests unitaires + 6 API, scénario §27 bout en bout |
| **#28** | correctif : `verifier_gardien()` distinguait mal « jamais lancé » de « lancé, rien trouvé » | **FERMÉ** — sabotage/restauration prouvés, +5 tests |
| **#29** | doc seule : la recherche web reste `UNKNOWN` en cloud à cause d'un 403 du bac à sable, pas seulement d'Ollama absent | **FERMÉ** — aucun code touché |
| **#30** | `apps/pwa/server/` supprimé (4 fichiers, 482 lignes) — décidé par le propriétaire depuis son téléphone | **FERMÉ** — 27 orphelins restants, tous `__init__.py` vides |
| **#31** | correctif interface `.writing-text` (mode clair) + DEC-0015 (audit de prompt WanGP) + DEC-0016 (Spec Kit refusé) — bundlées, PR fusionnée avant que chaque commit ait sa propre PR | **FERMÉ** — 35 tests, sabotage prouvé |
| **#32** | DEC-0017 — Agent-Reach refusé (sonde/installateur, rien à intégrer) ; `DeepResearcherAgent` corrigé : 3 recherches en séquence → en parallèle | **FERMÉ** — +1 test, sabotage (0,90 s séquentiel → 0,35 s parallèle) |
| **#33** | DEC-0018 — consolidation des modèles auditée, rien à fusionner (doc seule) | **FERMÉ** — aucun code touché |
| *(suivante)* | DEC-0019 — Qwen3-VL : `agents/vision/vision_agent.py`, intention `VISION`, `OllamaProvider.generate(images=...)`, pièces jointes image (jpg/png/webp/gif) | **FERMÉ** — 33 tests, 2 sabotages |

Mesures 7.2 (phase entière) : **toujours `UNKNOWN`**, structurellement — ne pas
retenter depuis le cloud (Ollama absent, recherche web bloquée par la
politique réseau du bac à sable). Attend son PC, raison déjà écrite dans
`docs/REPRISE.md`. La vision (DEC-0019) attend la même chose : `qwen3-vl:4b`
n'a jamais tourné, aucune image réelle n'a été analysée.

## Diagnostic machine (`doctor.py`), mesuré le 29/08/2026

Sur la machine de l'assistant (cloud, sans Ollama/Docker/ffmpeg/GPU — jamais
présents ici) :

```
[OK]   Python                   version 3.11.15
[ABS]  Environnement virtuel    aucun venv actif
[ABS]  Dependances              1 paquet manquant : uvicorn
[CONF] Cle API                  USMAN_API_KEY absente
[OK]   Inference (hybride)      mode HYBRIDE, tout passe par Ollama
[PANNE] Ollama / Modele rapide / Modele profond / Modele d'embeddings
[ABS]  Carte graphique / ffmpeg (video) / Docker (bac a sable)
[CONF] WanGP (generation video) / Video courte (MPT)
[CONF] Metre de plan (OpenTakeoff)  OPENTAKEOFF_MCP_DIR absent ou dist/server.js introuvable
[CONF] Courrier (Gmail) / Agenda (Calendar)  identifiants Google absents
[OK]   Connaissances metier     31 article(s) tarifes
[ABS]  Documents                dossier vide
```

**La ligne `Metre de plan (OpenTakeoff)` a été vérifiée BOUT EN BOUT** :
OpenTakeoff construit une fois dans cette session (`node`, `npm install`,
`npm run build`, hors dépôt), `OPENTAKEOFF_MCP_DIR` pointé dessus →

```
[OK]   Metre de plan (OpenTakeoff) OpenTakeoff repond : 42 outil(s) annonce(s).
```

`11 capacité(s) indisponible(s)` au lieu de 12. C'est exactement ce que
`scripts/installer_opentakeoff.ps1` produit chez le propriétaire (Windows) —
mesuré ici, jamais supposé. Le reste (Ollama, Docker, WanGP, MoneyPrinterTurbo,
Gmail/Agenda) reste `[ABS]`/`[CONF]`/`[PANNE]` sur cette machine, comme
attendu : rien de tout ça n'y a jamais été installé.

## Ce qui est fusionné dans `master` depuis le 28/08/2026 (PR #21 → #33)

1. `doctor.py` réécrit, puis relié à `sonder()` de chaque connecteur (jamais une seconde logique de santé) ;
2. **chapitre 9 — l'agenda**, **MoneyPrinterTurbo** branché sur l'agent vidéo ;
3. **ARENA hybride (DEC-0009)** : confidentialité 4 niveaux, Groq + DeepInfra, aiguilleur, banc d'essai ;
4. **Réseaux sociaux actifs (DEC-0010)** : méthode extraite de `charlie947/social-media-skills`, rien copié ;
5. **Coordination des tâches (DEC-0011)** : `grok-bot-0.18-reconstructed` refusé (aucune licence) ; `core/execution/coordination.py` écrit sans emprunt ;
6. **OpenTakeoff — métré de plan PDF (DEC-0012)** : transport MCP stdio, sous-ensemble réel, la limite plafond/mur/rampant corrigée sur indication du propriétaire ;
7. **Crochets d'exécution + disjoncteur (DEC-0013)** : idée extraite de DeepSeek Harness (Cordis refusé), premier consommateur réel — coupe court après des échecs consécutifs réels sur un service tombé ;
8. **Gardien de maintenance (DEC-0014)** : idée extraite de live-swe-agent (aucun code d'agent trouvé, refusé) — DÉCOUVRE et RAPPORTE seulement, jamais MODIFIE (commit/PR autonome explicitement hors périmètre, contraire à la règle non négociable du projet) ; correctif ultérieur pour que `doctor.py` distingue « jamais lancé » de « lancé, rien trouvé » ;
9. `apps/pwa/server/` supprimé (décision du propriétaire) ; correctif `.writing-text` invisible en mode clair sur l'interface ;
10. **Hell-Grind-AIGC-Skill (DEC-0015)** : `tools/video/prompt_audit.py` (audit déterministe de prompt, méthode extraite) + `VideoAnalyzerAgent.planifier_scene()` — premier appelant réel de `wan2gp.generer`, jamais invoqué si l'audit trouve une erreur bloquante ;
11. **GitHub Spec Kit (DEC-0016)** refusé — scaffolding de prompts pour agent de codage humain-supervisé, aucun moteur autonome ; câbler « implement » romprait la garantie PR de CLAUDE.md ;
12. **Agent-Reach (DEC-0017)** refusé — sonde/installateur pour agent de codage (yt-dlp, feedparser, Jina Reader, Exa), rien d'unique ; `DeepResearcherAgent` corrigé à la place : 3 recherches séquentielles → parallèles ;
13. **Consolidation des modèles (DEC-0018)** : inventaire audité, rien à fusionner — léger/profond sont des paliers de coût, pas des doublons ;
14. **Qwen3-VL — vision (DEC-0019)** : `agents/vision/vision_agent.py`, intention `VISION`, `qwen3-vl:4b` servi par Ollama (pas `transformers`), pièces jointes image encodées en mémoire jamais sur disque ; correctif au passage : `pwa_gateway.py` ne transmettait aucune pièce jointe à un agent spécialisé.

## Ce qui attend une action du PROPRIÉTAIRE

| Sujet | Ce qu'il faut de lui |
|---|---|
| ~~**`USMAN_API_KEY`**~~ | **Réglé le 12/09/2026 : il a décidé de ne PAS la changer** (« pas besoin de changer la clé »). Ne pas le lui redemander. Tenable parce qu'ARENA écoute sur `127.0.0.1` (mesuré : `scripts/start.ps1`, docstring de `main.py`) et que rien ne publie ce port. **Condition qui l'annule** : `apps/backend/Dockerfile:64` lance `--host 0.0.0.0` — si cette image tourne un jour avec `-p 8000:8000` sur une machine joignable, les deux clés de l'historique public redeviennent de vraies clés d'accès et il faut les changer AVANT d'exposer le port. Détail → `docs/CURRENT_TASK.md` |
| **Purge de l'historique** | jamais autorisée — **sa décision**. Attention : la raison écrite ici était « le dépôt est privé ». Il est **public** depuis le 06/09/2026. Ce qui la rend inutile aujourd'hui n'est plus la confidentialité mais la **mesure du 12/09/2026** : l'historique n'expose aucune clé de fournisseur externe, seulement six secrets dont quatre morts (LibreChat/Open WebUI retirés) et deux clés de l'API locale — à **changer**, ce qui suffit |
| **Identifiants Google** | 3 valeurs dans `.env` pour réveiller courrier + agenda |
| **MoneyPrinterTurbo** | `scripts/installer_moneyprinter.ps1`, puis `llm_provider = "ollama"` et une clé Pexels dans **leur** `config.toml` |
| **OpenTakeoff** | `scripts/installer_opentakeoff.ps1`, puis `OPENTAKEOFF_MCP_DIR` dans `.env` — vérifié bout en bout dans cette session (ci-dessus), il ne reste que le geste chez lui |
| **Interface (PWA)** | `npm run build` dans `apps/pwa/` pour que le correctif du mode clair (PR #31) serve réellement |
| **WanGP** | lancer `python wgp.py --mcp --mcp-transport streamable-http ...` pour que `planifier_scene` (DEC-0015) génère vraiment une scène |
| **Vision (Qwen3-VL)** | `ollama pull qwen3-vl:4b` pour que `VisionAgent` (DEC-0019) analyse vraiment une image — jamais chargé ni mesuré dans cette session (pas de GPU ici) |
| **Mesures 7.2** | `python -m pytest -m integration` et `python scripts/mesurer_performances.py` sur son PC |

## Prochaine action recommandée

**Ne pas ouvrir une nouvelle phase du plan de soi-même.** Le propriétaire donne
la suite. Si elle vient : le plan pointe sur **11.1 — appels d'offres
sénégalais** (`docs/PLAN_ARENA_OS.md`), les chapitres 8, 9 et 10 étant terminés.

## Ce qui n'est PAS à faire

- relire le dépôt entier au début d'une session — cette mémoire existe pour ça ;
- refaire vérifier un système verrouillé « pour être sûr » ;
- marquer quoi que ce soit `100%` sans preuve, ni afficher un chiffre non mesuré ;
- toucher à `apps/pwa/` : l'interface n'a **jamais** été regardée.
