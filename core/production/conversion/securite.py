"""Ce qu'un fichier fourni par le propriétaire ne peut pas faire.

Mission « File_Converter_Pro » (08/09/2026), §9 : les fichiers utilisateurs
sont non fiables. Trois familles de garde, chacune vérifiée par un sabotage
dans `tests/core/test_connecteur_file_conversion.py` :

1. **Un chemin d'entrée sensible reste refusé**, même donné explicitement —
   même liste et même logique que `core/connectors/gitingest.py`
   (SEGMENTS_INTERDITS), dupliquée ici plutôt que partagée : les deux
   connecteurs protègent le même risque, pas la même opération (l'un
   ingère un dépôt, l'autre convertit un fichier), et une dépendance
   croisée entre deux connecteurs n'apporterait rien qu'une constante
   recopiée n'apporte déjà.

2. **La sortie n'est jamais un chemin fourni par l'appelant.** Le connecteur
   choisit toujours un nom neuf sous `media/rendered/conversions/` — ça
   ferme à la fois l'écrasement d'un fichier existant et la traversée de
   chemin en écriture, sans avoir besoin de les détecter : il n'y a
   simplement rien à détecter.

3. **Une archive extraite ne peut ni s'évader de son dossier cible, ni
   épuiser la machine.** Chemin de membre résolu hors cible, lien
   symbolique, nombre de membres ou taille décompressée déraisonnable :
   les quatre refusent l'extraction avant d'écrire le moindre octet.
"""
from __future__ import annotations

import zipfile
from pathlib import Path
from typing import List, Optional, Tuple

#: Mêmes segments que `core/connectors/gitingest.py` — un chemin qui les
#: contient n'est jamais un fichier à convertir, quelle que soit la demande.
SEGMENTS_INTERDITS = frozenset({
    ".ssh", ".aws", ".gnupg", ".git-credentials", ".netrc",
    "id_rsa", "id_ed25519", "id_ecdsa",
})
FICHIERS_INTERDITS = frozenset({".env", "credentials.json", "secrets.json"})

#: Un fichier d'entrée plus gros que ça n'est pas traité : la conversion est
#: CPU/mémoire-bornée par le moteur choisi, jamais par un flux. Réglable par
#: appelant (le connecteur le fait dépendre de la famille — vidéo autorisée
#: plus large qu'un document) ; ceci est le plafond par défaut.
TAILLE_MAX_DEFAUT_OCTETS = 300 * 1024 * 1024

#: Une archive ZIP : au-delà, ce n'est plus une extraction raisonnable pour
#: cette machine, que le ratio de compression soit hostile ou non.
ZIP_MEMBRES_MAX = 10_000
ZIP_TAILLE_DECOMPRESSEE_MAX_OCTETS = 2 * 1024 * 1024 * 1024  # 2 Go


def chemin_source_est_sur(chemin: str) -> Tuple[Optional[Path], Optional[str]]:
    """`(chemin résolu, None)` si convertible, `(None, raison)` sinon.

    Résout AVANT de comparer : un `..` ou un lien symbolique qui vise un
    dossier interdit doit être refusé sur ce qu'il atteint réellement, pas
    sur le texte de la demande.
    """
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


def taille_acceptable(chemin: Path, plafond: Optional[int] = None) -> Optional[str]:
    """`None` si la taille passe, sinon la raison du refus.

    `plafond=None` relit `TAILLE_MAX_DEFAUT_OCTETS` au moment de l'appel,
    jamais figé en valeur par défaut au chargement du module — un test qui
    règle ce plafond plus bas doit pouvoir le vérifier sans redémarrer
    Python (`monkeypatch.setattr(securite, "TAILLE_MAX_DEFAUT_OCTETS", ...)`).
    """
    if plafond is None:
        plafond = TAILLE_MAX_DEFAUT_OCTETS
    taille = chemin.stat().st_size
    if taille <= 0:
        return "fichier vide"
    if taille > plafond:
        return (f"fichier trop volumineux ({taille / 1_048_576:.1f} Mo, "
                f"plafond {plafond / 1_048_576:.0f} Mo)")
    return None


