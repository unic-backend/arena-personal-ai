"""La chaine vocale d'ARENA, mesuree sur SA machine — jamais estimee ici.

    python scripts/verifier_voix.py
    python scripts/verifier_voix.py --usage recherche
    python scripts/verifier_voix.py --ref-audio media/ma_voix.wav \
        --autorisation "Ousmane Diop, proprietaire de la voix"

Ce que la commande fait, dans l'ordre, et **en passant par ARENA** (le
connecteur et son routeur, jamais VoiceStudio en direct — sinon elle
mesurerait VoiceStudio, pas ARENA) :

1. l'appareil reellement utilise par chaque moteur (`effective_device`), et
   lesquels sont ecartes pour cause de licence non commerciale ;
2. une synthese reelle par langue demandee, chronometree ;
3. la verification physique de chaque fichier : il existe, il pese quelque
   chose, sa duree est lisible, sa cadence est connue, **et il n'est pas
   silencieux** ;
4. le facteur temps reel (RTF) mesure, pas repris d'une fiche produit ;
5. le voice design (`instruct`) et le clonage, seulement s'ils sont demandes
   et possibles.

Ce qu'elle ne fait pas : installer, telecharger, demarrer VoiceStudio, ni
remplacer une mesure absente par un chiffre plausible. VoiceStudio eteint,
la sortie est `NON_CONFIGURE` ligne par ligne, et c'est le resultat correct.

**Le clonage n'est tente que si `--ref-audio` ET `--autorisation` sont
donnes.** Une voix sans autorisation declaree n'est jamais clonee, ici pas
plus qu'ailleurs.
"""
from __future__ import annotations

import argparse
import sys
import time
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

from core.actions.resultat import Statut  # noqa: E402
from core.connectors.audio_voix import ConnecteurAudioVoix  # noqa: E402

#: Les langues mesurees par defaut. Le wolof est la parce que c'est la langue
#: de ses chantiers ; il n'est PAS suppose fonctionner — c'est ce que cette
#: commande sert a savoir.
LANGUES = {"fr": "Bonjour, ceci est un essai de voix pour UniC Plaquiste.",
           "en": "Hello, this is a voice test for UniC Plaquiste.",
           "wo": "Salaam aleekum, jamm nga fanaane."}


def mesurer_le_wav(chemin: Path) -> Dict[str, Any]:
    """Ce qu'un WAV dit de lui-meme, sans ffmpeg — le CI n'en a pas, lui non plus.

    `amplitude_max` est la mesure qui compte : un fichier de la bonne taille,
    de la bonne duree et parfaitement silencieux est un echec, et seule
    l'amplitude le montre. Un champ non mesurable reste `None`.
    """
    mesure: Dict[str, Any] = {"octets": None, "secondes": None, "cadence": None,
                              "canaux": None, "amplitude_max": None, "lisible": False}
    if not chemin.is_file():
        return mesure
    mesure["octets"] = chemin.stat().st_size
    try:
        with wave.open(str(chemin), "rb") as flux:
            mesure["cadence"] = flux.getframerate()
            mesure["canaux"] = flux.getnchannels()
            images = flux.getnframes()
            mesure["secondes"] = round(images / flux.getframerate(), 3) if flux.getframerate() else None
            largeur = flux.getsampwidth()
            brut = flux.readframes(images)
            mesure["lisible"] = True
    except (wave.Error, OSError, EOFError):
        return mesure

    if largeur == 2 and brut:
        mesure["amplitude_max"] = max(
            abs(int.from_bytes(brut[i:i + 2], "little", signed=True))
            for i in range(0, len(brut) - 1, 2))
    return mesure


def _verdict(mesure: Dict[str, Any]) -> str:
    if not mesure["lisible"]:
        return "ECHEC (fichier illisible)"
    if not mesure["secondes"]:
        return "ECHEC (duree nulle)"
    if mesure["amplitude_max"] is None:
        return "PARTIEL (amplitude non mesurable : echantillons hors 16 bits)"
    if mesure["amplitude_max"] == 0:
        return "ECHEC (fichier parfaitement silencieux)"
    return "OK"


