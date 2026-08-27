# ARENA — où on en est, pour reprendre sans rien redemander

Écrit le 2026-08-27 à la demande du propriétaire (« on prend pause ici »).
Ce fichier est la mémoire de session : il dit ce qui est fait, ce qui est en
attente, et ce qui est bloqué. Le plan complet est dans `docs/PLAN_ARENA_OS.md`,
l'audit qui l'a produit dans `docs/AUDIT_ARENA_OS.md`.

---

## En cours

**Rien.** Le VOLET ARENA OS est en pause après la phase 6.2.

### L'interface PWA est branchée et elle répond — mesuré le 2026-08-27

Son application React est l'interface d'ARENA. Mesuré chez lui, bout en bout :
panneau Backend `ARENA · 317 ms`, `ollama · qwen2.5-coder:14b`, et une vraie
réponse du modèle local dans le chat. **LibreChat et Open WebUI ne servent
plus.**

Comment c'est branché : ARENA parle le protocole de son app
(`apps/backend/routers/pwa_gateway.py`), plutôt que l'inverse. Son
`remoteTransport.ts` n'a pas été touché. Même motif que `openai_gateway.py`
pour LibreChat.

**Ce qui n'est PAS encore fait, et ne doit pas être oublié :**

- `persona`, `memories`, `connectors` et `attachments` arrivent dans chaque
  requête et **ne sont pas appliqués**. Ils sont journalisés nommément. Les
  réglages correspondants de son interface n'ont donc aucun effet — à traiter,
  ou à masquer dans l'interface.
- `POST /files` répond `501` : aucune chaîne ne lit les pièces jointes.
- `apps/pwa/server/` est dans le dépôt, **non démarré, et il ne doit pas
  l'être** (voir `docs/DECISIONS.md`). Son `oauth.py` sera absorbé au chapitre 8.
- La PWA installable (manifeste, service worker, icônes) est servie mais
  **l'installation n'a pas été essayée**.

**Phase suivante autorisée : 6.3** — récupération sémantique, embeddings locaux.
Elle dépend d'`ollama serve`. Si la mesure est impossible, elle doit être
rapportée `BLOCKED`, pas contournée.

**Nouvelle demande du propriétaire, non commencée** : intégrer sa PWA comme
interface unique d'ARENA, et se passer de LibreChat et d'Open WebUI. Le code de
la PWA existe déjà chez lui. Voir *La PWA* plus bas.

---

## Terminé — 8 phases, 5 chapitres sur 12

| Phase | Ce qui existe maintenant | Commit |
|---|---|---|
| 1.1 | `core/actions/resultat.py` — 7 statuts. Un `SUCCESS` **exige une preuve** ; une action sans effet ne peut pas en porter. | `a5fcba3` |
| 2.1 | `core/actions/journal.py` — les 9 champs. Secrets masqués **avant** écriture. | `ecbf785` |
| 2.2 | Journal branché sur le chemin réel, `core/actions/timeline.py`, `GET /api/actions`. | `700afca` |
| 3.1 | `core/permissions/politique.py` + `config/permissions_services.yaml` — compte × service × action × risque. Action inconnue = **refusée**. | `c97183a` |
| 3.2 | `core/permissions/controle.py` — 2 couches, la plus stricte gagne. 10 actions rattachées aux coupe-circuits. `PERM_*` morts retirés. | `17e4a6f` |
| 4.1 | `core/connectors/base.py` — capacités, santé **mesurée**, permissions, quotas, journal, erreurs. | `e9d1d35` |
| 4.2 | `core/connectors/registre.py` — fabriques paresseuses, un connecteur cassé se dégrade seul. TikTok migré. | `7615630` |
| 5.1 | `core/actions/attente.py` — déposer n'exécute rien, confirmer deux fois n'exécute qu'une fois. | `a9ee76f` |
| 5.2 | `/api/actions/pending`, `confirm`, `cancel`, `/api/permissions`. | `bf51a71` |
| 6.1 | `core/memory/personnelle.py` — 4 mémoires, 4 natures, entités et relations. | `91bf014` |
| 6.2 | `core/memory/recuperation.py` — 4 signaux, budget dur. **1000 souvenirs → 12,2 ms.** | `1a1f8e9` |

