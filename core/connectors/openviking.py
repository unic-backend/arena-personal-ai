"""Connecteur OpenViking — mémoire/contexte/compétences, appelé par son
PROPRE serveur HTTP, jamais son code importé.

**Licence, vérifiée en clonant le dépôt réel, pas en faisant confiance à un
paraphrase** (mission « intégration unifiée », 06/09/2026, §13 : « ne
suppose jamais qu'une licence d'un sous-dossier s'applique à tout le
dépôt ») : le `LICENSE` racine de `volcengine/OpenViking` est **AGPLv3**.
Trois sous-dossiers (`crates/ov_cli`, `crates/ragfs`, `crates/ragfs-python`)
portent leur PROPRE `Cargo.toml` avec `license = "Apache-2.0"` — vérifié en
lisant ces trois fichiers, pas supposé depuis une note de mission. Mais ces
trois crates sont l'abstraction de système de fichiers BAS NIVEAU
(`ragfs::core::{FileSystem, PluginRegistry}` — un composant technique
générique, sans logique de mémoire/skills/L0-L1-L2) et un client CLI
Rust — jamais la capacité « OpenViking » que la mission demande (mémoire
hiérarchique, sessions, compétences), qui vit dans le reste du dépôt, sous
licence AGPLv3. Importer même la partie Apache-2.0 n'apporterait donc rien
d'utile ici : `SUGGESTION — NON IMPLÉMENTÉE`, pour la même raison que
BuildingPy/BIM as Code ont été écartés en DEC-0056 — un second morceau de
dépendance pour un besoin qu'il ne sert pas.

**Ce que ce connecteur appelle réellement** : le serveur OpenViking lui-même
tourne en service SÉPARÉ, installé et lancé par le propriétaire (son propre
`docker-compose.yml`/`ov` CLI) — jamais dans ce dépôt. Son API HTTP est
documentée dans son propre dépôt (`docs/en/api/`, lu directement) : réponses
`{"status": "ok", "result": {...}}` ou `{"status": "error", "error": {...}}`,
authentification par `Authorization: Bearer <clé>` ou `X-API-Key`. Ce
connecteur est un client HTTP ordinaire, comme Formbricks (DEC-0052) et
SiteGuard (DEC-0054) — jamais un import, jamais un lien.

**Ce qui rend ce composant différent de la mémoire d'ARENA déjà en place**
(`core/memory/`, DEC-0051 pour la comparaison la plus proche/txtai) : la
mémoire d'ARENA vit dans SA base SQLite locale, sans hiérarchie de niveaux ;
OpenViking rend un contexte DÉJÀ ASSEMBLÉ, budgété en tokens, dégradé par
palier (L0 résumé / L1 aperçu / L2 détail) et dédupliqué entre tours —
capacité qu'aucun système existant d'ARENA ne rend. **Rien ici ne remplace
`core/memory/memory_manager.py`** : cette capacité reste explicite, jamais
appelée à la place de la mémoire de chat — même discipline que txtai
(DEC-0051), le test dédié le fige
(`test_openviking_n_apparait_dans_aucune_intention_du_routeur`).

**Quatre capacités, volontairement bornées** (le serveur expose des dizaines
de routes — administration, ACL, WebDAV, snapshots — hors de la portée
réelle demandée : mémoire/contexte/compétences) :

1. `contexte` — `POST /api/v1/search/search` (`mode="context"`) : le
   contexte hiérarchique déjà assemblé, prêt à injecter. Une LECTURE.
2. `rechercher` — `POST /api/v1/search/find` : une recherche vectorielle
   simple, sans assemblage. Une LECTURE.
3. `competences` — `POST /api/v1/skills/find` : les compétences
   pertinentes pour une question. Une LECTURE.
4. `ecrire_ressource` — `POST /api/v1/resources` : ajoute une ressource
   (URL) à la base de contexte du propriétaire — une ÉCRITURE locale, sur
   SON serveur, jamais confirmée à chaque appel (même logique que le devis
   PDF, DEC-0041 : ce qui reste sur sa propre machine ne demande pas
   d'accord préalable).
"""
import logging
import os
import time
from typing import Any, Dict, List, Optional

import httpx

from core.actions.resultat import ResultatAction, echec, non_configure, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante, _maintenant

logger = logging.getLogger("usman.connecteurs.openviking")

DUREE_SONDE_SECONDES = 60.0


def _base_url() -> str:
    """Aucune URL par défaut (DEC-0002) : le serveur OpenViking est installé
    et lancé par le propriétaire, jamais deviné. Lu à l'appel, jamais au
    chargement du module — pour que les tests le fixent par variable
    d'environnement."""
    return os.getenv("OPENVIKING_URL", "").strip().rstrip("/")


def _cle_api() -> str:
    return os.getenv("OPENVIKING_API_KEY", "").strip()


