# ARENA — où on en est, pour reprendre sans rien redemander

Dernière mise à jour : **2026-09-01**, après la nuit VoiceStudio + Agency Agents
+ deux vagues d'audit général (PR #96 à #114).

## En une phrase

**29 défauts trouvés sur une suite verte**, tous mesurés avant correction et
vérifiés par sabotage. Les deux plus coûteux : tes prix modifiés dans
`config/metier.yaml` n'étaient vus qu'après un redémarrage du serveur,
et **deux agents sur trois versaient le texte web brut dans l'invite** — une
page pouvait parler à ARENA comme si c'était toi.

**Trois** formes reviennent, et ce sont elles qu'il faut chercher en premier la
prochaine fois :

1. **Une valeur lue une fois, servie comme si elle était actuelle** — quatre
   occurrences (sonde Docker, grille de prix, deux couches de permissions).
   `core/fichier_suivi.py` existe maintenant pour ça.
2. **Une règle apprise sur un endroit, jamais portée sur les autres** —
   **sept** occurrences. Quatre entre les quatre surfaces de réponse (PWA,
   `/api/chat`, `/api/chat/stream`, passerelle OpenAI) ; une entre les deux
   connecteurs MCP ; deux entre les trois agents qui lisent le web. Quand une
   règle est trouvée quelque part, la question suivante n'est pas « est-ce
   corrigé ? » mais **« qui d'autre fait la même chose ? »**.

3. **Une garantie écrite dans le code que rien ne tenait** — trois
   occurrences : la lecture seule de `SWEAgent`, la relecture des permissions,
   et le contrôle d'identifiant du transport MCP. La question qui les trouve :
   **« cette promesse, qu'est-ce qui la tient ? »**. Une garantie qu'aucun test
   ne fixe est une garantie qui tiendra jusqu'au jour où quelqu'un la
   contredira sans le savoir.

Et une leçon sur les tests : **trois tests épinglaient les mensonges corrigés**,
dont deux écrits par moi la même nuit. Un test qui appelle la fonction corrigée
au lieu de traverser le vrai chemin passe même après qu'on a retiré le
correctif. Le sabotage est la seule chose qui le débusque.


## Ce qui a changé cette nuit (PR #96 à #101)

**ARENA parle et écoute.** VoiceStudio est piloté par HTTP en local — c'est un
programme **séparé**, sous AGPL-3.0, dont aucune ligne n'entre ici (DEC-0027,
`docs/audits/voicestudio_rapport_final.md`). Il faut le démarrer soi-même ;
sans lui, ARENA répond `NOT_CONFIGURED` et dit ce qui manque.

**ARENA monte des vidéos.** Une phrase devient un plan d'opérations validées,
puis une timeline, puis un fichier vérifié (DEC-0026, `core/montage/`). Le
modèle propose ; il ne pilote rien, et ne peut désigner aucun fichier hors des
médias déposés.

**Dix défauts corrigés sur une suite verte** —
`docs/audits/audit_general_2026-09-01.md`. Les plus coûteux : `/health` taisait
six agents dont l'assistant devis ; `/api/chat/stream` mourait en silence ; des
sous-titres s'inventaient et pouvaient finir incrustés sur une vidéo.

**Une chose trouvée et délibérément pas corrigée** : le métré refuse
« une paroi de 12 x 2,50 m » (il accepte « 1 paroi de… »). Son échec est *sûr*
— il refuse et dit quoi donner. Une extension bâclée mettrait un mauvais prix
sur un document client. **C'est une décision du propriétaire.**

**Pour démarrer VoiceStudio sur son PC :**

```
git clone https://github.com/debpalash/VoiceStudio
cd VoiceStudio && uv sync
uv run uvicorn main:app --app-dir backend --host 127.0.0.1 --port 3900
```

**`uv sync`, jamais `pip install`** : avec pip, VoiceStudio ne démarre même pas
(torchaudio trop récent) et son moteur de voix échoue. Détail mesuré →
`docs/audits/voicestudio_audit.md`, §7.


**Lire d'abord `docs/REGLES_DE_TRAVAIL.md`** : le propriétaire n'écrit pas de
code. Une commande à la fois, annoncée avec son terminal ; fichiers entiers,
jamais de plages de lignes ; tout ce qui est fini part sur `master`.

---

## En service, mesuré chez lui

**Son interface PWA a remplacé LibreChat et Open WebUI.** Elle est servie par
ARENA lui-même. Le chat répond, les pièces jointes sont lues, la mémoire et le
persona sont appliqués.

**Elle marche depuis son téléphone**, sur ses données mobiles, sans VPN, via un
tunnel Cloudflare — et le modèle tourne toujours sur son PC. Rien ne part chez
un fournisseur d'IA (`docs/DECISIONS.md`).

Comment c'est branché : **ARENA parle le protocole de son app**
(`apps/backend/routers/pwa_gateway.py`), pas l'inverse. Son `remoteTransport.ts`
n'a jamais été modifié. Même motif que `openai_gateway.py` pour LibreChat.

### Ce qu'il faut lancer pour que ça marche

Trois terminaux, dans cet ordre, PC allumé :

1. `python -m uvicorn apps.backend.main:app --port 8000`
2. `& "C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --url http://localhost:8000`
3. le sien, pour travailler

**L'adresse du tunnel change à chaque redémarrage de cloudflared**, et il faut
la remettre dans le panneau Backend de l'app. C'est la friction qui reste.

---

## Ce qui ne marche pas encore, et qui n'est pas caché

- **`connectors`** arrive dans chaque requête et n'est pas appliqué. Le panneau
  « Connecteurs 0/17 » de son interface n'a donc aucun effet. Journalisé,
  jamais ignoré en silence.
- **`apps/pwa/server/`** est dans le dépôt, **non démarré, et il ne doit pas
  l'être** : son `.env.example` porte `USMAN_AI_PROVIDER=openai` par défaut.
  Son `oauth.py` (522 lignes, Google/GitHub/Slack/Notion/LinkedIn/Salesforce)
  sera absorbé dans `core/connectors/` au chapitre 8, avec les permissions.
- **Tailscale a été essayé et abandonné** : Android n'autorise qu'un seul VPN
  à la fois, et son accès internet dépend déjà d'un autre. Ce n'est pas un
  réglage à corriger, c'est une contrainte de son appareil.
- **La page de connexion Cloudflare Access est impossible** en l'état : son
  domaine `unicplaquiste.com` est géré par Netlify. Y basculer toucherait son
  site en production — décision à prendre à froid, pas en passant.

---

## Sécurité — l'état réel

`/api/*` exige `Authorization: Bearer <USMAN_API_KEY>`. Le débit est plafonné à
10 requêtes par minute. **Depuis le tunnel, ARENA est joignable depuis
Internet** : la clé et le plafond sont ce qui le protège, plus une adresse
longue et aléatoire. Ce n'est pas une forteresse, et il le sait.

