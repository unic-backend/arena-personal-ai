"""Ce que la machine branchée sait réellement faire, capacité par capacité.

**Mesuré le 03/09/2026.** Le propriétaire coche « Narration », « Vision »,
« Génération de scène » depuis son téléphone, branché sur Railway. Rien de tout
cela n'existe là-bas : ni Ollama, ni VoiceStudio, ni WanGP, ni
MoneyPrinterTurbo, ni Deep-Live-Cam — ils tournent tous sur son PC. Le projet
partait quand même, et il recevait `All connection attempts failed` après coup.

Le panneau proposait sept capacités sans jamais demander lesquelles la machine
branchée pouvait tenir. **Il n'avait aucun moyen de le demander : la route
n'existait pas.**

Rien n'est deviné ici. Chaque capacité est renvoyée à la sonde qui la mesure
déjà — celle du connecteur, celle du fournisseur — plutôt qu'à une seconde
logique qui pourrait diverger. C'est la discipline de `scripts/doctor.py`, et
c'est elle qui fait qu'une capacité ne peut pas être annoncée disponible par un
fichier pendant qu'un autre la mesure absente.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from core.connectors.base import EtatSante

#: Les capacités portées par un connecteur, et le connecteur qui les porte.
#: `montage` compte parmi elles : ffmpeg est local, donc il peut manquer.
PAR_CONNECTEUR: Dict[str, str] = {
    "wangp": "wan2gp",
    "moneyprinter": "moneyprinter",
    "narration": "audio",
    "transcription": "audio",
    "xaar_kaname": "xaar_kaname",
    "montage": "montage",
    "krillin_subtitle": "krillinai",
    "krillin_tts": "krillinai",
    "krillin_render_horizontal": "krillinai",
    "krillin_render_vertical": "krillinai",
    "krillin_cover": "krillinai",
}


def _depuis_connecteur(registre: Any, nom: str) -> Dict[str, Any]:
    """L'état d'un connecteur, par sa propre sonde.

    Une panne d'un connecteur marque SA ligne, jamais tout le rapport : sans
    cela, un moteur qui lève ferait disparaître les six autres réponses et le
    panneau n'afficherait plus rien du tout.
    """
    try:
        sante = registre.obtenir(nom).sonder()
    except Exception as erreur:  # noqa: BLE001 — un rapport ne meurt pas d'une panne qu'il rapporte
        return {
            "disponible": False,
            "raison": f"sonde en echec : {type(erreur).__name__}",
        }

    if sante.etat is EtatSante.OPERATIONNEL:
        return {"disponible": True, "raison": ""}

    raison = sante.message or sante.etat.value
    if sante.ce_qui_manque:
        raison = f"{raison} ({sante.ce_qui_manque})"
    return {"disponible": False, "raison": raison}


async def disponibilite_video(
    registre: Any,
    fournisseur_vision: Optional[Any] = None,
) -> Dict[str, Dict[str, Any]]:
    """Pour chaque capacité vidéo : disponible ou non, et pourquoi.

    Args:
        registre: le registre des connecteurs de cette machine.
        fournisseur_vision: le fournisseur du modèle de vision, ou `None`
            s'il n'est pas branché — auquel cas la vision est déclarée
            indisponible **avec cette raison**, jamais supposée présente.

    Returns:
        Un dictionnaire `capacite -> {disponible, raison}`. Une capacité
        absente de la réponse n'existe pas sur cette machine ; une capacité
        indisponible porte toujours une raison lisible.
    """
    etats: Dict[str, Dict[str, Any]] = {
        capacite: _depuis_connecteur(registre, connecteur)
        for capacite, connecteur in PAR_CONNECTEUR.items()
    }

    # La vision ne passe pas par un connecteur : elle interroge le modèle.
    if fournisseur_vision is None:
        etats["vision"] = {"disponible": False,
                           "raison": "aucun modele de vision branche"}
    else:
        try:
            joignable = await fournisseur_vision.is_available()
        except Exception as erreur:  # noqa: BLE001
            etats["vision"] = {"disponible": False,
                               "raison": f"sonde en echec : {type(erreur).__name__}"}
        else:
            etats["vision"] = {
                "disponible": bool(joignable),
                "raison": "" if joignable else
                          "le modele de vision ne repond pas depuis cette machine",
            }
    return etats