**État vérifié le 2026-08-27** : `ruff` → *All checks passed!* ·
`pytest tests/ -q` → **1106 passed, 21 deselected, 0 failed**.

---

## Ce qu'il faut savoir avant de toucher au code

- **Un `SUCCESS` sans preuve ne se construit pas.** `ResultatAction` lève. Ce
  n'est pas une convention, c'est un `ValueError`.
- **Deux couches de permission**, et la plus stricte gagne toujours. Les neuf
  booléens de `config/permissions.yaml` sont des **coupe-circuits généraux** ;
  dix liens action → interrupteur vivent dans le code
  (`INTERRUPTEURS_OBLIGATOIRES`) et **aucune configuration ne les retire**.
- **Une action inconnue est refusée.** Seule règle qui ne se configure pas.
- **Confirmer passe par `executer_confirmee()`**, une méthode distincte — jamais
  un argument `confirmation=True`, qui voyagerait dans les `**parametres`.
- **Rien n'entre en mémoire sans source.** Souvenirs, entités *et* relations.
- **Une `INFERENCE` ne devient `FAIT` que par `confirmer()`**, qui exige une
  source nouvelle.
- `securite.limiteur` est **un compteur de débit partagé par toute la suite** :
  un nouveau fichier de tests de routes doit le remettre à zéro dans sa fixture,
  sinon il passe seul et échoue en 429 dans la suite complète.

## Discipline appliquée à chaque phase

1. Lire le code avant de le changer.
2. Écrire le test, puis **saboter la garantie et prouver qu'un test échoue** —
   en vérifiant d'abord que la chaîne ciblée existe : une sabotage qui ne
   s'applique pas est une preuve qui n'existe pas.
3. `python -m ruff check .` **et** `python -m pytest tests/ -q`, sortie réelle
   collée dans le message qui la rapporte.
4. Un commit par phase, message en français, poussé sur `master`.
5. S'arrêter, rapporter, attendre « continue ».

---

## La PWA — demande du 2026-08-27, non commencée

Le propriétaire a construit une application PWA et veut qu'elle devienne
**l'interface unique** d'ARENA, en remplacement de LibreChat et d'Open WebUI.

Ce que le dépôt offre déjà comme point d'accrochage :
- `apps/backend/main.py` sert `apps/frontend/index.html` sur `/` et monte
  `/static` sur `apps/frontend/vendor/`.
- `POST /api/chat` et `POST /api/chat/stream` (SSE) existent et fonctionnent.
- CORS : `ALLOWED_ORIGINS`, jamais `*`.

**Décision en attente du propriétaire, elle change l'implémentation :**
la PWA a-t-elle une étape de compilation (React, Vue, Vite, Next) ou est-ce
du HTML/JS servi tel quel ?

**Point de sécurité à trancher avec lui, et il n'est pas optionnel :**
`/api/chat` exige `Authorization: Bearer USMAN_API_KEY`. Une PWA qui tourne
dans un navigateur **ne peut pas garder ce secret**. Trois issues possibles,
à lui présenter avant d'écrire une ligne — ne pas choisir à sa place, et
surtout ne pas retirer l'authentification pour que ça marche.

---

## Bloqué — gestes du propriétaire, rien de faisable ici

- **Les 6 secrets sont toujours dans l'historique public** et les clés ne sont
  pas changées. La purge est préparée, jamais autorisée. Cela **gate le
  chapitre 8** (connecteur e-mail réel).
- `ollama serve` ne tourne pas dans cet environnement : pas de GPU, pas de
  modèle. Les mesures de latence du §25 doivent être faites sur sa machine.
- Gmail, Agenda, Search Console, TikTok : aucun identifiant OAuth. Les
  connecteurs se déclarent `NOT_CONFIGURED` et c'est la règle qui fonctionne,
  pas un défaut.
