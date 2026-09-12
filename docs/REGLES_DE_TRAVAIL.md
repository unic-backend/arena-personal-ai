# Règles de travail — posées par le propriétaire le 2026-08-27

Permanentes. Elles priment sur toute habitude contraire.

Le propriétaire **n'écrit pas de code**. Il exécute ce qu'on lui donne, dans
VS Code. Tout ce qui suit découle de ce seul fait.

---

## 1. Les terminaux

Il travaille dans les terminaux de VS Code, nommés **terminal 1, terminal 2,
terminal 3**…

- Chaque commande est annoncée avec son terminal : « mets ça dans le terminal 1 ».
- **Une seule commande à la fois.** Jamais deux, jamais une liste à dérouler.
- On attend son retour avant la suivante.

## 2. Les fichiers

- Pour créer un fichier : donner **la commande** qui le crée, il la colle, le
  fichier apparaît.
- Puis donner **le code complet** à coller dedans.
- **Jamais « remplace les lignes 10 à 35 ».** Il ne sait pas où sont les lignes,
  et compter des lignes dans un fichier qu'on ne lit pas est une source d'erreur
  pour tout le monde. Toujours le fichier **entier** : il efface l'ancien, il
  colle le nouveau.

## 3. Git

Il ne connaît ni `master`, ni `travail`, ni les branches. Ce sont nos mots, pas
les siens.

- S'il doit changer de branche, on lui **explique en clair** ce que ça fait et
  on lui donne la commande.
- Ne jamais lui demander de choisir entre deux branches sans lui dire ce que
  chacune change pour lui.

### Une fusion se vérifie par le contenu, jamais par le message

GitHub fusionne parfois la tête **enregistrée** quand la PR a été lue, pas la
dernière poussée. La réponse dit `"merged": true` et les derniers commits ne
sont pas dans `master`. C'est arrivé **quatre** fois : #98, #103, #106, #110.

Ce n'est donc pas un incident, c'est le comportement normal quand on pousse
après avoir lu la PR. La vérification ci-dessous n'est pas une précaution :
c'est une étape.

Après chaque fusion, une seule commande tranche :

```
git fetch origin main && git diff --stat <derniere-tete> origin/main
```

**Rien en sortie = le contenu est bien passé.** Des lignes en sortie = ce qui
manque, et il faut rejouer ces commits sur une branche neuve.

`git merge-base --is-ancestor` ne sert à rien ici : un squash crée un commit
neuf, l'ancêtre ne correspond jamais. C'est le contenu qui fait foi.

## 4. Le déploiement va au fond

> « les commit push doivent aller au fond car d'autres outils travaillent sur ce
> projet, alors quand on déploie il doit être totalement déployé. Je ne veux pas
> de déploiements invisibles. »

Concrètement : tout travail terminé et vérifié part sur **`master`**, poussé sur
GitHub, visible par tout le monde. Pas de branche parallèle qu'on garde « pour
plus tard ». Pas de travail qui dort en local.

## 5. Ses jetons

> « je ne veux pas que tu tires tous mes tokens »

- Réponses courtes. Le résultat d'abord.
- Ne pas réexpliquer ce qui est déjà acquis.
- Ne pas réafficher un fichier qu'il vient de voir.
- Chercher dans le code plutôt que lire des fichiers entiers.

**Ce qui n'est jamais coupé pour économiser** : lire le code avant de le
changer, lancer les tests, et rapporter un échec avec sa vraie sortie.

---

## Ce que ces règles ne changent pas

Les règles de vérification restent entières :
`python -m ruff check .` **et** `python -m pytest tests/ -q`, sortie réelle
collée dans le message qui la rapporte. Une réponse courte parce que le travail
a été sauté est une fausse économie.

---

## Mode relais — depuis le 2026-08-28

Le propriétaire n'a plus accès à son PC pendant un temps indéterminé, et lit
depuis son téléphone. Il a autorisé explicitement l'assistant à **travailler
seul**. Ce qui change, et seulement cela :

- L'assistant **écrit les fichiers lui-même** dans le dépôt, lance `ruff` et
  `pytest`, commite et pousse. Le propriétaire ne colle plus rien.
- Le travail part sur la branche `claude/arena-personal-ai-qh66ix` et arrive par
  **pull request**, que le propriétaire fusionne depuis son téléphone. Rien ne
  va directement sur `master` en son absence : il ne peut plus lancer les tests
  lui-même, la PR est l'endroit où il voit ce qui entre.

Ce qui **ne change pas** : la vérification (`ruff` **et** `pytest`, sortie
réelle rapportée), le sabotage avant de déclarer une garantie tenue, une phase
par tour, et l'interdiction d'inventer une mesure.

**Ce que la machine de l'assistant ne peut pas faire**, et qu'aucune permission
ne répare : Ollama n'y est pas (donc ni modèle, ni embeddings `bge-m3`), la
recherche web n'y répond pas, et l'interface ne peut pas être regardée. Toute
scène qui en dépend se rapporte `UNKNOWN` et attend son PC.

Dès que son PC est rallumé : lancer `python scripts/mesurer_performances.py`
et coller le tableau — c'est la moitié manquante de la phase 7.2.
