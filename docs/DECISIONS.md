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
