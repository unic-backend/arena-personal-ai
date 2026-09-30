"""L'adaptateur de sante reseau : Netronome quand il est la, ARENA sinon.

C'est la **frontiere remplacable** exigee par l'architecture. Le reste d'ARENA
(diagnostics, chat, route) ne demande jamais Netronome directement : il demande
« le reseau est-il sain ? » a cet adaptateur, qui choisit sa source et le dit.

```
        ARENA (diagnostics, route /api/reseau/sante)
                        |
                evaluer_sante_reseau()      <- ce module
                        |
        +---------------+----------------+
        |                                |
   Netronome (optionnel)         Sonde native ARENA
   mesures completes             connectivite + DNS, sans dependance
```

Trois choses ne se negocient pas, reprises de CLAUDE.md :

1. **Une mesure absente se rapporte, elle ne se simule pas.** Sept statuts
   (`NON_CONFIGURE`, `INDISPONIBLE`, `DELAI_DEPASSE`, `ECHEC`, `PARTIEL`,
   `OPERATIONNEL`, `INCONNU`) disent exactement ou on en est. Aucun `0` ne
   remplace un debit non mesure.

2. **La sonde native ne pretend pas etre Netronome.** Elle mesure ce que la
   bibliotheque standard permet — une resolution DNS et un temps de connexion
   TCP — et laisse `None` tout le reste (debit, perte de paquets, gigue). Elle
   n'invente pas les mesures que seul Netronome sait prendre.

3. **ARENA fonctionne sans Netronome.** Netronome absent -> on retombe sur la
   sonde native, `source="natif"`, et on continue. C'est la definition meme
   d'une dependance optionnelle.
"""
from __future__ import annotations

import logging
import socket
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("usman.reseau.sante")


class StatutReseau(str, Enum):
    """L'issue d'une evaluation de sante reseau. Les valeurs traversent l'API."""

    NON_CONFIGURE = "NOT_CONFIGURED"  # aucune source de mesure branchee
    INDISPONIBLE = "UNAVAILABLE"      # source connue mais injoignable
    DELAI_DEPASSE = "TIMEOUT"         # la mesure n'a pas abouti a temps
    ECHEC = "FAILED"                  # tente, pas de resultat exploitable
    PARTIEL = "PARTIAL"               # une partie mesuree seulement
    OPERATIONNEL = "SUCCESS"          # reseau mesure et joignable
    INCONNU = "UNKNOWN"              # rien n'a pu etre determine


#: Cibles de la sonde native : des adresses IP publiques stables, joignables en
#: TCP/443, qu'on n'a pas besoin de resoudre pour tester la connectivite brute.
#: Ce ne sont PAS des fournisseurs d'IA et rien de sensible ne leur est envoye :
#: on ouvre une socket, on la referme.
CIBLES_CONNECTIVITE = (("1.1.1.1", 443), ("8.8.8.8", 443))

#: Nom a resoudre pour mesurer la sante DNS. Un nom neutre, pas une cible.
NOM_DNS_TEMOIN = "cloudflare.com"

#: La sonde native est bornee court : c'est un diagnostic explicite, pas une
#: boucle sur le chemin d'une conversation.
DELAI_SONDE_NATIVE = 2.0


def _maintenant() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class SanteReseau:
    """L'etat du reseau, avec sa source et de quoi le revérifier.

    Attributes:
        statut: l'un des sept statuts de `StatutReseau`.
        source: `netronome`, `natif`, ou `aucun`. Qui a produit la mesure.
        mesures: le schema de mesures d'ARENA. Un champ non mesure vaut `None`.
        message: une phrase lisible par le proprietaire.
        erreur: la cause quand `statut` n'est pas OPERATIONNEL, sinon `None`.
        mesure_le: horodatage UTC de l'evaluation.
        duree_ms: le temps qu'a pris l'evaluation elle-meme.
    """

    statut: StatutReseau
    source: str
    mesures: Dict[str, Any] = field(default_factory=dict)
    message: str = ""
    erreur: Optional[str] = None
    mesure_le: str = field(default_factory=_maintenant)
    duree_ms: Optional[float] = None

    @property
    def sain(self) -> bool:
        return self.statut is StatutReseau.OPERATIONNEL

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.statut.value,
            "source": self.source,
            "mesures": self.mesures,
            "message": self.message,
            "erreur": self.erreur,
            "mesure_le": self.mesure_le,
            "duree_ms": self.duree_ms,
        }


