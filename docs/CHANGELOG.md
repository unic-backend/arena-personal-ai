# CHANGELOG - Usman PERSONAL AI

## [Non publié]

### Ajouté — 03/09/2026 — Deux adresses, et le serveur qui répond vraiment

Le propriétaire branche son téléphone sur son PC et pose la bonne question :
*« mon PC éteint, est-ce que ton travail a cassé Railway ? »*

**Non** — vérifié : les nouveaux connecteurs sont déclarés en paresseux, aucun
n'importe torch au démarrage, aucune dépendance ajoutée au serveur. Mais
l'application ne retenait **qu'une seule adresse** (`url` était un texte, pas
une liste). Brancher son PC effaçait Railway ; PC éteint, plus rien ne
répondait jusqu'à ce qu'il recolle l'adresse à la main.

Une seconde adresse existe maintenant, avec sa propre clé. **L'ordre n'est pas
un détail** : sa machine d'abord, toujours — le modèle y tourne chez lui et
rien ne part chez un tiers (DEC-0002). Le secours n'est essayé **que** quand
le principal ne répond pas, jamais en parallèle : sonder les deux à la fois
pourrait envoyer un message dehors alors que son PC était seulement lent.

`activeRemoteCfg()` rend **celui qui a répondu**, pas celui qu'on préfère.
Sans ça, chaque message partirait vers le PC éteint pendant que le panneau
afficherait « en ligne » grâce au secours. L'écran nomme lequel des deux
répond — un « en ligne » qui ne dit pas où part le texte ne vaut rien.

Ce que ça coûte, et c'est écrit dans le test : **l'échec total prend ~13 s**
(2 serveurs × 3 tentatives × attentes croissantes). C'est le prix de la
bascule, et il ne se paie que quand les deux sont muets.

5 tests de plus (17 côté PWA), qui **exécutent** la bascule. Sabotages :
parler au préféré au lieu du répondant, ne plus essayer le secours, ne plus
enregistrer la seconde adresse — chacun fait tomber une garde.

### Corrigé — 03/09/2026 — Il voyait son ancienne interface, Dioumtoukay disparu

Même session, symptôme alarmant : *« je suis dans l'ancienne version de mon
interface et le modèle dioumtoukay n'est plus là, peut-être beaucoup de
travail sont cassés ou partis »*.

**Rien n'était perdu.** `apps/pwa/dist/` est ignoré par git — Vite le
régénère — donc il n'existe jamais après un `git pull`. `interface_servie()`
retombait alors **en silence** sur `apps/frontend/index.html`, l'ancienne
interface, où l'espace Dioumtoukay n'existe pas.

Le serveur savait laquelle il servait (`/health` le dit) ; le lanceur, lui,
ne disait rien. `Lancer_ARENA.bat` compile désormais la PWA quand elle manque,
annonce **toujours** laquelle sera servie, et quand npm est introuvable
explique ce qui sera perdu au lieu de démarrer sans le dire.

C'est le défaut de la nuit dans sa version la plus coûteuse : le silence a
fait croire à une perte de travail.

Suite Python : 3370 passent. Suite PWA : 17 passent.

### Corrigé — 03/09/2026 — Une trace rouge à la fin d'un démarrage réussi

`Lancer_ARENA.bat` démarre tout correctement — Ollama, serveur, tunnel,
adresse — puis affiche une trace Python en rouge. Elle se lit comme « ARENA
n'a pas démarré » alors que l'adresse à scanner est juste au-dessus.

Cause : le paquet `qrcode` manque, donc `python -c "import qrcode..."` écrit
sur la sortie d'erreur. Sous `$ErrorActionPreference = "Stop"`, PowerShell 5.1
en fait une erreur **bloquante** (`NativeCommandError`) — **avant** la
redirection.

**Un premier correctif avait ajouté `2>$null` et une branche sur
`$LASTEXITCODE`, en croyant la redirection suffisante.** Elle ne l'est pas.
C'est pour ça que ce correctif-ci porte un test plutôt qu'un commentaire : la
même erreur a été commise deux fois.

La préférence passe à `Continue` le temps de cet appel et revient dans un
`finally` — ailleurs dans ce script, une erreur doit toujours arrêter.

25 tests. Suite complète : 3370 passent.

### Corrigé — 03/09/2026 — Un installeur annonçait « Termine » sur un échec total

Le diagnostic sur sa machine rend tout au vert sauf une ligne :

```
[PANNE] Visages (Faceplugin)  Le moteur ne démarre pas.
                              (ModuleNotFoundError: No module named 'cv2')
```

Cause racine : **son Python est 3.14.6, et `torch==2.4.1` n'a de roues que
pour 3.8 à 3.12** (vérifié sur PyPI : `cp38` à `cp312`). L'environnement créé
depuis son interpréteur ne pouvait donc rien installer — et l'installeur a
affiché **« Termine »**.

`$ErrorActionPreference = "Stop"` **ne couvre pas** le code de sortie d'un
programme externe sous PowerShell 5.1. Le `pip install` a échoué de bout en
bout sans que le script s'en aperçoive.

C'est la règle 3 de la mentalité d'Usman — *une action ratée se rapporte telle
quelle* — appliquée à un script. Et le mensonge n'a été rattrapé qu'une étape
plus loin, par la ligne de diagnostic ajoutée le matin même. **Sans elle, il
aurait cru la capacité installée.**

Deux corrections :

- L'installeur **choisit** son interpréteur (`py -3.12`, `-3.11`, `-3.10`) au
  lieu de subir celui du système, refait un environnement bâti sur un Python
  trop récent, et **s'arrête en le disant** si aucune version compatible n'est
  présente. Un environnement construit sur le mauvais interpréteur est pire
  qu'une absence d'environnement : il a l'air installé.
- Il vérifie que le moteur **s'importe vraiment** avant d'annoncer la fin.

