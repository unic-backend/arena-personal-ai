"""L'adaptateur de sante reseau : Netronome quand il est la, natif sinon (DEC-0202).

Aucun vrai appel reseau dans le cas Netronome : le registre est factice. La
sonde native est testee sur des cibles locales qui echouent vite, sans sortir
de la machine — pas de dependance a un reseau pour un test hors ligne.
"""
from core.actions.resultat import a_confirmer, echec, non_configure, succes
from core.reseau.sante_reseau import (
    SanteReseau,
    StatutReseau,
    evaluer_sante_reseau,
    sonde_native,
)


class FauxRegistre:
    def __init__(self, resultat=None, leve=False):
        self._resultat = resultat
        self._leve = leve
        self.appels = []

    def executer(self, nom, capacite):
        self.appels.append((nom, capacite))
        if self._leve:
            raise RuntimeError("registre casse")
        return self._resultat


def _prober(connecte=True, dns="ok", latency=8.0):
    def sonde():
        base = {
            "network_status": None, "latency": latency if connecte else None,
            "download": None, "upload": None, "jitter": None, "packet_loss": None,
            "dns_latency": 3.0 if dns == "ok" else None, "dns_status": dns,
            "route_information": None, "provider": "native", "timestamp": None,
            "_connecte": connecte,
        }
        return base
    return sonde


# --- Sonde native : mesure ce qu'elle peut, invente rien ---------------------


def test_sonde_native_ne_fabrique_pas_les_mesures_absentes():
    vu = sonde_native(cibles=(("127.0.0.1", 1),), nom_dns="localhost", delai=0.5)
    # Debit, perte et gigue ne sont PAS mesurables nativement : ils restent None.
    assert vu["download"] is None
    assert vu["upload"] is None
    assert vu["packet_loss"] is None
    # localhost se resout sans reseau : la sante DNS est mesurable.
    assert vu["dns_status"] == "ok"


def test_sonde_native_rapporte_dns_en_echec():
    vu = sonde_native(cibles=(("127.0.0.1", 1),), nom_dns="nom.invalide.qui.n.existe.pas.arena", delai=0.5)
    assert vu["dns_status"] in ("failed", "ok")  # selon le resolveur ; jamais None ici


# --- Repli natif quand aucun registre ----------------------------------------


def test_sans_registre_utilise_le_natif_operationnel():
    sante = evaluer_sante_reseau(registre=None, prober_natif=_prober(connecte=True, dns="ok"))
    assert sante.statut is StatutReseau.OPERATIONNEL
    assert sante.source == "natif"
    assert sante.mesures["download"] is None  # jamais fabrique
    assert sante.mesures["network_status"] == "up"


def test_natif_partiel_quand_dns_tombe():
    sante = evaluer_sante_reseau(registre=None, prober_natif=_prober(connecte=True, dns="failed"))
    assert sante.statut is StatutReseau.PARTIEL


def test_natif_indisponible_quand_rien_ne_repond():
    sante = evaluer_sante_reseau(registre=None, prober_natif=_prober(connecte=False, dns="failed"))
    assert sante.statut is StatutReseau.INDISPONIBLE
    assert sante.mesures["network_status"] == "down"


# --- Netronome branche -------------------------------------------------------


def test_netronome_succes_mesure_disponible():
    resultat = succes(
        action="etat", cible="netronome", message="ok", preuve="GET",
        donnees={"latency": 9.0, "download": 100.0, "upload": 20.0, "packet_loss": 0.0},
        mesure_disponible=True)
    registre = FauxRegistre(resultat=resultat)
    sante = evaluer_sante_reseau(registre=registre, prober_natif=_prober())
    assert sante.statut is StatutReseau.OPERATIONNEL
    assert sante.source == "netronome"
    assert sante.mesures["download"] == 100.0
    assert sante.mesures["latency"] == 9.0
    assert sante.mesures["network_status"] == "up"
    assert registre.appels == [("netronome", "etat")]


def test_netronome_succes_sans_mesure_est_partiel():
    resultat = succes(
        action="etat", cible="netronome", message="pas encore de mesure", preuve="GET",
        donnees={}, mesure_disponible=False)
    sante = evaluer_sante_reseau(registre=FauxRegistre(resultat=resultat), prober_natif=_prober())
    assert sante.statut is StatutReseau.PARTIEL
    assert sante.source == "netronome"


# --- Netronome absent ou casse : ARENA continue ------------------------------


def test_netronome_non_configure_retombe_sur_le_natif():
    resultat = non_configure(action="etat", cible="netronome", ce_qui_manque="Netronome")
    sante = evaluer_sante_reseau(
        registre=FauxRegistre(resultat=resultat), prober_natif=_prober(connecte=True, dns="ok"))
    assert sante.source == "natif"
    assert sante.statut is StatutReseau.OPERATIONNEL
    assert "Netronome indisponible" in sante.message


def test_registre_qui_leve_retombe_sur_le_natif():
    sante = evaluer_sante_reseau(registre=FauxRegistre(leve=True), prober_natif=_prober())
    assert sante.source == "natif"
    assert sante.statut is StatutReseau.OPERATIONNEL


def test_netronome_refuse_retombe_sur_le_natif():
    """Une capacite refusee par la politique n'empeche pas ARENA de mesurer."""
    from core.actions.resultat import ResultatAction, Statut
    resultat = ResultatAction(Statut.REFUSE, "etat", "netronome", "refuse")
    sante = evaluer_sante_reseau(registre=FauxRegistre(resultat=resultat), prober_natif=_prober())
    assert sante.source == "natif"


def test_netronome_echec_reel_est_signale():
    resultat = echec(action="etat", cible="netronome", message="HTTP 500")
    sante = evaluer_sante_reseau(
        registre=FauxRegistre(resultat=resultat), prober_natif=_prober(connecte=False, dns="failed"))
    # Netronome a vraiment echoue (pas juste absent) et le natif ne sauve rien.
    assert sante.statut is StatutReseau.ECHEC
    assert sante.erreur is not None


def test_netronome_a_confirmer_nest_pas_traite_comme_une_mesure():
    resultat = a_confirmer(action="etat", cible="netronome", message="?")
    sante = evaluer_sante_reseau(registre=FauxRegistre(resultat=resultat), prober_natif=_prober())
    # Un statut inattendu ne devient jamais un SUCCESS : on retombe honnetement.
    assert sante.statut in (StatutReseau.PARTIEL, StatutReseau.ECHEC)


# --- Contrat de forme --------------------------------------------------------


def test_to_dict_porte_le_schema_complet():
    sante = evaluer_sante_reseau(registre=None, prober_natif=_prober())
    corps = sante.to_dict()
    for cle in ("status", "source", "mesures", "message", "erreur", "mesure_le", "duree_ms"):
        assert cle in corps
    for cle in ("latency", "download", "upload", "jitter", "packet_loss",
                "dns_latency", "dns_status", "route_information", "provider", "timestamp"):
        assert cle in corps["mesures"]
    assert isinstance(sante, SanteReseau)
