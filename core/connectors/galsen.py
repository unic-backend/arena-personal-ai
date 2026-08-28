"""Connecteur GalsenAPI — les donnees du Senegal, avec leur source.

GalsenAPI (Lassana Siby, licence MIT) publie le decoupage administratif du
Senegal et ses chiffres : regions, departements, arrondissements, communes,
villages, demographie. Sa particularite, et la raison pour laquelle elle entre
ici plutot qu'une autre : **chaque chiffre est trace vers sa source** — la
demographie vient du RGPH-5 2023 de l'ANSD, et l'API le dit elle-meme dans ses
reponses.

C'est le premier connecteur reel d'ARENA. Il l'est parce qu'il ne demande
aucune cle : rien a stocker, rien a faire fuiter, rien qui depende de la purge
des secrets qui gele le chapitre 8.

**Cinq regles :**

1. **Aucun chiffre sans son origine.** Chaque resultat porte l'attribution de
   l'API, la date de recuperation, et la note de source que l'API fournit quand
   elle en fournit une. Un nombre qui arriverait sans rien de tout cela ne
   serait qu'une rumeur bien formatee.

2. **Ce connecteur n'ecrit rien, et ne peut pas etre configure pour le faire.**
   Toutes ses capacites sont en lecture. Il n'existe aucun chemin d'ecriture a
   activer.

3. **Le quota de l'API est declare, pas subi.** 60 requetes par minute, annonce
   par son auteur. Il est inscrit sur chaque capacite pour que le cadre le fasse
   respecter : ce service est offert gratuitement, le saturer serait grossier.

4. **Un champ absent reste absent.** Une population que l'API ne donne pas vaut
   `None`. Jamais `0`, qui se lirait comme « personne n'y habite ».

5. **La sante est mesuree, puis gardee une minute.** Interroger l'API a chaque
   appel doublerait la consommation du quota. La mesure reste une mesure : elle
   porte sa date, et `Sante.mesure_le` la rend lisible.
"""
import logging
import os
import time
from typing import Any, Callable, Dict, Optional

import httpx

from core.actions.resultat import ResultatAction, echec, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante

logger = logging.getLogger("usman.connecteurs.galsen")

#: L'adresse de l'API. Dans l'environnement, jamais en dur ailleurs.
BASE_URL = os.getenv("GALSEN_API_URL", "https://galsenapi.lassanasiby.com/api/v1")

#: Plafond annonce par l'auteur de l'API : 60 requetes par minute et par IP.
QUOTA_PAR_MINUTE = 60

#: La licence MIT de GalsenAPI exige l'attribution. Elle voyage avec chaque
#: resultat : une donnee qui perd son auteur en route n'est plus citable.
ATTRIBUTION = "GalsenAPI — Lassana Siby (licence MIT, attribution requise)"

#: Duree pendant laquelle une mesure de sante reste valable.
DUREE_SONDE_SECONDES = 60.0

#: Delai d'attente d'une requete. Au-dela, le service est considere en panne
#: plutot que de faire attendre une reponse de chat.
DELAI_SECONDES = 15.0


def _http(chemin: str, parametres: Dict[str, Any]) -> Dict[str, Any]:
    """Un GET sur l'API. Rend la charge JSON, ou leve.

    Sortie reseau isolee dans une seule fonction : les tests la remplacent, et
    le reste du module n'a jamais besoin d'un serveur pour etre verifie.
    """
    url = f"{BASE_URL.rstrip('/')}/{chemin.lstrip('/')}"
    with httpx.Client(timeout=DELAI_SECONDES) as client:
        reponse = client.get(url, params=parametres)
        reponse.raise_for_status()
        return reponse.json()


#: Signature de la couche reseau, injectable.
AppelHttp = Callable[[str, Dict[str, Any]], Dict[str, Any]]


