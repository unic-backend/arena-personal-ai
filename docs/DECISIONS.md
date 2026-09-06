# REGISTRE DES DÉCISIONS ARCHITECTURALES (ADR)

## DEC-0001 : Arborescence complète unifiée dès la Phase 0
- Décision : Adopter l'arborescence complète dès le premier jour.

## DEC-0002 : Local-First strict
- Décision : Moteur de réflexion Qwen 3.5:9b sur Ollama / RTX A2000, Transcription Whisper locale, FFmpeg local. Aucune dépendance obligatoire à une API cloud payante.

## DEC-0003 : Sécurité des Publications
- Décision : Par défaut, `PUBLISH=False` et `DELETE=False`. Toute tentative de publication passe en mode Simulation avec génération de brouillons.

## DEC-0004 : Sans bac à sable, l'exécution de code est refusée
- Décision (26/08/2026) : si Docker est indisponible, `SandboxInterpreterTool`
  refuse d'exécuter (`sandbox_mode: REFUSED`) au lieu de basculer sur la machine.
  Le repli reste possible derrière `ALLOW_UNSAFE_EXEC=true`, posé explicitement.
- Pourquoi : le repli silencieux annulait toute la protection. Une autorisation
  ne se devine pas — toute valeur non reconnue vaut « non ».
- Coût si c'est faux : `CoderAgent` et `ReasoningEngine` ne fonctionnent plus
  quand Docker est arrêté. C'est délibéré : mieux vaut une capacité indisponible
  qu'une capacité dangereuse.

## DEC-0005 : Licence propriétaire, tous droits réservés
- Décision (26/08/2026, propriétaire) : le code n'est réutilisable par personne
  pour l'instant. Voir `LICENSE`.
- Coût si c'est faux : aucune contribution extérieure possible. À revoir si le
  projet doit s'ouvrir.
- Réserve : une licence interdit, elle n'empêche pas. Un dépôt public reste
  lisible et copiable ; seul le passage en privé bloque réellement.

---

## 2026-08-27 — ARENA est local. Aucune API d'IA extérieure.

**Décidé par le propriétaire, dans ses mots :**

> « ton devais être local, j'ai pas besoin d'API des autres IA, je fonctionne
> librement. Ces API de OpenAI etc. n'ont pas leur place ici, tout doit
> fonctionner avec mon propre API. »

> « je prévois de louer un serveur simple pour loger mon IA là-bas, pour que je
> puisse utiliser mon IA dans mon téléphone sans besoin d'allumer mon PC. »

> « mon app est d'abord pour moi seul, mais un jour elle peut être déployée
> librement. »

### Ce que cela décide

- **Le moteur est Ollama, sur sa machine ou sur son serveur.** Rien d'autre.
- **Aucune clé d'un fournisseur d'IA extérieur n'entre dans ce dépôt** :
  ni OpenAI, ni Anthropic, ni Gemini, ni Groq, ni Mistral, ni OpenRouter.
  Une variable qui en attend une est une invitation à en mettre une.
- **`apps/pwa/server/` ne doit pas être démarré en l'état.** Son
  `.env.example` porte `USMAN_AI_PROVIDER=openai` par défaut : le lancer
  enverrait ses conversations chez OpenAI. C'est l'inverse de la décision.
- **Un seul backend** : celui d'ARENA (`apps/backend/`), qui parle à Ollama et
  porte les permissions, le journal et les confirmations. L'interface PWA s'y
  branche ; elle ne parle pas à un second serveur.

### Ce que cela n'interdit pas

Le `oauth.py` de `apps/pwa/server/` (522 lignes, Google, GitHub, Slack, Notion,
LinkedIn, Salesforce) reste **utile et récupérable** : l'OAuth relie ARENA aux
comptes du propriétaire, ce n'est pas un fournisseur d'IA. Il sera absorbé dans
le cadre de connecteurs (`core/connectors/`), avec les permissions et le
journal — pas branché tel quel.

### Ce que le serveur loué change

Aujourd'hui ARENA tourne sur `127.0.0.1` : personne d'autre ne l'atteint. Sur un
serveur loué, il est sur Internet, et trois choses deviennent obligatoires plutôt
que souhaitables : **HTTPS**, une **authentification qui résiste à un inconnu**,
et **la rotation des clés encore dans l'historique Git**. À traiter au moment de
la location, pas après.

### Ce que ça coûte si c'est faux

Se priver des modèles cloud coûte de la qualité de rédaction sur les tâches
longues, et coûte les capacités qu'un modèle local ne fait pas (vision fine,
synthèse vocale). Le propriétaire a mesuré ce coût et l'accepte : ses données de
chantier, ses clients et ses devis ne sortent pas de chez lui.

---

## DEC-0006 : GalsenAPI est la source des données du Sénégal, et son attribution voyage avec chaque chiffre

*Décidé le 2026-08-28.*

- **Décision** : intégrer [GalsenAPI](https://github.com/sibylassana95/GalsenAPi)
  (Lassana Siby, licence MIT) comme connecteur en lecture seule
  (`core/connectors/galsen.py`), service `senegal_data`.

### Pourquoi celle-ci

Parce que chaque chiffre y est tracé jusqu'à sa source, et que l'API le dit
elle-même dans ses réponses : la démographie porte `"source_note": "RGPH-5 2023
(ANSD)"`. C'est la règle du projet — rien n'entre sans source — rendue par le
fournisseur lui-même plutôt que reconstituée après coup.

Et parce qu'elle est **publique** : aucune clé, rien à stocker, rien à faire
fuiter. C'est ce qui en fait le premier connecteur réellement opérationnel
d'ARENA, alors que le chapitre 8 reste gelé par la purge des secrets.

### Ce qui a été mesuré, le 2026-08-28

Interrogée depuis la machine de l'assistant : `HTTP 200`, 14 régions,
46 départements, **558 communes**, population totale 18 126 388.

Le chiffre de 558 mérite d'être noté : l'annonce publique du projet parlait de
553 communes, et une capture de son tableau de bord affichait une population de
18 032 473. Aucun des deux n'a été retenu. **C'est l'API qui répond, et sa
réponse est datée** — c'est exactement pour cela que la date de récupération
voyage avec chaque résultat.

### Ce que la licence oblige

MIT, avec attribution explicite à Lassana Siby. L'attribution n'est pas reléguée
à un fichier de licence : elle est jointe à **chaque résultat** rendu par le
connecteur (`detail["source"]`), avec la date de récupération. Une donnée qui
perd son auteur en route n'est plus citable.

### Ce que ça coûte si c'est faux

Si l'API disparaît ou change de forme, ARENA perd sa seule source de données
administratives sénégalaises — la santé passe `EN_PANNE` et le dit, mais aucune
réponse ne sera plus possible sur ces sujets. Le coût est assumé : la solution
serait de mettre les données en cache localement, ce qui poserait aussitôt la
question de leur fraîcheur et de leur date. Tant que ce n'est pas décidé, la
dépendance est réelle et visible.


## DEC-0007 : LibreChat et Open WebUI sont retirés — on ne change pas une clé morte, on retire ce qu'elle ouvrait

*Décidé par le propriétaire le 2026-08-28 : « moi j'utilise plus librechat, j'ai
mon propre interface a moi maintenant ».*

### Le problème

Six valeurs de secrets sont dans l'historique public du dépôt, pour cinq
variables. Quatre d'entre elles — `CREDS_KEY`, `JWT_SECRET`,
`JWT_REFRESH_SECRET`, `WEBUI_SECRET_KEY` — n'existaient que pour deux clients
tiers : LibreChat (port 3080) et Open WebUI (port 3000).

La configuration de LibreChat était la pire du lot : port publié sur toutes les
interfaces, `ALLOW_REGISTRATION=true`, et un `JWT_SECRET` publiquement lisible.
Un `docker compose up` lancé par mégarde ouvrait une interface de chat où
n'importe qui pouvait s'inscrire, avec de quoi forger des sessions.

### La décision

Retirer `docker-compose.yml` et `librechat.yaml`, et sortir les quatre clés de
`.env.example`. Le propriétaire n'utilise plus ces interfaces : son interface
est la PWA, servie par ARENA lui-même.

**Une clé morte ne se change pas : on retire ce qu'elle ouvrait.** La rotation
aurait demandé son PC et cinq valeurs à coller. Le retrait rend la fuite sans
effet, définitivement, sans qu'il ait à toucher quoi que ce soit.

`SECRET_KEY` part avec elles : aucune ligne de code ne la lisait. Une sécurité
morte qui ressemble à une sécurité est pire qu'aucune.

Reste **une** clé vivante, `USMAN_API_KEY` : elle ouvre `/api` et `/v1`,
c'est-à-dire ARENA. Sans elle, la passerelle refuse de servir — elle ne démarre
jamais « ouverte ».

### Ce que ça coûte si c'est faux

S'il veut rouvrir LibreChat ou Open WebUI un jour, il faut restaurer les deux
fichiers depuis l'historique Git — une commande, rien n'est perdu :

```
git checkout <commit-avant-le-retrait> -- docker-compose.yml librechat.yaml
```

Et il faudra alors leur donner des clés **neuves**, jamais celles de
l'historique. Un test le rappelle en échouant si ces fichiers reviennent tels
quels.


## DEC-0008 : MoneyPrinterTurbo tourne A COTE d'ARENA, pas dedans

*Demande du proprietaire le 2026-08-28 : integrer
`harry0703/MoneyPrinterTurbo`, « qu'il execute pour de vrai, pas installer juste
et le laisser dormir », et le mettre sur le modele adapte.*

### La decision

Le projet est **clone a cote** du depot (`scripts/installer_moneyprinter.ps1`),
avec son propre environnement virtuel et sa propre configuration. ARENA lui
parle par son API HTTP (`core/connectors/moneyprinter.py`), et le connecteur est
branche sur **l'agent video** — ce qui touche a la video va a la video.

Aucune ligne de ce projet n'entre dans ce depot.

### Pourquoi pas dedans

Trois raisons, dans l'ordre de ce qu'elles coutent :

1. **Ses cles.** Il a besoin d'une cle Pexels et d'un `config.toml`. Le vendre
   dans notre arborescence ferait entrer une configuration porteuse de secrets
   dans notre historique — celui-la meme qu'on vient de mettre en prive parce
   qu'il en contenait deja.
2. **Ses dependances.** Elles sont lourdes (montage, synthese vocale,
   sous-titrage) et n'ont rien a faire dans `requirements.txt`, qui ne liste
   que ce que ce code importe.
3. **Le precedent existe et il tient.** WanGP est integre exactement ainsi
   depuis le chapitre video : un service local, une API, un connecteur. Deux
   facons d'integrer un service local seraient une de trop.

### Ce que ca coute, et ce qu'il faut savoir

- **`llm_provider` doit valoir `ollama` dans SON `config.toml`.** Par defaut il
  vaut `moonshot` : les scripts video partiraient alors chez un fournisseur
  d'IA, ce que DEC-0002 refuse. Le script d'installation le dit en clair et le
  repete a la fin ; **il ne peut pas le forcer** — ce fichier appartient a
  l'autre projet.
- **Pexels est un service tiers.** Les plans video viennent de chez eux : le
  sujet de la video sort donc de la machine sous forme de mots-cles de
  recherche. Ce n'est pas un fournisseur d'IA, mais ce n'est pas rien, et il
  doit le savoir.
- **Si le service n'est pas lance, rien n'est promis.** Le connecteur rapporte
  `NOT_CONFIGURED` avec la commande de lancement, et `scripts/doctor.py` porte
  une ligne « Video courte (MPT) ».

### Ce que ca coute si c'est faux

Si le projet change son API — le prefixe `/api/v1`, la forme de `GET /tasks/{id}`
ou les etats -1 / 1 / 4 — le connecteur cesse de suivre les generations. Il ne
mentira pas pour autant : une reponse qu'il ne sait pas lire devient un etat
rapporte, pas une video promise. Le contrat lu dans leur code est cite dans le
docstring du connecteur, ce qui rend la verification possible sans le deviner.


## DEC-0009 : ARENA devient hybride — DEC-0002 est amendée, pas annulée

*Décidé par le propriétaire le 2026-08-28 : « Transform ARENA into a HYBRID AI
INFERENCE SYSTEM using local Ollama + Groq + DeepInfra ». Il demande
explicitement de **ne pas retirer Ollama** et de **ne pas le remplacer**.*

### Ce que ça change par rapport à DEC-0002

DEC-0002 disait : **« Rien ne part chez un fournisseur d'IA : c'est une
décision, pas un réglage. »** Cette phrase n'est plus vraie telle quelle, et il
faut le dire au lieu de la laisser pourrir dans le registre.

Ce qui la remplace :

> **Rien de sensible ne part chez un fournisseur d'IA. Le reste peut partir,
> pour la vitesse, et seulement si le réglage l'autorise.**

Ce qui **n'a pas** changé, et qui n'est pas négociable :

- Ollama reste le modèle **par défaut**, le **repli**, et le seul chemin autorisé
  pour ce qui est sensible ;
- un secret (`TRES_SENSIBLE`) ne sort **jamais** — aucun mode, aucun réglage,
  aucune demande explicite ne le fait sortir (`core/models/confidentialite.py`) ;
- sans réseau, sans clé, ou budget atteint : **Ollama**, et ARENA continue de
  répondre ;
- aucune clé n'entre dans le dépôt.

### Les trois régimes

| Mode | Ce qui peut sortir |
|---|---|
| `LOCAL_ONLY` | **rien** |
| `HYBRIDE` *(défaut)* | `PUBLIC` et `PRIVE` |
| `CLOUD_PREFERRED` | + `SENSIBLE` — un choix explicite du propriétaire |

Un mode inconnu **refuse** : devant un réglage qu'on ne comprend pas, sa machine
est la seule réponse sûre.

### Ce que ça coûte si c'est faux

C'est la décision la plus coûteuse du projet si elle se retourne.

- **Une mauvaise classification envoie chez un tiers ce qui n'aurait pas dû
  sortir** — le nom d'un client, un montant, un extrait de courrier. Ça ne se
  rattrape pas : envoyé une fois, envoyé pour toujours. C'est pourquoi le doute
  penche vers sa machine et pourquoi le classement est testé et saboté avant
  d'être cru.
- **La dépense.** Le cloud est à l'usage : un agent qui boucle coûte de l'argent
  réel. D'où les plafonds, et le repli automatique sur Ollama quand ils sont
  atteints — ARENA ne s'arrête pas, il redevient local.
- **La dépendance.** Une réponse rapide obtenue chez Groq n'est pas disponible
  quand Groq ne l'est pas. Le repli n'est pas une politesse : c'est ce qui
  garde ARENA utilisable.

Si le propriétaire veut revenir en arrière, une seule ligne suffit :
`AI_LOCAL_ONLY=true`. La décision reste réversible, et c'est voulu.

### Ce que ça donne réellement — mesuré le 30/08/2026

Jusqu'ici, ce registre ne portait **aucun chiffre** : `scripts/comparer_fournisseurs.py`
existe précisément pour que personne n'écrive « 5× plus rapide » sans l'avoir
lancé. Il a tourné, sur la machine du propriétaire (Windows, RTX A2000) :

| Fournisseur | Modèle | Scène | 1er mot | Total |
|---|---|---|---|---|
| ollama | `qwen3.5:9b` | courte | 48,1 s | 49,1 s |
| ollama | `qwen3.5:9b` | normale | 85,1 s | 87,8 s |
| ollama | `qwen3.5:9b` | longue | `UNKNOWN` | 114,6 s |
| groq | `openai/gpt-oss-120b` | courte | **0,707 s** | 0,711 s |
| groq | `openai/gpt-oss-120b` | normale | **0,349 s** | 0,739 s |
| groq | `openai/gpt-oss-120b` | longue | **0,383 s** | 1,019 s |
| deepinfra | — | — | `ABSENT` | pas de clé |

**Deux ordres de grandeur sur le temps jusqu'au premier mot** — la mesure qui
décide de ce qu'il ressent (règle 3 du script). Une réponse locale se fait
attendre presque une minute avant son premier mot ; la même question chez Groq
répond avant qu'il ait fini de lire sa propre phrase.

Cela ne change **rien** aux régimes ci-dessus : ce qui est sensible reste sur sa
machine, et lentement vaut mieux que dehors. Ce que ces chiffres justifient,
c'est le repli **inverse** — un `HYBRIDE` qui n'utiliserait jamais le cloud
rendrait ARENA inutilisable pour la conversation ordinaire.

Le `UNKNOWN` de la scène longue est à lire tel quel : aucun premier mot n'a été
horodaté sur ce passage. Ce n'est pas « instantané », et ce n'est pas zéro.


## DEC-0010 : d'un dossier de prompts, on extrait la méthode — pas les fichiers

*Demandé par le propriétaire le 28/08/2026 : intégrer
`charlie947/social-media-skills` (MIT) « as ACTIVE, OPERATIONAL capabilities »,
et surtout pas « a folder full of dormant skills ».*

### Ce que ce dépôt est vraiment

17 fichiers `SKILL.md` : des **instructions pour un modèle**. Aucune ligne
exécutable. Les copier dans `skills/` aurait produit exactement ce que la
mission « réveiller ce qui dort » a passé deux jours à corriger — du contenu
qu'aucune phrase du propriétaire n'atteint.

### La décision

**Leur méthode est extraite, leurs fichiers ne sont pas copiés.** Trois
transformations, et chacune change la nature de la chose :

| Dans la source | Dans ARENA |
|---|---|
| des règles en prose (« 20 lignes max », « no em dashes ») | du **code qui compte** — `tools/social/regles.py` |
| deux fichiers `about-me.md` / `voice.md` | des **souvenirs** dans la mémoire personnelle |
| « 32+ post ideas from pillars × formats » | une **combinatoire** qui rend le compte réel |

Le reste — le choix de la capacité, l'enchaînement, l'approbation — passe par ce
qu'ARENA a déjà : l'orchestrateur, le registre de connecteurs, la politique de
permissions, la file d'attente.

### Ce qui n'a PAS été intégré, et pourquoi

| Compétence | Raison |
|---|---|
| `post-scorer`, `reels-scripting` | exigent **Apify** et **Gemini** : déclarées `CONFIGURATION_REQUISE` |
| `gemini-infographic`, `gemini-carousel`, `quote-post`, `youtube-thumbnail`, `graphic-designer` | génération d'images : ARENA n'en a pas |
| `analytics-dashboard` | exige l'historique d'un compte connecté |
| `newsletter-voice`, `pinned-comment` | hors de son usage : il pose des cloisons, il n'a pas de newsletter |

Aucune n'est simulée. Chacune se déclare avec **ce qui lui manque**.

### Ce que ça coûte si c'est faux

Si la source change ses règles, ARENA garde les anciennes : elles sont figées
dans du code, plus dans un `SKILL.md` qu'on relirait. C'est le prix de la
vérifiabilité — et il est assumé, parce qu'une règle qu'on ne peut pas compter
n'en est pas une. Les seuils sont réunis en tête d'un seul fichier, cités depuis
la source, et se changent là.

**Attribution.** La source est sous licence MIT, et elle est nommée dans chaque
module qui en dérive (`SOURCE = ...`). Son dépôt n'est ni copié, ni modifié, ni
redistribué.


## DEC-0011 : `grok-bot-0.18-reconstructed` n'entre pas dans ARENA — sa leçon, si

*Demandé par le propriétaire le 28/08/2026 : intégrer
`b-nnett/grok-bot-0.18-reconstructed` comme couche d'exécution active. Sa
consigne autorisait explicitement à passer outre les conventions du projet,
mais **pas** les « licensing/provenance requirements ».*

### Ce que le dépôt dit de lui-même

Ce ne sont pas des suppositions : c'est écrit dans ses propres fichiers.

- `README.md` : « unofficial, source-oriented reconstruction of the publicly
  shipped Grok Bot 0.18.0 macOS app », « a hacking and research project ». Il
  **télécharge l'application officielle comme entrée de compilation** et
  **conserve le moteur de rendu d'origine**.
- `PROVENANCE.md` : le code est **extrait des binaires livrés** — « emitted code
  or source-path markers, extracted capsules/source maps, shipped strings/
  assets ». Puis, textuellement :

  > **« No upstream source-code license is implied. Do not present reconstructed
  > material as original source or an official build, and complete an
  > independent rights review before public redistribution. »**

### La décision

**Aucune ligne de ce dépôt n'est copiée dans ARENA.**

Il n'y a **aucune licence** qui autorise la réutilisation, et le code provient
de binaires propriétaires désassemblés. Copier cela reviendrait à redistribuer
du code non licencié dans un dépôt qu'on vient de nettoyer — et ça reste dans
l'historique Git pour toujours.

Le propriétaire a autorisé à passer outre les **conventions du projet**. La
provenance n'en est pas une : sa propre consigne l'exclut, et le dépôt source
exige lui-même une revue de droits avant toute redistribution.

### Ce qui a été fait à la place

Le besoin réel derrière sa demande — une **couche d'exécution qui tient l'état
d'une tâche à plusieurs étapes** — est réel, et ARENA ne l'avait pas. Il est
écrit ici, sans une ligne empruntée : `core/execution/coordination.py`.

L'audit a d'ailleurs montré qu'ARENA avait **déjà** presque tout le reste de ce
que la mission énumérait :

| Ce que la mission demandait | Ce qui existait déjà |
|---|---|
| routage d'inférence, repli fournisseur | `core/models/routeur.py` (DEC-0009) |
| exécution locale, bac à sable Docker | `tools/code/sandbox_interpreter.py` |
| MCP | `core/mcp/transport.py` + connecteur WanGP |
| cycle de vie des outils, santé | `core/connectors/base.py` + registre |
| streaming, activité | passerelle PWA + `Execution` |
| suivi d'usage | `core/models/usage.py` |
| **état d'une tâche multi-étapes** | **rien — c'est le manque, il est comblé** |

### Ce que ça coûte si c'est faux

Si une revue de droits établissait un jour que ce code est librement
réutilisable, ARENA aurait écrit lui-même un coordinateur qu'il aurait pu
emprunter. Le coût est quelques centaines de lignes — contre un historique Git
contaminé par du code propriétaire désassemblé, qui ne s'efface pas.

---

## DEC-0012 : OpenTakeoff — le métré d'un plan PDF, comme capacité à côté

*Demandé par le propriétaire le 29/08/2026 : intégrer
`Kentucky-ai/opentakeoff` (Apache-2.0) comme capacité de métré de plans de
construction, réellement utilisée par ARENA — pas installée et dormante.*

### Ce que le dépôt est vraiment

Un vrai moteur de métré, pas une démo : le canvas navigateur et son serveur
MCP (« environ 40 outils ») importent **les mêmes modules** de géométrie
(`web/src/lib`) — vérifié en le construisant et en le faisant tourner contre
son propre plan d'exemple (`demo/sample-plan.pdf`) :

```
$ node dist/server.js   # avec un client MCP qui pilote load_plan, set_scale,
                        # detect_rooms, derive_base, takeoff_summary
detect_rooms : 4 pièces, 1751.92 SF
takeoff_summary.totals.total_sf_net : 1751.92 ; lf_net : 346.44
```

Différence structurelle avec WanGP et MoneyPrinterTurbo (DEC-0008) : son
serveur MCP **ne parle que stdio** (`StdioServerTransport`, lu dans
`mcp/server.ts` et `mcp/Dockerfile` — « Never point a client config at
`npm start`… `node --import tsx` is the whole invocation »), jamais HTTP. Le
transport HTTP d'ARENA (`core/mcp/transport.py`, écrit pour WanGP) ne pouvait
pas s'y brancher tel quel.

### La décision

**Un sous-ensemble réel, jamais les quarante outils.** Le moteur sait aussi
faire cliquer une pièce à la main, marquer un rectangle autour d'un symbole
répété, comparer des révisions — tout ce qui suppose de DÉSIGNER un point ou
un rectangle sur l'image du plan. Un modèle de texte ne voit pas le plan ; lui
faire deviner des coordonnées produirait un métré faux avec l'air d'un métré
juste. Ce qui est branché ne devine aucune coordonnée : `set_scale` avec
l'échelle détectée sur le cartouche, `detect_rooms` (lit les numéros de pièce
déjà écrits sur le plan et flotte chaque pièce lui-même — le même moteur que
le clic humain), `derive_base`, `takeoff_summary`, `export_report`,
`export_marked_pdf`. Compter des portes une à une (`symbol_sweep`,
`count_marks`) ou déduire une ouverture précise (`cut_out`) restent
`SUGGESTION — NON IMPLÉMENTÉE` tant qu'aucun modèle ne peut regarder l'image.

**Un second transport MCP, pas une extension du premier.** `core/mcp/
stdio_transport.py` parle stdio : un processus, pas un port. Il réutilise le
contrat `Reponse` de `core/mcp/transport.py` (même protocole JSON-RPC, seul le
tuyau change) plutôt que de le dupliquer.

**Une limite honnête, écrite dans `agents/plaquiste/metre_plan.py` plutôt que
masquée dans un calcul silencieux — corrigée une fois par le propriétaire lui-
même (29/08/2026)** : la première version confondait « surface au sol » et
« surface de mur », en traitant doublage/habillage/coffre comme un plafond.
Sa correction : *« la surface d'un cloisons c'est largeurs et hauteur »*. Trois
issues, jamais quatre :

1. **plafond plat** (« plafond », « faux plafond ») : sa surface **est**, par
   définition, la surface au sol de la pièce — sans ambiguïté, sans hauteur ;
2. **un mur** (doublage/habillage/coffre = une face ; cloison/séparation, ou
   rien de nommé = deux faces par défaut) : `périmètre mesuré × hauteur`,
   **seulement si une hauteur est donnée** — `detect_rooms` mesure le
   PÉRIMÈTRE ENTIER de chaque pièce (murs porteurs et extérieurs compris), pas
   seulement les cloisons neuves ; chaque réponse qui utilise ce périmètre le
   dit, et demande de corriger la longueur si elle couvre des murs hors scope ;
3. **un rampant**, ou un mur **sans hauteur donnée** : rien n'est chiffré. Un
   rampant suit la pente du toit — ni la surface au sol, ni le périmètre × une
   hauteur verticale ne la donnent.

Six sabotages tiennent ces trois issues (voir le PR) : un doublage compté à
deux faces double sa quantité de matériaux et un test tombe ; un rampant
chiffré depuis le périmètre × hauteur produit un devis faux avec l'air d'un
devis mesuré, et un test le prouve.

**DEC-0008 tenue, adaptée au transport** : rien du dépôt OpenTakeoff n'entre
ici. `scripts/installer_opentakeoff.ps1` le construit à côté ; ARENA lance et
arrête lui-même le processus Node à chaque métré (`OPENTAKEOFF_MCP_DIR`).

### Ce que ça coûte si c'est faux

Un périmètre de pièce présenté comme une surface de cloisons partirait dans
un devis avec un mètre qui a l'air mesuré et ne l'est pas — plus trompeur
qu'un chiffre absent. C'est exactement ce que la limite plafond/cloison
empêche, et que le sabotage du PR vérifie.

---

## DEC-0013 : DeepSeek Harness — l'idée des crochets, pas Cordis

*Demandé le 29/08/2026 : auditer `deepseek-ai/deepseek-harness` (MIT,
« developer preview ») et en extraire ce qui améliore réellement ARENA, sans
imposer son architecture.*

### Ce que le dépôt est vraiment

