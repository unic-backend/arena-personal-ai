"""Connecteur Netronome — la conscience reseau d'ARENA, mesuree, jamais devinee.

Netronome (autobrr/netronome, **GPL-2.0-or-later**) est un outil de test et de
supervision reseau ecrit en Go + React : debit (Speedtest.net, iperf3,
LibreSpeed), traceroute, perte de paquets, sante DNS, supervision d'agents.

Il tourne **a cote** d'ARENA, comme MoneyPrinterTurbo et WanGP (DEC-0008) :
son propre binaire, sa propre base, sa propre configuration. ARENA lui parle
par son API HTTP. **Aucune ligne de Netronome n'entre dans ce depot** — ce qui
importe puisque sa licence GPL-2.0 se propagerait a une oeuvre derivee, et que
ce depot est public sous « tous droits reserves ». Parler a un programme separe
par le reseau n'est pas en deriver (simple agregation, GPL v2 §2).

Le contrat n'est pas devine, il est lu dans le code du projet :
`internal/server/server.go` declare `GET /api/speedtest/status`,
`GET /api/speedtest/history`, `POST /api/speedtest`, `GET /api/packetloss/monitors`,
`GET /api/dns/monitors` ; `internal/config/config.go` fixe l'ecoute par defaut
sur `127.0.0.1:7575` ; `internal/server/auth.go` laisse passer sans session tout
client dont l'IP est dans `auth.whitelist` (CIDR). Le chemin d'integration propre
est donc : Netronome lance en local, `whitelist = ["127.0.0.1/32"]`, ARENA lit
son API depuis la meme machine.

**Cinq regles portent ce connecteur :**

1. **Rien n'est simule.** Netronome eteint -> `NOT_CONFIGURED` avec la commande
   qui le lance. Jamais un debit plausible a la place d'une mesure.

2. **Un champ absent vaut `None`, jamais `0`.** Un debit non mesure n'est pas un
   debit nul. La traduction est litterale : ce que Netronome ne rend pas reste
   absent (voir `instantane_reseau`).

3. **Lire est libre, mesurer se confirme.** `etat` lit l'etat deja connu du
   service (lecture bon marche). `mesurer_debit` lance un vrai test de debit —
   il occupe la ligne plusieurs dizaines de secondes — et passe donc par la
   confirmation (`action="measure"`, politique `network`).

4. **Aucune cible reseau arbitraire n'est exposee au modele.** Le traceroute de
   Netronome vers un hote quelconque n'est volontairement PAS declare ici : il
   ouvrirait un scan interne pilotable par une entree non fiable. Le debit vise
   les serveurs deja configures dans Netronome, pas une cible libre.

5. **Aucun secret ne voyage dans un resultat.** Le cookie de session eventuel
   part dans l'en-tete, il n'entre dans aucun compte-rendu.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable, Dict, Optional

import httpx

from core.actions.resultat import ResultatAction, echec, non_configure, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante, _maintenant

logger = logging.getLogger("usman.connecteurs.netronome")

#: Ou joindre le service. `Host: 127.0.0.1`, `Port: 7575` dans
#: `internal/config/config.go`. L'adresse se change avec NETRONOME_URL.
BASE_URL = os.getenv("NETRONOME_URL", "http://127.0.0.1:7575")

#: Cookie de session optionnel, pour un Netronome qui n'a pas whiteliste ARENA.
#: Vide = on compte sur `auth.whitelist = ["127.0.0.1/32"]` cote Netronome, qui
#: est le chemin recommande pour une integration locale.
JETON_SESSION = os.getenv("NETRONOME_SESSION", "")

CE_QUI_MANQUE = (
    "Netronome lance sur la machine et joignable sur "
    f"{BASE_URL} (binaire autobrr/netronome : `netronome serve`), avec "
    'ARENA autorise sans session : `whitelist = ["127.0.0.1/32"]` dans la '
    "section [auth] de son config.toml. L'adresse se change avec NETRONOME_URL ; "
    "un cookie de session peut sinon etre fourni via NETRONOME_SESSION."
)

#: Fenetre par defaut demandee a l'historique. On ne veut que le dernier
#: resultat : `limit=1` suffit, `timeRange` borne la requete cote base.
FENETRE_HISTORIQUE = "1w"

#: On ne mesure la sante du service qu'une fois par minute : la sonde interroge
#: le reseau, la repeter a chaque appel couterait sans rien apprendre de neuf.
DUREE_SONDE_SECONDES = 60.0

#: Lecture d'etat : bornee court, c'est de la lecture de donnees deja calculees.
DELAI_LECTURE_SECONDES = 10.0

#: Un test de debit occupe la ligne : on laisse Netronome aller jusqu'a son
#: propre delai d'expiration avant d'abandonner cote client.
DELAI_MESURE_SECONDES = 180.0

QUOTA_LECTURE_PAR_MINUTE = 60
#: Plafond que **nous** nous imposons : un test de debit consomme de la bande
#: passante reelle. En empiler serait couteux et fausserait les mesures.
MESURES_PAR_MINUTE = 2


def _entetes() -> Dict[str, str]:
    """L'en-tete de session, vide quand ARENA passe par la whitelist."""
    return {"Cookie": f"session={JETON_SESSION}"} if JETON_SESSION else {}


