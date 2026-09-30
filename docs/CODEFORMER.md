# Restauration locale avec CodeFormer

ARENA expose CodeFormer comme une **transformation d'image** distincte de la
vision. « Que montre cette image ? » continue d'utiliser le modele de vision ;
« Restaure cette vieille photo » utilise CodeFormer et rend une nouvelle image.
L'original en memoire n'est jamais ecrase.

## Licence avant installation

CodeFormer est publie sous **NTU S-Lab License 1.0**. Elle permet la
redistribution et l'utilisation **non commerciale** sous conditions. Un usage
commercial, avec ou sans modification, exige de contacter les contributeurs.
ARENA n'accorde aucune permission supplementaire. Lire l'original :
<https://github.com/sczhou/CodeFormer/blob/master/LICENSE>.

BasicSR est Apache-2.0, FaceXLib est MIT et Real-ESRGAN est BSD-3-Clause. Le checkout
CodeFormer embarque ses implementations BasicSR/FaceXLib et utilise les poids
officiels de sa release v0.1.0. Le moteur reste dans un processus et un
environnement externes ; aucun code ni poids CodeFormer n'est distribue dans
ARENA.

## Installation explicite

Rien n'est telecharge au demarrage du serveur. Choisir un dossier **hors de ce
depot**, puis lancer :

```bash
python scripts/installer_codeformer.py /chemin/externe/CodeFormer \
  --accept-noncommercial-license --with-background
```

Le script :

1. clone uniquement l'amont officiel et se place sur le commit
   `b33cc7d639d6545bfcccc7e0bc6ae51f24e79c2b` ;
2. cree `.venv` dans ce checkout ;
3. installe les exigences officielles ;
4. telecharge les poids de la release officielle v0.1.0 ;
5. verifie chaque poids par SHA-256 avant de le rendre visible.

`--with-background` ajoute le poids Real-ESRGAN. Il est facultatif et requis
seulement pour « restaure cette photo et ameliore l'arriere-plan ».

Reporter les trois variables affichees par le script dans `.env`. Ne mettre
`USMAN_CODEFORMER_LICENSE_ACCEPTED=true` qu'apres lecture de la licence et,
pour un usage commercial, apres obtention de l'autorisation requise.

## Configuration

| Variable | Defaut | Role |
|---|---:|---|
| `USMAN_CODEFORMER_ROOT` | vide | checkout externe epingle |
| `USMAN_CODEFORMER_PYTHON` | `.venv` du checkout | interpreteur isole |
| `USMAN_CODEFORMER_LICENSE_ACCEPTED` | `false` | acceptation explicite |
| `USMAN_CODEFORMER_TIMEOUT_SECONDS` | `600` | delai dur par restauration |
| `USMAN_CODEFORMER_MAX_PIXELS` | `16000000` | plafond anti-allocation |
| `USMAN_CODEFORMER_MAX_SIDE` | `4096` | plafond par cote |
| `USMAN_CODEFORMER_CONCURRENCY` | `1` | executions simultanees |

CUDA est utilise par le CLI officiel quand PyTorch le voit. Sans CUDA, le CPU
est accepte mais signale comme potentiellement **tres lent**. Une seule
execution est autorisee par defaut pour borner VRAM/RAM.

## Utilisation

Joindre une image JPEG, PNG ou WebP puis demander, par exemple :

- `Restaure cette vieille photo.`
- `Ameliore les visages de ce portrait.`
- `Restaure cette photo et ameliore l'arriere-plan.`
- `Restaure cette photo, fidelite 0,7.`

`fidelity` est borne a `[0, 1]` et vaut `0,5` par defaut. Le rendu PNG est
valide par Pillow, stocke sous `media/rendered/restorations/`, servi par la
route authentifiee existante et accompagne d'un sidecar JSON de provenance.
Les noms de sortie sont aleatoires afin que deux demandes concurrentes ne
s'ecrasent jamais.

Si le checkout, l'environnement, la licence ou un poids manque, ARENA continue
de demarrer et seule cette capacite rend une indisponibilite explicite.
