"""Connecteur Case — un ordinateur Linux isole et persistant (DEC-0092).

`case-computers/case` (AGPL-3.0 pour `control-plane/`+`image/`, MIT pour
`mcp/`+`bin/`+`web/`+`tests/` — voir `docs/audits/case_audit.md`) donne
Dioumtoukay un second endroit ou travailler : pas la machine du proprietaire
(DEC-0038, `tools/atelier/atelier.py`), mais un CONTENEUR Linux dedie,
persistant, isole — utile pour un test qui doit tourner sur Linux, un paquet
qu'on ne veut pas installer sur la machine reelle, un navigateur qui garde
son identite entre deux sessions.

**Ce connecteur ne remplace rien.** `Atelier` reste la seule facon dont
Dioumtoukay touche la machine du proprietaire. Ce module ajoute une CAPACITE,
jamais un chemin oblige : un ordinateur Case se demande, il ne se substitue
jamais silencieusement a l'atelier.

**Frontiere de licence, deliberee.** Le control-plane (`cased`) et l'image du
bureau sont AGPL — rien de leur code n'est copie ici. Ce module est un CLIENT
HTTP (comme `core/connectors/github.py` vers l'API GitHub) : il parle a une
instance Case deployee separement, par son API REST documentee
(`control-plane/cased.py`, lu dans le commit audite). LICENSE.md de Case le
dit lui-meme : « Writing an agent that drives Case over MCP or REST. Not a
derivative work. » — exactement ce que fait ce fichier.

**REST plutot que MCP, et c'est une decision, pas un oubli.** Le serveur MCP
de Case (`mcp/case_mcp.py`, verifie reellement joignable avec le client MCP
DEJA present d'ARENA — `core/mcp/transport.py::ClientMcp`, sans une ligne de
code neuve) expose 25 outils, mais ni `wake` ni `destroy` n'y figurent —
deliberement, la surface MCP reste plus etroite que l'API (meme discipline
que « MCP has no credential-write tool », SECURITY.md de Case). L'API REST,
elle, porte le cycle de vie complet dans un seul contrat coherent. Mission
ARENA x CASE §28 : choisir REST ou MCP par operation, jamais forcer tout par
un seul chemin quand l'autre est plus complet.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, Optional

import httpx

from core.actions.resultat import ResultatAction, echec, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante, _maintenant

logger = logging.getLogger("usman.connecteurs.case_computer")

#: Combien de temps une sonde reste valable — meme patron que github.py :
#: une sonde a chaque appel gaspillerait un aller-retour pour une question
#: qui ne change pas seconde par seconde.
DUREE_SONDE_SECONDES = 30.0

#: `computer_create` de Case bloque jusqu'a ce que le conteneur reponde
#: (mcp/case_mcp.py : "Blocks until running") — Xvfb + Chromium + xfwm4 au
#: demarrage prennent plus qu'un appel HTTP ordinaire. Le delai des autres
#: appels reste celui d'`httpx` par defaut de ce module (20s).
DELAI_CREATION_SECONDES = 90.0

CE_QUI_MANQUE = (
    "USMAN_CASE_URL absent, ou l'instance Case qu'il designe est injoignable : "
    "deployer Case separement (docs/audits/case_audit.md, section deploiement "
    "local) puis renseigner USMAN_CASE_URL (defaut http://127.0.0.1:8787/v1) "
    "et USMAN_CASE_TOKEN dans .env."
)


def _url_base() -> str:
    return os.getenv("USMAN_CASE_URL", "http://127.0.0.1:8787/v1").rstrip("/")


def _url_sante() -> str:
    """`/health` vit a la racine de cased, jamais sous `/v1` — construit
    explicitement plutot que par un `..` relatif, fragile a lire et a maintenir."""
    base = _url_base()
    racine = base[: -len("/v1")] if base.endswith("/v1") else base
    return f"{racine}/health"


def _jeton() -> str:
    return os.getenv("USMAN_CASE_TOKEN", "").strip()


def _en_tetes() -> Dict[str, str]:
    jeton = _jeton()
    return {"Authorization": f"Bearer {jeton}"} if jeton else {}


class ConnecteurCaseComputer(Connecteur):
    """Un ordinateur Linux isole, persistant, pilote par l'API REST de Case."""

    service = "case"
    nom = "case"

    def __init__(self, client: Optional[httpx.Client] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        # Injectable pour les tests (httpx.MockTransport, jamais un vrai
        # deploiement Case) — meme raison que github.py.
        self._client = client
        self._sante: Optional[Sante] = None
        self._sante_mesuree_a: float = 0.0

    def _requeter(self, methode: str, chemin: str, *, delai: float = 20.0,
                 **kw: Any) -> httpx.Response:
        url = chemin if chemin.startswith("http") else f"{_url_base()}{chemin}"
        entetes = {**_en_tetes(), **kw.pop("headers", {})}
        if self._client is not None:
            return self._client.request(methode, url, headers=entetes, **kw)
        with httpx.Client(timeout=delai) as client:
            return client.request(methode, url, headers=entetes, **kw)

    # --- Contrat Connecteur --------------------------------------------------------

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "lister": Capacite(
                nom="lister", action="read",
                description="Liste les ordinateurs Case existants, avec leur etat.",
                ecriture=False),
            "etat": Capacite(
                nom="etat", action="read",
                description="L'etat d'un ordinateur Case (running/asleep/...).",
                ecriture=False),
            "creer": Capacite(
                nom="creer", action="write",
                description="Cree un nouvel ordinateur Linux isole et persistant.",
                ecriture=True),
            "dormir": Capacite(
                nom="dormir", action="write",
                description="Endort un ordinateur (l'etat persiste, les ressources se liberent).",
                ecriture=True),
            "reveiller": Capacite(
                nom="reveiller", action="write",
                description="Reveille un ordinateur endormi.",
                ecriture=True),
            "executer_commande": Capacite(
                nom="executer_commande", action="write",
                description="Execute une commande shell DANS l'ordinateur isole (jamais sur la machine du proprietaire).",
                ecriture=True),
            "lire_fichier": Capacite(
                nom="lire_fichier", action="read",
                description="Lit un fichier de l'ordinateur isole (sous /home/agent).",
                ecriture=False),
            "ecrire_fichier": Capacite(
                nom="ecrire_fichier", action="write",
                description="Ecrit un fichier dans l'ordinateur isole (8 Mo max, cote Case).",
                ecriture=True),
            "naviguer": Capacite(
                nom="naviguer", action="write",
                description="Ouvre une URL dans le navigateur de l'ordinateur isole.",
                ecriture=True),
            "capture_ecran": Capacite(
                nom="capture_ecran", action="read",
                description="Capture d'ecran de l'ordinateur isole (reveille s'il dormait).",
                ecriture=False),
            "detruire": Capacite(
                nom="detruire", action="destroy",
                description="Detruit definitivement un ordinateur et ses donnees persistantes.",
                ecriture=True),
        }

    def authentifier(self) -> bool:
        """Une URL est configuree. Ne verifie pas qu'elle repond — `sonder()`
        le fait. Le jeton (`USMAN_CASE_TOKEN`) reste optionnel cote Case
        (un deploiement local en boucle locale peut s'en passer, protege par
        le controle Host/Origin — SECURITY.md) ; l'exiger ici rejetterait une
        configuration que Case lui-meme considere valide."""
        return bool(os.getenv("USMAN_CASE_URL", "").strip()) or _url_base() != ""

    def sonder(self) -> Sante:
        maintenant = time.monotonic()
        if self._sante is not None and maintenant - self._sante_mesuree_a < DUREE_SONDE_SECONDES:
            return self._sante

        try:
            reponse = self._requeter("GET", _url_sante(), delai=5.0)
        except httpx.HTTPError as erreur:
            sante = Sante(etat=EtatSante.EN_PANNE,
                          message=f"Case injoignable a {_url_base()} : {type(erreur).__name__}",
                          ce_qui_manque=CE_QUI_MANQUE, mesure_le=_maintenant())
        else:
            if reponse.status_code != 200:
                sante = Sante(etat=EtatSante.EN_PANNE,
                              message=f"Case repond {reponse.status_code}.",
                              mesure_le=_maintenant())
            else:
                corps = reponse.json()
                if "computers" not in corps:
                    # Jeton absent/refuse : /health ne rend que {"ok": true}
                    # (SECURITY.md — porte ouverte, inventaire reserve au porteur).
                    sante = Sante(
                        etat=EtatSante.NON_CONFIGURE,
                        message="Case repond mais sans jeton valide (inventaire refuse).",
                        ce_qui_manque="USMAN_CASE_TOKEN absent ou refuse par cette instance Case.",
                        mesure_le=_maintenant())
                else:
                    docker_ok = corps.get("docker")
                    sante = Sante(
                        etat=EtatSante.OPERATIONNEL,
                        message=(f"Case repond : {corps.get('computers', 0)} ordinateur(s), "
                                f"{corps.get('running', 0)}/{corps.get('max_running', '?')} "
                                f"eveille(s), Docker {'OK' if docker_ok else 'INJOIGNABLE depuis cased'}."),
                        mesure_le=_maintenant())

        self._sante = sante
        self._sante_mesuree_a = maintenant
        return sante

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        methode = getattr(self, f"_faire_{capacite.nom}", None)
        if methode is None:
            return echec(capacite.nom, self.nom, "Capacite declaree sans implementation.")
        return methode(**parametres)

    # --- Capacites --------------------------------------------------------------------

    def _erreur_case(self, reponse: httpx.Response) -> str:
        """Le message d'erreur reel de Case, tel qu'il l'a rendu — jamais
        resume ni invente (ApiError : {"error": {"code", "message"}})."""
        try:
            corps = reponse.json()
            return str((corps.get("error") or {}).get("message") or reponse.text)
        except ValueError:
            return f"HTTP {reponse.status_code}"

    def _faire_lister(self, **_: Any) -> ResultatAction:
        try:
            reponse = self._requeter("GET", "/computers")
        except httpx.HTTPError as erreur:
            return echec("lister", self.nom, f"Case injoignable : {erreur}")
        if reponse.status_code != 200:
            return echec("lister", self.nom, self._erreur_case(reponse))
        ordinateurs = reponse.json().get("computers", [])
        return succes("lister", self.nom, f"{len(ordinateurs)} ordinateur(s).",
                      preuve=str(len(ordinateurs)), ordinateurs=ordinateurs)

    def _faire_etat(self, computer_id: str = "", **_: Any) -> ResultatAction:
        if not computer_id:
            return echec("etat", self.nom, "computer_id est requis.")
        try:
            reponse = self._requeter("GET", f"/computers/{computer_id}")
        except httpx.HTTPError as erreur:
            return echec("etat", computer_id, f"Case injoignable : {erreur}")
        if reponse.status_code == 404:
            return echec("etat", computer_id, f"Ordinateur introuvable : {computer_id}")
        if reponse.status_code != 200:
            return echec("etat", computer_id, self._erreur_case(reponse))
        corps = reponse.json()
        return succes("etat", computer_id, f"Etat : {corps.get('state', '?')}.",
                      preuve=corps.get("state", ""), ordinateur=corps)

    def _faire_creer(self, nom: str = "", **_: Any) -> ResultatAction:
        try:
            reponse = self._requeter("POST", "/computers",
                                     json={"name": nom} if nom else {},
                                     delai=DELAI_CREATION_SECONDES)
        except httpx.HTTPError as erreur:
            return echec("creer", self.nom, f"Case injoignable : {erreur}")
        if reponse.status_code != 201:
            # Cas reel mesure sans l'image de bureau construite : "ImageNotFound".
            # Rapporte tel quel — jamais simule comme une reussite.
            return echec("creer", nom or "(sans nom)", self._erreur_case(reponse))
        corps = reponse.json()
        return succes("creer", corps.get("id", ""),
                      f"Ordinateur cree : {corps.get('id', '?')}.",
                      preuve=corps.get("id", ""), ordinateur=corps)

    def _faire_dormir(self, computer_id: str = "", **_: Any) -> ResultatAction:
        if not computer_id:
            return echec("dormir", self.nom, "computer_id est requis.")
        try:
            reponse = self._requeter("POST", f"/computers/{computer_id}/sleep")
        except httpx.HTTPError as erreur:
            return echec("dormir", computer_id, f"Case injoignable : {erreur}")
        if reponse.status_code != 200:
            return echec("dormir", computer_id, self._erreur_case(reponse))
        return succes("dormir", computer_id, f"{computer_id} endormi.", preuve=computer_id)

    def _faire_reveiller(self, computer_id: str = "", **_: Any) -> ResultatAction:
        if not computer_id:
            return echec("reveiller", self.nom, "computer_id est requis.")
        try:
            reponse = self._requeter("POST", f"/computers/{computer_id}/wake",
                                     delai=DELAI_CREATION_SECONDES)
        except httpx.HTTPError as erreur:
            return echec("reveiller", computer_id, f"Case injoignable : {erreur}")
        if reponse.status_code != 200:
            return echec("reveiller", computer_id, self._erreur_case(reponse))
        return succes("reveiller", computer_id, f"{computer_id} reveille.", preuve=computer_id)

    def _faire_executer_commande(self, computer_id: str = "", commande: str = "",
                                 timeout_s: int = 30, **_: Any) -> ResultatAction:
        if not computer_id or not commande:
            return echec("executer_commande", self.nom, "computer_id et commande sont requis.")
        try:
            reponse = self._requeter(
                "POST", f"/computers/{computer_id}/exec", params={"wake": "true"},
                json={"command": commande, "timeout_s": timeout_s},
                delai=timeout_s + 30)
        except httpx.HTTPError as erreur:
            return echec("executer_commande", computer_id, f"Case injoignable : {erreur}")
        if reponse.status_code == 423:
            # Injection d'un identifiant en cours : Case refuse deliberement
            # (SECURITY.md) — ni un echec de la commande, ni une reussite.
            return echec("executer_commande", computer_id,
                        "Refuse (423) : une saisie d'identifiant est en cours sur cet ordinateur.")
        if reponse.status_code != 200:
            return echec("executer_commande", computer_id, self._erreur_case(reponse))
        corps = reponse.json()
        ok = corps.get("exit_code") == 0
        message = f"code {corps.get('exit_code')}"
        resultat = succes if ok else echec
        return resultat("executer_commande", computer_id, message,
                        **({"preuve": str(corps.get("exit_code"))} if ok else {}),
                        sortie=corps.get("stdout", ""), erreur=corps.get("stderr", ""),
                        code=corps.get("exit_code"))

    def _faire_lire_fichier(self, computer_id: str = "", chemin: str = "", **_: Any) -> ResultatAction:
        if not computer_id or not chemin:
            return echec("lire_fichier", self.nom, "computer_id et chemin sont requis.")
        try:
            reponse = self._requeter("GET", f"/computers/{computer_id}/files",
                                     params={"path": chemin, "wake": "true"}, delai=120.0)
        except httpx.HTTPError as erreur:
            return echec("lire_fichier", computer_id, f"Case injoignable : {erreur}")
        if reponse.status_code != 200:
            return echec("lire_fichier", computer_id, self._erreur_case(reponse))
        contenu = reponse.content
        return succes("lire_fichier", computer_id, f"{chemin} lu ({len(contenu)} octets).",
                      preuve=chemin, contenu=contenu)

    def _faire_ecrire_fichier(self, computer_id: str = "", chemin: str = "",
                              contenu: bytes = b"", **_: Any) -> ResultatAction:
        if not computer_id or not chemin:
            return echec("ecrire_fichier", self.nom, "computer_id et chemin sont requis.")
        if isinstance(contenu, str):
            contenu = contenu.encode("utf-8")
        try:
            reponse = self._requeter("PUT", f"/computers/{computer_id}/files",
                                     params={"path": chemin, "wake": "true"},
                                     content=contenu, delai=120.0)
        except httpx.HTTPError as erreur:
            return echec("ecrire_fichier", computer_id, f"Case injoignable : {erreur}")
        if reponse.status_code != 201:
            return echec("ecrire_fichier", computer_id, self._erreur_case(reponse))
        return succes("ecrire_fichier", computer_id,
                      f"{chemin} ecrit ({len(contenu)} octets).", preuve=chemin)

    def _faire_naviguer(self, computer_id: str = "", url: str = "", **_: Any) -> ResultatAction:
        if not computer_id or not url:
            return echec("naviguer", self.nom, "computer_id et url sont requis.")
        try:
            reponse = self._requeter("POST", f"/computers/{computer_id}/navigate",
                                     params={"wake": "true"}, json={"url": url}, delai=45.0)
        except httpx.HTTPError as erreur:
            return echec("naviguer", computer_id, f"Case injoignable : {erreur}")
        if reponse.status_code != 200:
            return echec("naviguer", computer_id, self._erreur_case(reponse))
        corps = reponse.json()
        if not corps.get("ok", True):
            return echec("naviguer", computer_id, corps.get("error") or "navigation refusee")
        return succes("naviguer", computer_id, f"Navigue vers {url}.", preuve=url, page=corps)

    def _faire_capture_ecran(self, computer_id: str = "", **_: Any) -> ResultatAction:
        if not computer_id:
            return echec("capture_ecran", self.nom, "computer_id est requis.")
        try:
            reponse = self._requeter("GET", f"/computers/{computer_id}/screenshot",
                                     params={"wake": "true"}, delai=45.0)
        except httpx.HTTPError as erreur:
            return echec("capture_ecran", computer_id, f"Case injoignable : {erreur}")
        if reponse.status_code != 200:
            return echec("capture_ecran", computer_id, self._erreur_case(reponse))
        return succes("capture_ecran", computer_id,
                      f"Capture recue ({len(reponse.content)} octets PNG).",
                      preuve=computer_id, png=reponse.content)

    def _faire_detruire(self, computer_id: str = "", **_: Any) -> ResultatAction:
        if not computer_id:
            return echec("detruire", self.nom, "computer_id est requis.")
        try:
            reponse = self._requeter("DELETE", f"/computers/{computer_id}")
        except httpx.HTTPError as erreur:
            return echec("detruire", computer_id, f"Case injoignable : {erreur}")
        if reponse.status_code == 404:
            return echec("detruire", computer_id, f"Ordinateur introuvable : {computer_id}")
        if reponse.status_code != 204:
            return echec("detruire", computer_id, self._erreur_case(reponse))
        return succes("detruire", computer_id, f"{computer_id} detruit.", preuve=computer_id)
