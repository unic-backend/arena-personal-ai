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

## Étape 0 — Mettre le dépôt en privé

Sur GitHub : `Settings` → tout en bas, `Change repository visibility` → `Private`.

C'est réversible, et ça arrête l'exposition pendant que vous travaillez.

---

## Étape 1 — Changer les clés *(la plus importante)*

Six valeurs ont fuité, correspondant à cinq variables. Générez une valeur
nouvelle pour **chacune**.

Lancez cette commande **cinq fois**, une par variable :

```
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Puis ouvrez votre fichier `.env` (à la racine du projet, jamais versionné) et
remplacez ces cinq lignes par les valeurs obtenues :

```
ARENA_API_KEY=<nouvelle valeur 1>
CREDS_KEY=<nouvelle valeur 2>
JWT_SECRET=<nouvelle valeur 3>
JWT_REFRESH_SECRET=<nouvelle valeur 4>
WEBUI_SECRET_KEY=<nouvelle valeur 5>
```

Redémarrez ensuite les services :

```
docker compose down
```

puis :

```
docker compose up -d
```

**Vérification** : LibreChat (`http://localhost:3080`) et Open WebUI
(`http://localhost:3000`) répondent toujours et voient les modèles `arena-*`.
Si oui, les anciennes clés ne servent plus à rien — **le risque est écarté**,
indépendamment de la suite.

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
et écrit un fichier `arena-secrets-a-purger.txt` **à côté** du dossier du projet
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
git filter-repo --replace-text ../arena-secrets-a-purger.txt --force
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
l'étape 3 (le fichier `arena-secrets-a-purger.txt` les contient, une par ligne
avant la flèche `==>`) :

```
git log --all -S "<valeur>" --oneline
```

Attendu : **aucune ligne** en sortie.

**3. Le projet fonctionne toujours :**

```
pytest
```

Attendu : `156 passed`.

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
del ..\arena-secrets-a-purger.txt
```

*(sous Linux ou macOS : `rm ../arena-secrets-a-purger.txt`)*

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
`documents/ARENA_ENGINEERING_WORKLOG.md`, entrée **T-01**.