def extraction_zip_sure(archive: Path, cible: Path) -> Optional[str]:
    """`None` si `archive` peut être extraite dans `cible`, sinon pourquoi pas.

    Vérifie TOUT avant d'écrire un seul octet : une archive refusée à la
    moitié de son extraction laisserait des fichiers partiels sur le disque.
    """
    try:
        with zipfile.ZipFile(archive) as zf:
            infos = zf.infolist()
            if len(infos) > ZIP_MEMBRES_MAX:
                return f"archive refusée : {len(infos)} membres (plafond {ZIP_MEMBRES_MAX})"

            total_decompresse = 0
            cible_resolue = cible.resolve()
            for info in infos:
                # Lien symbolique : bit Unix S_IFLNK dans les 16 bits hauts de
                # external_attr. Un membre qui en est un peut pointer n'importe
                # où une fois extrait ; il ne l'est jamais.
                mode_unix = info.external_attr >> 16
                if mode_unix and (mode_unix & 0o170000) == 0o120000:
                    return f"archive refusée : « {info.filename} » est un lien symbolique"

                destination = (cible_resolue / info.filename).resolve()
                if destination != cible_resolue and cible_resolue not in destination.parents:
                    return f"archive refusée : « {info.filename} » sort du dossier cible"

                total_decompresse += info.file_size
                if total_decompresse > ZIP_TAILLE_DECOMPRESSEE_MAX_OCTETS:
                    return (f"archive refusée : plus de "
                            f"{ZIP_TAILLE_DECOMPRESSEE_MAX_OCTETS / 1_073_741_824:.0f} Go "
                            f"une fois décompressée")

            membre_corrompu = zf.testzip()
            if membre_corrompu is not None:
                return f"archive corrompue : « {membre_corrompu} » ne se relit pas"
    except zipfile.BadZipFile as erreur:
        return f"archive illisible : {erreur}"

    return None


#: Formats Office Open XML/OpenDocument : des conteneurs ZIP. Un fichier qui
#: porte l'extension mais n'en est pas un n'est pas un docx corrompu au sens
#: normal — LibreOffice l'ouvre alors en RÉCUPÉRATION texte brut et produit
#: une sortie qui se relit très bien (mesuré le 08/09/2026 : un `.docx`
#: rempli d'octets arbitraires devient un PDF de 9 Ko, valide), ce qui
#: masquerait un vrai fichier corrompu derrière un « succès » trompeur.
FORMATS_ZIP_OFFICE = frozenset({"docx", "pptx", "xlsx", "odt", "odp", "ods"})


def format_source_coherent(chemin: Path, format_source: str) -> Optional[str]:
    """`None` si le contenu ressemble vraiment au format que l'extension
    annonce. Une vérification légère — les octets magiques, pas un parseur
    complet — mais suffisante pour distinguer un docx d'un fichier renommé.
    """
    if format_source in FORMATS_ZIP_OFFICE:
        import zipfile
        if not zipfile.is_zipfile(chemin):
            return (f"« .{format_source} » attendu, mais le fichier n'est pas un "
                    f"conteneur ZIP valide (Office Open XML/OpenDocument en sont toujours)")
    elif format_source == "pdf":
        with open(chemin, "rb") as f:
            entete = f.read(5)
        if entete != b"%PDF-":
            return "« .pdf » attendu, mais le fichier ne commence pas par l'en-tête PDF"
    return None


def noms_zip(chemins: List[Path]) -> Optional[str]:
    """`None` si tous les fichiers à compresser existent réellement."""
    for chemin in chemins:
        if not chemin.is_file():
            return f"« {chemin.name} » n'existe pas ou n'est pas un fichier"
    return None