Cloné et lu dans son propre code, pas seulement son README. `dsh` est un
harnais d'agent en TypeScript/Node, bâti sur **Cordis** — un bus d'évènements
à contexte partagé typé (« everything is a plugin ») où même le cœur (moteur
de tours, registre d'outils, journal de session) est un plugin remplaçable.
Chaque appel d'outil traverse trois « waterfalls » ordonnées —
`tools/pre-execute` → `tools/execute` → `tools/post-execute`
(`packages/core/tools/src/index.ts`) — sur lesquelles des politiques
transverses se greffent sans toucher au cœur : `packages/guard/timeout-policy`
enveloppe l'exécution d'un délai, `packages/guard/repeat-tool-reminder`
détecte un outil rappelé à l'identique. Deux bridges (`packages/hooks/
hooks-claude-code`, `hooks-codex`) traduisent ce même protocole vers des
commandes shell externes, au format `hooks.json` de Claude Code et de Codex.

### La décision : l'idée, jamais le code ni l'architecture entière

Cordis résout un problème qu'ARENA n'a pas : de nombreuses équipes
indépendantes qui publient des plugins dans un même hôte, avec composition à
chaud, profils et bundles. ARENA est un seul dépôt, une seule personne qui le
fait évoluer, huit connecteurs déclarés dans `runtime.py`. Réécrire
`core/connectors/base.py` et `RegistreConnecteurs` en un bus d'évènements
généraliste **créerait un second système de permissions et d'orchestration**
à côté de celui déjà verrouillé et testé — exactement ce que la mission elle-
même interdit (« Do not create two competing permission systems »).

Ce qui est réel et manquant : **rien, dans `core/connectors/base.py`, ne
permet d'observer ou d'intercepter une exécution sans modifier ce fichier
verrouillé.** C'est la seule pièce extraite — traduite en Python, aucune
ligne de TypeScript reprise (Cordis n'a pas d'équivalent direct dans un
runtime synchrone à un seul processus).

### Ce qui a été construit

`core/execution/hooks.py` — `RegistreDeCrochets`, deux points, ajoutés
**après** les quatre contrôles verrouillés (permission → confirmation →
santé → quota), jamais à leur place : `avant_execution` (un veto
opérationnel, jamais une permission — la différence est écrite dans le
`ResultatAction` : `ECHEC`, jamais `DENIED`) et `apres_execution` (un
observateur, jamais un veto). Un crochet cassé ne casse jamais l'appel qu'il
observe.

Premier consommateur réel, jamais démonstratif : `core/execution/
disjoncteur.py`. Aucun module existant ne le faisait — `LimiteurDebit`
plafonne un DÉBIT, pas une SANTÉ ; un service tombé (MoneyPrinterTurbo
arrêté, OpenTakeoff jamais construit, WanGP injoignable) faisait repayer le
délai d'attente complet à chaque appel suivant. Après des échecs consécutifs
**réels** (`NOT_CONFIGURED`/`DENIED`/`NEEDS_CONFIRMATION` ne comptent pas :
rien n'a été tenté contre le service), le disjoncteur coupe court sans
rappeler `_executer()` — mesuré par un test qui vérifie le compte d'appels
réels, pas seulement le résultat rendu.

Câblé dans `apps/backend/runtime.py` : un seul `RegistreDeCrochets` et un
seul `Disjoncteur`, partagés par les huit connecteurs déclarés — comme
`journal` et `file_attente` le sont déjà.

### Ce qui n'a délibérément pas été fait — `SUGGESTION — NON IMPLÉMENTÉE`

| Idée de DeepSeek Harness | Pourquoi elle n'entre pas ici |
|---|---|
| Cordis entier (bus de plugins, profils, bundles) | résout un problème qu'ARENA n'a pas (plusieurs équipes) ; créerait un second système d'orchestration |
| Assembleur de prompt par sections | `composer_instruction()` par agent, et le classement d'intention de l'orchestrateur, font déjà ce que ça vise — chaque agent ne voit déjà que son propre domaine |
| Personas par tâche (mode chantier/recherche/code...) | ce sont déjà les agents spécialisés d'ARENA (plaquiste, email, researcher, coder…), sous un autre nom — les renommer n'ajoute aucune capacité |
| Chargement dynamique de plugins a chaud | la mission elle-même l'exclut (« do not implement unsafe dynamic code loading ») ; `RegistreConnecteurs.declarer()` (fabriques paresseuses, santé mesurée, `orphelins.py` interdit le dormant) est déjà une frontière contrôlée |
| Bridges hooks vers des commandes shell (format Claude Code/Codex) | ARENA est un seul processus Python ; rien n'indique un besoin de crochets en scripts externes |

### Ce que ça coûte si c'est faux

Un disjoncteur qui compterait un `NOT_CONFIGURED` comme un échec couperait un
service jamais configuré après trois tentatives qui n'ont rien tenté —
message trompeur. Un veto qui n'arrêterait pas vraiment `_executer()`
laisserait croire à une protection qui n'existe pas. Les deux sont dans le
tableau de sabotage du PR.

---

## DEC-0014 : Live-SWE-agent — rien à intégrer, un gardien construit à côté

*Demandé le 29/08/2026 : intégrer `OpenAutoCoder/live-swe-agent` comme
« gardien d'ingénierie autonome » — un sous-système qui inspecte, teste,
diagnostique et répare ARENA en continu, y compris à distance quand la
machine du propriétaire est éteinte.*

### Ce que le dépôt contient vraiment

Cloné et inspecté fichier par fichier — pas seulement le README, comme la
mission le demandait explicitement. **Le dépôt ne contient AUCUN code
d'agent.** `LICENSE`, `README.md`, `assets/`, et un dossier `config/` avec
un unique fichier YAML de configuration. Sa propre documentation le dit :

> *« We built Live-SWE-agent on top of the popular mini-swe-agent framework
> with very minimal modifications. To use Live-SWE-agent, simply install
> mini-swe-agent first (...) and use the custom Live-SWE-agent config. »*

Le moteur réel — boucle d'agent, exécution, environnement — est
**`mini-swe-agent`, un second dépôt tiers non fourni ici**. La « self-
évolution », présentée comme l'apport central, est une INSTRUCTION dans le
prompt système du fichier YAML (« you can create your own tools in Python
(...) create a simple edit tool ») — pas un moteur, pas une mémoire, pas
une file de tâches, pas un bac à sable : rien de tout ce que les §7, §14,
§15, §19, §21 de la mission supposaient déjà écrit. Fait notable, mesuré
dans ce même fichier : `agent.mode: confirm` — même le dépôt source fait
confirmer chaque action par un humain par défaut.

### La décision

**Rien n'est copié — il n'y a rien à copier.** L'architecture « gardien
autonome 24/7, avec ouvre-PR et travailleur distant » que la mission
détaille (§9, §18, §19) devrait être écrite intégralement dans ARENA,
quelle que soit la décision : aucune ligne de Live-SWE-agent ne s'y
prêterait.

**Deux parties de la mission restent hors de portée de cette session, et
pour des raisons qui ne sont pas des préférences de style :**

1. **Un gardien qui commettrait des correctifs ou ouvrirait des pull
   requests sans revue** contournerait la règle non négociable de ce
   projet — *« il ne peut pas lancer les tests, la PR est l'endroit où il
   voit ce qui entre »* (`CLAUDE.md`). La mission autorise à faire évoluer
   des conventions internes, mais exclut explicitement de contourner « des
   sauvegardes contre les actions destructrices » — c'en est une.
2. **Un travailleur distant (VPS, Hetzner, Railway) qui tournerait quand
   son PC est éteint** exige un compte, un budget récurrent et des
   identifiants que lui seul peut fournir. Rien ici ne peut décider pour
   lui d'engager une dépense mensuelle récurrente.

Les deux restent `SUGGESTION — NON IMPLÉMENTÉE` : documentées, pas
construites à moitié pour avoir l'air faites.

### Ce qui est construit : la moitié sûre, réelle, jamais démonstrative

`core/guardian/` — DÉCOUVRIR, ENREGISTRER, RAPPORTER. Jamais MODIFIER.

- `diagnostics.py` : trois catégories, chacune sur un outil déjà dans ce
  dépôt — `pytest` (bugs réellement en échec), `ruff --output-format=json`
  (qualité), `scripts/orphelins.py` réutilisé en process (code mort). Une
  « analyse de sécurité » ou « d'architecture » n'existe pas : un champ qui
  rendrait toujours `[]` se ferait passer pour une garantie absente.
- `file_maintenance.py` : mémoire persistante SQLite (§14, §21 de la
  mission) — un même constat revu ne recrée pas une tâche, une tâche dont
  le diagnostic ne trouve plus trace passe `TERMINEE`, jamais supposée.
- `gardien.py` : un cycle — diagnostiquer, dédupliquer, dire ce qui a
  disparu, rapporter (§22). Câblé dans `runtime.py`, exposé par
  `GET /api/gardien/rapport` et `POST /api/gardien/cycle` (même clé, même
  limiteur que `/api/observability`) — déclenché explicitement, jamais une
  boucle `while True` qui tourne seule (§28 de la mission l'interdit
  d'ailleurs elle-même).

### La preuve — le scénario contrôlé du §27, pour de vrai

Un test cassé pour de vrai (`assert 1 == 2`) ajouté à `tests/`, un cycle
réel lancé : `pytest`/`ruff` tournent en sous-processus, le défaut entre en
file (`DISCOVERED`, gravité `P2`, preuve = la trace réelle). Le fichier de
test retiré, un second cycle : la tâche passe `COMPLETED`. **Cette mesure a
elle-même trouvé une vraie régression** — les deux nouvelles routes
avaient cassé `tests/test_surface_api.py`, l'empreinte figée de la
surface HTTP — corrigée avant ce commit, pas après.

### Ce que ça coûte si c'est faux

Un gardien qui dirait « résolu » sans qu'un diagnostic l'ait revérifié
romprait la même garantie que `core/actions/resultat.py` (« un `SUCCESS`
sans preuve ne se construit pas »). Un gardien qui écrirait du code sans
qu'une pull request passe devant le propriétaire retirerait la seule
protection qui l'empêche aujourd'hui de voir un mauvais correctif partir
sans lui. Les deux sont pourquoi ce PR s'arrête où il s'arrête.

---

## DEC-0015 : Hell-Grind-AIGC-Skill — un auditeur de prompt, pas un moteur

*Demandé le 29/08/2026 : intégrer les capacités utiles de « Higgsfield AI /
Hell Grind » comme une capacité réelle de production vidéo dans ARENA.*

### Ce que le dépôt contient vraiment

Aucun lien n'accompagnait la mission — cherché et retrouvé :
`github.com/renmu2017/Hell-Grind-AIGC-Skill` (MIT, Copyright (c) 2026
renmu2017). Cloné et inspecté fichier par fichier.

C'est un **Skill Codex** (le mécanisme de compétence de la CLI OpenAI Codex,
sans équivalent dans ARENA) : `SKILL.md`, son `openai.yaml` (dans agents/), 22 fichiers
`references/*.md` de méthode (architecture de prompt en 7 couches, contrat
de plan en 12 segments, diagnostic d'échec, schéma de projet en 14 tables),
et trois scripts Python — `init_project.py`, `validate_project.py`,
`audit_prompt.py` — **déterministes, sans dépendance tierce, sans réseau,
sans base de données**, comme le dépôt le revendique et comme la lecture le
confirme. `NOTICE.md` est explicite sur ses propres limites :

> *« No original film file, source asset pack, bulk prompt dataset, or
> long project-specific prompt is distributed here. (...) The Hell Grind
> film, original assets, bulk prompt dataset, and project-specific source
> prompts are not included in this repository and are not licensed by
> this repository. »*

**Ce n'est ni un modèle de génération, ni un monteur.** Aucun poids, aucun
appel réseau, aucune primitive ffmpeg — uniquement de la méthode
(documentation) et des vérificateurs de texte locaux.

### Ce qu'ARENA a déjà, vérifié avant d'écrire une ligne

- `core/connectors/wan2gp.py` — génère une **scène** sur WanGP à partir d'un
  prompt (`generer`, paramètre `source`). Câblé dans `runtime.py`,
  enregistré dans `CONNECTEURS_VIDEO`, mais **jamais réellement invoqué** :
  seul le suivi (`suivre_la_generation`) l'utilisait. Aucun appelant
  n'envoyait de prompt de scène avant cette PR.
- `core/connectors/moneyprinter.py` — fabrique une vidéo **complète** sur un
  sujet (script, plans, voix, sous-titres, montage internes à
  MoneyPrinterTurbo). Different problème, connecteur different — la
  distinction est déjà posée dans `video_analyzer_agent.py`.
- `tools/video/{ffmpeg_tool,crop_tool,subtitle_tool}.py` — montage (coupe,
  recadrage, sous-titres).
- `agents/video_analyzer/video_analyzer_agent.py` — un seul agent vidéo,
  responsabilités déjà séparées en son sein (analyser / suivre / fabriquer).

Le vrai manque, confirmé par grep sur tout le dépôt : **rien n'auditait un
prompt avant de le confier à WanGP.** Une génération occupe la carte
graphique plusieurs minutes ; un prompt sans sujet, sans durée ou avec une
caméra verrouillée ET en mouvement dans la même phrase la dépense pour un
résultat qu'il faudra recommencer.

### La décision

**Rien du Skill Codex n'est copié** — `SKILL.md` et son `openai.yaml` (dans agents/)
n'ont pas d'équivalent ni de sens hors de Codex ; ARENA route ses intentions
par mots-clés et par modèle, pas par fichier de compétence. **Le schéma de
projet en 14 tables (`init_project.py`/`validate_project.py`) n'est pas
porté non plus** : dimensionné pour un film de 95 minutes, il dépasse très
largement l'échelle réelle d'ARENA (une poignée de scènes par demande) —
le porter aurait été construire une capacité pour un usage qu'il n'a pas.
`SUGGESTION — NON IMPLÉMENTÉE` si un jour une production à plusieurs scènes
suivies dans le temps devient un besoin réel.

**Ce qui est réellement réutilisable, et qui l'est** : l'auditeur de prompt
(`audit_prompt.py`) — une méthode déterministe, testée, à coût nul, qui
comble exactement le manque mesuré ci-dessus. Porté avec ses catégories de
contrôle et son barème de score inchangés (c'est la partie déjà éprouvée) ;
ses motifs de détection, écrits en chinois/anglais dans la source, sont
retraduits en français/anglais — les prompts de génération s'écrivent en
anglais la plupart du temps, mais Ousmane décrit une scène en français.

### Ce qui est construit : un vrai chemin d'exécution, pas une capacité qui dort

- `tools/video/prompt_audit.py` — `auditer_prompt(texte, support)` : 12
  modules détectés, 10 catégories de problème (sujet manquant, durée
  manquante, fin de caméra absente, audio absent, conflit immobile/en
  mouvement, conflit de caméra, chronologie dépassée, négations
  redondantes, paramètres de plateforme mêlés au prompt, dialogue exact
  sans limite visuelle), score 0–100. Pur, sans effet de bord, testé avec
  20 cas déterministes.
- `agents/video_analyzer/video_analyzer_agent.py` — nouvelle méthode
  `planifier_scene(description)` : audite, puis **n'appelle `wan2gp` que
  si `audit.pret` est vrai** ; sinon rend les problèmes bloquants, sans
  jamais toucher au connecteur. Premier appelant réel de la capacité
  `generer` de WanGP.
- Détection de phrase (`description_de_plan`, motifs `PLANIFIER_SCENE`
  dans l'orchestrateur) : « prépare le prompt de cette scène », « storyboard »,
  « plan de tournage », « découpe en plans » — testée AVANT la fabrication
  complète (`FABRIQUER_VIDEO`), qui partage le verbe « prépare ».

Chemin réel : *phrase du propriétaire → `description_de_plan` → audit
déterministe → (bloqué et expliqué) OU (`registre.executer("wan2gp",
"generer", source=...)`, sous confirmation comme toute génération)*.

### La preuve

```
python -m pytest tests/tools/test_prompt_audit.py tests/agents/test_video_planification.py -q
→ 35 passed
python -m pytest tests/ -q
→ 1972 passed, 21 deselected (1937 avant cette PR)
python scripts/orphelins.py
→ 130 modules, 103 atteints, 27 orphelins (tous des __init__.py — inchangé)
```

Sabotage : le gate d'audit dans `planifier_scene` remplacé par `if False:`
— `test_un_prompt_incomplet_ne_part_jamais` tombe, avec la preuve exacte
qu'un prompt sans durée ni fin de caméra atteint `wan2gp`. Restauré,
revérifié vert.

### Ce que ça coûte si c'est faux

Un prompt mal formé envoyé à WanGP sans audit dépenserait plusieurs minutes
de la carte graphique du propriétaire pour un résultat probablement à
refaire — exactement le problème que `Hell-Grind-AIGC-Skill` documente
avoir rencontré en production réelle, et exactement ce que ce gate empêche
maintenant, avant le premier appel.

---

## DEC-0016 : GitHub Spec Kit — refusé, un problème déjà réglé et hors du métier d'ARENA

*Demandé le 29/08/2026 : intégrer `github/spec-kit` comme « capacité active
de développement et d'ingénierie » d'ARENA — un cycle
spécifier → planifier → découper en tâches → implémenter → converger,
câblé dans l'orchestrateur, pour qu'ARENA « développe et maintienne
elle-même et d'autres projets logiciels ».*

### Ce que le dépôt contient vraiment

Cloné et inspecté fichier par fichier : `github/spec-kit`, MIT
(Copyright GitHub, Inc.), 1.0.0, actif. `src/specify_cli` (≈ 55 000 lignes)
+ des dizaines d'intégrations d'agents (Claude Code, Copilot, Cursor,
Windsurf, Codex...) + un système d'extensions/presets/bundles.

**Ce que c'est réellement, dans les mots du dépôt lui-même** — le README :

> *« Launch your coding agent in the project directory, then: 0. Establish
> your project principles (`/speckit-constitution`)... 1. Specify... 2.
> Plan... 3. Break down... 4. Implement... 5. Converge... »*

et l'extension bug, sur son propre mécanisme :

> *« This extension delivers an opinionated, repeatable bug workflow that
> **any AI coding agent can drive**. »*

Vérifié en lisant sa commande `implement` (223 lignes, dans
templates/commands/ de Spec Kit) : ce n'est
pas un moteur — c'est un **prompt**, un texte d'instructions que l'agent de
codage **déjà présent dans la session de l'humain** (Claude Code, Copilot...)
suit lui-même, avec **ses propres outils** (lire, écrire, exécuter, tester),
sous **la même supervision humaine que n'importe quelle session de codage**.
Spec Kit ne contient aucun exécuteur autonome : `specify_cli` scaffold des
fichiers et des commandes ; c'est l'agent de codage — piloté par un humain —
qui fait le travail. Exactement ce que cette session (Claude Code, sur ce
dépôt, sous ta revue via pull request) fait déjà.

### Ce qu'ARENA a déjà, vérifié avant d'écrire une ligne

Cette même session a déjà tranché, il y a quelques échanges, la question
que ce dépôt repose sous un autre nom :

- **DEC-0014 (Live-SWE-agent, 29/08/2026)** a déjà refusé qu'ARENA modifie
  du code de façon autonome — « une garde qui commettrait des correctifs ou
  ouvrirait des pull requests elle-même contournerait exactement la
  garantie que CLAUDE.md pose comme non négociable ». `core/guardian/`
  DÉCOUVRE et RAPPORTE, ne MODIFIE jamais.
- **`core/actions/resultat.py`** interdit déjà la construction d'un
  `SUCCES` sans preuve — plus strict que la « convergence » de Spec Kit,
  qui reste une vérification déclarative faite par l'agent, pas une
  contrainte imposée au type lui-même.
- **`core/execution/coordination.py` (DEC-0011)** suit déjà un état de
  tâche à plusieurs étapes, sans rien emprunter à `grok-bot`.

Le §11 de cette mission le dit lui-même : *« If ARENA already has planning;
task management; reasoning; testing; auditing; convergence — do not build
duplicate competing systems. »* C'est exactement la situation.

### La décision

**Refusé.** Pas pour une question de licence (MIT, dépôt actif, rien à
reprocher) — pour deux raisons qui ne sont pas des préférences de style :

1. **La seule étape de Spec Kit qui n'existe pas déjà dans ARENA sous une
   forme plus stricte est « implement » — écrire et modifier du code.**
   Câbler ça dans l'orchestrateur d'ARENA pour qu'elle « développe et
   maintienne elle-même » romprait la même garantie non négociable que
   DEC-0014 vient de protéger : *« il ne peut pas lancer les tests, la PR
   est l'endroit où il voit ce qui entre »* (`CLAUDE.md`). Un ARENA qui
   écrit et fusionne du code sans passer par une pull request qu'il revoit
   n'est plus le produit que ce dépôt construit.
2. **« Développer et maintenir d'autres projets logiciels » n'est pas le
   métier d'ARENA.** ARENA est l'assistant personnel d'un plaquiste à
   Dakar — devis, vidéo, documents, réseaux sociaux, courrier, agenda. Rien
   dans son métier n'appelle une capacité générique d'agent de codage
   autonome ; en construire une ferait d'ARENA un produit différent de
   celui que `CLAUDE.md` décrit, sans qu'on le lui ait demandé.

Rien n'est câblé, aucun `.specify/` n'est copié dans le dépôt : une copie
non branchée serait exactement l'« intégration dormante » que la mission
elle-même interdit (§10) — mieux vaut refuser proprement que fabriquer un
dossier qui ne sert à rien.

### Ce qui reste vrai, et ce qui ne l'est pas

Le triage tâche-simple / tâche-moyenne / tâche-complexe que la mission
décrit (§5) est une bonne discipline — mais c'est déjà celle que cette
session applique à chaque mission de ce fichier `DECISIONS.md` : un
correctif d'une ligne se pousse directement, une intégration de dépôt tiers
passe par audit → décision → implémentation → tests → preuve. Le formaliser
en templates Markdown dans ce dépôt (à la façon de `docs/REGLES_DE_TRAVAIL.md`)
est possible, mais ce serait un gabarit pour les sessions futures de Claude
Code sur CE dépôt — pas une capacité de l'ARENA déployée, et ce n'est pas ce
que la mission demandait. `SUGGESTION — NON IMPLÉMENTÉE`.

### Ce que ça coûte si c'est faux

Construire un « agent de codage autonome » à l'intérieur d'ARENA sans
passer par la revue humaine referait exactement l'erreur que le
propriétaire a déjà cadrée dans `documents/RUNBOOK_PURGE_SECRETS.md` et
`CLAUDE.md` : une action irréversible (du code fusionné) prise sans qu'il
ait pu la voir passer. C'est le même coût que DEC-0014 a déjà refusé de
payer ; refuser une seconde fois, pour un dépôt différent qui pose la même
question, coûte une session de moins qu'une capacité qu'il faudrait
démanteler ensuite.

---

## DEC-0017 : Agent-Reach — rien à intégrer, la recherche existante corrigée à la place

*Demandé le 29/08/2026 : unifier les capacités de recherche déjà présentes
dans ARENA (recherche web, navigateur, recherche profonde) avec
`Panniantong/Agent-Reach`, sans dupliquer, en parallélisant ce qui peut
l'être et en fusionnant les résultats en une seule réponse structurée.*

### Ce que le dépôt contient vraiment

Aucun lien fourni — la mission commençait à la section 20, sans les
sections 1 à 19 qui auraient normalement nommé le dépôt. Retrouvé par
recherche : `github.com/Panniantong/agent-reach` (MIT, Copyright (c) 2025
Agent Eyes), cloné et audité fichier par fichier plutôt que supposé depuis
son README.

**Ce que chaque canal fait réellement, vérifié en lisant le code, pas
la description** :

| Canal | Ce qu'il fait vraiment |
|---|---|
| `youtube.py` | sonde si `yt-dlp` (un outil tiers indépendant) est installé et fonctionnel — ne récupère rien lui-même |
| `rss.py` | sonde si `feedparser` (bibliothèque Python standard) est importable — ne parse rien lui-même |
| `web.py` | route toute page vers **Jina Reader** (`r.jina.ai`), un service cloud tiers |
| recherche « tout le web » | route vers **Exa**, un service cloud tiers (`mcp.exa.ai`), malgré la mention « gratuit, sans clé » |
| Twitter, Reddit, Instagram, Facebook, Xiaohongshu | exigent les cookies de session du propriétaire, extraits de **son propre navigateur** |

`core.py` le dit de lui-même dans sa docstring : *« This class provides
health-check functionality »*. Agent-Reach n'est ni un moteur de recherche
ni un moteur de récupération : c'est une **couche de diagnostic et
d'installation pour un agent de codage** — elle vérifie que des outils déjà
indépendants (`yt-dlp`, `feedparser`, `gh`) sont présents et configurés,
puis dit à l'agent de codage (Claude Code, Copilot...) quelle commande
lancer. Le travail réel est fait par ces outils tiers, pas par Agent-Reach.

### Ce qu'ARENA a déjà, vérifié avant d'écrire une ligne

Trois agents de recherche existent, chacun avec sa responsabilité — aucune
« recherche A → B → C → D » qui se marche dessus : l'orchestrateur choisit
UNE branche par intention (`FRESH_INFO`, `DEEP_RESEARCH`, `TREND_SEARCH`),
jamais les quatre à la fois. Le problème que la mission redoute (plusieurs
chercheurs qui tournent pour la même question) n'existe pas dans
l'architecture actuelle.

- **`FreshInfoAgent`** (313 lignes) : le plus abouti des trois — recherche
  bornée dans le temps, lecture de pages **déjà en parallèle**
  (`asyncio.wait` avec annulation des pages lentes), repli sur les extraits
  du moteur quand aucune page n'est lisible, extraction du passage
  pertinent (pas juste le début de la page), contenu externe **enveloppé**
  (`TrustLevel.EXTERNAL`) avant d'atteindre le modèle, jamais de réponse
  sans source. Rien à améliorer ici sans preuve d'un défaut — traité comme
  **FERMÉ**.
- **`TrendAnalyzerAgent`** (56 lignes) : une seule requête. Aucun gain de
  parallélisme possible.
- **`DeepResearcherAgent`** (77 lignes) : **un vrai défaut trouvé** — trois
  requêtes issues du plan de recherche étaient lancées **séquentiellement**
  (`for q in queries: self.search_tool.search(...)`), exactement le
  problème que la mission décrit en §22.

### La décision

**Rien d'Agent-Reach n'est intégré.** Pas pour la licence (MIT, rien à
reprocher) : parce qu'il n'y a rien à intégrer qui n'existe pas déjà,
séparément et plus proprement, ailleurs :

- Les canaux zero-config (`youtube.py`, `rss.py`) ne sont que des sondes
  vers des bibliothèques déjà indépendantes. Si ARENA veut lire une
  transcription YouTube ou un flux RSS, la bonne intégration est un
  connecteur direct vers `yt-dlp`/`feedparser` — pas une dépendance vers
  un outil de bootstrap d'agent de codage qui, lui-même, ne fait que
  vérifier leur présence. `SUGGESTION — NON IMPLÉMENTÉE` : hors du
  périmètre demandé (« unifier l'existant »), ce serait une nouvelle
  capacité, avec son propre installateur et sa propre décision.
- La recherche « tout le web » et la lecture de page passeraient par des
  services cloud tiers non revus (Exa, Jina Reader) — exactement le genre
  de dépendance silencieuse que DEC-0009 a explicitement encadrée
  (confidentialité classée, jamais par défaut) pour Groq/DeepInfra. Les
  activer sans la même revue romprait cette discipline.
- Twitter/Reddit/Instagram/Facebook/Xiaohongshu exigent les cookies de
  session **personnels** du propriétaire, extraits de son navigateur — une
  question de consentement et de portée qui lui revient, pas une décision
  que cette intégration peut prendre pour lui.

**Ce qui est corrigé, réellement, dans l'existant** : le vrai défaut trouvé
en auditant — `DeepResearcherAgent` lançait ses trois recherches en
séquence. Corrigé avec `asyncio.gather` + `asyncio.to_thread`, aucune
nouvelle dépendance, aucun nouveau risque.

### La preuve

```
python -m pytest tests/agents/test_deep_researcher.py -q
→ 6 passed (nouveau : test_les_trois_requetes_tournent_en_parallele)
```

Nouveau test : trois recherches truquées à 0,3 s chacune. Séquentiel :
0,90 s (mesuré par sabotage — le `for` restauré temporairement fait tomber
le test avec l'écart exact). Parallèle : 0,35 s pour l'ensemble du test.

Sabotage : le `asyncio.gather` remplacé par le `for` séquentiel d'origine
→ `test_les_trois_requetes_tournent_en_parallele` tombe avec
`0.90 s ... elles n'ont pas tourne en parallele`. Restauré, revérifié vert.

### Ce que ça coûte si c'est faux

Prétendre avoir « unifié la recherche » en ajoutant une dépendance vers un
outil qui ne fait que sonder d'autres outils n'aurait rien changé de
mesurable — un dossier de plus, aucune capacité de plus. Le seul gain réel
mesurable était dans le code déjà là, pas dans le dépôt qu'on demandait
d'ajouter.

---

## DEC-0018 : consolidation des modèles — rien à fusionner, déjà minimal par conception

*Demandé le 29/08/2026 : classer les modèles d'ARENA par groupe de capacité
(raisonnement, code, vision, embeddings, audio, génération vidéo) et, pour
chaque groupe qui contiendrait plusieurs modèles redondants, déterminer
s'ils peuvent être fusionnés (poids, LoRA, distillation...) en un seul
moteur le plus fort possible.*

### L'inventaire réel, mesuré dans le code — pas supposé

```
apps/backend/config.py:
  MODELE_RAPIDE = "qwen2.5-coder:14b"   (voie LEGERE)
  MODELE_PROFOND = "qwen3.5:9b"          (voie PROFONDE)
  GROQ_MODELE = "llama-3.3-70b-versatile"       (cloud, repli, opt-in)
  DEEPINFRA_MODELE = "meta-llama/Llama-3.3-70B-Instruct"  (cloud, repli, opt-in)

core/memory/semantique.py:
  MODELE_EMBEDDINGS = "bge-m3"           (Ollama, local)

tools/audio/transcription_tool.py:
  faster-whisper, taille "tiny"          (CPU, local)
```

**Aucun modèle de vision. Aucun modèle de génération vidéo possédé par
ARENA** — WanGP et MoneyPrinterTurbo sont des outils tiers appelés par
connecteur (`core/connectors/wan2gp.py`, `moneyprinter.py`) : ARENA n'a ni
leurs poids ni leur code d'entraînement, il n'y a donc rien qui *lui*
appartienne à fusionner ou distiller dans ces deux groupes.

### Classement par groupe (taxonomie de la mission)

| Groupe | Modèles trouvés | Nombre |
|---|---|---|
| A — Raisonnement général | `qwen3.5:9b` (local, profond) ; `qwen2.5-coder:14b` (local, léger) ; Llama 3.3 70B chez Groq et DeepInfra (cloud, repli, opt-in) | 4 emplacements, **0 redondance de même rang** |
| B — Code | `qwen2.5-coder:14b` — **le même modèle que la voie légère du groupe A**, vérifié : `apps/backend/runtime.py:230` cable `CoderAgent` sur `fast_provider` | 1, déjà partagé avec A |
| C — Vision | aucun | 0 |
| D — Embeddings / retrieval | `bge-m3` | 1 |
| E — Audio | `faster-whisper` (tiny) | 1 |
| F — Génération vidéo | aucun modèle possédé (WanGP/MoneyPrinterTurbo sont des outils tiers, pas des poids ARENA) | 0 |

### La décision

**Rien n'est fusionné, rien n'est distillé.** Chaque groupe contient soit
zéro modèle, soit un seul, à une exception près (groupe A) qui n'est pas
une redondance mais une architecture de coût **déjà documentée et
délibérée** — la fusionner casserait une garantie déjà écrite, pas
seulement inutile :

**`qwen2.5-coder:14b` et `qwen3.5:9b` ne sont pas deux modèles qui font le
même travail.** `core/execution/voies.py` le dit dans ses propres règles :

> *« Une question simple n'atteint jamais le raisonnement profond. »*
> *« Les budgets croissent avec la voie, sur toutes les dimensions. Une
> voie plus profonde qui s'autoriserait moins que la précédente serait une
> erreur de table, pas un réglage. »*

Fusionner les deux en « le plus fort des deux » ferait payer à *chaque*
question — y compris « bonjour » — le coût GPU et la latence du modèle
profond. C'est exactement l'inverse de ce que la phase 7.1 (DEC déjà
actée) a construit : un palier bon marché pour ce qui est simple, un
palier coûteux réservé à ce qui le mérite. La mission elle-même l'interdit
— *« If two models perform different jobs, DO NOT merge them »* — et ici,
« répondre vite et pas cher » et « raisonner longtemps » sont deux jobs,
pas un.

**Groq et DeepInfra ne sont pas deux fournisseurs redondants à fusionner
non plus.** `core/models/routeur.py` documente sa propre raison d'être :

> *« Puis le repli, dans cet ordre : Groq → DeepInfra → Ollama. Il s'arrête
> au premier qui répond, et il ne boucle jamais. »*

C'est une chaîne de **repli infrastructurel** (l'un est indisponible, on
essaie l'autre), pas deux intelligences qui tournent pour la même question
— et ARENA ne possède les poids d'aucun des deux : il n'y a rien à
fusionner chez un fournisseur cloud tiers.

**`qwen2.5-coder:14b` n'a pas besoin d'être « consolidé » avec un modèle de
code séparé, parce qu'il n'y en a pas** : `CoderAgent` utilise déjà ce même
modèle (`runtime.py:230`, `provider=fast_provider`). Groupe A et groupe B
partagent déjà un seul moteur — la mission demande la conclusion à
laquelle ARENA était déjà arrivée, pour une raison différente (limiter le
nombre de modèles à charger sur 12 Go de VRAM, DEC-0002).

### Pourquoi ARENA n'a jamais eu de doublons à consolider

Ce n'est pas un hasard : DEC-0002 (local-first strict) et la contrainte
matérielle (RTX A2000, 12 Go de VRAM) ont empêché dès le départ d'accumuler
plusieurs modèles par domaine — charger un deuxième modèle de 9-14B a un
coût réel et immédiat sur cette carte. « Un modèle par palier, un modèle
par domaine » n'est pas une simplification a posteriori : c'est la
contrainte qui a toujours gouverné ce dépôt.

### Ce que ça coûte si c'est faux

Fusionner ou distiller sans preuve d'une vraie redondance produirait soit
un modèle plus lent et plus coûteux pour les questions simples (en
écrasant la voie légère), soit une opération d'ingénierie ML (poids,
tokenizer, famille de modèle, infrastructure d'entraînement) tentée sans
aucun gain de capacité à en attendre — un risque réel pour un bénéfice
nul. Le coût de ne rien faire ici est zéro : rien n'était redondant.

---

## DEC-0019 : Qwen3-VL — ARENA voit une image, pour de vrai

*Demandé le 29/08/2026 : construire la capacité de vision qui manquait,
d'après le dépôt officiel `QwenLM/Qwen3-VL`, en respectant le matériel
local (RTX A2000, 12 Go de VRAM) et l'architecture déjà en place.*

### Ce que le dépôt contient vraiment

Cloné et audité : `github.com/QwenLM/Qwen3-VL` (Apache 2.0). Le dépôt est
composé de cookbooks (notebooks de demonstration — OCR, document parsing,
grounding, video understanding, computer use...), d'un outil de fine-tuning
(`qwen-vl-finetune`), d'un petit paquet utilitaire (`qwen-vl-utils`) et
d'un demo web. **Aucun poids de modèle** — normal, ils vivent sur
HuggingFace/ModelScope, pas dans un dépôt Git. Le quickstart officiel
charge le modèle via `transformers` (`AutoModelForImageTextToText` +
`AutoProcessor`), pensé pour un GPU de datacenter, pas pour 12 Go de VRAM
partagés avec deux autres modèles déjà installés.

**Six tailles publiées** (2B, 4B, 8B, 30B-A3B MoE, 32B, 235B-A22B MoE),
chacune en édition Instruct et Thinking (raisonnement prolongé). Le plus
gros modèle n'est pas retenu par défaut — la mission le demandait
explicitement.

### Le choix : Ollama sert Qwen3-VL, pas `transformers`

Vérifié avant de choisir, pas supposé : `ollama.com/library/qwen3-vl`
publie des tags GGUF prêts à l'emploi — `qwen3-vl:4b` (4,44 Md de
paramètres, quantification Q4_K_M, **3,3 Go** de téléchargement) et
`qwen3-vl:8b-instruct` (8,77 Md, Q4_K_M, **6,1 Go**), tous deux avec un
contexte de 256K et une entrée texte+image.

**Retenu : `qwen3-vl:4b`.** Ollama est déjà « le défaut, le repli, et le
seul chemin autorisé » pour tout ce qui est local dans ce projet
(`core/models/routeur.py`) — vendre `transformers`/`qwen-vl-utils` comme
un second moteur d'inférence à côté d'Ollama aurait dupliqué toute
l'infrastructure de chargement de modèle pour un seul cas d'usage. Le 4B
laisse une marge confortable à côté de `qwen2.5-coder:14b` et `qwen3.5:9b`
sur la même carte ; le 8B (`VISION_LOCAL_MODEL=qwen3-vl:8b-instruct`) reste
un réglage possible si sa machine a la marge — jamais le défaut, comme
demandé.

**Pas de palier cloud.** `GroqProvider`/`DeepInfraProvider` ne servent
aucun modèle de vision dans ce projet — les y faire transiter aurait
répondu sur le texte seul, en perdant l'image en silence. Vision reste
donc strictement locale ; un palier distant reste `SUGGESTION — NON
IMPLÉMENTÉE` si Groq/DeepInfra proposent un jour un modèle de vision et
que le propriétaire le demande.

### Ce qu'ARENA avait déjà, vérifié avant d'écrire une ligne

Une image jointe à la conversation était **rejetée d'entrée** :
`apps/backend/pieces_jointes.py` ne reconnaît que des formats texte
(`tools/documents/reader.py` : PDF, DOCX, TXT, MD, CSV — utilisé aussi par
LightRAG/GraphRAG, qui n'acceptent que du texte). Une photo tombait donc en
`NON_PRIS_EN_CHARGE`, sans faire tomber la conversation, mais sans jamais
être comprise non plus.

Autre défaut trouvé en auditant, distinct du premier : quand un agent
spécialisé était choisi (`AGENTS_SPECIALISES`), la passerelle PWA
construisait un `ChatRequest` **sans les pièces jointes** — même une fois
le format image reconnu, l'image ne serait jamais arrivée jusqu'à l'agent.
Corrigé au même endroit (`apps/backend/routers/pwa_gateway.py`).

### Ce qui est construit : un chemin réel, de la phrase au modèle

1. **`apps/backend/pieces_jointes.py`** — une image (`.jpg/.jpeg/.png/.webp/.gif`)
   ne passe plus par `tools/documents/reader.py` (qui resterait
   text-only, pour ne pas faire dériver LightRAG/GraphRAG) : ses octets
   sont encodés en base64 **directement en mémoire**, sans jamais toucher
   le disque — plus stricte que la règle de vie privée déjà en place pour
   un document (`PieceJointe.image_base64`, exclu de `to_dict()`).
2. **`core/models/ollama_provider.py`** — `OllamaProvider.generate()` gagne
   un paramètre optionnel `images` (base64, format `/api/generate`) ; le
   contexte passe de 4096 à 8192 jetons uniquement quand une image est
   présente. Rétrocompatible : tous les appelants existants n'y touchent
   pas.
3. **`agents/vision/vision_agent.py`** — `VisionAgent` : sans image jointe,
   il le dit et ne devine rien ; Ollama éteint, il le dit
   (`NOT_CONFIGURED`) ; le modèle de vision non installé (Ollama refuse la
   requête), il le dit avec la commande `ollama pull qwen3-vl:4b` ; une
   consigne écrite sur l'image elle-même est traitée comme une donnée,
   jamais comme un ordre — même discipline que pour un document joint.
4. **Orchestrateur** — nouvelle intention `VISION` (« analyse cette
   image », « lis le texte de cette image », « analyse ce plan de
   construction »...), testée avant le métier pour la même raison que la
   vidéo : le sujet d'une photo est souvent le chantier lui-même. Voie
   `PROFONDE` (`core/execution/voies.py`) : une image coûte plus cher
   qu'un tour de texte.
5. **`scripts/doctor.py`** — `Modele de vision` rejoint les trois autres
   modèles déjà vérifiés au démarrage (`verifier_modele`, réutilisé tel
   quel, aucune seconde logique de santé).

Chemin réel : *phrase → `VISION` (mots-clés ou modèle) → `vision_agent.run()`
→ pièces jointes filtrées aux images → `OllamaProvider.generate(images=...)`
→ réponse*.

### La preuve

```
python -m ruff check .      → All checks passed!
python -m pytest tests/ -q  → 2006 passed, 21 deselected (1973 avant, +33)
python scripts/orphelins.py → 132 modules, 104 atteints (agents.vision.vision_agent atteint,
                               seul agents.vision.__init__ orphelin — un marqueur de paquet)
python scripts/doctor.py    → [PANNE] Modele de vision  qwen3-vl:4b : indeterminable,
                               Ollama ne repond pas (mesuré sur cette machine cloud —
                               honnête, pas un `[OK]` inventé)
```

Deux sabotages :
- Le gate « sans image, rien ne part » dans `VisionAgent.run()` remplacé
  par `if False:` → les 4 tests de `TestSansImage` tombent tous. Restauré,
  revérifié vert.
- Le passage de `attachments` dans `pwa_gateway.py` retiré → le nouveau
  test `test_les_pieces_jointes_atteignent_un_agent_specialise` tombe avec
  `[] == ['<identifiant>']` — exactement le défaut trouvé en auditant.
  Restauré, revérifié vert.

### Ce qui n'a pas pu être mesuré, et pourquoi

Cette session tourne dans le cloud, sans Ollama ni GPU (comme pour chaque
capacité locale de ce projet). Ce qui suit reste `NON VÉRIFIÉ` tant que ce
n'est pas lancé chez le propriétaire :

- le chargement réel de `qwen3-vl:4b`, son temps de démarrage et sa
  consommation de VRAM mesurée (le calcul ci-dessus vient de la fiche
  publiée par Ollama, pas d'une mesure sur sa carte) ;
- la latence d'une inférence réelle, avec une vraie image ;
- la qualité des réponses (description, OCR, plan de construction) sur des
  photos de chantier réelles ;
- la compréhension vidéo de Qwen3-VL (§9 de la mission) — non implémentée :
  aucun mécanisme d'extraction de trame n'existe côté ARENA, et l'ajouter
  sans pouvoir mesurer le coût réel (VRAM, latence) sur cette machine
  aurait été deviner plutôt que construire. `SUGGESTION — NON
  IMPLÉMENTÉE`.

`python scripts/mesurer_performances.py` (phase 7.2, déjà `UNKNOWN` pour
les mêmes raisons que le reste de l'inférence) est l'endroit naturel où
ajouter une scène de vision, une fois qu'elle peut tourner chez lui.

### Licence et provenance

Apache 2.0 (Qwen3-VL, dépôt officiel Alibaba/QwenLM). **Aucun fichier du
dépôt n'est copié** : ni les cookbooks, ni `qwen-vl-utils`, ni le code de
fine-tuning — rien de tout cela n'est nécessaire une fois qu'Ollama sert le
modèle. Le seul artefact qui entre dans ARENA est le **nom du tag**
(`qwen3-vl:4b`), une chaîne de configuration, pas du code réutilisé. Les
poids eux-mêmes ne transitent jamais par ce dépôt Git : ils sont
téléchargés par Ollama, chez le propriétaire, au moment du
`ollama pull`.

### Ce que ça coûte si c'est faux

Un mauvais choix de taille de modèle aurait deux coûts possibles, opposés :
trop gros, il ne charge pas sur 12 Go à côté des deux autres modèles et
`doctor.py` le dirait en `[PANNE]` — capacité indisponible, pas dangereuse ;
trop petit et de mauvaise qualité sur les plans de construction, il
donnerait une lecture erronée d'un dessin de chantier reprise dans un
devis. C'est pourquoi la description d'une image n'est **jamais** injectée
automatiquement dans une réponse commerciale sans qu'il l'ait demandée —
`VISION` reste une intention explicite, jamais un enrichissement
silencieux d'une autre.

---

## DEC-0020 : diagnostic et réparation — aucune nouvelle capacité, la dette technique

*Demandé le 29/08/2026 : auditer ce que les missions précédentes ont
laissé derrière elles — pas ajouter, réparer. Diagnostic d'abord, preuve
par sabotage pour chaque correctif, jamais de second tour de dette pendant
la réparation.*

### Ce qui a été audité

TODO/FIXME/XXX (aucun réel — les deux hits sont le suffixe de document
`"XXX"`, pas un marqueur de code) ; les ~50 `except Exception` du dépôt,
un par un ; le cycle de vie des clients `httpx` et du transport MCP stdio
(fermeture, timeout, escalade `terminate`→`wait`→`kill`) ; `shell=True`,
`eval`/`exec`/`pickle`, les excepts nus (aucun) ; les frontières
MODEL→RUNTIME et STREAMING→CLIENT (`core/models/routeur.py`,
`core/models/ollama_provider.py`, `core/models/openai_compatible.py`) ;
`core/execution/travaux.py` (la file de fond) ; l'intégration Qwen3-VL
(DEC-0019) relue au niveau du code, pas seulement de la mesure manquante ;
`scripts/orphelins.py` (aucun module réel endormi, inchangé).

La quasi-totalité de ce qui a été inspecté était déjà correcte — chaque
panne externe s'y rapporte comme un état (`echec()`, `Sante(EN_PANNE)`,
`NOT_CONFIGURED`), jamais comme un `pass` silencieux. C'est la mesure
attendue d'un dépôt déjà passé par la discipline sabotage-puis-restauration
sur chaque mission précédente — ce n'est pas un satisfecit gratuit, c'est
ce que l'audit a trouvé.

### Deux défauts confirmés, corrigés

**1. Sécurité, P2 — un chemin de plan pouvait désigner le dépôt d'ARENA
lui-même.** `agents/plaquiste/plaquiste_agent.py` : `chemin_dans()`
(`agents/plaquiste/metre_plan.py`) lit n'importe quel chemin absolu
terminé par `.pdf` **écrit dans la phrase**, sans autre contrôle — par
conception (DEC-0012), pour que le propriétaire désigne un plan posé
n'importe où sur sa machine. Mais rien n'empêchait alors une phrase de
désigner un fichier du dépôt lui-même — le seul endroit où ARENA garde ses
propres secrets (`.env`, `config/metier.yaml`) — avant de le
transmettre à `core/connectors/opentakeoff.py`, qui ne fait lui-même
qu'une vérification d'existence, aucune contention. Portée aujourd'hui :
narrow (serveur lié à `127.0.0.1`) ; deviendrait P1 si le serveur était un
jour exposé au-delà.

Correctif : `chemin_hors_du_depot()`, un contrôle de contention
(`Path(chemin).resolve().relative_to(BASE_DIR.resolve())`) appelé juste
après l'extraction du chemin dans `_mesurer_le_plan()`. Un chemin qui tombe
dans le dépôt rend `REFUSE` avant tout appel au connecteur. La légitimité
du proprietaire — designer un plan n'importe ou ailleurs sur sa machine —
n'est pas restreinte.

**2. Fiabilité/Architecture, P2/P3 — l'historique des travaux de fond
grossissait sans fin.** `core/execution/travaux.py` documente le
parallélisme comme borné (règle 3 du module, un sémaphore) mais rien ne
bornait le **stockage** : `_travaux`/`_taches` n'évacuaient jamais un
travail `TERMINE`/`ECHOUE`/`ANNULE`. Sur un serveur de longue durée, ces
deux dictionnaires grossissent pour toujours — le défaut exact que la
mission demandait de chercher (« unbounded queues/unbounded memory
growth »). Impact réel aujourd'hui borné (un seul utilisateur, peu de
travaux soumis), mais réel sur l'échelle de temps d'un serveur qui tourne
des mois.

Correctif : `TRAVAUX_TERMINES_GARDES = 200` (même forme que
`MESURES_GARDEES` dans `pwa_gateway.py`), et `_purger_les_anciens()`
appelée à chaque fin de travail (`finally`) — retire les travaux **finis**
les plus anciens au-delà de la limite. Un travail encore `EN_ATTENTE` ou
`EN_COURS` n'est jamais purgé, quel que soit le nombre de travaux finis
accumulés autour de lui.

**3. Fiabilité, P3 — un jeton de flux Ollama illisible disparaissait sans
trace.** `core/models/ollama_provider.py`, `generate_stream()` : une ligne
de flux qui échoue au `json.loads` (chunk tronqué, ligne malformée) était
absorbée par un `except Exception: pass` sans aucun journal, même en
`DEBUG` — exactement le « malformed model output silently accepted » que
la mission signale. Le flux continue correctement (bon comportement), mais
une anomalie réelle du modèle local — celui que ce dépôt existe pour faire
tourner — devenait indiagnosticable. Correctif : un `logger.debug()` sur
la ligne rejetée, cohérent avec la convention déjà en place partout
ailleurs dans le dépôt (chaque `except Exception` documenté du dépôt
journalise ou renvoie un état — celui-ci était la seule exception).

### La preuve

Trois sabotages, un par correctif, chacun restauré et revérifié vert :
- `chemin_hors_du_depot()` remplacée par `return True` inconditionnel →
  `test_un_chemin_dans_le_depot_d_arena_est_refuse` tombe : le chemin
  atteint réellement `opentakeoff.mesurer` (l'appel non scripté du double
  de test le prouve).
- `_purger_les_anciens()` neutralisée (`if True: return` avant tout
  retrait) → `test_l_historique_des_travaux_finis_est_borne` tombe :
  `10 == 3` échoue, l'historique n'est plus plafonné.
- Le nouveau `logger.debug()` retiré, `except Exception: pass` restauré →
  `test_la_ligne_illisible_est_journalisee` tombe : plus aucune trace de
  la ligne rejetée.

```
python -m ruff check .      → All checks passed!
python -m pytest tests/ -q  → 2011 passed, 21 deselected (2006 avant, +5)
python scripts/orphelins.py → 132 modules, 104 atteints, 28 orphelins (inchangé —
                               tous des __init__.py, aucun module réel touché)
```

### Ce qui a été délibérément laissé de côté

Rien d'autre n'a franchi le seuil de « confirmé, avec une preuve ». Ne pas
confondre absence de preuve et absence de défaut : les composants marqués
`NON VÉRIFIÉ` dans `PROJECT_MEMORY/COMPLETED_SYSTEMS.md` (Qwen3-VL chargé
réellement, Gmail/Agenda, WanGP, LightRAG, la mesure 7.2 entière) le
restent — ils dépendent d'Ollama/Docker/réseau/GPU, absents de cette
machine, et rien dans cette session ne les rend mesurables. Aucun d'eux
n'a été rouvert « pour être sûr », conformément à la règle du projet.

### Ce que ça coûte si c'est faux

Le correctif §1 est le plus sensible : un contrôle de contention trop
étroit refuserait à tort un plan légitime posé ailleurs sur sa machine — le
test `test_demander_aussi_un_pdf_declenche_l_export_derriere_confirmation`
(chemin hors dépôt, `/chantiers/A-101.pdf`) continue de passer, preuve que
la contention ne mord que sur le dépôt lui-même. Les correctifs §2 et §3
sont sans risque de régression fonctionnelle : l'un purge un historique
déjà lu par `inventaire()` uniquement pour affichage, l'autre ajoute un
journal sans changer le comportement du flux.


## DEC-0021 : ARENA est hébergé en ligne — tout monte, sauf les documents clients

*Décidé par le propriétaire le 30/08/2026. Sa demande, dans ses mots :
« utiliser mon IA comme une IA normale, chat, Grok, Gemini, où je veux quand je
veux, avec un serveur un peu plus puissant que mon PC, et oui, sans que mon PC
s'allume ».*

### Le constat qui a ouvert la question

L'accès téléphone existait déjà (PWA servie par ARENA, tunnel Cloudflare,
mesuré le 27/08). Groq a été branché et mesuré le 30/08 : **0,349 s jusqu'au
premier mot contre 85 s en local** (DEC-0009). Ces deux choses réunies donnent
presque ce qu'il demande — il manque une seule pièce, et ce n'est ni le modèle
ni l'interface : **c'est l'endroit où le serveur tourne.**

Corollaire qui compte pour le budget : **le serveur n'a pas besoin d'être
puissant.** La puissance est chez Groq. Le serveur ne fait que porter ARENA et
sa base. Un serveur modeste suffit, et c'est ce qui rend la chose finançable.

### Ce qui est décidé

| Ce qui monte | Ce qui reste chez lui |
|---|---|
| la mémoire (conversations, faits retenus) | `data/documents/` — contrats, plans, pièces jointes |
| `config/metier.yaml` — sa grille de prix | |
| `data/devis/` — les devis produits | |

Il a tranché en connaissant les trois niveaux de visibilité, qui lui ont été
donnés avant la question :

1. **Les autres personnes : non.** `USMAN_API_KEY` garde la passerelle. ARENA
   reste à lui seul, comme aujourd'hui.
2. **L'hébergeur : oui, techniquement.** C'est sa machine et son disque. Ce
   n'est pas une question de piratage, c'est une question de propriétaire du
   matériel — et c'est la vraie différence avec son PC.
3. **Groq : voit le texte qu'on lui envoie.** Déjà vrai aujourd'hui pour tout
   ce qui n'est pas classé sensible.

### Ce que ça change dans DEC-0009, et ce que ça ne change pas

DEC-0009 disait : *« Rien de sensible ne part chez un fournisseur d'IA. »* Cette
phrase visait les **fournisseurs de modèles**. Elle ne prévoyait pas qu'ARENA
lui-même quitte sa machine, et il faut le dire au lieu de laisser l'ambiguïté.

Ce qui la remplace :

> **Sa grille de prix et ses devis vivent là où ARENA vit. Ses documents
> clients, non : ils restent chez lui, et ARENA dit qu'il ne les voit pas
> plutôt que de répondre sans eux.**

Ce qui **n'a pas** changé :

- un secret (`TRES_SENSIBLE`) ne sort toujours **jamais** vers un fournisseur de
  modèle, aucun mode, aucun réglage ;
- `data/documents/` reste hors dépôt et hors serveur — c'est la seule ligne que
  cette décision trace, et elle est nette ;
- une capacité absente **se rapporte**. Un document injoignable parce que son PC
  est éteint donne `NOT_CONFIGURED` avec sa raison, jamais une réponse bâtie sur
  ce qui manque.

### Les deux conséquences techniques, nommées ici, construites ailleurs

Elles ne sont pas implémentées par cette décision — elles sont ses phases
suivantes, et les écrire ici évite qu'on les découvre en production :

1. **Le routeur suppose Ollama présent.** `_candidats()` ajoute toujours
   `LOCAL` en dernier recours — sa docstring dit « rend toujours au moins
   Ollama : ARENA répond, quoi qu'il arrive ». Sur un serveur sans GPU, ce
   dernier recours n'existe pas. Pire : une demande classée sensible est routée
   vers `LOCAL` **et lui seul**. Telle quelle, elle n'aurait nulle part où
   aller. À mesurer avant de corriger.
2. **La surface publique change de nature.** ARENA écoute aujourd'hui chez lui.
   En ligne, n'importe qui peut frapper à la porte. L'authentification et le
   limiteur existent ; ils n'ont jamais été audités sous cet angle.

### Ce que ça coûte si c'est faux

- **Sa grille de prix est son métier.** Elle sort de ses devis réels et vaut des
  années de chantiers. Sur le disque d'un tiers, elle est exposée à ce que ce
  tiers subit — une faille chez l'hébergeur, une saisie, une revente d'actifs.
  Ça ne se rattrape pas : copié une fois, copié pour toujours.
- **Une dépense mensuelle récurrente** commence, et elle continue même les mois
  où il n'utilise pas ARENA. DEC-0014 avait laissé cette question ouverte
  précisément parce que personne ne peut engager son argent à sa place ; elle
  est maintenant tranchée par lui.
- **La dépendance à l'hébergeur.** ARENA hébergé n'est disponible que lorsque
  l'hébergeur l'est. Son PC, lui, ne tombe que quand il le décide.
- **Le retour arrière reste possible** et doit le rester : la base est un
  fichier SQLite, la configuration des variables d'environnement. Rapatrier
  ARENA chez lui doit rester une copie de fichiers, jamais une migration. Si un
  jour ce n'est plus vrai, c'est que cette décision a dérivé.


## DEC-0022 : deux régimes — sa machine reste prudente, le serveur est utile

*Décidé par le propriétaire le 30/08/2026, après lui avoir demandé de trancher
et lui avoir donné une recommandation qu'il a suivie. La question posée était :
« sur le serveur en ligne, tes devis et tes prix ont-ils le droit de partir chez
Groq pour recevoir une réponse ? »*

### Ce que la mesure avait montré

Phase 2.1 (`scripts/mesurer_sans_ollama.py`, PR #39) : sur un serveur sans carte
graphique, une demande classée `SENSIBLE` est routée vers sa machine **et vers
elle seule**. DEC-0021 fait justement monter sa grille de prix et ses devis sur
ce serveur. Sans décision, ARENA hébergé aurait su discuter de tout — sauf de
son métier.

### La décision

| Où | Mode | Ce qui peut sortir |
|---|---|---|
| son PC | `HYBRIDE` *(inchangé)* | `PUBLIC`, `PRIVE` |
| le serveur | `CLOUD_PREFERRED` | + `SENSIBLE` |

**Le réglage existait déjà** (`NIVEAUX_SORTANTS`, DEC-0009). Rien n'est inventé :
c'est un choix **par machine**, pas un changement d'architecture.

Ce qui ne bouge dans aucun mode :

- `TRES_SENSIBLE` — mots de passe, clés, jetons — **ne sort jamais** ;
- `data/documents/` reste chez lui (DEC-0021) ;
- une capacité absente se rapporte, elle ne se simule pas.

### Pourquoi ce partage plutôt qu'un mode unique

Les jours où son PC tourne, rien de sensible ne le quitte : c'est gratuit, et
c'est la prudence par défaut. Les jours où il est éteint — un chantier, un
déplacement — il accepte que Groq voie, parce que l'alternative est de ne pas
avoir son assistant du tout. Un mode unique aurait choisi une fois pour toutes
à sa place, dans un sens ou dans l'autre.

### Ce que ça coûte si c'est faux

- **Groq reçoit le texte de ses devis et le nom de ses clients** dès qu'il passe
  par le serveur. Ce n'est pas une hypothèse : l'API lit ce qu'on lui envoie.
  Envoyé une fois, envoyé pour toujours.
- **`UNKNOWN`, et il le reste** : la politique de confidentialité de Groq ne dit
  pas si les entrées de l'API sont conservées ou servent à entraîner — elle
  renvoie à un contrat de service qui n'a pas été lu. Cette inconnue lui a été
  dite avant qu'il tranche, et elle est une raison de plus pour que ses devis ne
  partent que les jours où il n'a pas le choix.
- **Un serveur mal configuré devient le régime permanent.** Si le PC finit par
  démarrer en `CLOUD_PREFERRED` par recopie d'un fichier, la prudence des jours
  où il est allumé disparaît sans que personne le remarque. Le mode se lit dans
  le diagnostic (`Inference (hybride)`) : c'est là qu'on le vérifie.

Retour arrière : `AI_LOCAL_ONLY=true`, une ligne, comme dans DEC-0009.

### Ce que cette décision autorise, et rien de plus

Elle ne change **aucune valeur par défaut du dépôt** : `.env.example` reste en
`HYBRIDE`, et c'est voulu — un dépôt cloné ne doit pas partir en mode le plus
ouvert. Le serveur recevra son mode par sa propre configuration, au moment où il
sera monté (chapitre 3).

Ce qui est construit avec elle, et qui vaut dans tous les modes : quand personne
ne peut répondre, l'échec **dit sa cause et ce qui la lèverait**
(`RouteurModeles._pourquoi_personne`). Un `RuntimeError` nu ne distinguait pas
« ce modèle n'existe pas ici » de « tout est tombé une minute ». Sur le serveur,
le premier est permanent, et le second ne se produira jamais.

---

## DEC-0023 : trou D fermé en deux signaux — un décompte lu, un avis regardé

*Demandé par le propriétaire le 30/08/2026, après une clarification qu'il a
lui-même demandée (« qu'est-ce que chacun rapporte ? ») sur deux façons
possibles de fermer le trou D (détection d'ouvertures) laissé ouvert à la
phase 5 de `docs/audits/document_construction_audit.md`. Sa décision, dans ses
mots : « on peut avoir les 2 ».*

### Les deux options posées, et pourquoi aucune ne suffisait seule

1. **`count_marks` d'OpenTakeoff** — lit les tags déjà écrits sur le plan
   (un tableau de menuiseries D1/W1 avec ses comptes). Déterministe, sans
   modèle, sans coordonnée devinée. Mais **ne dit rien si le plan n'a pas de
   tableau de menuiseries déjà annoté** — beaucoup de plans reçus n'en ont pas.
2. **Un avis de Qwen3-VL** sur l'image de la page. Fonctionne même sans
   tableau annoté. Mais c'est une lecture d'image par un modèle : une
   impression, jamais une mesure — le present comme un chiffre certain aurait
   été exactement le risque que DEC-0012 refuse déjà pour `symbol_sweep`/
   `cut_out` (« un métré faux avec l'air d'un métré juste »).

Les deux se complètent plus qu'ils ne se remplacent : le premier est fiable
quand il répond, le second répond toujours mais n'engage rien. Le propriétaire
a choisi de les construire tous les deux, présentés **toujours distinctement**,
jamais fondus en un seul chiffre.

### Ce qui est construit

**Signal 1 — `compter_marques`** (`core/connectors/opentakeoff.py`) : nouvelle
capacité en lecture seule, appelle `load_plan` puis `count_marks` (`commit`
toujours `False`). Déclenchée par une nouvelle regex `DEMANDE_DE_DECOMPTE`
(« combien de portes/fenêtres », « compter les portes/fenêtres », « nombre de
portes/fenêtres »). `agents/plaquiste/metre_plan.py` traduit le détail brut en
`MarquesPlan`/`formater_marques`, qui rapporte chaque marque, le total, un
avertissement `INCOMPLET` si des feuilles ont été ignorées, et se termine
toujours par une phrase rappelant que ceci lit du texte déjà écrit et « ne
devine aucun symbole sur l'image ».

**Signal 2 — avis visuel Qwen3-VL** (`agents/plaquiste/plaquiste_agent.py`) :
`_rendre_premiere_page` rend la première page du plan en PNG (`pypdfium2`,
déjà en place depuis la phase 2 de l'audit OCR) ; `_avis_visuel_depuis` l'envoie
à `provider_vision.generate()` avec une consigne explicite (`DEMANDE_VISUELLE_
OUVERTURES`) demandant une impression et invitant le modèle à dire son
incertitude. Tout échec (modèle absent, erreur réseau, image illisible) est
absorbé et rend `None` — ce signal ne casse jamais une réponse par ailleurs
utile. `PlaquisteAgent` reçoit `provider_vision` en constructeur ;
`apps/backend/runtime.py` lui transmet **la même instance** `ollama_vision`
déjà construite pour `VisionAgent` — pas un second modèle chargé pour cet
agent seul.

Dans `run()`, quand les deux signaux sont présents, la réponse les distingue
explicitement : le décompte OpenTakeoff d'abord, puis « CE QUE LE MODELE DE
VISION DIT AVOIR VU... (une IMPRESSION, jamais une mesure certaine) », avec une
phrase rappelant que l'un lit du texte déjà écrit et l'autre regarde l'image et
peut se tromper ou en manquer.

`symbol_sweep`/`cut_out` (désigner un rectangle sur l'image) restent
`SUGGESTION — NON IMPLEMENTEE` : personne n'a mesuré si Qwen3-VL peut pointer
une coordonnée avec une précision suffisante, et les construire sans cette
mesure aurait été le même risque refusé plus haut.

### Preuve par sabotage

- `core/connectors/opentakeoff.py` : forcer `commit=True` dans l'appel à
  `count_marks` a fait échouer le test vérifiant `commit is False` (lecture
  seule garantie) — restauré.
- `agents/plaquiste/plaquiste_agent.py` : retirer le `try/except` de
  `_avis_visuel_depuis` a fait remonter un `ConnectionError` brut jusqu'à
  `run()`, cassant `TestAvisVisuelDuPlan::test_un_echec_du_modele_ne_casse_pas_
  la_reponse` (le reste de la réponse doit survivre à un échec du modèle de
  vision) — restauré.

`python -m pytest tests/ -q` → 2229 passed, 1 skipped, 21 deselected.
`python -m ruff check .` → All checks passed!

### Ce qui reste `NON VÉRIFIÉ`

Le signal 1 (`compter_marques`) est testé entièrement hors ligne (double
scripté du transport MCP) — sa logique est vérifiée, mais aucun vrai plan avec
tableau de menuiseries n'a été mesuré ici.

Le signal 2 (avis visuel) n'a **jamais tourné sur `qwen3-vl:4b` réel** — cette
machine n'a pas de GPU (§ »Ce que la machine de l'assistant ne peut pas
faire », `CLAUDE.md`). Le branchement et la logique sont testés avec un double
du modèle ; la qualité réelle de l'impression reste `UNKNOWN` tant que le
propriétaire ne l'a pas fait tourner chez lui sur un vrai plan.

### Ce que ça coûte si c'est faux

- **Si le signal 2 est pris pour une mesure** malgré l'avertissement répété
  dans la phrase elle-même : un chiffrage basé dessus serait faux avec l'air
  d'être juste — exactement le risque déjà refusé pour `symbol_sweep`/
  `cut_out`. La phrase « impression, jamais une mesure certaine » est la seule
  garde ; elle n'empêche rien côté code, elle informe.
- **Si `compter_marques` est incomplet** (`feuilles_ignorees` non vide) et que
  ce n'est pas remarqué : `complet=False` est toujours transmis jusqu'à
  l'utilisateur (`formater_marques` l'affiche en `INCOMPLET`), jamais caché —
  mais rien n'empêche de lire la réponse trop vite.

Retour arrière : retirer le branchement de `run()` (deux blocs identifiés,
`marques = ...` et `avis_visuel = ...`) restaure le comportement précédent sans
toucher au reste de l'agent.

---

## DEC-0024 : Gmail — le bouton « Connecter » fait enfin ce qu'il affiche

*Demandé par le propriétaire le 31/08/2026 : « CONNECTORS & REAL
INTEGRATIONS — MAKE EVERY CONNECTOR ACTUALLY OPERATIONAL ». Signalé
concrètement : cliquer sur Gmail dans l'interface ne terminait jamais la
connexion. Après audit complet (tracé du bouton jusqu'à l'API Google, rien
supposé) et deux choix qu'il a tranchés : Gmail d'abord, de bout en bout ;
retirer le coffre chiffré côté navigateur plutôt que le garder à côté d'un
modèle serveur-only.*

### Ce que l'audit a trouvé, avant d'écrire une ligne

Le module de connecteurs de la PWA (`ConnectorsModal.tsx`, `connectorStore.ts`,
`catalog.ts`) est arrivé en un seul commit (`8ff90c2 feat(pwa): interface
React du proprietaire`) — un gabarit générique, jamais câblé à ARENA. Deux
causes cumulées faisaient que rien ne pouvait jamais fonctionner :

1. **Aucune route `/connectors/*` n'existait côté serveur.**
   `apps/backend/main.py` ne montait que 7 routeurs, jamais `connectors`.
2. **Le catalogue affichait 17 connecteurs ; le backend réel en avait 8, et
   un seul se recoupait (Gmail).** Notion, GitHub, GitLab, Jira, Linear, X,
   WhatsApp, HTTP, RSS, Slack, Salesforce, HubSpot, Postgres n'avaient et
   n'ont toujours **aucun** code backend — des boutons qui ne pouvaient
   physiquement rien faire.

Même avec la route, `core/connectors/google_oauth.py` ne savait qu'échanger
un `refresh_token` déjà obtenu ailleurs (OAuth Playground, à la main) —
aucun code n'initiait le consentement Google. Le clic ne pouvait donc rien
faire non plus, même une fois la route posée.

**Désaccord architectural trouvé au passage** : le frontend chiffrait les
jetons `apikey` (AES-256) dans le navigateur et les envoyait à chaque
requête — un modèle « bring-your-own-key côté client », l'inverse du reste
d'ARENA (secrets uniquement côté serveur, `.env`, jamais le navigateur —
`core/security/trust.py`, `core/permissions/`). Le propriétaire a tranché :
le retirer.

### Ce qui est construit

**Le flux réel, CONNECT → OAUTH → CONSENTEMENT → CALLBACK → JETON STOCKÉ :**

- `core/connectors/google_oauth.py` : `url_consentement()` (construit l'URL
  vers l'écran Google, `access_type=offline&prompt=consent` pour garantir un
  `refresh_token` à **chaque** connexion, pas seulement la première) et
  `code_pour_jetons()` (échange `authorization_code` → jetons). L'échange
  `refresh_token` existant (`echanger()`, chapitre 8/9 déjà en place) n'est
  pas touché.
- `apps/backend/routers/connectors.py` (nouveau) : `/connectors/{id}/auth`
  (redirige vers Google, `state` CSRF à usage unique, 10 min), `/callback`
  (échange le code, écrit le jeton dans `os.environ` **et** `.env` quand ce
  fichier existe — silencieux sinon, pour un déploiement hébergé où les
  variables vivent dans le panneau de la plateforme, jamais un fichier),
  `/status` (interroge `registre.sante("gmail")`, jamais une affirmation
  plausible), `/disconnect` (efface uniquement le `refresh_token`, jamais
  `client_id`/`secret`). Seul `gmail` est déclaré dans
  `FOURNISSEURS_OAUTH` : un autre identifiant reçoit une erreur qui le dit,
  jamais un faux succès.
- Authentification/débit **déclarés à côté de chaque route**
  (`dependencies=[Depends(...)]`), jamais appelés à la main dans le corps —
  suit la même règle que `tests/test_surface_api.py` fige et audite pour
  tout le reste de l'API, plutôt que d'en inventer une seconde invisible
  pour ce test. `/auth` réutilise `verify_media_access` (déjà écrite pour
  `/media/rendered` : en-tête OU paramètre `cle`, parce qu'une redirection
  de navigateur — `window.open()` — ne pose jamais d'en-tête) ; `/status` et
  `/disconnect` gardent `verify_api_key`.

**Le catalogue de la PWA reconcilié à la réalité** (`catalog.ts`) : les 16
connecteurs sans code backend sont retirés, pas laissés en façade — un
bouton qui ne peut rien faire est pire qu'aucun bouton. Seul Gmail reste.
Le coffre AES-256 navigateur (`VaultSecurityCard`, `vaultStore.ts`,
`security/vault.ts`) est supprimé : plus rien à protéger côté client, le
jeton vit uniquement sur le serveur d'ARENA. `connectorStore.ts` corrigé au
passage : le paramètre envoyé au backend était `?key=`, le backend attend
`?cle=` (même bug que celui qui empêchait déjà la connexion) ; le
`postMessage` de retour ne vérifiait aucune origine — corrigé pour
n'accepter que l'origine du backend appelé.

### Preuve par sabotage

- Le `state` CSRF redevenu rejouable (`.pop()` → `.get()`, sans le
  retirer) : `test_callback_echange_reussi_persiste_le_jeton` échoue —
  restauré, revérifié vert.
- La dépendance d'authentification retirée de `/auth` :
  `test_surface_api.py::test_chaque_route_garde_ses_methodes_et_ses_dependances`
  **et** deux tests locaux échouent — restauré, revérifié vert. Ce second
  sabotage prouve que le filet de sécurité existant (`test_surface_api.py`,
  qui fige toute la surface HTTP d'ARENA) couvre bien ce nouveau routeur, et
  pas seulement mes propres tests.

`python -m pytest tests/ -q` → 2253 passed, 1 skipped, 21 deselected.
`python -m ruff check .` → All checks passed!
`npm run build` (apps/pwa) → réussi. `npx tsc --noEmit` → aucune erreur.

### Ce qui reste `NON VÉRIFIÉ`

Rien de ce chantier n'a encore été essayé contre un vrai compte Google : la
logique est testée hors ligne (doubles du transport HTTP), jamais bout en
bout. Il manque **une seule chose côté propriétaire** : créer l'app OAuth
sur console.cloud.google.com (identifiant « application web », URI de
redirection `{PUBLIC_BASE_URL}/connectors/gmail/callback`), mettre
`GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET` dans `.env`, puis cliquer
« Connecter » dans ARENA. `GOOGLE_REFRESH_TOKEN` s'écrit alors tout seul.

### Ce que ça coûte si c'est faux

- **Le `state` CSRF est en mémoire, pas partagé entre plusieurs processus.**
  ARENA est mono-processus aujourd'hui ; si un déploiement futur ajoute
  plusieurs workers derrière un répartiteur de charge, une requête `/auth`
  et son `/callback` pourraient atterrir sur deux processus différents et
  échouer à tort. Rien ne casse silencieusement : l'échec dit « lien de
  consentement expiré ou déjà utilisé », jamais un faux succès.
- **`.env` réécrit à chaud** : `_persister_refresh_token` remplace la ligne
  `GOOGLE_REFRESH_TOKEN=` ou l'ajoute. Une édition manuelle du fichier
  pendant l'échange (fenêtre de quelques centaines de millisecondes) pourrait
  perdre l'un des deux changements — improbable, jamais mesuré comme un
  risque réel sur une machine mono-utilisateur.
- **Les 16 autres connecteurs du catalogue restent à construire**, et
  chacun exige que le propriétaire enregistre une app chez le fournisseur
  concerné (Meta for Developers pour Instagram, LinkedIn Developer, TikTok
  for Developers, Reddit, Google Business Profile API...) avant qu'une
  ligne de code réelle puisse leur être écrite — aucune ne peut être
  fabriquée à sa place. Détail complet : `docs/audits/connecteurs_audit.md`.

Retour arrière : retirer `app.include_router(connectors.router)` de
`apps/backend/main.py` restaure le comportement précédent (bouton mort) sans
toucher au reste du backend.

## DEC-0025 : destinataire du devis — le modèle comprend, sur son propre choix contraire du matin même

*Le 31/08/2026, plus tard le même jour que DEC-0024 : le propriétaire a
testé en direct la capture déterministe qu'il avait lui-même demandée
(« Il les redit clairement, je les capture »). Sur une vraie conversation,
il avait donné le nom du client et le lieu du chantier dans une phrase
libre, sans le mot-clé attendu — rien n'avait été capté, le PDF refusait de
partir. Sa réaction : « il va falloir l'entraîner pour ca alors car il
dois bien comprendre ». Prévenu explicitement, avant de trancher, que ce
n'est pas un problème d'entraînement mais un choix de sécurité volontaire,
et que le lever fait courir un risque réel — le modèle peut se tromper de
nom ou de lieu sur un devis, et rien ne le détecterait avant l'envoi — il a
choisi quand même : « Oui, laisse le modèle comprendre naturellement ».*

### Ce qui change

`destinataire_depuis_l_historique()` (capture déterministe, Q&A labellisée
— DEC créée le matin même) reste en place et reste **prioritaire** : elle
ne devine jamais, et un champ qu'elle trouve n'est jamais écrasé.

Un second mécanisme, `_destinataire_par_modele()`
(`agents/plaquiste/plaquiste_agent.py`), intervient en **dernier recours
seulement** : au moment où un document est réellement demandé
(`DEMANDE_DE_DOCUMENT`) et qu'un champ (client, lieu ou objet) manque
encore après la capture déterministe. Un appel séparé au modèle, avec une
instruction dédiée à l'extraction (`INSTRUCTION_EXTRACTION_DESTINATAIRE`)
qui lui interdit explicitement d'inventer et lui demande une chaîne vide
plutôt qu'une supposition, lit tout l'échange et rend un JSON strict. Une
réponse illisible ou un appel qui échoue rend `{}`, jamais un crash — même
discipline « best-effort » que `_avis_visuel_du_plan` pour le modèle de
vision.

**Jamais silencieux** : chaque champ compris ainsi par le modèle est
signalé en tête du message de confirmation du document — « Compris
automatiquement dans ta phrase, vérifie avant de confirmer : client = ...,
lieu = ... » — avant que `produire` (action à confirmer, jamais écrite
d'autorité) ne parte. Le principe qui restait vrai avant DEC-0024 et
continue de l'être ici : ce n'est jamais un envoi automatique à un client,
c'est un fichier local qu'il relit.

### Ce que ça coûte si c'est faux

Le risque que DEC-0024 avait précisément voulu fermer redevient réel : un
nom de client ou un lieu de chantier mal compris dans une phrase ambiguë
peut atterrir dans un PDF sans qu'aucun mécanisme automatique ne le
détecte — seule la relecture du propriétaire avant confirmation l'attrape.
Accepté explicitement par lui, pas une régression passée inaperçue.

Retour arrière : ne plus appeler `_destinataire_par_modele()` dans `run()`
restaure la capture strictement déterministe de DEC-0024, sans toucher au
reste de l'agent.

---

## DEC-0026 : le montage — le modèle propose un plan, il ne pilote pas la timeline

*Décidé le 01/09/2026, mission « intégration OpenCut ». Suite directe de
l'audit `docs/audits/opencut_audit.md`, qui n'intégrait rien.*

### Le problème

L'audit a conclu qu'OpenCut apporte un **modèle de projet** (timeline, pistes,
éléments) et non un moteur de rendu utilisable ici : sa version classique rend
dans le navigateur, la réécriture Rust n'a ni API headless ni couche MCP. ARENA
a donc repris le modèle et gardé `ffmpeg` comme rendu, derrière une frontière
remplaçable (`core/montage/`).

Restait la question que le modèle de projet ne répond pas : **par où une phrase
du propriétaire devient-elle une timeline ?** La mission le posait comme une
contrainte, pas comme une option : *« Do not let the LLM directly manipulate
arbitrary internal state without validation. Use a structured operation layer. »*

### La décision

Trois barrières, dans cet ordre, et la deuxième est la seule qui soit une
frontière de sécurité :

1. **La liste des opérations est fermée** (`OPERATIONS_OUVERTES`,
   `core/connectors/montage.py`). Un nom hors liste ou commençant par `_` est
   refusé et nommé.

2. **Le modèle ne cite jamais un chemin de fichier.** Il travaille sur un
   inventaire `{nom: chemin}` bâti côté serveur (`medias_montables()` dans
   `apps/backend/routers/chat.py`, limité aux dossiers de rushes et aux
   extensions montables) et ne nomme que des noms. `core/montage/planificateur.py`
   substitue le vrai chemin ; un `chemin` cité dans un plan est refusé même
   s'il est exact, et le prompt ne montre aucune arborescence.

3. **Les paramètres sont lus sur `Montage` par introspection**, jamais recopiés
   — une liste écrite à la main aurait divergé en silence à la première
   signature changée.

Et une règle qui n'est pas une barrière mais la même discipline que partout
ailleurs ici : **un plan refusé ne devient jamais un plan de repli.** Ni coupe
de quinze secondes, ni timeline vide qui rendrait un fichier noir. Ollama
éteint, JSON illisible, plan vide : l'agent le rapporte.

### Ce que ça coûte si c'est faux

Le modèle ne peut monter que ce que le propriétaire a téléversé. S'il veut
assembler un fichier rangé ailleurs sur son disque, ARENA refusera de le
trouver — il devra le déposer dans `media/`. C'est le prix accepté : sans
l'inventaire, un texte injecté dans une transcription qu'ARENA vient de lire
pourrait faire entrer n'importe quel fichier de la machine dans une vidéo.

### Ce qui a été mesuré, et ce qui ne l'a pas été

La chaîne a tourné en entier le 01/09/2026, **sauf l'appel au modèle** :
Ollama n'est pas sur la machine de l'assistant (`docs/REGLES_DE_TRAVAIL.md`).
Le plan utilisé était la réponse qu'un modèle rend réellement — de la prose
autour d'un bloc ```json, une opération inventée (`publier_sur_instagram`) et
un chemin cité (`/etc/passwd`). Les deux ont été refusées et nommées ; les
neuf autres opérations ont composé, puis rendu
`1080x1920`, `h264`, `6.000000 s`, 180 images, logo et titre incrustés
vérifiés à l'image extraite. Le cadrage a été mesuré et non estimé : la
source 16:9 occupe 1080 × 608, soit 1.776 — l'aspect est préservé.

**`MONTAGE` avec un vrai modèle reste `UNKNOWN` jusqu'à ce que le PC du
propriétaire soit rallumé.** L'aiguillage, la validation, la composition et le
rendu sont mesurés ; la qualité du plan que Qwen produit ne l'est pas.

### Un défaut trouvé par le CI, pas par cette machine

`ConnecteurMontage.sonder()` rendait `NON_CONFIGURE` sans ffmpeg. La base lit
la santé **avant toute capacité**, donc ce refus coupait aussi `composer`, qui
est du Python pur. La machine de l'assistant a ffmpeg : la suite locale ne
pouvait pas voir le défaut. Le CI, qui ne l'a pas, a fait tomber quatre tests.
Trois tests cachent désormais ffmpeg de force, pour que la garantie tienne sur
une machine qui l'a.

Retour arrière : retirer `"MONTAGE"` de `AGENTS_SPECIALISES`
(`apps/backend/config.py`) et de l'aiguilleur rend l'intention inatteignable
sans toucher à `core/montage/`, qui reste appelable par le registre.

---

## DEC-0027 : l'audio d'ARENA — VoiceStudio piloté, jamais absorbé

*Décidé le 01/09/2026, mission « intégration VoiceStudio ». Audit complet →
`docs/audits/voicestudio_audit.md`.*

### Le problème

ARENA savait transcrire (faster-whisper `tiny`, CPU) et incruster des
sous-titres. Il **ne savait pas parler** : `tools/social/voix.py` traite de son
style d'écriture, pas de parole. Une voix off pour une vidéo de chantier était
hors de portée.

VoiceStudio apporte exactement ça — et il est sous **AGPL-3.0-only**, quand
`LICENSE` d'ARENA dit « All rights reserved ».

### La décision

**VoiceStudio tourne comme processus séparé, joint par HTTP sur `127.0.0.1`.
Aucune de ses lignes n'entre dans ARENA, aucune n'est modifiée.**

Ce n'est pas une préférence de style. Copier son source, ou l'importer comme
bibliothèque, ferait d'ARENA une œuvre dérivée : ARENA devrait être publié en
entier sous AGPL-3.0. Le couplage est donc délibérément large — HTTP, API
OpenAI-compatible, aucune structure de données partagée.

Trois conséquences dans le code :

1. **`core/connectors/audio_voix.py`** parle l'API et rien d'autre. Il refuse
   toute adresse qui n'est pas la boucle locale (`AdresseNonLocale`) : une voix
   est une donnée personnelle, et un `OMNIVOICE_URL` mal réglé enverrait les
   enregistrements du propriétaire chez un tiers.
2. **Parler est une écriture.** `transcrire` lit un fichier déjà là ; `parler`
   écrit un WAV et passe par la file de confirmation, comme le devis PDF.
3. **Le succès est le fichier.** Un `200` ne suffit pas : le WAV est re-sondé
   avec ffprobe, et une durée illisible efface le fichier et rend un échec.

### Ce que ça coûte si c'est faux

Si un couplage HTTP suffisait à créer une œuvre dérivée — lecture minoritaire,
mais elle existe —, ARENA devrait passer en AGPL ou acheter la licence
commerciale que VoiceStudio propose. Et si le propriétaire n'a pas démarré
VoiceStudio, ARENA ne parle pas du tout : il le dit
(`NOT_CONFIGURED`) au lieu de se rabattre sur autre chose.

### Ce qui n'a PAS été dupliqué

**Les sous-titres restent au studio.** L'intention `AUDIO` les lui prenait —
`test_ces_demandes_vont_au_studio[sous-titre ma vidéo]` est tombé le 01/09/2026.
ARENA fabrique déjà les sous-titres de bout en bout (transcription +
incrustation 9:16) ; une transcription rend du texte, incruster est un travail
d'image. La règle « ne pas dupliquer » a tranché, et un test la fixe.

`tools/audio/transcription_tool.py` n'est pas touché non plus.

### Ce qui a été mesuré, et ce qui reste inconnu

Vérifié : santé, liste des moteurs, transcription, synthèse (5742 ms, 275678
octets, amplitude max 26029 — pas du silence), et le tour complet texte → voix
→ texte. Puis la voix off posée dans une timeline et rendue : MP4 `h264` +
`aac`, audio extrait à 25892 d'amplitude.

`UNKNOWN` — **la VRAM**. Cette machine n'a pas de GPU (`vram_total_gb: 0.0`).
Rien n'a été mesuré sur la RTX A2000, et rien n'a été inventé. ARENA n'ajoute
aucune politique VRAM : VoiceStudio a la sienne (`min_vram_gb`,
`/model/unload/{id}`, éviction), et deux politiques concurrentes valent moins
qu'une seule qui marche.

`UNKNOWN` — **une voix française**. Le seul moteur TTS installable ici est
anglais, et `/engines/tts` n'expose aucune information de langue : ARENA ne
peut donc pas router par langue. Le message de succès **nomme le moteur qui a
parlé**, pour que le propriétaire voie qu'un moteur anglais a lu son texte.

Retour arrière : retirer `"AUDIO"` de `AGENTS_SPECIALISES` rend l'intention
inatteignable sans toucher au connecteur, qui reste appelable par le registre.


---

## DEC-0028 : des méthodes de spécialistes, pas des spécialistes

*Décidé le 01/09/2026, mission « intégration Agency Agents ».*

### Le problème

`msitarzewski/agency-agents` (MIT, commit `3c958888`) contient **319
définitions d'agents** répartis en 19 divisions. Chacune est un prompt de rôle
d'environ 230 lignes : identité, personnalité, mission, métriques de succès.

La demande du propriétaire était explicite : *« ARENA remains ONE AI. Do not
create 150 disconnected AI personalities. »*

### La décision

**Aucun agent n'a été créé. Aucune définition n'a été copiée.**

Ce qui entre dans ARENA est un **catalogue de méthodes** :
`core/specialistes/catalogue.py`. Douze métiers, chacun tenant en un
enregistrement compact — les étapes, les contrôles, la définition de « fini »,
et **le chemin d'ARENA qui exécute**.

Ce qui a été gardé de la source : les taxonomies, et la partie substantielle
des listes de contrôle (STRIDE, OWASP, pyramide de tests, référencement
local). Ce qui a été laissé : la prose de rôle. « Tu es stratégique et
soucieux de la qualité » ne change rien à ce qui est produit et allonge chaque
prompt.

Quatre règles portent le catalogue :

1. **Aucun spécialiste décoratif.** `capacite` nomme une intention que
   l'aiguilleur sait router. Un test refuse l'ajout d'un métier qu'ARENA ne
   sait pas exécuter — c'est précisément ainsi que ce genre de système
   pourrit : on ajoute des noms, personne ne vérifie qu'ils mènent quelque
   part.
2. **Aucun doublon.** Quand ARENA sait déjà faire — recherche, réseaux
   sociaux, devis, montage — la méthode **enrichit** l'agent existant.
3. **Une méthode n'est pas un ton.** Des étapes et des contrôles, rien
   d'autre.
4. **Deux méthodes au maximum**, et souvent zéro. Le risque n'est pas d'en
   manquer une : c'est d'en convoquer six pour une question qui n'en demandait
   aucune.

### Le branchement

Un seul endroit compose les règles d'ARENA et la méthode
(`apps/backend/prompts.prompt_avec_methode`), et les **trois** chemins de
réponse y passent. Trois assemblages séparés auraient dérivé — c'est
exactement ce qui était arrivé à la liste d'agents de `/health`.

La méthode vient **après** les règles d'ARENA : elle précise comment
travailler, elle ne peut rien effacer de ce que la plateforme s'interdit.

### Ce que ça coûte si c'est faux

Le choix se fait par mots-clés, pas par un modèle. C'est délibéré : un
aiguillage qui dépend d'Ollama ne marche pas quand Ollama est éteint, et le
propriétaire a besoin qu'ARENA reste utile sans son PC. Le prix : une demande
formulée d'une façon que le catalogue ne prévoit pas n'obtient aucune méthode,
et ARENA répond comme avant — dégradation silencieuse, mais dans le sens sûr.

### Deux défauts trouvés par les tests de ce module

- **« ci » était reconnu dans « merci »** : la recherche par sous-chaîne
  convoquait un spécialiste DevOps sur un remerciement. Corrigé par une
  reconnaissance aux frontières de mot.
- **« devis » et « chantier » déclenchaient le chiffrage** — ce sont les mots
  de tous les jours du propriétaire. « Corrige ce bug dans le module de
  devis » et « monte une vidéo du chantier » convoquaient une méthode de
  calcul de marge. Les déclencheurs portent maintenant sur l'argent et les
  quantités ; pour le reste, l'intention `PLAQUISTE` de l'aiguilleur fait déjà
  le renfort.

### L'audit d'après intégration, et ce qu'il a trouvé

La mission demandait de ne pas s'arrêter à l'implémentation. L'audit a compté
**onze intentions qu'ARENA sait router et qu'aucune méthode n'atteignait**.
Chacune est désormais dans l'une de trois cases, et un test l'exige :

- **couverte par une méthode** — sécurité, tests, architecture, données, SEO…
- **couverte par le renfort** — `SWE_FIX` → tests, `AUDIO`/`STUDIO` → média,
  `TREND_SEARCH`/`BROWSER` → recherche.
- **laissée de côté, avec la raison écrite** — `EMAIL` et `VISION`. Leurs
  agents portent déjà une discipline plus forte que ce qu'on écrirait ici :
  le courrier ne part jamais sans confirmation et ne quitte pas la machine
  quand il est sensible ; une image est une donnée, jamais une instruction.

Une vraie lacune est apparue : **lire ses propres documents** n'avait aucune
méthode. `RAG_DOCS` interrogeait l'index et rendait du texte, sans exiger de
citer le passage ni de dire quand les documents ne répondent pas. Le
spécialiste `documents` comble ça.

Et une leçon déjà apprise cette nuit a resservi : le test qui vérifiait les
outils portait une **liste écrite à la main**. Elle est maintenant dérivée du
registre des connecteurs et vérifiée par import — un test qui dérive finit par
autoriser n'importe quoi.

Retour arrière : `bloc_de_methode` rend une chaîne vide si le catalogue est
vidé, et les trois chemins de réponse retrouvent le prompt d'avant sans autre
changement.

## DEC-0029 — Le bac à sable re-sonde Docker quand la réponse était « non »

**2026-09-01.** `SandboxInterpreterTool` mesurait la présence de Docker une seule
fois, dans `__init__`. `CoderAgent` et `ReasoningEngine` étant construits au
démarrage du serveur (`apps/backend/runtime.py`), la mesure datait du lancement
d'ARENA et n'était jamais revue : un Docker démarré **après** le serveur restait
invisible, et le refus répétait « démarre Docker » à quelqu'un qui venait de le
démarrer. Seul un redémarrage du serveur le débloquait.

Une mesure **négative** se re-sonde donc, au plus une fois toutes les 30 s.
Une mesure **positive** ne se re-sonde pas : si le démon a disparu entre-temps,
`docker run` échoue et le chemin d'exception refuse déjà — l'exécution est sa
propre sonde. C'est la convention des connecteurs
(`core/connectors/base.py` mesure la santé avant chaque capacité), au coût
d'appel près : `docker info` prend jusqu'à trois secondes, ce qui serait payé à
chaque bloc de code.

**Ce que ça coûte si c'est faux** : jusqu'à 30 secondes d'écart entre le moment
où le propriétaire lance Docker et celui où ARENA le voit. Le refus reste juste
pendant ce délai, il n'exécute rien sur l'hôte.

Trouvé par le diagnostic général, pas par un test : la suite était verte.

## DEC-0030 — Un flux coupé écrit ce qui s'est passé, des deux côtés

**2026-09-01.** `/agent/stream` écrivait le tour du propriétaire avant la
génération et ne rendait rien côté assistant quand la génération tombait :
l'historique gardait une question orpheline, relue ensuite par l'orchestrateur
et par `fresh_info` pour résoudre une question elliptique. `/api/chat/stream`
tenait déjà la règle ; la PWA, non.

Ce qui est écrit est ce qui s'est réellement passé — le début effectivement
généré, suivi de `[interrompu : X]` — jamais une réponse fabriquée. Une panne
survenue avant l'écriture de la question n'écrit rien : sinon c'est la réponse
qui devient orpheline.

**Ce que ça coûte si c'est faux** : un tour d'historique porte un texte
tronqué. Le tour suivant le lit comme un début de réponse coupé, ce qu'il est,
au lieu de lire une question posée deux fois.

## DEC-0031 — Le tableau `messages` du client fait foi

**2026-09-01.** La passerelle OpenAI ne transmettait au modèle que le dernier
message utilisateur, et retombait sur `session_id="default"` pour toutes les
conversations. Le protocole étant sans état, c'est le client qui porte le fil :
son tableau `messages` est désormais reconstruit en conversation, exactement
comme l'historique du navigateur fait foi côté PWA.

Un message `system` du client reste **hors** du fil : un texte extérieur ne
prend pas l'autorité des consignes d'ARENA.

La clé de session vient du premier message utilisateur, faute d'identifiant
dans le protocole.

**Ce que ça coûte si c'est faux** : deux conversations ouvertes par exactement
la même phrase partagent une mémoire. Et un client qui envoie un fil très long
fait un prompt très long — c'est lui qui décide de ce qu'il envoie, ARENA ne
tronque pas en silence.

## DEC-0032 — Un flux vide n'est pas une réponse, et n'est pas une panne

**2026-09-01.** Un fournisseur qui termine son flux sans un seul morceau ne
lève rien : l'appel était noté `succès`, aucun repli n'avait lieu, et
`dernier_choix` gardait la valeur du tour précédent — l'interface nommait le
mauvais moteur. Un flux vide déclenche désormais le repli, comme n'importe quel
échec survenu avant le premier mot.

Mais **sans** mettre le fournisseur au frais. `_echec(LOCAL)` ferait répondre
`is_available()` « Ollama hors-ligne » pendant deux minutes alors qu'Ollama
répond : ARENA dirait une chose fausse sur la machine du propriétaire. Un flux
vide est une mauvaise réponse, pas une indisponibilité prouvée.

**Ce que ça coûte si c'est faux** : un fournisseur réellement cassé qui rend du
vide est ré-essayé à chaque phrase, au lieu d'être écarté pendant deux minutes.
On paie une tentative vide par tour ; on ne dit rien de faux.

## DEC-0033 — Chaque cause d'indisponibilité porte son propre nom

**2026-09-01.** `GraphRAGTool.query_global` traduisait tout code de sortie non
nul de `docker run` par « Espace de connaissances prêt. Ajoutez vos
documents… ». Démon éteint, image absente, requête plantée : la même phrase,
et un remède qui n'aurait rien changé.

Quatre causes, quatre réponses distinctes, parce qu'elles n'appellent pas le
même geste. « Ajoutez vos documents » n'est dit que dans le seul cas où c'est
vrai : l'espace est vide.

La sonde Docker (`demon_repond`, `image_construite`) vit dans
`tools/docker_local.py`. Elle n'existait qu'au bac à sable, et c'est pour ça
que le moteur de graphe ne la posait pas.

**Ce que ça coûte si c'est faux** : deux appels `docker` (~100 ms quand le
démon répond) avant chaque requête de graphe. Une requête de graphe dure des
secondes ; la sonde ne se voit pas.

## DEC-0034 — La grille de prix suit le fichier, pas le démarrage du serveur

**2026-09-01.** `PlaquisteAgent` et `DevisConnector` lisaient
`config/metier.yaml` une seule fois, dans leur constructeur — donc au
démarrage du serveur. Un prix modifié n'était vu qu'au redémarrage suivant, et
rien ne le disait. Mesuré : fichier à 999 999, agent toujours à 4 500.

La relecture se déclenche sur la **date de modification** du fichier, jamais
sur une horloge. Un fichier effacé vide la grille au lieu de figer l'ancienne :
refuser de chiffrer est plus sûr que chiffrer sur une grille fantôme.

**Ce que ça coûte si c'est faux** : un `stat()` par chiffrage. Si le système de
fichiers rendait une date instable, la grille serait relue à chaque appel — un
`yaml.safe_load` d'un fichier de quelques kilo-octets, sans conséquence sur le
résultat.

## DEC-0035 — Les règles de permission suivent leur fichier

**2026-09-01.** `PolitiqueDePermissions` et `PermissionManager` lisaient leur
fichier une seule fois, à la construction — et les deux sont des singletons
créés au démarrage du serveur. Une règle durcie dans le fichier n'était pas
appliquée jusqu'au redémarrage suivant, et la docstring de la première
annonçait pourtant que `recharger()` évitait exactement cela.

Le sens du risque décide : une règle assouplie non vue laisse ARENA plus
strict que demandé, une règle durcie non vue laisse passer ce qui vient d'être
interdit. Seul le second sens compte.

La mécanique vit dans `core/fichier_suivi.py`, écrite après avoir trouvé la
même forme de défaut **quatre** fois dans la même nuit. Un fichier absent rend
la valeur vide, jamais l'ancienne.

**Ce que ça coûte si c'est faux** : un `stat()` par vérification de permission.
Si la date était instable, le fichier serait relu à chaque appel — un
`yaml.safe_load` de quelques kilo-octets, sans effet sur la décision.

## DEC-0036 — Un plan à moitié tombé est PARTIEL, jamais un succès

**2026-09-01.** `composer` rendait `SUCCESS` quelles que soient les opérations
tombées : mesuré sur une vraie vidéo, une timeline de 0 ms avec l'unique clip
refusé était annoncée « réussie », l'erreur reléguée dans un champ que le
message ne reprenait pas.

`Statut.PARTIEL` existait pour ça. Il s'applique à `composer` et au rendu, et
le compte de lignes écartées entre dans le **message** — c'est lui qui est lu.
L'agent rend `warning` plutôt que `success` dans ce cas.

Un projet jamais créé reste `ECHEC` : `PARTIEL` dit « une partie a eu lieu »,
et sans projet rien n'a eu lieu.

**Ce que ça coûte si c'est faux** : une interface qui traite `PARTIAL` comme un
échec afficherait une alerte pour un plan très majoritairement appliqué. Le
projet est dans la charge utile et reste utilisable ; l'inverse — un échec pris
pour une réussite — laissait le propriétaire attendre une vidéo qui n'existait pas.

## DEC-0037 — Le workspace Video : orchestrer ce qui existe déjà, pas le refaire

**2026-09-01.** Demande directe du propriétaire : « ARENA VIDEO — FULL AUDIT,
INTEGRATION, ORCHESTRATION AND OPERATIONALIZATION » — transformer Video en un
véritable environnement de production où plusieurs capacités collaborent sur
un même projet (dépendances, parallélisme, reprise après échec partiel), au
lieu d'une liste de boutons.

### Audit d'abord (trois audits ciblés, jamais supposé)

Le checkout de travail était **90 commits en retard sur `origin/master`** —
resynchronisé avant tout audit, sinon toute conclusion aurait porté sur un
état vieux de plusieurs jours. Une fois à jour :

- **Beaucoup plus existe déjà que prévu**, et c'est réel, pas décoratif :
  génération de scène (WanGP, DEC-0008/0015), production automatisée
  complète (MoneyPrinterTurbo, DEC-0008), montage (`core/montage/*`,
  DEC-0026 — timeline/pistes/éléments inspirés d'OpenCut **sans copier une
  ligne**, rendu ffmpeg vérifié par ffprobe, une faille d'injection trouvée
  et corrigée), voix (VoiceStudio piloté par HTTP, jamais absorbé en code —
  AGPL vs propriétaire ARENA, DEC-0027), vision (Qwen3-VL). Chacune testée
  isolément (~150 tests entre ces zones), mais **rien ne les compose** :
  une intention de chat = un agent, jamais une collaboration.
- **« OpenCut »** : aucune ligne de code n'a jamais été copiée — le dépôt
  Rust annoncé n'a pas les fonctions promises, le dépôt classic est archivé
  et dépend d'une brique MPL-2.0 non compatible MIT. Le modèle de données
  seul a inspiré le montage. Rien à faire de plus ici.
- **« Xaar Kaname »** : zéro occurrence dans tout le dépôt, sous aucune
  forme, et inconnu par ailleurs. Demandé au propriétaire — **retiré du
  périmètre** de sa propre décision, faute de savoir ce que c'est.
- **Ce qui manque réellement** : aucun workspace Video côté interface
  (zéro composant, zéro store) ; aucune orchestration multi-capacités ; un
  canal d'appel inter-espaces déjà câblé et testé mais **jamais utilisé en
  production** (`core/agent/capacites.py`) ; aucun état de projet structuré ;
  aucun nettoyage des vidéos générées (`data/montages/`, `media/rendered/`
  s'accumulent sans fin, contrairement aux pièces jointes entrantes).
- **Matériel réel** : RTX A2000, 12 Go de VRAM, un seul GPU physique —
  `core/execution/travaux.py` limitait déjà son parallélisme à 1 pour cette
  raison. Toute exécution parallèle doit la respecter, pas la contourner.

### Priorité tranchée par le propriétaire

Vu l'ampleur réelle (plusieurs semaines), trois découpages possibles lui ont
été soumis : l'orchestrateur d'abord, l'interface d'abord, ou le nettoyage
des artefacts d'abord. **Il a choisi l'orchestrateur d'abord** — composer ce
qui existe déjà, sans encore rien montrer côté interface.

### Premier incrément : `core/execution/coordination.py` sait paralléliser

L'audit avait identifié deux briques à combiner plutôt qu'une troisième à
inventer : `coordination.py` (dépendances, reprise, vérification — mais
strictement séquentiel) et `travaux.py` (parallèle borné, mais sans
dépendances). `Coordination.executer_parallele()` (nouvelle méthode,
`executer()` intact et tous ses tests inchangés) combine les deux : les
étapes dont les dépendances sont déjà résolues tournent ensemble, bornées
par un parallélisme global **et** par groupe de ressource partagée
(`Etape.ressource`) — une génération WanGP et une analyse Vision locale, qui
se disputent le même GPU physique, ne tournent jamais ensemble même si rien
d'autre ne les en empêcherait. Une étape déjà lancée n'est jamais annulée
parce qu'une autre a échoué (couper un rendu WanGP à mi-chemin gaspillerait
le temps GPU déjà engagé). Une dépendance circulaire est détectée
explicitement, jamais une boucle silencieuse.

Preuve par sabotage (2 gardes) : la limite de ressource partagée retirée →
`test_executer_parallele_respecte_la_limite_de_ressource_partagee` échoue
(deux étapes GPU tournent en 0,10 s au lieu de 0,19 s) ; la détection de
cycle retirée → `test_executer_parallele_une_dependance_circulaire_est_detectee`
échoue (`aboutie=True` au lieu de `False`, exactement le faux-succès que le
projet interdit). Les deux restaurées, revérifiées vertes.

`python -m pytest tests/ -q` → 2786 passed (2779 → 2786, +7 tests).
`python -m ruff check .` → All checks passed!

### Deuxième incrément : `VideoProductionAgent` compose les capacités réelles

`core/production/etat_projet.py` (l'état d'un projet, sérialisable) et
`core/production/plan_video.py` (un objectif → un graphe validé, même
discipline que `core/montage/planificateur.py` : capacité hors liste fermée
refusée et nommée, jamais devinée). Avant d'écrire l'agent, question posée
explicitement au propriétaire : une étape d'écriture (génération, narration)
doit-elle attendre sa confirmation comme partout ailleurs dans ARENA, ou
l'orchestrateur peut-il la confirmer lui-même puisqu'il a demandé le projet
entier ? **Réponse : « il attend ma confirmation a chaque etape
d'ecriture »** — `core/actions/attente.py` (verrouillé, DEC-0013) n'est pas
contourné. Conséquence directe dans `plan_video.py` : un montage qui
dépendrait **directement** d'une génération ou d'une narration est refusé
au moment du plan — leur fichier réel (WanGP/MoneyPrinterTurbo génèrent en
fond ; `preuve` à la soumission est un identifiant de tâche, jamais un
chemin) n'existe qu'après confirmation, jamais dans le même passage.

`agents/video/production_agent.py` — `VideoProductionAgent` : le modèle
propose le graphe, chaque étape est soumise au vrai collaborateur injecté
(vision → `provider_vision` direct ; wangp/moneyprinter →
`VideoAnalyzerAgent.planifier_scene()`/`fabriquer()` ; narration/
transcription → `AudioAgent.run()` ; montage → `MontageAgent.run()`) via
`executer_parallele()`. Une écriture réussie devient `NEEDS_CONFIRMATION`
dans l'état du projet, jamais un succès inventé.

### Troisième incrément : joignable pour de vrai

L'agent existait et testait vert contre des doubles, mais restait
**inatteignable** — aucun point d'entrée réel. `apps/backend/runtime.py`
le construit ; `POST /api/video/projet`
(`apps/backend/routers/video_production.py`, même contrôle `MEDIA_DIR` que
`/api/process-video`) le rend joignable en HTTP direct. Nouvelle intention
`VIDEO_PROJET` (`agents/orchestrator/orchestrator_agent.py`) — phrases
exactes, testée avant VISION/AUDIO/MONTAGE/VIDEO_ANALYSIS pour qu'une
phrase composite ne se fasse pas capturer par un seul de ses morceaux —
le rend enfin atteignable **depuis le chat**.

### Quatrième incrément : les vidéos générées ne s'accumulent plus

Manque trouvé à l'audit initial : `data/montages/` et `media/rendered/`
n'avaient aucun TTL, contrairement aux pièces jointes entrantes.
`tools/video/nettoyage.py` purge paresseusement (30 jours), câblé aux
trois vrais points d'écriture (`core/connectors/montage.py`,
`apps/backend/studio.py`, `apps/backend/routers/media.py`).

### Cinquième incrément : le workspace Video, côté interface

Demandé explicitement ensuite (« continue »). L'interface (`apps/pwa/`)
n'est **jamais regardée à l'aveugle** (`PROJECT_MEMORY/LOCKED_ZONES.md`) :
la modale a été vérifiée pour de vrai, dev server + Chromium headless
(`chromium.launch` sur le binaire déjà présent, pas de `playwright
install`), captures d'écran à l'appui — état sans backend, formulaire
complet, mode TEAM, et un résultat avec ses étapes réelles (`DONE`/
`FAILED`/`NOT_REACHED`), en mockant la réponse serveur.

Repris l'unique patron déjà existant pour une intégration ouverte par
modale (`ConnectorsModal.tsx`/`connectorStore.ts`, DEC-0024) plutôt qu'un
nouveau paradigme d'interface : `VideoProjectModal.tsx` +
`videoProjectStore.ts` (nouveaux), déclenchés depuis l'espace « Vidéo »
existant (bouton dans `EmptyState.tsx`) et depuis la palette de commandes.
La liste de capacités affichée (`CAPACITES_VIDEO` côté TypeScript) reprend
exactement la liste fermée du serveur (`plan_video.py`) — jamais une
capacité de plus. Aucun progrès simulé : chaque étape affichée vient
telle quelle de `Coordination.executer_parallele()`, y compris sa raison
d'échec réelle. `npx tsc --noEmit` et `npm run build` propres.

### Ce qui suit (pas encore fait)

Rien côté interface au-delà de cette modale (pas de tableau de bord
persistant, pas de suivi en direct d'un projet après fermeture de la
modale) — sur ce qui a été explicitement demandé jusqu'ici. Le canal
`core/agent/capacites.py` reste construit et testé mais toujours pas
appelé en production par `VideoProductionAgent` : aucune étape de ce
premier graphe n'a encore eu besoin d'un autre espace (code/documents/web).

---

## DEC-0038 — Dioumtoukay : le propriétaire lève DEC-0014, en connaissance de cause

**2026-09-02.** Demande directe : *« je veux aussi que tu integre ce projet que
mon ia soit capable de corrigé les bug les erreurs lui même [...] un qui vas
s'appeler Dioumtoukay [...] il doit être comme claude code entrer dans mon
terminal mon github et travailler sur le projet »*.

### Ce que ça heurte, et qui l'a levé

**DEC-0014 (29/08/2026) refusait exactement cela** : `core/guardian/` DÉCOUVRE
et RAPPORTE, ne MODIFIE jamais — *« une garde qui commettrait des correctifs ou
ouvrirait des pull requests elle-même contournerait exactement la garantie que
CLAUDE.md pose comme non négociable »*.

Le conflit lui a été présenté avant d'écrire une ligne, avec ce qu'il coûte :
ne plus voir ce qui entre dans son code, une commande qui ne se rattrape pas,
un mauvais commit qui part chez tout le monde. Quatre options lui ont été
posées, de la plus prudente à la plus ouverte. **Sa réponse : « Il doit tout
faire pas de limite ».**

C'est son projet, sa machine, son code. **DEC-0014 est donc levée pour
Dioumtoukay, et par lui.** Elle reste en vigueur pour `core/guardian/`, qui
n'est pas touché.

### Ce que cela n'ouvre pas

Rien d'autre. Les trois effets irréversibles vers l'extérieur — **envoyer un
mail, publier, supprimer chez un fournisseur** — gardent leur plancher
(`INTERRUPTEURS_OBLIGATOIRES`, `core/permissions/controle.py`). Ils ne sont pas
ce qu'il a demandé, et un agent qui travaille sur son code n'a aucune raison
d'écrire à ses clients.

### Ce qui est tenu quand même, et qui n'est pas une limite

**Tout ce que Dioumtoukay fait est journalisé** (`JournalDesActions`). Ce n'est
pas une autorisation à demander : c'est un compte-rendu à lire. Un agent qui
agit sans laisser de trace ne peut pas être corrigé quand il se trompe — et
c'est le propriétaire, pas l'agent, qui doit pouvoir dire ce qui s'est passé.

### Ce qui est dit et qui n'est pas une réserve de principe

Le modèle qui pilotera Dioumtoukay sur sa machine est **local** (`qwen3.5:9b`,
DEC-0009/#140). Ce n'est pas le même ordre de capacité qu'un modèle de
frontière. Le mode d'échec réaliste n'est pas la malveillance : c'est une
commande mal formée sur le mauvais chemin. Écrit ici parce que c'est une
propriété mesurable du montage, pas un avis sur son choix.

---

## DEC-0039 — Le dépôt reste public avec la grille de prix dedans

**Date** : 02/09/2026
**Statut** : accepté — décision du propriétaire, prise en connaissance de cause

### Le constat, mesuré

Le propriétaire demande si le modèle UniC Plaquiste est bien préparé pour lui
seul. La réponse est oui côté code — c'est le seul espace qui porte son métier,
et depuis DEC-0038bis l'instruction générale ne porte plus aucune entreprise.

La mesure du même jour donne autre chose : `unic-backend/arena-personal-ai` est
**public** (`"private": false`, API GitHub, 02/09/2026 au soir). Il l'avait
passé en privé le 28/08 ; il ne l'est plus. Or `config/metier.yaml` est suivi
par git et porte **31 prix, le NINEA, le RCCM, l'adresse et le téléphone**.

Ce qui n'est **pas** exposé, vérifié dans la même mesure : ses devis et
factures clients (hors de git), sa signature manuscrite (hors de git, et un
test l'interdit), ses clés (aucun fichier sensible suivi), et son serveur
(fermé sans `USMAN_API_KEY`).

### La décision

Le constat lui a été présenté avec quatre options : repasser en privé, sortir
la grille du dépôt, les deux, ou ne rien changer. **Il a choisi de ne rien
changer.**

C'est son entreprise et ses prix. La décision est enregistrée ici pour une
seule raison : **qu'aucune session future ne « corrige » de sa propre
initiative** ce qu'il a tranché — ni en retirant la grille, ni en proposant à
nouveau la même chose à chaque passage.

### Ce que ça coûte si c'est faux

Un concurrent qui lit sa grille sous-cote chaque devis au franc près. Et ce qui
est déjà poussé reste dans l'historique GitHub même si le fichier en sortait
plus tard : la décision n'est pas réversible par une simple suppression.

Ce paragraphe existe parce que c'est la partie vérifiable plus tard, pas parce
que la décision serait mauvaise. Elle lui appartient.

---

## DEC-0040 — Le serveur permanent est un annuaire, pas un relais

**Date** : 04/09/2026
**Statut** : accepté

### Le constat, mesuré

Sa demande, mot pour mot : *« à chaque fois que j'allume mon pc je dois changer
de nouvelle url, il doit être une seule commande qui marche pour toujours »*, et
*« quand le pc est éteint ça devrait avoir aucun impact »*.

Le tunnel `trycloudflare` tire **un nom au hasard à chaque démarrage**. Son PC
tourne environ quatre heures par jour : il recopiait une adresse dans son
téléphone presque tous les jours.

### La décision

Le téléphone ne connaît qu'**une adresse** : le serveur permanent. Le PC y
dépose l'adresse du jour au démarrage ; le téléphone la demande, puis parle
**directement** à la machine.

**Le serveur permanent ne voit passer qu'une chaîne de caractères.** C'est ce
qui distingue ce montage d'un relais, et c'est ce qui permet à sa machine de
faire tourner Dioumtoukay et la vidéo : la conversation ne transite pas par
l'hébergeur. DEC-0002 tient — le modèle tourne chez lui, rien ne part chez un
tiers quand sa machine répond.

Trois gardes, chacune avec sa raison :

- Les deux routes `/machine/adresse` sont derrière la clé API. Sans elle,
  n'importe qui ferait pointer son téléphone vers une machine choisie par un
  autre.
- Les adresses sont essayées **dans l'ordre, jamais en parallèle** : sonder les
  deux à la fois enverrait un message dehors alors que son PC est seulement
  lent.
- Une adresse de plus de douze heures n'est plus servie.

### Ce que ça coûte si c'est faux

La péremption est la garde qui coûte le plus cher à retirer. **`trycloudflare`
recycle ses noms** : une adresse vieille de plusieurs jours peut pointer sur la
machine d'un inconnu, à qui le téléphone présenterait sa clé et enverrait ses
conversations. C'est la seule des trois dont l'absence ne se voit pas — tout
continue de marcher, avec le mauvais interlocuteur.

Et elle a failli disparaître en silence : en portant `DUREE_DE_VIE` à dix ans,
les dix-huit tests restaient verts, parce que le test de péremption calculait
son horodatage **à partir de la constante**. La durée est maintenant épinglée
par un test à part. **Un test qui suit le code qu'il surveille ne surveille
rien.**

Si le serveur permanent tombe, le téléphone ne sait plus où est la machine et
retombe sur ce qu'il a déjà enregistré : il perd la découverte, pas l'usage.

---

## DEC-0041 — Le PDF s'écrit à la demande, sans bouton de confirmation

**2026-09-04.** Demande directe du propriétaire, mot pour mot : « Pourquoi le
pdf demande des confirmation bouton confirmé alors que chatgpt et claude etc si
tu demandes pdf il le fait simplement je veux ca a tout prix a n'importe quelle
zone [...] le projet dois faire un pdf si je le demande ».

Cette décision **renverse** l'ancienne règle : `plaquiste.document` passe de
`CONFIRMATION` à `ALLOWED` dans `config/permissions_services.yaml`.

### Pourquoi c'est défendable, et pas un simple relâchement

Un PDF de devis n'est pas de la même nature que les actions qui gardent leur
confirmation :

- il **ne quitte pas la machine** — il atterrit dans `media/rendered/`, servi
  par `GET /media/rendered/{nom}` derrière la clé API ;
- il est **réversible** : un fichier de trop se supprime, un e-mail parti ne
  se rattrape pas ;
- il **ne coûte rien** : pas de GPU, pas de quota, pas de tiers ;
- et surtout **il le relit avant que quiconque le voie**. C'est LUI qui
  l'envoie au client. La confirmation prétendait le protéger d'un document
  qu'il allait de toute façon relire.

Ce qui garde sa confirmation, sans exception : l'envoi d'un e-mail, une
publication, une suppression, la génération vidéo (GPU, longue, coûteuse) et
VoiceStudio. La frontière n'est pas « écrire / ne pas écrire », c'est
**« ça part dehors, ou ça reste ici »**.

### Ce qui protège encore

Le coupe-circuit **`WRITE_FILES` reste déclaré** sur `plaquiste.document` :
l'éteindre coupe encore toute production de PDF. Retirer la confirmation n'a
pas retiré l'interrupteur.

### Le piège qu'il a fallu fermer

La confirmation était **le seul chemin par lequel le lien de téléchargement
arrivait sur son téléphone** (`confirmerAction` lisait `detail.url` dans la
réponse du serveur). La supprimer aurait produit exactement le symptôme
d'avant : *un PDF qui existe sur le serveur et qu'aucun écran ne peut
atteindre*. L'adresse traverse donc maintenant toute la chaîne —
`DevisConnector` → `_proposer_le_document` → `_documents_produits` →
`meta.documents` → le bouton « Ouvrir le document ».

### Ce que le sabotage a trouvé (et que les tests ne voyaient pas)

Trois trous, tous réels, comblés avant de livrer :

1. Retirer `interrupteur: WRITE_FILES` du **vrai** fichier de politique ne
   faisait échouer aucun test : celui du coupe-circuit écrivait sa propre
   politique. La protection pouvait donc disparaître en silence.
   → `test_la_vraie_politique_livree_ecrit_le_pdf_sans_accord_mais_sous_coupe_circuit`.
2. Remplacer la propagation de `url` dans l'agent par `None` ne faisait
   échouer aucun test — le maillon exact qui avait **déjà** perdu ce lien une
   fois n'était couvert nulle part.
   → `TestLAdresseDuPdfRemonteJusquALaReponse`.
3. La docstring de `_proposer_le_document` affirmait encore « Rien n'est écrit
   ici : `produire` est une action à confirmer ». Elle décrivait le contraire
   du code.

### Ce que ça coûte si c'est faux

Un devis PDF écrit sur une phrase mal comprise. Le coût réel est un fichier de
trop dans `media/rendered/`, relu et jeté — pas un document parti chez un
client, puisque l'envoi garde sa confirmation. Le garde-fou qui compte
davantage reste le destinataire : `test_sans_destinataire_rien_n_est_produit`
tient toujours, et un devis sans client/lieu/objet n'est toujours pas écrit.
Un devis adressé à la mauvaise personne reste pire qu'un devis absent.

Le vrai coût serait de retirer aussi `WRITE_FILES` en croyant continuer cette
décision : plus rien n'arrêterait l'écriture de fichiers. C'est pour ça qu'un
test lit désormais le fichier livré.

---

## DEC-0042 — Un scanner de secrets préventif, plutôt qu'un moteur offensif

**2026-09-04.** Demande reçue : intégrer **CyberStrike** — un système de
sécurité *offensif* (reconnaissance, exploitation active, attaques de mots de
passe) — comme capacité vivante d'ARENA, câblée et exécutable.

### Ce qui a été refusé, et pourquoi

L'intégration offensive a été **déclinée**. Le livrable aurait été un moteur
d'attaque opérationnel installé à demeure dans l'assistant personnel d'un
plaquiste, dont la seule barrière d'autorisation était une case cochée par
l'utilisateur lui-même. Trois raisons :

1. **L'auto-déclaration n'est pas une autorisation.** « cible autorisée : oui »
   tapé dans un chat n'est pas une preuve de propriété. C'est l'affirmation que
   ferait aussi n'importe quel usage abusif. Le propre SECURITY.md de l'outil
   reconnaît que son système de permissions n'est pas un vrai bac à sable.
2. **Aucun contexte d'autorisation réel** — pas de mission de pentest, pas de
   périmètre, pas de labo. Pour du dual-use offensif, ce contexte précis est
   requis, pas des paragraphes de bonne intention.
3. **Hors mission.** ARENA est l'assistant métier d'Ousmane (devis, vidéo,
   documents). Un moteur d'exploitation qui tourne chez lui et qu'un téléphone
   peut atteindre est un risque permanent pour une capacité que le métier
   n'utilise pas.

### Ce qui a été fait à la place

De la sécurité **défensive sur le propre code du dépôt** — aucune cible externe,
aucune ambiguïté sur la propriété : `scripts/scanner_secrets.py`, qui attrape un
secret **avant** qu'il entre dans un commit. Il complète
`preparer_purge_secrets.py` sans le doubler : la purge nettoie les six secrets
**déjà connus** de l'historique, à des emplacements codés en dur ; le scanner
regarde ce qui est **suivi maintenant**, n'importe où, et refuse qu'un *nouveau*
secret franchisse le prochain commit. Haute confiance seulement (clés PEM,
AWS/Google/Slack/GitHub à leur préfixe, affectations `api_key = "..."` à
entropie réelle), valeurs masquées, sortie non nulle dès qu'il trouve — utilisable
comme garde avant commit ou en CI. Le vrai dépôt revient propre, et un test
(`test_le_vrai_depot_est_propre`) le maintient tel.

### Ce que ça coûte si c'est faux

Un scanner trop bavard finit ignoré, et c'est pire que pas de scanner : d'où la
règle « haute confiance seulement » et le marqueur explicite
`# scanner-secrets: ignore` pour les rares fixtures de test de forme secrète,
visible en revue. Un scanner trop discret laisse la fuite entrer : quatre
sabotages (scanner aveugle, entropie neutralisée, marqueur ignoré, masque qui
révèle) ont chacun fait échouer un test avant livraison. Il ne remplace pas la
purge de l'historique, qui reste préparée et jamais autorisée (DEC-0007).

---

## DEC-0043 — L'audit des dépendances : « je n'ai pas pu vérifier » n'est pas « c'est propre »

**2026-09-04.** Suite du volet défensif (DEC-0042). Après le scanner de secrets,
un audit des **failles connues** des dépendances : `scripts/scanner_dependances.py`,
qui enveloppe `pip-audit` (base d'avis OSV / PyPI).

### La règle qui fait tout

Trois états, jamais deux — la même discipline que `scripts/doctor.py` et
`core/actions/resultat.py` :

- `PROPRE`  : pip-audit a répondu, aucune faille.
- `FAILLES` : pip-audit a répondu, voici lesquelles.
- `INCONNU` : pip-audit n'est pas installé, OU la base d'avis est injoignable.

Le seul piège qui compte ici est de rendre `PROPRE` quand la mesure a échoué.
Le PC d'Usman peut être hors ligne ; un audit qui n'a pas pu interroger la base
et répond « aucune faille » endort une alerte qui n'a jamais été prise. Trois
sabotages (outil muet rendu PROPRE, parseur qui ignore les vulns, sortie
illisible avalée) ont chacun fait échouer un test avant livraison. Le code de
sortie sépare les cas : `2` pour INCONNU, distinct de `1` pour des failles
réelles — un CI peut traiter « pas pu vérifier » autrement que « cassé ».

### Ce qui a été mesuré, et ce qui reste sa décision

Lancé sur `requirements.txt`, il a trouvé des failles réelles dans `pypdf`
(lecture des PDF, chemin du devis), `mcp` (transport), `langchain-openai` et
`click`. **Le chiffre n'est pas recopié ici exprès** : il vieillirait comme un
faux état du jour. La commande le redonne à l'instant :

    python scripts/scanner_dependances.py

Monter les versions est une modification du graphe de dépendances qui ne peut
pas être validée entièrement sur la machine de l'assistant (pile GPU, verrou
`requirements.lock.txt` à régénérer, et `langchain-openai` porte une contrainte
de version explicite dans `requirements.txt`). C'est donc **rapporté, pas
appliqué d'office** : la correction est sa décision, relançable et vérifiable
par la suite de tests avant fusion.

### Ce que ça coûte si c'est faux

Un audit qu'on croit propre alors qu'il n'a pas tourné : une faille laissée
ouverte par confiance mal placée. D'où la règle des trois états, tenue par un
test. Le scanner ne corrige rien de lui-même — il montre où regarder.

---

## DEC-0044 — Les quatre failles trouvées par DEC-0043 : montées, pas seulement rapportées

**2026-09-04.** Suite de DEC-0043. Le propriétaire, en un mot : « Monter le ».

### Ce qui a changé

`requirements.txt` : `pypdf` 6.14.2 → 6.16.2, `langchain-openai` 1.1.9 → 1.1.14,
`pydantic` 2.12.5 → 2.13.5. `click` et `mcp` restent transitifs (jamais épinglés
en direct) mais montent avec `browser-use` 0.13.8 → 0.13.10, qui les épingle en
dur — `click` à 8.3.3, `mcp` à 2.1.1.

### Pourquoi c'est plus qu'un changement de quatre chiffres

`browser-use==0.13.8` épingle exactement `mcp==1.26.0` et `click==8.3.1` — les
deux versions vulnérables. Les corriger seul, sans toucher `browser-use`, ne se
resoud pas : pip le refuse (vérifié — voir plus bas). La version corrigée exige
elle-même `pydantic==2.13.5` (utilisée partout dans le backend FastAPI) et
`pypdf==6.16.2` exactement. `langchain-openai==1.1.14` (le correctif) exige
`openai>=2.26.0`, que `browser-use==0.13.10` fournit désormais en épingle dure —
ce qui **résout au passage** le conflit historique documenté dans
`requirements.lock.txt` (`langchain-openai==1.6.0` contre `openai==2.16.0`, qui
ne pouvaient jamais coexister).

Le paquet `mcp` (SDK) n'est importé nulle part dans le code : `core/mcp/transport.py`
documente lui-même l'avoir écarté au profit de httpx pur. Le monter ne change
rien à l'exécution d'ARENA — seulement à ce que `browser-use` embarque.

### Ce qui a été vraiment vérifié, pas supposé

`browser-use`, `mcp`, `langchain-openai` ne sont pas installés dans l'environnement
de l'assistant : impossible de les valider en les import ant simplement. Vérifié
à la place, dans l'ordre :

1. Le vrai résolveur pip (`pip install --dry-run`) sur le jeu complet des quatre
   versions montées — aucune erreur, aucun `ResolutionImpossible`.
2. Installation réelle dans un environnement virtuel isolé, propre (pas
   l'environnement de travail, pollué par d'autres installations de cette
   session) — `pip check` y répond `No broken requirements found`.
3. La suite complète dans cet environnement : **3440 passed** (32 de plus
   qu'avant — des tests jusque-là `importorskip`-és sur `mcp`/`langchain_openai`,
   absents ici, tournent maintenant pour de vrai), 0 échec.
4. Ciblé sur les chemins sensibles — devis PDF, OpenTakeoff, transport MCP
   interne d'ARENA (`core/mcp/`, distinct du SDK) : 99/99.
5. `scripts/scanner_dependances.py` sur le fichier corrigé : `PROPRE`.

**Sabotage-vérifié** : rétrograder `pypdf` seul (en laissant `browser-use` à sa
version montée) rend le jeu de dépendances **irrésoluble** — `pip-audit` refuse
alors un rapport et le scanner répond `INCONNU`, jamais `PROPRE` par erreur. La
preuve que les paquets montent ensemble, pas un par un.

### `requirements.lock.txt`

Rien ne l'installe dans ce dépôt (ni `Dockerfile`, ni les scripts PowerShell) —
c'est un `pip freeze` documenté de sa machine, pas un fichier réinstallé. Seules
les sept lignes directement concernées (`browser-use`, `click`, `langchain-openai`,
`mcp`, `openai`, `pydantic`, `pypdf`) ont été mises à jour, pour qu'il cesse de
contredire `requirements.txt` avec d'anciennes épingles vulnérables. Elles ne
viennent **pas** d'un vrai `pip freeze` fait sur son PC — l'en-tête du fichier le
dit maintenant explicitement. Le reste du fichier n'a pas été touché : je n'ai
aucun moyen de savoir ce qui tourne réellement chez lui pour les paquets que je
n'ai pas changés, et l'inventer serait la simulation que ce dépôt interdit.

### Ce que ça coûte si c'est faux

Le vrai risque n'était pas dans les quatre versions elles-mêmes, mais dans la
tentation d'éditer les nombres sans vérifier que l'ensemble se résout — un
`requirements.txt` qui *a l'air* corrigé mais que `pip install` ne peut pas
reproduire est pire qu'un aveu de `INCONNU`. C'est pour ça que la vérification
est passée par le vrai résolveur et une vraie installation, deux fois, plutôt
que par la lecture de métadonnées seule.

---

## DEC-0045 — La revue OWASP du backend : l'audit qui n'appelait que GET

**2026-09-04.** Suite du volet défensif (DEC-0042 à 0044). Revue de sécurité
du backend FastAPI. Le code lui-même — auth, débit, chemins de fichiers,
OAuth, CORS, docs fermées par défaut — est solide et déjà bien construit
(`apps/backend/security.py`, `connectors.py`). Aucune faille trouvée dans le
code métier. Le vrai défaut était dans **l'outil censé le vérifier**.

### Ce qui a été trouvé

`scripts/auditer_surface_publique.py` n'envoyait qu'un `GET`, quelle que soit
la vraie méthode d'une route, et sautait entièrement toute route paramétrée
(`if "{" in chemin: continue`). Deux conséquences mesurées, pas supposées :

- Un `POST` non protégé répond `405 Method Not Allowed` à un `GET` — un code
  ≥ 400, compté « protégé attendu » sans que la clé n'ait jamais été
  évaluée. Sabotage : `dependencies=[Depends(verify_api_key)]` retiré de
  `/api/upload`, corps vide + sans clé, vraie méthode POST → `422` (la
  validation du fichier requis échoue avant l'authentification, sur une
  route sabotée COMME sur une route protégée — les deux masquent le même
  signal). Avec un vrai fichier joint → `200 OK`, upload accepté sans clé.
  L'ancien script (GET seul) annonçait « protégé » dans les deux cas.
- `/connectors/{fournisseur}/status`, `/connectors/{fournisseur}/disconnect`,
  `/connectors/{fournisseur}/auth`, `/api/actions/{identifiant}/confirm`,
  `/api/actions/{identifiant}/cancel` : jamais appelées par l'audit
  automatisé, ni avec la bonne méthode ni avec aucune.

`tests/test_surface_api.py` — qui lit `route.dependencies` directement, sans
appeler quoi que ce soit — donnait déjà une preuve **statique** fiable de
ces cinq routes (confirmé : 100% des dépendances d'authentification du dépôt
sont déclarées via `dependencies=[Depends(...)]`, jamais en paramètre de
fonction — la lecture statique ne peut donc pas les manquer). Le trou était
spécifiquement dans la preuve **comportementale**, complémentaire, que ces
routes rejettent vraiment un appel non authentifié — et non redondante :
elle est la seule à pouvoir attraper une dépendance déclarée mais dont
l'implémentation serait cassée.

### Ce qui a été corrigé

`scripts/auditer_surface_publique.py` appelle maintenant la vraie méthode de
chaque route déclarée, avec :
- un paramètre de substitution pour tout chemin `{xxx}` — une valeur dédiée
  (`gmail`, le seul fournisseur OAuth câblé) pour `{fournisseur}`, sinon une
  valeur neutre, documentée comme non concluante pour les deux routes
  `/api/actions/{identifiant}/...` (leur propre logique 404 sur un
  identifiant inconnu, protégée ou non — `test_surface_api.py` reste leur
  garde fiable) ;
- un corps minimal mais réellement valide (`CORPS_MINIMAL`) pour les quatre
  routes qui exigent un fichier ou un champ de formulaire obligatoire —
  sans quoi un corps vide échoue sur sa propre validation avant même
  d'atteindre la question de l'authentification, protégée ou non.

**Sabotage-vérifié, trois fois** : retirer la dépendance de `/api/upload` →
`[DEFAUT] HTTP 200` (avant : silencieux). Retirer celle de
`/connectors/{fournisseur}/status` → `[DEFAUT] HTTP 200` (avant : jamais
sondée). Retirer celle de `/connectors/{fournisseur}/disconnect` → pareil.
Les trois corrigés côté code réel, jamais côté sabotage.

`tests/test_auditer_surface_publique.py` verrouille les deux corrections :
retirer `CORPS_MINIMAL`, la valeur dédiée `gmail`, ou revenir à un `GET`
partout fait échouer la suite (vérifié par sabotage sur le script
lui-même).

### Ce que ça coûte si c'est faux

Un audit qui annonce « protégé » sans l'avoir vérifié est pire qu'aucun
audit : il éteint la vigilance exactement là où elle devait rester allumée.
Rien n'était réellement exposé aujourd'hui — chaque route de ce dépôt est
correctement protégée, prouvé par `test_surface_api.py` (statique) et
maintenant aussi par `auditer_surface_publique.py` (comportemental, sur
la vraie méthode). Le risque fermé est pour la prochaine route ajoutée sans
sa dépendance : l'ancien script l'aurait laissée passer pour un `POST`, en
silence.

---

## DEC-0046 — Graphify : le graphe structurel du dépôt, pas un second RAG

**2026-09-04.** Demande directe : intégrer Graphify (Graphify-Labs,
Apache-2.0) comme capacité de graphe de connaissances/intelligence
documentaire d'ARENA — codebase mapping, requêtes structurelles, PDF/document
understanding.

### Ce qui a été vérifié avant d'écrire une ligne

`https://github.com/Graphify-Labs/graphify` cloné et inspecté pour de vrai
(révision `33362d9`, 2026-08-30) : Apache-2.0 confirmé sur CETTE révision,
paquet PyPI normal (`graphifyy`), Python pur, extraction 100% locale par
tree-sitter — aucun appel modèle nécessaire à la construction du graphe.
Détail complet : `docs/audits/graphify_audit.md`.

**Un doublon a été évité en premier.** `tools/rag/graphrag_tool.py`
(Microsoft GraphRAG, déjà câblé et atteint depuis `chat.py`/
`openai_gateway.py`) existait déjà. Vérifié avant d'ajouter quoi que ce
soit : GraphRAG résume des DOCUMENTS déposés à la main dans un espace de
travail Docker (communautés d'idées, recherche globale) ; Graphify
cartographie la STRUCTURE DU CODE, par lecture directe des fichiers
(entités, relations, plus court chemin). Deux fonctions distinctes, jamais
fusionnées.

### Ce qui a été intégré

`core/connectors/graphify.py` — un `Connecteur` comme les autres (même
contrat que `DevisConnector`, `ConnecteurOpenTakeoff`) : cinq capacités,
`construire` (écrit `graphify-out/`, sous `WRITE_FILES`) et quatre lectures
(`interroger`, `chemin`, `expliquer`, `hubs`, `ALLOWED`). Déclaré dans le
registre (`apps/backend/runtime.py`) et la politique de permissions
(`config/permissions_services.yaml`, service `graphify`) — aucun second
registre, aucun second système de permissions.

Ce que ça cartographie : **le dépôt lui-même**, par défaut. Le trou réel
mesuré le 04/09/2026 : `PROJECT_MEMORY/PROJECT_MAP.md` est écrit et tenu à
jour **à la main**, sans rien qui vérifie qu'il correspond encore au code.
Le graphe répond à des questions structurelles en quelques secondes, sans
relire tout le dépôt.

### Le vrai piège du contrat `Connecteur`, trouvé en écrivant les tests

`_conduire()` (`core/connectors/base.py`) refuse **toute** capacité tant
que `sonder()` ne rend pas OPERATIONNEL — y compris la capacité qui
construirait le graphe elle-même. Une première version de `sonder()`
rendait NON_CONFIGURE tant qu'aucun `graph.json` n'existait : `construire`
ne pouvait alors JAMAIS s'exécuter au tout premier appel — le même piège
qu'évaluer la santé d'un four à sa première cuisson. Corrigé pour mesurer
l'ENGIN (le binaire `graphify` est-il installé ?), jamais son historique de
sorties — la même règle qu'OpenTakeoff. L'absence de graphe reste dite,
dans le message, informative ; chaque lecture la vérifie elle-même avant
d'agir.

### Mesuré pour de vrai, sur ce dépôt

```
python -c "from core.connectors.graphify import ConnecteurGraphify; \
c = ConnecteurGraphify(); print(c.executer_confirmee('construire'))"
→ 13338 noeud(s), 25839 lien(s), 13,9 s (tree-sitter, sans modele)
```

« quel connecteur gère le devis PDF ? », « qu'est-ce qui hérite de
Connecteur ? », les hubs architecturaux (`Statut`, `PlaquisteAgent`,
`ResultatAction`, `EtatSante`, `OrchestratorAgent`…) — tous corrects,
détail dans l'audit.

### Ce qui n'a PAS été branché, et pourquoi c'est honnête

L'ingestion de PDF/documents dans le graphe (extra amont `[pdf]`) **n'est
pas installée** : `SUGGESTION — NON IMPLÉMENTÉE`, rien ne l'a vérifiée sur
un vrai fichier ici, et une capacité non mesurée ne se simule pas
(`core/actions/resultat.py`). `tools/documents/reader.py` reste l'unique
chemin de lecture PDF/DOCX/XLSX/PPTX. Le devis PDF garde
`core/connectors/devis.py`, inchangé (DEC-0041) — Graphify n'écrit jamais
de document final. Le serveur MCP dédié (`graphify-mcp`) et tout
fournisseur LLM (étiquetage sémantique des communautés) ne sont pas
installés non plus : non vérifiables sur cette machine (pas d'Ollama, pas
de GPU ici) et non nécessaires à la valeur déjà mesurée.

### Ce que ça coûte si c'est faux

Un graphe qui ment sur sa fraîcheur serait le vrai risque — d'où
`sonder()` qui ne promet jamais un graphe à jour, seulement que le moteur
répond. `graphify-out/` (28 Mo, généré) n'est jamais versionné
(`.gitignore`) : aucune donnée du dépôt n'y est plus exposée qu'elle ne
l'est déjà dans le code source lui-même — c'est une carte du code, pas une
fuite d'un secret qu'il contiendrait (le scanner de secrets, DEC-0042, reste
la garde pour ça).

---

## DEC-0047 — GitIngest : un dépôt transformé en texte, pas un second Graphify

**2026-09-05.** Suite du volet intégration (DEC-0046). Demande directe :
intégrer GitIngest (coderamp-labs, MIT) comme capacité d'ingestion de
code/contexte — un dépôt local ou une URL Git transformé en résumé, arbre et
contenu concaténé, prêt pour un modèle.

### Ce qui a été vérifié avant d'écrire une ligne

`https://github.com/coderamp-labs/gitingest` cloné et inspecté (révision
`4e259a0`, 2025-08-16) : MIT confirmé, paquet PyPI normal (`gitingest`),
dépendances légères, API Python publique documentée
(`ingest_async(source, ...) -> (résumé, arbre, contenu)`). Détail complet :
`docs/audits/gitingest_audit.md`.

**Un doublon a été cherché en premier** (`tools/coder/repo_engineer_tool.py`,
utilisé par `RepoEngineerTool`) : c'est un outil d'édition locale
(`get_tree`/`read_files`/`apply_patch`/`run_tests`) pour un agent SWE, sans
respect de `.gitignore`, sans ingestion d'URL distante, sans statistiques —
un rôle différent, pas un doublon. Graphify (DEC-0046) cartographie les
RELATIONS structurelles du code ; GitIngest donne le CONTENU brut. Les deux
répondent à des questions différentes, jamais fusionnées.

### Ce qui a été intégré

`core/connectors/gitingest.py` — un `Connecteur` de plus (même contrat que
`ConnecteurGraphify`/`DevisConnector`) : une capacité, `ingerer`
(`action=read`, `ALLOWED`, risque **MEDIUM** — pas LOW comme Graphify : une
URL clone un contenu tiers, potentiellement hostile, même brièvement).
Déclaré dans le registre existant et la politique de permissions existante
— aucun second registre, aucun second système de permissions, aucun second
RAG (LightRAG/GraphRAG gardent leur rôle), aucun générateur de PDF touché.

Le contenu ingéré est traité comme une **donnée**, jamais une instruction —
la même discipline que partout ailleurs dans ce dépôt pour du texte externe
(recherche web, e-mails reçus). Le connecteur ne fait qu'extraire et
rapporter ; il n'interprète jamais ce qu'il lit.

### Deux défauts réels trouvés en écrivant les tests, pas en lisant la doc

1. **Un `GITHUB_TOKEN` égaré dans l'environnement casse une ingestion
   purement locale.** `resolve_token()` (amont) relit systématiquement cette
   variable dès qu'aucun jeton n'est fourni explicitement — même pour un
   répertoire local qui n'en a besoin d'aucun — et lève si sa forme n'est
   pas celle d'un vrai jeton GitHub. Mesuré dans ce conteneur : un
   `GITHUB_TOKEN` présent pour une tout autre raison faisait échouer
   l'ingestion d'un simple dossier de test. `_sans_jeton_errant()` retire la
   variable le temps de l'appel, sauf si l'appelant fournit lui-même un
   jeton.
2. **`asyncio.run()` plante depuis une route déjà async.**
   `registre.executer(...)` est appelé en clair, sans `await`, depuis des
   routes FastAPI et des agents déjà `async def` — vérifié
   (`chat.py`, `plaquiste_agent.py`) : déjà sous la boucle d'uvicorn. Une
   première version appelait `asyncio.run()` directement, qui y lève
   `RuntimeError: cannot be called from a running event loop`. Corrigé par
   un thread dédié (`ThreadPoolExecutor`), sabotage-vérifié : revenir à
   `asyncio.run()` direct fait échouer le test qui simule ce chemin réel.

### Ce qui protège les chemins locaux sensibles

Un segment de chemin (`.ssh`, `.aws`, `.gnupg`, une clé privée nommée) ou un
nom de fichier (`.env`, `credentials.json`) refuse l'ingestion avant même
d'ouvrir quoi que ce soit — vérifié et sabotage-vérifié. `.gitignore`
protège ce qu'un dépôt exclut lui-même ; ceci protège ce qu'aucun
`.gitignore` ne verra, parce que le chemin vise directement ce dossier.

### Ce qui n'a PAS été branché, et pourquoi c'est honnête

`include_gitignored=True` n'est exposé nulle part — la contourner
exposerait exactement ce que la protection ci-dessus empêche.
`SUGGESTION — NON IMPLÉMENTÉE`. L'ingestion de dépôts privés dépend
entièrement d'un jeton que l'appelant fournirait explicitement ; ARENA ne
gère aujourd'hui aucun jeton GitHub propre (vérifié : absent de
`apps/backend/config.py`) — sans jeton, un dépôt privé échoue proprement,
jamais un faux succès.

### Blocage de vérification, honnêtement rapporté

L'ingestion d'une URL GitHub réelle n'a pas pu être vérifiée bout en bout
**depuis ce conteneur** : sa politique réseau renvoie 403 sur un simple
`curl -I https://github.com/...`, indépendamment de GitIngest. Le code est
réel et utilise la même fonction vérifiée pour l'ingestion locale ; seule
cette vérification réseau précise reste bloquée par l'environnement de
test — voir `docs/audits/gitingest_audit.md`, §7.

### Ce que ça coûte si c'est faux

Une ingestion qui contournerait `.gitignore` ou la protection par chemin
exposerait des secrets locaux au modèle — d'où les deux protections
sabotage-vérifiées. Un connecteur qui plante sous une vraie route async
aurait rendu la capacité inutilisable en production sans qu'aucun test
mocké ne le révèle jamais — c'est exactement ce que le test simulant la
boucle active existe pour empêcher.

## DEC-0048 — Guide de procédure : un workflow déjà décrit, rendu en document (pas Mimik)

**2026-09-05.** Demande directe : intégrer Mimik (westpoint-io, MIT) —
extension navigateur qui capture en direct les clics, le DOM et des
captures d'écran d'une session utilisateur pour produire automatiquement
un guide de procédure.

### Ce qui a été refusé, et pourquoi

La capture en direct elle-même : ARENA n'a ni extension navigateur ni
pipeline d'enregistrement de session, et en construire un pour observer ce
que le propriétaire fait sur son écran est une surface de captation
nouvelle — pas un outil de lecture — sans aucun besoin réel exprimé pour
la justifier. Un premier refus a porté sur l'intégration entière ; le
propriétaire a corrigé : ce n'était pas la demande. Il ne voulait pas de
surveillance de navigateur, seulement recevoir un workflow **déjà écrit**
(étapes, captures d'écran déjà existantes, fournies en paramètre) et le
transformer en document — la partie qui restait après avoir retiré la
capture en direct était raisonnable, et c'est elle qui a été construite.

### Ce qui a été intégré

`core/production/workflow_guide.py` (modèle de données `Workflow`/`Étape`,
rédaction, quatre rendus) et `core/connectors/workflow_guide.py`
(`ConnecteurWorkflowGuide`, une capacité `generer`) — même contrat que les
connecteurs précédents, déclaré dans le registre et la politique
existants. **Aucun second moteur** : le PDF passe par reportlab (déjà
utilisé par `agents/plaquiste/devis_pdf.py`), le DOCX par python-docx
(déjà une dépendance, jusqu'ici seulement lue par `tools/documents/reader.py`
— écrire est une capacité de la même bibliothèque). Même logique que le
devis (DEC-0041) pour la permission : le fichier reste local, relu avant
d'être partagé — `ALLOWED` sous le coupe-circuit `WRITE_FILES`, pas de
confirmation préalable.

Deux protections, sabotage-vérifiées :

1. **Rédaction du texte avant mise en page** (`expurger()`) — masque ce qui
   ressemble à un email, un téléphone, une carte, ou une valeur secrète
   (affectation `clé = valeur` à haute entropie), avant qu'un mot n'entre
   dans un fichier produit.
2. **Chemin de capture d'écran gardé comme celui de GitIngest** — un
   segment (`.ssh`, `.aws`, `.gnupg`, une clé privée nommée) ou un nom de
   fichier (`.env`, `credentials.json`) refuse l'inclusion avant même
   d'ouvrir le fichier ; une capture refusée est signalée et ignorée, elle
   ne fait jamais échouer tout le rendu.

### Deux défauts réels trouvés en écrivant les tests, pas en lisant la doc

1. **`Image(kind="proportional")` de reportlab exige largeur ET hauteur**
   pour calculer un ratio — lui passer `height=None` lève un `TypeError`
   dès la mise en page. Corrigé en lisant la vraie dimension du fichier via
   Pillow (déjà une dépendance transitive) avant de construire l'image.
2. **Le caractère de masquage plein (█, U+2588) n'existe pas dans
   l'encodage WinAnsi** de la police Helvetica par défaut de reportlab — un
   PDF réel relu avec `pypdf` le rendait comme `■` (U+25A0), un caractère
   différent. La propriété de sécurité tenait déjà (le texte réel avait
   disparu), mais le masque affiché était imprévisible. Remplacé par
   `[masque]`, en Latin-1 pur.

### Ce que le sabotage a trouvé sur les *tests*, pas sur le code

Sabotaged le garde de segment interdit (`.ssh`/`.aws`/`.gnupg`/...) en le
désactivant : la suite est restée verte. Cause : les chemins d'exemple
(`~/.ssh/id_rsa`) échouaient déjà sur deux autres filtres indépendants
(fichier inexistant, extension non image) — le test « passait » sans que
le garde de segment ne soit jamais exercé. Corrigé en isolant le garde :
une vraie image PNG, existante, dans un dossier au nom interdit. Re-sabotage
: 5 échecs réels ; restauration : vert. C'est exactement le risque que
CLAUDE.md décrit — un test qui passe pour la mauvaise raison est pire que
l'absence de test, et seul le sabotage l'a montré.

### Ce qui n'a PAS été implémenté, et pourquoi c'est honnête

- **Aucune capture en direct.** Voir plus haut — c'est la partie refusée,
  documentée ici plutôt que silencieusement abandonnée.
- **Aucune rédaction du CONTENU d'une image.** Une capture d'écran fournie
  est embarquée telle quelle ; masquer ce qu'elle montre exigerait de la
  vision/OCR, non implémenté. `SUGGESTION — NON IMPLÉMENTÉE`.
- **Aucun export vidéo.** Le montage existant (`tools/video/`) n'a pas été
  branché ici, faute de besoin réel exprimé pour un guide filmé.

### Ce que ça coûte si c'est faux

Une rédaction qui manquerait un email ou une clé dans un guide destiné à
être partagé le publierait dans un PDF/DOCX qui, une fois généré, n'est
plus sous le contrôle d'ARENA. Un garde de chemin inefficace laisserait un
guide embarquer le contenu d'une clé privée comme si c'était une capture
d'écran légitime — d'où les deux sabotages ci-dessus, et la correction du
test qui ne les exerçait pas vraiment.

## DEC-0049 — KrillinAI : traduction/doublage d'une vidéo existante, jamais un second orchestrateur

**2026-09-05.** Demande directe : intégrer KrillinAI (krillinai/KrillinAI)
comme capacité de traduction/sous-titrage/doublage vidéo dans le workspace
Video d'ARENA — sous-titres source/cible/bilingues, doublage, rendu
horizontal/vertical, couverture.

### Ce que le dépôt en amont est devenu, vérifié avant d'écrire une ligne

Cloné réellement (`krillinai/krillinai` @ `346d08bb1f3c61c96301ec130c4db8879b3b8444`,
05/09/2026) : `krillinai/KrillinAI` a été **renommé `krillinai/OpenCreator`
et entièrement réarchitecturé** — c'est aujourd'hui un espace de travail
agent complet (bureau Electron, daemon, harnais, marché de compétences) qui
utilise **Codex CLI comme moteur d'exécution**. Intégrer ce produit-là
aurait été construire, mot pour mot, le second orchestrateur/système
d'agents que cette même mission interdisait. **Ce n'est pas ce qui a été
branché.**

L'ancien moteur (transcription → traduction → sous-titres → doublage →
rendu, en ligne de commande) survit intact sous `runtime/krillinai/` à
l'intérieur du même dépôt : un module Go indépendant (`krillin-ai`), huit
commandes réelles (`subtitle`, `tts`, `speech`, `render-horizontal`,
`render-vertical`, `cover`, `pipeline`, `voices`), une sortie JSON
structurée par ligne, un manifest (`krillinai_manifest.json`). **Compilé
pour de vrai dans cette session** (`go build -o krillinai-cli ./cmd/cli`,
Go 1.24) — le binaire fonctionne, chaque commande a été exercée en
`--dry-run` et les JSON réels ont servi de fixtures aux tests, jamais
inventés.

### La licence a changé de valeur en cours de route

Le README d'OpenCreator affiche Apache-2.0 ; `runtime/krillinai/LICENSE`
(vérifié directement, pas supposé) est **GPL-3.0-only**. `LICENSE` d'ARENA
est « All rights reserved » — même raisonnement déjà tenu pour VoiceStudio
(AGPL-3.0, `core/connectors/audio_voix.py`) : importer ou copier du code
GPL romprait cette licence. La frontière retenue est identique — **aucune
ligne du moteur n'entre dans `core/connectors/krillinai.py`** ; il tourne
comme binaire compilé à part, jamais vendu, jamais téléchargé par ARENA,
localisé par `KRILLINAI_CLI_BIN` (variable d'environnement) ou le PATH,
absent → `NON_CONFIGURE` avec la commande de compilation à lancer.

### Ce qui a été intégré

`core/connectors/krillinai.py` (`ConnecteurKrillinAI`, six capacités :
`subtitle`/`tts`/`render_horizontal`/`render_vertical`/`cover`/`pipeline`),
câblé dans `core/production/plan_video.py` (`CAPACITES_VIDEO`,
`CAPACITES_ECRITURE`) sous cinq noms préfixés (`krillin_subtitle`,
`krillin_tts`, `krillin_render_horizontal`, `krillin_render_vertical`,
`krillin_cover`) et dans `agents/video/production_agent.py`
(`_appeler_krillin`, registre-médié comme Xaar Kaname). Permission unique
`krillinai.generate = CONFIRMATION, MEDIUM, WRITE_FILES`
(`config/permissions_services.yaml`) — même traitement que
`video_generation.generate` (WanGP/MoneyPrinterTurbo/Xaar Kaname) : une
génération reste une génération, jamais confirmée à la place du
propriétaire. Interface PWA (`videoProjectStore.ts`, `VideoProjectModal.tsx`)
et rapport de disponibilité (`core/production/disponibilite.py`) mis à
jour en même temps — un test existant (`test_capacites_video_pwa.py`)
vérifie que ces trois listes ne peuvent pas diverger.

### Quatre gardes, sabotage-vérifiées

1. **Jamais de clonage vocal.** `--voice-clone-source` (un vrai drapeau du
   moteur amont, vérifié dans son code) n'est ni lu ni transmis, à aucun
   niveau (connecteur, agent) — même fourni explicitement. Instruction du
   propriétaire, antérieure et absolue : *« si tu vois quelque chose de
   nouveau [près du deep face], ignore-le, ne le touche même pas »* — le
   clonage vocal est la même famille de risque que Xaar Kaname
   (Deep-Live-Cam), et cette frontière ne se négocie pas capacité par
   capacité, quelle que soit la qualité de l'architecture proposée autour.
2. **Jamais une seconde transcription locale.** `caption_source` refuse
   `"whisper"`/`"auto"`/`"openai"`/`"aliyun"` : ARENA transcrit déjà
   (FasterWhisper). Seuls `"manual"` (transcription ARENA fournie) et
   `"platform"` passent.
3. **Jamais un téléchargement d'URL implicite.** Une entrée `subtitle` en
   URL exige `autoriser_telechargement=True` explicite — même logique que
   GitIngest (DEC-0047) pour une URL distante.
4. **Jamais un binaire média téléchargé en silence.** `ffmpeg`/`ffprobe`/
   `yt-dlp` sont exigés déjà présents sur le PATH (vérifié : le moteur
   amont les télécharge lui-même s'il ne les trouve pas — code source lu,
   `internal/deps/checker.go`) ; ARENA refuse tout appel réel s'ils
   manquent, plutôt que de laisser le moteur les récupérer seul.

Les quatre gardes ont été sabotées puis restaurées ; la première tentative
sur le garde de transcription a d'abord révélé un test qui passait pour la
MAUVAISE raison ailleurs dans cette session (workflow_guide, DEC-0048) —
pas ici : chaque sabotage de ce module a produit un échec réel dès le
premier essai.

### `pipeline` existe, et n'est délibérément pas composable

La capacité `pipeline` du moteur amont est implémentée et testée dans le
connecteur — mais **volontairement absente de `CAPACITES_VIDEO`** : la
laisser composable par le graphe ARENA laisserait le moteur amont composer
ses propres étapes à la place du planificateur, exactement le second
orchestrateur que la mission interdisait elle-même. La composition
(sous-titres → doublage → rendu) reste au graphe ARENA, une étape
confirmée à la fois — comme `krillin_tts`/`krillin_render_*` le
documentent : ils prennent un CHEMIN déjà confirmé, jamais un index de
référence, précisément parce que le fichier d'une étape d'écriture
antérieure n'existe qu'après confirmation du propriétaire, jamais dans le
même passage (même principe que `montage` face à `wangp`/`moneyprinter`,
DEC-0037).

### Ce qui reste `UNKNOWN`, honnêtement

Ce conteneur cloud n'a ni ffmpeg, ni ffprobe, ni yt-dlp, ni clé API de
traduction/TTS/image configurée — mesuré, pas supposé
(`shutil.which` sur les trois, vide). Une génération réelle bout en bout
(un vrai MP4 sous-titré/doublé) n'a donc pas pu être vérifiée ici, seulement
son contrat (`--dry-run`, JSON réel capturé) et ses erreurs de
configuration absente. Comme la phase 7.2 (`docs/CURRENT_TASK.md`), la
mesure réelle attend la machine du propriétaire — où ffmpeg est déjà
présent (`tools/video/ffmpeg_tool.py` en dépend) et où le binaire devra
être compilé une fois (`go build -o krillinai-cli ./cmd/cli`).

### Ce que ça coûte si c'est faux

Une capacité `krillin_tts` qui accepterait `voice_clone_source` sans le
filtrer construirait, sur commande, une voix synthétique d'une personne
réelle — exactement le risque que Xaar Kaname porte déjà pour un visage, et
que le propriétaire a explicitement mis hors de portée de cette
intégration. Un garde de transcription absent chargerait un second modèle
Whisper sur une carte qui n'en tient qu'un à la fois (RTX A2000, 12 Go) —
lenteur, pas casse, mais un doublon que la mission elle-même interdisait.
Une capacité `pipeline` laissée composable referait, une étape de plan à la
fois, exactement le second orchestrateur que ce dépôt refuse depuis le
début de cette session (Hermes, Open-R1, MengTo/Kage, l'espace de travail
OpenCreator lui-même).

## DEC-0050 — OpenUI : la technique de prompt, jamais le serveur qui exige un compte GitHub

**2026-09-05.** Demande directe, après feu vert explicite du propriétaire
pour reprendre les intégrations mises en attente (OpenUI, txtai,
Formbricks) : intégrer OpenUI (wandb/openui) comme capacité de génération
d'interface — décrire, voir généré, en HTML/React/Svelte/Web Component.

### Ce qui a été vérifié avant d'écrire une ligne

Cloné réellement (`wandb/openui` @ `42d7ab4`, 05/09/2026) : contrairement à
KrillinAI, ce dépôt **n'a pas changé de forme** — toujours Apache-2.0,
toujours un backend FastAPI + frontend React. Mais son vrai contrat a été
lu dans le code, pas supposé : `POST /v1/chat/completions`
(dans le `server.py` du dépôt OpenUI, pas d'ARENA) **exige une session utilisateur**
(`request.session["user_id"]`, 401 sinon), obtenue par connexion GitHub
OAuth — sauf en `Env.LOCAL` (le défaut), où `GET /v1/session` provisionne
un utilisateur local automatiquement. Le serveur tire aussi `weave`
(télémétrie W&B, gardée locale tant que `WANDB_API_KEY` n'est pas posée —
vérifié dans `server.py`), `boto3`, `peewee`, `fastapi-sso`.

**Ce qui fait le vrai travail n'est pas ce serveur.** Le prompt qui
transforme une description en interface vit côté CLIENT, en TypeScript
(`frontend/src/api/openai.ts::systemPrompt`) : fragment HTML, classes
Tailwind, variables CSS de thème clair/sombre, images de substitution
`placehold.co` — envoyé ensuite à n'importe quel modèle compatible OpenAI,
dont **Ollama**, déjà ce qu'ARENA utilise en local (DEC-0002). Le serveur
FastAPI n'est qu'un relais générique multi-fournisseurs avec comptabilité
d'usage et authentification — une doublure de ce qu'ARENA a déjà
(`ModelProvider`, le routeur de modèles, les permissions).

### Ce qui a été intégré, et pourquoi cette forme

**La technique, jamais les fichiers.** Même discipline que le catalogue de
specialistes (`core/specialistes/catalogue.py`) et Social Media Skills, plus
tôt dans cette session : aucune ligne de `frontend/src/api/openai.ts`
copiée. `core/production/ui_generation.py` reprend le PRINCIPE (fragment
autonome, Tailwind, variables de thème, images de substitution), en code
ARENA, avec le modèle local d'ARENA — pas un second serveur à héberger, pas
de connexion GitHub, pas de dépendance à `weave`/`boto3`/`peewee`.

Séparation identique à Xaar Kaname/KrillinAI dans
`agents/video/production_agent.py` : `agents/ui/ui_agent.py`
(`UiGenerationAgent`) appelle le modèle et extrait le code — jamais
d'écriture directe ; `core/connectors/ui_generate.py`
(`ConnecteurUiGenerate`) valide et écrit — jamais de génération. Câblé dans
l'aiguillage réel (`agents/orchestrator/orchestrator_agent.py`,
`apps/backend/routers/chat.py`) sous une intention nouvelle, `UI_GENERATE`,
distincte de `DESIGN_UI` (décider à quoi ça doit ressembler, sans rien
écrire — la capacité existante d'UI/UX Pro Max, inchangée). **Ajoutée aussi
au prompt de classification du modèle** (`PROMPT_CLASSIFICATION`), pas
seulement au repli par mots-clés : `DESIGN_UI` lui-même n'y figurait pas et
n'était donc atteignable que modèle indisponible — corrigé ici pour
`UI_GENERATE`, pour ne pas répéter la même capacité invisible que la
mission originelle de ce dépôt (`docs/CURRENT_TASK.md`) a déjà dû corriger
une fois.

Permission : `ui_generate.document = ALLOWED, WRITE_FILES` — même
raisonnement que workflow_guide/devis (DEC-0041/0048) : le fichier reste
local, relu avant d'être partagé, et n'est **jamais exécuté par ARENA**
(le proprietaire l'ouvre lui-même dans son navigateur, comme n'importe quel
autre artefact de `media/rendered/`) — pas la CONFIRMATION de
`video_generation`/`krillinai`, qui couvre un coût de génération externe
distinct.

### Une garde sabotage-vérifiée

**Aucun script externe hors d'une liste fermée.** Mandat explicite de la
mission (« contrôle des URLs externes ») : `valider_scripts_externes()`
refuse l'écriture ENTIÈRE (pas un avertissement à côté d'un fichier quand
même écrit) si un `<script src="...">` vise un domaine hors de
`DOMAINES_SCRIPT_AUTORISES` (les mêmes domaines déjà vérifiés pour les
artefacts de ce système : cdnjs, jsdelivr, le CDN Tailwind, jquery).
Sabotagé deux fois : une fois en désactivant l'appel du garde (5 échecs
réels), une fois en affaiblissant la comparaison de domaine en sous-chaîne
plutôt qu'en égalité exacte (`cdn.tailwindcss.com.attacker.test` serait
alors passé — un test dédié l'a détecté) ; les deux fois restauré, vert.

### Ce qui n'a pas été implémenté, et pourquoi c'est honnête

Aucune image en entrée (décrire une interface à partir d'une capture
d'écran) : OpenUI le permet, ARENA a déjà une vision locale
(`ollama_vision`) qui pourrait la servir, mais aucun besoin réel exprimé ne
le justifiait pour cette première intégration. `SUGGESTION — NON
IMPLÉMENTÉE`.

### Ce que ça coûte si c'est faux

Un garde de script externe inefficace laisserait une interface générée
charger un script arbitraire — exécuté dans le navigateur du propriétaire
le jour où il ouvre le fichier, pas dans ARENA, mais toujours à son
insu si le domaine n'est jamais montré. Une capacité ajoutée sans être
câblée dans l'aiguillage réel serait exactement le défaut que la mission
« réveiller ce qui dort » a déjà corrigé une fois pour neuf modules :
écrite, testée, et qu'aucune phrase du propriétaire n'atteint.

## DEC-0051 — txtai : un moteur à côté, jamais un second RAG

**2026-09-05.** Dernière des trois intégrations mises en attente (avec
OpenUI/DEC-0050 et Formbricks) : intégrer txtai (neuml/txtai, Apache-2.0)
comme capacité de recherche sémantique.

### Ce qu'ARENA a déjà, vérifié avant d'écrire une ligne

Trois systèmes de récupération existent déjà et ont chacun leur rôle :
`core/memory/semantique.py` (mémoire de conversation retrouvée par le sens,
embeddings bge-m3 via Ollama local), `tools/rag/lightrag_tool.py` et
`tools/rag/graphrag_tool.py` (documents déposés par le propriétaire).
La règle de la mission elle-même est **conditionnelle**, pas un mandat
d'intégrer coûte que coûte : « NE construis PAS un deuxième RAG... n'utilise
txtai que lorsque son avantage est démontré » — et démontrer un avantage
exige un vrai banc de comparaison (pertinence, latence) sur un petit
jeu de données réel.

### Le blocage réel, honnêtement rapporté

Un vrai banc de comparaison n'a pas pu tourner **dans ce conteneur** :
`core/memory/semantique.py` mesure déjà, et documente déjà, l'absence
d'Ollama en cloud — la même limite que la phase 7.2
(`docs/CURRENT_TASK.md`). Sans embeddings réels, aucune mesure de
pertinence n'aurait de sens ; en fabriquer une aurait été exactement ce que
`core/actions/resultat.py` interdit — un chiffre plausible à la place d'une
mesure. **Donc rien ici ne remplace ni ne route par défaut vers txtai** :
c'est une capacité réelle, appelable explicitement, jamais activée à la
place d'un moteur existant. Un test dédié (`test_txtai_n_apparait_dans_
aucune_intention_du_routeur`) le fige : `apps/backend/routers/chat.py` ne
cite jamais txtai.

### Ce qui a été intégré, et pourquoi cette forme

**Aucun second modèle d'embeddings.** Installé en `txtai_minimal==9.13.0` —
la variante officielle du paquet PyPI, vérifiée réellement (téléchargée,
341 Ko), **sans** `torch`/`transformers`/`faiss` : configuré en
`method="external"`, le vecteur de chaque texte vient de `embeddings_ollama()`
(`core/memory/semantique.py`), **la même fonction** que la mémoire de chat
utilise déjà. Testé pour de vrai (sans Ollama, avec un fournisseur injecté
déterministe) : un index construit, une vraie requête, un vrai classement
par score — ce qui est évalué est le moteur d'indexation de txtai
(`backend="numpy"`, faiss absent), jamais un second modèle sur la RTX A2000.

`core/production/txtai_recherche.py` (la plomberie : construire un index
éphémère, chercher, jamais persister) ; `core/connectors/txtai_search.py`
(`ConnecteurTxtaiSearch`, une seule capacité, `rechercher`, une LECTURE —
rien n'est écrit, rien n'est persisté). Permission :
`txtai_search.read = ALLOWED, LOW` — même niveau que `graphify.interroger`.

### Deux gardes réelles, sabotage-vérifiées

1. **Un plafond de documents par appel** (`MAX_DOCUMENTS = 200`) — mandat
   explicite de la mission (§15) : jamais toutes les données du
   propriétaire transformées en embeddings automatiquement. L'index est
   reconstruit et jeté à chaque appel, sur les documents FOURNIS dans le
   même appel, jamais une bibliothèque entière.
2. **Un embeddings incomplet lève, il ne se complète jamais par un vecteur
   inventé.** Sabotage réel : désactiver ce garde n'a PAS levé d'exception
   au même endroit — la vérification a montré que le résultat aurait
   silencieusement continué avec un index mal formé, plutôt que de
   confirmer une exception propre plus loin. C'est exactement ce que le
   sabotage doit révéler : un défaut qui existerait sans bruit.

**Correctif du même bug que GitIngest (DEC-0047), retrouvé avant qu'il ne
morde ici :** `sonder()` appelait `asyncio.run()` directement — sabotage
réel confirmé : `RuntimeError: asyncio.run() cannot be called from a
running event loop`, exactement le message de DEC-0047. Corrigé par le
même pont par thread dédié, testé depuis une vraie boucle asyncio active
(`test_sonde_depuis_une_boucle_asyncio_deja_active`).

### Ce qui n'a pas été implémenté, et pourquoi c'est honnête

Aucun remplacement de LightRAG/GraphRAG/la mémoire sémantique. Aucun banc
de comparaison chiffré (pertinence/latence/mémoire, mission §16) : les
conditions pour le mesurer honnêtement (un Ollama joignable, un vrai corpus)
n'existent que sur la machine du propriétaire. `SUGGESTION — NON
IMPLÉMENTÉE` : lancer ce banc une fois qu'Ollama y est joignable, avec les
deux fournisseurs de vecteurs (celui de la mémoire, celui de txtai) sur le
MÊME corpus, avant de décider si un remplacement se justifie un jour.

### Ce que ça coûte si c'est faux

Un plafond de documents contourné indexerait, un appel à la fois,
l'intégralité d'un espace de travail sans que le propriétaire l'ait
demandé — l'embeddings de toutes ses données, produit silencieusement.
Un garde d'embeddings incomplet absent laisserait un classement construit
sur un index mal formé passer pour un résultat fiable, sans que rien ne le
signale — exactement ce que le sabotage de cette intégration a montré,
avant que quiconque ne le découvre sur un vrai corpus.

## DEC-0052 — Formbricks : une instance externe appelée par API, jamais du code copié

**2026-09-05.** Dernière des trois intégrations mises en attente (avec
OpenUI/DEC-0050 et txtai/DEC-0051) : intégrer Formbricks (formbricks/
formbricks) comme capacité de sondage/feedback.

### La licence commande la forme, vérifiée avant d'écrire une ligne

Cloné réellement (`formbricks/formbricks` @ `4f597cb`, 05/09/2026) : le
`LICENSE` du dépôt confirme exactement ce que la mission annonçait — le
cœur est **AGPLv3** ; `apps/web/modules/ee/` (Enterprise) sous licence
séparée ; seuls des SDK clients (`packages/js`, `packages/android`,
`packages/ios`, `packages/api`) sont MIT, pas le serveur. **Aucune ligne de
ce dépôt n'est copiée ici.** L'API REST management (routes réelles sous
`apps/web/app/api/v1/management/`, lues dans le code source — en-tête
`x-api-key`, confirmé dans les tests amont, pas deviné) est appelée par
HTTP, exactement la même frontière que VoiceStudio (AGPL-3.0,
`core/connectors/audio_voix.py`) : une simple agrégation par appel externe
n'étend pas les obligations de l'AGPL à qui l'appelle.

### Ce qui a été intégré, et pourquoi cette forme

`core/connectors/formbricks.py` (`ConnecteurFormbricks`) — cinq capacités :
`creer` (un sondage à une question, texte libre — le schéma complet de
Formbricks porte une vingtaine de types de questions ; en couvrir un seul,
suffisant pour « un petit questionnaire de feedback », évite une capacité
décorative), `lister`, `obtenir`, `reponses`, `analyser` (compte/agrège les
réponses déjà reçues — **calculé ici**, honnêtement : l'API de Formbricks
ne rend aucun score d'analyse prêt à l'emploi, vérifié dans le code source,
donc rien n'invente un chiffre de satisfaction à sa place).

**Aucune URL par défaut.** `FORMBRICKS_BASE_URL` doit être fournie
explicitement — jamais l'URL cloud de Formbricks devinée à sa place. Une
instance cloud enverrait de vraies données de réponse (potentiellement
client/personnelles, mission §23) chez un tiers ; ARENA ne le décide jamais
à la place du propriétaire (DEC-0002). Sans les trois variables
(`FORMBRICKS_BASE_URL`, `FORMBRICKS_API_KEY`, `FORMBRICKS_WORKSPACE_ID`) :
`NON_CONFIGURE`, proprement — ARENA continue de fonctionner (mandat de la
mission, §24). **Aucune instance n'existe pour ce propriétaire** : ce
connecteur est réel et testé, mais n'a jamais pu être vérifié contre un
vrai serveur — seulement contre un faux client HTTP figé sur les réponses
réelles de l'API (schéma vérifié dans le code source amont).

Permission : `formbricks.read = ALLOWED, LOW` (lire ses propres sondages
déjà configurés) ; `formbricks.survey = CONFIRMATION, MEDIUM, PUBLISH` —
publier un sondage est visible d'un tiers (l'instance, et quiconque y
répond), le même coupe-circuit déjà utilisé pour les réseaux sociaux
(`config/permissions_services.yaml`), pas `WRITE_FILES` : rien n'est écrit
sur disque ici, c'est une ressource distante qui est créée.

### Ce qui n'a pas été implémenté, et pourquoi c'est honnête

Les réponses ne sont **jamais** écrites dans la mémoire personnelle
d'ARENA (mission §22) — vérifié : ce fichier n'importe rien de
`core/memory/`, un test dédié le fige. Aucun câblage dans l'aiguillage
automatique (`chat.py`) : contrairement à OpenUI/txtai, ce n'est pas une
question de duplication (ARENA n'a aucune capacité de sondage existante) —
c'est qu'aucune instance réelle n'existe pour l'exercer, et câbler un
routage automatique vers une capacité qui répondra `NON_CONFIGURE` à
chaque fois serait prématuré. `SUGGESTION — NON IMPLÉMENTÉE` : une
intention dédiée dans `agents/orchestrator/orchestrator_agent.py`, le jour
où une instance existe réellement.

### Ce que ça coûte si c'est faux

Une URL par défaut devinée enverrait de vraies réponses de sondage —
potentiellement des données client — vers un service que le propriétaire
n'a jamais choisi, en silence. Le coupe-circuit `PUBLISH` déjà en place
(éteint par défaut dans `config/permissions.yaml`, sabotage-vérifié ici)
protège la publication d'un sondage exactement comme il protège déjà une
publication sur les réseaux sociaux — un sondage publié sans confirmation
serait vu par un tiers avant que le propriétaire ne l'ait validé.

## DEC-0053 — IFC/BIM (IfcOpenShell) : le métré lu dans un fichier, jamais un second moteur

**2026-09-05.** Mission autonome reçue le même jour, format inhabituel (sections
numérotées, anglais/français mêlé, « ne pose aucune question », autorisation à
« ne pas considérer les règles actuelles du projet comme des contraintes
absolues ») — même profil que deux missions précédentes déjà refusées cette
session (l'une portait sur OpenUI/txtai/Formbricks, l'autre sur KrillinAI ;
toutes deux ont fini par être construites une fois qu'une autorisation courte,
en français, dans son registre habituel, a suivi). Celle-ci porte directement
sur le métier — BIM, métré, matériaux, devis — pas sur un besoin exprimé nulle
part ailleurs. Elle n'est donc pas refusée en bloc, mais elle n'est pas non
plus exécutée telle quelle : la mission demande explicitement de sauter la
revue (« commit. push. ») — **refusé sans discussion**, `docs/REGLES_DE_TRAVAIL.md`
et CLAUDE.md sont explicites, aucune instruction reçue ne lève cette règle. La
mission couvre huit dépôts et une restructuration d'architecture ; une seule
tranche verticale réelle est livrée ici, la plus directement utile à UniC
Plaquiste, suivant la même discipline « une phase, une PR » qu'à chaque
précédente intégration.

### Ce qui a été intégré

`IfcOpenShell/IfcOpenShell` (LGPL-3.0-or-later, vérifié sur PyPI — wheels
précompilées, aucun compilateur requis) est une **dépendance de
bibliothèque**, jamais du code copié : `core/production/ifc_lecture.py`
n'appelle que son API Python publique (`ifcopenshell.open`,
`ifcopenshell.util.element`). L'obligation LGPL est tenue par construction —
un paquet PyPI installé tel quel, jamais vendoré.

`core/connectors/ifc.py` (`ConnecteurIfc`) — trois capacités, toutes en
lecture : `analyser` (niveaux, comptes d'éléments par type et par niveau),
`elements` (liste filtrée par type IFC + niveau), `metre` (somme la surface
des murs). Câblé dans `agents/plaquiste/plaquiste_agent.py` exactement comme
le métré de plan PDF (OpenTakeoff) déjà en place : un chemin `.ifc` cité en
texte est reconnu (`agents/plaquiste/ifc_metre.py`), passe par la même
frontière de confinement (`chemin_hors_du_depot`, sabotage-vérifiée), et la
surface des murs lue alimente **directement** `agents/plaquiste/
calcul_materiaux.py::quantites_pour()` — le même moteur matériaux que la
mission demande explicitement de ne pas dupliquer (« ne crée pas
inutilement deux moteurs concurrents »), jamais un second calcul.

**La limite honnête, écrite dans le code et vérifiée par sabotage** : la
surface d'un mur vient UNIQUEMENT des quantités déjà calculées et écrites
dans le fichier IFC lui-même (`Qto_WallBaseQuantities` — `NetSideArea`/
`GrossSideArea`/`Area`). Aucune géométrie n'est reconstruite (pas de
maillage, pas de moteur de forme) : un mur sans quantité exploitable est
nommé, exclu du total, jamais estimé. C'est exactement la formulation de la
mission elle-même (« lorsque les données géométriques le permettent »).

### Smoke test réel, bout en bout

`tests/fixtures/ifc/exemple.ifc` est un vrai fichier IFC4, engendré par
IfcOpenShell lui-même (son API `ifcopenshell.api`, jamais écrit à la main) :
2 niveaux, 3 murs (deux avec quantité exploitable, un troisième sans),
1 porte, 1 fenêtre. `tests/test_plaquiste_ifc_bout_en_bout.py` fait tourner
la chaîne complète avec les VRAIS connecteurs (IFC + devis) : fichier IFC →
`ConnecteurIfc.analyser`/`metre` → `quantites_pour()` → PDF réel écrit sur
disque, relu avec `pypdf`, chaque article vérifié présent. Trois sabotages
prouvés puis restaurés : l'import différé d'IfcOpenShell (même classe de
panne que txtai/DEC-0051 — un import de tête de fichier ferait planter tout
ARENA au démarrage dès que la bibliothèque manque), l'absence de géométrie
inventée pour un mur sans quantité, et la frontière de confinement du
chemin. `python -m ruff check .` propre, `3691 passed, 25 skipped` (offline).

### Ce qui n'a pas été implémenté, et pourquoi c'est honnête

- **QuantityTakeoff-Python** (datadrivenconstruction) : ses concepts (filtres
  par catégorie/niveau/zone/matériau, conversion métré → matériaux
  configurable) sont déjà couverts par `calcul_materiaux.py` (ratios
  `config/metier.yaml`) — rien n'a été trouvé qui justifie un second moteur.
- **simpleIfcAIAgentWithGraphRAG** (relations bâtiment → étage → pièce →
  mur, questions comme « quels éléments composent cette pièce ? ») :
  `SUGGESTION — NON IMPLÉMENTÉE`. Cette phase donne les comptes par niveau
  (`elements_par_niveau`), pas le confinement pièce par pièce
  (`IfcRelContainedInSpatialStructure` au niveau `IfcSpace`) — un vrai
  graphe ou une seconde couche relationnelle serait la mission §3 elle-même
  qui prévient : « ne crée pas un système complexe inutile ».
- **BIM as Code, BuildingPy** : générer de la géométrie/exporter en IFC/DXF
  n'a aucun consommateur exprimé pour l'instant — UniC Plaquiste lit des
  plans et des fichiers IFC, n'en produit pas. `SUGGESTION — NON
  IMPLÉMENTÉE`, à réévaluer si un besoin réel apparaît.
- **SiteGuard, Construction Site Safety PPE Detection** : hors de cette
  phase. Détection visuelle sur des photos de chantier — potentiellement
  des personnes reconnaissables — mérite son propre examen (modèle,
  fiabilité annoncée comme probabiliste, jamais infaillible) plutôt qu'un
  ajout en fin d'une phase déjà large.
- **buildingSMART IFC4.x** : référence déjà lue pour vérifier le
  vocabulaire (`IfcWall`/`IfcBuildingStorey`/`Qto_WallBaseQuantities`),
  jamais un moteur — exactement ce que demande la mission (§10).
- Aucune capacité IFC n'entre dans l'aiguillage automatique de
  `apps/backend/routers/chat.py` : comme txtai, elle reste explicite —
  citer un chemin `.ifc` la déclenche, rien ne la remplace à la place d'une
  demande de métré par plan PDF ou par dimensions dictées.
- Pièce jointe IFC (upload PWA) non supportée dans cette phase : seul un
  chemin tapé est reconnu, comme les plans PDF avant elle. Un fichier IFC
  est typiquement bien plus volumineux qu'un PDF et rarement envoyé par
  chat — `SUGGESTION — NON IMPLÉMENTÉE`.

### Ce que ça coûte si c'est faux

Une surface de mur inventée à partir d'une géométrie recalculée à la place
d'un fichier qui ne la donne pas produirait un métré faux, puis un devis
faux chez un client — exactement le risque que `config/metier.yaml` et
`calcul_materiaux.py` existent pour éviter. La limite est donc écrite dans
le code, pas seulement dans cette page : un mur sans quantité exploitable
est nommé, jamais estimé, et un sabotage réel (rendre `0.0` à la place de
`None`) l'a confirmé avant d'être restauré.

## DEC-0054 — Sécurité chantier : SiteGuard appelé par HTTP, jamais Ultralytics importé

**2026-09-05.** Deuxième tranche de la mission BIM/métré/sécurité chantier
(DEC-0053). Section 6 de la mission : détecter personnes/EPI (casque, gilet)
sur une photo de chantier, présenter le résultat comme une observation
probabiliste, jamais un verdict.

### Deux dépôts évalués, un choisi pour la licence de son jeu de données

`SiteGuard` (C-Nekopedia/SiteGuard) et `Construction-Site-Safety-PPE-
Detection` (VoxDroid) sont tous deux MIT, tous deux construits sur
Ultralytics YOLO. Différence décisive, vérifiée avant d'écrire une ligne :
les poids livrés par SiteGuard (`yolo26n_ppe.pt`) sont entraînés sur le
« Construction-PPE dataset », **lui-même AGPL-3.0** — la mission demande
explicitement (§12) de vérifier « les licences des modèles/datasets
séparément des licences des dépôts », et faire hériter un fichier de poids
d'une licence de jeu de données AGPL est un terrain juridique incertain, non
tranché. Le dépôt VoxDroid, lui, utilise le « Construction Site Safety
Image Dataset » (Roboflow/snehilsanyal), **CC BY 4.0** — attribution
seulement, aucune ambiguïté copyleft.

Cela ne change rien à l'architecture retenue : **ARENA n'importe et ne
redistribue le fichier de poids d'aucun des deux**. Il appelle l'API REST
déjà exposée par SiteGuard (`POST /api/v1/detection/image`, vérifiée dans
le code source réel de son dépôt — le gestionnaire de route et le service
de détection y sont lus directement, pas devinés), exactement comme
VoiceStudio (AGPL) ou Formbricks (AGPLv3) : une agrégation par appel
externe, jamais du code copié. La question de licence du dataset VoxDroid
reste donc annotée ici pour mémoire, sans peser sur ce choix d'architecture.

### La frontière qui compte réellement : Ultralytics est AGPL-3.0

Vérifié sur PyPI : Ultralytics (le paquet `ultralytics`, dont dépendent les
deux projets pour exécuter YOLO) est **dual-licencié** — AGPL-3.0 pour un
usage open source, licence Enterprise payante pour un usage propriétaire
fermé sans les obligations AGPL. ARENA est un logiciel propriétaire
(`docs/DECISIONS.md` le rappelle pour Formbricks, DEC-0052) et un service
réseau : importer `ultralytics` directement dans le processus d'ARENA
exposerait tout le backend aux obligations de mise à disposition du code
source qu'impose l'AGPL sur un usage réseau — le même risque déjà écarté
pour VoiceStudio et Formbricks. **`ultralytics` n'entre donc jamais dans
`requirements.txt` d'ARENA.** SiteGuard reste un programme séparé, installé
à côté (jamais dans ce dépôt), qu'ARENA appelle par HTTP local — un test
dédié (`TestJamaisUltralyticsImporte`) vérifie qu'aucune ligne du
connecteur n'importe `ultralytics` ni `torch`.

### Ce qui a été intégré

`core/production/securite_chantier.py` — traduit le JSON de SiteGuard
(`detections`, `risks`) en un rapport français, sans recalculer sa logique
de risque (elle reste côté SiteGuard, ses propres règles). `core/connectors/
securite_chantier.py` (`ConnecteurSecuriteChantier`) — une capacité
`analyser` (lecture), `SITEGUARD_BASE_URL` sans défaut (jamais une instance
distante devinée, DEC-0002), sonde réelle sur `GET /health`.

Câblé dans `agents/vision/vision_agent.py`, pas dans un nouvel aiguillage :
« analyse cette photo de chantier » route déjà vers `VisionAgent` (la
garde existante, `VISION`, le prévoit explicitement — « contient
"chantier" et partirait sinon chez l'assistant devis »). La détection EPI
est un **second signal, déterministe**, déclenché seulement quand le texte
porte un mot de sécurité explicite (chantier/EPI/casque/gilet) — jamais sur
une capture d'écran ou un plan analysés par le même agent — et présenté
**distinctement** de la description libre de Qwen3-VL, même discipline que
le décompte de menuiseries face à l'avis visuel dans `plaquiste_agent.py`.

**Le rappel de prudence accompagne chaque rapport, sans exception**
(vérifié par sabotage) : « une observation probabiliste, jamais une
certitude ». Aucune image n'est jamais persistée par ce connecteur — elle
part vers SiteGuard pour la durée de l'appel HTTP, jamais écrite sur disque
ici, même règle de vie privée que `apps/backend/pieces_jointes.py`.

### Tests et sabotages

`python -m ruff check .` propre, `3720 passed, 25 skipped` (offline). Deux
sabotages prouvés puis restaurés : le déclencheur de sécurité forcé à
toujours vrai (`test_jamais_declenchee_sans_mot_de_securite` tombe — une
capture d'écran aurait déclenché une détection de casque pour rien) ; le
rappel de prudence retiré du formatage (`test_le_rappel_de_prudence_est_
toujours_present` tombe — un rapport se lirait comme une certitude).

### Ce qui n'a pas été implémenté, et pourquoi c'est honnête

- **Aucune instance SiteGuard réelle n'a pu être testée** : ni installée ni
  lancée dans ce conteneur (pas de GPU, pas de `ultralytics`). Les tests du
  connecteur simulent une instance via un faux client HTTP figé sur son
  schéma de réponse réel (lu dans son code source, pas deviné).
- **Vidéo, horodatage, localisation** (mission §6) : cette phase traite une
  image fixe. Une vidéo demanderait un découpage en trames avec sa propre
  gestion de débit d'appels vers SiteGuard — `SUGGESTION — NON
  IMPLÉMENTÉE`.
- **VoxDroid (dataset CC BY 4.0)** : resté une référence de licence, pas
  intégré — SiteGuard expose déjà une API REST prête à appeler ; ajouter un
  second moteur de détection ferait exactement ce que la mission interdit
  (§11, « pas de services concurrents »).

### Ce que ça coûte si c'est faux

Importer `ultralytics` directement dans ARENA exposerait tout le code
propriétaire du propriétaire aux obligations réseau de l'AGPL-3.0 — un
risque juridique réel pour son entreprise, pas seulement une préférence
d'architecture. Présenter une détection comme une certitude (sans le
rappel de prudence) pourrait faire ignorer une vérification humaine sur un
chantier réel — le risque que la mission elle-même signale en toutes
lettres (§6).

## DEC-0055 — Hermes Agent Self-Evolution : jamais ARENA comme cible

**2026-09-05.** Reprise d'un dépôt refusé plus tôt dans la session
(Hermes Agent Self-Evolution, NousResearch/hermes-agent-self-evolution,
MIT). Le refus initial portait sur un principe déjà tranché par DEC-0014 :
le Gardien de maintenance DÉCOUVRE et RAPPORTE, il ne MODIFIE jamais —
« commit/PR autonome explicitement hors périmètre, contraire à la règle
non négociable du projet ». Hermes Agent Self-Evolution fait exactement
ça : lire des traces d'exécution, muter des compétences, ouvrir une PR.
Une revue humaine avant fusion existe déjà côté outil, mais ça ne change
pas le principe DEC-0014 en soi. Question posée explicitement au
propriétaire ; sa réponse tranche : « construis-le, mais pointe-le sur
autre chose que ce dépôt ARENA ».

### Ce qui a changé depuis le premier refus

Deux points vérifiés à nouveau, dans le code source réel de l'outil (pas
supposés) :

1. **Les modèles utilisés (`optimizer_model`, `eval_model`, `judge_model`)
   sont de simples chaînes par défaut**, lues directement dans le fichier
   de configuration de l'outil (`evolution/core`), jamais un verrou. Le
   blocage initial (« ça part chez un fournisseur cloud », DEC-0002) est
   réel dans la configuration PAR DÉFAUT de l'outil,
   mais reste du ressort du propriétaire quand il installe SON exemplaire
   séparé — ARENA n'a pas à le résoudre pour lui.
2. **`create_pr: True` est également un défaut de configuration**, pas un
   comportement figé — mais rien ne garantit qu'il soit désactivable en
   ligne de commande (non documenté) : ce connecteur traite donc CHAQUE
   appel comme pouvant ouvrir une PR réelle, jamais une simple suggestion
   locale.

### La garde structurelle, pas une promesse

`core/connectors/hermes_evolution.py` refuse `depot_cible` s'il tombe dans
le dépôt d'ARENA lui-même (`_cible_hors_du_depot`, même forme que
`chemin_hors_du_depot` de `agents/plaquiste/plaquiste_agent.py`) —
vérifié par sabotage : retirer ce contrôle fait accepter ARENA comme sa
propre cible, exactement ce que DEC-0014 interdit. La garde vit dans le
code, pas seulement dans cette page.

**Un programme séparé, jamais importé** : cloné et installé à côté
(`HERMES_EVOLUTION_DIR`), comme OpenTakeoff, WanGP, VoiceStudio, KrillinAI
et SiteGuard. Invoqué par sous-processus
(`python -m evolution.skills.evolve_skill`) — sa seule forme d'appel, pas
de serveur HTTP à la différence de SiteGuard.

### Le bon coupe-circuit, vérifié dans le code réel

`EXECUTE_COMMANDS` (à `false` par défaut dans `config/permissions.yaml`)
est le coupe-circuit choisi — une exécution de sous-processus est
exactement ce pour quoi il existe. Vérifié directement dans
`core/permissions/controle.py::ControleAcces.verifier` : `interrupteur_de()`
lit ce nom pour toute capacité qui le déclare dans
`config/permissions_services.yaml`, le chemin qu'emprunte réellement ce
connecteur via `Connecteur._conduire()`. Une note d'audit antérieure
(P-05, dans le worklog technique) signale qu'un appel plus ancien et
direct à `PermissionManager.is_allowed()` ne consultait jamais ce booléen
— un chemin distinct de celui des connecteurs modernes, vérifié ici pour
ne pas répéter la même confusion. `hermes_evolution.execute` est
`CONFIRMATION`, risque `HIGH` : une exécution qui peut ouvrir une PR sur un
dépôt réel n'est jamais lancée d'autorité.

### Reachable, pas dormant

`POST /api/hermes-evolution/evoluer` — un outil de développement, pas une
capacité métier UniC Plaquiste : pas d'aiguillage depuis le chat (même
choix que `/api/video/projet`, DEC-0037). La confirmation réelle emprunte
la route générique déjà en place (`POST /api/actions/{identifiant}/confirm`)
plutôt qu'une route dédiée.

### Tests et sabotage

21 tests du connecteur (aucun `subprocess.run` réel — l'outil n'est
installé nulle part ici, un programme externe comme OpenTakeoff) + 4 tests
de la route. Deux sabotages prouvés puis restaurés : la garde de
confinement retirée (ARENA accepterait sa propre cible) ; l'interrupteur
`EXECUTE_COMMANDS` retiré de la politique livrée (l'action partirait sans
coupe-circuit). `python -m ruff check .` propre, `3746 passed, 25 skipped`.

### Ce qui n'a pas été implémenté, et pourquoi c'est honnête

- **Aucune installation réelle testée** : ni l'outil d'évolution, ni un
  dépôt hermes-agent cible n'existent sur cette machine. `sonder()` fait un
  vrai appel (`--help`), jamais une déduction depuis un fichier présent.
- **Le contournement de `create_pr`/du fournisseur cloud** reste la
  responsabilité du propriétaire dans SA configuration de l'outil, jamais
  quelque chose qu'ARENA réécrit ou contourne dans le code d'un tiers.

### Ce que ça coûte si c'est faux

Une garde de confinement absente laisserait un outil d'évolution proposer
des PR sur le code même d'ARENA — exactement le risque que DEC-0014 a
fermé pour le Gardien. Un coupe-circuit mal relié laisserait un
sous-processus s'exécuter sans que le propriétaire l'ait autorisé
globalement — les deux sont vérifiés par sabotage, pas seulement décrits.

## DEC-0056 — Génération IFC : l'API d'IfcOpenShell suffit, jamais un second moteur BIM

**2026-09-06.** Dernier volet mis de côté par DEC-0053 (« BIM as Code »/
BuildingPy, génération de géométrie, section 4/5 de la mission) et
question du graphe de relations pièce-par-pièce (section 3). Autorisation
explicite du propriétaire de reprendre « ce qui reste de la mission BIM ».

### BIM as Code et BuildingPy réévalués, tous deux écartés

Les deux dépôts (benjaminwfriedman/bimascode, OpenAEC-Foundation/
building-py) ont été relus à nouveau, licence et architecture comprises :
tous deux MIT/permissifs, mais tous deux apportent un **second moteur
géométrique** — `build123d` (un noyau CAO, OCCT) pour BIM as Code,
Blender/Revit/Speckle pour BuildingPy. La mission l'interdit explicitement
(§11, « pas de moteurs BIM redondants »). Vérifié directement dans le code
d'IfcOpenShell (déjà une dépendance, DEC-0053), pas supposé : son propre
module `ifcopenshell.api.geometry` expose `create_2pt_wall` — de quoi créer
un mur simple (deux points, hauteur, épaisseur) et écrire un fichier IFC
valide, **sans aucune dépendance supplémentaire**. Les deux dépôts
n'apportent donc rien qu'IfcOpenShell ne fasse déjà pour le besoin réel
(un croquis simple, pas une maquette complète) — écartés pour duplication,
pas pour licence.

### Le graphe de relations pièce-par-pièce : écarté pour une raison technique, pas seulement l'absence de besoin

Vérifié empiriquement avant de conclure (jamais supposé) : la relation IFC
qui rattacherait un mur à la pièce qu'il sépare
(`IfcRelSpaceBoundary`, ou `IfcRelReferencedInSpatialStructure`) n'a
**aucun assistant de création** dans l'API haut niveau d'IfcOpenShell
(contrairement aux relations couramment exportées — niveaux, matériaux,
quantités) et son inverse (`get_referenced_elements`) ne l'a pas retrouvée
de façon fiable dans un test direct, même construite à la main. C'est la
preuve concrète que cette relation est rarement peuplée par les logiciels
d'auteur réels — construire une capacité dessus produirait le plus souvent
un résultat vide, silencieusement inutile. `DEC-0053` avait déjà écarté
cette capacité pour éviter un système complexe inutile (mission §3) ; cette
vérification confirme que la prudence était aussi technique, pas seulement
un principe.

### Ce qui a été intégré

`core/production/ifc_generation.py` — `generer_croquis_cloison(longueur_m,
hauteur_m, epaisseur_m, nom)` : un projet IFC minimal, une cloison
rectiligne, sa quantité `Qto_WallBaseQuantities.NetSideArea` écrite dans le
même geste — **calculée exactement comme `agents/plaquiste/
calcul_materiaux.py` la lirait** (longueur x hauteur, une face), jamais un
second calcul qui pourrait diverger du devis. `core/connectors/
ifc_generation.py` (`ConnecteurIfcGeneration`) — une capacité `generer`
(écriture), `ALLOWED` sous `WRITE_FILES` (même logique que le devis,
DEC-0041 : le fichier reste local, dans `media/rendered/`, relu avant
d'être partagé).

Câblé dans `agents/plaquiste/plaquiste_agent.py` sur une phrase EXPLICITE
de génération (« génère le fichier ifc », « exporte... en ifc ») —
volontairement distincte et jamais déclenchée par la lecture d'un fichier
IFC existant (`chemin_dans`, DEC-0053) : lire et écrire sont deux demandes
différentes, vérifié par sabotage. Les dimensions (longueur x hauteur)
sont lues par un analyseur dédié, séparé de `agents/plaquiste/metre.py::
lire_demande` — celui-ci compte des parois et rend une surface déjà
multipliée, jamais la longueur et la hauteur séparément, ce qu'exige la
génération d'un mur.

### Tests et sabotages

Smoke test réel bout en bout : un croquis engendré est relu par notre
propre `ifc_lecture.py` (DEC-0053) et rend exactement la même surface.
Deux sabotages prouvés puis restaurés : une surface fausse écrite dans le
fichier généré (`+1.0`) fait tomber la garantie de cohérence
écriture/lecture ; le déclencheur de génération élargi à tout message
contenant « ifc » fait tomber la frontière lecture/écriture (lire un
fichier IFC existant aurait aussi tenté d'en générer un). `python -m ruff
check .` propre, `3777 passed, 25 skipped`.

### Ce qui n'a pas été implémenté, et pourquoi c'est honnête

- **Portes et fenêtres** : ajouter une ouverture suppose de positionner un
  linteau, une mesure que rien ici ne fait encore. `SUGGESTION — NON
  IMPLÉMENTÉE`.
- **Export DXF** : la mission le demande (§4) mais n'a aucun consommateur
  exprimé au-delà de l'IFC lui-même — pas construit pour l'instant.
- **Plusieurs murs / une pièce complète** : cette phase reste UNE cloison
  rectiligne ; composer un plan complet exigerait une disposition (angles,
  intersections) qu'aucune donnée actuelle ne fournit.
- **Le graphe de relations pièce-par-pièce** : voir plus haut — resterait
  `SUGGESTION — NON IMPLÉMENTÉE` même avec un besoin exprimé, tant que
  la fiabilité de la relation sous-jacente n'est pas démontrée sur un
  fichier réel d'un logiciel d'auteur.

### Ce que ça coûte si c'est faux

Une surface écrite dans le fichier IFC généré qui ne correspondrait pas à
celle du devis produirait deux documents contradictoires chez le même
client — un croquis technique et un devis qui ne s'accordent pas. La
garantie est donc dans le code (le même calcul, jamais recalculé), vérifiée
par sabotage, pas seulement énoncée ici.

## DEC-0057 — Drift : un éditeur vidéo appelé par son propre serveur MCP, jamais absorbé dans le métier

**2026-09-06.** Mission autonome du propriétaire : intégrer les capacités
réellement utiles de github.com/CutWire-Studios/Drift dans le workspace
Video existant (DEC-0037), avec une frontière explicite et répétée dans sa
propre demande : « DRIFT APPARTIENT EXCLUSIVEMENT AU WORKSPACE VIDEO » —
jamais UniC Plaquiste, jamais BIM, jamais métré/devis/matériaux/chantier/
finances/CRM. Exemple donné par lui-même : des photos/vidéos de chantier
entrent par le workspace Video, en ressort une vidéo avant/après ; jamais
Drift devenant un moteur BIM/métré/devis.

### Licence, vérifiée avant d'écrire une ligne

`LICENSE` des deux dépôts lus directement (pas un paraphrase de README) :
Drift et Drift-Addons sont tous deux **GPLv3**. Même frontière déjà tenue
pour VoiceStudio (AGPL) et KrillinAI (GPL-3.0, DEC-0049) : un programme
**séparé**, installé à côté de ce dépôt, jamais importé ni copié. Ce que
`core/connectors/drift.py` appelle n'est pas du code Drift : c'est son
**propre serveur MCP**, documenté dans son propre fichier de documentation
MCP — exactement la
frontière que Drift propose lui-même à un agent externe (« Turn on Agent
access and Cursor, Claude Code, or another compatible agent can work in
the open project »). Drift n'entre donc jamais dans ce dépôt.

### Le protocole, tel que Drift le documente — jamais deviné

`POST /mcp` avec `Authorization: Bearer <jeton>` (le serveur ne répond que
sur `127.0.0.1`, un jeton généré par session, jamais fixe). Cinq opérations
exposées comme des outils MCP : `catalog` (liste des dix toolboxes),
`toolbox({name})` (le schéma JSON réel d'UNE toolbox), `apply({ops:[...]})`
(exécute une liste de mutations comme un seul geste d'annulation),
`inspect({clips,detail})`, `capture()`. Dix toolboxes : media, timeline,
canvas, playback, text, effects, subtitles (Whisper inclus), audio, ai
(denoise/détection de visage/auto-reframe), scene (détection de plans).

`core/mcp/transport.py::ClientMcp` (déjà écrit pour WanGP) a reçu une seule
extension additive : un paramètre `jeton` optionnel, inclus dans l'en-tête
`Authorization: Bearer` seulement s'il est fourni — WanGP, qui n'en fournit
jamais, n'est pas affecté (ses tests restent verts sans modification).

### Ce qui a été intégré

`core/connectors/drift.py` (`ConnecteurDrift`, service `video_drift`) :
cinq capacités en miroir exact des cinq opérations Drift — quatre lectures
(`catalogue`, `boite_a_outils`, `etat_projet`, `capture`) et une écriture
(`appliquer`, sous `CONFIRMATION` + `WRITE_FILES`, même niveau que
`video_generation.generate`). Aucune URL ni jeton par défaut (DEC-0002) :
`DRIFT_MCP_URL`/`DRIFT_MCP_TOKEN` sont lus à l'appel, jamais un port deviné
— contrairement à WanGP dont le port par défaut est documenté dans son
propre README, celui de Drift ne l'est pas.

`core/production/plan_drift.py` traduit une demande en langage naturel
("coupe les silences", "ajoute une transition") en liste d'opérations
`apply({ops})` **sans jamais deviner ce que Drift accepte** : les dix
toolboxes sont la seule liste fermée écrite en dur (documentée par Drift
lui-même) ; à l'intérieur d'une toolbox, une opération et ses paramètres ne
sont acceptés que s'ils apparaissent dans le VRAI schéma renvoyé par
`toolbox({name})` **dans ce même appel** — une toolbox jamais chargée, une
opération absente du schéma, ou un paramètre inconnu sont refusés et
nommés, jamais exécutés à l'aveugle. Tout paramètre qui désigne un média
(`path`/`media`/`file`/`clip_path`/`source`) est résolu depuis un inventaire
`{nom: chemin}` ouvert par l'appelant — le modèle ne cite jamais un chemin,
seulement un nom, même garantie que `core/montage/planificateur.py`.

**Hypothèse explicite, non vérifiable sans le poste du propriétaire** (ce
dépôt tourne dans le cloud, Drift est un programme de bureau Qt qui n'y
tourne pas) : `toolbox({name})` est supposée rendre une forme proche de
celle de MCP lui-même (`tools/list` — `{"tools": [{"name", "inputSchema"}]}`).
Si la forme réelle diverge, le module refuse toute opération plutôt que
d'en deviner une — le mode d'échec est un refus, jamais une exécution
hasardeuse. `SUGGESTION — À CONFIRMER SUR SA MACHINE`, avec le vrai Drift.
Même limite, et même choix, pour la forme exacte d'un élément de `ops`
envoyé à `apply` : isolée dans une seule fonction (`_vers_forme_drift`),
pour qu'un ajustement futur reste local.

`agents/video/production_agent.py` : capacité `drift` ajoutée à
`CAPACITES_VIDEO` et `CAPACITES_ECRITURE` (`core/production/plan_video.py`)
— une écriture comme wangp/xaar_kaname/krillin_*, jamais confirmée à la
place du propriétaire ; un montage ne peut pas en dépendre directement dans
le même plan (même garde que pour les autres écritures). `_appeler_drift`
résout les références en inventaire, interroge Drift (catalogue puis les
dix schémas de toolbox), demande au modèle un plan d'opérations, le valide,
puis appelle `appliquer` via le registre — jamais en direct, ce qui fait
respecter la confirmation. Ajoutée à `CAPACITES_GPU_LOCAL` : un export
Drift tourne sur la même RTX A2000 que WanGP/vision/Xaar Kaname, il ne doit
pas s'y disputer la carte. `_artefact_final` sait désormais chercher, dans
la réponse d'un `apply` réussi, un chemin de fichier vidéo qui existe
réellement sur le disque (`_chemin_plausible`, profondeur bornée) — jamais
un chemin supposé, seulement un qui existe.

`core/production/disponibilite.py` (`PAR_CONNECTEUR`) et les deux fichiers
PWA (`videoProjectStore.ts`, `VideoProjectModal.tsx`) ont reçu `drift` —
sans ça, la capacité aurait existé partout sauf sur l'écran d'où on la
déclenche (précisément la dérive que `tests/test_capacites_video_pwa.py`
mesure depuis le 03/09/2026).

### La frontière du workspace Video, mesurée, pas seulement promise

`tests/core/test_connecteur_drift.py::TestFrontiereWorkspaceVideo` scanne
tout `core/`, `agents/`, `apps/`, `config/` (hors tests/docs) et échoue si
un fichier hors d'une liste explicite de six chemins autorisés nomme
« Drift » (sensible à la casse : « drift » minuscule reste le mot anglais
ordinaire, sans rapport). Un futur ajout qui referencerait Drift depuis
`agents/plaquiste/` ou `core/production/ifc*.py` ferait échouer ce test —
la frontière se mesure à chaque changement, elle ne se déclare pas une fois.

### Tests et sabotages

42 tests neufs (connecteur : 14, planificateur : 21, agent/smoke : 7), plus
les tests existants corrigés. Smoke test réel bout en bout
(`TestDrift::test_smoke_drift_jusqu_a_un_fichier_reel_exporte`) : une
demande en langage naturel traverse tout le chemin — inventaire de
références, catalogue, dix schémas de toolbox, plan composé par un modèle
scripté, validation contre le vrai schéma, `apply` confirmé — jusqu'à un
fichier réellement présent sur le disque, retrouvé comme `artefact_final`.

Quatre sabotages prouvés puis restaurés : (1) une référence à « Drift »
injectée dans un fichier métier (`ifc_generation.py`) fait tomber le test
de frontière ; (2) le rejet d'une opération absente du vrai schéma
désactivé fait planter la validation avec un `KeyError` — la preuve que la
garde protège d'un crash, pas seulement d'un refus poli ; (3) la
substitution nom→chemin désactivée fait fuiter le nom brut dans
`medias_autorises[...]`, `KeyError` à l'identique ; (4) `video_drift.apply`
passé à `ALLOWED` fait aboutir un appel Drift sans confirmation. Les quatre
restaurés, `python -m ruff check .` propre, suite complète : `3819 passed,
25 skipped, 48 deselected`.

Régressions détectées et corrigées en cours de route (la mesure, pas la
mémoire) : `tests/test_capacites_video_pwa.py`,
`tests/test_disponibilite_video.py` (deux listes parallèles de capacités
non mises à jour), `tests/test_documentation.py` (compteur `CLAUDE.md`
périmé — `python scripts/orphelins.py` mesure 201 modules, 160 atteints).

### Ce qui n'a pas été implémenté, et pourquoi c'est honnête

- **Drift-Addons** (Whisper/SAM2/ONNX/GPU) : la mission demande de
  l'inspecter, mais Drift documente déjà `subtitles.generate_subtitles`
  (Whisper) et `ai.*` (denoise, détection de visage, auto-reframe) comme
  des opérations natives de son propre serveur MCP — atteignables par ce
  connecteur SANS rien de plus. Ajouter Drift-Addons sans un besoin
  d'addon précis qu'aucune toolbox native ne couvre serait une seconde
  dépendance pour un recouvrement déjà servi. `SUGGESTION — NON
  IMPLÉMENTÉE`, à réévaluer si un addon précis manque une fois mesuré sur
  sa machine.
- **La restructuration du reste du pipeline vidéo** (fusion/suppression de
  moteurs existants pour éviter tout chevauchement avec Drift) : la
  mission autorise à réviser la répartition mais interdit explicitement de
  supprimer une capacité pour chevauchement partiel. Aucun chevauchement
  mesuré ne justifiait un retrait cette phase-ci (WanGP génère, Drift
  monte ; KrillinAI traduit/double, Drift monte ; aucun des deux ne fait
  ce que l'autre fait déjà en mieux, mesuré sur les schémas documentés
  seulement — pas sur un Drift réel). `SUGGESTION — NON IMPLÉMENTÉE`.
- **La forme exacte d'un élément `ops` et celle du schéma `toolbox()`** :
  voir plus haut — la seule chose qu'une session sur sa machine, avec le
  vrai Drift, peut trancher. Isolées chacune dans une fonction unique pour
  que la confirmation coûte un ajustement local, pas une réécriture.
- **Un rendu de la sortie `capture()` dans l'interface PWA** (aperçu JPEG
  en direct pendant un montage Drift) : aucune demande exprimée au-delà de
  la capacité elle-même, qui existe déjà (`capture`, lecture). `SUGGESTION
  — NON IMPLÉMENTÉE`.

### Ce que ça coûte si c'est faux

Une opération Drift acceptée sur la foi d'un schéma mal interprété
modifierait un projet vidéo réel du propriétaire de façon irréversible
dans l'état actuel de Drift (un `apply` est « un seul geste d'annulation »,
mais rien ici ne pilote cette annulation) — d'où le choix de tout refuser
plutôt que de deviner face à une forme de schéma incertaine, et la
confirmation obligatoire avant que quoi que ce soit n'atteigne un projet
réellement ouvert.

## DEC-0058 — Claude Context + OpenViking : deux couches réelles ; Agent-Reach reste refusé (DEC-0017 reconfirmé)

**2026-09-06.** Mission autonome : intégrer Claude Context (zilliztech,
compréhension du code), OpenViking (volcengine, mémoire/contexte/
compétences) et Agent-Reach (Panniantong, internet) comme trois couches
complémentaires du cerveau d'ARENA, sans les rendre indépendantes.

### Ce qui existait déjà, vérifié avant d'écrire une ligne

Trois voisins proches, chacun avec sa responsabilité, aucun doublon créé :
`core/connectors/graphify.py` (DEC-0046, graphe STRUCTUREL par
tree-sitter, sans modèle) ; `core/connectors/txtai_search.py` (DEC-0051,
index ÉPHÉMÈRE construit et jeté à chaque appel, plafonné à 200
documents FOURNIS) ; `core/memory/` (mémoire de conversation locale,
sans hiérarchie de niveaux). Aucun des trois ne tient un index PERSISTANT
et incrémental d'un dépôt, ni un contexte hiérarchique budgété en tokens —
c'est exactement ce que Claude Context et OpenViking apportent, et rien
d'autre n'a été touché ou fusionné pour ça.

### Claude Context — recherche sémantique de code, par son propre serveur MCP

Dépôt cloné et audité (`zilliztech/claude-context`), MIT confirmé
(`LICENSE` lu directement). C'est un projet TypeScript/Node.js : la bonne
frontière n'est pas légale mais architecturale — son propre serveur MCP
officiel (`@zilliz/claude-context-mcp`, `packages/mcp/src/index.ts`,
transport `StdioServerTransport`, quatre outils réels lus dans le code :
`index_codebase`, `search_code`, `clear_index`, `get_indexing_status`)
est la frontière déjà prévue par le projet pour un client externe — même
patron qu'OpenTakeoff (`core/connectors/opentakeoff.py`), même transport
(`core/mcp/stdio_transport.py`, réutilisé sans une ligne de plus, étendu
d'un paramètre additif `environnement` pour ce connecteur — WanGP/
OpenTakeoff, qui n'en fournissent jamais, ne sont pas affectés).

**Local-first forcé par la structure, pas par confiance** (DEC-0002).
Claude Context accepte quatre fournisseurs d'embeddings et documente
OpenAI comme choix par défaut. `core/connectors/claude_context.py::
_environnement()` construit l'environnement du sous-processus en partant
de `os.environ`, puis ÉCRASE `EMBEDDING_PROVIDER` à `"Ollama"` — un
`OPENAI_API_KEY` présent ailleurs sur la machine, pour un usage sans
rapport, ne peut jamais faire router un embedding vers un service cloud à
travers ce connecteur. `OLLAMA_HOST` reprend la MÊME variable que le
reste d'ARENA (`OLLAMA_BASE_URL`, `core/memory/semantique.py`) — jamais
une deuxième adresse Ollama inventée (un test dédié du dépôt,
`test_personne_d_autre_n_ecrit_l_adresse_en_dur`, l'a fait échouer une
première fois, corrigé). `CLAUDE_CONTEXT_MILVUS_ADDRESS` et
`CLAUDE_CONTEXT_EMBEDDING_MODEL` n'ont aucun défaut — un Milvus local
(auto-hébergé, Apache-2.0) existe, son adresse n'est jamais devinée.
Quatre capacités : `indexer`/`vider_index` (écritures locales et
rebâtissables, `ALLOWED` sous `WRITE_FILES`, même logique que
`graphify.construire`) et `rechercher`/`etat_indexation` (lectures).

### OpenViking — contexte hiérarchique/mémoire/compétences, par son propre serveur HTTP

Dépôt cloné et audité (`volcengine/OpenViking`). **Licence vérifiée fichier
par fichier, jamais supposée d'un sous-dossier à l'autre** (mission §13) :
le `LICENSE` racine est AGPLv3 ; trois sous-dossiers (`crates/ov_cli`,
`crates/ragfs`, `crates/ragfs-python`) portent chacun leur PROPRE
`Cargo.toml` avec `license = "Apache-2.0"`, vérifié en lisant ces trois
fichiers. Mais ces trois crates sont une abstraction de système de
fichiers BAS NIVEAU (`ragfs::core::{FileSystem, PluginRegistry}`,
consommée EN PROCESSUS via un binding Rust) — aucune logique de mémoire,
skills ou hiérarchie L0/L1/L2, qui vit dans le reste du dépôt, sous
AGPLv3. Importer la partie Apache-2.0 n'aurait donc rien apporté ici :
même raisonnement que le rejet de BuildingPy en DEC-0056, un second
morceau de dépendance pour un besoin qu'il ne sert pas.

Le serveur OpenViking lui-même (`docker-compose.yml`, port 1933) expose
une API HTTP publique et documentée dans son propre dépôt (`docs/en/
api/`, vingt-quatre pages lues directement, pas devinées) : réponses
`{"status":"ok","result":{...}}`, authentification `Bearer`/`X-API-Key`.
`core/connectors/openviking.py` en appelle quatre routes, un client HTTP
ordinaire — même frontière que Formbricks (DEC-0052) et SiteGuard
(DEC-0054), jamais un import :
- `contexte` → `POST /api/v1/search/search` (`mode="context"`) : le
  contexte DÉJÀ ASSEMBLÉ, budgété en tokens (`max_tokens`), dégradé par
  palier L0/L1/L2 et dédupliqué entre tours côté serveur — exactement ce
  qu'aucun système d'ARENA ne rend aujourd'hui.
- `rechercher` → `POST /api/v1/search/find` : recherche vectorielle simple.
- `competences` → `POST /api/v1/skills/find`.
- `ecrire_ressource` → `POST /api/v1/resources` : ajoute une URL à la
  base de contexte du propriétaire — écriture locale sur SON serveur,
  `ALLOWED` sous `WRITE_FILES` (même logique que le devis PDF, DEC-0041 :
  ce qui reste sur sa propre machine ne demande pas d'accord préalable).

**Rien ne remplace `core/memory/memory_manager.py`.** Cette capacité
reste explicite, jamais appelée à la place de la mémoire de chat — même
discipline que txtai (DEC-0051).

### Agent-Reach — dépôt re-cloné, DEC-0017 reconfirmé, rien de nouveau à intégrer

Re-vérifié à neuf (pas recopié de mémoire) : dépôt cloné et relu, huit
jours après l'audit de DEC-0017. Le dépôt le dit toujours de lui-même :
« Agent Reach 是一个能力层（capability layer），不是又一个工具 » (« une
couche de capacité, pas un autre outil ») — il sélectionne, installe,
teste et route entre des outils tiers déjà indépendants (`yt-dlp`,
`feedparser`, `gh`, Jina Reader, Exa via `mcporter`), il ne cherche ni ne
lit rien lui-même. Une évolution mesurée depuis DEC-0017 va dans le même
sens que la conclusion, pas contre elle : YouTube/Bilibili a perdu
`yt-dlp` (bloqué par le contrôle anti-scraping de Bilibili depuis
06/2026) au profit d'un CLI de repli — une dépendance de plus qui casse,
pas une capacité qui se stabilise. La recherche « tout le web » et la
lecture de page restent routées vers des services cloud tiers (Exa, Jina
Reader) non revus selon la discipline DEC-0009 ; les réseaux sociaux
exigent toujours les cookies de session **personnels** du propriétaire.

**La décision ne change pas** : rien d'Agent-Reach n'est intégré.
L'internet layer d'ARENA reste `FreshInfoAgent`/`TrendAnalyzerAgent`/
`agents/researcher/researcher_agent.py` (déjà parallélisé, DEC-0017) —
relu à nouveau ici, aucun TODO ni défaut trouvé qui justifierait un
changement forcé (mission : « si elle est correcte, améliore-la » — rien
à améliorer sans preuve d'un défaut, exactement le principe qui a fermé
`FreshInfoAgent` en DEC-0017).

### La couche qui les fait collaborer, sans troisième système parallèle

`core/context/recherche_unifiee.py` — une heuristique par mots-clés (code/
mémoire/internet) décide QUELLES sources une question appelle, les
interroge en PARALLÈLE (`asyncio.gather`), fusionne avec PROVENANCE
(`"codebase"`/`"openviking_memory"`/`"web"`, jamais un bloc anonyme). Un
modèle pour cette décision aurait été un coût pour un signal déjà lisible
dans la question — même choix que le repli mots-clés de
`agents/orchestrator/orchestrator_agent.py`. Chaque source reste un appel
ORDINAIRE (`registre.executer(...)`, ou l'agent internet déjà existant) :
aucun nouveau système de permissions, de registre ou de routage n'a été
inventé — le sien reste soumis à celui déjà en place. Atteignable
réellement, pas dormant : `POST /api/contexte/rechercher`
(`apps/backend/routers/contexte_unifie.py`), jamais câblé au chat (même
choix que `/api/hermes-evolution/evoluer` — un outil explicite, pas une
capacité métier).

**Un défaut réel trouvé et corrigé en écrivant les tests** : appeler
`registre.executer(...)` (synchrone, bloquant — httpx, sous-processus)
directement dans une coroutine bloque la boucle asyncio ENTIÈRE le temps
de l'appel, malgré un `asyncio.gather` de façade — exactement le défaut
que DEC-0017 avait déjà trouvé et corrigé pour `DeepResearcherAgent`.
Mesuré par un test de parallélisme réel (deux sources à 0,1 s chacune,
0,1 s au total attendu) : sans le pont par thread
(`asyncio.to_thread`), le total mesuré passe à 0,2 s — le sabotage
inverse (retirer `asyncio.to_thread`) l'a confirmé, puis restauré.

### Tests et sabotages

49 tests neufs (Claude Context : 13, OpenViking : 16, recherche unifiée :
17, route `/api/contexte/rechercher` : 3), plus les tests existants
corrigés. Trois sabotages prouvés puis restaurés : (1) l'écrasement de
`EMBEDDING_PROVIDER` retiré fait disparaître la clé de l'environnement du
sous-processus (`KeyError`) ; (2) l'appel direct au registre (sans
`asyncio.to_thread`) fait retomber le test de parallélisme à 0,2 s ; (3)
une URL OpenViking par défaut ajoutée fait tenter une vraie connexion
réseau au lieu de rapporter `NON_CONFIGURE` — la différence entre
`Statut.NON_CONFIGURE` et `Statut.ECHEC` prouve que l'appel a réellement
été tenté. `python -m ruff check .` propre, suite complète :
`3869 passed, 25 skipped, 48 deselected`.

Régressions détectées et corrigées en cours de route (la mesure, pas la
mémoire) : `test_configuration_clients.py` (une deuxième adresse Ollama
inventée), `test_documentation.py` (le nouveau module de recherche
unifiée dormait tant qu'aucune route ne l'atteignait — corrigé en
l'atteignant réellement, pas en le documentant comme exception ; compteur
`CLAUDE.md` périmé — `python scripts/orphelins.py` mesure 206 modules,
164 atteints).

### Ce qui n'a pas été implémenté, et pourquoi c'est honnête

- **Le reste de la surface OpenViking** (ACL, snapshots, WebDAV,
  administration, agent evolution, watches) : hors de la portée réelle
  demandée (mémoire/contexte/compétences). `SUGGESTION — NON IMPLÉMENTÉE`.
- **L'upload de fichier local vers OpenViking** (`temp_upload` +
  multipart) : `ecrire_ressource` ne couvre que l'ajout par URL — un
  besoin réel mais non exprimé ici. `SUGGESTION — NON IMPLÉMENTÉE`.
- **Un banc de comparaison chiffré entre la mémoire d'ARENA et
  OpenViking** (pertinence/latence, comme envisagé pour txtai en
  DEC-0051) : ni Ollama ni un serveur OpenViking réel n'existent dans ce
  bac à sable — même limite que la phase 7.2. `SUGGESTION — NON
  IMPLÉMENTÉE`, à mesurer sur sa machine.
- **Un routage par modèle plutôt que par mots-clés** pour la recherche
  unifiée : l'heuristique actuelle couvre les exemples de la mission ;
  un modèle n'apporterait rien de mesurable ici sans corpus réel de
  questions ambiguës. `SUGGESTION — NON IMPLÉMENTÉE`.

### Ce que ça coûte si c'est faux

Un `EMBEDDING_PROVIDER` qui filtrerait depuis l'environnement hérité
enverrait le code du propriétaire — potentiellement des secrets, des prix,
des chemins de chantier — vers un service cloud tiers à son insu,
exactement ce que DEC-0002 existe pour empêcher. Une URL OpenViking
devinée par défaut connecterait ARENA à un service qui n'est pas le sien.
Les deux gardes sont vérifiées par sabotage, pas seulement énoncées.

## DEC-0059 — Lightpanda : moteur optionnel derrière la navigation déjà en place, jamais un second navigateur

**2026-09-06.** Mission autonome : évaluer Lightpanda (`lightpanda-io/
browser`) pour ARENA, avec une règle absolue explicite : ne jamais créer un
second système s'il en existe déjà un, comparer et fusionner sinon.

### Ce qu'ARENA possède déjà, vérifié avant d'écrire une ligne

Recherche explicite dans `agents/`, `core/`, `apps/`, `tools/`, `tests/`,
`config/`, `documentation` (mission §« règle anti-doublon ») : ARENA a
**déjà un navigateur complet**, pas une absence à combler.
`agents/browser/browser_agent.py` (`BrowserAgent`, intention `BROWSER` de
l'orchestrateur, câblée dans `apps/backend/routers/chat.py:404-405`)
pilote `tools/browser/browser_use_tool.py::BrowserUseTool` —
`browser-use==0.13.10` (agent autonome : clics, formulaires, extraction,
piloté par un LLM local via Ollama) sur `playwright==1.62.0` (Chromium
local complet, JavaScript, DOM). Ces deux dépendances sont réelles et
installées depuis le 04/09/2026 — deux jours avant cette mission, pas un
trou dans l'architecture. `tools/search/source_fetcher.py` (utilisé par
`FreshInfoAgent`) est un lecteur de page STATIQUE (httpx + parseur HTML
`stdlib`, sans JavaScript) : un rôle différent, jamais concurrent.

**Le vrai défaut trouvé pendant l'audit** (mission §« sécurité », phase 1
demandait explicitement d'inspecter les permissions) : `BrowserAgent`
appelait `BrowserUseTool` en direct, **hors du registre et des
permissions** (`ControleAcces`/`config/permissions_services.yaml`) — la
seule capacité d'ARENA agissant de façon autonome sur le web (clics,
formulaires, donc des effets externes réels) sans passer par le même
contrôle d'accès que WanGP, KrillinAI ou les connecteurs des missions
précédentes. Aucun rapport avec Lightpanda : un défaut préexistant,
trouvé en auditant l'existant comme demandé, corrigé dans la foulée.

### Lightpanda, audité en clonant le dépôt réel

`lightpanda-io/browser` cloné et inspecté (jamais son seul README) : un
navigateur écrit **à partir de zéro en Zig** (moteur JS V8, parseur HTML
`html5ever`/Servo, `libcurl`) — pas un fork de Chromium. Statut, dit par
le projet lui-même : « Beta [...] you may still encounter errors or
crashes » — honnête, pas du marketing. Vraies infrastructures de test
(`make test`, tests de bout en bout, Web Platform Tests publiés
quotidiennement sur `perf.lightpanda.io/wpt`). Serveur CDP natif
(`lightpanda serve --port 9222`), compatible Puppeteer/Playwright par
construction — c'est le point d'entrée que ce dépôt utilise.

**Licence, vérifiée en lisant `LICENSE` et `LICENSING.md` directement**
(mission §« licence ») : AGPL-3.0-only, sans exception ni double licence
— contrairement à OpenViking (DEC-0058), aucun sous-dossier séparément
licencié. Même frontière que tout composant AGPL/GPL déjà traité cette
session (VoiceStudio, KrillinAI, SiteGuard, Drift, OpenViking) : un
service **séparé**, jamais importé (impossible de toute façon — Zig,
pas Python) ni vendorisé. Se connecter à son serveur CDP comme client,
sans le modifier, est l'usage que le projet documente et attend
lui-même — aucune obligation de la clause réseau de l'AGPLv3 (section 13)
ne s'applique à un client non modifié d'un service non modifié.

### Ce qui a été intégré, et sous quelle forme

**Aucun second agent, aucun second outil.** `tools/browser/
browser_use_tool.py::BrowserUseTool.run_task()` reçoit un paramètre
additif `cdp_url: Optional[str] = None`, transmis à `browser_use.browser.
session.BrowserSession(cdp_url=...)` — vérifié dans le code RÉELLEMENT
installé (`browser-use==0.13.10`, pas deviné depuis sa documentation) :
fourni, `browser_use` se connecte à un navigateur DÉJÀ lancé (Lightpanda)
au lieu d'en démarrer un ; `None` (le défaut) laisse le comportement
IDENTIQUE à avant ce paramètre.

`core/connectors/browser.py` (`ConnecteurBrowser`) porte le routage et
corrige le défaut de permission dans le même geste — une seule capacité
logique, `naviguer` :

1. **Lightpanda configuré ET sain** (`LIGHTPANDA_CDP_URL` réglé — aucun
   défaut, DEC-0002 — et `GET {url}/json/version` répond 200 : cet
   endpoint est vérifié dans le CODE SOURCE de Lightpanda,
   `src/server/http.zig::serveJSONVersion`, avec son propre test unitaire
   `"server: get /json/version"`, jamais supposé) : tenté en premier.
2. **Échec Lightpanda, à tout moment** : repli silencieux et automatique
   sur le moteur existant — jamais un échec transmis tant que Chromium
   peut répondre. Justifié par le statut « Beta » du projet lui-même.
3. **Lightpanda non configuré** : le moteur existant est utilisé
   directement — comportement STRICTEMENT identique à avant ce
   connecteur pour un propriétaire qui ne configure rien.

`agents/browser/browser_agent.py` appelle désormais
`registre.executer("browser", "naviguer", tache=...)` au lieu de
`BrowserUseTool` en direct — même discipline que `VisionAgent` pour
`securite_chantier` (DEC-0054). Permission : `browser.browse = ALLOWED,
risque MEDIUM, interrupteur SEARCH_WEB` (réutilise le regroupement « web »
déjà existant, jamais un second coupe-circuit inventé) — `ALLOWED` pour
préserver le comportement RÉEL d'avant cette mission (aucune confirmation
n'existait), tout en le rendant enfin GOUVERNÉ : le propriétaire peut
resserrer en `CONFIRMATION` par simple configuration, sans toucher au
code. `naviguer` reste déclarée `ecriture=True` (des clics/formulaires ont
un effet externe réel).

### Tests et sabotages

20 tests neufs (connecteur : 12, agent : 5, `cdp_url` sur `BrowserUseTool`
réel : 3), plus l'existant relu. Trois sabotages prouvés puis restaurés :
(1) le repli après échec Lightpanda retiré → un échec réel se présente
comme un succès (`Statut.SUCCES` au lieu de `Statut.ECHEC`) — la preuve
qu'un défaut ici mentirait sur ce qui s'est réellement passé ; (2) la
garde « pas de registre, pas de navigation » retirée de `BrowserAgent` →
`AttributeError` au lieu d'un refus propre ; (3) le health-check
Lightpanda ignoré → le moteur non joignable est quand même tenté. `python
-m ruff check .` propre, suite complète : `3889 passed, 25 skipped,
48 deselected`.

### Smoke test réel — ce qui a pu être vérifié dans ce bac à sable, et pourquoi une partie ne l'a pas pu

**Vérifié pour de vrai** (Chromium `/opt/pw-browsers/chromium`, déjà
présent ici) : lancement réel (0,57 s), navigation réelle vers une page
locale servie par un vrai serveur HTTP (`127.0.0.1`, jamais un mock),
exécution JavaScript réelle (le texte extrait a été écrit par le
`<script>` de la page elle-même, pas présent dans le HTML brut),
extraction réelle du contenu, fermeture propre — 1,05 s au total. Preuve
que le moteur EXISTANT (la branche par défaut de ce connecteur) fonctionne
de bout en bout dans cet environnement.

**Non vérifiable ici, et pourquoi** : la politique réseau de ce bac à
sable bloque toute destination hors d'une liste précise (registres de
paquets, API Anthropic) — une navigation vers un site public réel
(`example.com` y compris) est refusée par le proxy sortant, mesuré
directement (`connect_rejected`, 403). Le smoke test réel a donc ciblé
une page locale plutôt qu'un site public, ce qui reste un test honnête du
mécanisme (navigation + JS + extraction), pas du contenu d'Internet.
Le chemin `browser_use.Agent` complet (la boucle autonome pilotée par un
LLM) n'a pas pu tourner : Ollama est absent de ce conteneur — même limite
que la phase 7.2 (`docs/CURRENT_TASK.md`) et que WanGP toute la session.
`browser_use.BrowserSession.start()` a par ailleurs échoué SANS
`cdp_url` dans ce bac à sable précis (extensions non téléchargeables,
lancement Chrome nécessitant des permissions de conteneur que
`browser_use` ne configure pas par défaut ici) — indépendant de ce
connecteur, jamais rencontré avec Playwright utilisé directement. Aucun
Lightpanda réel n'a pu tourner non plus (ni binaire ni Docker disponibles
ici, comme pour tout composant nécessitant Docker cette session).
`SUGGESTION — À VÉRIFIER SUR SA MACHINE` : le smoke test complet
(Lightpanda réel, `browser_use.Agent` avec Ollama, repli mesuré sur un
Lightpanda arrêté en cours de tâche) attend son PC, comme les mesures 7.2.

### Ce qui n'a pas été implémenté, et pourquoi c'est honnête

- **Un classement des tâches par compatibilité Lightpanda a priori**
  (mission : « compatible Lightpanda → Lightpanda, nécessite fonctions
  absentes → moteur existant ») : impossible à deviner honnêtement sans
  visiter la page cible en premier. Remplacé par une stratégie empirique
  strictement plus sûre — tenter, puis retomber sur tout échec — qui
  couvre exactement le troisième cas du diagramme de la mission
  (« échec Lightpanda → fallback ») sans jamais inventer une
  classification a priori. `SUGGESTION — NON IMPLÉMENTÉE` : un vrai
  classement demanderait un jeu de mesures sur des tâches réelles,
  disponible seulement sur sa machine.
- **Benchmarks chiffrés Lightpanda vs Chromium** (mission §« comparaison
  avec l'existant ») : aucun binaire Lightpanda n'a pu tourner ici. Les
  chiffres du propre dépôt Lightpanda (16x moins de RAM, 9x plus rapide)
  ne sont PAS repris comme acquis — mission §« ne crois pas
  automatiquement les chiffres marketing » — seulement cités comme
  revendication à vérifier. `SUGGESTION — À MESURER SUR SA MACHINE`.
- **Installation effective de Lightpanda** (binaire, Docker ou WSL2) :
  hors de portée de ce dépôt — le propriétaire choisit et installe à
  côté, comme WanGP/OpenTakeoff/MoneyPrinterTurbo. Ce connecteur reste
  `NON_CONFIGURE`-compatible (aucune tentative sans `LIGHTPANDA_CDP_URL`)
  jusqu'à ce geste.

### Ce que ça coûte si c'est faux

Un repli qui échouerait silencieusement laisserait une tâche de
navigation échouer sans que l'appelant sache que Lightpanda, et non le
moteur existant, en était la cause — d'où le sabotage qui a confirmé que
retirer le repli change RÉELLEMENT le statut rendu, pas seulement un
message. Une permission de navigation restée non gouvernée aurait laissé
un agent autonome cliquer/remplir des formulaires sur le web sans que le
coupe-circuit général (`SEARCH_WEB`) ni le journal des actions ne le
voient — exactement le défaut trouvé et corrigé ici.

---

## DEC-0060 — AutoPentestX : même refus que CyberStrike (DEC-0042 reconfirmé), rien câblé

**2026-09-06.** Demande reçue : auditer **AutoPentestX**
(github.com/Gowtham-Darkseid/AutoPentestX) et fusionner ses meilleures
capacités dans un « Security Engine » unifié d'ARENA — reconnaissance,
scan de vulnérabilités, exploitation, reporting CVE/CVSS — avec interdiction
explicite de dupliquer si une capacité équivalente existe déjà.

### Audit d'ARENA d'abord — ce qui existe déjà

Aucun Security Engine, Security Router ni SecurityAgent n'existe dans
`agents/`, `core/`, `apps/`. La seule trace de sécurité *offensive* dans le
dépôt est **DEC-0042** (04/09/2026) : une demande d'intégrer **CyberStrike**
(reconnaissance, exploitation active, attaques de mots de passe) a été
**refusée**, remplacée par deux capacités *défensives sur le propre code
du dépôt* : `scripts/scanner_secrets.py` (DEC-0042) et
`scripts/scanner_dependances.py` (DEC-0043, failles connues des
dépendances via `pip-audit`). Aucune des deux ne vise une cible externe.

### Audit réel d'AutoPentestX (dépôt cloné, code lu — pas le README seul)

Licence : **MIT** (`LICENSE`), avec une clause additionnelle explicite
« for educational and authorized testing purposes only ». `DISCLAIMER.md`
place l'intégralité de la charge d'autorisation sur l'auteur de la
commande — « you MUST obtain written authorization from the system
owner » — sans aucun mécanisme technique qui vérifie cette autorisation :
exactement l'« auto-déclaration n'est pas une autorisation » identifiée
par DEC-0042.

Le code confirme que c'est un moteur offensif complet, pas un rapport :

- son module scanner (`scanner.py`, dans `modules/` du dépôt AutoPentestX)
  — scan de ports et détection d'OS via **Nmap** (`nmap.PortScanner()`)
  sur une cible réseau arbitraire fournie en paramètre.
- son module d'analyse de vulnérabilités (`vuln_scanner.py`) — **Nikto**
  (scan web) et **SQLMap** (injection SQL) lancés en sous-processus contre
  la même cible.
- ses modules CVE et risque (`cve_lookup.py` / `risk_engine.py`) —
  recherche CVE (circl.lu, NVD) et score CVSS pour les services détectés.
- son moteur d'exploitation (`exploit_engine.py`) — intégration
  **Metasploit** : associe vulnérabilités/CVE à des modules d'exploit
  connus (EternalBlue, Shellshock, Drupalgeddon2, backdoors FTP…) et
  **génère de vrais scripts de ressource Metasploit** (`.rc`, avec
  `RHOSTS`/`RPORT`/`PAYLOAD`/`LHOST`/`LPORT` déjà remplis, payload par
  défaut `generic/shell_reverse_tcp`). Le « safe mode » n'empêche que la
  ligne finale `exploit` d'être décommentée — le reste de la chaîne
  (scan, association, script prêt à l'emploi) tourne identiquement.

C'est la même catégorie d'outil que CyberStrike, à l'identique sur les
trois points qui avaient motivé le refus : reconnaissance + exploitation
active contre des cibles externes, autorisation reposant uniquement sur
une déclaration de l'utilisateur, aucun rapport avec le métier d'Ousmane
(devis, vidéo, documents — un plaquiste à Dakar, pas un pentesteur).

### Ce qui a été refusé, et pourquoi

**Rien n'a été câblé.** Aucun connecteur, aucun agent, aucune capacité
`security.scan`/`security.assess`/`security.recon` n'a été ajouté à
ARENA. Les trois raisons de DEC-0042 s'appliquent sans changement :

1. Une case « cible autorisée » cochée dans un chat n'est pas une preuve
   de propriété — AutoPentestX le confirme lui-même : toute la charge
   d'autorisation est déclarative, jamais vérifiée techniquement.
2. Aucun contexte réel de mission de pentest, de périmètre écrit ou de
   labo n'existe dans ARENA pour donner un sens à cette autorisation.
3. Hors mission : un moteur capable de scanner un réseau, générer des
   payloads Metasploit et chercher des CVE, accessible depuis un
   téléphone, est un risque permanent pour un usage que le métier
   n'a jamais demandé.

### Ce qui existait déjà couvre ce qu'AutoPentestX apporte de légitime

La seule partie d'AutoPentestX qui n'est pas intrinsèquement offensive
— le reporting (ses modules `pdf_report.py` et `database.py`) — n'a de
sens qu'attachée aux résultats d'un scan externe qu'ARENA ne doit pas
lancer. Le besoin défensif réel (savoir si le dépôt lui-même contient un
secret ou une dépendance vulnérable) est déjà couvert par DEC-0042/DEC-0043,
contre la seule cible dont la propriété n'est pas ambiguë : le dépôt
d'ARENA lui-même. Rien à fusionner, rien à remplacer, rien de nouveau à
créer.

### Ce que ça coûte si c'est faux

Le coût d'un refus à tort serait une capacité manquante que le métier ne
réclame pas. Le coût d'une intégration à tort serait un moteur de scan
réseau et de génération de payloads d'exploitation, tournant chez lui,
atteignable depuis son téléphone, sur la seule foi d'une phrase tapée
dans un chat — le exact scénario que DEC-0042 a déjà écarté. Le second
coût est sans commune mesure avec le premier ; la décision reste la même.
