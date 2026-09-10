"""Le connecteur de donnees de marche : CoinGecko, lecture seule, sans cle.

`FauxClient` simule ce que CoinGecko rendrait — jamais un vrai appel reseau
dans les tests. Meme pattern que `tests/core/test_connecteur_securite_chantier.py`.
"""
import pytest

from core.actions.resultat import Statut
from core.connectors.base import EtatSante
from core.connectors.market_data import ConnecteurMarketData, identifiant_coingecko


class FausseReponse:
    def __init__(self, status_code=200, donnees=None, texte=""):
        self.status_code = status_code
        self._donnees = donnees if donnees is not None else {}
        self.text = texte or str(donnees)

    def json(self):
        return self._donnees


class FauxClient:
    reponses_get: dict = {}
    appels: list = []

    def __init__(self, **kw):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get(self, url, **kw):
        FauxClient.appels.append(("GET", url, kw.get("params")))
        for suffixe, reponse in FauxClient.reponses_get.items():
            if url.endswith(suffixe):
                return reponse
        return FausseReponse(404)


@pytest.fixture(autouse=True)
def _reinitialiser_faux_client(monkeypatch):
    import core.connectors.market_data as module
    FauxClient.reponses_get = {"/ping": FausseReponse(200, {"gecko_says": "(V3) To the Moon!"})}
    FauxClient.appels = []
    monkeypatch.setattr(module.httpx, "Client", FauxClient)


class TestIdentifiantCoinGecko:
    def test_ticker_connu_traduit(self):
        assert identifiant_coingecko("BTC") == "bitcoin"
        assert identifiant_coingecko("eth") == "ethereum"
        assert identifiant_coingecko("SOL") == "solana"

    def test_id_inconnu_passe_tel_quel(self):
        assert identifiant_coingecko("chainlink") == "chainlink"


class TestSonde:
    def test_coingecko_joignable_operationnel(self):
        sante = ConnecteurMarketData().sonder()
        assert sante.etat is EtatSante.OPERATIONNEL

    def test_coingecko_en_panne(self):
        FauxClient.reponses_get = {"/ping": FausseReponse(500)}
        sante = ConnecteurMarketData().sonder()
        assert sante.etat is EtatSante.EN_PANNE

    def test_coingecko_injoignable_non_configure(self, monkeypatch):
        import httpx

        import core.connectors.market_data as module

        class ClientQuiEchoue:
            def __init__(self, **kw):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def get(self, *a, **kw):
                raise httpx.ConnectError("refuse")

        monkeypatch.setattr(module.httpx, "Client", ClientQuiEchoue)
        sante = ConnecteurMarketData().sonder()
        assert sante.etat is EtatSante.NON_CONFIGURE


class TestPrix:
    def test_prix_reel_recupere(self):
        FauxClient.reponses_get["/simple/price"] = FausseReponse(200, {
            "bitcoin": {"usd": 78107, "usd_24h_change": -1.8},
        })
        resultat = ConnecteurMarketData().executer("prix", actifs=["bitcoin"])
        assert resultat.statut is Statut.SUCCES, resultat.message
        assert resultat.detail["prix"]["bitcoin"]["usd"] == 78107
        assert resultat.preuve  # une preuve existe toujours pour un succes

    def test_ticker_traduit_avant_l_appel(self):
        FauxClient.reponses_get["/simple/price"] = FausseReponse(200, {
            "bitcoin": {"usd": 78107},
        })
        resultat = ConnecteurMarketData().executer("prix", actifs=["BTC"])
        assert resultat.statut is Statut.SUCCES
        # La cle rendue est celle DEMANDEE ("BTC"), jamais l'id CoinGecko —
        # c'est ce que l'appelant a nomme.
        assert "BTC" in resultat.detail["prix"]

    def test_aucun_actif_est_un_echec(self):
        resultat = ConnecteurMarketData().executer("prix", actifs=[])
        assert resultat.statut is Statut.ECHEC
        assert [a for a in FauxClient.appels if a[1].endswith("/simple/price")] == []

    def test_actif_inconnu_de_coingecko_est_un_echec(self):
        FauxClient.reponses_get["/simple/price"] = FausseReponse(200, {})
        resultat = ConnecteurMarketData().executer("prix", actifs=["mot-invente-xyz"])
        assert resultat.statut is Statut.ECHEC

    def test_actif_partiellement_trouve_le_signale(self):
        FauxClient.reponses_get["/simple/price"] = FausseReponse(200, {
            "bitcoin": {"usd": 78107},
        })
        resultat = ConnecteurMarketData().executer("prix", actifs=["bitcoin", "mot-invente-xyz"])
        assert resultat.statut is Statut.SUCCES
        assert "mot-invente-xyz" in resultat.detail["manquants"]

    def test_coingecko_refuse_est_un_echec(self):
        FauxClient.reponses_get["/simple/price"] = FausseReponse(429, texte="rate limited")
        resultat = ConnecteurMarketData().executer("prix", actifs=["bitcoin"])
        assert resultat.statut is Statut.ECHEC
        assert "429" in resultat.message


