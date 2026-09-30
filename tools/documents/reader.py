"""Extraction du texte d'un document, avec sa provenance.

Les deux moteurs documentaires du projet — LightRAG et GraphRAG — n'acceptent
que du texte brut. Aucun ne sait ouvrir un PDF ni un fichier Word. C'est cette
étape-là qui manquait.

Deux règles portées par ce module :

1. **Un document illisible est signalé, jamais résumé de mémoire.** Le résultat
   porte un état (`LU`, `VIDE`, `NON_PRIS_EN_CHARGE`, `ECHEC`) ; il ne renvoie
   jamais un texte plausible à la place d'un texte réel.
2. **Chaque morceau de texte garde son origine.** Nom du fichier et, pour un PDF,
   numéro de page. Sans cela, une réponse ne peut pas citer sa source — et une
   réponse documentaire sans source ne vaut pas mieux qu'une réponse de mémoire.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("usman.tools.documents")

# Formats que ce module sait ouvrir. Une extension absente d'ici est refusee
# explicitement, elle n'est pas ignoree en silence.
EXTENSIONS_LISIBLES = {".pdf", ".docx", ".txt", ".md", ".csv", ".xlsx", ".pptx"}

# Un document plus gros que cela est probablement une archive ou une video mal
# nommee ; le lire d'un bloc occuperait la memoire pour rien.
TAILLE_MAX_OCTETS = 50 * 1024 * 1024


@dataclass
class Passage:
    """Un morceau de texte, et l'endroit exact d'ou il vient.

    `via_ocr` distingue un texte réellement encodé dans le document d'un texte
    **deviné** par reconnaissance optique sur une page scannée. Les deux sont
    utiles, mais pas avec la même certitude — la citation le dit.
    """

    texte: str
    fichier: str
    page: Optional[int] = None
    via_ocr: bool = False

    @property
    def source(self) -> str:
        """Libellé lisible de la provenance, tel qu'il sera cité."""
        base = f"{self.fichier}, page {self.page}" if self.page else self.fichier
        return f"{base} (OCR)" if self.via_ocr else base


@dataclass
class Document:
    """Résultat de la lecture d'un fichier."""

    chemin: Path
    statut: str
    passages: List[Passage] = field(default_factory=list)
    raison: Optional[str] = None

    @property
    def lu(self) -> bool:
        return self.statut == "LU"

    @property
    def texte(self) -> str:
        """Le document entier, passages séparés par une ligne vide."""
        return "\n\n".join(p.texte for p in self.passages)

    @property
    def caracteres(self) -> int:
        return sum(len(p.texte) for p in self.passages)

    def resume(self) -> Dict[str, Any]:
        """Description courte, sans le contenu — pour les journaux et les rapports."""
        return {
            "fichier": self.chemin.name,
            "statut": self.statut,
            "passages": len(self.passages),
            "caracteres": self.caracteres,
            "passages_ocr": sum(1 for p in self.passages if p.via_ocr),
            "raison": self.raison,
        }


def _echec(chemin: Path, statut: str, raison: str) -> Document:
    logger.info(f"Document non lu ({raison}) : {chemin.name}")
    return Document(chemin=chemin, statut=statut, raison=raison)


def _nettoyer(texte: str) -> str:
    """Normalise les espaces sans toucher aux retours à la ligne signifiants."""
    lignes = [ligne.rstrip() for ligne in texte.replace("\r\n", "\n").split("\n")]
    # Deux lignes vides de suite n'apportent rien de plus qu'une seule.
    sortie, precedente_vide = [], False
    for ligne in lignes:
        vide = not ligne.strip()
        if vide and precedente_vide:
            continue
        sortie.append(ligne)
        precedente_vide = vide
    return "\n".join(sortie).strip()


def _lire_texte_simple(chemin: Path) -> List[Passage]:
    """Fichier texte : encodage tolérant, un seul passage."""
    brut = chemin.read_bytes().decode("utf-8", errors="replace")
    contenu = _nettoyer(brut)
    return [Passage(texte=contenu, fichier=chemin.name)] if contenu else []


#: Les langues qu'ARENA demande a tesseract quand elles sont INSTALLEES sur
#: la machine. Ses devis sont francais, ses plans souvent anglais ; tesseract
#: combine `fra+eng` et lit les deux sans qu'on devine la langue de la page —
#: c'est sa fonction documentee, pas une astuce. L'ordre dicte la chaine
#: resultante (`fra+eng`), elle est figee par test.
LANGUES_VOULUES_OCR = ("fra", "eng")

_langues_ocr_detectees: Optional[str] = None
_detection_faite = False


