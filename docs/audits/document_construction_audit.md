# Audit — documents, PDF, et compréhension de plans de construction

*Demandé le 30/08/2026 : donner à ARENA une capacité réelle de document,
PDF, et plan de construction — ingestion (PDF/scanné/image/DOCX/XLSX/PPTX),
génération PDF réelle, compréhension de plans (pièces, murs, ouvertures,
cotes), métré déterministe, et un pipeline plan → métré → devis → PDF
réellement branché. Audit d'abord, rien installé avant preuve.*

## Ce que cet audit change par rapport aux quatre précédents

Molmo, claude-artisan et les DEC-0012/13/14/19 avant eux se terminaient par
« rien n'existait, on installe » ou « rien à installer, c'est déjà fait ».
**Celui-ci est différent : une grande partie de ce que la mission demande
existe déjà, construite et testée sous un autre nom (DEC-0012, DEC-0019),
et le travail réel est de fermer des trous précis, pas de partir de zéro.**
Le trouver a demandé de lire le code, pas de faire confiance au titre de la
mission.

---

## 1. Ce qu'ARENA a déjà — inventaire vérifié, fichier par fichier

| Demandé par la mission | Existe déjà | Où |
|---|---|---|
| Lecture PDF (texte) | **Oui** | `tools/documents/reader.py`, `pypdf`, un passage par page |
| Lecture DOCX | **Oui** | idem, `python-docx`, paragraphes + tableaux |
| Lecture TXT/MD/CSV | **Oui** | idem |
| OCR / PDF scanné | **Non** — `pypdf.extract_text()` rend une chaîne vide sur un PDF sans couche texte ; le code le sait et le dit (`"aucun texte extractible (document scanne ?)"`) mais ne fait rien d'autre. **Aucun moteur OCR nulle part dans le dépôt.** | — |
| Lecture XLSX | **Non**, absent de `EXTENSIONS_LISIBLES` | — |
| Lecture PPTX | **Non**, idem | — |
| Compréhension d'image / vision | **Oui** (DEC-0019, la veille) | `agents/vision/vision_agent.py`, `qwen3-vl:4b` via Ollama — **100% logique vérifiée, jamais mesuré sur sa RTX A2000** |
| Upload de fichier (interface) | **Oui**, mais **effacé dès qu'il est lu** — voir §3 | `apps/backend/pieces_jointes.py` |
| Génération PDF | **Oui, déjà à la charte UniC Plaquiste**, pas un PDF générique | `agents/plaquiste/devis_pdf.py` (rendu, `reportlab`) + `core/connectors/devis.py` (connecteur, confirmation, preuve sur disque) |
| Calculs de construction (surfaces, matériaux) | **Oui**, déterministe, vérifié contre un vrai devis | `agents/plaquiste/calcul_materiaux.py` — **zone verrouillée** (`LOCKED_ZONES.md`) |
| Connaissances UniC Plaquiste (prix, charte, exclusions) | **Oui**, réelles, tirées de ses devis | `config/unic_plaquiste.yaml` — **zone verrouillée** |
| Génération devis/facture | **Oui pour devis** ; le moteur de rendu accepte déjà un `type_document` libre (« Genere un devis OU une facture », docstring de `devis_pdf.py`) mais **rien n'appelle jamais `type_document="FACTURE"`** — capacité de rendu prête, jamais orchestrée | `agents/plaquiste/devis_pdf.py` |
| Compréhension de plan (pièces, cotes, surfaces) | **Oui**, déterministe, bout-en-bout constaté une fois (4 pièces, 1751.92 SF) | DEC-0012, `core/connectors/opentakeoff.py` + `agents/plaquiste/metre_plan.py` — Kentucky-ai/opentakeoff (Apache-2.0), à côté (DEC-0008), jamais copié |
| Distinction PLAN FACT / CALCULÉ / INTERPRÉTATION | **Oui, déjà exactement ce que la mission demande**, avec sabotages qui le prouvent | DEC-0012 : plafond = surface au sol (fait), mur = périmètre mesuré × hauteur **donnée** (calcul), rampant = rien (refus explicite, jamais deviné) |
| Détection d'ouvertures (portes/fenêtres) à déduire | **Non** — nommément `SUGGESTION — NON IMPLÉMENTÉE` dans DEC-0012 lui-même : ça suppose un modèle qui regarde l'image, qui n'existait pas encore le 29/08 | `agents/plaquiste/metre_plan.py`, capacités `symbol_sweep`/`count_marks`/`cut_out` d'OpenTakeoff jamais branchées |
| Pipeline plan → métré → devis → PDF | **Oui, déjà câblé end-to-end pour un plan désigné par un chemin tapé en texte** | `agents/plaquiste/plaquiste_agent.py::run()` — lit le plan, mesure, calcule les quantités, propose le PDF, le tout sous confirmation |
| Orchestration (Usman → agent métier) | **Oui** | `agents/orchestrator/orchestrator_agent.py`, intention `PLAQUISTE` |
| Modèle existant réutilisable pour le raisonnement | **Oui** | `fast_provider` (routeur hybride, DEC-0009), déjà celui que `PlaquisteAgent` utilise |