**La garde a immédiatement trouvé le même défaut dans les trois autres
installeurs** — MoneyPrinterTurbo, OpenTakeoff, UI/UX Pro Max. Aucun ne
regardait `$LASTEXITCODE`. Tous les quatre s'arrêtent maintenant sur l'échec
de leur `git`, `npm`, `pip` ou `venv`.

24 tests (`tests/test_scripts_powershell.py`). Suite complète : 3369 passent.

### Corrigé — 03/09/2026 — Les scripts PowerShell ne démarraient pas chez lui

Il colle la séquence d'installation. Les deux installeurs sont refusés avant
leur première ligne :

```
Le terminateur " est manquant dans la chaîne.
... ite-Host "  UI/UX Pro Max â€" intelligence de design, a cote d'ARENA"
```

Windows PowerShell 5.1 décode un `.ps1` **sans BOM** en cp1252, jamais en
UTF-8. Un `—` (trois octets) devient trois caractères parasites, `«` et `»` en
produisent deux chacun. Tombés dans une chaîne, le guillemet fermant n'est
plus trouvé et **le script entier est rejeté**.

La solution évidente — enregistrer avec un BOM — est fermée ici :
`test_aucun_fichier_ne_commence_par_un_bom` l'interdit, pour de bonnes raisons
de son côté. Reste la seule qui marche partout : de l'ASCII pur.

**Cinq des sept scripts en contenaient**, pas seulement les deux nouveaux. Les
trois plus anciens (`installer_moneyprinter`, `installer_opentakeoff`,
`lancer_arena`) n'avaient pas encore cassé — leurs caractères ne tombaient pas
dans une chaîne. Ils attendaient la mauvaise ligne au mauvais endroit.

C'est la troisième fois en deux jours qu'un encodage casse quelque chose ici
— après le BOM du YAML et le double encodage de `plan_video.py`. Les trois
avaient la même forme : un fichier écrit sous une hypothèse d'encodage, lu
sous une autre.

16 tests (`tests/test_scripts_powershell.py`). Le second mesure le symptôme
exact qu'il a vu — une ligne qui laisse une chaîne ouverte — car l'ASCII seul
ne le garantit pas. Sabotages : remettre un tiret cadratin, remettre un
guillemet en trop ; chacun fait tomber sa garde.

Suite complète : 3361 passent.

### Ajouté — 03/09/2026 — La PWA a enfin un lanceur de tests

Le point était noté dans `docs/REPRISE.md` comme « un travail à part ». Il
n'était plus tenable : le code qui décide si une démo du navigateur peut
répondre à la place du serveur — donc **se faire passer pour son IA** —
n'était gardé que par des tests Python qui **lisent** le source TypeScript.

Une garde qui lit du texte voit une forme, pas un comportement.

`npm test` (vitest + jsdom) tourne, et la CI l'exécute dans un job `pwa` avec
le typecheck et le build. `jsdom` n'est pas décoratif : `backendStore` lit
`localStorage` et s'abonne à `online` — sans navigateur simulé, ces
chemins-là ne s'exécutent pas du tout.

12 tests, sur ce qui a réellement fait mal cette nuit :

| Ce qui est exécuté | Ce que ça empêche |
|---|---|
| `choisirTransport(null)` rend le refus, jamais la voie sur appareil | qu'une démo réponde à sa place |
| `choisirTransport(null, true)` reste local | que le montage vidéo tombe avec la démo |
| `offlineTransport` ne produit **aucun** jeton | qu'on remette du texte à la place du serveur |
| il distingue « aucun serveur » de « serveur muet » | qu'on cherche une panne sans la nommer |
| une coupure **non signée** revient branchée | qu'il doive réparer le défaut à la main |
| une coupure **signée** tient | que son choix soit annulé par la reprise |
| un échec de sonde **ne débranche pas** | qu'une coupure passagère devienne durable |

Trois sabotages — repli redevenu la démo, reprise désactivée, échec qui
débranche — font tomber une garde chacun.

**Ce qui reste non couvert, et il faut le dire** : le rendu à l'écran. Aucun
composant React n'est monté ici, et Playwright reste manuel. Un lanceur qui
existe ne teste pas tout ; il teste ce qu'on lui a écrit.

**Le premier passage en CI est tombé, et le défaut méritait d'être gardé.**
La CI épinglait Node 20 pendant que le développement tournait en 22. `undici@8`
(tiré par jsdom) appelle `webidl.util.markAsUncloneable`, absente de Node 20 :
les 12 tests passaient en local et la CI rendait **« no tests »** avec deux
erreurs non capturées — ce qui se lit comme une suite vide, pas comme une panne.

Un lanceur de tests qui rapporte « aucun test » au lieu d'un échec est plus
dangereux que pas de lanceur du tout.

La version vient désormais d'`apps/pwa/.nvmrc`, lue par la CI
(`node-version-file`) et déclarée dans `engines`. Un seul endroit décide, donc
le poste de travail et la CI ne peuvent plus diverger en silence.

Suite Python : 3345 passent. Suite PWA : 12 passent.

### Corrigé — 03/09/2026 — Trois documents qui décrivaient un dépôt qui n'existe plus

Même faute que celle traquée partout ailleurs ici — **une valeur écrite qui
prétend être une mesure** — mais visant la prochaine session plutôt qu'un
utilisateur.

**`CLAUDE.md` annonçait « 104 modules, 77 atteints ».** Le dépôt en compte 176
et en atteint 137. L'écart s'était creusé sans que rien ne le signale : un
nombre figé dans le fichier que chaque session lit en premier ne vieillit pas
visiblement, il se lit comme l'état du jour.

`test_le_compteur_de_modules_de_CLAUDE_md_est_a_jour` relance la commande et
compare. **Il échouera à chaque module ajouté ou branché, et c'est voulu** : le
correctif tient en un nombre, le coût de l'oubli est un fichier d'accueil qui
ment.

