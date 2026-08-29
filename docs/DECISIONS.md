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
