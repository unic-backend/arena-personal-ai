"""Le connecteur Netronome : sante reseau locale, jamais simulee (DEC-0202).

Les appels HTTP sont injectes (`appel_get`/`appel_post`) : aucun vrai appel
reseau dans ces tests, meme pattern que `test_connecteur_moneyprinter.py`. Ce qui
touche vraiment le reseau est marque `integration` ailleurs.
"""
import httpx

from core.actions.resultat import Statut
from core.connectors.base import EtatSante
from core.connectors.netronome import (
    NetronomeConnector,
    _latence_ms,
    instantane_reseau,
)


def _erreur_http(code: int) -> httpx.HTTPStatusError:
    requete = httpx.Request("GET", "http://127.0.0.1:7575/api/speedtest/status")
    reponse = httpx.Response(code, request=requete)
    return httpx.HTTPStatusError(f"HTTP {code}", request=requete, response=reponse)


class FauxReseau:
    """Un Netronome factice : on lui dit quoi rendre par chemin d'URL."""

    def __init__(self, reponses=None, erreur=None, post=None, erreur_post=None):
        self.reponses = reponses or {}
        self.erreur = erreur
        self.post = post
        self.erreur_post = erreur_post
        self.appels_post = []

    def get(self, chemin, parametres, delai):
        if self.erreur is not None:
            raise self.erreur
        for suffixe, valeur in self.reponses.items():
            if chemin.endswith(suffixe):
                if isinstance(valeur, Exception):
                    raise valeur
                return valeur
        raise _erreur_http(404)

    def poster(self, chemin, charge, delai):
        self.appels_post.append((chemin, charge))
        if self.erreur_post is not None:
            raise self.erreur_post
        return self.post


def _connecteur(faux: FauxReseau) -> NetronomeConnector:
    return NetronomeConnector(appel_get=faux.get, appel_post=faux.poster)


# --- Traduction des mesures --------------------------------------------------


class TestLatenceMs:
    def test_millisecondes(self):
        assert _latence_ms("12.3ms") == 12.3

    def test_secondes_converties(self):
        assert _latence_ms("1.2s") == 1200.0

    def test_nombre_brut(self):
        assert _latence_ms(15) == 15.0

    def test_absente_reste_none(self):
        assert _latence_ms(None) is None
        assert _latence_ms("") is None

    def test_illisible_reste_none(self):
        assert _latence_ms("rapide") is None


class TestInstantaneReseau:
    def test_champs_traduits(self):
        dernier = {
            "downloadSpeed": 95.4, "uploadSpeed": 12.1, "latency": "8.5ms",
            "jitter": 1.2, "packetLoss": 0.5, "testType": "speedtest",
            "serverName": "Dakar", "createdAt": "2026-09-30T10:00:00Z",
        }
        vu = instantane_reseau(dernier, {}, None, None)
        assert vu["download"] == 95.4
        assert vu["upload"] == 12.1
        assert vu["latency"] == 8.5
        assert vu["packet_loss"] == 0.5
        assert vu["provider"] == "speedtest"
        assert vu["route_information"] is None

    def test_champ_absent_reste_none_jamais_zero(self):
        vu = instantane_reseau({}, {}, None, None)
        assert vu["download"] is None
        assert vu["upload"] is None
        assert vu["packet_loss"] is None

    def test_moniteurs_resumes(self):
        perte = [{"enabled": True, "lastState": "critical"}, {"enabled": False}]
        dns = [{"enabled": True, "lastStatus": "ok"}]
        vu = instantane_reseau({}, {}, perte, dns)
        assert vu["packet_loss_monitors"] == {"total": 2, "actifs": 1, "degrades": 1}
        assert vu["dns_monitors"] == {"total": 1, "actifs": 1}
        assert vu["dns_status"] == "ok"


# --- Capacites ---------------------------------------------------------------


def test_capacites_lecture_libre_mesure_ecriture():
    caps = NetronomeConnector().capacites()
    assert set(caps) == {"etat", "mesurer_debit"}
    assert caps["etat"].action == "read"
    assert caps["etat"].ecriture is False
    assert caps["mesurer_debit"].action == "measure"
    assert caps["mesurer_debit"].ecriture is True


def test_aucune_cible_reseau_arbitraire_exposee():
    """Le traceroute vers un hote libre n'est PAS declare (regle de securite)."""
    caps = NetronomeConnector().capacites()
    assert "traceroute" not in caps
    assert "ping" not in caps


# --- Sonde de sante ----------------------------------------------------------


def test_sonde_operationnelle_quand_le_service_repond():
    faux = FauxReseau(reponses={"/api/speedtest/status": {}})
    sante = _connecteur(faux).sonder()
    assert sante.etat is EtatSante.OPERATIONNEL
    assert sante.mesure_le is not None


