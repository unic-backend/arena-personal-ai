# Marche à suivre — Rotation des clés et purge de l'historique Git

**Tâche T-01.** À lire en entier avant de commencer. Chaque étape se fait
**une commande à la fois**, en vérifiant le résultat avant de passer à la suivante.

---

## Ce qu'il faut comprendre d'abord

L'historique du dépôt contient **6 valeurs de secrets écrites en clair**, dans
`librechat.yaml` et `docker-compose.yml`. Le dépôt est public.

Deux choses différentes, à ne pas confondre :

| | Effet |
|---|---|
| **Changer les clés** (rotation) | Rend les anciennes valeurs **inutiles**. C'est la seule action qui protège vraiment. |
| **Purger l'historique** | Retire les valeurs du dépôt. **Ne les dépublie pas** : les copies déjà faites les gardent. |

> **La rotation seule suffit à être en sécurité. La purge seule ne suffit pas.**
> Si vous ne deviez faire qu'une chose : l'étape 1.

Ce que la purge **ne peut pas** faire :
- effacer les copies (`git clone`) déjà téléchargées par d'autres ;
- effacer les *forks* du dépôt sur GitHub ;
- effacer immédiatement les commits que GitHub garde accessibles par leur
  identifiant — il faut le demander au support GitHub pour cela.

---

## Étape 0 — Mettre le dépôt en privé ✅ **FAIT le 28/08/2026**

Le propriétaire l'a fait lui-même. Vérifié par l'API GitHub : `"private": true`,
0 fork, 0 copie visible.

**Ce que ça change.** L'exposition publique est close : plus personne, hors des
comptes autorisés, ne peut lire l'historique ni les six valeurs qu'il contient.
Combiné au retrait de LibreChat et Open WebUI (DEC-0007), qui a rendu quatre de
ces cinq clés inutiles, **le risque est essentiellement fermé**.

**Ce que ça ne change pas.** Les valeurs restent écrites dans l'historique, et
une copie faite avant le 28/08 les garde. C'est pour cela que l'étape 1 —
changer `USMAN_API_KEY` — garde son intérêt si le doute subsiste, et que la
purge reste possible. Elle n'est plus urgente.

(Étape réversible : la même page permet de repasser le dépôt en public.)

---

## Étape 1 — Changer la clé *(la plus importante)*

**Mise à jour du 2026-08-28.** Six valeurs avaient fuité, pour cinq variables.
Le propriétaire a dit ce jour-là qu'il n'utilise plus LibreChat : il a sa propre
interface, servie par ARENA. **LibreChat et Open WebUI ont donc été retirés du
dépôt**, avec `docker-compose.yml` et `librechat.yaml`.

Conséquence directe, et c'est la meilleure protection possible : quatre des cinq
clés **n'ouvrent plus rien**.

| Clé | État |
|---|---|
| `CREDS_KEY` | morte — plus aucun service ne la lit |
| `JWT_SECRET` | morte — idem |
| `JWT_REFRESH_SECRET` | morte — idem |
| `WEBUI_SECRET_KEY` | morte — idem |
| **`USMAN_API_KEY`** | **vivante — elle ouvre ARENA lui-même** |

Une clé morte ne se change pas : on retire ce qu'elle ouvrait. C'est fait, et un
test le tient (`tests/test_configuration_clients.py`, classe
`TestLesClesMortesNeServentPlus`) : si l'un de ces fichiers revient, ou si l'une
de ces quatre lignes réapparaît dans `.env.example`, la suite échoue.

### Ce qu'il reste à faire : une seule clé

`USMAN_API_KEY` (ancien nom : `ARENA_API_KEY`) est la seule qui protège encore
quelque chose. Le propriétaire dit l'avoir changée une fois. **Si vous n'en êtes
pas certain, changez-la : ça ne coûte rien et ça referme la question.**

Générez une valeur, dans le terminal 1 :