**`docs/REPRISE.md` listait comme ouvert ce qui était fermé cette nuit.** « Une
seule panne de `/health` déconnecte l'application » est corrigé (`3f2d8be`) —
et la note dit maintenant ce que ce défaut a coûté avant d'être vu : entre
01:36 et 02:39, le propriétaire a parlé à une démo du navigateur qui se faisait
passer pour son IA, parce que cette coupure était écrite dans le `localStorage`
de son téléphone et que rien ne l'effaçait.

Deux limites y sont ajoutées, parce qu'elles se redécouvriront sinon : **les
moteurs lourds ne tournent que sur son PC** (conséquence de DEC-0022, désormais
visible avant de lancer plutôt qu'après l'échec), et **le SDK Faceplugin n'a
aucune licence** — un usage commercial demande de vérifier auprès de l'éditeur.

La note sur les tests de la PWA est corrigée aussi : ils existent maintenant,
en Python, et **ne mesurent que la structure du source TypeScript, jamais le
comportement à l'écran**. Le dire évite qu'on les prenne pour ce qu'ils ne sont
pas.

Suite complète : 3345 passent.

### Ajouté — 03/09/2026 — La mentalité d'Usman, écrite et tenue par des tests

Le propriétaire demande d'améliorer la mentalité d'Usman en y intégrant « le
raisonnement de Claude ». **Ce n'est pas possible et ça se dit** : le code et
les poids de Claude ne sont publics nulle part. Annoncer une intégration
qu'on ne peut pas faire serait exactement le défaut retiré cette nuit.

Ce qui est fait à la place est réel : les sept règles que cette plateforme a
payées pour apprendre, posées dans le prompt de base d'Usman
(`apps/backend/prompts.py`, `DISCIPLINE`).

| Règle | Le défaut qui l'a payée |
|---|---|
| 1 — dire ce qu'on n'a pas vérifié | — |
| 2 — n'annoncer aucune capacité absente | 01:36, une démo se fait passer pour son IA et promet « exécution terminal réelle » |
| 3 — rapporter un échec tel quel | un bouton « Confirmer » sous un message disant que le moteur est mort |
| 4 — « absent » ≠ « inconnu » | déjà distingué dans le code, pas dans la parole du modèle |
| 5 — ne rien boucher avec du plausible | quatre tests ont figé des valeurs fabriquées jusqu'à `main` |
| 6 — corriger en une phrase | — |
| 7 — dire ce qui a été fait | — |

**Une règle qui ne peut pas nommer sa mesure n'entre pas.** C'est ce qui
sépare une discipline d'une liste de bonnes manières, et un test le vérifie :
retirer les dates de l'en-tête fait tomber une garde.

Ce qui est mesuré, et ce qui ne l'est pas — la distinction est écrite dans le
fichier de test plutôt que supposée :

- **Mesuré** : les sept règles présentes, une seule fois, arrivant jusqu'aux
  trois chemins de réponse. La méthode d'un spécialiste vient après elles et
  ne peut rien effacer.
- **Non mesuré** : que le modèle les *suive*. Aucun modèle ne tourne en CI
  (DEC-0022). Prétendre le contraire serait la règle 2.

Un test qui vérifie qu'une instruction existe ne prouve pas qu'elle change un
comportement. Il prouve qu'elle ne peut pas disparaître en silence — et c'est
déjà ce qui manquait.

14 tests. Sabotages : retirer une règle, ne plus poser la discipline dans le
prompt, ajouter une huitième règle sans mesure, effacer les dates — chacun
fait tomber une garde. Suite complète : 3344 passent.

### Ajouté — 03/09/2026 — Analyse de visages et intelligence de design

Deux moteurs externes rejoignent ARENA. Même architecture — la seule qui existe
ici — mais **pour deux raisons opposées**, et c'est ce qui mérite d'être écrit.
Détail complet → `docs/audits/faceplugin_et_ui_ux_audit.md`.

**Faceplugin** (analyse de visages) : son dépôt ne porte **aucun fichier
`LICENSE`**. Son README affiche un badge « Open Source » et « no licensing
fees » — ni l'un ni l'autre ne concède quoi que ce soit en droit. Sans licence
explicite : tous droits réservés. Il reste donc dehors, comme Deep-Live-Cam.

**UI/UX Pro Max** (design) : **MIT**, Python pur, aucune dépendance. Rien
n'interdirait de le versionner. Il reste dehors **par convention** — une seule
règle pour tous les moteurs vaut mieux que deux selon la licence, parce que
c'est la seconde qu'on oublie d'appliquer.

**Quatre capacités de visage, et la frontière est l'identité.** Compter des
visages et placer leurs repères ne disent pas *qui* : ce sont des lectures.
Extraire un gabarit (256 dimensions) et comparer deux visages produisent de la
biométrie — ces deux-là demandent l'accord du propriétaire à chaque appel
(`biometrie_visage.biometrie: CONFIRMATION`, risque `HIGH`).

Quatre garanties tenues par la structure, pas par une intention : aucune base
de visages et rien pour en constituer une (`comparer` exige les deux images
dans le même appel) ; aucun gabarit écrit sur le disque ; `detecter` ne ramène
jamais de caractéristiques même si le moteur les a calculées dans la même
passe ; rien en arrière-plan.

**UI/UX Pro Max est en lecture seule, délibérément.** Le moteur sait persister
un design system (`--persist`) ; cette option n'est pas exposée. Une capacité
de raisonnement qui demanderait des droits d'écriture « au cas où » les
élargirait sans usage.

**Testé contre les moteurs réels**, pas seulement avec des doubles : 1 visage
détecté, 68 repères, vecteur de 256 dimensions, similarité 86,3 entre deux
photos et **100,0 d'une image contre elle-même** — le contrôle qui prouve que
le score n'est pas fabriqué. Une image sans visage rend `nombre: 0` ; comparer
deux images sans visage rend un échec **sans score**, parce qu'un 0 se lirait
« comparées, très différentes ».