def test_sonde_non_configure_quand_injoignable():
    faux = FauxReseau(erreur=httpx.ConnectError("refuse"))
    sante = _connecteur(faux).sonder()
    assert sante.etat is EtatSante.NON_CONFIGURE
    assert "Netronome" in sante.ce_qui_manque


def test_sonde_non_configure_sur_401():
    faux = FauxReseau(erreur=_erreur_http(401))
    sante = _connecteur(faux).sonder()
    assert sante.etat is EtatSante.NON_CONFIGURE


def test_sonde_en_panne_sur_500():
    faux = FauxReseau(erreur=_erreur_http(500))
    sante = _connecteur(faux).sonder()
    assert sante.etat is EtatSante.EN_PANNE


# --- Lecture d'etat ----------------------------------------------------------


def test_etat_rend_les_mesures():
    faux = FauxReseau(reponses={
        "/api/speedtest/status": {"isComplete": True},
        "/api/speedtest/history": {"data": [{
            "id": 7, "downloadSpeed": 100.0, "uploadSpeed": 20.0,
            "latency": "9ms", "packetLoss": 0.0,
        }], "total": 1},
        "/api/packetloss/monitors": [],
        "/api/dns/monitors": [],
    })
    resultat = _connecteur(faux).executer("etat")
    assert resultat.statut is Statut.SUCCES
    assert resultat.detail["donnees"]["download"] == 100.0
    assert resultat.detail["mesure_disponible"] is True


def test_etat_non_configure_quand_injoignable():
    faux = FauxReseau(erreur=httpx.ConnectError("refuse"))
    resultat = _connecteur(faux).executer("etat")
    assert resultat.statut is Statut.NON_CONFIGURE


def test_etat_succes_mais_sans_mesure_le_dit():
    """Netronome tourne mais n'a encore rien mesure : succes honnete, pas de mesure."""
    faux = FauxReseau(reponses={
        "/api/speedtest/status": {},
        "/api/speedtest/history": {"data": [], "total": 0},
        "/api/packetloss/monitors": [],
        "/api/dns/monitors": [],
    })
    resultat = _connecteur(faux).executer("etat")
    assert resultat.statut is Statut.SUCCES
    assert resultat.detail["mesure_disponible"] is False


def test_etat_401_est_non_configure():
    faux = FauxReseau(reponses={"/api/speedtest/status": _erreur_http(403)})
    resultat = _connecteur(faux).executer("etat")
    assert resultat.statut is Statut.NON_CONFIGURE


# --- Mesure de debit (couteuse, confirmee) -----------------------------------


def test_mesurer_debit_demande_confirmation():
    faux = FauxReseau(reponses={"/api/speedtest/status": {}}, post={"id": 1, "downloadSpeed": 50.0})
    resultat = _connecteur(faux).executer("mesurer_debit")
    # La politique network.measure vaut CONFIRMATION : rien n'est parti.
    assert resultat.statut is Statut.A_CONFIRMER
    assert faux.appels_post == []


def test_mesurer_debit_confirme_rend_le_debit():
    faux = FauxReseau(reponses={"/api/speedtest/status": {}}, post={"id": 42, "downloadSpeed": 88.0, "uploadSpeed": 11.0, "latency": "7ms"})
    resultat = _connecteur(faux).executer_confirmee("mesurer_debit")
    assert resultat.statut is Statut.SUCCES
    assert resultat.preuve == "42"
    assert resultat.detail["donnees"]["download"] == 88.0


def test_mesurer_debit_sans_debit_est_un_echec():
    """Un test « termine » sans debit mesurable n'est pas une reussite."""
    faux = FauxReseau(reponses={"/api/speedtest/status": {}}, post={"id": 42})
    resultat = _connecteur(faux).executer_confirmee("mesurer_debit")
    assert resultat.statut is Statut.ECHEC


def test_mesurer_debit_timeout_est_un_echec_pas_un_zero():
    faux = FauxReseau(reponses={"/api/speedtest/status": {}}, erreur_post=httpx.TimeoutException("trop long"))
    resultat = _connecteur(faux).executer_confirmee("mesurer_debit")
    assert resultat.statut is Statut.ECHEC
    assert "delai" in resultat.message.lower()


def test_mesurer_debit_ne_passe_que_des_serveurs_configures():
    """`server_id` devient un identifiant de serveur Netronome, jamais un hote libre."""
    faux = FauxReseau(reponses={"/api/speedtest/status": {}}, post={"id": 1, "downloadSpeed": 5.0})
    _connecteur(faux).executer_confirmee("mesurer_debit", server_id="dakar-1")
    assert faux.appels_post[0][1] == {"serverIds": ["dakar-1"]}


def test_capacite_inconnue_ne_touche_pas_le_reseau():
    faux = FauxReseau()
    resultat = _connecteur(faux).executer("traceroute", host="8.8.8.8")
    assert resultat.statut is Statut.NON_IMPLEMENTE
    assert faux.appels_post == []
