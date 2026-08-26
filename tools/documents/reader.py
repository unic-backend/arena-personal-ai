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

logger = logging.getLogger("arena.tools.documents")

# Formats que ce module sait ouvrir. Une extension absente d'ici est refusee
# explicitement, elle n'est pas ignoree en silence.
EXTENSIONS_LISIBLES = {".pdf", ".docx", ".txt", ".md", ".csv"}

# Un document plus gros que cela est probablement une archive ou une video mal
# nommee ; le lire d'un bloc occuperait la memoire pour rien.
TAILLE_MAX_OCTETS = 50 * 1024 * 1024


@dataclass
class Passage:
    """Un morceau de texte, et l'endroit exact d'ou il vient."""

    texte: str
    fichier: str
    page: Optional[int] = None

    @property
    def source(self) -> str:
        """Libellé lisible de la provenance, tel qu'il sera cité."""
        return f"{self.fichier}, page {self.page}" if self.page else self.fichier


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


def _lire_pdf(chemin: Path) -> List[Passage]:
    """PDF : un passage par page, la page est conservée pour la citation."""
    from pypdf import PdfReader

    lecteur = PdfReader(str(chemin))
    passages = []
    for numero, page in enumerate(lecteur.pages, 1):
        try:
            contenu = _nettoyer(page.extract_text() or "")
        except Exception as e:
            # Une page illisible ne doit pas faire perdre tout le document.
            logger.debug(f"Page {numero} illisible dans {chemin.name} : {e}")
            continue
        if contenu:
            passages.append(Passage(texte=contenu, fichier=chemin.name, page=numero))
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


LECTEURS = {
    ".pdf": _lire_pdf,
    ".docx": _lire_docx,
    ".txt": _lire_texte_simple,
    ".md": _lire_texte_simple,
    ".csv": _lire_texte_simple,
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
        return _echec(chemin, "VIDE", "aucun texte extractible (document scanne ?)")

    logger.info(f"Document lu : {chemin.name} ({len(passages)} passage(s))")
    return Document(chemin=chemin, statut="LU", passages=passages)