Sa clé vit dans le navigateur de son téléphone — **son choix, présenté avec ses
conséquences** (voir l'échange du 2026-08-27). Ne pas revenir dessus sans qu'il
le demande.

**Toujours dû, et lui seul peut le faire** : les 6 secrets sont encore dans
l'historique public du dépôt, et les clés ne sont pas changées. La purge est
préparée, jamais autorisée. **Cela gate le chapitre 8.**

---

## VOLET ARENA OS — 16 phases, 7 chapitres sur 12

| Phase | Ce qui existe | Commit |
|---|---|---|
| 1.1 | `core/actions/resultat.py` — 7 statuts, un `SUCCESS` **exige une preuve** | `a5fcba3` |
| 2.1 | `core/actions/journal.py` — 9 champs, secrets masqués avant écriture | `ecbf785` |
| 2.2 | `core/actions/timeline.py`, `GET /api/actions` | `700afca` |
| 3.1 | `core/permissions/politique.py` — compte × service × action × risque | `c97183a` |
| 3.2 | `core/permissions/controle.py` — 2 couches, la plus stricte gagne | `17e4a6f` |
| 4.1 | `core/connectors/base.py` — capacités, santé mesurée, quotas | `e9d1d35` |
| 4.2 | `core/connectors/registre.py` — fabriques paresseuses | `7615630` |
| 5.1 | `core/actions/attente.py` — confirmer deux fois n'exécute qu'une fois | `a9ee76f` |
| 5.2 | `/api/actions/pending`, `confirm`, `cancel`, `/api/permissions` | `bf51a71` |
| 6.1 | `core/memory/personnelle.py` — 4 mémoires, 4 natures | `91bf014` |
| 6.2 | `core/memory/recuperation.py` — 1000 souvenirs → 12,2 ms | `1a1f8e9` |
| 6.3 | `core/memory/semantique.py` - 5e signal, embeddings locaux `bge-m3`, seuil mesure 0,45 | 2026-08-27 |
| 6.4 | `core/memory/consolidation.py` - regroupement sans suppression, resume par nature | 2026-08-27 |
| 7.1 | `core/execution/voies.py` - 4 voies, budgets croissants, CHAT jamais profond | 2026-08-28 |
| 7.2 | `core/execution/mesures.py` + `scripts/mesurer_performances.py` - 7 scenes, UNKNOWN jamais remplace par un chiffre | 2026-08-28 |
| 10.1 | `core/execution/travaux.py` - file bornee, une panne de fond ne remonte jamais au chat | 2026-08-28 |

**Phase 7.2 terminee le 2026-08-28 : l instrument existe, les chiffres non.**

python scripts/mesurer_performances.py chronometre les 7 scenes. Relancee le
2026-08-29, meme machine cloud : 2 mesurees (recuperation 4,0 ms, outil
0,0 ms), 5 UNKNOWN. **Ces chiffres ne comptent pas** : la specification
demande la machine du proprietaire.

Raison des 5 UNKNOWN, precisee le 2026-08-29 (`ddgs` installe pour verifier) :
- 4 scenes modele (premier jeton, question simple, normale, complexe) :
  `ConnectError`, Ollama n existe pas sur cette machine.
- recherche web : les moteurs que `ddgs` interroge (startpage.com,
  search.brave.com) rendent `403 Forbidden` via le proxy de sortie de cette
  machine cloud - une regle du bac a sable, pas une panne reseau a reessayer.
  Ce n est donc pas seulement Ollama qui manque : la recherche web elle-meme
  n est mesurable QUE sur son PC, ou l acces internet n est pas filtre ainsi.

A FAIRE DES QUE SON PC EST RALLUME, avant toute autre phase :
    python scripts/mesurer_performances.py
puis coller le tableau ici. Tant que ce n est pas fait, les 4 scenes modele et
la recherche web restent UNKNOWN, et aucune cible de la phase 7.1 n a ete
confrontee au reel.

**Phase 10.1 terminee le 2026-08-28.** `core/execution/travaux.py` : soumettre
inscrit et rend la main, une panne de fond devient ECHOUE sans jamais remonter,
le parallelisme est borne, la progression se compte et un total inconnu vaut
None. 13 tests.

Nuance a garder en tete : le test de latence mesure un **tour de chat simule**
(une coroutine locale), pas un vrai appel au modele - Ollama n existe pas sur la
machine de l assistant. La garantie prouvee est structurelle : le chat se
termine pendant que le travail tourne encore. La latence reelle sous charge
reste a mesurer sur son PC, avec le harnais de la phase 7.2.

**Hors plan, ajoute le 2026-08-28 : le connecteur GalsenAPI.**
`core/connectors/galsen.py`, service senegal_data, lecture seule, 11 tests.
Demande par le proprietaire apres avoir vu le projet passer sur X. Voir
DEC-0006 dans docs/DECISIONS.md.

C est le PREMIER connecteur reellement operationnel : l API est publique, donc
il ne depend d aucun secret et n est pas gele par la purge. Mesure en direct le
2026-08-28 : HTTP 200, 14 regions, 46 departements, 558 communes, population
18 126 388, source RGPH-5 2023 (ANSD).

Ce qui reste a faire dessus : rien ne l appelle encore depuis le chemin de
reponse. Comme semantique.py, consolidation.py et voies.py, il existe et il est
teste, mais Usman ne s en sert pas quand le proprietaire lui parle. Le
branchement de ces quatre modules merite sa propre phase.

**Branchement commence le 2026-08-28 : la frontiere de confiance.**
`core/security/trust.py` vient de GalSen-IA (Apache-2.0, meme
proprietaire), repris tel quel : il n importe que la bibliotheque standard.
Il est BRANCHE dans `contenu_pieces()` : le texte de chaque piece jointe
entre enveloppe, avec son origine, ses balises neutralisees et les consignes
cachees relevees et transportees avec lui. 9 tests.

Ce que le prompt gagne, que le titre en prose ne donnait pas : une origine par
bloc (deux fichiers se distinguent), des balises qui ne traversent plus, et un
releve qui accompagne le texte au lieu d etre efface.

Deuxieme branchement le 2026-08-28 : les pages web lues par FreshInfoAgent
entrent au niveau EXTERNAL dans _formater_les_sources(). C est le chemin le
plus expose : le texte vient de pages que personne ne controle. La
numerotation [1] reste hors de l enveloppe, sinon les citations que le gabarit
demande cesseraient de fonctionner.

Reste a brancher : les reponses de GalsenAPI le jour ou elles entreront dans
un prompt (elles n y entrent pas encore), puis semantique.py, consolidation.py
et voies.py.

**Ce qui a ete ecarte de GalSen-IA, volontairement :**
- src/services/senegal/ : 45 departements, alors que GalsenAPI en mesure 46.
  Deux sources qui se contredisent dans le meme projet, c est pire qu une.
- src/knowledge_engine/ : recouvre LightRAG et GraphRAG deja presents.
- Le corpus wolof de 2105 phrases : excellent, mais en CC BY-SA 4.0
  (share-alike), ce qui suivrait dans ARENA. Et aucun usage aujourd hui.
- corpus/languages/aliases.yaml : a prendre, mais quand une recherche
  multilingue existera pour s en servir.

**Generation video locale : WanGP (Wan2GP), ajoute le 2026-08-28.**
`core/connectors/wan2gp.py` + `core/mcp/transport.py`, service
video_generation, 12 tests. Demande par le proprietaire.

WanGP n a PAS d API HTTP : son interface est Gradio. Il embarque en revanche un
serveur MCP, et c est par la qu ARENA passe. Le format de file --process a ete
ecarte : sa structure interne n est pas documentee, et la deviner aurait repete
l erreur deja faite sur /files.

POUR QUE CA MARCHE, sur son PC, une fois WanGP installe :
    python wgp.py --mcp --mcp-transport streamable-http --mcp-host 127.0.0.1 --mcp-port 8765
Sans cette commande, la sonde rapporte NON_CONFIGURE et donne cette ligne. Rien
n a pu etre mesure contre un vrai WanGP : la machine de l assistant n a pas de
carte graphique. Les 12 tests tournent sur un faux serveur MCP.

Ce que la politique impose : generer est une ECRITURE, en CONFIRMATION, sous le
coupe-circuit WRITE_FILES. Lire les modeles ou la galerie est libre.

Le suivi est branche : `core/connectors/suivi_video.py` interroge WanGP jusqu au
fichier, DANS la file de travaux de fond. C est le PREMIER usage reel de
core/execution/travaux.py (phase 10.1) : la conversation continue pendant que
la carte graphique travaille. La progression vient de total_tasks et
successful_tasks annonces par WanGP, jamais d une estimation ; tant qu il ne
les donne pas, le total reste None.

Decision : la generation n a PAS ete ajoutee a INTERRUPTEURS_OBLIGATOIRES. Ce
plancher du code est reserve aux trois actions irreversibles (envoyer, publier,
supprimer) ; une video generee s efface. Un test existant a refuse l ajout, et
il avait raison — le test n a pas ete modifie.

## Audit des modules orphelins — 2026-08-28

Mesure par parcours des imports depuis apps/backend/main, pwa_gateway, runtime
et l orchestrateur : 101 modules, 64 atteints, 37 orphelins.

Le pire trouve, et corrige : `agents/plaquiste/calcul_materiaux` n etait importe
QUE par scripts/mesurer_performances.py. Le proprietaire demandait un metre et
le modele inventait les quantites, alors que les ratios sortent de son devis
reel. Branche par `agents/plaquiste/metre.py` : les dimensions sont lues dans la
phrase, le calcul est fait, et les quantites entrent dans l instruction comme un
fait a ne pas recalculer. Verifie : 18 parois de 5,40 x 2,50 redonnent les 234
plaques, 288 montants et 54 rails du devis UC-2026-0804-FG2.

Le deuxieme corrige : `agents/plaquiste/devis_pdf` savait rendre le devis a la
charte de l entreprise depuis le premier jour et aucun chemin de reponse ne l
appelait. Branche par `core/connectors/devis.py` (service plaquiste, capacite
`chiffrer` en lecture et `produire` en ecriture) et par le registre passe a
PlaquisteAgent. Verifie de bout en bout : un PDF reel ecrit sur le disque,
3720 octets, dont le chemin est la preuve du succes.

Deux limites tenues par des tests, et sabotees pour le prouver :
- `produire` ne part jamais sans confirmation — le fichier part chez un client.
- le destinataire n est jamais devine dans la phrase : il vient du contexte de
  la conversation, ou le PDF n est pas lance.

Mesure apres ces deux corrections, master fusionne : 104 modules, 68 atteints,
36 orphelins.

## La video a la video, les documents aux documents — 2026-08-28

Demande du proprietaire : « que ces modeles integres soient executes et bien
installes dans chacune de leurs parties : celle qui contient pour video a la
video, celle de document au document. » Deux branchements, chacun sur l agent
que la chose concerne.

**La video.** `core/connectors/suivi_video` et `core/execution/travaux` sont
branches sur `VideoAnalyzerAgent`, et nulle part ailleurs. « Ou en est ma
video ? » n exige plus aucun fichier : l agent lit l identifiant de la derniere
generation acceptee **dans le journal des actions**, la ou le connecteur WanGP l
a depose comme preuve, ouvre le suivi dans la file de fond et rend la main. Le
tour de chat se termine avant le suivi — c est ce que le test mesure. Une
seconde question ne rouvre pas un second suivi. Sans WanGP lance, la reponse est
`NOT_CONFIGURED` avec la commande de lancement, et rien n est suivi.

**Les documents.** `tools/documents/indexer` et `tools/documents/inventory` sont
branches sur le chemin documentaire du chat (intention `RAG_DOCS`). « Indexe mes
documents » indexe ; « d apres mes documents, ... » interroge — la meme intention,
deux travaux, separes par la phrase. L indexation part dans un fil separe : sur
la boucle, elle gelerait toutes les conversations, pas seulement la sienne.
Relancee, elle ne reindexe rien qui n a pas bouge (c est l inventaire qui le
dit). Sans Ollama, elle refuse en donnant `ollama pull nomic-embed-text` et
n indexe rien a moitie. Le compte-rendu ne porte que des nombres : ces fichiers
contiennent des noms de clients et des montants.

Mesure apres ces deux branchements : 104 modules, 72 atteints, 32 orphelins.

## La memoire du chat — phase A, 2026-08-28

Deux etapes, chacune verifiee avant la suivante, comme le proprietaire l a
demande : « fais-le etape par etape, sois sur que ca marche avant de livrer ».

**A.1 — le sens.** `core/memory/semantique` est branche dans
`souvenirs_pertinents` de la passerelle PWA. Ce que ca corrige, mesure :
« combien de panneaux ai-je pris pour ce chantier ? » ne ramenait rien alors que
« 234 plaques BA13 commandees » etait en memoire — aucun mot utile en commun.
Le test `test_le_lexical_seul_ratait_ce_souvenir` garde cette preuve. L index des
vecteurs vit dans runtime.py et dure : recree a chaque question, il repaierait la
vectorisation de toute la memoire a chaque tour. `prompt_systeme` est devenue
asynchrone — les vecteurs se demandent au serveur local. Sans Ollama, la
recuperation reste MODE_LEXICAL et le journal dit pourquoi ; la passerelle rend
alors ce qu elle rendait avant. Le seuil 0.45 n a pas ete touche : il a ete
mesure avec bge-m3.

**A.2 — une chose dite une fois.** `core/memory/consolidation` regroupe ce que
la recuperation rend, juste avant la construction du prompt. Une phrase retenue
deux fois prenait deux lignes et ARENA se repetait ; elle en prend une, suivie
de « vu 2 fois ». Rien n est efface en memoire : les deux souvenirs gardent leur
date et leur source (un test le verifie apres l appel). Une supposition ne
rejoint jamais un fait, deux sources restent deux preuves, et l ordre du
classement est conserve.

Mesure apres la phase A : 104 modules, 74 atteints, 30 orphelins.

## Le cout d une reponse, et le raisonnement — phases B et E, 2026-08-28

**B.1 — les voies.** `core/execution/voies` declarait quatre regimes et leurs
budgets ; personne ne les consultait. L orchestrateur consulte desormais
`voie_pour(intention)` juste apres le classement, et la voie voyage avec la
reponse. Effet reel : ce que la memoire a le droit d ajouter au prompt vient du
budget de la voie, plus d une constante unique de 1200 caracteres identique
pour les quatorze intentions. Une intention inconnue prend la voie la moins
chere qui puisse repondre. `objectif_secondes` reste une cible : rien n est
chronometre la.

**B.2 — les mesures.** `core/execution/mesures` chronometre maintenant chaque
tour sur la passerelle, et le confronte a la cible de sa voie. Un agent
specialise passe par `chronometrer` ; un tour conversationnel est mesure du
depart au dernier jeton. Un tour interrompu n entre PAS avec les secondes
ecoulees — elles mesureraient l echec, pas la reponse : il entre INDISPONIBLE
avec sa raison. Nouvelle route `GET /api/observability` (cle + limitation de
debit) : elle rend le tableau, y compris les voies que personne n a encore
empruntees, marquees UNKNOWN, et une mediane qui vaut null quand rien n a ete
mesure. Le rapport garde les 200 derniers tours.

**E — le moteur de raisonnement.** La question de la phase E est tranchee dans
le sens du branchement, pas de la suppression — aucune suppression n a ete
decidee, elle se demande au proprietaire. Ce qu il fait de mieux que l existant :
DEEP_REASONING recevait une passe du modele rapide et un chiffre sorti de sa
tete ; il recoit maintenant un plan, un calcul REELLEMENT execute en bac a
sable, et une redaction faite a partir du resultat obtenu. Quand le bac a sable
refuse (Docker inactif), la reponse porte l avertissement : le prompt de
synthese recevait deja la phrase d erreur, mais une consigne n est pas une
garantie. `/health` annoncait « ReasoningEngine » parmi les agents actifs alors
qu aucun chemin ne l atteignait : l annonce est enfin vraie.

## Chapitre 8 — le courrier, rouvert et termine le 2026-08-28

Le chapitre etait gele pour une raison precise : on n ajoute pas de nouveaux
secrets a un depot public dont l historique fuit. Le proprietaire a passe le
depot en prive et retire les deux clients tiers qui portaient les cles mortes ;
il a rouvert le chapitre le meme jour. Deux etapes, verifiees l une apres
l autre.

**8.1 — lire.** `core/connectors/gmail.py` : `lister`, `chercher`, `lire`.
L API officielle en HTTPS avec httpx, aucune dependance ajoutee. Le jeton
d acces s obtient par echange du jeton de rafraichissement et se garde jusqu a
peu avant son expiration ; il ne voyage jamais dans un resultat.
`authentifier()` ne dit vrai que si Google a reellement rendu un jeton — trois
variables presentes ne sont pas trois variables valables. Sans identifiants :
NOT_CONFIGURED avec ce qui manque, jamais une liste vide qui se lirait « aucun
message ». Le message rendu, en-tetes compris, traverse la frontiere de
confiance au niveau EXTERNAL : un sujet se choisit aussi librement qu un corps.

**8.2 — trier, rediger, et n envoyer qu avec son accord.**
`agents/email/email_agent.py` lit cinq messages au maximum par demande, les
fait trier par le modele sous une instruction qui interdit d inventer un
chiffre ou un nom, et rend les en-tetes seulement — le corps reste dans
l invite. Pour repondre, il redige puis SOUMET l envoi : la capacite `envoyer`
du connecteur porte `action="send"`, que la politique classe en CONFIRMATION.
Le cadre met l envoi en attente avant meme d appeler l implementation, et
l agent ne connait aucun autre chemin. Le destinataire vient du contexte de la
conversation, jamais d une lecture de la phrase.

Aiguillage : nouvelle intention EMAIL, sa voie est RECHERCHE — la boite n est
pas sur la machine, et c est la seule voie qui autorise a en sortir. Un piege
evite au passage : « ecris un mail au client pour le chantier de Diamniadio »
reste chez l assistant metier, qui connait la grille de prix. Un test du
proprietaire du 27/08 le tenait deja ; les mots-cles du courrier ont ete
resserres pour ne designer que sa BOITE.

## MoneyPrinterTurbo — integre le 2026-08-28

Demande du proprietaire, capture d'ecran du depot a l'appui : « installe ce
projet et fais le executer et qu'il marche de vrai pas installer juste et le
laisser dormir, tu le mets dans le modele adapte ».

Integre comme WanGP : un service separe, clone a cote du depot, joint par son
API HTTP (DEC-0008). Le contrat n a pas ete devine, il a ete lu dans LEUR code (les chemins
cites ci-apres sont dans leur depot, pas dans le notre) : prefixe « /api/v1 »
pose dans app/controllers/v1/base.py, `POST /videos` et `GET /tasks/{task_id}`
dans leur controleur video, les etats -1 / 1 / 4 dans leur app/models/const.py,
et le jeton dans l en-tete `x-api-key`.

Le connecteur traduit l etat d une tache dans la forme que
`core/connectors/suivi_video.py` sait deja lire. C est ce qui permet de
reutiliser le suivi ecrit pour WanGP au lieu d en ecrire un second : un test
fait tourner le vrai `suivre_generation` sur une tache MoneyPrinter.

Branche sur l agent video, avec deux garanties :
- **generer est une confirmation** (`action="generate"`, CONFIRMATION dans la
  politique) : une generation occupe la carte graphique plusieurs minutes ;
- **le sujet n est jamais invente.** Il est ce qui RESTE de sa phrase une fois la
  demande retiree : « fais-moi une video sur les cloisons BA13 » laisse « les
  cloisons BA13 ». Sans sujet, on demande — on ne complete pas.

Piege evite : « fais-moi une video sur les cloisons BA13 » contient « ba13 » et
partait chez l assistant devis, qui n a jamais su faire une video. Les demandes
de fabrication sont donc testees AVANT le metier.

Bug attrape par un test au premier jet : « génère » porte un accent GRAVE sur le
second e, que `[ée]` ne couvrait pas — l extraction du sujet rendait `None` sur
la formulation la plus naturelle.

Ce qui ne peut PAS etre mesure depuis le cloud : le service lui-meme. Il exige
ffmpeg, une cle Pexels et un modele. Le connecteur est verifie contre le contrat
lu ; `scripts/doctor.py` porte la ligne « Video courte (MPT) » qui dira, chez
lui, si le service repond.

## Chapitre 9 — l agenda, termine le 2026-08-28

Ce que le proprietaire demande a un agenda, ce n est pas une grille : c est
« quand puis-je caser ce chantier ? » et « est-ce que ca tombe sur autre
chose ? ». `core/connectors/calendrier.py` repond a ces deux questions-la et
sait poser un rendez-vous, derriere confirmation.

Le calcul des creneaux libres est la vraie matiere du chapitre, et il est
teste hors ligne. Ce qu il refuse de faire :
- un evenement « journee entiere » bloque la journee entiere. Google rend
  `end.date` au lendemain ; le compter comme un point a minuit annoncerait libre
  un jour ou il est deja pris ;
- un evenement sans fin lisible bloque sa journee au lieu de ne rien prendre ;
- un evenement qu on ne sait pas lire est COMPTE (`illisibles`), jamais oublie :
  c est peut-etre lui qui remplit le jour qu on vient d annoncer libre ;
- un evenement annule ne prend rien ;
- les heures ouvrees sont declarees (8 h - 18 h, dimanche exclu), pas devinees :
  proposer 3 h du matin serait exact et inutilisable ;
- deux rendez-vous bout a bout ne sont pas un conflit.

Ecrire est une confirmation : `creer` porte `action="create"`, que la politique
classe en CONFIRMATION. Modifier et supprimer ne sont pas declares, donc
n existent pas. Une creation sans identifiant rendu est un ECHEC — un SUCCESS
sans preuve ne se construit pas.

Branchement : l assistant metier. Sa description annoncait « planning » depuis
le premier jour et il n avait acces a aucun agenda — le modele proposait des
jours au hasard. Ses creneaux reels entrent maintenant dans l instruction comme
des faits, avec la consigne de n en inventer aucun autre ; quand l agenda n est
pas lisible, l instruction lui interdit de proposer une date. Poser un
rendez-vous exige titre, debut et fin dans le CONTEXTE de la conversation,
jamais dans la phrase : une date devinee met une equipe sur la route un mauvais
jour.

Aiguillage : « suis-je libre cette semaine ? » contient « cette semaine », un
mot d actualite qui l envoyait chercher les nouvelles du monde. Les
formulations d agenda sans ambiguite sont donc testees AVANT l information
fraiche, et vont a l assistant metier — son agenda est son metier.

`core/connectors/google_oauth.py` : l echange de jeton, ecrit une fois pour les
deux services. Le courrier l utilise desormais aussi. Les noms attendus sont
`GOOGLE_*` ; les anciens `GMAIL_*` restent acceptes pour qu un `.env` deja
rempli ne cesse pas de marcher.

## Le diagnostic mentait — corrige le 2026-08-28

Question du proprietaire : « est-ce que toutes les choses integrees sur ce
projet marchent ? ». L'audit a rendu trois chiffres verifiables (ruff au vert,
1520 tests, aucun module endormi) et une liste honnete de ce qui ne peut pas
etre mesure depuis le cloud : 21 tests exigent Ollama, ffmpeg, Docker, un
reseau ou LightRAG.