Trois défauts trouvés et corrigés en chemin :

| Défaut | Ce qu'il produisait |
|---|---|
| Le pont ne trouvait pas le SDK | Python ajoute le dossier du *script*, pas le dossier courant |
| Le SDK écrit `priors nums:4420` sur la sortie standard | une mesure réussie se rapportait « sortie illisible » |
| Ruff et deux gardes descendaient dans les moteurs | 434 erreurs et 5 faux coupables venus de `sympy` |

Le pont préfixe donc sa réponse d'un marqueur, et `MOTEURS_EXTERNES` est
déclaré une seule fois (`scripts/orphelins.py`) puis réutilisé — deux listes
auraient divergé.

**`core.connectors.ponts.faceplugin_pont` n'est pas dormant** : il tourne avec
l'interpréteur *du SDK*, donc ARENA ne peut pas l'importer sans charger torch
dans son propre environnement. `LANCES_EN_SOUS_PROCESSUS` le déclare avec le
nom de son appelant, pour qu'on puisse le vérifier.

L'ancien test d'isolation de Xaar Kaname est **fondu** dans
`tests/test_moteurs_externes_restent_dehors.py` : deux fichiers mesuraient la
même règle du dépôt et pouvaient diverger. Aucune assertion perdue — le
sabotage que l'ancien attrapait fait toujours tomber une garde, et la règle
couvre maintenant les sept moteurs.

69 tests ajoutés. Suite complète : 3329 passent.

### Corrigé — 03/09/2026 — Les trois défauts vus sur son écran de 02:47

Les trois existaient indépendamment de la machine branchée. Corrigés pendant
que son PC démarrait.

**1. `â€"` était dans le fichier, pas à l'affichage.** `plan_video.py`
contenait littéralement ces caractères à la place du tiret cadratin, sur
13 lignes, et `permissions_services.yaml` sur 7 — un texte UTF-8 relu en
cp1252 puis ré-enregistré.

La réparation se fait par `encode("cp1252")`, **pas latin-1** : `€` (U+20AC)
n'existe pas en latin-1, et c'est justement lui qui compose `â€"`. Un premier
essai en latin-1 a laissé intactes exactement les lignes à réparer. Le YAML a
été vérifié : `yaml.safe_load` rend le même objet avant et après — seul le
texte a changé, jamais une décision. Garde ajoutée à `tests/test_encodage.py`.

**2. Un bouton « Confirmer » sous un message disant que le moteur est
absent.** Il en recevait deux pour une synthèse vocale, juste sous
« VoiceStudio ne répond pas sur `http://127.0.0.1:3900` ». Confirmer ne pouvait
qu'échouer, et il l'apprenait après avoir appuyé.

Une action en attente porte désormais l'état du moteur qui l'exécuterait, par
la sonde du connecteur. Moteur absent : pas de « Confirmer », la raison à la
place, et « Annuler » reste pour vider la file. **Une sonde qui échoue laisse
le bouton** — ne pas savoir mesurer n'est pas un refus, et retirer le bouton
remplacerait un faux « ça marche » par un faux « c'est cassé ».

**3. L'espace « Vidéo » rendait le routage pire que ne rien choisir.**

```
« Monte-moi un clip promo à partir de ces photos »
  sans espace       → MONTAGE          (juste)
  espace « video »  → VIDEO_ANALYSIS   (faux)
```

D'où « Aucune vidéo valide fournie pour l'analyse » sur une demande de montage
à partir de photos — **et c'est l'application elle-même qui suggérait cette
phrase.** Un espace dit une famille, pas une action : cliquer « Vidéo » ne dit
pas analyser plutôt que monter. `FAMILLE_PAR_ESPACE` laisse les mots-clés
nommer l'action *dans* la famille ; hors famille leur avis est ignoré, car
avoir cliqué « Vidéo » est une instruction. Les espaces sans famille déclarée
gardent exactement l'ancien comportement.

16 tests ajoutés. Suite complète : 3258 passent.

### Ajouté — 03/09/2026 — Le panneau vidéo dit ce que la machine branchée sait faire

**Mesuré à 02:47.** Le propriétaire, sur son téléphone branché à Railway, coche
des capacités et lance un projet. Retour : `modele de vision : All connection
attempts failed`, `VoiceStudio ne repond pas sur http://127.0.0.1:3900`. Aucun
de ces moteurs n'existe sur Railway — Ollama, VoiceStudio, WanGP,
MoneyPrinterTurbo et Deep Live Cam tournent tous sur son PC.

Le panneau proposait les sept capacités sans jamais demander lesquelles la
machine tenait, **et il n'avait aucun moyen de le demander : la route
n'existait pas.** C'est le défaut de la nuit sous une autre forme — annoncer
une capacité qu'on n'a pas. Il ne mentait pas dans une phrase, il mentait dans
un bouton.

`GET /agent/capabilities` (`core/production/disponibilite.py`) renvoie chaque
capacité à **la sonde qui la mesure déjà** — celle du connecteur, celle du
fournisseur de vision — jamais à une seconde logique qui pourrait diverger.
C'est la discipline de `scripts/doctor.py`.

Dans l'interface, ce qui ne peut pas tourner est grisé, barré, non cliquable,
**et la raison est écrite sous la liste** : un téléphone n'a pas de survol,
donc une raison en `title=` n'existe pas. Si le serveur ne répond pas à la
sonde, aucun verdict n'est affiché — ne rien savoir s'affiche comme ne rien
savoir, jamais comme « tout marche ».

7 tests. **Deux gardes ont dû être resserrées après un sabotage qui passait** :
compter les occurrences de `disponibilite: null` sans regarder dans quelle
branche laissait vider le `catch` sans qu'un test tombe. Une garde qui compte
sans regarder où ne garde rien.