def _get(chemin: str, parametres: Dict[str, Any], delai: float) -> Any:
    url = f"{BASE_URL.rstrip('/')}/{chemin.lstrip('/')}"
    with httpx.Client(timeout=delai) as client:
        reponse = client.get(url, params=parametres, headers=_entetes())
        reponse.raise_for_status()
        return reponse.json()


def _post(chemin: str, charge: Dict[str, Any], delai: float) -> Any:
    """Le seul chemin qui lance une mesure reelle."""
    url = f"{BASE_URL.rstrip('/')}/{chemin.lstrip('/')}"
    with httpx.Client(timeout=delai) as client:
        reponse = client.post(url, json=charge, headers=_entetes())
        reponse.raise_for_status()
        return reponse.json()


AppelGet = Callable[[str, Dict[str, Any], float], Any]
AppelPost = Callable[[str, Dict[str, Any], float], Any]


def _latence_ms(brut: Any) -> Optional[float]:
    """La latence en millisecondes, ou `None` si Netronome ne l'a pas rendue.

    Netronome porte la latence sous forme de chaine (« 12.3ms », « 1.2s »).
    On la traduit sans jamais inventer : illisible ou absente -> `None`.
    """
    if brut is None:
        return None
    if isinstance(brut, (int, float)):
        return float(brut)
    texte = str(brut).strip().lower()
    if not texte:
        return None
    try:
        if texte.endswith("ms"):
            return float(texte[:-2])
        if texte.endswith("s"):
            return float(texte[:-1]) * 1000.0
        return float(texte)
    except ValueError:
        return None


def instantane_reseau(
    dernier: Dict[str, Any], statut: Dict[str, Any],
    moniteurs_perte: Any, moniteurs_dns: Any,
) -> Dict[str, Any]:
    """Traduit l'etat Netronome dans le schema de sante reseau d'ARENA.

    La traduction est litterale : un champ que Netronome ne donne pas reste
    absent (`None`), jamais remplace par `0`. Les debits Netronome sont deja en
    Mbps ; on les laisse tels quels.
    """
    def _nombre(valeur: Any) -> Optional[float]:
        return float(valeur) if isinstance(valeur, (int, float)) else None

    perte = dernier.get("packetLoss")
    instantane: Dict[str, Any] = {
        "download": _nombre(dernier.get("downloadSpeed")),
        "upload": _nombre(dernier.get("uploadSpeed")),
        "latency": _latence_ms(dernier.get("latency")),
        "jitter": _nombre(dernier.get("jitter")),
        "packet_loss": _nombre(perte),
        "provider": dernier.get("testType") or None,
        "server": dernier.get("serverName") or None,
        "timestamp": dernier.get("createdAt") or None,
        # Traceroute non expose au modele (regle 4) : la route reste inconnue,
        # pas vide — la difference compte.
        "route_information": None,
        "test_en_cours": bool(statut.get("isComplete") is False and statut.get("type")),
    }

    if isinstance(moniteurs_perte, list):
        actifs = [m for m in moniteurs_perte if isinstance(m, dict) and m.get("enabled")]
        degrades = [m for m in actifs if str(m.get("lastState") or "").lower() in ("critical", "warning", "down")]
        instantane["packet_loss_monitors"] = {
            "total": len(moniteurs_perte), "actifs": len(actifs), "degrades": len(degrades),
        }

    if isinstance(moniteurs_dns, list):
        actifs = [m for m in moniteurs_dns if isinstance(m, dict) and m.get("enabled")]
        instantane["dns_monitors"] = {"total": len(moniteurs_dns), "actifs": len(actifs)}
        # La sante DNS globale n'est deduite que si Netronome la porte ; sinon
        # elle reste inconnue plutot que faussement « OK ».
        etats = [str(m.get("lastStatus") or m.get("lastState") or "").lower() for m in actifs]
        etats = [e for e in etats if e]
        if etats:
            instantane["dns_status"] = "degraded" if any(e not in ("ok", "up", "healthy") for e in etats) else "ok"

    return instantane