```
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Ouvrez `.env` (à la racine, jamais versionné) et remplacez cette ligne :

```
USMAN_API_KEY=<la valeur obtenue>
```

Redémarrez ARENA. **Attention** : l'interface PWA garde la clé de son côté — il
faut la remettre là aussi, sinon chaque message répond 401.

**Vérification** : ouvrez ARENA, envoyez un message. S'il répond, la nouvelle
clé est en place, et l'ancienne — celle qui est dans l'historique public — ne
sert plus à rien. **Le risque est écarté, indépendamment de la suite.**

### Ce qui n'est pas une clé, et qui compte plus

Le dépôt est **public**. Le passer en privé arrête l'exposition immédiatement
(GitHub → `Settings` → tout en bas → `Change repository visibility`). C'est
réversible, et ça se fait depuis un téléphone.

---

## Étape 2 — Sauvegarder avant de toucher à l'historique

L'étape 5 est irréversible. Faites une copie complète :

```
git clone --mirror https://github.com/unic-backend/arena-personal-ai arena-sauvegarde.git
```

Gardez ce dossier `arena-sauvegarde.git` jusqu'à ce que tout soit vérifié.

---

## Étape 3 — Trouver les secrets à purger

Depuis le dossier du projet :

```
python scripts/preparer_purge_secrets.py
```

Le script lit l'historique, affiche les secrets trouvés **sous forme masquée**,
et écrit un fichier `usman-secrets-a-purger.txt` **à côté** du dossier du projet
— délibérément hors du dépôt, pour qu'il ne puisse pas être versionné.

Sortie attendue : `6 secret(s) trouvé(s) dans l'historique`.

---

## Étape 4 — Réécrire l'historique

Installez l'outil :

```
pip install git-filter-repo
```

Puis, depuis le dossier du projet :

```
git filter-repo --replace-text ../usman-secrets-a-purger.txt --force
```

> **Ne pas utiliser** `git filter-repo --path librechat.yaml --invert-paths`.
> Cette commande, proposée dans un rapport d'audit, **supprime `librechat.yaml`
> de tout l'historique** — y compris la version actuelle, dont LibreChat a besoin
> pour fonctionner. Elle laisse aussi les secrets présents dans les autres
> fichiers. Vérifié le 26/08/2026 sur une copie.

---

## Étape 5 — Vérifier avant de publier

Trois contrôles. Les trois doivent passer.

**1. Les fichiers sont toujours là :**

```
git show HEAD:librechat.yaml
```

Attendu : le fichier s'affiche, avec `apiKey: "${ARENA_API_KEY}"`.

**2. Les secrets ont disparu de l'historique.** Pour chaque valeur listée à
l'étape 3 (le fichier `usman-secrets-a-purger.txt` les contient, une par ligne
avant la flèche `==>`) :

```
git log --all -S "<valeur>" --oneline
```

Attendu : **aucune ligne** en sortie.

**3. Le projet fonctionne toujours :**

```
pytest
```

Attendu : `369 passed, 21 deselected` — mesuré le 26/08/2026.

---

## Étape 6 — Publier la réécriture *(irréversible)*

**Ne faites cette étape que si les trois contrôles de l'étape 5 sont passés.**

`git filter-repo` a supprimé le lien vers GitHub par sécurité. Il faut le remettre :

```
git remote add origin https://github.com/unic-backend/arena-personal-ai
```

Puis publier :

```
git push --force --all origin
```

Et les étiquettes de version, s'il y en a :

```
git push --force --tags origin
```

**Conséquence** : tous les identifiants de commits changent. Toute copie du dépôt
faite avant cette opération devient incompatible — il faut la supprimer et
refaire un `git clone`.

---

## Étape 7 — Finir proprement

Supprimez le fichier qui contient les secrets en clair :

```
del ..\usman-secrets-a-purger.txt
```

*(sous Linux ou macOS : `rm ../usman-secrets-a-purger.txt`)*

Puis, si vous voulez que GitHub oublie aussi les anciens commits accessibles par
leur identifiant, ouvrez une demande au support GitHub en citant le dépôt et en
demandant un *garbage collection* après réécriture d'historique.

Enfin, remettez le dépôt en public si vous le souhaitez (étape 0, en sens inverse).

---

## En cas de problème

Rien n'est perdu tant que `arena-sauvegarde.git` existe. Pour revenir en arrière :

```
git clone arena-sauvegarde.git arena-restaure
```

---

## Trace

Une fois l'opération faite, notez la date et le résultat dans
`documents/USMAN_ENGINEERING_WORKLOG.md`, entrée **T-01**.
