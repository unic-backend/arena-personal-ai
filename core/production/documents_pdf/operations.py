"""Les opérations réelles, toutes via `pypdf` — déjà une dépendance ARENA
(lecture, `tools/documents/reader.py`), étendue ici à l'écriture. Aucune
n'écrit un fichier partiel sans lever : `OperationPdfEchouee` porte la
raison, la preuve que la sortie est un PDF réel et complet vient d'ailleurs
(`validation.py`).

**Le format PDFx** (`AlexandrosGounis/pdfx`, MIT, voir `docs/audits/
pdfx_audit.md` et `SPEC.md` du dépôt externe) est un manifeste JSON UTF-8
embarqué comme pièce jointe PDF nommée exactement `pdfx-manifest.json` —
« l'astuce entière tient en une pièce jointe », selon leurs propres mots.
Rien de plus n'est nécessaire pour le lire ou l'écrire : c'est `pypdf.
PdfWriter.add_attachment` et `PdfReader.attachments`, mesurés le
09/09/2026, sans bibliothèque supplémentaire.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


class OperationPdfEchouee(Exception):
    """Une opération PDF a échoué pour une raison attendue — pas un bug d'ARENA."""


NOM_MANIFESTE = "pdfx-manifest.json"
VERSION_PDFX = "1.0"


def _lire(chemin: Path):
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        lecteur = PdfReader(str(chemin))
    except PdfReadError as erreur:
        raise OperationPdfEchouee(f"PDF illisible : {erreur}") from erreur
    except Exception as erreur:  # noqa: BLE001 — pypdf leve plusieurs types selon la casse
        raise OperationPdfEchouee(f"PDF illisible : {type(erreur).__name__}: {erreur}") from erreur

    if lecteur.is_encrypted:
        raise OperationPdfEchouee(
            "PDF chiffré — ARENA ne devine ni ne contourne un mot de passe. "
            "Fournis-le explicitement si tu en as le droit.")
    return lecteur


def _ecrire(writer, sortie: Path) -> None:
    try:
        sortie.parent.mkdir(parents=True, exist_ok=True)
        with open(sortie, "wb") as f:
            writer.write(f)
    except OSError as erreur:
        raise OperationPdfEchouee(f"écriture impossible : {erreur}") from erreur


def nombre_de_pages(chemin: Path) -> int:
    """Le nombre de pages, en passant par la MÊME garde que toute autre
    opération (`_lire()` — chiffré refusé explicitement).

    Mesuré le 09/09/2026 : le connecteur appelait `PdfReader(...).pages`
    directement pour valider des indices de page AVANT d'appeler une
    opération — sur un PDF chiffré, `len(...)` lève `FileNotDecryptedError`
    à cet endroit précis, hors de toute garde, et remonte comme une panne
    non gérée plutôt qu'un refus propre. Cette fonction est le seul chemin
    qui compte les pages désormais.
    """
    return len(_lire(chemin).pages)


# --- Fusion, avec ou sans manifeste PDFx ----------------------------------------

def fusionner(fichiers: List[Path], sortie: Path, titre: str = "",
             noms: Optional[List[str]] = None, format_pdfx: bool = False) -> Dict[str, Any]:
    """Concatène les PDF dans l'ordre donné. Si `format_pdfx`, embarque le
    manifeste — le fichier reste un PDF ordinaire, lisible partout, ET un
    PDFx pour un lecteur qui sait le reconnaître (mission §1, §10 : le
    format lui-même le garantit).

    Rend le détail (nombre de pages par document, total) — jamais deviné.
    """
    from pypdf import PdfWriter

    writer = PdfWriter()
    documents: List[Dict[str, Any]] = []
    for i, chemin in enumerate(fichiers):
        lecteur = _lire(chemin)
        writer.append(lecteur)
        nom = (noms[i] if noms and i < len(noms) else chemin.stem)
        documents.append({"name": nom, "pages": len(lecteur.pages)})

    if format_pdfx:
        manifeste = {"pdfx": VERSION_PDFX, "documents": documents}
        if titre:
            manifeste["title"] = titre
        writer.add_attachment(NOM_MANIFESTE, json.dumps(manifeste, ensure_ascii=False).encode("utf-8"))

    _ecrire(writer, sortie)
    return {"documents": documents, "total_pages": sum(d["pages"] for d in documents)}


# --- Lecture du manifeste PDFx --------------------------------------------------