CE_QUI_MANQUE = (
    "OpenViking n'est pas configuré : installer et lancer le serveur "
    "OpenViking à côté (jamais dans ce dépôt, son docker-compose.yml ou "
    "`ov serve`), puis OPENVIKING_URL=http://127.0.0.1:1933 (et "
    "OPENVIKING_API_KEY si le serveur en exige une) dans .env."
)


def _entetes() -> Dict[str, str]:
    entetes = {"Content-Type": "application/json"}
    cle = _cle_api()
    if cle:
        entetes["Authorization"] = f"Bearer {cle}"
    return entetes


class ConnecteurOpenViking(Connecteur):
    """Mémoire/contexte hiérarchique/compétences, via le serveur OpenViking."""

    service = "openviking"
    nom = "openviking"

    def __init__(self, client: Optional[httpx.Client] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._client_impose = client
        self._sante: Optional[Sante] = None
        self._sante_mesuree_a: float = 0.0

    def _client(self) -> httpx.Client:
        return self._client_impose or httpx.Client(timeout=30.0)

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "contexte": Capacite(
                nom="contexte", action="read",
                description=(
                    "Contexte hiérarchique déjà assemblé (L0/L1/L2), budgété en tokens, "
                    "prêt à injecter dans une invite."),
                ecriture=False),
            "rechercher": Capacite(
                nom="rechercher", action="read",
                description="Recherche vectorielle simple dans la mémoire/les ressources d'OpenViking.",
                ecriture=False),
            "competences": Capacite(
                nom="competences", action="read",
                description="Compétences (skills) pertinentes pour une question.",
                ecriture=False),
            "ecrire_ressource": Capacite(
                nom="ecrire_ressource", action="document",
                description="Ajoute une ressource (URL) à la base de contexte du propriétaire.",
                ecriture=True),
        }

    def authentifier(self) -> bool:
        """Vrai : la clé (si le serveur en exige une) voyage dans l'en-tête
        de chaque appel, il n'y a pas de poignée de main séparée à réussir."""
        return True

    def sonder(self) -> Sante:
        maintenant = time.monotonic()
        if self._sante is not None and maintenant - self._sante_mesuree_a < DUREE_SONDE_SECONDES:
            return self._sante

        base_url = _base_url()
        if not base_url:
            sante = Sante(etat=EtatSante.NON_CONFIGURE, message="OPENVIKING_URL absent.",
                         ce_qui_manque=CE_QUI_MANQUE, mesure_le=_maintenant())
        else:
            try:
                client = self._client()
                ferme = self._client_impose is None
                try:
                    reponse = client.get(f"{base_url}/health")
                finally:
                    if ferme:
                        client.close()
                if reponse.status_code == 200:
                    sante = Sante(etat=EtatSante.OPERATIONNEL,
                                 message="OpenViking répond.", mesure_le=_maintenant())
                else:
                    sante = Sante(etat=EtatSante.EN_PANNE,
                                 message=f"OpenViking répond {reponse.status_code}.",
                                 mesure_le=_maintenant())
            except httpx.HTTPError as erreur:
                sante = Sante(etat=EtatSante.NON_CONFIGURE,
                             message=f"OpenViking injoignable : {erreur}",
                             ce_qui_manque=CE_QUI_MANQUE, mesure_le=_maintenant())

        self._sante = sante
        self._sante_mesuree_a = maintenant
        return sante

    # --- Execution --------------------------------------------------------------

    def _poster(self, chemin: str, corps: Dict[str, Any]) -> httpx.Response:
        base_url = _base_url()
        client = self._client()
        ferme = self._client_impose is None
        try:
            return client.post(f"{base_url}{chemin}", json=corps, headers=_entetes())
        finally:
            if ferme:
                client.close()

    @staticmethod
    def _corps_erreur(reponse: httpx.Response) -> str:
        try:
            corps = reponse.json()
        except ValueError:
            return reponse.text[:500]
        if isinstance(corps, dict) and corps.get("status") == "error":
            erreur = corps.get("error") or {}
            return str(erreur.get("message") or erreur)
        return str(corps)[:500]

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        if capacite.nom == "contexte":
            return self._contexte(parametres)
        if capacite.nom == "rechercher":
            return self._rechercher(parametres)
        if capacite.nom == "competences":
            return self._competences(parametres)
        return self._ecrire_ressource(parametres)

    def _contexte(self, parametres: Dict[str, Any]) -> ResultatAction:
        requete = str(parametres.get("requete") or "").strip()
        if not requete:
            return echec(action="contexte", cible=self.nom,
                         message="Aucune question fournie : rien à assembler.")

        corps: Dict[str, Any] = {"query": requete, "mode": "context"}
        if parametres.get("max_tokens"):
            corps["max_tokens"] = int(parametres["max_tokens"])
        if parametres.get("session_id"):
            corps["session_id"] = str(parametres["session_id"])
        if parametres.get("objectif") in ("chat", "coding"):
            corps["purpose"] = parametres["objectif"]

        try:
            reponse = self._poster("/api/v1/search/search", corps)
        except httpx.HTTPError as erreur:
            return non_configure(action="contexte", cible=self.nom,
                                 ce_qui_manque=CE_QUI_MANQUE, detail_erreur=str(erreur))
        if reponse.status_code != 200:
            return echec(action="contexte", cible=self.nom,
                         message=f"OpenViking a refusé ({reponse.status_code}) : {self._corps_erreur(reponse)}")

        resultat = (reponse.json() or {}).get("result") or {}
        entrees = resultat.get("entries") or []
        return succes(
            action="contexte", cible=self.nom,
            message=f"{len(entrees)} élément(s) de contexte assemblé(s) pour « {requete} ».",
            preuve=f"{len(entrees)} élément(s)",
            entrees=entrees, rendu=resultat.get("rendered") or "",
            digest=resultat.get("digest") or "", stats=resultat.get("stats") or {},
        )

    def _rechercher(self, parametres: Dict[str, Any]) -> ResultatAction:
        requete = str(parametres.get("requete") or "").strip()
        if not requete:
            return echec(action="rechercher", cible=self.nom,
                         message="Aucune question fournie : rien à chercher.")

        corps: Dict[str, Any] = {"query": requete}
        if parametres.get("cible_uri"):
            corps["target_uri"] = parametres["cible_uri"]
        if parametres.get("types"):
            corps["context_type"] = list(parametres["types"])
        if parametres.get("limite"):
            corps["node_limit"] = int(parametres["limite"])

        try:
            reponse = self._poster("/api/v1/search/find", corps)
        except httpx.HTTPError as erreur:
            return non_configure(action="rechercher", cible=self.nom,
                                 ce_qui_manque=CE_QUI_MANQUE, detail_erreur=str(erreur))
        if reponse.status_code != 200:
            return echec(action="rechercher", cible=self.nom,
                         message=f"OpenViking a refusé ({reponse.status_code}) : {self._corps_erreur(reponse)}")

        resultat = (reponse.json() or {}).get("result") or {}
        total = resultat.get("total", 0)
        return succes(
            action="rechercher", cible=self.nom,
            message=f"{total} résultat(s) pour « {requete} ».",
            preuve=f"{total} résultat(s)",
            memoires=resultat.get("memories") or [], ressources=resultat.get("resources") or [],
            competences=resultat.get("skills") or [], total=total,
        )

    def _competences(self, parametres: Dict[str, Any]) -> ResultatAction:
        requete = str(parametres.get("requete") or "").strip()
        if not requete:
            return echec(action="competences", cible=self.nom,
                         message="Aucune question fournie : rien à chercher.")

        corps: Dict[str, Any] = {"query": requete}
        if parametres.get("limite"):
            corps["limit"] = int(parametres["limite"])

        try:
            reponse = self._poster("/api/v1/skills/find", corps)
        except httpx.HTTPError as erreur:
            return non_configure(action="competences", cible=self.nom,
                                 ce_qui_manque=CE_QUI_MANQUE, detail_erreur=str(erreur))
        if reponse.status_code != 200:
            return echec(action="competences", cible=self.nom,
                         message=f"OpenViking a refusé ({reponse.status_code}) : {self._corps_erreur(reponse)}")

        resultat = reponse.json() or {}
        competences: List[Any] = resultat.get("result") or []
        return succes(
            action="competences", cible=self.nom,
            message=f"{len(competences)} compétence(s) pertinente(s) pour « {requete} ».",
            preuve=f"{len(competences)} compétence(s)",
            competences=competences,
        )

    def _ecrire_ressource(self, parametres: Dict[str, Any]) -> ResultatAction:
        url = str(parametres.get("url") or "").strip()
        if not url:
            return echec(action="ecrire_ressource", cible=self.nom,
                         message="Aucune URL fournie : rien à ajouter.")

        corps: Dict[str, Any] = {"path": url, "wait": True}
        if parametres.get("raison"):
            corps["reason"] = str(parametres["raison"])
        if parametres.get("cible_uri"):
            corps["to"] = str(parametres["cible_uri"])

        try:
            reponse = self._poster("/api/v1/resources", corps)
        except httpx.HTTPError as erreur:
            return non_configure(action="ecrire_ressource", cible=self.nom,
                                 ce_qui_manque=CE_QUI_MANQUE, detail_erreur=str(erreur))
        if reponse.status_code not in (200, 201):
            return echec(action="ecrire_ressource", cible=self.nom,
                         message=f"OpenViking a refusé ({reponse.status_code}) : {self._corps_erreur(reponse)}")

        resultat = (reponse.json() or {}).get("result") or {}
        uri = resultat.get("uri") or corps.get("to") or url
        return succes(action="ecrire_ressource", cible=self.nom,
                      message=f"Ressource ajoutée : {uri}", preuve=str(uri), donnees=resultat)