Il a aussi trouve un vrai defaut, et il etait dans l'outil cense repondre a
cette question. `scripts/doctor.py`, 32 lignes, aucun test, affichait :

    print("[OK] Environnement virtuel (.venv) actif")

sans rien verifier. Lance hors du venv, il disait quand meme OK. Un diagnostic
auquel on ne peut pas se fier est plus dangereux qu'aucun diagnostic, parce
qu'on lui fait confiance pour decider si le probleme est ailleurs.

Reecrit : quinze mesures reelles — Python, venv (par `sys.prefix`, cette fois),
dependances importees une par une, cle API, Ollama et ses trois modeles, carte
graphique, ffmpeg, Docker, WanGP, les trois valeurs Gmail, le fichier de prix,
le classeur de documents. Chaque defaut porte la commande qui le repare, et un
test verifie qu'aucun n'en est depourvu. La cle API se verifie par sa longueur,
jamais par sa valeur : un diagnostic colle dans une conversation ne divulgue
rien. Ollama eteint rend `None`, pas une liste vide — « il ne repond pas » et
« il repond sans modele » sont deux phrases et deux remedes. Le code de sortie
vaut 1 quand ARENA ne peut pas repondre, ce qui le rend utilisable dans un
script.

## Mission « reveiller ce qui dort » — TERMINEE le 2026-08-28

