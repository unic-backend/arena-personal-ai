"""Connecteur VectCutAPI — montage CapCut/Jianying via son serveur MCP stdio.

VectCutAPI est Apache-2.0 et reste un programme séparé installé à côté d'ARENA.
On réutilise le transport MCP stdio existant : aucun fork du moteur de montage,
aucun second agent vidéo, aucune dépendance VectCut ajoutée au coeur d'ARENA.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from core.actions.resultat import ResultatAction, echec, non_configure, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante
from core.mcp.stdio_transport import ClientMcpStdio

OUTILS = frozenset({
    "create_draft", "add_video", "add_audio", "add_image", "add_text",
    "add_subtitle", "add_effect", "add_sticker", "add_video_keyframe",
    "get_video_duration", "save_draft",
})
LECTURES = frozenset({"get_video_duration"})
CE_QUI_MANQUE = (
    "VectCutAPI n'est pas configuré : cloner sun-guannan/VectCutAPI séparément, "
    "installer ses dépendances, puis définir VECTCUT_PATH vers ce dossier."
)


def _dossier() -> str:
    return os.getenv("VECTCUT_PATH", "").strip()


class ConnecteurVectCut(Connecteur):
    service = "video_editing"
    nom = "vectcut"

    def __init__(self, client: Optional[ClientMcpStdio] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._client_impose = client

    def capacites(self) -> Dict[str, Capacite]:
        return {
            outil: Capacite(
                nom=outil,
                action="read" if outil in LECTURES else "apply",
                description=f"Outil VectCutAPI MCP : {outil}.",
                ecriture=outil not in LECTURES,
            )
            for outil in sorted(OUTILS)
        }

    def _client(self) -> Optional[ClientMcpStdio]:
        if self._client_impose is not None:
            return self._client_impose
        dossier = _dossier()
        if not dossier:
            return None
        return ClientMcpStdio(
            [os.getenv("VECTCUT_PYTHON", "python"), "mcp_server.py"],
            dossier=dossier,
        )

    def sonder(self) -> Sante:
        from core.connectors.base import _maintenant

        dossier = _dossier()
        if self._client_impose is None and (
            not dossier or not (Path(dossier) / "mcp_server.py").is_file()
        ):
            return Sante(
                etat=EtatSante.NON_CONFIGURE,
                message="VECTCUT_PATH absent ou mcp_server.py introuvable.",
                ce_qui_manque=CE_QUI_MANQUE,
                mesure_le=_maintenant(),
            )
        client = self._client()
        if client is None:
            return Sante(EtatSante.NON_CONFIGURE, ce_qui_manque=CE_QUI_MANQUE,
                         mesure_le=_maintenant())
        with client:
            reponse = client.outils()
        if not reponse.ok:
            return Sante(
                EtatSante.NON_CONFIGURE,
                message=f"VectCut MCP ne répond pas ({reponse.raison}).",
                ce_qui_manque=CE_QUI_MANQUE,
                mesure_le=_maintenant(),
            )
        annonces = {str(x.get("name") or "") for x in reponse.resultat.get("tools", [])}
        manquants = OUTILS - annonces
        if manquants:
            return Sante(
                EtatSante.EN_PANNE,
                message=f"VectCut répond mais {len(manquants)} outil(s) attendu(s) manquent.",
                mesure_le=_maintenant(),
            )
        return Sante(
            EtatSante.OPERATIONNEL,
            message=f"VectCut MCP opérationnel : {len(annonces)} outil(s).",
            mesure_le=_maintenant(),
        )

    def authentifier(self) -> bool:
        return True

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        client = self._client()
        if client is None:
            return non_configure(action=capacite.nom, cible=self.nom,
                                 ce_qui_manque=CE_QUI_MANQUE)
        if capacite.nom not in OUTILS:
            return echec(action=capacite.nom, cible=self.nom, message="Outil VectCut non autorisé.")
        with client:
            reponse = client.appeler(capacite.nom, dict(parametres))
        if not reponse.ok:
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"VectCut MCP a échoué : {reponse.raison}.")
        donnees = reponse.resultat
        return succes(
            action=capacite.nom,
            cible=self.nom,
            message=f"VectCut a exécuté {capacite.nom}.",
            preuve=f"outil MCP {capacite.nom}",
            donnees=donnees,
        )