`/agent/capabilities` est enregistrée dans l'empreinte de
`tests/test_surface_api.py` — qui a d'ailleurs attrapé la nouvelle route
toute seule. Sans `limiter_debit` : une lecture d'état, appelée à chaque
ouverture du panneau, ne doit pas consommer le quota des envois.

Suite complète : 3247 passent.

### Corrigé — 03/09/2026 — Xaar Kaname existait partout sauf sur l'écran d'où on le lance

Le propriétaire demande comment utiliser Deep Live Cam depuis son interface. La
chaîne était complète — modale « Projet vidéo » → `POST /api/video/projet` →
agent vidéo → connecteur → confirmation → moteur — et `xaar_kaname` **manquait
dans la seule liste qui décide de ce qu'on peut cocher**.

Le commentaire au-dessus de cette liste prévenait déjà qu'elle devait refléter
`plan_video.py:CAPACITES_VIDEO` « exactly », et redoutait la dérive inverse :
proposer une capacité que le serveur refuse. C'est l'autre sens qui s'est
produit — une capacité que rien ne permettait de choisir. **Un commentaire
n'empêche pas une dérive, il la raconte après coup.**

3 tests (`tests/test_capacites_video_pwa.py`) mesurent l'égalité des deux
listes, contenu et ordre, et exigent une icône et un libellé pour chaque
capacité — une capacité sans icône fait planter la modale au rendu.

Ce qui reste vrai et ne dépend pas de ce correctif : le moteur ne tourne que
sur le PC du propriétaire (`tools/video/xaar_kaname/`, hors du dépôt, AGPL).
Depuis Railway il n'existe pas, et `scripts/doctor.py` le dit.

### Corrigé — 03/09/2026 — La coupure de l'ancien défaut dormait encore sur son téléphone

**Mesuré à 02:19.** Le correctif de 01:36 empêchait une nouvelle coupure ; il
n'effaçait pas celle déjà écrite. Le propriétaire est revenu sur le même écran,
et la seule issue proposée était d'aller rebrancher à la main — **lui faire
réparer le défaut**.

Trois choses, et la troisième est la plus importante.

**1. La coupure subie est annulée, celle qu'il a choisie tient.** Le bouton
« Déconnecter » signe désormais sa coupure (`debrancheParLui`). Une adresse
enregistrée, débranchée *sans* cette signature, ne peut venir que de l'ancien
défaut : elle est rebranchée au démarrage, et la sonde tranche.

**2. Le message dit ce qui ne va pas.** Trois cas au lieu d'un : aucun serveur
enregistré, serveur muet, serveur muet *avec la raison mesurée*. « Rebranche-le
dans le panneau » envoyait chercher une panne sans la nommer.

**3. La phrase et le mécanisme qui la tient sont écrits ensemble.** Le message
annonce « il est réessayé tout seul ». Une veille le rend vrai : nouvelle sonde
pendant la panne, attente doublée jusqu'à une minute — assez pour rattraper vite
une panne courte, assez peu pour ne pas marteler une adresse morte sur sa
batterie. L'évènement `online` seul ne couvrait que le réseau du téléphone, et
ne disait rien d'un serveur qui redémarre.

`test_le_message_ne_promet_que_ce_qui_existe` mesure l'accord entre les deux :
si la veille disparaît, la phrase devient fausse et le test tombe. **Sans lui,
ce correctif aurait réintroduit exactement le défaut qu'il répare** — une
promesse à l'écran sans le code derrière.

6 tests de plus (24 au total). Sabotages : ne plus annuler la coupure subie, ne
plus signer la coupure volontaire, retirer la veille, retirer un des trois
messages de la liste sans préfixe — chacun fait tomber sa garde.

Suite complète : 3236 passent. `tsc`, build PWA et garde des orphelins propres.

### Supprimé — 03/09/2026 — La démo du navigateur, et tout ce qu'elle simulait

Suite du correctif du même jour. Le repli était coupé ; le code restait, et un
import d'une ligne l'aurait rebranché — c'est un import d'une ligne qui avait
produit le défaut.

**2 139 lignes retirées.** Six pipelines qui ne touchaient rien de réel
(réparation de build, recherche web, calcul, exécution de code, terminal,
conversation), le faux projet *pulseboard* et son système de fichiers en
`localStorage`, le faux index documentaire et sa version française, le faux
terminal, et les 288 lignes de prose écrite d'avance qu'ils servaient.

Avec eux partent le bouton « relancer la commande » — il aurait rejoué une
commande du **vrai** serveur contre le **faux** projet — et l'entrée
« réinitialiser l'espace de travail » des réglages et de la palette, qui
réinitialisait un dépôt qui n'existe plus.

**Ce qui reste tourne vraiment sur l'appareil** : sonder une vidéo, la couper,
lire une pièce jointe. `runAgent` n'a plus de voie par défaut : y arriver
autrement que par la vidéo lève `BACKEND_OFFLINE` au lieu de composer un texte.

| Mesure | Avant | Après |
|---|---|---|
| Paquet servi | 763 kB | **690 kB** |
| Compressé | 226 kB | **200 kB** |

4 tests de plus (18 au total). Sabotages : remettre un fichier de la démo,
remettre la phrase d'accueil, remettre une voie par défaut qui rend du texte —
chacun fait tomber sa garde. Le premier lecteur de commentaires du test
signalait son propre commentaire d'explication ; il suit maintenant les blocs
`/* */` pour de bon.

Suite complète : 3230 passent. `tsc`, build PWA et garde des orphelins propres.

### Corrigé — 03/09/2026 — Une démo du navigateur répondait à sa place, signée Usman

**Mesuré sur son téléphone, à 01:36.** Il écrit « Bonjour ». Une réponse
arrive en 2,4 s, avec une carte d'activité verte : « je suis **Usman**, un
atelier IA observable ». Elle lui propose « exécution terminal réelle » et
« une vraie arborescence projet ».

