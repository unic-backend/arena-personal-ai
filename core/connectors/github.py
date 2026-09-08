"""Connecteur GitHub — le premier de ce dépôt (DEC-0073).

Jusqu'ici, le seul accès à un dépôt distant passait par `Atelier.git()` : du
`git` en ligne de commande, sans aucune vue sur l'API GitHub elle-même — pas
de Pull Request, pas d'état de CI, pas de commentaire de revue. L'audit
Open SWE (`docs/audits/open_swe_audit.md`) mesure que c'est là que ce projet
apporte le plus : une intégration GitHub complète, chaque appel best-effort —
une permission manquante côté GitHub ne doit jamais faire tomber le reste.

**Ce module reprend cette discipline, jamais son code** (Python contre
TypeScript, et surtout une infrastructure de déploiement propre à Open SWE) :
chaque appel HTTP est protégé, une erreur réseau devient un `ResultatAction`
en échec, jamais une exception qui remonte.

**La garde qui compte le plus : `create_pull_request` est `CONFIRMATION`**,
déclarée dans `config/permissions_services.yaml`, et la PR s'ouvre **en
brouillon par défaut** (`draft=True`) même une fois confirmée. Les deux à la
fois, délibérément redondants — l'un est la garde d'ARENA, l'autre celle
d'Open SWE, et rien n'oblige à choisir entre les deux (DEC-0073).

**Authentification : un jeton personnel, dans `USMAN_GITHUB_TOKEN`.** Pas de
flux OAuth pour ce connecteur — DEC-0038 a déjà réglé la question de la
confiance accordée à l'agent qui travaille sur le dépôt ; construire un
second mécanisme d'autorisation ici n'ajouterait rien.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

import httpx

from core.actions.resultat import ResultatAction, echec, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante, _maintenant

logger = logging.getLogger("usman.connecteurs.github")

API = "https://api.github.com"

#: Combien de temps une sonde reste valable avant d'en refaire une — le même
#: patron que `opentakeoff.py` : une sonde à chaque appel gaspillerait le
#: quota GitHub pour une question qui ne change pas seconde par seconde.
DUREE_SONDE_SECONDES = 60.0

CE_QUI_MANQUE = (
    "USMAN_GITHUB_TOKEN absent de .env : un jeton personnel GitHub, portee "
    "'repo' au minimum (github.com/settings/tokens), colle dans .env."
)


def _jeton() -> str:
    return os.getenv("USMAN_GITHUB_TOKEN", "").strip()


def _en_tetes() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {_jeton()}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


class ConnecteurGitHub(Connecteur):
    """Lecture de dépôt, recherche, branche, Pull Request, état de CI, revue."""

    service = "github"
    nom = "github"

    def __init__(self, client: Optional[httpx.Client] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        # Un client injectable : les tests posent un faux transport plutot que
        # de parler au vrai GitHub (`httpx.MockTransport`), jamais un compte
        # de test ni un depot reel.
        self._client = client
        self._sante: Optional[Sante] = None
        self._sante_mesuree_a: float = 0.0

    def _requeter(self, methode: str, url: str, **kw: Any) -> httpx.Response:
        """Une requete, sur le client injecte s'il y en a un, sinon un client
        jetable. **Ne ferme jamais un client injecte** : un `with` sur
        `self._client` le fermerait apres le premier appel, et le deuxieme
        appel de la meme sonde ou du meme test tomberait sur un client mort —
        c'est le genre de defaut qu'un seul test suffit a manquer si le test
        ne fait lui-meme qu'un seul appel."""
        if self._client is not None:
            return self._client.request(methode, url, **kw)
        with httpx.Client(timeout=20.0) as client:
            return client.request(methode, url, **kw)

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "lire_fichier": Capacite(
                nom="lire_fichier", action="read",
                description="Lit le contenu d'un fichier du depot, a une reference donnee.",
                ecriture=False),
            "chercher_code": Capacite(
                nom="chercher_code", action="read",
                description="Cherche un terme dans le code du depot.",
                ecriture=False),
            "creer_branche": Capacite(
                nom="creer_branche", action="write",
                description="Cree une branche a partir d'une reference existante.",
                ecriture=True),
            "creer_pull_request": Capacite(
                nom="creer_pull_request", action="create_pr",
                description="Ouvre une Pull Request, en brouillon.",
                ecriture=True),
            "etat_ci": Capacite(
                nom="etat_ci", action="read",
                description="L'etat combine des verifications sur un commit (CI).",
                ecriture=False),
            "commentaires_pr": Capacite(
                nom="commentaires_pr", action="read",
                description="Les commentaires de revue et de discussion d'une Pull Request.",
                ecriture=False),
        }

    def authentifier(self) -> bool:
        """Un jeton est present. Ne verifie pas qu'il est valable — `sonder()` le fait."""
        return bool(_jeton())

    # --- Sante --------------------------------------------------------------------

    def sonder(self) -> Sante:
        maintenant = time.monotonic()
        if self._sante is not None and maintenant - self._sante_mesuree_a < DUREE_SONDE_SECONDES:
            return self._sante

        if not self.authentifier():
            sante = Sante(etat=EtatSante.NON_CONFIGURE, message="Aucun jeton GitHub configure.",
                          ce_qui_manque=CE_QUI_MANQUE, mesure_le=_maintenant())
        else:
            try:
                reponse = self._requeter("GET", f"{API}/user", headers=_en_tetes())
                if reponse.status_code == 200:
                    login = reponse.json().get("login", "?")
                    sante = Sante(etat=EtatSante.OPERATIONNEL,
                                  message=f"GitHub repond, authentifie comme {login}.",
                                  mesure_le=_maintenant())
                elif reponse.status_code == 401:
                    sante = Sante(etat=EtatSante.NON_CONFIGURE,
                                  message="Le jeton GitHub est refuse (401).",
                                  ce_qui_manque=CE_QUI_MANQUE, mesure_le=_maintenant())
                else:
                    sante = Sante(etat=EtatSante.EN_PANNE,
                                  message=f"GitHub repond {reponse.status_code}.",
                                  mesure_le=_maintenant())
            except httpx.HTTPError as erreur:
                sante = Sante(etat=EtatSante.EN_PANNE,
                              message=f"GitHub injoignable : {type(erreur).__name__}",
                              mesure_le=_maintenant())

        self._sante = sante
        self._sante_mesuree_a = maintenant
        return sante

    # --- Execution ------------------------------------------------------------------

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        methode = getattr(self, f"_faire_{capacite.nom}", None)
        if methode is None:
            return echec(capacite.nom, self.nom, "Capacite declaree sans implementation.")
        return methode(**parametres)

    def _requete(self, methode: str, chemin_ou_url: str, **kw: Any) -> httpx.Response:
        url = chemin_ou_url if chemin_ou_url.startswith("http") else f"{API}{chemin_ou_url}"
        return self._requeter(methode, url, headers=_en_tetes(), **kw)

    # -- lire_fichier --

    def _faire_lire_fichier(self, depot: str = "", chemin: str = "",
                            ref: str = "", **_: Any) -> ResultatAction:
        if not depot or not chemin:
            return echec("lire_fichier", self.nom, "depot (owner/repo) et chemin sont requis.")
        params = {"ref": ref} if ref else {}
        try:
            reponse = self._requete("GET", f"/repos/{depot}/contents/{chemin}", params=params)
        except httpx.HTTPError as erreur:
            return echec("lire_fichier", depot, f"Requete GitHub en echec : {erreur}")

        if reponse.status_code == 404:
            return echec("lire_fichier", depot, f"Fichier introuvable : {chemin}")
        if reponse.status_code != 200:
            return echec("lire_fichier", depot, f"GitHub repond {reponse.status_code}.")

        corps = reponse.json()
        if isinstance(corps, list):
            return echec("lire_fichier", depot, f"{chemin} est un dossier, pas un fichier.")
        import base64
        contenu = base64.b64decode(corps.get("content", "")).decode("utf-8", errors="replace")
        return succes("lire_fichier", depot, f"{chemin} lu ({len(contenu)} caracteres).",
                      preuve=corps.get("sha", ""), contenu=contenu)

    # -- chercher_code --

    def _faire_chercher_code(self, depot: str = "", terme: str = "",
                             **_: Any) -> ResultatAction:
        if not depot or not terme:
            return echec("chercher_code", self.nom, "depot (owner/repo) et terme sont requis.")
        requete = f"{terme} repo:{depot}"
        try:
            reponse = self._requete("GET", "/search/code", params={"q": requete})
        except httpx.HTTPError as erreur:
            return echec("chercher_code", depot, f"Requete GitHub en echec : {erreur}")

        if reponse.status_code != 200:
            return echec("chercher_code", depot, f"GitHub repond {reponse.status_code}.")

        corps = reponse.json()
        occurrences = [
            {"chemin": item.get("path", ""), "url": item.get("html_url", "")}
            for item in corps.get("items", [])
        ]
        return succes("chercher_code", depot,
                      f"{len(occurrences)} occurrence(s) de {terme!r}.",
                      preuve=str(corps.get("total_count", 0)), occurrences=occurrences)

    # -- creer_branche --

    def _faire_creer_branche(self, depot: str = "", nom_branche: str = "",
                             depuis: str = "main", **_: Any) -> ResultatAction:
        if not depot or not nom_branche:
            return echec("creer_branche", self.nom, "depot et nom_branche sont requis.")
        try:
            base = self._requete("GET", f"/repos/{depot}/git/ref/heads/{depuis}")
        except httpx.HTTPError as erreur:
            return echec("creer_branche", depot, f"Requete GitHub en echec : {erreur}")
        if base.status_code != 200:
            return echec("creer_branche", depot,
                         f"Reference {depuis!r} introuvable ({base.status_code}).")
        sha = base.json().get("object", {}).get("sha", "")

        try:
            reponse = self._requete("POST", f"/repos/{depot}/git/refs", json={
                "ref": f"refs/heads/{nom_branche}", "sha": sha,
            })
        except httpx.HTTPError as erreur:
            return echec("creer_branche", depot, f"Requete GitHub en echec : {erreur}")

        if reponse.status_code == 422:
            return echec("creer_branche", depot, f"La branche {nom_branche!r} existe deja.")
        if reponse.status_code not in (200, 201):
            return echec("creer_branche", depot, f"GitHub repond {reponse.status_code}.")
        return succes("creer_branche", depot, f"Branche {nom_branche!r} creee depuis {depuis!r}.",
                      preuve=sha)

    # -- creer_pull_request --

    def resultat_attendu(self, capacite: Capacite, **parametres: Any) -> str:
        if capacite.nom == "creer_pull_request":
            depot = parametres.get("depot", "?")
            tete = parametres.get("tete", "?")
            base = parametres.get("base", "main")
            return (f"Une Pull Request s'ouvre sur {depot}, de {tete!r} vers {base!r}, "
                    f"EN BROUILLON — elle n'est pas prete a fusionner.")
        return super().resultat_attendu(capacite, **parametres)

    def _faire_creer_pull_request(self, depot: str = "", titre: str = "", tete: str = "",
                                  base: str = "main", corps: str = "", **_: Any) -> ResultatAction:
        if not depot or not titre or not tete:
            return echec("creer_pull_request", self.nom,
                         "depot, titre et tete (la branche source) sont requis.")
        try:
            # Toujours en brouillon : la seconde garde de DEC-0073, redondante
            # avec la CONFIRMATION deja passee pour arriver jusqu'ici.
            reponse = self._requete("POST", f"/repos/{depot}/pulls", json={
                "title": titre, "head": tete, "base": base, "body": corps, "draft": True,
            })
        except httpx.HTTPError as erreur:
            return echec("creer_pull_request", depot, f"Requete GitHub en echec : {erreur}")

        if reponse.status_code != 201:
            detail = reponse.json().get("message", "") if reponse.content else ""
            return echec("creer_pull_request", depot,
                         f"GitHub refuse la creation ({reponse.status_code}) : {detail}")

        corps_json = reponse.json()
        return succes("creer_pull_request", depot,
                      f"Pull Request #{corps_json.get('number')} ouverte en brouillon.",
                      preuve=corps_json.get("html_url", ""),
                      numero=corps_json.get("number"), url=corps_json.get("html_url", ""))

    # -- etat_ci --

    def _faire_etat_ci(self, depot: str = "", ref: str = "", **_: Any) -> ResultatAction:
        if not depot or not ref:
            return echec("etat_ci", self.nom, "depot et ref (SHA ou branche) sont requis.")
        try:
            reponse = self._requete("GET", f"/repos/{depot}/commits/{ref}/check-runs")
        except httpx.HTTPError as erreur:
            return echec("etat_ci", depot, f"Requete GitHub en echec : {erreur}")

        if reponse.status_code != 200:
            return echec("etat_ci", depot, f"GitHub repond {reponse.status_code}.")

        courses = reponse.json().get("check_runs", [])
        # Le meme repli SUCCESS/PENDING/FAILURE qu'Open SWE (`pull_request_
        # checks.py`) : la question qui compte n'est pas le detail de chaque
        # verification, c'est le verdict d'ensemble.
        if not courses:
            resume = "en_attente"
        elif any(c.get("conclusion") in ("failure", "timed_out", "cancelled") for c in courses):
            resume = "echec"
        elif any(c.get("status") != "completed" for c in courses):
            resume = "en_cours"
        else:
            resume = "succes"

        detail = [{"nom": c.get("name", ""), "statut": c.get("status", ""),
                  "conclusion": c.get("conclusion")} for c in courses]
        return succes("etat_ci", depot, f"CI sur {ref} : {resume} ({len(courses)} verification(s)).",
                      preuve=resume, resume=resume, verifications=detail)

    # -- commentaires_pr --

    def _faire_commentaires_pr(self, depot: str = "", numero: int = 0, **_: Any) -> ResultatAction:
        if not depot or not numero:
            return echec("commentaires_pr", self.nom, "depot et numero de PR sont requis.")
        try:
            revue = self._requete("GET", f"/repos/{depot}/pulls/{numero}/comments")
            discussion = self._requete("GET", f"/repos/{depot}/issues/{numero}/comments")
        except httpx.HTTPError as erreur:
            return echec("commentaires_pr", depot, f"Requete GitHub en echec : {erreur}")

        if revue.status_code != 200 or discussion.status_code != 200:
            return echec("commentaires_pr", depot,
                         f"GitHub repond {revue.status_code}/{discussion.status_code}.")

        def _extraire(liste: List[Dict[str, Any]], genre: str) -> List[Dict[str, Any]]:
            return [{"auteur": c.get("user", {}).get("login", "?"),
                    "corps": c.get("body", ""), "genre": genre,
                    "chemin": c.get("path")} for c in liste]

        commentaires = _extraire(revue.json(), "revue") + _extraire(discussion.json(), "discussion")
        return succes("commentaires_pr", depot, f"{len(commentaires)} commentaire(s) sur la PR #{numero}.",
                      preuve=str(len(commentaires)), commentaires=commentaires)