Mesure finale : 104 modules, 77 atteints, 27 orphelins — dont 23 `__init__.py`
vides et les 4 fichiers de `apps/pwa/server/`. **Aucun module reel endormi.**
`python scripts/orphelins.py` ne nomme plus rien.

Le detail des neuf modules et de leurs preuves est dans `docs/CURRENT_TASK.md`.
**Ne pas ouvrir une nouvelle phase du plan de soi-meme** : le proprietaire donne
la suite. Deux questions attendent sa reponse — la rotation des cles, et le sort
de `apps/pwa/server/`.

**Phase suivante autorisee ensuite : 11.1** - appels d offres senegalais. Le chapitre 8
reste bloque par la purge des secrets.

Plan complet : `docs/PLAN_ARENA_OS.md`. Audit d'origine : `docs/AUDIT_ARENA_OS.md`.

---

## Ce qu'il faut savoir avant de toucher au code

- **Un `SUCCESS` sans preuve ne se construit pas** — `ResultatAction` lève.
- **Deux couches de permission**, la plus stricte gagne. Dix liens
  action → interrupteur vivent dans le code (`INTERRUPTEURS_OBLIGATOIRES`) et
  **aucune configuration ne les retire**.
- **Une action inconnue est refusée.** Seule règle qui ne se configure pas.
- **Confirmer passe par `executer_confirmee()`**, une méthode distincte — jamais
  un argument, qui voyagerait dans les `**parametres`.