Rien de tout cela n'était vrai, et son IA n'avait pas parlé.

| Ce qui se passait | Où |
|---|---|
| Le texte est écrit en dur, aucun modèle n'intervient | `strings.ts:424` |
| Un filtre sur le mot « bonjour » le déclenche | `orchestrator.ts:608` |
| Serveur décroché → le navigateur répond à sa place | `chatStore.ts:554` |
| Une seule sonde ratée débranchait le serveur, et c'était enregistré | `backendStore.ts:84` |
| Le « projet » proposé est un faux dépôt nommé *pulseboard*, dans le `localStorage` | `vfs.ts` |
| L'état du serveur n'existait que dans le panneau backend, jamais dans la conversation | — |

C'est le défaut que ce dépôt refuse partout ailleurs — annoncer une capacité
qu'on n'a pas — au seul endroit qu'il lit vraiment.

**Ce qui change.** Un point de décision unique (`choisirTransport`) : la vidéo
reste sur l'appareil, où elle tourne pour de bon ; tout le reste passe par son
serveur, ou ne répond pas. Sans serveur, `offlineTransport` refuse et dit
pourquoi — pas de texte produit, pas de repli. Le message ne se préfixe pas de
« le moteur a renvoyé une erreur » : aucun moteur n'a répondu, et c'est
exactement ce malentendu qui faisait passer la démo pour son IA.

**Et la déconnexion qui l'y avait amené.** La sonde réessaie trois fois avant
d'abandonner, et `enabled` ne bouge plus : il dit ce que le propriétaire veut,
pas ce que le réseau permet à cet instant. Seul le bouton « Déconnecter » le
change. Quand le réseau revient, la sonde repart seule.

14 tests (`tests/test_pwa_pas_de_demo_dans_le_chat.py`), écrits en Python
faute de lanceur côté PWA. **Deux gardes ont dû être resserrées après un
sabotage qui passait** : remettre `localTransport` comme repli, et remettre
`enabled: false` dans le seul `set` du bouton « Déconnecter » — les deux
laissaient les tests verts. Un test qui vérifie qu'une pièce existe ne vérifie
pas qu'elle est branchée.

Suite complète : 3226 passent. `tsc` et le build de la PWA sont propres.

### Ajouté — 03/09/2026 — Xaar Kaname branché de bout en bout

Le connecteur du propriétaire est arrivé sur le dépôt. Il était **complet et
juste** — il lance le moteur, et surtout il vérifie que le fichier a vraiment
été écrit au lieu de croire un code de retour à 0. Ce qui manquait était
autour : de quoi l'atteindre, et de quoi savoir s'il est là.

**Trois défauts mesurés entre l'agent vidéo et le connecteur**, chacun cassé et
remis pour prouver qu'un test le tient :

| Défaut | Ce qu'il produisait | Tests qui tombent si on le remet |
|---|---|---|
| Le résultat était lu sous la clé `status` seule | un `SUCCESS` se lisait `None`, donc l'étape échouait alors qu'elle avait réussi | 2 |
| L'appel au registre n'était jamais attendu | la coroutine restait un objet, rien ne partait | 2 |
| Les chemins partaient tels quels | le moteur tourne dans **son** dossier : un chemin relatif y désigne un autre fichier, ou aucun | 1 |

Le troisième n'était mesuré par aucun test — les deux tests existants passent
des chemins déjà absolus, donc ils ne pouvaient pas le voir. Un test le mesure
maintenant.

**Le moteur avait aussi disparu du diagnostic.** WanGP, MoneyPrinterTurbo,
VoiceStudio et OpenTakeoff ont chacun leur ligne dans `scripts/doctor.py` ;
Xaar était le seul sans. Le propriétaire n'apprenait son absence qu'en lançant
une génération — après coup, et sans savoir quoi installer. La ligne existe, et
elle distingue **trois** états au lieu de deux :

- dossier absent → `NON_CONFIGURE`, avec le chemin attendu. Rien n'est cassé :
  rien n'est installé. Le dire « en panne » enverrait réparer une installation
  qui n'a jamais existé.
- dossier présent mais `.venv` ou `run.py` manquant → `EN_PANNE`. Là, une
  installation a commencé sans aller au bout.
- tout est là → `OPERATIONNEL`.

**La protection n'a pas bougé** : `video_generation.generate` reste à
`CONFIRMATION`. Mesuré en direct — un appel au connecteur rend `A_CONFIRMER`,
« Rien n'est parti », avec un identifiant à confirmer.

Le moteur reste **hors du dépôt** (AGPL-3.0), comme VoiceStudio.

13 tests ajoutés (`tests/test_connecteur_xaar_kaname.py`, `tests/test_doctor.py`,
`tests/agents/video/test_production_agent.py`). Suite complète : 3212 passent.

### Corrigé — 03/09/2026 — Un BOM en tête d'un fichier de configuration

`config/permissions_services.yaml` commençait par trois octets invisibles
(BOM UTF-8) qui faisaient tomber `test_aucun_fichier_ne_commence_par_un_bom`.
Trois octets retirés, aucune ligne de contenu touchée.

### Ajouté — 03/09/2026 — Xaar Kaname : le moteur reste dehors