**Conclusion de cette section** : la mission suppose une page presque
blanche. Elle ne l'est pas. Le vrai travail est plus étroit, et plus
précis, que « construire cette capacité » — c'est fermer cinq trous
nommés ci-dessous.

---

## 2. Les cinq trous réels, chacun vérifié dans le code

### A — Aucun OCR : un plan scanné rend `VIDE`, jamais lu

`tools/documents/reader.py::_lire_pdf` ne lit que la couche texte d'un PDF.
Un plan réel est souvent un **scan** ou un export raster sans couche texte
— exactement le cas que le code annonce déjà sans le résoudre
(`"document scanne ?"`). Aucune ligne du dépôt ne rend une page de PDF en
image, et aucun moteur OCR n'existe nulle part.

**C'est le trou le plus important** : sans lui, une bonne partie des
« plans PDF » réels qu'un client envoie n'entrent jamais dans le pipeline
DEC-0012, qui suppose un PDF **structuré** (le moteur OpenTakeoff lit une
géométrie vectorielle, pas une image).

### B — XLSX et PPTX absents de `reader.py`

Demandé explicitement par la mission, absent de `EXTENSIONS_LISIBLES`.
Aucun obstacle trouvé à les ajouter — la question est le choix du moteur
(§4), pas la faisabilité.

### C — Un plan envoyé par pièce jointe (upload PWA) n'atteint jamais OpenTakeoff

C'est le trou le plus délicat, et celui qui **change potentiellement
l'implémentation** — voir §5.

`agents/plaquiste/metre_plan.py::chemin_dans()` ne reconnaît qu'un chemin
**absolu tapé dans la phrase** (design voulu de DEC-0012 : « le propriétaire
désigne un plan posé n'importe où sur sa machine »). Un plan envoyé par le
bouton d'upload de la PWA suit un chemin totalement différent
(`apps/backend/pieces_jointes.py`) : **le fichier est écrit dans un
répertoire temporaire, lu, puis effacé immédiatement** — règle de vie
privée n°1 du module, appliquée à *tout* document, devis compris. Au moment
où `PlaquisteAgent` pourrait vouloir le passer à OpenTakeoff (qui est un
**processus externe**, lisant un vrai chemin sur disque), le fichier n'existe
déjà plus.

**Les deux chemins de plan qui existent aujourd'hui (texte tapé, upload
PWA) ne se rejoignent nulle part.**

### D — Aucune déduction d'ouvertures (portes/fenêtres)

Nommé sans détour par DEC-0012 lui-même comme non fait, pour la raison
qu'il donne : compter des symboles sur un plan suppose un modèle qui **voit**
l'image. DEC-0019 (Qwen3-VL) existe depuis, mais n'a jamais été relié à
cette question précise — et n'a, de toute façon, **jamais tourné avec une
vraie image** sur cette machine.

### E — Un seul type de document (devis), un moteur de rendu déjà générique

`devis_pdf.py::Devis.type_document` accepte déjà n'importe quelle chaîne, et
le style se limite à changer l'en-tête et le libellé — mais rien n'appelle
jamais `"FACTURE"`, et rien ne rend un bon de commande, un bon de livraison,
un contrat ou un rapport de métré. Pas de ligne de taxe (TVA) ni de bloc
« conditions de paiement » dans le gabarit actuel — à vérifier auprès du
propriétaire si c'est un oubli ou un choix (ses devis réels, base de la
charte reprise, n'en montraient peut-être pas).

