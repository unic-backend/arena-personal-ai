"""Hugging Face Hub - decouverte de modeles, sans second orchestrateur."""
from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional
from urllib.parse import quote

import httpx

from core.actions.resultat import ResultatAction, echec, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante, _maintenant

API = "https://huggingface.co"
DUREE_SONDE_SECONDES = 60.0


class ConnecteurHuggingFace(Connecteur):
    service = "huggingface"
    nom = "huggingface"

    def __init__(self, client: Optional[httpx.Client] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._client = client
        self._sante: Optional[Sante] = None
        self._sante_mesuree_a = 0.0

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "chercher_modeles": Capacite(
                nom="chercher_modeles", action="read",
                description="Cherche des modeles publics sur Hugging Face Hub.",
            ),
            "modele": Capacite(
                nom="modele", action="read",
                description="Lit les metadonnees verifiables d'un modele Hugging Face.",
            ),
        }

    def authentifier(self) -> bool:
        return True

    def _headers(self) -> Dict[str, str]:
        token = os.getenv("HF_TOKEN", "").strip()
        return {"Authorization": f"Bearer {token}"} if token else {}

    def _get(self, chemin: str, **kwargs: Any) -> httpx.Response:
        if self._client is not None:
            return self._client.get(f"{API}{chemin}", headers=self._headers(), **kwargs)
        with httpx.Client(timeout=15.0) as client:
            return client.get(f"{API}{chemin}", headers=self._headers(), **kwargs)

    def sonder(self) -> Sante:
        maintenant = time.monotonic()
        if self._sante is not None and maintenant - self._sante_mesuree_a < DUREE_SONDE_SECONDES:
            return self._sante
        try:
            reponse = self._get("/api/models", params={"limit": 1})
            etat = EtatSante.OPERATIONNEL if reponse.status_code == 200 else EtatSante.EN_PANNE
            message = (
                "Hugging Face Hub repond."
                if etat is EtatSante.OPERATIONNEL
                else f"Hugging Face Hub repond {reponse.status_code}."
            )
        except httpx.HTTPError as erreur:
            etat = EtatSante.EN_PANNE
            message = f"Hugging Face Hub injoignable : {type(erreur).__name__}."
        self._sante = Sante(etat=etat, message=message, mesure_le=_maintenant())
        self._sante_mesuree_a = maintenant
        return self._sante

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        methode = getattr(self, f"_faire_{capacite.nom}", None)
        if methode is None:
            return echec(capacite.nom, self.nom, "Capacite sans implementation.")
        return methode(**parametres)

    def _faire_chercher_modeles(
        self, recherche: str = "", limite: int = 8, **_: Any
    ) -> ResultatAction:
        recherche = (recherche or "").strip()
        if not recherche:
            return echec("chercher_modeles", self.nom, "recherche est requise.")
        limite = max(1, min(int(limite), 20))
        try:
            reponse = self._get(
                "/api/models",
                params={"search": recherche, "sort": "trendingScore", "limit": limite},
            )
        except httpx.HTTPError as erreur:
            return echec("chercher_modeles", self.nom, f"Requete HF en echec : {erreur}")
        if reponse.status_code != 200:
            return echec(
                "chercher_modeles", self.nom,
                f"Hugging Face Hub repond {reponse.status_code}.",
            )
        modeles = [{
            "id": item.get("id", ""),
            "pipeline_tag": item.get("pipeline_tag"),
            "downloads": item.get("downloads"),
            "likes": item.get("likes"),
            "trending_score": item.get("trendingScore"),
            "gated": item.get("gated", False),
            "tags": item.get("tags", []),
        } for item in reponse.json()]
        return succes(
            "chercher_modeles", self.nom,
            f"{len(modeles)} modele(s) trouve(s) pour {recherche}.",
            preuve=f"hf:{recherche}:{len(modeles)}", modeles=modeles,
        )

    def _faire_modele(self, modele: str = "", **_: Any) -> ResultatAction:
        modele = (modele or "").strip()
        if not modele or "/" not in modele:
            return echec("modele", self.nom, "modele doit etre au format organisation/nom.")
        try:
            reponse = self._get(f"/api/models/{quote(modele, safe='/')}")
        except httpx.HTTPError as erreur:
            return echec("modele", self.nom, f"Requete HF en echec : {erreur}")
        if reponse.status_code == 404:
            return echec("modele", self.nom, f"Modele introuvable : {modele}.")
        if reponse.status_code != 200:
            return echec("modele", self.nom, f"Hugging Face Hub repond {reponse.status_code}.")
        item = reponse.json()
        safetensors = item.get("safetensors") or {}
        card = item.get("cardData") or {}
        detail = {
            "id": item.get("id", modele),
            "pipeline_tag": item.get("pipeline_tag"),
            "parametres": safetensors.get("total"),
            "license": card.get("license"),
            "gated": item.get("gated", False),
            "downloads": item.get("downloads"),
            "likes": item.get("likes"),
            "tags": item.get("tags", []),
        }
        return succes(
            "modele", self.nom, f"Metadonnees de {modele} lues.",
            preuve=str(item.get("sha") or modele), **detail,
        )