def lire_manifeste(chemin: Path) -> Optional[Dict[str, Any]]:
    """Le manifeste PDFx, ou `None` si le fichier n'en a pas — auquel cas
    SPEC.md dit de le traiter comme un document unique, jamais une erreur :
    « Plain PDFs are therefore valid PDFX files ».

    Un manifeste présent mais malformé retombe sur `None` aussi (même
    règle) — jamais une exception pour un fichier par ailleurs valide.
    """
    lecteur = _lire(chemin)
    pieces = lecteur.attachments.get(NOM_MANIFESTE)
    if not pieces:
        return None
    try:
        manifeste = json.loads(bytes(pieces[0]).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None

    if not isinstance(manifeste, dict) or "documents" not in manifeste:
        return None
    documents = manifeste.get("documents")
    if not isinstance(documents, list) or not documents:
        return None
    for doc in documents:
        if not isinstance(doc, dict) or "name" not in doc or "pages" not in doc:
            return None
        if not isinstance(doc["pages"], int) or doc["pages"] < 1:
            return None
    return manifeste


def _partition_pdfx(manifeste: Dict[str, Any], nombre_de_pages: int) -> List[Dict[str, Any]]:
    """Applique la règle de troncature/complétion de SPEC.md, §Reader
    behavior : la somme des pages du manifeste peut différer du PDF réel."""
    documents = manifeste["documents"]
    curseur = 0
    partition = []
    for doc in documents:
        if curseur >= nombre_de_pages:
            break
        fin = min(curseur + doc["pages"], nombre_de_pages)
        partition.append({"name": doc["name"], "debut": curseur, "fin": fin})
        curseur = fin
    if curseur < nombre_de_pages:
        partition.append({"name": "untitled", "debut": curseur, "fin": nombre_de_pages})
    return partition


def demonter(chemin: Path, dossier_sortie: Path) -> List[Dict[str, Any]]:
    """Récupère les documents d'origine d'un PDFx — mission §12 : « ARENA
    peut retrouver individuellement devis.pdf, facture.pdf... ». Sans
    manifeste, rend UN SEUL fichier (le PDF entier) : c'est le comportement
    « document unique » que SPEC.md demande pour un PDF ordinaire.
    """
    from pypdf import PdfWriter

    lecteur = _lire(chemin)
    manifeste = lire_manifeste(chemin)
    partition = (_partition_pdfx(manifeste, len(lecteur.pages)) if manifeste
                else [{"name": chemin.stem, "debut": 0, "fin": len(lecteur.pages)}])

    resultats = []
    dossier_sortie.mkdir(parents=True, exist_ok=True)
    for i, part in enumerate(partition):
        writer = PdfWriter()
        for p in range(part["debut"], part["fin"]):
            writer.add_page(lecteur.pages[p])
        sortie = dossier_sortie / f"{i:02d}-{_nom_sur(part['name'])}.pdf"
        _ecrire(writer, sortie)
        resultats.append({"name": part["name"], "pages": part["fin"] - part["debut"],
                          "fichier": str(sortie)})
    return resultats


def _nom_sur(nom: str) -> str:
    import re
    import unicodedata
    normalise = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode("ascii")
    normalise = re.sub(r"[^a-zA-Z0-9]+", "-", normalise).strip("-").lower()
    return normalise[:60] or "document"


# --- Scinder par groupes de pages explicites ------------------------------------

def scinder(chemin: Path, groupes: List[List[int]], dossier_sortie: Path) -> List[Dict[str, Any]]:
    """Un fichier par groupe d'indices (0-based) — indépendant de tout
    manifeste, contrairement à `demonter`."""
    from pypdf import PdfWriter

    lecteur = _lire(chemin)
    dossier_sortie.mkdir(parents=True, exist_ok=True)
    resultats = []
    for i, groupe in enumerate(groupes):
        writer = PdfWriter()
        for p in groupe:
            writer.add_page(lecteur.pages[p])
        sortie = dossier_sortie / f"groupe-{i:02d}.pdf"
        _ecrire(writer, sortie)
        resultats.append({"pages": len(groupe), "fichier": str(sortie)})
    return resultats


# --- Réordonner, supprimer, extraire, pivoter -----------------------------------

def reordonner(chemin: Path, ordre: List[int], sortie: Path) -> int:
    from pypdf import PdfWriter
    lecteur = _lire(chemin)
    writer = PdfWriter()
    for i in ordre:
        writer.add_page(lecteur.pages[i])
    _ecrire(writer, sortie)
    return len(ordre)


def supprimer_pages(chemin: Path, pages: List[int], sortie: Path) -> int:
    from pypdf import PdfWriter
    lecteur = _lire(chemin)
    writer = PdfWriter()
    writer.append(lecteur)
    for i in sorted(set(pages), reverse=True):
        writer.remove_page(i)
    _ecrire(writer, sortie)
    return len(writer.pages)


def extraire_pages(chemin: Path, pages: List[int], sortie: Path) -> int:
    from pypdf import PdfWriter
    lecteur = _lire(chemin)
    writer = PdfWriter()
    for i in pages:
        writer.add_page(lecteur.pages[i])
    _ecrire(writer, sortie)
    return len(pages)


def pivoter_pages(chemin: Path, pages: List[int], degres: int, sortie: Path) -> int:
    if degres % 90 != 0:
        raise OperationPdfEchouee(f"rotation {degres}° refusée — seuls les multiples de 90° le sont.")
    from pypdf import PdfWriter
    lecteur = _lire(chemin)
    writer = PdfWriter()
    writer.append(lecteur)
    for i in pages:
        writer.pages[i].rotate(degres)
    _ecrire(writer, sortie)
    return len(pages)


# --- Extraction d'images ---------------------------------------------------------

def extraire_images(chemin: Path, dossier_sortie: Path) -> List[Dict[str, Any]]:
    lecteur = _lire(chemin)
    dossier_sortie.mkdir(parents=True, exist_ok=True)
    resultats = []
    for num_page, page in enumerate(lecteur.pages):
        try:
            images = page.images
        except Exception as erreur:  # noqa: BLE001 — une page mal formee n'arrete pas les autres
            resultats.append({"page": num_page, "erreur": f"{type(erreur).__name__}: {erreur}"})
            continue
        for image in images:
            nom_sur = f"page{num_page:03d}-{_nom_sur(image.name)}"
            sortie = dossier_sortie / nom_sur
            try:
                sortie.write_bytes(image.data)
            except OSError as erreur:
                resultats.append({"page": num_page, "erreur": f"écriture impossible : {erreur}"})
                continue
            resultats.append({"page": num_page, "fichier": str(sortie), "taille_octets": len(image.data)})
    return resultats