---

## 3. Ce qui NE bouge PAS — zones verrouillées, respectées telles quelles

Consulté (`PROJECT_MEMORY/LOCKED_ZONES.md`) avant d'écrire un mot de plan :
`config/unic_plaquiste.yaml` (ses prix réels) et
`agents/plaquiste/calcul_materiaux.py` (vérifié contre le devis
`UC-2026-0804-FG2`) sont verrouillés. **Aucun des cinq trous ci-dessus n'a
besoin d'y toucher** — la fermeture de chacun ajoute une lecture ou un
appelant, jamais une réécriture de ces deux fichiers.

`core/connectors/base.py` (confirmation avant écriture) n'est pas non plus
touché : tout nouveau connecteur (facture, bon de commande…) hérite de la
même chaîne permission → confirmation → journal, comme `devis` aujourd'hui.

---

## 4. Candidats externes — audités, pas supposés

### Docling (IBM/Linux Foundation AAIF) — **corrigé après mesure : trop lourd pour B, encore candidat pour A seul**

*Correction du 30/08/2026, phase 1 : ce paragraphe annonçait Docling
« CPU-capable » et « léger » sans l'avoir installé. Mesuré depuis, dans un
environnement isolé — l'erreur est corrigée ici plutôt que laissée debout.*

- **Licence** : MIT (le compagnon `Granite-Docling` est Apache 2.0). Propre.
- **Maintenance** : très active — donné à la Linux Foundation AAIF début
  2026, disponibilité générale sur IBM watsonx en juin 2026. Pas un projet
  gelé.
- **Mesuré, pas supposé** : `pip install docling` embarque par défaut
  `torch`, `torchvision`, `transformers`, `accelerate` et une douzaine de
  paquets `nvidia-cu13-*` (CUDA) — **5,5 Go installés**, pour une capacité
  qui n'a pas besoin de tout ça pour XLSX et PPTX (ce sont des formats
  structurés, pas des images à faire lire par un modèle de mise en page).
  Cette pile poserait aussi un risque réel de conflit avec le CUDA
  qu'Ollama utilise déjà sur sa carte, jamais mesuré ensemble.
- **Décision revue** : Docling **ne sert plus** à combler B ni A. Réévalué
  avec la même rigueur en phase 2 (mesurer avant de choisir) : Tesseract +
  `pypdfium2` couvrent A pour moins de 65 Mo, sans le risque de conflit CUDA.
  Docling ne reste écarté que pour cette raison de poids — pas pour une
  faiblesse de qualité, jamais mesurée ici.

### XLSX et PPTX (trou B) — fermé sans Docling, avec `openpyxl` et `python-pptx`

**Fait, phase 1 (cette PR).** Les formats structurés n'ont besoin d'aucun
modèle : `openpyxl` (déjà la bibliothèque derrière `XlsxWriter`, présente
en transitif) et `python-pptx` lisent XLSX et PPTX directement, sans
dépendance à un moteur de mise en page ou d'OCR. **Mesuré** : les deux
installés ensemble pèsent **66 Mo**, contre 5,5 Go pour Docling — le même
principe que `python-docx` déjà en place pour `.docx`, appliqué aux deux
formats qui manquaient. Zéro conflit avec l'écosystème CUDA d'Ollama,
puisqu'aucun des deux n'en a besoin.

### Tesseract + `pypdfium2` — **retenu pour le trou A (OCR), phase 2, fait**

*Choisi et mesuré en phase 2 (cette PR), après le même geste qu'en phase 1 :
peser avant d'installer, jamais supposer.*

- **Licence** : Apache 2.0 (Tesseract, maintenu par Google). `pypdfium2`
  (rendu PDF→image) Apache-2.0/BSD, `pytesseract` (le pont Python) Apache 2.0.
  Aucun des trois n'a de restriction d'usage commercial.