- **Rien n'entre en mémoire sans source.** Une `INFERENCE` ne devient `FAIT` que
  par `confirmer()`, qui exige une source nouvelle.
- **Le contenu d'une pièce jointe est une donnée, jamais une consigne**, et son
  bloc passe en dernier dans le prompt.
- `securite.limiteur` est **un compteur de débit partagé par toute la suite** :
  un nouveau fichier de tests de routes doit le remettre à zéro dans sa fixture.
- `apps/pwa` est **exclu du lint** (`pyproject.toml`) : c'est une application à
  part. Exclusion provisoire.

## Discipline, à chaque phase

1. Lire le code avant de le changer. **Lire le protocole, ne pas le deviner** —
   `/files` a été supposé au pluriel et rendait un 422 à chaque pièce jointe.
2. Écrire le test, puis **saboter la garantie et prouver qu'un test échoue**, en
   vérifiant d'abord que la chaîne ciblée existe. Une sabotage qui ne s'applique
   pas est une preuve qui n'existe pas. Une sabotage qui ne fait rien échouer
   veut dire que le test manque, ou que le code est mort.
3. `python -m ruff check .` **et** `python -m pytest tests/ -q`, sortie réelle
   collée dans le message qui la rapporte.
4. Un commit par correctif. C'est **lui** qui commit et qui pousse.

**État vérifié le 2026-08-28 : 1320 passed, 0 failed** — sur la machine cloud de
l'assistant. Dernier état mesuré sur la machine du propriétaire : 1272 passed,
le 2026-08-28, avant les 14 tests du harnais de mesure.
---

## VOLET « ARENA en ligne, PC éteint » — phase 2.1, mesure du 30/08/2026

DEC-0021 envoie ARENA sur un serveur sans carte graphique. La question était :
que devient le routeur quand Ollama n'est pas là ?

```
python scripts/mesurer_sans_ollama.py
```

Mesure réelle — fournisseur local sur un port mort, Groq déclaré :

| Scène | Niveau | Candidats | Pourquoi |
|---|---|---|---|
| une définition | `PRIVE` | `groq, local` | PRIVE autorisé en HYBRIDE, groq d'abord |
| un rappel | `PRIVE` | `groq, local` | PRIVE autorisé en HYBRIDE, groq d'abord |
| un devis client | `SENSIBLE` | **`local` seul** | SENSIBLE reste sur sa machine en HYBRIDE |

**Le constat, en une ligne : sur le serveur, toute demande métier n'a nulle part
où aller.** Devis, prix et clients sont classés `SENSIBLE`, et le mode `HYBRIDE`
les route vers sa machine — et vers elle seule. C'est exactement ce que DEC-0021
fait monter sur le serveur, donc exactement ce qui cesserait de répondre.

Second constat, plus discret : l'échec est un `RuntimeError` nu — « Aucun
fournisseur n'a pu répondre. » Il ne distingue pas *« Ollama n'existe pas sur
cette machine »* de *« tout est tombé une minute »*. Sur le serveur, le premier
serait permanent et le message resterait le même.

Ce que la mesure ne dit pas : aucune réponse réelle n'a été obtenue ici, faute
de clé Groq sur la machine cloud. Ce qui est mesuré, c'est la **décision** du
routeur — candidats, ordre, raison — qui ne demande aucun réseau.

Rien n'est corrigé ici : la phase 2.1 mesure, la 2.2 corrigera. Et la correction
touche à la **confidentialité**, pas seulement au routage : elle demande une
décision du propriétaire, pas un patch.

## VOLET « ARENA en ligne, PC éteint » — phase 2.2, DEC-0022 du 30/08/2026

Sa décision : son PC reste `HYBRIDE`, le serveur tourne en `CLOUD_PREFERRED`.
Le réglage existait déjà (`NIVEAUX_SORTANTS`) — rien d'inventé, un choix par
machine. `.env.example` ne change pas : un dépôt cloné démarre toujours dans le
mode le plus fermé. Détail complet et ce que ça coûte si c'est faux : DEC-0022.

Construit avec la décision : `RouteurModeles._pourquoi_personne()`. Un échec
disait « Aucun fournisseur n'a pu répondre. », sans dire si c'était une
coupure passagère ou un modèle qui n'existe pas sur cette machine. Il nomme
maintenant les fournisseurs essayés et, quand c'est le classement qui a fermé
la porte (pas une panne), le mode qui l'aurait ouverte — jamais pour un secret.

## VOLET « ARENA en ligne, PC éteint » — phase 3.1, paquet déployable du 30/08/2026

