# Audit — ternera/exif-viewer

**Dépôt étudié** : https://github.com/ternera/exif-viewer
**Commit audité** : `3ceea2599e25db3dd0efee18901ea92757b35fb2` (17/05/2026,
tête du dépôt).
**Licence** : **aucune** — vérifié directement, pas supposé : ni fichier
`LICENSE`, ni section licence dans `README.md`. Par défaut, cela signifie
« tous droits réservés » par l'auteur ; seule la consultation/fork sur
GitHub est couverte par les CGU de la plateforme, pas la réutilisation.
**Méthode** : clone réel, lecture ligne à ligne de `manifest.json`,
`background.js`, `content.js`, `exif.min.js` (364 lignes). Rien pris sur la
seule foi du `README.md`.

---

## Ce que le dépôt est réellement

Une **extension Chrome MV3** (menu contextuel « clic droit sur une image →
View EXIF Data »). Rien de plus : elle ne s'installe pas, ne tourne pas
côté serveur, et n'a aucun équivalent avec ce qu'ARENA a besoin de faire
(analyser un fichier déjà sur la machine du propriétaire, ou joint à une
conversation, sans navigateur ni clic).

## Matrice de validation

| Capacité | Affirmation (README) | Vérifié comment | État |
|---|---|---|---|
| Réglages appareil (fabricant, modèle, ouverture, vitesse, ISO) | « Camera settings » | `exif.min.js` couvre `Make`, `Model`, `FNumber`, `ExposureTime`, `LensModel` (grep direct) | **IMPLEMENTED** |
| GPS | « Location data » | `GPSLatitude`/`GPSLongitude` presents dans `exif.min.js` ; `content.js` les affiche BRUTS, sans geocodage inverse | **IMPLEMENTED, minimal** — coordonnées seules, aucune traduction en lieu |
| Date/heure | « Date and time » | Parseur generique (table de tags EXIF), pas de champ special-case trouve par recherche exacte — le mecanisme reste generique | **PARTIAL a confirmer** — pas de preuve directe d'un champ `DateTimeOriginal` nomme explicitement |
| Logiciel, artiste, copyright | « Software used, artist information » | `Artist`, `Copyright` presents dans `exif.min.js` | **IMPLEMENTED** |
| Confidentialité (« we don't collect any personal data ») | Affirmation README | Aucun appel reseau trouve hors `fetch(img.src)` (necessaire pour charger l'image elle-meme) ; aucune permission `storage` dans `manifest.json` ; aucun `host_permissions` large | **CONFIRMÉ** par lecture directe, pas seulement l'affirmation |
| Tests | Non mentionnes | Aucun fichier de test dans le depot | **ABSENT** |

## Architecture

`manifest.json` (MV3) : `background.js` (service worker, menu contextuel) +
`content.js` (injecte dans la page, recoit le message `showExif`, recupere
l'image via `fetch`, appelle `EXIF.getData(img, callback)` /
`EXIF.getAllTags(img)`, affiche un tooltip HTML brut) + `exif.min.js` (le
parseur EXIF lui-meme).

**`exif.min.js` merite une remarque, pas une accusation.** Sa signature
(`EXIF.getData(img, callback)`, `EXIF.getAllTags`) reproduit exactement
l'API du parseur JavaScript `exif-js` (bien connu, historiquement MIT) —
une ressemblance de FORME notee ici, jamais verifiee octet a octet (aucun
besoin : rien de ce fichier n'entre dans ARENA, Python n'a aucun usage
d'un parseur JavaScript).

## GPS et confidentialité (mission §5)

Le dépôt affiche les coordonnées GPS EXIF **brutes**, dans un tooltip sur
la page — jamais envoyées à un service tiers, jamais stockées
(`chrome.storage` absent des permissions), jamais transformees en adresse.
C'est exactement la discipline reprise (independamment, pas copiee) dans
`core/connectors/media_metadata.py` : coordonnees rendues telles quelles,
aucun appel reseau, aucune persistance par le connecteur lui-meme.

## Sécurité

`manifest.json` : `content_security_policy` restrictive
(`script-src 'self'; object-src 'self'`), permissions minimales
(`activeTab`, `contextMenus`, `scripting` — pas de `host_permissions` large,
pas de `storage`). Une extension bien scopee pour ce qu'elle fait.

## Ce qui est réellement réutilisable

**La checklist des champs EXIF standards** — Make, Model, LensModel,
ISOSpeedRatings, FNumber, ExposureTime, FocalLength, Orientation,
DateTimeOriginal, Software, Copyright, Artist, GPSLatitude/Longitude. Ce
n'est pas du code ni une expression originale de ce dépôt : ce sont les
noms de tags de la **spécification EXIF/TIFF elle-même**, le même
vocabulaire que `PIL.ExifTags.Base`/`PIL.ExifTags.GPS` exposent déjà
nativement dans Pillow — confirmé en les important directement
(`core/connectors/media_metadata.py`), jamais recopiés depuis ce dépôt.

## Ce qui n'a délibérément pas été repris

- **L'extension elle-même** — ARENA n'a besoin d'aucune interface installée
  dans un navigateur ; elle lit un fichier déjà sur la machine ou joint à
  la conversation.
- **`exif.min.js`** — aucune ligne. Pillow (deja une dependance d'ARENA)
  lit l'EXIF nativement, verifie directement (`Image.getexif()`,
  `get_ifd()` pour les sous-IFD Exif et GPS) — voir la section « Test GPS
  reel » de la mission.
- **L'affichage tooltip brut** — ARENA structure la reponse (champs nommes,
  `None` explicite pour ce qui manque), jamais un dump `Object.entries`
  generique.

## Décision

ARENA n'avait AUCUNE capacite de metadonnees techniques avant cette
mission (audit prealable, `docs/DECISIONS.md` DEC-0081) : rien a
conserver, rien a comparer — **IMPLEMENT_NEW**, avec Pillow + ffprobe
(deja des dependances d'ARENA), zero nouvelle dependance, zero ligne de ce
depot.
