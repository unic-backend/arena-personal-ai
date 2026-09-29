# Diagnostic du dépôt — 29/09/2026

*Mesuré sur `arena/01a0ef06-arena-personal-ai`, branchée de `main` à `694ab54`
(« Merge pull request #396 … wake-word-usman »). Chaque chiffre de ce fichier
vient d'une commande relancée ce jour-là, jamais d'une lecture de document.*

Environnement de mesure : Linux, Python 3.11, venv jetable installé avec la
liste de paquets de `.github/workflows/ci.yml` — **sans** `libreoffice`,
`ffmpeg`, `tesseract` ni `txtai_minimal`. Cette différence est volontaire :
elle révèle ce qui casse hors de l'image exacte de la CI (§ 2).

---

## 1. Ce qui va bien, et qui est mesuré

| Mesure | Commande | Résultat |
|---|---|---|
| Lint | `ruff check .` | **All checks passed** (0 erreur, 803 fichiers Python) |
| Suite hors-ligne | `pytest -q` | **7566 passés**, 61 ignorés, 57 désélectionnés, 71 échecs (§ 2 et § 3) |
| Modules atteints | `scripts/orphelins.py` | 368 modules, 298 atteints, **0 orphelin réel** (les 70 sont des `__init__.py` ou des services autonomes déclarés) |
| Routeurs montés | `apps/backend/main.py` | **19 sur 19** (20 fichiers, dont `__init__.py`) |
| Surface HTTP | schéma OpenAPI | **74 chemins, 78 opérations** |
| Secrets dans l'arbre | grep + `.gitleaks.toml` | aucun ; pas de `.env` versionné ; les seules occurrences sont des faux dans les tests, annotés `scanner-secrets: ignore` |

Quatre choses sortent nettement du lot pour un dépôt de cette taille :

- **La CI ne se contente pas de lint + tests.** Elle résout `requirements.txt`
  sur 3.11 et 3.12, **construit** l'image Docker, vérifie que le conteneur
  abandonne root, qu'un volume root-owned reste inscriptible, qu'il démarre
  *sans* volume, et fait tourner un smoke OCR/conversion/PDF *dans* l'image.
  C'est le genre d'étape qu'on ajoute après s'être fait mal, et ça se voit.
- **Trois scans gitleaks**, dont un sur l'historique entier — cohérent avec un
  dépôt public.
- **`permissions: contents: read`** explicite sur le workflow.
- **Le rapport test/code est de ~1:1** (84 700 lignes de tests pour 85 800
  lignes de code applicatif). Rare, et c'est ce qui rend les constats ci-dessous
  trouvables.

---

## 2. Le défaut réel : la relecture à chaud ne voit pas tous les changements

**Gravité : haute — c'est le seul point de ce diagnostic qui touche la sécurité.**

> **Corrigé le 29/09/2026, dans la foulée de ce diagnostic — voir DEC-0190.**
> Le correctif va plus loin que ce que cette section proposait : date, taille
> et inode ne suffisaient **pas non plus**. Remplacer `4500` par `5200` ou
> `ALLOWED` par `DENIED` ne change aucun des trois. L'empreinte inclut donc un
> hachage du contenu (22 µs, contre 7,9 ms pour le parse évité). 7 tests
> réparés, 7 ajoutés, vérifiés par mutation. Le texte ci-dessous est conservé
> tel qu'il a été mesuré, parce que c'est lui qui a mené au correctif.

`core/fichier_suivi.py` déclenche une relecture sur la **seule** date de
modification :

```python
def date_de(chemin): return chemin.stat().st_mtime
...
if date != self._date: self._valeur = self._lecteur(self.chemin)
```

Mesuré aujourd'hui sur le système de fichiers de ce bac à sable :

```
écriture 1 -> st_mtime_ns = 1790716950743122667
écriture 2 -> st_mtime_ns = 1790716950743122667   (identique)
```

Deux écritures successives portent la **même** date. Le fichier a changé, la
date non, la relecture n'a jamais lieu. Huit tests le constatent sans
ambiguïté, et ils ne dépendent d'aucun binaire externe :

| Test | Ce qu'il montre |
|---|---|
| `tests/core/test_fichier_suivi.py::test_un_changement_est_vu` | `'premier' == 'second'` échoue : le contenu modifié n'est pas relu |
| `tests/core/test_permissions_a_jour.py` (3 tests) | **une règle durcie n'est pas appliquée** : `decider("email","send")` rend `AUTORISE` là où le fichier dit `REFUSE` |
| `tests/test_plaquiste_grille_a_jour.py` (3 tests) | un prix modifié, un article ajouté ne sont pas vus au chiffrage suivant |

C'est **exactement** le défaut que l'en-tête de `fichier_suivi.py` dit avoir
corrigé le 01/09/2026 (« une règle durcie n'était pas appliquée »). Le module
l'a corrigé pour le cas « une valeur lue une fois au démarrage », pas pour le
cas « deux écritures dans le même tic d'horloge du système de fichiers ».

La CI ne peut pas le voir : sous ext4 avec horodatage nanoseconde et des
écritures espacées, la date change presque toujours. Elle change **moins
souvent** sur un partage réseau, un volume Docker monté depuis Windows, ou un
système de fichiers à granularité seconde — et la machine du propriétaire est
sous Windows 11.

**Correctif proposé** (3 lignes, sans changer l'API) : comparer un triplet au
lieu d'une date.

```python
def empreinte_de(chemin):
    try:
        s = chemin.stat()
        return (s.st_mtime_ns, s.st_size, s.st_ino)
    except OSError:
        return None
```

Le `None` pour « absent » est conservé tel quel — c'est une distinction que le
module documente et qui reste juste. `st_size` attrape le cas mesuré ci-dessus
dès que la taille bouge ; `st_ino` attrape la réécriture atomique par
remplacement. Ça ne rend pas la détection parfaite (même taille, même tic,
même inode reste indétectable), mais ça fait passer les huit tests et ça ferme
le scénario « politique de permissions durcie, jamais appliquée ».

---

## 3. La suite de tests dépend de binaires natifs non déclarés comme tels

**Gravité : moyenne — coût de maintenance et faux signal.**

63 des 71 échecs ne sont pas des bugs : il manque `soffice`, `ffmpeg`,
`tesseract` ou le paquet `txtai_minimal`.

| Famille | Nb | Ce qui manque |
|---|---|---|
| `test_connecteur_pdf`, `test_connecteur_file_conversion`, `test_word_pdf`, `test_presentation_pdf`, `test_rediger_un_document`, `test_dioumtoukay_pdf`… | ~46 | LibreOffice / ffmpeg / tesseract |
| `test_connecteur_txtai_search` | 12 | `txtai_minimal` (installé par la CI, mais pas par `pip install -r requirements.txt` seul dans un venv minimal) |
| `tests/tools/test_crop_tool.py` | 5 | `ffmpeg` |

Le commentaire de `ci.yml` assume ce choix : le marqueur `integration` signifie
« service externe », pas « bibliothèque locale ». La conséquence est réelle
quand même — **l'absence d'un binaire se lit comme un échec de code**, et le
nouveau venu (ou une machine sans LibreOffice) voit 63 tests rouges sans savoir
que son environnement est en cause.

Deux pistes, par ordre de coût croissant :

1. Un marqueur `binaire_externe` + un `skipif` qui teste `shutil.which("soffice")`.
   Un test sauté nomme ce qui manque ; un test rouge ne nomme rien. La CI, qui
   installe les binaires, les exécute comme aujourd'hui.
2. Faire installer la CI depuis un fichier (`requirements-test.txt`) plutôt que
   depuis une liste de 25 paquets écrite à la main dans le YAML. Aujourd'hui
   cette liste et `requirements.txt` peuvent diverger sans que rien ne le dise,
   et `requirements.lock.txt` — qui existe — n'est utilisé par aucune étape.

---

## 4. Les documents de référence ont pris du retard sur les mesures

**Gravité : moyenne — c'est le défaut que `CLAUDE.md` décrit lui-même.**

`docs/CURRENT_STATE.md` (« chaque chiffre vient d'une commande ») affiche :

| Ce que le document dit | Mesuré le 29/09 | Écart |
|---|---|---|
| Routers montés : 17 sur 17 | **19 sur 19** | +2 |
| Routes exposées : 66 | **74 chemins / 78 opérations** | +8 |
| Orphelins mesurés : 63 | **70** | +7 |

Aucun de ces écarts n'est une régression — le dépôt a grandi. Mais
`CLAUDE.md` avertit en toutes lettres qu'« un chiffre figé dans le fichier que
chaque session lit en premier ne vieillit pas visiblement : il se lit comme
l'état du jour », et c'est précisément ce qui s'est produit dans
`CURRENT_STATE.md`. `tests/test_documentation.py` garde déjà le compte
d'orphelins ; le même mécanisme appliqué au nombre de routeurs et à la taille
du schéma OpenAPI rendrait ces trois lignes impossibles à laisser vieillir.

`PROJECT_MEMORY/PROJECT_MAP.md` date du 28/08, `ACTIVE_WORK.md` du 19/09 et
décrit encore comme « en cours » une PR sur `claude/chemin-execution-bout-en-bout` ;
`docs/CURRENT_TASK.md` porte la mission vidéo du 01/09 alors que le dernier
commit livre le mot-clé vocal (DEC-0189). La mémoire opérationnelle est riche,
mais son point d'entrée ne dit plus où on en est.

---

## 5. Points mineurs, vérifiés

- **`scripts/silent_failure_gate.py` plante au lieu d'expliquer.** Sur un clone
  superficiel (`HEAD^` absent), il rend une `CalledProcessError` brute de 12
  lignes. Le workflow le protège en passant `--base`, mais lancé à la main il
  devrait dire « impossible de déterminer la base » — le dépôt applique déjà
  cette discipline ailleurs (l'étape gitleaks différentielle échoue avec un
  message explicite).
- **`python` résolu par le PATH dans la boucle de réparation.**
  `tests/test_dioumtoukay_reprise.py` échoue ici avec `No module named pytest` :
  la commande exécutée est `python -B -m pytest`, et dans un venv dont le PATH
  n'est pas activé, `python` est celui du système. Le reste du dépôt utilise
  `sys.executable` (`core/guardian/diagnostics.py`, `tools/coder/repo_engineer_tool.py`) —
  normaliser `python` → `sys.executable` à l'exécution fermerait l'écart.
  Restent deux appels littéraux à `"python"` : `core/connectors/vectcut.py:60`
  (avec repli d'environnement) et `tools/rag/graphrag_tool.py:118`.
- **Modules très gros**, difficiles à tester en isolation et générateurs de
  conflits : `agents/dioumtoukay/dioumtoukay_agent.py` (2680 lignes),
  `agents/plaquiste/plaquiste_agent.py` (2082),
  `apps/backend/routers/pwa_gateway.py` (1662), `routers/chat.py` (1422),
  `agents/orchestrator/orchestrator_agent.py` (1400).
- **270 `except Exception`** dans `core/`, `agents/`, `apps/`. Aucun `except:`
  nu — c'est bien. Le garde-fou `silent_failure_gate` ne regarde que le code
  *modifié* par une PR : le stock existant n'a jamais été passé en revue.
- **Masse documentaire** : `docs/DECISIONS.md` pèse **700 Ko** dans un seul
  fichier, `docs/CHANGELOG.md` 180 Ko, `docs/audits/` 504 Ko. Un découpage par
  année ou par domaine (`docs/decisions/2026-09.md`) rendrait la relecture et
  les diffs praticables.
- **`pyproject.toml` n'a pas de section `[project]`** : ni nom, ni version, ni
  dépendances déclarées, ni `requires-python`. Défendable pour une application
  qui ne s'installe pas, mais rien n'empêche aujourd'hui quelqu'un de lancer le
  dépôt sous 3.10 (`target-version = "py311"` n'est qu'une consigne de lint).
- **Dépendances** : 98 déclarées, dont un tiers de très lourdes
  (`browser-use`, `lightrag-hku`, `chromadb`, `faster-whisper`). Les
  commentaires de `requirements.txt` montrent un suivi manuel et sérieux des
  failles publiées (PYSEC-2026-76, montée de `pypdf`, de `mcp`…), mais **aucune
  étape de CI ne scanne les vulnérabilités** : le jour où personne ne relit ces
  commentaires, plus rien ne le fait. `pip-audit` en étape non bloquante
  coûterait une minute.

---

## 6. Ce que je ferais dans l'ordre

1. ~~**`core/fichier_suivi.py` : empreinte au lieu de date** (§ 2).~~
   **Fait le 29/09/2026** (DEC-0190) : 7 tests réparés, 7 ajoutés, suite à
   7580 passés, `ruff` propre. Une règle de permission durcie ne peut plus
   être ignorée en silence.
2. **Marqueur `binaire_externe` + `skipif`** sur les 51 tests LibreOffice /
   ffmpeg / tesseract (§ 3). La suite redevient lisible hors de l'image CI.
3. **Réaligner `docs/CURRENT_STATE.md`** et étendre `test_documentation.py` aux
   nombres de routeurs et de routes (§ 4) — sinon l'écart reviendra.
4. **Installer la CI depuis un fichier**, pas depuis une liste en YAML, et
   ajouter `pip-audit` (§ 3 et § 5).
5. Le reste (découpe des gros modules, découpe de `DECISIONS.md`, revue du
   stock d'`except Exception`) est du fond de tiroir : utile, jamais urgent.

---

*Aucun fichier du dépôt n'a été modifié par ce diagnostic : il ne fait que
mesurer. Les commandes sont toutes reproductibles telles quelles.*
