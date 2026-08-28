# ARENA — où on en est, pour reprendre sans rien redemander

Dernière mise à jour : 2026-08-27, après la mise en service de l'interface PWA
et de l'accès téléphone.

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

python scripts/mesurer_performances.py chronometre les 7 scenes. Lancee sur la
machine cloud de l assistant : 2 mesurees (recuperation 6,9 ms, outil 0,0 ms),
5 UNKNOWN - pas de Ollama, pas de recherche web. **Ces chiffres ne comptent
pas** : la specification demande la machine du proprietaire.

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

Reste a brancher, dans cet ordre suggere : les resultats de recherche web et
les reponses de GalsenAPI (memes enveloppes, niveau EXTERNAL), puis
semantique.py, consolidation.py et voies.py.

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

Decision : la generation n a PAS ete ajoutee a INTERRUPTEURS_OBLIGATOIRES. Ce
plancher du code est reserve aux trois actions irreversibles (envoyer, publier,
supprimer) ; une video generee s efface. Un test existant a refuse l ajout, et
il avait raison — le test n a pas ete modifie.

**Phase suivante autorisee : 11.1** - appels d offres senegalais. Le chapitre 8
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

**État vérifié le 2026-08-28 : 1319 passed, 0 failed** — sur la machine cloud de
l'assistant. Dernier état mesuré sur la machine du propriétaire : 1272 passed,
le 2026-08-28, avant les 14 tests du harnais de mesure.