def afficher_les_moteurs(connecteur: ConnecteurAudioVoix) -> bool:
    resultat = connecteur.executer_confirmee("moteurs")
    print(f"[{resultat.statut.value}] {resultat.message}")
    if resultat.statut is not Statut.SUCCES:
        return False
    for moteur in resultat.detail.get("voix", []):
        print(f"    - {moteur['id']:<22} appareil={moteur['appareil'] or 'UNKNOWN'} "
              f"routage={moteur['routage'] or 'UNKNOWN'} "
              f"commercial={moteur['usage_commercial']} ({moteur['licence']})")
    return True


def synthetiser(connecteur: ConnecteurAudioVoix, texte: str, langue: str,
                usage: str, instruct: str = "") -> None:
    debut = time.perf_counter()
    resultat = connecteur.executer_confirmee(
        "parler", texte=texte, langue=langue, usage=usage, instruct=instruct)
    ecoule = time.perf_counter() - debut

    etiquette = f"{langue}{' + instruct' if instruct else ''}"
    if resultat.statut is not Statut.SUCCES:
        print(f"  {etiquette:<16} [{resultat.statut.value}] {resultat.message}")
        return

    mesure = mesurer_le_wav(Path(resultat.preuve))
    rtf = (round(ecoule / mesure["secondes"], 3)
           if mesure["secondes"] else "UNKNOWN")
    print(f"  {etiquette:<16} {_verdict(mesure)} — moteur={resultat.detail['moteur']} "
          f"appareil={resultat.detail['appareil'] or 'UNKNOWN'} "
          f"duree={mesure['secondes']}s cadence={mesure['cadence']} "
          f"amplitude={mesure['amplitude_max']} genere_en={ecoule:.2f}s RTF={rtf}")


def cloner(connecteur: ConnecteurAudioVoix, ref_audio: str, autorisation: str,
           usage: str) -> None:
    debut = time.perf_counter()
    resultat = connecteur.executer_confirmee(
        "cloner", texte=LANGUES["fr"], ref_audio=ref_audio,
        autorisation=autorisation, usage=usage)
    ecoule = time.perf_counter() - debut

    if resultat.statut is not Statut.SUCCES:
        print(f"  clonage          [{resultat.statut.value}] {resultat.message}")
        return
    mesure = mesurer_le_wav(Path(resultat.preuve))
    print(f"  clonage          {_verdict(mesure)} — moteur={resultat.detail['moteur']} "
          f"duree={mesure['secondes']}s amplitude={mesure['amplitude_max']} "
          f"genere_en={ecoule:.2f}s")


def principal(arguments: Optional[List[str]] = None) -> int:
    analyseur = argparse.ArgumentParser(description=__doc__)
    analyseur.add_argument("--usage", default="commercial",
                           help="commercial (defaut) ou recherche")
    analyseur.add_argument("--langues", default=",".join(LANGUES),
                           help="langues a mesurer, separees par des virgules")
    analyseur.add_argument("--instruct", default="femme, voix grave, accent africain",
                           help="voice design a essayer ; vide pour ne pas l'essayer")
    analyseur.add_argument("--ref-audio", default="",
                           help="enregistrement de reference pour le clonage")
    analyseur.add_argument("--autorisation", default="",
                           help="qui a autorise cette voix — obligatoire pour cloner")
    options = analyseur.parse_args(arguments)

    connecteur = ConnecteurAudioVoix()
    print("=== Moteurs, appareils et licences ===")
    if not afficher_les_moteurs(connecteur):
        print("\nRien d'autre ne peut etre mesure sans VoiceStudio. "
              "Tout le reste est UNKNOWN, et le rester est le bon resultat.")
        return 1

    print(f"\n=== Synthese reelle (usage : {options.usage}) ===")
    for langue in [code.strip() for code in options.langues.split(",") if code.strip()]:
        synthetiser(connecteur, LANGUES.get(langue, LANGUES["fr"]), langue,
                    options.usage)

    if options.instruct:
        print("\n=== Voice design (`instruct`) ===")
        synthetiser(connecteur, LANGUES["fr"], "fr", options.usage,
                    instruct=options.instruct)

    print("\n=== Clonage ===")
    if options.ref_audio and options.autorisation:
        cloner(connecteur, options.ref_audio, options.autorisation, options.usage)
    else:
        print("  clonage          NON TENTE — il faut --ref-audio ET --autorisation. "
              "Une voix sans autorisation declaree ne se clone pas.")

    print("\nMesure faite sur cette machine, a cet instant. Elle ne se recopie "
          "pas : elle se relance.")
    return 0


if __name__ == "__main__":
    raise SystemExit(principal())
