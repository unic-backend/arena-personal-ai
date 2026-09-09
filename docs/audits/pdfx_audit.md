# Audit PDFx — ce qu'ARENA avait, ce qui manquait, ce qui s'est fusionné

*Mesuré le 09/09/2026. Dépôt audité : `AlexandrosGounis/pdfx` (clone
superficiel), licence **MIT**.*

Mission du propriétaire : étudier PDFx et déterminer quelles capacités
peuvent améliorer ARENA — sans cloner l'application, sans deuxième système
PDF, sans deuxième architecture documentaire. Ce document est l'étape
« auditer → comparer » avant tout code ; la décision est
`docs/DECISIONS.md`, DEC-0076.

---

## 1. Audit PDFx — ce qu'il est réellement

**Une application de bureau Electron/React/TypeScript** — pas un service,
pas une bibliothèque Python. `package.json` : `pdf-lib` (assemblage),
`pdfjs-dist` (rendu), `tesseract.js` (OCR), `@ai-sdk/*` (assistant IA
multi-fournisseur : Anthropic, Google, OpenAI). Architecture réelle
(`src/main/`, `src/renderer/`) : processus principal Electron, rendu React,
un module `pdfx/` qui porte l'assemblage, la rédaction (`pdfx/redact/`, 15
fichiers — un vrai sous-système de caviardage, non demandé par la mission),
l'OCR, un pont IA (`app/ai-bridge/`).

**Le format PDFx** (`SPEC.md`, 89 lignes, lu intégralement) est la vraie
trouvaille — décrit avec précision, jamais deviné :

- Un fichier `.pdfx` est un **PDF valide** (ISO 32000-1:2008), ouvrable
  dans n'importe quel lecteur.
- Ses pages sont la concaténation, **dans l'ordre**, des pages de chaque
  document membre.
- Un manifeste JSON UTF-8 est embarqué comme **pièce jointe PDF standard**
  (embedded file stream, §7.11.4), nommée exactement `pdfx-manifest.json`.
- Le manifeste liste, par document : son nom et son nombre de pages — la
  partition des pages du PDF final se déduit de cette liste, dans l'ordre.
- **Un PDF sans manifeste est un PDFx valide à un seul document** —
  compatibilité totale, dans les deux sens.

« L'astuce entière tient en une pièce jointe » (README, traduit). Rien de
plus.

**Dépendances** : `pdf-lib`, `pdfjs-dist`, `tesseract.js`, `@ai-sdk/*` — un
écosystème Node/Electron. Aucune n'entre dans ARENA (backend Python).

---

## 2. Audit ARENA — ce qui existait déjà

- **`pypdf` était déjà une dépendance ARENA** (`requirements.txt`), utilisée
  en LECTURE par `tools/documents/reader.py` pour le RAG. **Jamais en
  écriture.** Aucune fusion, aucune scission, aucun réordonnancement,
  aucune suppression/extraction de page, aucune rotation, aucune extraction
  d'image, aucun manifeste — rien de tout ça n'existait.
- **`pypdfium2`** (déjà une dépendance, DEC-0074) rend une page PDF en
  image — pour l'OCR, pas pour du montage de pages. Complémentaire, jamais
  concurrent.
- **`core/production/conversion/`** (DEC-0074, mission File_Converter_Pro)
  fait de la conversion de FORMAT (PDF→DOCX, HTML→PDF...) via LibreOffice/
  WeasyPrint — jamais de manipulation de PAGES à l'intérieur d'un PDF. Les
  deux domaines ne se recouvrent pas : confirmé en le vérifiant, pas
  supposé.
- **`core/production/organisation/`** (DEC-0075, mission AI File Sorter)
  déplace/copie/supprime des FICHIERS entiers — jamais leur contenu.