class NetronomeConnector(Connecteur):
    """Sante reseau mesuree par Netronome, en local, derriere son API HTTP."""

    service = "network"
    nom = "netronome"

    def __init__(
        self,
        appel_get: Optional[AppelGet] = None,
        appel_post: Optional[AppelPost] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._get = appel_get or _get
        self._post = appel_post or _post
        self._sante: Optional[Sante] = None
        self._sante_mesuree_a: float = 0.0

    # --- Capacites ------------------------------------------------------------

    def capacites(self) -> Dict[str, Capacite]:
        """Une lecture bon marche, une mesure couteuse. Rien d'autre.

        Le traceroute vers un hote libre n'est PAS declare : ce qui n'est pas
        ici n'existe pas (base.py, regle 1), et c'est voulu (regle 4 du module).
        """
        return {
            "etat": Capacite(
                nom="etat", action="read",
                description=("Lit la sante reseau deja connue de Netronome : dernier debit "
                             "mesure, latence, perte de paquets, moniteurs. Ne lance aucun test."),
                ecriture=False, quota_par_minute=QUOTA_LECTURE_PAR_MINUTE),
            "mesurer_debit": Capacite(
                nom="mesurer_debit", action="measure",
                description=("Lance un vrai test de debit (download/upload/latence) via Netronome. "
                             "Occupe la ligne plusieurs dizaines de secondes."),
                ecriture=True, quota_par_minute=MESURES_PAR_MINUTE),
        }

    def authentifier(self) -> bool:
        """Vrai : le service est local. La whitelist CIDR de Netronome remplace
        toute authentification cote ARENA ; un cookie de session n'est requis
        que si le proprietaire ne veut pas whitelister 127.0.0.1."""
        return True

    # --- Sante ----------------------------------------------------------------

    def sonder(self) -> Sante:
        """Demande le statut du dernier test. Un port ouvert ne prouve rien."""
        maintenant = time.monotonic()
        if self._sante is not None and maintenant - self._sante_mesuree_a < DUREE_SONDE_SECONDES:
            return self._sante

        try:
            self._get("/api/speedtest/status", {}, DELAI_LECTURE_SECONDES)
        except httpx.HTTPStatusError as erreur:
            code = erreur.response.status_code
            if code in (401, 403):
                sante = Sante(
                    etat=EtatSante.NON_CONFIGURE,
                    message=(f"Netronome repond sur {BASE_URL} mais refuse ARENA "
                             f"(HTTP {code}) : la whitelist ou la session manque."),
                    ce_qui_manque=CE_QUI_MANQUE, mesure_le=_maintenant())
            else:
                sante = Sante(
                    etat=EtatSante.EN_PANNE,
                    message=f"Netronome a repondu HTTP {code} sur {BASE_URL}.",
                    mesure_le=_maintenant())
        except (httpx.HTTPError, ValueError) as erreur:
            sante = Sante(
                etat=EtatSante.NON_CONFIGURE,
                message=(f"Netronome ne repond pas sur {BASE_URL} "
                         f"({type(erreur).__name__})."),
                ce_qui_manque=CE_QUI_MANQUE, mesure_le=_maintenant())
        else:
            sante = Sante(
                etat=EtatSante.OPERATIONNEL,
                message=f"Netronome repond sur {BASE_URL}.",
                mesure_le=_maintenant())

        self._sante = sante
        self._sante_mesuree_a = maintenant
        return sante

    # --- Execution ------------------------------------------------------------

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        if capacite.nom == "etat":
            return self._etat(capacite)
        return self._mesurer_debit(capacite, parametres)

    def _lire(self, chemin: str, parametres: Dict[str, Any]) -> Any:
        """Une lecture qui distingue « service absent » de « service casse »."""
        return self._get(chemin, parametres, DELAI_LECTURE_SECONDES)

    def _etat(self, capacite: Capacite) -> ResultatAction:
        """Lit l'etat deja connu du service. Ne lance aucun test."""
        try:
            statut = self._lire("/api/speedtest/status", {})
            historique = self._lire(
                "/api/speedtest/history",
                {"timeRange": FENETRE_HISTORIQUE, "page": 1, "limit": 1},
            )
        except httpx.HTTPStatusError as erreur:
            code = erreur.response.status_code
            if code in (401, 403):
                return non_configure(action=capacite.nom, cible=self.nom, ce_qui_manque=CE_QUI_MANQUE)
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"Netronome a repondu HTTP {code}.")
        except (httpx.HTTPError, ValueError):
            # Service injoignable : ce n'est pas un echec de mesure, c'est une
            # capacite absente. Le dire, avec la commande qui la reveille.
            return non_configure(action=capacite.nom, cible=self.nom, ce_qui_manque=CE_QUI_MANQUE)

        # Les moniteurs sont optionnels cote Netronome : leur absence n'est pas
        # une erreur, elle laisse simplement leur resume hors de l'instantane.
        moniteurs_perte = self._lire_optionnel("/api/packetloss/monitors")
        moniteurs_dns = self._lire_optionnel("/api/dns/monitors")

        dernier = self._premier_resultat(historique)
        instantane = instantane_reseau(
            dernier or {}, statut if isinstance(statut, dict) else {},
            moniteurs_perte, moniteurs_dns,
        )

        # « Une mesure existe » veut dire un vrai resultat de debit (latence,
        # download, upload). Des moniteurs configures mais sans resultat ne
        # remplacent pas cette mesure — leur resume reste dans l'instantane.
        if dernier is None:
            return succes(
                action=capacite.nom, cible=self.nom,
                message="Netronome repond, mais aucune mesure de debit n'existe encore.",
                preuve=f"GET {BASE_URL}/api/speedtest/status",
                donnees=instantane, mesure_disponible=False)

        return succes(
            action=capacite.nom, cible=self.nom,
            message="Sante reseau lue depuis Netronome.",
            preuve=f"GET {BASE_URL}/api/speedtest/history",
            donnees=instantane, mesure_disponible=True)

    def _lire_optionnel(self, chemin: str) -> Any:
        """Une lecture dont l'absence n'est pas une erreur (moniteur non active)."""
        try:
            return self._lire(chemin, {})
        except (httpx.HTTPError, ValueError) as erreur:
            logger.debug("Moniteur Netronome %s indisponible : %s", chemin, type(erreur).__name__)
            return None

    @staticmethod
    def _premier_resultat(historique: Any) -> Optional[Dict[str, Any]]:
        """Le dernier resultat de debit, ou `None` s'il n'y en a aucun."""
        donnees = historique.get("data") if isinstance(historique, dict) else historique
        if isinstance(donnees, list) and donnees and isinstance(donnees[0], dict):
            return donnees[0]
        return None

    def _mesurer_debit(self, capacite: Capacite, parametres: Dict[str, Any]) -> ResultatAction:
        """Lance un vrai test de debit. Appele **uniquement** apres confirmation."""
        corps: Dict[str, Any] = {}
        serveur = str(parametres.get("server_id") or "").strip()
        if serveur:
            # Une cible parmi les serveurs deja configures dans Netronome, jamais
            # un hote libre : on transmet un identifiant de serveur, pas une URL.
            corps["serverIds"] = [serveur]

        try:
            resultat = self._post("/api/speedtest", corps, DELAI_MESURE_SECONDES)
        except httpx.HTTPStatusError as erreur:
            code = erreur.response.status_code
            if code in (401, 403):
                return non_configure(action=capacite.nom, cible=self.nom, ce_qui_manque=CE_QUI_MANQUE)
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"Netronome a refuse le test (HTTP {code}).")
        except httpx.TimeoutException:
            return echec(action=capacite.nom, cible=self.nom,
                         message="Le test de debit a depasse le delai avant de rendre un resultat.")
        except (httpx.HTTPError, ValueError):
            return non_configure(action=capacite.nom, cible=self.nom, ce_qui_manque=CE_QUI_MANQUE)

        if not isinstance(resultat, dict):
            return echec(action=capacite.nom, cible=self.nom,
                         message="Netronome a accepte le test mais n'a pas rendu de resultat exploitable.")

        instantane = instantane_reseau(resultat, {}, None, None)
        identifiant = resultat.get("id")
        download = instantane.get("download")
        if download is None:
            # Un test « termine » sans debit mesure n'est pas une reussite.
            return echec(
                action=capacite.nom, cible=self.nom,
                message="Netronome a rendu un resultat sans debit mesurable.")

        return succes(
            action=capacite.nom, cible=self.nom,
            message=(f"Debit mesure : {download} Mbps down / "
                     f"{instantane.get('upload')} Mbps up."),
            preuve=str(identifiant) if identifiant is not None else f"POST {BASE_URL}/api/speedtest",
            donnees=instantane)
