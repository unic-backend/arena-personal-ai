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

## VOLET ARENA OS — 14 phases, 6 chapitres sur 12

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

**Phase suivante autorisée : 7.2** - mesures : premier jeton, question simple,
normale, complexe, récupération, recherche, outil. Les chiffres se mesurent sur
sa machine, sinon ils restent UNKNOWN.

**Prérequis mesuré le 2026-08-27** : la récupération sémantique exige
ollama pull bge-m3. Sans lui, elle rapporte LEXICAL - SERVEUR_ABSENT et ne
simule rien. nomic-embed-text a été mesuré puis écarté : il classait un
souvenir sans rapport devant le bon (0,596 contre 0,457).

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

**État vérifié sur sa machine le 2026-08-27 : 1272 passed, 0 failed.**