def _detecter_langues_ocr() -> Optional[str]:
    """La chaine `lang` couvrant fra/eng, reduite aux packs reellement
    installes, ou None si ni l'un ni l'autre ne l'est.

    Mesure du 30/09/2026, vrai binaire tesseract 5.5.2 : passer `fra` en dur
    a une machine ou seul `eng` est installe ne leve aucune erreur visible —
    `image_to_string` recouvre l'echec du binaire et le `except` de
    `_ocr_page` rendait une chaine vide : le scan anglais disparaissait sans
    laisser d'etat (`VIDE`, comme une page blanche). `get_languages` pose la
    question au binaire lui-meme ; binaire absent ou packs manquants, la
    reponse est None et l'OCR n'est pas tente du tout.
    """
    try:
        import pytesseract
    except ImportError:
        return None
    try:
        installees = set(pytesseract.get_languages(config=""))
    except Exception as e:  # noqa: BLE001 — binaire absent ou sortie inconnue : un etat, pas un crash
        logger.debug(f"Langues tesseract illisibles : {e}")
        return None
    voulues = [langue for langue in LANGUES_VOULUES_OCR if langue in installees]
    return "+".join(voulues) if voulues else None


def langues_ocr() -> Optional[str]:
    """Les langues d'OCR utilisables, detectees une seule fois par processus.

    Les packs ne changent pas pendant une lecture, et la question coute un
    appel au binaire : on ne la repose pas page par page.
    """
    global _langues_ocr_detectees, _detection_faite
    if not _detection_faite:
        _langues_ocr_detectees = _detecter_langues_ocr()
        _detection_faite = True
    return _langues_ocr_detectees


def _oublier_langues_ocr() -> None:
    """Oublie la detection — pour les tests, et le jour ou un pack est
    installe en pleine session."""
    global _langues_ocr_detectees, _detection_faite
    _langues_ocr_detectees = None
    _detection_faite = False


#: 300 DPI : la resolution standard pour une reconnaissance fiable. Mesure du
#: 30/08/2026 : en dessous (scale=2.0, ~144 DPI), le texte d'une page A4
#: entiere devient illisible pour tesseract — verifie avec un vrai scan
#: fabrique dans le test, pas suppose.
ECHELLE_RENDU_OCR = 300 / 72


def _ocr_page(chemin: Path, index: int) -> str:
    """Le texte d'une page sans couche texte, lu par reconnaissance optique.

    Rend une chaine vide si l'OCR n'est pas disponible (`pypdfium2`/
    `pytesseract` non installes, binaire `tesseract` absent, ou aucun des
    packs `fra`/`eng` installe) ou n'a rien trouve — jamais une exception qui
    ferait perdre tout le document pour une seule page.
    """
    langues = langues_ocr()
    if langues is None:
        logger.debug(f"OCR non tente sur {chemin.name} : ni le pack fra ni le pack eng installe.")
        return ""
    try:
        import pypdfium2 as pdfium
        import pytesseract
    except ImportError:
        return ""
    document = None
    try:
        document = pdfium.PdfDocument(str(chemin))
        page = document[index]
        image = page.render(scale=ECHELLE_RENDU_OCR).to_pil()
        return pytesseract.image_to_string(image, lang=langues)
    except Exception as e:  # noqa: BLE001 — tesseract absent, page corrompue : un etat, pas un crash
        logger.debug(f"OCR impossible sur la page {index + 1} de {chemin.name} : {e}")
        return ""
    finally:
        # Sans cette fermeture explicite, le fichier restait ouvert jusqu'au
        # passage du ramasse-miettes — un moment indetermine. Sur Linux ca ne
        # genait personne : `unlink()` efface un fichier meme ouvert. Sous
        # Windows, l'appelant (`DepotPiecesJointes.deposer`) essaie d'effacer
        # ce meme fichier juste apres et recoit
        # `PermissionError: [WinError 32]` — mesure le 01/09/2026 sur la
        # machine du proprietaire, invisible sur Linux.
        if document is not None:
            document.close()


def _lire_pdf(chemin: Path) -> List[Passage]:
    """PDF : un passage par page, la page est conservée pour la citation.

    Une page sans texte extractible est un candidat au scan : elle passe par
    l'OCR avant d'être déclarée vide. Le passage garde la trace de son
    origine (`via_ocr`) — un texte deviné par reconnaissance optique n'a pas
    la même certitude qu'un texte réellement encodé dans le PDF.
    """
    from pypdf import PdfReader

    passages = []
    # Ouvert explicitement, pour fermer le fichier avant de rendre la main —
    # `PdfReader(str(chemin))` ouvre le fichier lui-meme et ne le referme
    # qu'au passage du ramasse-miettes, a un moment indetermine. L'appelant
    # (`DepotPiecesJointes.deposer`) efface ce meme fichier juste apres :
    # sous Windows, l'effacement echouait tant que ce handle restait ouvert
    # (`PermissionError: [WinError 32]`, mesure le 01/09/2026, invisible sur
    # Linux ou `unlink()` efface un fichier meme ouvert).
    with open(chemin, "rb") as flux:
        lecteur = PdfReader(flux)
        for numero, page in enumerate(lecteur.pages, 1):
            try:
                contenu = _nettoyer(page.extract_text() or "")
            except Exception as e:
                # Une couche texte illisible ne faisait perdre la page qu'en
                # silence : elle est tentee par l'OCR, comme un scan. Ce n'est
                # qu'au bout de cet essai qu'elle est laissee de cote — et une
                # page perdue ne fait toujours pas perdre tout le document.
                logger.debug(f"Couche texte illisible a la page {numero} de {chemin.name}, OCR tente : {e}")
                contenu = _nettoyer(_ocr_page(chemin, numero - 1))
                if contenu:
                    passages.append(Passage(texte=contenu, fichier=chemin.name, page=numero, via_ocr=True))
                continue
            via_ocr = False
            if not contenu:
                contenu = _nettoyer(_ocr_page(chemin, numero - 1))
                via_ocr = bool(contenu)
            if contenu:
                passages.append(Passage(texte=contenu, fichier=chemin.name, page=numero, via_ocr=via_ocr))
    return passages