class GalsenConnector(Connecteur):
    """Lecture seule sur les donnees publiques du Senegal."""

    service = "senegal_data"
    nom = "galsen"

    def __init__(self, appel: Optional[AppelHttp] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._appel = appel or _http
        self._sante: Optional[Sante] = None
        self._sante_mesuree_a: float = 0.0

    # --- Ce que le connecteur sait faire ---------------------------------------

    def capacites(self) -> Dict[str, Capacite]:
        """Cinq lectures. Aucune ecriture — il n'y en a pas a declarer."""
        def lecture(nom: str, action: str, description: str) -> Capacite:
            return Capacite(nom=nom, action=action, description=description,
                            ecriture=False, quota_par_minute=QUOTA_PAR_MINUTE)

        return {
            "regions": lecture(
                "regions", "read",
                "Liste les 14 regions du Senegal avec leur population et leur superficie."),
            "departements": lecture(
                "departements", "read",
                "Liste les departements, filtrables par region (pcode) ou par nom."),
            "communes": lecture(
                "communes", "read",
                "Cherche une commune par son nom et rend son departement et sa population."),
            "rechercher": lecture(
                "rechercher", "search",
                "Cherche un lieu du Senegal, tous niveaux confondus."),
            "statistiques": lecture(
                "statistiques", "read",
                "Les compteurs nationaux et la population totale, avec leur source."),
        }

    # --- Sante -----------------------------------------------------------------

    def sonder(self) -> Sante:
        """Interroge reellement l'API. Une mesure recente est reutilisee une minute."""
        maintenant = time.monotonic()
        if self._sante is not None and maintenant - self._sante_mesuree_a < DUREE_SONDE_SECONDES:
            return self._sante

        try:
            charge = self._appel("statistics/", {})
        except Exception as erreur:  # noqa: BLE001 — une panne est un etat, pas un crash
            sante = Sante(
                etat=EtatSante.EN_PANNE,
                message=f"GalsenAPI ne repond pas : {type(erreur).__name__}",
                mesure_le=self._horodatage(),
            )
        else:
            geographie = (charge or {}).get("geographie") or {}
            if not geographie:
                sante = Sante(
                    etat=EtatSante.EN_PANNE,
                    message="GalsenAPI a repondu sans compteurs exploitables.",
                    mesure_le=self._horodatage(),
                )
            else:
                sante = Sante(
                    etat=EtatSante.OPERATIONNEL,
                    message=(f"GalsenAPI repond : {geographie.get('regions')} regions, "
                             f"{geographie.get('communes')} communes."),
                    mesure_le=self._horodatage(),
                )

        self._sante = sante
        self._sante_mesuree_a = maintenant
        return sante

    @staticmethod
    def _horodatage() -> str:
        from core.connectors.base import _maintenant
        return _maintenant()

    def authentifier(self) -> bool:
        """Vrai : l'API est publique. Il n'y a aucun identifiant a presenter.

        Ce n'est pas une authentification reussie par chance — c'est l'absence
        d'authentification requise, et c'est precisement ce qui rend ce
        connecteur activable sans toucher au moindre secret.
        """
        return True

    # --- Execution ---------------------------------------------------------------

    #: Chemin de l'API et parametres acceptes, par capacite. Un parametre absent
    #: de cette table n'est jamais transmis : l'appelant ne choisit pas l'URL.
    ROUTES: Dict[str, Any] = {
        "regions": ("regions/", ("search",)),
        "departements": ("departements/", ("search", "region")),
        "communes": ("communes/", ("search", "departement")),
        "rechercher": ("search/", ("q",)),
        "statistiques": ("statistics/", ()),
    }

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        """Appelle l'API et rend le resultat avec sa provenance."""
        chemin, acceptes = self.ROUTES[capacite.nom]
        envoyes = {cle: valeur for cle, valeur in parametres.items()
                   if cle in acceptes and valeur not in (None, "")}

        try:
            charge = self._appel(chemin, envoyes)
        except Exception as erreur:  # noqa: BLE001 — l'echec se rapporte, il ne remonte pas
            logger.info("GalsenAPI %s en echec : %s", chemin, erreur)
            return echec(
                action=capacite.nom, cible=self.nom,
                message=f"GalsenAPI n'a pas repondu : {type(erreur).__name__}.",
                chemin=chemin,
            )

        elements = charge.get("results") if isinstance(charge, dict) else None
        nombre = charge.get("count") if isinstance(charge, dict) else None
        provenance = self._provenance(charge)

        return succes(
            action=capacite.nom,
            cible=self.nom,
            message=self._resume(capacite.nom, nombre, elements),
            preuve=f"GET {chemin} {envoyes or ''}".strip(),
            donnees=elements if elements is not None else charge,
            nombre=nombre,
            **provenance,
        )

    @staticmethod
    def _provenance(charge: Any) -> Dict[str, str]:
        """L'origine, jointe a chaque resultat. La note de l'API si elle existe."""
        from core.connectors.base import _maintenant
        provenance = {"source": ATTRIBUTION, "recupere_le": _maintenant()}
        if isinstance(charge, dict):
            note = (charge.get("population") or {}).get("source_note") \
                if isinstance(charge.get("population"), dict) else None
            if note:
                provenance["source_donnees"] = note
        return provenance

    @staticmethod
    def _resume(nom: str, nombre: Optional[int], elements: Any) -> str:
        """Une phrase lisible. Un compte inconnu se dit, il ne se devine pas."""
        if nom == "statistiques":
            return "Compteurs nationaux du Senegal."
        if nombre is None:
            trouve = len(elements) if isinstance(elements, list) else None
            if trouve is None:
                return f"Reponse de GalsenAPI pour {nom}, sans compte annonce."
            return f"{trouve} resultat(s) pour {nom}."
        return f"{nombre} resultat(s) pour {nom}."
