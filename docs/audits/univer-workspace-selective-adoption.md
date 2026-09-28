# Univer Workspace — revue d'intégration sélective (2026-09-28)

Sources examinées :
- `dream-num/univer-workspace`
- `dream-num/univer-cli`

## Décision d'architecture

ARENA n'embarque pas un second agent, un second orchestrateur, un second système
d'authentification ni le serveur Workspace complet.

Les capacités Office sont exposées derrière le registre de connecteurs existant
et appelées par Dioumtoukay. Le chemin utilisateur reste :

PWA -> routeur ARENA -> Dioumtoukay -> registre -> office_univer -> Univer CLI

Le moteur local utilise le paquet public épinglé `univer-cli@0.5.0`. Les
documents de travail sont des conteneurs `.univer` sous `data/univer/`.
Les exports téléchargeables restent sous `media/rendered/office/`.

## Capacités retenues

- import Office local (XLS/XLSX/XLSM/CSV/TSV/DOC/DOCX/PPT/PPTX) ;
- Units Sheet, Doc, Slide, Base et Board ;
- Worktrees isolés ;
- lecture/inspection structurée ;
- exécution Facade JavaScript de confiance ;
- état ready / reopen / merge / discard ;
- export XLSX/CSV/TSV/DOCX/PPTX ;
- rendu PDF ;
- lint géométrique des Slides.

Le JavaScript Facade n'est pas un sandbox. Dans ARENA il est donc séparé des
opérations documentaires ordinaires et reste sous confirmation +
`EXECUTE_COMMANDS`.

## Ce qui n'est pas dupliqué

- Workspace Agent : Dioumtoukay existe déjà et reste l'unique agent machine ;
- serveur d'identité/permissions Workspace : ARENA possède déjà ses politiques ;
- stockage Workspace distant : les `.univer` restent dans le volume local ;
- navigateur Workspace : la PWA ARENA reste l'interface du propriétaire.

## Licence

Le code des dépôts examinés est Apache-2.0.

Le runtime distribué par Univer CLI embarque aussi des composants Univer Pro
avec leurs propres conditions. La documentation amont décrit la crédentielle
embarquée comme une licence runtime **de développement localhost**, tournante
sur 90 jours, distincte de la licence logicielle du dépôt.

Conséquence dans ARENA :
- en développement, le runtime embarqué peut être mesuré et testé ;
- en mode production, ARENA ne considère pas ce runtime comme configuré tant
  qu'une licence runtime explicitement autorisée pour la production n'est pas
  fournie via `UNIVER_LICENSE` ;
- aucune réponse de santé ne transforme la licence de développement en licence
  de production.

## Validation exigée

La CI Docker doit exécuter le moteur réel sous l'utilisateur non-root ARENA :

1. créer un `.univer` ;
2. créer un Worktree ;
3. créer une Sheet ;
4. écrire puis relire des cellules ;
5. inspecter la modification ;
6. passer le Worktree à ready ;
7. fusionner ;
8. relire le trunk ;
9. exporter un vrai XLSX et le relire avec openpyxl ;
10. réimporter ce XLSX ;
11. produire un vrai PDF avec Chromium.

Un connecteur mocké ne remplace pas ce test runtime.
