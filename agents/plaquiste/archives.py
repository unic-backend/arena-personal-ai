"""Les documents reels d'UniC Plaquiste, retrouves par la demande.

La phase 1 a donne les prix. Elle n'a pas donne les **formulations** : la facon
dont le proprietaire annonce un geste commercial, explique la surface
developpee, ou liste ce qui n'est pas inclus. Ces phrases sont dans ses devis,
pas dans une grille de tarifs.

Ce module lit ses documents et rend les passages qui parlent de la demande. Il
ne resume pas, ne reformule pas, n'invente pas : il **cite**, avec le nom du
fichier et le numero de page.

Aucune dependance nouvelle, aucun modele : `tools/documents/reader.py` sait
deja lire un PDF page par page, et la selection se fait sur les mots. Le jour
ou une recherche semantique existera, elle remplacera `_pertinence` sans
toucher au reste.

**Les documents ne sont pas dans le depot.** Ils portent le nom du client, ses
montants et le lieu du chantier. Le dossier est local et ignore par git.
"""
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from tools.documents.reader import lire_document

logger = logging.getLogger("usman.agent.plaquiste.archives")

DOSSIER_ARCHIVES = Path(__file__).resolve().parents[2] / "documents" / "unic_plaquiste"

EXTENSIONS = (".pdf", ".docx", ".txt", ".md")

# Le mode d emploi du dossier n est pas une archive du proprietaire.
FICHIERS_IGNORES = {"lisez_moi.md", "readme.md"}

# Mots trop courants pour distinguer un passage d'un autre.
MOTS_VIDES = {
    "le", "la", "les", "un", "une", "des", "du", "de", "et", "ou", "a", "au",
    "aux", "en", "pour", "par", "sur", "dans", "avec", "que", "qui", "est",
    "sont", "ce", "cette", "ces", "il", "elle", "je", "tu", "nous", "vous",
    "fais", "fait", "faire", "moi", "mon", "ma", "mes", "plus", "tout",
}

ACCENTS = str.maketrans("àâäéèêëîïôöùûüç", "aaaeeeeiioouuuc")


def _mots(texte: str) -> set:
    bruts = re.findall(r"[\w'-]{3,}", (texte or "").lower().translate(ACCENTS))
    return {m.strip("'-") for m in bruts} - MOTS_VIDES


@dataclass
class Extrait:
    """Un passage retenu, et d'ou il vient."""

    texte: str
    source: str
    score: int


def documents_disponibles(dossier: Path = DOSSIER_ARCHIVES) -> List[Path]:
    """Liste les fichiers lisibles du dossier d'archives. Vide si absent."""
    if not dossier.is_dir():
        return []
    return sorted(
        chemin for chemin in dossier.iterdir()
        if chemin.is_file()
        and chemin.suffix.lower() in EXTENSIONS
        and chemin.name.lower() not in FICHIERS_IGNORES
    )


def _pertinence(passage: str, attendus: set) -> int:
    """Nombre de mots de la demande presents dans le passage."""
    return len(attendus & _mots(passage))


def extraits_pour(
    demande: str,
    dossier: Path = DOSSIER_ARCHIVES,
    maximum: int = 4,
    taille_max: int = 900,
) -> List[Extrait]:
    """Rend les passages des archives qui parlent de la demande.

    Liste vide quand rien ne correspond — et c'est une reponse, pas un echec :
    l'agent dira qu'il n'a pas trouve, au lieu de citer un passage hors sujet.
    """
    attendus = _mots(demande)
    if not attendus:
        return []

    trouves: List[Extrait] = []
    for chemin in documents_disponibles(dossier):
        document = lire_document(chemin)
        if not document.lu:
            logger.warning("Archive illisible : %s (%s)", chemin.name, document.raison)
            continue
        for passage in document.passages:
            score = _pertinence(passage.texte, attendus)
            if score:
                trouves.append(Extrait(passage.texte[:taille_max], passage.source, score))

    trouves.sort(key=lambda e: e.score, reverse=True)
    if trouves:
        logger.info("%d extrait(s) retenu(s) dans les archives.", min(len(trouves), maximum))
    return trouves[:maximum]


def formater(extraits: List[Extrait]) -> Optional[str]:
    """Met les extraits en forme pour le prompt, provenance comprise.

    Rend `None` s'il n'y a rien : l'appelant doit pouvoir distinguer « pas
    d'archive » de « une archive vide ».
    """
    if not extraits:
        return None
    blocs = [
        "DOCUMENTS REELS D'UNIC PLAQUISTE — reprends ces formulations telles quelles.",
        "Cite la provenance quand tu t'appuies dessus. N'invente aucun chiffre "
        "qui ne s'y trouve pas.",
        "",
    ]
    for numero, extrait in enumerate(extraits, 1):
        blocs.append(f"[{numero}] ({extrait.source})\n{extrait.texte}")
    return "\n\n".join(blocs)