- **Aucun moteur vision, aucune génération de PDF de scratch autre que
  `agents/plaquiste/devis_pdf.py`** (gabarit `reportlab` fixe pour un
  devis — un cas d'usage précis, pas une capacité PDF générale).
- **`core/security/trust.py`** existait déjà (DEC de la fusion « unifiée »
  du 06/09/2026) et protège déjà la lecture de contenu documentaire côté
  `file_organization` (DEC-0075) — directement réutilisable ici.

**Le manque net** : aucune capacité de manipulation de PAGES PDF, et
aucune notion de « plusieurs documents dans un seul fichier ».

---

## 3. Comparaison, capacité par capacité

| Capacité | ARENA (avant) | PDFx | Verdict |
|---|---|---|---|
| Fusionner des PDF | Absent | `pdf-lib` (assemblage) | **BETTER PDFX (idée)** — construit avec `pypdf`, déjà présent |
| Scinder / réordonner / supprimer / extraire des pages | Absent | Interface de tri par glisser-déposer | **BETTER PDFX (idée)** — même moteur `pypdf` |
| Rotation de pages | Absent | Non trouvé explicitement dans le code lu | **CONSTRUIT quand même** — trivial avec `pypdf`, mesuré fonctionnel |
| Extraction de texte | `tools/documents/reader.py` (lecture RAG) | `pdfjs-dist` (rendu) | **RÉUTILISÉ, jamais dupliqué** — `extraire_texte` délègue à `lire_document()` |
| Extraction d'images | Absent | Non trouvé explicitement | **CONSTRUIT** — `pypdf` le fait nativement (`page.images`), mesuré sur une vraie image |
| **Format manifeste multi-documents** | Absent | **Le cœur du projet** — un JSON en pièce jointe PDF | **ADOPTÉ (décision D, voir §4)** — trivial avec `pypdf.add_attachment`/`.attachments`, zéro dépendance neuve |
| Redaction/caviardage | Absent | Sous-système complet (15 fichiers TS) | **NOT USEFUL ici** — non demandé par la mission, gros morceau TypeScript non transportable |
| OCR | `pytesseract` déjà utilisé (`reader.py`) | `tesseract.js` | **ÉQUIVALENT** — rien à fusionner, deux bindings du même moteur |
| Assistant IA compréhension de PDF | `@ai-sdk` propre à PDFx | Le router de modèles ARENA existant | **NOT USEFUL tel quel** — ARENA route déjà ses propres modèles ; PDFx n'apporte que son propre client IA, hors sujet ici |
| Interface multi-documents (grille) | Absent | Le cœur de l'UX PDFx | **NOT INTÉGRÉ** — ARENA n'a pas d'interface PDF propre ; le concept (plusieurs documents, un ordre) est porté par `fusionner`/`demonter`, sans UI |
| Sécurité fichiers | Gitingest/conversion/organisation ont chacun leur garde | Non auditée (fermé, hors du périmètre TypeScript) | **CONSTRUIT** — `core/production/documents_pdf/securite.py`, sabotage-vérifié |

---

## 4. Décision sur le format PDFx (mission §10)

**D — ARENA supporte l'import ET l'export.**

Justification, mesurée avant de trancher :

- **Coût quasi nul.** `pypdf.PdfWriter.add_attachment()` et `PdfReader.
  attachments` existent déjà dans la version installée (6.14.2) — aucune
  dépendance neuve, testé en écrivant puis relisant un vrai manifeste.
- **Compatibilité totale, garantie par le format lui-même.** Un PDF
  ordinaire reste un PDFx valide (documenté et vérifié : `manifeste()` sur
  un PDF sans pièce jointe rend `a_un_manifeste: False`, jamais une
  erreur).
- **Usage réel identifié par le propriétaire lui-même** (mission §12) :
  bundler devis/facture/plans/photos/rapport d'un même projet dans un seul
  fichier partageable, tout en gardant la capacité de les retrouver un par
  un. Mesuré fonctionnel de bout en bout : `fusionner(..., format_pdfx=
  True)` puis `demonter()` retrouve les trois documents d'origine, noms et
  contenu exacts.

---

## 5. Ce qui a été construit

- **`core/production/documents_pdf/`** — `operations.py` (fusionner,
  démonter, scinder, réordonner, supprimer/extraire des pages, pivoter,
  extraire images, lire/écrire le manifeste PDFx — tout via `pypdf`),
  `securite.py` (chemin sensible, cohérence de l'en-tête `%PDF-`, indices
  de page hors bornes), `validation.py` (un PDF écrit est rouvert et
  compté avant d'être déclaré un succès).
- **`core/connectors/pdf.py`** — dix capacités, toutes `ALLOWED` sous
  `WRITE_FILES` (aucune ne touche jamais le fichier source — chacune
  écrit un fichier neuf).
- **Quatre actions dans la boucle de Dioumtoukay** (`pdf_fusionner`,
  `pdf_demonter`, `pdf_pages`, `pdf_extraire_texte`) — les six autres
  capacités restent atteignables via `registre.executer("pdf", ...)`,
  model-agnostic par construction.
- **`core/production/disponibilite_pdf.py`**, branché sur
  `/agent/capabilities`.

## 6. Ce qui n'a délibérément PAS été intégré, et pourquoi

- **L'application Electron elle-même, son UI en grille, son rendu
  `pdf.js`.** ARENA reste un backend Python ; forcer Electron dans son
  cœur pour une seule capacité aurait été exactement l'erreur que la
  mission interdit (§22).
- **Le sous-système de rédaction/caviardage** (15 fichiers TypeScript) —
  non demandé, gros morceau à réimplémenter pour un besoin non exprimé.
- **L'assistant IA propre à PDFx** (`@ai-sdk`, ses propres clés) — ARENA
  route déjà ses propres modèles ; en ajouter un second aurait été le
  « deuxième assistant IA » explicitement interdit (§15).
- **L'extraction de « document boundaries » par heuristique visuelle**
  (détecter où un document finit et où le suivant commence, sans
  manifeste) — PDFx ne le fait pas non plus sans manifeste ; hors du
  périmètre mesuré de cette mission.

## 7. Licence

PDFx est **MIT** — permissif, compatible avec un dépôt propriétaire.
**Aucune ligne de code copiée** malgré tout : `pdf-lib`/`pdfjs-dist` sont
TypeScript, `pypdf` est la bibliothèque Python déjà en place. Ce qui a été
repris, c'est le FORMAT (documenté publiquement dans `SPEC.md`, conçu pour
être réimplémenté par quiconque) — jamais une ligne de leur code.