- **Mesuré** : `tesseract-ocr` + `tesseract-ocr-fra` (binaire système) pèsent
  **~6 Mo** installés ; `pytesseract` + `pypdfium2` (Python) **56 Mo**. Total
  sous les 65 Mo, contre 5,5 Go pour Docling — même ordre de grandeur que la
  correction de phase 1, pour la même raison : aucun modèle de mise en page
  n'est nécessaire pour reconnaître du texte imprimé.
- **Bout en bout, avec le vrai binaire** : un « scan » réel fabriqué dans le
  test (texte rendu en image, aucune couche texte, page pleine à ~300 DPI) →
  `pypdf` confirme l'absence de texte → rendu par `pypdfium2` → lu par
  `pytesseract` → texte retrouvé. **Résolution critique, mesurée, pas
  supposée** : un rendu à ~144 DPI (`scale=2.0`) rendait le texte illisible
  pour tesseract sur la même image ; 300 DPI (`scale=300/72`) le lit
  correctement — la valeur retenue dans le code porte cette mesure en
  commentaire, pas un chiffre choisi au hasard.
- **Windows** : Tesseract publie un installeur officiel UB Mannheim, et un
  paquet `winget` (`UB-Mannheim.TesseractOCR`) — même mécanisme que ffmpeg
  déjà utilisé dans ce projet (`scripts/doctor.py`). Non testé sur sa machine
  (pas de Windows ici) ; `doctor.py` le vérifie désormais au démarrage,
  comme ffmpeg et Docker, et nomme la commande qui l'installe s'il manque.

### MinerU (OpenDataLab) — non retenu, la même raison que Docling

- **Licence** : Apache 2.0, avec un plafond commercial (100 M d'utilisateurs
  actifs mensuels ou 20 M$/mois de revenu) — sans objet pour UniC Plaquiste.
- **Maintenance** : très active (v3.4.0, juin 2026, ~69,7k étoiles).
- **Pourquoi pas retenu** : même famille de coût que Docling — moteur OCR
  PP-OCRv6 (écosystème PaddleOCR), pensé pour un débit documentaire élevé,
  pas pour cohabiter avec trois modèles déjà chargés sur 12 Go de VRAM
  partagés. Tesseract fait le travail demandé (reconnaître du texte imprimé
  sur un plan ou un devis scanné) sans cette pile. À reconsidérer seulement
  si la qualité de Tesseract s'avère insuffisante sur de vrais scans du
  propriétaire — mesuré chez lui, jamais supposé d'ici.

### CubiCasa5K — **rejeté**, sur la licence autant que sur le principe

- **Licence du jeu de données** : Creative Commons
  Attribution-NonCommercial 4.0 — **non commercial**, exactement le cas que
  la mission demande d'exclure explicitement. UniC Plaquiste est une
  activité commerciale ; entraîner ou redistribuer un modèle sur ce jeu de
  données n'est pas permis ici.
- **Même sans la licence, l'approche ne convient pas** : la segmentation
  ML (CubiCasa-style) rend des masques probabilistes — une pièce détectée
  à 87% de confiance, pas un fait vérifiable. La mission demande l'inverse
  (« must be deterministic and independently verifiable »), et c'est
  exactement ce qu'OpenTakeoff (DEC-0012) fait déjà : lire les numéros de
  pièce réellement écrits sur le plan et l'échelle réellement indiquée au
  cartouche, jamais deviner une forme depuis des pixels.
- **Rien à utiliser, pas même comme méthode** : l'idée d'OpenTakeoff (lire
  ce qui est écrit, ne jamais inférer une géométrie par apprentissage) est
  déjà celle en place, et c'est la meilleure des deux pour ce projet.

### WeasyPrint — **non retenu**, ce serait le doublon que la mission interdit

