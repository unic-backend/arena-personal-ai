# CHANGELOG - Usman PERSONAL AI

## [Non publié]

### Corrigé et amélioré — 02/09/2026 — Dioumtoukay travaille mieux

Demande du propriétaire, le jour même de la première version : « bien améliorer
dioumtoukay pour qu'il soit fort dans ses travail […] savoir corriger des fail
des bug des erreur ». Quatre manques mesurés sur la version du matin.

- **Il devait réécrire un fichier entier pour en corriger une ligne.** C'était
  le plus coûteux : `ecrire` remplace TOUT, donc changer une ligne dans un
  fichier de six cents obligeait le modèle à les restituer toutes de mémoire —
  et un modèle local de 14 milliards de paramètres n'y arrive pas sans en
  abîmer une. `remplacer` cite le passage exact et ne touche à rien d'autre. Il
  **refuse** un passage introuvable (le modèle a cité de mémoire) ou présent
  plusieurs fois (rien ne dit lequel il visait), et dit quoi faire à la place.
- **La fin des sorties longues était coupée.** `_couper` gardait le début ;
  `pytest` écrit son verdict — « 3 failed » et le nom des tests tombés — sur
  ses toutes dernières lignes. Une suite bavarde faisait donc disparaître la
  seule information qui comptait, et Dioumtoukay concluait « les tests passent »
  sur une sortie amputée. La coupe garde maintenant **le début et la fin**.
