"""Ce que deux connecteurs audio ont en commun, partage une seule fois.

`core/connectors/audio_voix.py` (VoiceStudio) et `core/connectors/csm.py`
(Sesame CSM) parlent tous les deux a un service SEPARE sur la boucle locale,
puis verifient de la meme facon le fichier que ce service vient d'ecrire.
Avant ce module, cette logique n'existait que dans `audio_voix.py` ; l'ajout
de CSM (mission Sesame CSM, DEC-0080) l'aurait copiee — exactement ce que
cette meme mission interdit ("DO NOT duplicate... existing audio
processing"). Elle vit ici, une fois, importee par les deux.

Deux regles, identiques a celles qui existaient deja dans `audio_voix.py` et
qui ne changent pas de sens en changeant de fichier :

1. **Rien ne sort de la machine.** Un service de voix ecoute sur la boucle
   locale ; une adresse qui n'y est pas est refusee, jamais suivie.
2. **Le succes est le fichier, pas la reponse HTTP.** Un `200` ne suffit pas :
   le fichier est re-sonde avec `ffprobe`, et une duree nulle est un echec.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

logger = logging.getLogger("usman.connecteurs.audio")

#: Les hotes acceptes pour tout service de voix qu'ARENA pilote par HTTP.
HOTES_LOCAUX = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})


class AdresseNonLocale(ValueError):
    """L'URL configuree pour un service de voix sort de la machine."""


def hote_local_ou_refuse(url: str, nom_variable: str) -> str:
    """`url`, ou lève si son hôte n'est pas la boucle locale.

    Args:
        url: l'adresse configuree (deja nettoyee de son `/` final).
        nom_variable: le nom de la variable d'environnement, pour le message.

    Raises:
        AdresseNonLocale: l'hote configure n'est pas local.
    """
    hote = urlparse(url).hostname
    if hote not in HOTES_LOCAUX:
        raise AdresseNonLocale(
            f"{nom_variable} pointe vers « {hote} », hors de cette machine. "
            "Les voix et les enregistrements restent locaux : refuse."
        )
    return url


def ressemble_a_du_wav(chemin: Path) -> bool:
    """Le fichier porte-t-il l'en-tête d'un WAV : « RIFF » … « WAVE » ?

    Ce n'est **pas** une mesure de durée et ne la remplace pas. C'est le seul
    contrôle possible quand `ffprobe` manque, et il suffit à distinguer un son
    d'un message d'erreur qu'un service de voix aurait renvoyé avec un code
    200 — ce que `sonder_le_fichier` cherche précisément à attraper.
    """
    try:
        with chemin.open("rb") as flux:
            entete = flux.read(12)
    except OSError:
        return False
    return entete[:4] == b"RIFF" and entete[8:12] == b"WAVE"


def sonder_le_fichier(chemin: Path, ffprobe: str = "ffprobe") -> Dict[str, Any]:
    """Ce que ffprobe mesure sur un fichier audio. Rien n'est suppose.

    Un champ que la sonde ne donne pas reste `None` — jamais `0`, qui se
    lirait comme une mesure.

    `sonde_disponible` dit si `ffprobe` a pu repondre. **Sans lui, `duree_ms`
    vaut `None` pour une raison qui ne concerne pas le fichier**, et confondre
    les deux revenait a jeter un son valide : mesure du 02/09/2026, un WAV
    reel de 2 s et 176 478 octets supprime parce que `ffprobe` manquait.
    """
    inconnu: Dict[str, Any] = {"duree_ms": None, "octets": None, "format": None,
                               "sonde_disponible": None}
    if not chemin.is_file():
        return inconnu
    inconnu["octets"] = chemin.stat().st_size
    try:
        sortie = subprocess.run(
            [ffprobe, "-v", "error", "-show_entries",
             "format=duration,format_name", "-of", "default=nw=1:nk=1", str(chemin)],
            capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as erreur:
        logger.warning("ffprobe indisponible pour %s : %s", chemin, erreur)
        inconnu["sonde_disponible"] = False
        return inconnu

    inconnu["sonde_disponible"] = True
    # L'ordre des lignes n'est PAS celui demande a `-show_entries` : ffprobe
    # rend `format_name` d'abord, `duration` ensuite. Lire « la derniere
    # ligne » comme le format laissait donc ce champ toujours `None`, sur des
    # fichiers parfaitement mesurables (mesure du 02/09/2026). Chaque ligne est
    # maintenant reconnue pour ce qu'elle est, jamais pour sa position.
    for brute in sortie.stdout.splitlines():
        ligne = brute.strip()
        if not ligne:
            continue
        try:
            duree = float(ligne)
        except ValueError:
            if inconnu["format"] is None:
                inconnu["format"] = ligne
        else:
            if inconnu["duree_ms"] is None:
                inconnu["duree_ms"] = int(round(duree * 1000))
    return inconnu
