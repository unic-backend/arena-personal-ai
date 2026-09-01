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
propres secrets (`.env`, `config/unic_plaquiste.yaml`) — avant de le
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
| `config/unic_plaquiste.yaml` — sa grille de prix | |
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