- **Il cherchait à l'aveugle.** `chercher` trouve un texte dans les fichiers
  (via `grep`, ou ici même s'il manque) : corriger un bug ne commence plus par
  deviner le fichier.
- **Il ne savait pas où il était.** Le premier tour reçoit maintenant des
  repères mesurés — branche git, fichiers modifiés, contenu de la racine —
  pris **une seule fois**, au départ.

Deux ajouts au rapport et à la mémoire : les **fichiers réellement modifiés**
sont nommés à part (une écriture ratée n'y figure pas), et un travail qui a
modifié quelque chose est retenu en mémoire longue — pas une simple lecture.

Mesuré sur du vrai code GitHub : `git clone` de `pallets/itsdangerous`,
`chercher` y trouve `def dumps` avec son fichier et sa ligne, et le code cloné
s'exécute (`Signer('cle').sign(b'bonjour')` → code 0).

### Ajouté — 02/09/2026 — Dioumtoukay, celui qui agit sur la machine

Demande du propriétaire : « il doit être comme claude code entrer dans mon
terminal mon github et travailler sur le projet ». La décision qui l'autorise
est **DEC-0038** — il a levé DEC-0014 (« découvrir et rapporter, jamais
modifier ») après qu'on lui ait présenté ce que ça coûte, en répondant « il
doit tout faire pas de limite ».

- **`tools/atelier/`** — les mains : lire, écrire, lister, déplacer, exécuter,
  git. Aucun garde-fou, c'est sa décision. Deux choses tenues, qui n'en sont
  pas : **tout laisse une trace** dans `JournalDesActions` (un compte-rendu à
  lire, pas une autorisation à demander), et **un échec se rapporte au lieu de
  se déguiser** — le défaut mesuré le 01/09 dans `tools/docker_local.py`, où un
  code de sortie non nul ne levait pas.
- **`agents/dioumtoukay/`** — la boucle : le modèle rend **une action à la
  fois**, elle est exécutée pour de vrai, et son résultat réel — sortie,
  erreur, code de sortie — revient dans l'invite suivante. Il travaille donc
  sur ce qui s'est passé, jamais sur ce qu'il imaginait. Borné à 12 actions :
  une boucle sans fin est la première façon dont un agent autonome devient
  nuisible.
- **Atteignable depuis l'interface** : nouvelle intention `ATELIER`, nouvel
  espace « Dioumtoukay » dans la barre latérale, et l'aiguillage hors ligne
  reconnaît ses phrases (« range mon dossier… », « lance les tests… »).
  Sans ce branchement, les deux modules précédents seraient du code mort.
- Ce qui le sépare de `RepoEngineerAgent`, qui reste inchangé : celui-là lit et
  propose sans jamais rien modifier. Ici on exécute.

### Corrigé — 01/09/2026 (troisième vague, défauts n° 25 à 29)

- **Deux agents sur trois versaient le texte web brut dans l'invite.**
  `DeepResearcherAgent` et `TrendAnalyzerAgent` laissaient passer une page
  contenant « IGNORE TES INSTRUCTIONS » et une balise `<system>` telle quelle.
  Le module de sécurité avait annoncé le constat : neuf chemins, une seule
  barrière.
- **« WanGP a répondu », quand WanGP venait de refuser** : `isError` n'était lu
  que par un des deux connecteurs MCP. La règle vit maintenant sur `Reponse`.
- **Une réponse MCP en retard pouvait être servie à l'appel suivant** — la
  bonne forme, le mauvais appel. Le contrôle existait, rien ne le tenait.
- **Une conversation trop grosse n'était pas sauvegardée en silence** : le
  serveur nommait le refus, l'interface le jetait.
- **Le serveur bloquait son propriétaire au sixième message d'une minute.**
  Deux requêtes par message, dix par minute : la limite passe à soixante.
- **La lecture seule de `SWEAgent` ne tenait à rien** : `SWEACITool.edit`
  écrivait des fichiers, sans appelant ni test.

### Corrigé — 01/09/2026 (deuxième vague d'audit, défauts n° 14 à 24)

Onze défauts de plus, **tous trouvés sur une suite verte**, tous mesurés avant
d'être corrigés, tous vérifiés par sabotage.

- **Tes prix modifiés n'étaient vus qu'au redémarrage.** `unic_plaquiste.yaml`
  était lu une seule fois, au démarrage du serveur. Le plus coûteux de la
  série : un mauvais prix sur un document qui part chez un client (DEC-0034).
- **Une règle de permission durcie n'était pas appliquée** — et la docstring
  annonçait justement la capacité manquante (DEC-0035).
- **« Espace de connaissances prêt », disait GraphRAG, Docker éteint.**
  N'importe quel échec devenait cette phrase rassurante (DEC-0033).
- **Un flux vide était compté comme un succès** : aucun repli, et l'interface
  annonçait le moteur du tour précédent (DEC-0032).
- **La passerelle OpenAI jetait la conversation** — seul le dernier message
  arrivait au modèle — et toutes les conversations partageaient une mémoire
  (DEC-0031).
- **Un devis conduit depuis un client extérieur ne finissait jamais** : le
  correctif du 31/08 n'avait été posé que sur la PWA.
- **La bulle vide**, corrigée pour LibreChat le 26/08, était vivante sur les
  **trois** autres surfaces — dont celle du propriétaire.
- **Un flux PWA coupé laissait une question orpheline** dans la mémoire, relue
  ensuite pour résoudre une question elliptique.
- **Un Docker démarré après ARENA restait invisible** : la sonde datait du
  démarrage du serveur (DEC-0029).
- **Le diagnostic faisait installer `nomic-embed-text`** quand le code demande
  `bge-m3` depuis le 27/08.
- **Un plan de montage à moitié tombé était annoncé « réussi »** : timeline à
  0 ms, statut `SUCCESS` (DEC-0036).

### Ajouté — 01/09/2026
- `core/fichier_suivi.py` — relecture d'un fichier de configuration sur sa date
  de modification, écrite **une** fois après avoir trouvé la même forme de
  défaut quatre fois dans la même nuit.
- `tools/docker_local.py` — la sonde Docker, partagée par le bac à sable et le
  moteur de graphe. Elle n'existait qu'au premier, et c'est pour ça que le
  second ne la posait pas.
- Comparaison de la clé API en temps constant (`secrets.compare_digest`).
  Durcissement, pas défaut mesuré.

### Ajouté — 01/09/2026 (spécialistes)
- **ARENA applique la méthode du métier concerné.** Sécurité, tests,
  architecture, référencement, contenu, données, produit… douze métiers, chacun
  avec ses étapes, ses contrôles et sa définition de « fini » (DEC-0028).
- **Toujours une seule intelligence** : aucun agent créé, aucune des 319
  définitions du dépôt source copiée. Deux méthodes au maximum par demande, et
  souvent aucune.
- **Aucun spécialiste décoratif** : un test refuse un métier qu'ARENA ne sait
  pas exécuter.

### Corrigé — 01/09/2026 (audit général)
- **Un nom de fichier avec apostrophe cassait l'incrustation des sous-titres.**
  « chantier d'Ouakam » suffisait. Les trois échappements ffmpeg possibles
  perdent l'apostrophe : le fichier est désormais recopié sous un nom sûr
  le temps de l'appel.
- **Une propriété de texte pouvait ouvrir une option ffmpeg.** Un `couleur`
  choisi par le modèle injectait `fontfile=` dans le graphe de filtres ; avec
  `textfile=`, le contenu d'un fichier de la machine pouvait finir incrusté
  dans une vidéo publiée. Les valeurs sont désormais contraintes à leur forme.
- **`/health` taisait six agents**, dont l'assistant devis. La liste écrite à
  la main a dérivé ; elle est désormais dérivée de ce qui existe vraiment.
- **Le bac à sable prenait une image manquante pour une erreur de code** :
  un agent serait parti corriger du code correct.
- **Une recherche qui n'avait rien pu lire répondait « aucun résultat ».**
- **`/api/chat/stream` mourait en silence** quand Ollama tombait : `200` et
  zéro ligne, et une question orpheline laissée dans l'historique.
- **Une recherche documentaire en panne s'annonçait comme une réponse.** Le
  test qui gardait cet espace épinglait le mensonge ; il a été renforcé.
- **La passerelle compatible OpenAI sortait en `500` nu** quand Ollama tombait,
  sur la surface qu'utilisent les outils extérieurs. Elle rend désormais un
  objet d'erreur JSON en 503, et son flux ne meurt plus en silence.
- **Les sous-titres ne s'inventent plus.** Sans transcription, deux phrases
  écrites en dur produisaient un vrai fichier annoncé comme un succès — de la
  réclame pouvait finir incrustée sur une vidéo de chantier. Et « corrigés »
  était écrit même quand la relecture n'avait pas eu lieu.
- **Le sélecteur d'extraits n'annonce plus une détection qui n'a pas eu lieu.**
  Sans analyse, il disait « extrait le plus viral détecté (0 → 15 s) » sur une
  vidéo de 6,7 secondes.
- **Le docteur ne connaissait pas la voix**, et ne se contente plus d'un port
  qui répond : il demande les moteurs.

Rapport complet → `docs/audits/audit_general_2026-09-01.md`.

### Ajouté — 01/09/2026 (audio)
- **ARENA parle et écoute.** « Lis-moi ce texte », « transcris cet
  enregistrement » : la parole et l'écoute passent par VoiceStudio, piloté en
  local par HTTP. Aucune de ses lignes n'entre dans ARENA — il est sous
  AGPL-3.0 (DEC-0027, `docs/audits/voicestudio_audit.md`).
- **Une voix off entre dans une vidéo montée.** Texte → voix → piste audio de
  la timeline → MP4 final vérifié (`h264` + `aac`).
- **Le moteur se choisit sur ce qui est réellement installé**, jamais sur le
  défaut du service — qui pointait vers un moteur absent.
- **Une voix ne sort pas de la machine** : toute adresse non locale pour
  VoiceStudio est refusée.

### Corrigé — 01/09/2026 (audio)
- **Les sous-titres restaient au studio.** La nouvelle intention audio les lui
  prenait ; ARENA les fabrique déjà de bout en bout. Régression trouvée par la
  suite existante, corrigée, et un test la fixe.

### Ajouté — 01/09/2026
- **ARENA sait monter une vidéo, et une phrase suffit.** « Monte-moi un short
  du chantier de Ouakam » devient un plan d'opérations validées, une timeline
  composée, puis un fichier vérifié. Le modèle propose ; il ne pilote rien
  (DEC-0026, `core/montage/`, `agents/montage/`).
- **Le modèle ne peut désigner aucun fichier.** Il choisit parmi les rushes que
  le propriétaire a téléversés, par leur nom seul. Un chemin cité dans un plan
  est refusé même s'il est exact.
- **Une opération inventée n'arrête pas le reste.** Les lignes écartées sont
  nommées une par une ; les autres montent.

### Ajouté — 30/08/2026
- **Les conversations sont les mêmes sur tous ses appareils.** Coffre côté
  serveur (`core/conversations/depot.py`), deux routes authentifiées
  (`GET /conversations`, `POST /conversations/sync`), et synchronisation depuis
  l'interface au démarrage, à la fin de chaque tour et après une suppression.
  La plus récente gagne ; une suppression pose une pierre tombale pour ne pas
  ressusciter au prochain envoi ; une panne réseau ne coûte jamais une
  conversation.
- **Volume persistant Railway** monté sur `/app/data` : la mémoire, le journal
  et les approbations survivent enfin aux redéploiements (DEC-0021).
- **Un `ErrorBoundary` autour de chaque message.** Il n'en existait aucun dans
  l'application : une seule erreur de rendu effaçait tout l'écran.

### Corrigé — 30/08/2026
- **Écran noir sur une réponse de recherche.** Le serveur envoie une adresse de
  source, jamais un domaine ; `DomainMark` lisait `domain.length` dessus. Le
  domaine est désormais déduit de l'adresse à la réception **et** à la lecture
  du stockage, pour réparer aussi les conversations déjà enregistrées.
- **La recherche web ne cherchait pas.** Trois causes empilées : le délai de
  recherche était plus court que ce que l'outil s'accorde (6 s contre 25 s) ;
  la passe `text` filtrée sur la semaine ne cherchait plus la question et
  volait la place de celle qui répond ; et le mot « secret », lu dans une page
  Wikipédia, faisait classer la demande `TRES_SENSIBLE`, ce qui interdit le
  cloud — sans Ollama sur le serveur, plus aucun fournisseur ne pouvait
  répondre.
- **Un nom de champ n'est un secret que suivi de sa valeur.** `FRAGMENTS_SECRETS`
  vient du journal des actions, où ces chaînes sont des *noms de champ* ; les
  chercher dans de la prose confondait « scrutin secret » avec une fuite. Les
  regex de clés, les formulations françaises (mot de passe, IBAN, CVV) et les
  formes possessives classent toujours `TRES_SENSIBLE`.
- `reglage()` retire les espaces et retours à la ligne en fin de valeur : un
  panneau de variables mobile en ajoute, et la clé stockée ne correspondait
  alors plus jamais à celle présentée.
- Renommer ou épingler une conversation met à jour sa date : sans cela
  l'arbitrage de la synchronisation aurait perdu ces changements en silence.

### Sécurité
- La clé de la passerelle ne figure plus dans le dépôt : `librechat.yaml` lit
  `${ARENA_API_KEY}`, que `docker-compose.yml` transmet au conteneur LibreChat.
- Les endpoints métier `/api/upload`, `/api/process-video`, `/api/chat` et
  `/api/chat/stream` exigent la même clé Bearer que `/v1`. Ils étaient ouverts.
- CORS restreint aux interfaces locales (`ARENA_ALLOWED_ORIGINS`) au lieu de `*`,
  méthodes limitées à `GET`/`POST`. Combiné aux endpoints ouverts, `*` laissait
  n'importe quel site appeler les agents depuis le navigateur.
- L'interface `apps/frontend/index.html` envoie la clé et l'oublie si elle est refusée.
- Le bac à sable ne dégrade plus : sans Docker, l'exécution de code est
  **refusée** (`sandbox_mode: REFUSED`) au lieu de basculer sur la machine hôte.
  Le repli reste possible derrière `ALLOW_UNSAFE_EXEC=true`, explicitement.
- `CoderAgent` ne relance plus le modèle pour corriger un code refusé : ce
  n'est pas le code qui a échoué. Il renvoie `status: refused`.
- `EXECUTE_COMMANDS` passe à `false` par défaut, dans `config/permissions.yaml`
  **et** dans `DEFAULT_PERMISSIONS` — un `permissions.yaml` introuvable retombait
  sinon sur la valeur permissive. `.env.example` annonçait aussi l'inverse.

### Déploiement
- `requirements.txt` ne contient plus que les 12 dépendances réellement importées
  par le code. Le `pip freeze` d'origine est conservé dans `requirements.lock.txt`.
- `pywin32` retiré des dépendances directes : plus aucun import ne le référence, et
  il faisait échouer le build Docker Linux. Il garde un marqueur
  `sys_platform == "win32"` dans le lock.
- `langchain-openai` épinglé en `1.1.9` : la `1.6.0` du lock exige `openai>=2.45`
  alors que `browser-use==0.13.8` épingle `openai==2.16.0`. Le couple gelé était
  déjà impossible à réinstaller.

### Tests
- Socle pytest exécutable hors ligne : `tests/conftest.py` fournit un `FakeProvider`
  scripté (aucun réseau, réponses données à l'avance, appels enregistrés) et une
  mémoire SQLite jetable par test. `pyproject.toml` configure pytest, `asyncio_mode`
  et le marqueur `integration`, désélectionné par défaut.
- `requirements-dev.txt` ajoute `pytest` et `pytest-asyncio`.
- Quatre fichiers convertis en vrais tests pytest (assertions au lieu de `print`) :
  permissions, mémoire de conversation, interpréteur local et bac à sable.
  `tests/test_memory_chat.py` n'exécutait plus rien : son appel à `/api/chat`
  partait à l'import et n'affirmait rien. Il teste maintenant la mémoire elle-même.
- Les tests d'isolation Docker du bac à sable portent le marqueur `integration`.
- Trois agents testés hors ligne sur `FakeProvider` : orchestrateur (aiguillage,
  historique transmis au modèle), `CoderAgent` (refus du bac à sable, boucle
  d'auto-correction bornée) et `PublisherAgent` (`PUBLISH` bloqué, publication
  réelle non implémentée).
- Quatre agents de plus testés hors ligne : `TrendAnalyzer` et `DeepResearcher`
  (recherche web doublée, aucun appel réseau), `RepoEngineer` et `SWEAgent`
  (lecture seule vérifiée : toute écriture disque fait échouer le test).
- Tout ce qui exige Ollama, Docker, ffmpeg, Whisper, Chromium ou le réseau porte
  le marqueur `integration` et s'ignore proprement quand le service manque.
  `pytest` est vert par défaut : **103 passed, 17 deselected**.
- `tests/test_api.py` couvre désormais l'authentification des quatre routes `/api`,
  la passerelle `/v1`, une clé vide qui ferme au lieu d'ouvrir, et le CORS.
  Il exigeait `status == "healthy"`, donc Ollama : il vérifie maintenant l'API.
- La vidéo de test est générée dans un dossier temporaire, plus dans `media/source/`.

### Qualité
- `ruff` configuré dans `pyproject.toml` (`E4, E7, E9, F, W, I, B`) et le dépôt passe
  à zéro erreur. 178 corrections automatiques : imports inutiles, imports non triés,
  espaces en fin de ligne, fichiers sans saut de ligne final.
- Trois `raise HTTPException` dans une clause `except` chaînent maintenant leur cause
  (`from e`) ou déclarent explicitement qu'ils la masquent (`from None`).
- `E501` n'est pas activé : l'imposer reformaterait des prompts entiers.

### Infrastructure
- `LICENSE` ajouté : logiciel propriétaire, tous droits réservés. Le dépôt public
  n'avait aucune licence, ce qui laissait le statut juridique implicite.
- CI GitHub Actions (`.github/workflows/ci.yml`) : un job lint + suite hors ligne
  sur Python 3.11, un job qui vérifie que `requirements.txt` se résout encore sur
  3.11 et 3.12.
- `.dockerignore` ajouté : `.env`, `.git`, tests, docs, `data/` et `media/` ne
  partent plus dans le contexte de build.

### Comportement
- L'intention est maintenant classée par le modèle rapide au lieu d'une liste de
  mots-clés. « Explique-moi le **code** de la route », « **Calcule** mon devis » et
  « Quelle **erreur** j'ai faite hier ? » partaient vers le `CoderAgent`.
- Le modèle répond une étiquette d'une liste fermée ; toute autre réponse est
  rejetée. Modèle injoignable ou réponse hors liste → repli sur les mots-clés,
  **annoncé dans les journaux**, jamais silencieux.
- La classification n'est faite qu'une fois par requête : `dispatch_request` et
  `OrchestratorAgent.run` réutilisent l'étiquette au lieu de la recalculer. Sans
  ça, un message de chat coûtait trois appels au modèle au lieu d'un.

### Corrigé
- **L'interface fonctionne désormais sans Internet.** Elle chargeait sa mise en forme
  depuis `cdn.tailwindcss.com` : hors ligne, elle s'affichait sans style — ce qui
  contredisait la doctrine local-first (`DEC-0002`). Mesuré dans un vrai navigateur,
  réseau coupé : l'en-tête faisait **137,875 px au lieu de 64**, le corps n'était plus
  en `flex`. Le fichier est maintenant servi par le backend sur `/static/`.
- `apps/frontend/vendor/PROVENANCE.md` déclare l'origine, la version, la date, la
  taille et l'empreinte SHA-256 du fichier tiers embarqué. Deux tests vérifient que
  le fichier réellement présent correspond à ce qui est déclaré.

- BOM UTF-8 retiré de **37 fichiers** (l'audit en signalait 3). Il rendait la
  première ligne illisible telle quelle : `import httpx` et `import yaml` étaient
  invisibles à un `grep '^import'`, ce qui a failli les faire oublier dans
  `requirements.txt`. `tests/test_encodage.py` empêche leur retour.
- `/api/upload` filtre désormais le type et la taille. Il acceptait n'importe quel
  fichier — un `.exe` comme une vidéo — et lisait tout en mémoire avant d'écrire :
  un fichier de 8 Go occupait 8 Go de RAM. L'écriture se fait par blocs de 1 Mo,
  la mémoire ne dépend plus de la taille du fichier (mesuré : 64 Mo → 2 Mo de pic
  au lieu de 64). Plafond réglable par `ARENA_UPLOAD_MAX_BYTES`.
- Scan de secrets en CI (`gitleaks`), avec deux règles propres au projet :
  les règles standard ne détectaient **pas** la clé de `librechat.yaml`, trop
  courte pour leur seuil d'entropie — c'est-à-dire la fuite qui a déclenché l'audit.
  Deux contrôles : les fichiers actuels, et les commits ajoutés par la branche.
- Limitation de débit sur les quatre routes qui appellent le modèle : 10 requêtes
  par minute et par adresse (`ARENA_RATE_LIMIT_REQUESTS` / `_WINDOW`), réponse 429
  avec `Retry-After`. Fenêtre glissante en mémoire, sans dépendance nouvelle.
- Les refus d'authentification sont journalisés (adresse, route, motif). **La clé
  présentée n'est jamais écrite dans les journaux.**

### Ajouté
- **Lecture des documents** (`tools/documents/reader.py`) : PDF page par page, Word
  (paragraphes **et tableaux** — un devis vit souvent dans un tableau), texte, Markdown
  et CSV. Les deux moteurs documentaires du projet n'acceptaient que du texte brut :
  aucun ne savait ouvrir un PDF.
- Chaque morceau de texte garde son origine (fichier, et numéro de page pour un PDF),
  pour qu'une réponse documentaire puisse citer précisément sa source.
- Un document illisible est **signalé** (`VIDE`, `NON_PRIS_EN_CHARGE`, `ECHEC`), jamais
  remplacé par un résumé de mémoire. Un PDF scanné dit qu'il est scanné.
- `pypdf` et `python-docx` deviennent des dépendances directes.
- **Inventaire des documents** (`tools/documents/inventory.py`) : ce qui est déjà
  indexé, ce qui a changé, ce qui a disparu. Un document inchangé n'est pas
  réindexé — chaque passage indexé occupe la carte graphique.
- Le suivi porte sur le **contenu** (empreinte SHA-256), pas sur la date : recopier
  un fichier ne le rend pas modifié.
- Un document supprimé du dossier est **signalé**, jamais retiré en silence.
- `data/documents/` et `data/rag/` sont exclus de Git. Le dépôt est public :
  un devis client qui y entrerait n'en ressortirait pas. Trois tests le vérifient.
- **Commande d'indexation** : `python scripts/indexer_documents.py`. Elle vérifie
  qu'Ollama répond et que `nomic-embed-text` est installé **avant** de commencer ;
  sinon elle refuse, sans rien indexer ni rien noter.
- La provenance part avec le texte : chaque passage est inséré préfixé de
  `[Source : devis.pdf, page 2]`, pour que le moteur puisse citer précisément.
- Un document que le moteur refuse **n'est pas noté comme indexé** : il est repris
  au passage suivant, au lieu que l'index se croie complet.

- **Pipeline d'information fraîche.** Une question dont la réponse a pu changer
  (dernière version, actualité, qui occupe un poste, prix, météo) n'est plus
  répondue de mémoire : Usman cherche, **lit les pages**, et répond en citant
  ses sources. Nouvelle intention `FRESH_INFO`, nouvel agent `FreshInfoAgent`,
  nouveau modèle `arena-fresh` dans le menu de LibreChat et Open WebUI.
- Sans résultat de recherche, ou sans page lisible, **le modèle n'est pas appelé** :
  Usman le dit plutôt que de répondre de mémoire.
- `tools/search/source_fetcher.py` : lecture d'une page web, refus des adresses
  internes, plafonds de taille et de durée, état explicite en cas d'échec.

### Corrigé
- La réponse de `/api/chat` annonçait `intent: "CHAT"` même quand un agent
  spécialisé avait répondu. L'aiguilleur renseigne désormais l'intention suivie.

### Remanié
- `apps/backend/main.py` découpé : **652 → 61 lignes**. Il n'assemble plus que
  l'application, les origines autorisées, le dossier des rendus et trois groupes
  de routes. Le comportement est inchangé — la table des routes et les dépendances
  attachées à chacune sont figées par `tests/test_surface_api.py`.
- Nouveaux modules : `config.py` (réglages), `runtime.py` (objets partagés),
  `security.py` (authentification, débit, chemins), `prompts.py` (instruction
  système), et `routers/` (`chat`, `media`, `openai_gateway`).
- L'instruction système n'affirme plus « Année actuelle : 2026 », ni le nom du
  président et du premier ministre du Sénégal. Trois valeurs figées dans le code,
  qui deviennent fausses sans que rien ne le signale. Elle donne à la place la
  **date réellement lue sur la machine**, la consigne de ne pas répondre de mémoire
  sur ce qui a pu changer, et les faits que le propriétaire a lui-même enregistrés.

## [1.7.0] - 2026-08-25
### Sécurité
- La passerelle `/v1` exige désormais une clé API (`ARENA_API_KEY` dans `.env`).
  Sans elle, toute requête est refusée (401).
- Validation stricte des chemins vidéo : un fichier hors du dossier `media/`
  est refusé, sur `/api/chat` comme sur `/api/process-video`.
- Bac à sable Docker opérationnel : le code généré par l'IA s'exécute dans
  l'image `usman-sandbox`, sans accès au disque ni à Internet.
- Secrets LibreChat et Open WebUI sortis de `docker-compose.yml` vers `.env`,
  et intégralement renouvelés.
- Les erreurs 403 ne sont plus transformées en 500.

### Corrigé
- LightRAG : chemin d'import corrigé et passage au modèle `nomic-embed-text`.
- GraphRAG : utilise l'image `arena-graphrag` (qui contient réellement GraphRAG)
  au lieu d'une image Python vide.
- SWEAgent : la recherche dans le dépôt utilisait le premier mot de la phrase.
  Elle cible maintenant le nom de fichier cité ou le mot le plus significatif.
- Les agents spécialisés se choisissent dans le menu de LibreChat, et non plus
  par détection de mots courants ("projet", "document"...).
- Connexions SQLite refermées après chaque usage.
- L'adresse d'Ollama et les noms de modèles sont lus depuis `.env`.
- Encodage des accents réparé dans `README.md` et les fichiers `docs/`.

### Maintenance
- Base MongoDB retirée du suivi Git et purgée de l'historique (`.git` : 822 Mo -> 0).
- `requirements.txt` régénéré : 17 -> 174 dépendances réelles.
- Suppression des scripts jetables qui pouvaient écraser le code source.
- Tests : le faux `test_orchestrator.py` (copie du code source) est remplacé par
  un vrai test ; `test_sandbox.py` échoue désormais quand la protection est absente.

### Limites connues
- GraphRAG est prêt mais nécessite l'ajout de documents puis une indexation.
- `SWEAgent` et `RepoEngineerAgent` analysent et proposent : ils ne modifient
  aucun fichier.
- Les deux modèles Ollama (15,6 Go) dépassent les 12 Go de VRAM de la carte :
  Ollama alterne leur chargement.

## [1.6.0] - 2026-08-25
### Ajouté
- Integration de SWEAgent (Princeton NLP ACI Pattern).
- Integration de RepoEngineerAgent (Odysseus / Devin Multi-file Pattern).
- Integration de Browser-Use & Playwright (Navigation Web Autonome).
- Integration de Microsoft GraphRAG & LightRAG (Graphes de Connaissances).
- Integration d'OpenSandbox (Bac a sable Docker isole).
- Integration des interfaces LibreChat (:3080) et Open WebUI (:3000).