`apps/backend/Dockerfile` existe depuis le tout premier commit du dépôt et
**personne ne l'avait jamais construit** — ni un humain, ni la CI, qui ne
faisait que résoudre `requirements.txt` (ce qui avait déjà attrapé pywin32
sans marqueur de plateforme, mais ne prouve pas qu'une image se construit).

Construit et lancé réellement pendant cette phase, en contournant le proxy du
bac à sable pour joindre PyPI : l'image tourne, `/health` répond authentifié
et non authentifié, et le conteneur passe `healthy` sous le `HEALTHCHECK` de
Docker lui-même — pas seulement dans le fichier.

Ce qui a été durci et ajouté :

- `USER arena` — le propriétaire ne se connecte jamais à ce conteneur, il n'a
  besoin d'aucun privilège que le processus n'a pas lui-même. Vérifié :
  `whoami` dans le conteneur rend `arena`, pas `root`.
- `HEALTHCHECK` sur `/health` — la bonne sonde pour un conteneur : elle mesure
  que le processus vit, pas que chaque service distant répond (ça, c'est le
  diagnostic applicatif, DEC-0022).
- `deploy/docker-compose.yml` — **pas à la racine** : un `docker-compose.yml`
  racine a déjà fui quatre secrets (LibreChat, Open WebUI) et un test le garde
  absent. `data/` et `media/` sont montés en volume — sans ça, reconstruire
  l'image effacerait la mémoire, la grille de prix et les devis produits
  (DEC-0021) en silence. Aucune variable n'y est fixée en dur : tout vient de
  `.env`, jamais de ce fichier versionné.
- `.github/workflows/ci.yml` — un nouveau job construit vraiment l'image à
  chaque push et chaque PR.

Prochaine phase : **3.2**, les données (SQLite) et leur sauvegarde.

## VOLET « ARENA en ligne, PC éteint » — phase 3.2, sauvegarde du 30/08/2026

`data/database/memory.db` porte **tout** : mémoire du chat, journal des
actions, tâches en attente, mémoire personnelle, entités et relations, file du
gardien — onze tables mesurées, un seul fichier. Le volume monté en phase 3.1
protège d'un rebuild du conteneur ; **rien ne protégeait d'un fichier
corrompu, d'une écriture interrompue ou d'un `rm -rf data`.**

```
python scripts/sauvegarder_donnees.py
```

Testé sur sa vraie base — pas une base de test — pendant cette phase : une
copie écrite via l'API de sauvegarde de SQLite (jamais un `cp` brut, qui
saisirait une page à moitié écrite pendant une transaction), relue et vérifiée
par `PRAGMA integrity_check` sur la copie elle-même, puis re-confirmée par une
seconde connexion indépendante — 11 tables retrouvées, intactes.

Un vrai bug trouvé par le test de rétention lui-même avant d'être corrigé :
`garder=0` supprimait la sauvegarde qui venait d'être écrite, avant même que
son chemin soit renvoyé — un succès rapporté sur un fichier qui n'existait
déjà plus. La sauvegarde qui vient d'être vérifiée est maintenant protégée de
sa propre purge ; `garder` compte le total voulu, elle incluse.

Documenté dans `deploy/docker-compose.yml` : la ligne de crontab qui déclenche
la sauvegarde depuis l'hôte via `docker compose exec`. Le résultat vit dans
`data/sauvegardes/`, sur le volume — une reconstruction du conteneur ne
l'efface pas non plus.

**Un second bug, plus grave, trouvé en testant cette ligne pour de vrai.**
`USER arena`, fixé en phase 3.1, casse le conteneur au tout premier démarrage
dès que `data/` est monté depuis l'hôte — la phase 3.1 n'avait été vérifiée
que sans volume. Un volume monté arrive `root:root` ; `USER arena` ne peut
plus rien y écrire, et `PermissionError: /app/data/rag` tue le conteneur avant
que `/health` réponde. Corrigé par `apps/backend/entrypoint.sh` : le
conteneur démarre root le temps de corriger les permissions du volume, puis
passe la main avec `gosu` — jamais `sudo`, qui permettrait un retour à root.
Reproduit avec le vrai `Dockerfile`, corrigé, puis rejoué à l'identique :
`docker exec ... ls -la /app/data` montre `arena arena`, `/health` répond. La
CI rejoue maintenant ce même scénario (volume root, écriture, `whoami`) à
chaque build — `docker build` seul ne pouvait pas voir cette panne.

**Chapitre 3 terminé.**

## VOLET « ARENA en ligne, PC éteint » — chapitre 4, phase 4.1, audit du 30/08/2026

Aujourd'hui ARENA écoute chez son propriétaire, derrière un tunnel Cloudflare
dont l'adresse est longue et change à chaque redémarrage. En ligne (DEC-0021),
l'adresse sera fixe et permanente : ce que cette phase trouve joignable
aujourd'hui, tout Internet pourra le trouver aussi.

Mesuré, pas lu : `scripts/auditer_surface_publique.py` appelle l'application
réelle (`TestClient` sur `apps.backend.main.app`) sans jamais présenter de
clé, plutôt que de faire confiance à `dependencies=[Depends(verify_api_key)]`
dans le code. Résultat, **4 défauts réels** :

- **`/media/rendered` répond sans clé.** Prouvé avec un vrai fichier : déposé
  sous un nom que `/api/upload` produirait (`…_vertical_9_16.mp4`), il est
  servi en `HTTP 200` à quiconque en devine — ou en connaît déjà — le nom.
  Rien ne protège ce mount : c'est un `StaticFiles` sans dépendance.
- **`/openapi.json`, `/docs`, `/redoc` répondent sans clé.** Le comportement
  par défaut de FastAPI ; aucune route déclarée ne les couvre.

Ce qui a été vérifié comme correct, pas seulement supposé :

- Chaque route réelle sous `/api/*` et `/v1/*` (introspection récursive de
  `app.routes`, y compris les sous-routeurs `include_router`) exige la clé —
  aucune n'a été trouvée en défaut.
- CORS n'autorise jamais `*` (`ALLOWED_ORIGINS` par défaut : `localhost`
  uniquement).
- Les pages d'interface volontairement publiques (`/`, `/health`, la page hors
  ligne, le manifeste, le service worker, `/ui/classique`, `/icons/{nom}`) le
  sont par choix, pas par oubli.

Rien n'est corrigé dans cette phase : elle mesure, la 4.2 durcit.

## VOLET « ARENA en ligne, PC éteint » — chapitre 4, phase 4.2, durcissement du 30/08/2026

Les deux défauts de la 4.1, fermés :

- **`/media/rendered` exige désormais la clé.** Le mount `StaticFiles` est
  remplacé par une route (`servir_media_rendu`) qui appelle
  `validate_media_path` puis `verify_media_access` — une variante de
  `verify_api_key` qui accepte aussi la clé en paramètre `?cle=`, parce qu'un
  `<video src="...">` ne peut poser aucun en-tête `Authorization` ; c'est le
  navigateur qui charge l'URL, pas du JavaScript. L'interface classique
  (`apps/frontend/index.html`) est mise à jour pour l'y ajouter — la lecture
  vidéo existante n'est pas cassée par ce durcissement.
- **La documentation FastAPI est fermée par défaut.** `docs_actives()`
  (`apps/backend/config.py`) ne s'ouvre que si `.env` porte
  `APP_ENV=development` ; sans cette variable — l'oubli le plus probable — le
  serveur reste fermé. `.env.example` est mis à jour à `APP_ENV=production`
  pour qu'un nouveau clone parte fermé, pas ouvert.