class TestHistorique:
    def test_historique_reel_recupere(self):
        FauxClient.reponses_get["/market_chart"] = FausseReponse(200, {
            "prices": [[1000, 100.0], [2000, 105.0], [3000, 98.0]],
        })
        resultat = ConnecteurMarketData().executer("historique", actif="bitcoin", jours=30)
        assert resultat.statut is Statut.SUCCES, resultat.message
        assert resultat.detail["points"] == [[1000, 100.0], [2000, 105.0], [3000, 98.0]]

    def test_jours_est_plafonne(self):
        FauxClient.reponses_get["/market_chart"] = FausseReponse(200, {"prices": [[1, 1.0]]})
        resultat = ConnecteurMarketData().executer("historique", actif="bitcoin", jours=99999)
        assert resultat.statut is Statut.SUCCES
        appel = [a for a in FauxClient.appels if a[1].endswith("/market_chart")][0]
        assert appel[2]["days"] == 365

    def test_jours_invalide_retombe_sur_le_defaut(self):
        FauxClient.reponses_get["/market_chart"] = FausseReponse(200, {"prices": [[1, 1.0]]})
        resultat = ConnecteurMarketData().executer("historique", actif="bitcoin", jours="pas-un-nombre")
        assert resultat.statut is Statut.SUCCES
        appel = [a for a in FauxClient.appels if a[1].endswith("/market_chart")][0]
        assert appel[2]["days"] == 30

    def test_aucun_actif_est_un_echec(self):
        resultat = ConnecteurMarketData().executer("historique", actif="")
        assert resultat.statut is Statut.ECHEC

    def test_actif_inconnu_404_est_un_echec_explicite(self):
        FauxClient.reponses_get["/market_chart"] = FausseReponse(404)
        resultat = ConnecteurMarketData().executer("historique", actif="mot-invente-xyz")
        assert resultat.statut is Statut.ECHEC
        assert "inconnu" in resultat.message.lower()

    def test_historique_vide_est_un_echec(self):
        FauxClient.reponses_get["/market_chart"] = FausseReponse(200, {"prices": []})
        resultat = ConnecteurMarketData().executer("historique", actif="bitcoin")
        assert resultat.statut is Statut.ECHEC


class TestAucuneEcriture:
    """La garantie centrale de la mission (§10) : ce connecteur ne peut
    executer aucun ordre, aucune ecriture — verifie sur les capacites REELLEMENT
    declarees, pas sur une intention."""

    def test_aucune_capacite_d_ecriture_declaree(self):
        capacites = ConnecteurMarketData().capacites()
        assert all(not c.ecriture for c in capacites.values())
        assert set(capacites) == {"prix", "historique"}


class TestLaVraiePolitiqueLivree:
    def test_lire_reste_allowed_dans_le_depot_reel(self):
        from core.permissions.politique import FICHIER_POLITIQUE, PolitiqueDePermissions

        regle = PolitiqueDePermissions(chemin=FICHIER_POLITIQUE).regle("market_data", "read")
        assert regle is not None, "market_data.read a disparu de la politique livree"
        assert regle.get("decision") == "ALLOWED"
