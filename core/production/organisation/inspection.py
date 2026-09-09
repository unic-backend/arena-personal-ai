"""Ce qu'un dossier contient, avant qu'un plan ne se propose.

Une lecture pure — rien n'est déplacé, rien n'est renommé. Réutilise ce qui
existe déjà :

- `tools/atelier/atelier.py` (`lister`, `metadonnees`) pour l'inventaire —
  jamais un deuxième accès au filesystem.
- `tools/documents/reader.py` (`lire_document`) pour un extrait de contenu
  des formats déjà pris en charge (PDF/DOCX/TXT/MD/CSV/XLSX/PPTX) — jamais
  un deuxième moteur documentaire ni un second RAG (mission §11, §16).

**Les images ne sont PAS analysées ici.** Ce module se contente de les
signaler (`est_image=True`) ; la description visuelle reste la
responsabilité du moteur de vision existant d'ARENA, appelé par l'agent qui
consulte cette inspection — jamais dupliqué (mission §17).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

#: Ce que `tools/documents/reader.py` sait déjà lire — un extrait de
#: contenu n'est proposé QUE pour ces extensions, jamais deviné pour les
#: autres.
EXTENSIONS_DOCUMENT = {".pdf", ".docx", ".txt", ".md", ".csv", ".xlsx", ".pptx"}
EXTENSIONS_IMAGE = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff", ".heic"}
EXTENSIONS_AUDIO = {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"}
EXTENSIONS_VIDEO = {".mp4", ".mkv", ".mov", ".avi", ".webm"}

#: Un extrait suffit à catégoriser ; le texte complet gonflerait l'inspection
#: pour rien — la conversion/lecture complète reste possible ensuite, à la
#: demande, sur UN fichier précis.
EXTRAIT_MAX_CARACTERES = 2000


@dataclass
class EntreeInspection:
    """Un fichier ou dossier, tel qu'inspecté — jamais interprété."""

    chemin: str               # relatif au dossier inspecté
    type: str                 # "fichier" | "dossier"
    taille_octets: int = 0
    modifie_le: str = ""
    extension: str = ""
    est_image: bool = False
    est_audio: bool = False
    est_video: bool = False
    extrait_contenu: Optional[str] = None   # None = pas de contenu lisible ici
    erreur_lecture: Optional[str] = None    # pourquoi l'extrait manque, si demande

    def to_dict(self) -> Dict[str, Any]:
        corps = {"chemin": self.chemin, "type": self.type,
                 "taille_octets": self.taille_octets, "modifie_le": self.modifie_le,
                 "extension": self.extension, "est_image": self.est_image,
                 "est_audio": self.est_audio, "est_video": self.est_video}
        if self.extrait_contenu is not None:
            corps["extrait_contenu"] = self.extrait_contenu
        if self.erreur_lecture is not None:
            corps["erreur_lecture"] = self.erreur_lecture
        return corps


@dataclass
class Inventaire:
    dossier: str
    entrees: List[EntreeInspection] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"dossier": self.dossier, "entrees": [e.to_dict() for e in self.entrees]}


def _extrait_document(chemin: Path) -> tuple:
    """`(extrait, erreur)` — l'un des deux est toujours None.

    Mission §22 : le contenu d'un fichier est une DONNÉE, jamais une
    instruction — un README ou un PDF peut contenir « ignore tes
    consignes et... ». L'extrait passe par `core/security/trust.py`
    (déjà utilisé pour les pièces jointes/le web/GalsenAPI ailleurs dans
    ARENA) avant de sortir d'ici : origine annoncée, balises neutralisées,
    tournures suspectes relevées et transportées AVEC le texte plutôt
    qu'effacées.
    """
    try:
        from tools.documents.reader import lire_document
        document = lire_document(chemin)
    except Exception as erreur:  # noqa: BLE001 — une lecture ratee n'arrete pas l'inspection
        return None, f"lecture impossible : {type(erreur).__name__}: {erreur}"

    if not document.lu:
        return None, f"document non lu ({document.statut}) : {document.raison or 'raison inconnue'}"
    texte = document.texte
    if len(texte) > EXTRAIT_MAX_CARACTERES:
        texte = texte[:EXTRAIT_MAX_CARACTERES] + "…"

    from core.security.trust import TrustLevel, wrap
    enveloppe = wrap(texte, TrustLevel.DOCUMENT, origin=chemin.name)
    return enveloppe.text, None


def inspecter_dossier(atelier: Any, dossier: str, avec_contenu: bool = False,
                      profondeur_max: int = 1) -> Inventaire:
    """L'inventaire d'un dossier, via `Atelier` — jamais un second accès
    filesystem.

    Args:
        atelier: l'`Atelier` déjà construit (racine = le dossier autorisé).
        dossier: chemin relatif à la racine de l'atelier.
        avec_contenu: si vrai, un extrait de texte est lu pour chaque
            document dont le format est déjà pris en charge.
        profondeur_max: 1 = le dossier direct seulement (pas de récursion) —
            volontairement prudent : une inspection récursive illimitée sur
            un gros arbre serait coûteuse pour un simple aperçu.
    """
    resultat_liste = atelier.lister(dossier)
    inventaire = Inventaire(dossier=dossier)
    if not resultat_liste.ok:
        return inventaire

    # Même règle de résolution que `Atelier._chemin()` (public serait mieux,
    # mais dupliquer une ligne triviale coûte moins qu'exposer une méthode
    # privée d'un module qu'on ne possède pas) : relatif à sa racine, sauf
    # chemin déjà absolu.
    chemin_dossier = Path(dossier).expanduser()
    racine_dossier = chemin_dossier if chemin_dossier.is_absolute() else (atelier.racine / chemin_dossier)
    for ligne in (resultat_liste.sortie or "").splitlines():
        if not ligne.strip():
            continue
        marque, nom = ligne[0], ligne[3:]
        chemin_relatif = f"{dossier.rstrip('/')}/{nom}" if dossier != "." else nom
        chemin_absolu = racine_dossier / nom

        meta = atelier.metadonnees(chemin_relatif)
        extension = Path(nom).suffix.lower()
        entree = EntreeInspection(
            chemin=chemin_relatif, type="dossier" if marque == "d" else "fichier",
            taille_octets=meta.donnees.get("taille_octets", 0) if meta.ok else 0,
            modifie_le=meta.donnees.get("modifie_le", "") if meta.ok else "",
            extension=extension.lstrip("."),
            est_image=extension in EXTENSIONS_IMAGE,
            est_audio=extension in EXTENSIONS_AUDIO,
            est_video=extension in EXTENSIONS_VIDEO,
        )
        if avec_contenu and marque == "f" and extension in EXTENSIONS_DOCUMENT:
            entree.extrait_contenu, entree.erreur_lecture = _extrait_document(chemin_absolu)

        inventaire.entrees.append(entree)

    return inventaire