def _lire_docx(chemin: Path) -> List[Passage]:
    """Word : paragraphes et tableaux. Un devis vit souvent dans un tableau."""
    from docx import Document as DocxDocument

    document = DocxDocument(str(chemin))
    morceaux = [p.text for p in document.paragraphs if p.text.strip()]

    for tableau in document.tables:
        for ligne in tableau.rows:
            cellules = [c.text.strip() for c in ligne.cells if c.text.strip()]
            if cellules:
                morceaux.append(" | ".join(cellules))

    contenu = _nettoyer("\n".join(morceaux))
    return [Passage(texte=contenu, fichier=chemin.name)] if contenu else []


def _lire_xlsx(chemin: Path) -> List[Passage]:
    """Excel : un passage par feuille, les lignes vides ignorees.

    `data_only=True` lit la derniere valeur calculee d'une formule, pas sa
    formule elle-meme — un devis dans un tableur montre ses chiffres, pas
    `=B2*C2`.
    """
    from openpyxl import load_workbook

    classeur = load_workbook(str(chemin), data_only=True, read_only=True)
    try:
        passages = []
        for nom_feuille in classeur.sheetnames:
            feuille = classeur[nom_feuille]
            lignes = []
            for ligne in feuille.iter_rows(values_only=True):
                cellules = [str(v).strip() for v in ligne if v is not None and str(v).strip()]
                if cellules:
                    lignes.append(" | ".join(cellules))
            contenu = _nettoyer("\n".join(lignes))
            if contenu:
                passages.append(Passage(texte=contenu, fichier=f"{chemin.name} ({nom_feuille})"))
        return passages
    finally:
        classeur.close()


def _lire_pptx(chemin: Path) -> List[Passage]:
    """PowerPoint : un passage par diapositive, la diapositive vaut la page."""
    from pptx import Presentation

    presentation = Presentation(str(chemin))
    passages = []
    for numero, diapositive in enumerate(presentation.slides, 1):
        morceaux = []
        for forme in diapositive.shapes:
            if forme.has_text_frame and forme.text_frame.text.strip():
                morceaux.append(forme.text_frame.text)
            elif forme.has_table:
                for ligne in forme.table.rows:
                    cellules = [c.text.strip() for c in ligne.cells if c.text.strip()]
                    if cellules:
                        morceaux.append(" | ".join(cellules))
        contenu = _nettoyer("\n".join(morceaux))
        if contenu:
            passages.append(Passage(texte=contenu, fichier=chemin.name, page=numero))
    return passages


LECTEURS = {
    ".pdf": _lire_pdf,
    ".docx": _lire_docx,
    ".txt": _lire_texte_simple,
    ".md": _lire_texte_simple,
    ".csv": _lire_texte_simple,
    ".xlsx": _lire_xlsx,
    ".pptx": _lire_pptx,
}


def lire_document(chemin: Path | str, taille_max: int = TAILLE_MAX_OCTETS) -> Document:
    """Lit un document et renvoie son texte, ou l'état qui explique l'échec."""
    chemin = Path(chemin)

    if not chemin.exists() or not chemin.is_file():
        return _echec(chemin, "ECHEC", "fichier introuvable")

    extension = chemin.suffix.lower()
    if extension not in EXTENSIONS_LISIBLES:
        lisibles = ", ".join(sorted(EXTENSIONS_LISIBLES))
        return _echec(
            chemin, "NON_PRIS_EN_CHARGE",
            f"format {extension or 'sans extension'} ; formats lus : {lisibles}",
        )

    taille = chemin.stat().st_size
    if taille > taille_max:
        return _echec(chemin, "ECHEC", f"fichier trop volumineux ({taille / 1024**2:.0f} Mo)")

    try:
        passages = LECTEURS[extension](chemin)
    except Exception as e:
        return _echec(chemin, "ECHEC", f"{type(e).__name__}: {e}")

    if not passages:
        raison = "aucun texte extractible (document scanne ?)"
        if extension == ".pdf" and langues_ocr() is None:
            raison += (" ; OCR non tente : ni le pack tesseract 'fra' ni le pack 'eng' "
                       "n'est installe sur cette machine")
        return _echec(chemin, "VIDE", raison)

    logger.info(f"Document lu : {chemin.name} ({len(passages)} passage(s))")
    return Document(chemin=chemin, statut="LU", passages=passages)
