# Connecter Usman à ton IA

L'interface Usman ne parle à **rien en dur** : elle consomme un flux
d'événements via un contrat `AgentTransport`. Trois étapes suffisent.

---

## 1 · Configurer le vrai modèle

```bash
cd server
cp .env.example .env
```

Dans `.env`, choisis un fournisseur, un modèle et sa clé. Les clés restent
exclusivement côté serveur.

| Fournisseur | `USMAN_AI_PROVIDER` | Variable de clé |
| --- | --- | --- |
| OpenAI | `openai` | `OPENAI_API_KEY` |
| OpenRouter | `openrouter` | `OPENROUTER_API_KEY` |
| Groq | `groq` | `GROQ_API_KEY` |
| Mistral | `mistral` | `MISTRAL_API_KEY` |
| Anthropic | `anthropic` | `ANTHROPIC_API_KEY` |
| Google Gemini | `gemini` | `GEMINI_API_KEY` |
| Ollama local | `ollama` | aucune clé requise |

Exemple Ollama :

```env
USMAN_AI_PROVIDER=ollama
USMAN_AI_MODEL=qwen3
USMAN_AI_BASE_URL=http://localhost:11434
```

## 2 · Lancer le backend

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8787
```

`GET /health` fait un vrai appel non facturable à l’API du fournisseur
(`/models`, modèle Gemini, ou `/api/tags` pour Ollama). Le panneau ne passe
au vert que si le fournisseur répond réellement.

## 3 · Connecter l'interface

Barre latérale → panneau **BACKEND** →
coller `http://localhost:8787` → **Tester & connecter**.