`scripts/auditer_surface_publique.py` ne trouve plus aucun défaut :
`tests/test_auditer_surface_publique.py` verrouille ce zéro, et
`tests/test_surface_api.py` (l'empreinte de toute la surface HTTP) connaît la
nouvelle route et sa dépendance.

Chapitre 4 terminé.

## VOLET « ARENA en ligne, PC éteint » — chapitre 5, premier déploiement réel du 30/08/2026

Serveur choisi : **Railway** (Docker direct, domaine HTTPS fixe, volumes
persistants, pas de GPU nécessaire — cohérent avec DEC-0022 : ce serveur ne
fait jamais tourner Ollama, seul le PC du propriétaire le fait).

Premier déploiement réel, trouvé et corrigé sur le vif :

- **L'interface servie n'était pas la PWA.** `apps/backend/Dockerfile` ne
  construisait jamais `apps/pwa/dist/` — gitignoré par construction (Vite le
  régénère), il n'existe donc jamais dans une image construite depuis un
  clone frais. `interface_servie()` (`apps/backend/main.py`) retombait alors
  silencieusement sur l'ancienne interface classique, sans qu'aucun test ne
  le voie (les tests tournent sur le dépôt, où `dist/` peut déjà exister
  localement). Corrigé par une étape de construction (`node:20-slim`) ajoutée
  au Dockerfile, dont le résultat est copié dans l'image finale.
  Vérifié réellement : image construite et lancée, `GET /` renvoie
  `"interface":"pwa"` dans `/health` et le HTML de la PWA (thème sombre,
  `theme-color: #0a0a0b`), pas celui de l'interface classique.
- `.dockerignore` exclut désormais `apps/pwa/node_modules` et `apps/pwa/dist`
  du contexte : reconstruits par l'image à chaque fois, ceux du poste de
  travail ne servent à rien et alourdissaient l'envoi pour rien.

Variables de service posées sur Railway : `USMAN_API_KEY` (propre au
serveur, différente de celle du PC), `APP_ENV=production`,
`AI_MODE=CLOUD_PREFERRED` (DEC-0022 : réglage du serveur, pas celui du PC),
`GROQ_API_KEY` (réutilisée depuis le `.env` du PC), `USMAN_ALLOWED_ORIGINS`
pointée sur le domaine Railway généré.

Point non résolu, sans gravité : `/health` rapporte `"ollama_available":true`
sur Railway alors qu'aucun Ollama n'y tourne — ce champ ne sert qu'au
diagnostic secondaire, pas au routage réel (DEC-0022), et n'affecte donc rien
de fonctionnel. À creuser si l'occasion se présente.

**Panne réelle après ce déploiement : le serveur ne répondait plus du tout**
(502, en boucle). `apps/backend/entrypoint.sh` plantait :

```
chown: cannot access '/app/data': No such file or directory
```

`data/` est exclu de l'image par `.dockerignore` (monté en volume, jamais
copié) — et Railway ne monte aucun volume par défaut, contrairement à
`deploy/docker-compose.yml`. Le dossier n'existait donc nulle part. Corrigé
par un `mkdir -p /app/data /app/media` avant le `chown` : correct que le
volume existe ou non. Vérifié réellement, les deux cas rejoués : sans volume
(le cas Railway), et avec un volume root:root (le cas docker-compose.yml).
La CI rejoue maintenant le premier cas à chaque build, pas seulement le
second.

**Aucun volume Railway n'était configuré** au moment de ce chapitre :
`/app/data` était donc éphémère à chaque redéploiement — la mémoire et les
devis n'y survivaient pas, alors que DEC-0021 l'exige. **Réglé le 30/08/2026**,
voir *VOLET « Mêmes conversations sur tous ses appareils », phase 1* plus bas :
volume monté sur `/app/data`, persistance vérifiée après redéploiement.

**Chapitre 5 terminé, confirmé par le propriétaire depuis son téléphone** :
l'interface PWA répond, authentifiée, sur l'adresse Railway. Le VOLET
« ARENA en ligne, PC éteint » est fonctionnel — ARENA est joignable sans que
son PC soit allumé. Le volume persistant, seul point resté ouvert à la clôture
de ce chapitre, a été posé le 30/08/2026 (voir plus bas).

---

## Suite du 30/08/2026 — ce qui a été trouvé une fois le serveur en ligne

Le VOLET précédent s'arrêtait à « ARENA répond depuis le téléphone ». La suite
est ce que l'usage réel a révélé, dans l'ordre où le propriétaire l'a rencontré.
Chaque point a été **mesuré sur le serveur en ligne**, jamais déduit.

### La clé d'API refusée trois fois — et ce n'était pas la clé

Trois clés successives, toutes rejetées par `/health`. Deux hypothèses fausses
avant la bonne :