def _schema_vide() -> Dict[str, Any]:
    """Le schema de mesures, tout a `None` : rien mesure n'est pas rien a zero."""
    return {
        "network_status": None,
        "latency": None,
        "download": None,
        "upload": None,
        "jitter": None,
        "packet_loss": None,
        "dns_latency": None,
        "dns_status": None,
        "route_information": None,
        "provider": None,
        "timestamp": None,
    }


def sonde_native(
    cibles=CIBLES_CONNECTIVITE, nom_dns: str = NOM_DNS_TEMOIN,
    delai: float = DELAI_SONDE_NATIVE,
) -> Dict[str, Any]:
    """La sonde de repli : connectivite TCP + resolution DNS, sans dependance.

    Elle mesure honnetement ce que la bibliotheque standard permet et laisse a
    `None` ce qu'elle ne peut pas mesurer. Elle ne fait aucune requete HTTP,
    n'envoie aucune donnee : elle ouvre une socket vers un port et la referme.

    Returns:
        Un fragment du schema de mesures : `latency` (ms, connexion TCP la plus
        rapide), `dns_latency` (ms), `dns_status` (`ok`/`failed`/`None`), et un
        drapeau `_connecte` interne. Debit, perte et gigue restent `None` :
        seule une vraie mesure (Netronome) les connait.
    """
    resultat: Dict[str, Any] = _schema_vide()
    resultat["provider"] = "native"

    latences: List[float] = []
    for hote, port in cibles:
        debut = time.monotonic()
        connexion = None
        try:
            connexion = socket.create_connection((hote, port), timeout=delai)
        except (OSError, socket.timeout) as erreur:
            logger.debug("Sonde native : %s:%s injoignable (%s).", hote, port, type(erreur).__name__)
            continue
        else:
            latences.append((time.monotonic() - debut) * 1000.0)
        finally:
            if connexion is not None:
                connexion.close()

    connecte = bool(latences)
    resultat["_connecte"] = connecte
    if latences:
        resultat["latency"] = round(min(latences), 2)

    # Sante DNS : une resolution reussie et son temps. Un echec est un echec DNS,
    # pas une latence de zero.
    debut = time.monotonic()
    try:
        socket.getaddrinfo(nom_dns, None)
    except (OSError, socket.gaierror) as erreur:
        resultat["dns_status"] = "failed"
        logger.debug("Sonde native : resolution DNS de %s en echec (%s).", nom_dns, type(erreur).__name__)
    else:
        resultat["dns_status"] = "ok"
        resultat["dns_latency"] = round((time.monotonic() - debut) * 1000.0, 2)

    return resultat


def _evaluer_native(prober: Callable[[], Dict[str, Any]]) -> SanteReseau:
    """Construit un `SanteReseau` a partir de la seule sonde native."""
    debut = time.monotonic()
    try:
        brut = prober()
    except Exception as erreur:  # noqa: BLE001 — la sonde ne doit jamais faire tomber l'appelant
        logger.error("Sonde native en echec : %s", erreur)
        return SanteReseau(
            statut=StatutReseau.INCONNU, source="natif",
            mesures=_schema_vide(),
            message="La sonde reseau native a echoue.",
            erreur=f"{type(erreur).__name__}: {erreur}",
            duree_ms=round((time.monotonic() - debut) * 1000.0, 2))

    connecte = bool(brut.pop("_connecte", False))
    dns_status = brut.get("dns_status")
    mesures = {**_schema_vide(), **{k: v for k, v in brut.items() if k in _schema_vide()}}

    if connecte and dns_status == "ok":
        statut = StatutReseau.OPERATIONNEL
        mesures["network_status"] = "up"
        message = ("Reseau joignable (sonde native ARENA). Debit et perte de paquets "
                   "non mesures : Netronome n'est pas branche.")
        erreur = None
    elif connecte or dns_status == "ok":
        statut = StatutReseau.PARTIEL
        mesures["network_status"] = "degraded"
        message = "Reseau partiellement joignable (sonde native ARENA)."
        erreur = "connectivite ou DNS degrade"
    else:
        statut = StatutReseau.INDISPONIBLE
        mesures["network_status"] = "down"
        message = "Aucune connectivite reseau depuis la sonde native ARENA."
        erreur = "aucune cible joignable, resolution DNS en echec"

    return SanteReseau(
        statut=statut, source="natif", mesures=mesures, message=message, erreur=erreur,
        duree_ms=round((time.monotonic() - debut) * 1000.0, 2))