Le point devient vert avec la latence mesurée. À partir de là,
chaque message part en `POST /agent/stream` vers **ton** serveur ;
le runtime local reste le repli (et traite toujours les vidéos
sur l'appareil — les URLs blob ne sont pas transférables).

> En production : active HTTPS, ajoute `USMAN_BACKEND_TOKEN` côté serveur
> puis la même valeur dans le champ « jeton d’accès du backend »
> (envoyée en `Authorization: Bearer …`), et restreins le CORS côté serveur.

Les adaptateurs réels sont dans `server/providers.py`. Ils lisent directement
les flux SSE/NDJSON officiels et ne transmettent que les deltas de réponse
publique. Les champs de raisonnement privé (`thinking_delta`, `thinking`)
sont volontairement ignorés. Le frontend affiche donc le texte **au fil des
deltas réels**, sans délai artificiel.

## Pièces jointes

Le trombone accepte jusqu’à 5 fichiers de 25 MB chacun :

- images JPEG, PNG, WebP et autres formats décodables ;
- PDF avec extraction réelle du texte et du nombre de pages ;
- DOCX, TXT, Markdown, CSV, JSON, XML, HTML, YAML et fichiers de code ;
- audio et vidéo, avec métadonnées du conteneur.

Le navigateur valide d’abord le format et crée les aperçus. Pour une IA
distante, chaque fichier passe ensuite par `POST /files`. Le serveur vérifie
le type, extrait le contenu dans un répertoire temporaire privé, renvoie un
identifiant aléatoire puis purge le fichier après `USMAN_FILE_TTL_SECONDS`.
Le nom fourni par l’utilisateur n’est jamais utilisé comme chemin disque.

Les documents extraits sont placés dans le contexte avec des balises
`<attachment>`. Les images sont envoyées sous le format vision natif de
chaque fournisseur. Gemini reçoit aussi l’audio en `inline_data`; OpenAI
reçoit WAV/MP3 via `input_audio` si le modèle sélectionné le supporte.
Anthropic, Ollama et les modèles sans capacité audio ne reçoivent que les
métadonnées : Usman ne prétend donc jamais avoir écouté un fichier qu’un
modèle ne peut pas décoder.

Le traitement vidéo avancé (vignettes et découpe) reste local afin d’éviter
un upload massif et de préserver la confidentialité.

## Instructions personnelles & Persona

Chaque requête transmet les préférences utilisateur configurées dans l’interface :
- `persona.user_name` & `persona.user_role`
- `persona.tone` (`balanced`, `concise`, `expert`, `pedagogical`)
- `persona.format` (`standard`, `code_first`, `bullet_heavy`)
- `persona.instructions` : directives textuelles libres

Le backend injecte ces directives directement dans le prompt système du modèle sans
écraser les garde-fous de sécurité.

## Mémoire personnelle transparente

Chaque requête transmet la liste des souvenirs et faits actifs :
- `memories: [{ "id": "mem_1", "category": "preference", "content": "..." }]`
- Le serveur émet un événement observable d’activité (`tool: "memory_vault"`, `kind: "database"`)
  pour que l’utilisateur voie exactement quand ses souvenirs sont rappelés.
- Les faits sont injectés de manière structurée dans le contexte système `[Usman Active Long-Term Memories]`.

---

## Le contrat du flux (SSE)

Une trame SSE par événement, JSON dans `data:` :

```
data: {"type":"activity","event":{ … }}
data: {"type":"token","text":"…"}
data: {"type":"done","meta":{"sources":[…]}}
data: {"type":"error","message":"…"}
```

### Reprise automatique après coupure

Usman attribue un `run_id` stable à chaque requête et le transmet aussi dans
`X-Usman-Run-ID`. Le backend conserve jusqu’à 2 000 trames numérotées pendant
15 minutes. Chaque trame est donc émise avec un identifiant SSE :

```text
id: 42
data: {"type":"token","text":"suite de la réponse"}
```

Après une coupure, le frontend se reconnecte avec `Last-Event-ID: 42`. Le
serveur rejoue uniquement les trames suivantes, sans relancer le modèle et
sans dupliquer les tokens déjà affichés. Un commentaire `: keep-alive` est
envoyé toutes les 15 secondes pour éviter les timeouts des reverse proxies.
Le client respecte aussi `Retry-After`, attend le retour du réseau si le
navigateur passe hors ligne, puis applique un backoff exponentiel limité à
quatre tentatives.

### Cycle de vie d'un outil (exemple : recherche web)

```jsonc
// quand l'outil démarre
{"type":"activity","event":{
  "id":"ev_1","kind":"search","tool":"web_search",
  "status":"running","phase":"started",
  "title":"Searching the web","startedAt":1735689600000,
  "input":{"query":"latest AI reasoning models"}
}}

// pendant (autant de fois que tu veux — nombres réels uniquement)
{"type":"activity","event":{
  "id":"ev_1","status":"running","phase":"progress",
  "description":"6/10 sources ouvertes",
  "progress":{"done":6,"total":10,"unit":"sources"}
}}

// à la fin — même id → l'interface met à jour la carte existante
{"type":"activity","event":{
  "id":"ev_1","status":"completed","phase":"completed",
  "title":"Searching the web","description":"Found 10 results",
  "output":{"result_count":10}
}}
```

### Enfants d'un outil

Ajoute `parentId` pour imbriquer (sources ouvertes, fichiers
modifiés, suites de tests) :

```jsonc
{"type":"activity","event":{
  "id":"ev_2","parentId":"ev_1","kind":"browser","tool":"browser",
  "status":"completed","phase":"completed",
  "title":"arxiv.org","description":"Reasoning models in 2026…"
}}
```

### Erreurs et retry

`status:"failed"` + `metadata:{"retryable":true}` ⇒ l'interface
affiche la carte rouge avec bouton **Réessayer** (le retry
ré-exécute côté front pour les commandes ; pour tes outils distants,
émets simplement un nouvel événement terminal quand c'est résolu).

### Kinds disponibles

`thinking` · `planning` · `tool` · `search` · `file` · `terminal` ·
`code` · `browser` · `database` · `calculation` · `analysis` ·
`video` · `response` · `error`

Chaque kind possède un rendu spécialisé automatique : bloc terminal
(`input.command`, `output.stdout`, `output.exitCode`), exécution de
code (`input.code`, `output.stdout`, `output.error`), carte recherche
(`input.query`, `output.results[]`), ops fichiers
(`metadata:{op,path,added,removed}`), vidéo, diagnostics…
**Un nouvel outil devient observable sans toucher le frontend** :
écris ses événements avec le kind correspondant.

### Règles d'or

1. **N'émettre un événement que si l'opération a réellement eu lieu.**
   Pas de « Searching the web… » si aucune recherche n'a tourné.
2. Labels haut-niveau uniquement — jamais de chaîne de raisonnement
   privée dans `title`/`description`.
3. Progressions chiffrées uniquement avec des nombres réels
   (`progress.done/total`).
4. Streamer les tokens dès qu'ils arrivent du modèle ; terminer
   toujours par `{"type":"done"}`.

---

## Dépannage

| Symptôme | Cause probable |
| --- | --- |
| Point rouge « inaccessible » | CORS, mauvais port, ou `/health` absent |
| Message d'erreur « backend 500 » | Exception côté serveur — voir logs uvicorn |
| Rien ne stream | Buffering proxy : garde `X-Accel-Buffering: no` |
| Les vidéos ne partent pas au serveur | Normal — traitées on-device par design |
