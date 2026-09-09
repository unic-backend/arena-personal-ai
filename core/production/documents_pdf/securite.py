"""Un PDF fourni par le propriétaire n'est pas fiable — mission §18.

Même liste que `core/production/conversion/securite.py` et
`core/connectors/gitingest.py` : le même risque, recopié plutôt que
partagé entre connecteurs qui ne protègent pas la même opération.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

SEGMENTS_INTERDITS = frozenset({
    ".ssh", ".aws", ".gnupg", ".git-credentials", ".netrc",
    "id_rsa", "id_ed25519", "id_ecdsa",
})
FICHIERS_INTERDITS = frozenset({".env", "credentials.json", "secrets.json"})

#: Au-delà, un PDF n'est pas traité — CPU/mémoire d'une machine personnelle,
#: pas d'un serveur dédié. Mesuré le 09/09/2026 : 500 pages réelles pèsent
#: 0,12 Mo et s'ouvrent en 56 ms ; ce plafond vise les PDF hostiles
#: (beaucoup d'objets, peu de contenu utile), pas l'usage normal.
TAILLE_MAX_OCTETS = 200 * 1024 * 1024

#: Au-delà, une opération de pages n'est pas raisonnable pour un seul appel
#: synchrone — mesuré : 100 fichiers fusionnés en 0,29 s, largement en
#: dessous. Le plafond protège contre un nombre de pages absurde, pas contre
#: la lenteur mesurée ici.
PAGES_MAX = 5000


def chemin_source_est_sur(chemin: str) -> Tuple[Optional[Path], Optional[str]]:
    """`(chemin résolu, None)` si le fichier peut être ouvert, `(None, raison)` sinon."""
    brut = Path(chemin).expanduser()
    try:
        resolu = brut.resolve()
    except OSError as erreur:
        return None, f"chemin illisible : {erreur}"

    segments_bas = {p.lower() for p in resolu.parts}
    trouve = SEGMENTS_INTERDITS & segments_bas
    if trouve:
        return None, f"chemin sensible refusé (« {sorted(trouve)[0]} » dans le chemin)"
    if resolu.name.lower() in FICHIERS_INTERDITS:
        return None, f"chemin sensible refusé (« {resolu.name} »)"
    if not resolu.is_file():
        return None, "fichier introuvable"

    return resolu, None


def taille_acceptable(chemin: Path) -> Optional[str]:
    taille = chemin.stat().st_size
    if taille <= 0:
        return "fichier vide"
    if taille > TAILLE_MAX_OCTETS:
        return (f"fichier trop volumineux ({taille / 1_048_576:.1f} Mo, "
                f"plafond {TAILLE_MAX_OCTETS / 1_048_576:.0f} Mo)")
    return None


def format_source_coherent(chemin: Path) -> Optional[str]:
    """`None` si le fichier commence vraiment par l'en-tête PDF.

    Mesuré le 08/09/2026 (mission File_Converter_Pro) : LibreOffice
    « récupérait » un fichier mal étiqueté sans jamais dire qu'il n'était
    pas ce qu'il prétendait. `pypdf` fait la même chose sur un flux
    suffisamment proche d'un PDF — la vérification des octets magiques,
    ici comme là-bas, reste la seule chose qui referme ce cas.
    """
    with open(chemin, "rb") as f:
        entete = f.read(5)
    if entete != b"%PDF-":
        return "le fichier ne commence pas par l'en-tête PDF (« %PDF- »)"
    return None


def nombre_de_pages_acceptable(n: int) -> Optional[str]:
    if n <= 0:
        return "le PDF n'a aucune page"
    if n > PAGES_MAX:
        return f"{n} pages, plafond {PAGES_MAX}"
    return None


def indices_valides(indices: List[int], nombre_de_pages: int) -> Optional[str]:
    """`None` si tous les indices (0-based) tombent réellement dans le
    document, sinon la raison — jamais un `IndexError` opaque plus loin."""
    if not indices:
        return "aucune page indiquée"
    hors_bornes = [i for i in indices if i < 0 or i >= nombre_de_pages]
    if hors_bornes:
        return (f"page(s) {hors_bornes} hors bornes — le document a "
                f"{nombre_de_pages} page(s) (index 0 à {nombre_de_pages - 1})")
    return None
