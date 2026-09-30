# Conversion de diagrammes en DrawIO éditable avec Edit-Banana

ARENA expose Edit-Banana comme une **capacité de transformation de diagramme**,
distincte de la compréhension visuelle générale. « Que montre ce diagramme ? »
continue d'utiliser le modèle de vision standard ; « Transforme ce diagramme en
DrawIO éditable » utilise Edit-Banana et produit un document `.drawio`
téléchargeable et modifiable. Le fichier original n'est jamais modifié.

## Ce que la capacité fait et ne fait pas

### Ce qu'elle fait
- Reconstruit la géométrie vectorielle des boîtes, connecteurs et formes à partir d'une image (PNG, JPG, WebP, BMP, TIFF).
- Détecte les textes via OCR local pour les insérer comme textes éditables dans les cellules DrawIO.
- Produit un fichier XML DrawIO `.drawio` valide et téléchargeable, ouvrable dans Diagrams.net / DrawIO / VS Code.

### Ce qu'elle ne fait pas
- Elle ne remplace pas le moteur de vision d'ARENA (Qwen-VL / modèle multimodal).
- Elle ne prétend pas reconstruire parfaitement 100% des tracés artistiques, manuscrits ou hyper-complexes.
- Elle n'implémente pas de conversion PDF multi-pages non vérifiée ni d'export PPTX non prouvé par l'amont.

## Licences et accès aux modèles

### Edit-Banana
Le dépôt officiel <https://github.com/BIT-DataLab/Edit-Banana> contient un fichier
`LICENSE` sous **GNU AGPL-3.0** (bien que son README mentionne Apache 2.0).
En vertu des principes d'ARENA, le fichier `LICENSE` officiel fait foi :
**aucun code source, bibliothèque ni modèle d'Edit-Banana n'est copié ou intégré**
dans le dépôt ARENA. Le moteur tourne exclusivement comme **processus externe isolé**.

### SAM3 (Segment Anything Model 3)
Edit-Banana s'appuie sur SAM3. L'accès aux checkpoints de SAM3 est soumis aux
conditions de licence de Meta / SAM3 (accès contrôlé sur Hugging Face / ModelScope).
ARENA ne contourne aucun accès protégé et ne distribue aucun poids de modèle.

## Installation explicite

Rien n'est téléchargé au démarrage d'ARENA. Pour installer le moteur externe,
choisir un dossier situé **en dehors du dépôt ARENA** et exécuter :

```bash
python scripts/installer_edit_banana.py /chemin/externe/Edit-Banana --accept-agpl-license
```

Le script d'installation :
1. Clone le dépôt officiel `https://github.com/BIT-DataLab/Edit-Banana.git` (commit épinglé `88c6e288ef8329606114eb91924559c5d1838d2e`) ;
2. Crée un environnement virtuel isolé `.venv` dans ce dossier ;
3. Installe les dépendances nécessaires (PyTorch, torchvision, OCR, etc.) sans toucher à l'environnement d'ARENA ;
4. Initialise la configuration `config/config.yaml`.

Après l'installation, placez le fichier de checkpoint SAM3 (`sam3.pt`) dans le dossier `models/` du checkout externe, ou configurez son chemin.

## Configuration (.env)

| Variable | Défaut | Rôle |
|---|---:|---|
| `USMAN_EDIT_BANANA_ROOT` | *(vide)* | Racine du checkout externe Edit-Banana |
| `USMAN_EDIT_BANANA_PYTHON` | *(vide)* | Chemin de l'interpréteur Python du `.venv` externe |
| `USMAN_EDIT_BANANA_LICENSE_ACCEPTED` | `false` | Confirmation explicite de la licence AGPL-3.0 et SAM3 |
| `USMAN_EDIT_BANANA_SAM3_CHECKPOINT` | *(vide)* | Chemin optionnel vers le fichier `sam3.pt` |
| `USMAN_EDIT_BANANA_TIMEOUT_SECONDS` | `300` | Délai maximum par conversion (secondes) |
| `USMAN_EDIT_BANANA_MAX_PIXELS` | `36000000` | Plafond de résolution anti-DoS |
| `USMAN_EDIT_BANANA_MAX_SIDE` | `8192` | Dimension maximale par côté (pixels) |

## Utilisation

Joindre une image de schéma ou diagramme (PNG, JPG, WebP) et demander :

- `Transforme cette image en diagramme DrawIO éditable.`
- `Make this diagram editable.`
- `Convert this architecture diagram to DrawIO.`
- `Rends ce schéma éditable.`
- `Recrée ce flowchart en DrawIO.`

Le document DrawIO produit est validé, écrit sous `media/rendered/diagrams/` (ou `conversions/`),
accompagné d'un fichier de provenance JSON `.drawio.json` et mis à disposition pour téléchargement.

## Diagnostic et état `NOT_CONFIGURED`

Pour vérifier l'état du connecteur :

```bash
python scripts/doctor.py
```

La ligne `Diagrammes éditables (Edit-Banana)` indique :
- `OK` : le moteur est opérationnel et prêt à convertir.
- `NON CONFIGURE` : `USMAN_EDIT_BANANA_ROOT`, `USMAN_EDIT_BANANA_LICENSE_ACCEPTED=true`, ou le checkpoint SAM3 manque.
- `EN PANNE` : le processus a échoué ou une dépendance système est manquante.

## Remplacement ou suppression

Comme Edit-Banana est complètement découplé d'ARENA derrière le connecteur `ConnecteurEditBanana`
et la capacité `diagram_to_drawio` :
1. Pour désactiver : retirer les variables `USMAN_EDIT_BANANA_*` du fichier `.env`.
2. Pour supprimer : supprimer le dossier externe du checkout.
3. Pour remplacer par un autre moteur de vectorisation : adapter `ServiceEditBanana` ou enregistrer un nouveau moteur dans `core/production/conversion/registre.py`.
