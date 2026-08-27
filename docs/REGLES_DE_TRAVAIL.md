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