Le propriétaire a intégré **Xaar Kaname** (le nom ARENA de **Deep-Live-Cam**)
sur sa machine, et demande de finir et déployer. À la date de cette entrée, le
connecteur et le moteur étaient sur son disque seul. Le connecteur est arrivé
depuis (voir l'entrée du même jour ci-dessus) ; le moteur, lui, reste dehors.

Ce qui est verrouillé ici, et qui ne dépend pas de ses fichiers :
**`tools/video/xaar_kaname/` n'entrera jamais dans git.**

Deep-Live-Cam est sous **AGPL-3.0** ; `LICENSE` d'ARENA dit « All rights
reserved », et le dépôt est **public** (DEC-0039). Faire entrer son source
ferait d'ARENA une œuvre dérivée. C'est le raisonnement déjà tenu pour
VoiceStudio (DEC-0027) : la frontière est un **processus séparé**, joint par
sa ligne de commande.

Mesuré avant la règle — le `.gitignore` d'ARENA couvrait `.venv`, mais **pas**
`models/inswapper_128.onnx` (plusieurs centaines de Mo), **pas** les rendus,
**pas** le source AGPL. Après : tout est ignoré, `git status` ne voit plus rien
sous ce dossier.

10 tests (fondus le 03/09/2026 dans `tests/test_moteurs_externes_restent_dehors.py`, qui mesure la même
règle pour les sept moteurs externes), dont celui qui mesure que
VoiceStudio, WanGP et MoneyPrinterTurbo n'ont jamais mis une ligne dans git —
la règle du dépôt est vérifiée, pas supposée. Sabotage : règle retirée,
6 tests tombent.

### Corrigé — 03/09/2026 — L'écran disait « ollama » quoi qu'il arrive

Mesuré sur le téléphone du propriétaire, pendant qu'il changeait l'adresse de
son backend. Son écran affichait **« ollama · qwen3.5:9b »**, et son backend
distant répondait `"provider": "ollama"`, `"ollama_available": true`.

Or ce backend tourne sur un hébergeur cloud, avec `GROQ_API_KEY` configurée.
Deux choses s'y ajoutaient :

- **`provider` était écrit en dur** dans `/health`. Quel que soit le moteur qui
  répond, il valait « ollama ». L'interface l'affiche tel quel
  (`backendStore.ts` : `remoteProvider: r.provider`).
- **`ollama_available` mesure l'aiguilleur, pas Ollama** : il vaut `true` dès
  qu'**un** fournisseur répond — Groq compris.

Résultat : le texte pouvait partir chez Groq pendant que le téléphone affichait
« ollama ». **Un écran qui dit « local » alors que la phrase voyage est pire
qu'un écran muet** : il donne une garantie de confidentialité que rien ne
soutient — et le propriétaire venait de demander où allaient ses données.

`RouteurDeModeles.fournisseur_en_service` rend désormais celui qui a
réellement répondu, et `None` tant que rien n'a été servi : « on ne sait pas
encore » n'est pas « local ». `/health` affiche `indetermine` dans ce cas.

Le test qui exigeait `corps["provider"] == "ollama"` **épinglait le défaut**.
Il n'est pas affaibli, il est retourné — vérifié par sabotage : en remettant
la valeur en dur, trois tests tombent.

**Signalé, non corrigé :** le nom `ollama_available` reste inexact — il veut
dire « un fournisseur répond ». Le renommer touche un contrat que l'interface
lit ; ce n'est pas le sujet de ce correctif.

### Corrigé — 02/09/2026 — Le QR code du lanceur n'avait jamais marché

Mesuré sur la machine du propriétaire, au premier démarrage de la soirée :

```
python -c "import qrcode,sys; ..."
ModuleNotFoundError: No module named 'qrcode'
```

`scripts/lancer_arena.ps1` appelle `qrcode` depuis PowerShell, par `python -c`.
Un scan d'imports Python ne voit **rien** : ce n'est pas un `import` dans un
`.py`, c'est une chaîne dans un script shell. Le paquet n'a donc jamais été
déclaré, jamais installé par `pip install -r requirements.txt`, et **le carré à
scanner n'a jamais fonctionné chez personne** depuis que le lanceur existe.

Deux moitiés, et la seconde comptait plus que la première :

- **La dépendance est déclarée** (`qrcode==8.2`, dans `requirements.txt` et
  dans le verrou). Sa seule dépendance sous Windows, `colorama`, était déjà là.
- **Le lanceur ne plante plus.** La trace Python s'affichait entre « ARENA --
  demarrage » et « Laisse les deux fenetres ouvertes » : au milieu d'un
  démarrage **réussi**, ce qui se lit comme un échec alors que le serveur et le
  tunnel tournaient tous les deux. Sans le paquet, il dit maintenant en une
  ligne que l'adresse au-dessus suffit, et comment retrouver le carré.
- La phrase « Scanne ce carre » n'est plus affichée **que s'il y a un carré** :
  l'annoncer avant de savoir, c'était promettre ce qui allait échouer.

`tests/test_lanceur.py` ferme le trou pour de bon : tout module importé par un
`python -c` du lanceur doit être déclaré, ou appartenir à la bibliothèque
standard. Vérifié par sabotage — en retirant la déclaration, deux tests tombent.

### Corrigé — 02/09/2026 — Le diagnostic se trompait de modèle

Trouvé au moment où le propriétaire allume son PC, juste avant qu'il lance la
première commande. `doctor.py` lisait `CODER_LOCAL_MODEL`, l'appelait
**« Modèle rapide »** et le déclarait **essentiel**. Le chat lit en réalité
`CHAT_LOCAL_MODEL` puis `DEFAULT_LOCAL_MODEL`
(`apps/backend/config.py` : `MODELE_RAPIDE = MODELE_CONVERSATION`).

Conséquence exacte : avec `qwen3.5:9b` installé mais pas le modèle de code, le
rapport annonçait **« ARENA NE PEUT PAS RÉPONDRE »** — alors que le chat aurait
répondu. Et le modèle de Dioumtoukay n'était vérifié **nulle part** sous son
vrai rôle : le lancer sans son modèle ne se voyait pas.

Même défaut, même correction que pour les embeddings le 27/08 : les modèles
sont désormais lus **depuis le code**, pas depuis un second jeu de valeurs par
défaut écrit dans le diagnostic. Trois lignes au lieu de deux —
**Modèle de conversation** (essentiel), **Modèle profond**, **Modèle de code
(Dioumtoukay)** — et `apps/backend/config.py` illisible donne `ABSENT` avec sa
raison, jamais un nom de modèle inventé.

### Changé — 02/09/2026 — Les chemins ne nomment plus aucune entreprise

Suite de la décision ci-dessous, et sa dernière conséquence : les fichiers
eux-mêmes portaient encore un nom de société, ce qui disait à quiconque clone
le dépôt qu'il n'est pas pour lui.

Les anciens noms sont écrits ici **sans leur dossier** : un test vérifie que
tout chemin cité par la documentation existe encore, et citer l'ancien
emplacement le ferait échouer — à juste titre.

| Avant (nom de fichier) | Après |
|---|---|
| `unic_plaquiste.yaml` | `config/metier.yaml` |
| `logo_unic_plaquiste.png` | `config/marque/logo.png` |
| dossier `unic_plaquiste` | `documents/metier/` |
| `signature_uthman.png` | `signature.png` |

**Le risque n'était pas dans le code, il était sur le disque.** `documents/`
est exclu de git : renommer un dossier ici ne renomme rien chez qui que ce
soit. Les archives et la signature manuscrite du propriétaire sont restées
dans l'ancien dossier, et une constante pointant sur le nouveau nom les aurait
rendues invisibles — sans erreur, sans message.

`agents/plaquiste/chemins.py` résout donc les chemins **à l'appel**, avec une
règle en une phrase : *l'ancien dossier est lu tant qu'il porte des documents
que le nouveau n'a pas.* Le mode d'emploi livré par git ne compte pas comme un
document — sinon la bascule masquerait les vrais. Dès qu'un fichier entre dans
le nouveau dossier, elle se fait seule.

Vérifié après renommage, sur le vrai dépôt : diagnostic `31 article(s)
tarifés`, et un devis réel de 198 000 FCFA sorti avec **2 images** (logo +
signature), aucun article sans prix. 14 tests ajoutés
(`tests/agents/test_chemins_metier.py`), dont ceux qui tiennent la bascule.

### Changé — 02/09/2026 — L'instruction générale ne porte plus aucune entreprise

Décision du propriétaire, qui **remplace** la sienne du même jour : « ce projet
est libre comme bonjour, tout le monde peut s'en servir […] rien n'est aligné à
UniC Plaquiste, que seulement le modèle UniC Plaquiste ».

Il avait d'abord demandé que sa présence en ligne soit connue partout, et elle
l'était : le site, l'application, la fiche Google Maps, TikTok et Instagram
d'UniC Plaquiste entraient dans l'instruction de **toutes** les conversations —
vidéo, documents et code compris.

- Le bloc quitte `apps/backend/prompts.py`, qui **n'importe plus rien** de
  `agents.plaquiste`. La règle devient vérifiable plutôt que déclarée, et un
  test lit les imports du module (pas son texte) pour la tenir.
- Rien n'est perdu : `composer_instruction` porte toujours les quatre adresses
  dans l'espace UniC Plaquiste.

Mesuré après le changement : instruction générale 986 caractères, **aucun** lien
UniC, le mot « plaquiste » absent ; instruction UniC Plaquiste 4766 caractères,
**4 liens sur 4**.

Mesuré aussi, en retirant `config/metier.yaml` : le chat, la vidéo, les
documents, le code et Dioumtoukay s'importent et fonctionnent sans lui, et 152
des 153 tests qui tombent sont des tests du métier. La plateforme était déjà
générale ; ce changement retire le dernier endroit où elle ne l'était pas.

### Corrigé — 02/09/2026 — Audit de la vidéo et de la voix

Demande du propriétaire : « va dans vidéo tous ce qui est là-bas verify et
améliorer […] la voix la vidéo si ça crée des vidéos bien […] corrige les
erreurs et verify bien ». Trois défauts mesurés, aucun supposé.

- **Deux tiers des sous-titres ne s'affichaient pas.** Sur « on pose le BA13
  sur les rails puis on visse tout » — 10 mots en 1 seconde, un débit d'oral
  ordinaire — 4 des 6 lignes produites avaient leur **fin avant leur début**.
  libass ne les affiche jamais et ne le signale pas. Cause : un plancher de
  0,4 s par mot appliqué **avant** de vérifier qu'il tenait dans le segment ;
  au troisième mot, le départ dépassait déjà la fin. Les mots sont répartis sur
  la durée réelle, et aucune ligne ne peut plus sortir avec une fin antérieure
  à son début.
- **La voix jetait un son valide quand `ffprobe` manquait.** `duree_ms = None`
  voulait dire deux choses — « le fichier est mauvais » et « rien n'a pu le
  mesurer » — et le connecteur ne retenait que la première : un WAV réel de 2 s
  et 176 478 octets était supprimé et rapporté en échec. La règle 2 du module
  tient toujours (l'en-tête du conteneur est vérifiée, donc une erreur JSON
  renvoyée avec un code 200 reste refusée), mais la durée non mesurée n'est
  plus annoncée.
- **`format` n'était jamais mesuré** : `ffprobe` rend `format_name` **avant**
  `duration`, et le code lisait « la dernière ligne ».
- **Le diagnostic pouvait dire ffmpeg « absent » alors qu'il est installé**, et
  conseiller de l'installer. Trois états maintenant, pas deux : absent, installé
  mais muet, ou il répond.

**Les deux outils qui font le résultat visible n'avaient aucun test** —
`SubtitleTool` et `CropTool`, les seuls de la vidéo dans ce cas. C'est ce qui a
permis au premier défaut de tenir. 14 tests ajoutés
(`tests/tools/test_sous_titres_et_recadrage.py`).

Vérifié sur un rendu réel : 1280×720 → 1080×1920 avec fond flouté, sous-titres
incrustés au style CapCut, dernier mot en jaune. La chaîne vidéo produit bien
ce qu'elle annonce.

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