1. des caractères spéciaux abîmés par un copier-coller mobile — faux ;
2. une espace ou un retour à la ligne en fin de valeur — **vrai mais pas la
   cause** ici. `reglage()` ne faisait aucun `.strip()`, ce qui est un défaut
   réel : corrigé et testé (PR #52), mais l'erreur a persisté après.

La cause a été trouvée par la **Console Railway**, en interrogeant le conteneur
vivant plutôt qu'en supposant :

```
python3 -c "import os; print(repr(os.environ.get('USMAN_API_KEY')))"  ->  None
printenv | grep -i usman                                             ->  USMAN API KEY=...
```

Le **nom** de la variable portait des espaces au lieu de tirets bas. La valeur
était correcte depuis le début. Variable supprimée puis recréée sous le bon nom.

*Leçon retenue : la Console Railway répond en une commande à une question qui a
coûté une heure de suppositions. À utiliser dès le deuxième échec inexpliqué.*

### La recherche web ne cherchait pas — trois défauts empilés

Le propriétaire : « il répond mais il ne fait pas de recherche ». Trois causes
distinctes, trouvées l'une après l'autre, chacune masquée par la précédente.

| # | Cause | Correctif |
|---|---|---|
| 1 | `FreshInfoAgent` bornait la recherche à 6 s alors que `search(recent=True)` enchaîne jusqu'à cinq appels réseau et s'accorde 25 s | délai porté à 30 s (PR #53) |
| 2 | La passe `text` + `timelimit="w"` ne cherchait plus la question — seulement le mot « qui » (*Quizlet*, *Merriam-Webster*) — et prenait les 5 places, si bien que la passe qui répond n'était jamais lancée | passe supprimée ; le filtre de fraîcheur ne s'applique plus qu'à `news` (PR #54) |
| 3 | Le mot **« secret »**, lu dans la page Wikipédia (« élu au scrutin secret »), classait la demande `TRES_SENSIBLE` → cloud interdit → et sans Ollama sur Railway, plus aucun fournisseur | un nom de champ n'est un secret que **suivi de sa valeur** (PR #55) |

Le troisième mérite d'être retenu : `FRAGMENTS_SECRETS` vient de
`core/actions/journal.py`, où `masquer()` lit ces chaînes comme des **noms de
champ**. Les chercher comme sous-chaînes dans de la prose téléchargée confond un
secret avec un mot ordinaire. Rien n'a été affaibli : les regex de clés, les
formulations françaises (mot de passe, IBAN, CVV) et les formes possessives
classent toujours `TRES_SENSIBLE`, et les neuf tests de sécurité existants
passent sans avoir été touchés.

Vérifié en direct après déploiement : « qui est le président du Sénégal » →
*« Bassirou Diomaye Faye, depuis son investiture le 2 avril 2024 »*, trois
sources Wikipédia à l'appui.

### L'écran noir de la PWA

Une réponse de recherche rendait l'écran **entièrement noir**, et rouvrir la
conversation le renoircissait — elle est enregistrée.

Le serveur décrit une source par son **adresse** et n'envoie jamais de
`domain` ; `SourceMeta` le déclarait obligatoire et `DomainMark` lisait
`domain.length`. Une exception pendant le rendu démonte tout l'arbre React — et
**il n'existait aucun `ErrorBoundary` dans toute l'application**, ce qui est le
vrai défaut : n'importe quelle erreur d'affichage effaçait l'écran.

Corrigé (PR #56) : domaine déduit de l'adresse aux deux frontières (flux SSE et
`localStorage`, pour réparer aussi l'existant), `DomainMark` tolérant, et un
`ErrorBoundary` autour de chaque message. Reproduit puis vérifié avec Playwright
sur le paquet construit ; la garde a été **sabotée-vérifiée** — encadré
d'erreur au lieu de l'écran noir.

*Déclarer un champ obligatoire ne le rend pas présent : ça cache le trou
jusqu'à ce que le rendu le trouve.*

## VOLET « Mêmes conversations sur tous ses appareils » — terminé le 30/08/2026

Le propriétaire : les conversations de son PC n'apparaissaient pas sur son
téléphone. Ce n'était pas une panne : elles vivaient dans le `localStorage` de
chaque navigateur, donc nulle part en commun.

**Phase 1 — le disque persistant.** Le point laissé ouvert au chapitre 5 est
fermé. Volume Railway monté sur `/app/data` (0,5 Go, disponible sur le forfait
d'essai). Il ne se crée pas depuis *Settings* mais depuis le **canevas du
projet** (`+ Add` → *Volume*), et il faut **redéployer à la main** ensuite.
Persistance prouvée, pas supposée : après redéploiement dans un conteneur neuf
(`fa8bc69abbbd` → `372911692e56`), un fichier daté écrit avant se relisait
inchangé, et `df` montre `/dev/zd7376 … /app/data` comme système de fichiers
distinct. La mémoire, le journal et les approbations y survivent désormais —
DEC-0021 est enfin satisfaite.

**Phase 2 — le coffre côté serveur** (`core/conversations/depot.py`, PR #57).
Deux décisions, avec ce qu'elles coûtent si elles sont fausses :

- *La conversation est stockée entière, en JSON, jamais découpée en colonnes.*
  Le serveur est un coffre, pas un modèle : la forme appartient à l'interface,
  qui la fait évoluer souvent. La découper obligerait à migrer la base à chaque
  changement d'écran et perdrait en silence les champs inconnus du serveur.
  Coût si c'est faux : aucune requête champ par champ côté serveur — dont rien
  n'a besoin aujourd'hui.
- *La plus récente gagne*, arbitrée sur le `updatedAt` du client. Un seul
  propriétaire, deux appareils jamais utilisés en même temps. Coût si c'est
  faux : une modification faite sur un appareil endormi perd contre une plus
  récente ailleurs.

Une suppression pose une **pierre tombale** au lieu d'effacer la ligne : sans
elle, l'appareil absent au moment de la suppression renvoie la conversation et
elle ressuscite à chaque synchronisation.

**Phase 3 — le client** (`apps/pwa/src/lib/sync/`, PR #58). Synchronisation au
démarrage, à la fin de chaque tour et après une suppression. Trois règles de
sûreté qui disent toutes la même chose — **synchroniser ne doit jamais coûter
une conversation** : une panne réseau ne change rien localement ; une
conversation locale absente de la réponse est **gardée**, seule une pierre
tombale efface ; un serveur trop ancien fait taire la synchronisation au lieu
d'échouer à chaque message.

Renommer et épingler datent désormais la conversation : l'arbitrage se fait sur
cette date, et un renommage non daté perdrait silencieusement contre la copie de
l'autre appareil.

Vérifié en direct sur le serveur après déploiement : dépôt (`ecrites: 1`),
relecture entière, puis pierre tombale (`total: 0`) — la trace de test effacée.
Côté interface, vérifié avec Playwright sur le paquet construit : une
conversation « écrite sur le PC » arrive, s'enregistre et s'affiche ; serveur
injoignable, rien n'est perdu ; suppression par l'interface, la pierre tombale
part bien.

### Ce qui reste ouvert

- ~~**La CI ne peut pas passer au vert**~~ — **plus vrai, mesuré le
  03/09/2026.** Le dépôt est public depuis DEC-0039, et les exécutions publiques
  ne consomment pas le budget : la CI tourne et passe au vert (`3a1f798`,
  `2535f91`, le 03/09/2026). Ce point restait écrit ici depuis la PR #43 et
  aurait fait renoncer à regarder la CI sans la consulter. **Un rouge sur
  `master` est donc de nouveau un vrai rouge**, à traiter comme tel — c'était le
  cas le 03/09/2026 après le merge de la PR #152, corrigé depuis.
  Ce qui reste vrai : l'historique contient les six valeurs de secrets décrites
  dans `documents/RUNBOOK_PURGE_SECRETS.md`, et cette purge reste à faire.
- ~~**`apps/pwa` n'a aucun lanceur de tests**~~ — **fait le 03/09/2026.**
  `npm test` (vitest + jsdom) tourne, et la CI l'exécute avec le typecheck et
  le build (`apps/pwa` est un job à part).
  12 tests couvrent ce qui a réellement fait mal cette nuit : `choisirTransport`
  ne rend jamais la voie sur appareil sans serveur, `offlineTransport` ne
  produit **aucun** jeton et distingue « aucun serveur enregistré » de
  « serveur muet », une coupure non signée revient branchée au démarrage, une
  coupure signée tient, et un échec de sonde **ne débranche pas**.
  Ce qu'ils apportent par rapport aux tests Python qui lisaient le source : ils
  **exécutent** le code. Les trois sabotages correspondants font tomber une
  garde chacun — ce que les tests de lecture, eux, ne voyaient pas toujours.
  Ce qui reste non couvert : le rendu à l'écran. Aucun composant React n'est
  monté ici, et Playwright reste manuel.
- ~~**Une seule panne de `/health` déconnecte l'application**~~ — **corrigé le
  03/09/2026** (`3f2d8be`). La sonde réessaie trois fois avant d'abandonner,
  `enabled` ne bouge plus (il dit ce que le propriétaire veut, pas ce que le
  réseau permet — seul le bouton « Déconnecter » le change, et il signe sa
  coupure), et une veille re-sonde pendant la panne, l'attente doublant jusqu'à
  une minute.
  Ce que ça a coûté avant d'être vu : le 03/09/2026 entre 01:36 et 02:39, le
  propriétaire a parlé à une **démo du navigateur** qui se faisait passer pour
  son IA, parce que cette coupure-là était écrite dans le `localStorage` de son
  téléphone et que rien ne l'effaçait. La démo est supprimée (`c9a6838`).
- **La fusion est par conversation, pas par message.** Modifier le même fil sur
  les deux appareils hors ligne garde le plus récent en entier.
- **Les moteurs lourds ne tournent que sur son PC.** Ollama, VoiceStudio,
  WanGP, MoneyPrinterTurbo, Deep-Live-Cam et le SDK Faceplugin sont absents de
  Railway, qui n'a pas de carte graphique. Branché là-bas, seul le chat
  répond (Groq) — et depuis le 03/09/2026 le panneau vidéo le **dit** au lieu
  de proposer sept capacités dont six échoueront (`GET /agent/capabilities`).
  Ce n'est pas un défaut à corriger : c'est la conséquence de DEC-0022, et
  elle est maintenant visible avant de lancer plutôt qu'après l'échec.
- **Le SDK Faceplugin n'a aucune licence.** Aucun fichier `LICENSE` dans son
  dépôt — un badge « Open Source » dans son README ne concède rien en droit.
  Il reste hors du dépôt, et **un usage commercial demande de vérifier auprès
  de l'éditeur** avant toute distribution.