def _mesures_depuis_netronome(donnees: Dict[str, Any]) -> Dict[str, Any]:
    """Traduit l'instantane du connecteur Netronome dans le schema d'ARENA."""
    mesures = _schema_vide()
    correspondances = (
        "latency", "download", "upload", "jitter", "packet_loss",
        "dns_latency", "dns_status", "route_information", "provider", "timestamp",
    )
    for cle in correspondances:
        if donnees.get(cle) is not None:
            mesures[cle] = donnees[cle]
    return mesures


def evaluer_sante_reseau(
    registre: Any = None,
    prober_natif: Callable[[], Dict[str, Any]] = sonde_native,
    connecteur: str = "netronome",
) -> SanteReseau:
    """Evalue la sante reseau : Netronome d'abord, sonde native en repli.

    Args:
        registre: le `RegistreConnecteurs` d'ARENA. `None` -> on saute
            directement a la sonde native (aucune source riche branchee).
        prober_natif: la sonde de repli, injectable pour les tests.
        connecteur: le nom du connecteur reseau dans le registre.

    Returns:
        Un `SanteReseau`. Ne leve jamais : une panne devient un statut honnete,
        jamais une exception qui remonte dans le chemin de diagnostic.
    """
    debut = time.monotonic()

    if registre is None:
        return _evaluer_native(prober_natif)

    try:
        resultat = registre.executer(connecteur, "etat")
    except Exception as erreur:  # noqa: BLE001 — un registre en panne retombe sur le natif
        logger.error("Appel du connecteur reseau en echec : %s", erreur)
        return _evaluer_native(prober_natif)

    corps = resultat.to_dict() if hasattr(resultat, "to_dict") else {}
    statut_brut = corps.get("status")

    # Netronome absent ou non branche : on retombe sur la sonde native. C'est
    # le comportement de dependance optionnelle — ARENA ne s'arrete pas.
    if statut_brut in ("NOT_CONFIGURED", "NOT_IMPLEMENTED", "DENIED"):
        native = _evaluer_native(prober_natif)
        return SanteReseau(
            statut=native.statut, source="natif", mesures=native.mesures,
            message=f"{native.message} (Netronome indisponible : {statut_brut})",
            erreur=native.erreur,
            duree_ms=round((time.monotonic() - debut) * 1000.0, 2))

    if statut_brut in ("SUCCESS", "PARTIAL"):
        donnees = corps.get("detail", {}).get("donnees", {}) if isinstance(corps.get("detail"), dict) else {}
        mesures = _mesures_depuis_netronome(donnees if isinstance(donnees, dict) else {})
        mesure_disponible = bool(
            isinstance(corps.get("detail"), dict) and corps["detail"].get("mesure_disponible")
        )
        if mesure_disponible:
            mesures["network_status"] = "up"
            statut = StatutReseau.OPERATIONNEL
        else:
            mesures["network_status"] = "unknown"
            statut = StatutReseau.PARTIEL
        return SanteReseau(
            statut=statut, source="netronome", mesures=mesures,
            message=corps.get("response") or "Sante reseau lue depuis Netronome.",
            erreur=None,
            duree_ms=round((time.monotonic() - debut) * 1000.0, 2))

    # Netronome branche mais l'appel a echoue : c'est un echec de mesure, pas une
    # absence de source. On le dit, et on tente quand meme la sonde native pour
    # ne pas laisser ARENA aveugle.
    native = _evaluer_native(prober_natif)
    return SanteReseau(
        statut=StatutReseau.PARTIEL if native.sain else StatutReseau.ECHEC,
        source="natif",
        mesures=native.mesures,
        message=f"Netronome a echoue ; repli sur la sonde native. {native.message}",
        erreur=corps.get("response") or statut_brut or "echec Netronome",
        duree_ms=round((time.monotonic() - debut) * 1000.0, 2))
