"""Ce que la machine branchée peut vraiment faire pour du Software Engineering.

Même patron que `disponibilite_video.py` (VOLET vidéo, 03/09/2026) : chaque
capacité est renvoyée à la sonde qui la mesure déjà, jamais à une seconde
logique qui pourrait diverger. DEC-0073 unifie quatre entrées vers le code en
une capacité `software_engineering` — cette fonction est ce qui répond
« qu'est-ce qui marche, là, maintenant ? » sans jamais le deviner.

Trois backends, jamais confondus :

- `dioumtoukay` : agit vraiment sur le dépôt (lit, écrit, exécute, git).
  Dépend d'un moteur de modèle joignable — sondé via `provider.is_available()`,
  jamais supposé parce que le processus tourne.
- `github` : Pull Request, état de CI, commentaires de revue. Dépend d'un
  jeton (`USMAN_GITHUB_TOKEN`) et du réseau — sondé par `ConnecteurGitHub.
  sonder()`, jamais par la seule présence de la variable d'environnement.
- `specialistes` : `RepoEngineerAgent` et `SWEAgent`, consultés en cours de
  tâche (DEC-0073). Même moteur que `dioumtoukay` : les trois tombent
  ensemble quand le moteur de modèle ne répond pas.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from core.connectors.base import EtatSante


async def disponibilite_swe(
    provider_code: Optional[Any] = None,
    connecteur_github: Optional[Any] = None,
    dioumtoukay: Optional[Any] = None,
) -> Dict[str, Dict[str, Any]]:
    """Pour chaque backend Software Engineering : disponible ou non, et pourquoi.

    Args:
        provider_code: le `ModelProvider` que Dioumtoukay utilise. `None` s'il
            n'est pas branché, auquel cas `dioumtoukay` et `specialistes`
            sont déclarés indisponibles **avec cette raison**.
        connecteur_github: le connecteur GitHub, ou `None` s'il n'a pas été
            construit (le registre le rend `None` si sa fabrique a échoué).
        dioumtoukay: l'agent lui-même, pour dire s'il a un connecteur GitHub
            et des spécialistes réellement branchés — pas seulement si le
            moteur répond.

    Returns:
        `capacite -> {disponible, raison}`. Une capacité absente de la
        réponse n'existe pas sur cette machine.
    """
    etats: Dict[str, Dict[str, Any]] = {}

    if provider_code is None:
        raison = "aucun modele de code branche"
        etats["dioumtoukay"] = {"disponible": False, "raison": raison}
        etats["specialistes"] = {"disponible": False, "raison": raison}
    else:
        try:
            joignable = await provider_code.is_available()
        except Exception as erreur:  # noqa: BLE001 — un rapport ne meurt pas d'une panne qu'il rapporte
            etats["dioumtoukay"] = {"disponible": False,
                                    "raison": f"sonde en echec : {type(erreur).__name__}"}
        else:
            etats["dioumtoukay"] = {
                "disponible": bool(joignable),
                "raison": "" if joignable else "le moteur de code ne repond pas",
            }
        # Les specialistes partagent le meme moteur : les separer laisserait
        # croire qu'ils pourraient repondre pendant que Dioumtoukay est en
        # panne, ce qui n'arrive jamais dans cette configuration.
        a_les_deux = bool(dioumtoukay and dioumtoukay.analyste and dioumtoukay.chercheur_de_bug)
        if not a_les_deux:
            etats["specialistes"] = {"disponible": False,
                                     "raison": "RepoEngineerAgent ou SWEAgent non branche"}
        else:
            etats["specialistes"] = dict(etats["dioumtoukay"])

    if connecteur_github is None:
        etats["github"] = {"disponible": False, "raison": "connecteur non construit"}
    else:
        try:
            sante = connecteur_github.sonder()
        except Exception as erreur:  # noqa: BLE001
            etats["github"] = {"disponible": False,
                               "raison": f"sonde en echec : {type(erreur).__name__}"}
        else:
            if sante.etat is EtatSante.OPERATIONNEL:
                etats["github"] = {"disponible": True, "raison": ""}
            else:
                raison = sante.message or sante.etat.value
                if sante.ce_qui_manque:
                    raison = f"{raison} ({sante.ce_qui_manque})"
                etats["github"] = {"disponible": False, "raison": raison}

    return etats