La mission suggère WeasyPrint pour « un vrai fichier PDF ». ARENA en produit
déjà un, réel, à la charte exacte du propriétaire, avec logo, numérotation
légale, calcul en Python (jamais par le modèle), et une preuve sur disque
vérifiée — `reportlab`, déjà là, déjà testé, déjà vérifié une fois avec un
vrai fichier de 3720 octets (PR #13). Remplacer un moteur de rendu qui
fonctionne par un autre, pour la même sortie, serait un remaniement non
demandé par la mission elle-même (« reuse the existing... do NOT invent a
new company design ») et casserait une charte déjà fidèle à ses documents
réels.

---

## 5. Le point qui change l'implémentation — à trancher avant de coder

**Fermer le trou C (upload PWA → OpenTakeoff) demande de choisir entre deux
principes du projet, et ce n'est pas à moi de trancher seul** :

1. Garder la règle actuelle (« un document est effacé dès qu'il est lu »)
   → un plan envoyé par upload ne pourra **jamais** être mesuré par
   OpenTakeoff, qui a besoin d'un vrai fichier sur disque pendant la durée
   de la mesure. La capacité resterait limitée aux plans désignés par un
   chemin tapé (le cas déjà couvert).
2. Assouplir la règle, **seulement pour un plan activement en cours de
   mesure** : garder le fichier le temps de l'appel à OpenTakeoff (quelques
   secondes), l'effacer aussitôt après — jamais accumulé, jamais au-delà
   du tour de conversation.

Les deux sont défendables ; aucun n'est neutre. La règle actuelle est une
protection de vie privée écrite en toutes lettres dans
`pieces_jointes.py` ; l'assouplir, même brièvement, pour un seul type de
fichier est le genre de décision que `docs/DECISIONS.md` documente
d'habitude avec son propriétaire, pas une extrapolation de code.

---

## 6. Plan d'implémentation proposé — phases, dans l'ordre du risque

Ordre proposé, chaque phase vérifiable seule. Les phases 1, 2 et 3 sont
faites ; les quatre autres restent à autoriser :

| Phase | Ce qu'elle ferme | Nouvelle dépendance | Touche une zone verrouillée ? |
|---|---|---|---|
| **1 — FAIT** | XLSX + PPTX dans `reader.py`, via `openpyxl`/`python-pptx` (pas Docling — voir §4, corrigé après mesure : 66 Mo contre 5,5 Go) | `openpyxl`, `python-pptx` (tous deux MIT/légers) | Non |
| **2 — FAIT** | OCR sur PDF scanné (trou A), via Tesseract + `pypdfium2` (pas Docling/MinerU — voir §4, mesuré : ~65 Mo, bout en bout avec le vrai binaire) | `pytesseract`, `pypdfium2` (Apache 2.0/BSD) + le binaire système `tesseract-ocr` | Non |
| **3 — FAIT** | `type_document="FACTURE"` réellement orchestré (trou E, partiel) : détection de « génère la facture » (même discipline que « génère le devis », jamais le mot seul), transmise à `DevisConnector`, vérifiée dans le vrai PDF produit (`pypdf`) | Aucune | Non |
| **4** | Décision du propriétaire sur §5, puis upload PWA → OpenTakeoff (trou C) | Aucune | Non (mais §5 à trancher avec lui) |
| **5** | Détection d'ouvertures via Qwen3-VL sur une page de plan rendue en image (trou D) | Aucune — `pypdfium2` (déjà en place depuis la phase 2) rend la page en image | Non — mais **NON VÉRIFIABLE avant que `qwen3-vl:4b` tourne réellement chez lui** |
| **6** | Bon de commande / bon de livraison / rapport de métré (reste du trou E) | Aucune | Non |
| **7** | Tests bout en bout : plan → métré → devis → PDF, avec un plan de test connu | Aucune | Non |

La phase 5 dépend d'une mesure que cette machine ne peut pas faire
(§ »Ce que la machine de l'assistant ne peut pas faire », `CLAUDE.md`) —
elle peut être **codée et testée en logique** ici, mais son résultat réel
restera `NON VÉRIFIÉ` tant que le propriétaire n'a pas chargé
`qwen3-vl:4b` et fait tourner une vraie image de plan.

## Ce que ça coûte si cet audit est faux

Un trou mal identifié coûterait une phase entière construite sur la
mauvaise hypothèse — par exemple, ajouter un OCR sans remarquer que le
vrai obstacle est l'upload qui efface le fichier avant qu'OpenTakeoff
puisse le lire. C'est pourquoi chaque trou ci-dessus cite le fichier et la
ligne de raisonnement exacts, pas une supposition sur ce qui manque.
