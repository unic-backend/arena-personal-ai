"""L'agent finance : donnees reelles -> calcul -> risque -> interpretation,
dans cet ordre fixe, jamais l'inverse.

Le test le plus important de ce fichier est `TestJamaisDeFabrication` :
quand les donnees de marche sont indisponibles, le modele n'est JAMAIS
consulte — c'est le defaut precis reproche a AutoHedge dans l'audit.
"""
import pytest

from agents.finance.finance_agent import FinanceAgent, extraire_actif, extraire_ordre_simule
from core.actions.resultat import ResultatAction, echec, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante
from core.connectors.registre import RegistreConnecteurs
from core.finance.paper_trading import PortefeuilleSimule
from core.models.base import ModelProvider


@pytest.fixture
def portefeuille(tmp_path):
    """Jamais `data/database/memory.db` reel dans un test — meme convention
    que la fixture `memoire` de `tests/conftest.py`."""
    return PortefeuilleSimule(db_path=str(tmp_path / "finance_test.db"))


class FauxConnecteurMarketData(Connecteur):
    """Remplace ConnecteurMarketData dans le registre. Un vrai `Connecteur`
    (le registre refuse tout le reste — `isinstance` verifie, voir
    `RegistreConnecteurs.obtenir`), mais dont `_executer` rend des donnees
    canned plutot que d'appeler CoinGecko : le comportement HTTP reel est
    deja couvert par `tests/core/test_connecteur_market_data.py`."""

    service = "market_data"
    nom = "market_data"

    def __init__(self, points=None, echoue_historique=False, echoue_prix=False, **kwargs):
        super().__init__(**kwargs)
        self.points = points or [(i * 1000, 100.0 + i) for i in range(40)]
        self.echoue_historique = echoue_historique
        self.echoue_prix = echoue_prix
        self.appels = []

    def capacites(self):
        return {
            "prix": Capacite(nom="prix", action="read", description="test", ecriture=False),
            "historique": Capacite(nom="historique", action="read", description="test", ecriture=False),
        }

    def authentifier(self) -> bool:
        return True

    def sonder(self) -> Sante:
        return Sante(etat=EtatSante.OPERATIONNEL, message="test")

    def _executer(self, capacite: Capacite, **parametres) -> ResultatAction:
        self.appels.append((capacite.nom, parametres))
        if capacite.nom == "prix":
            if self.echoue_prix:
                return echec("prix", "market_data", "en panne")
            return succes("prix", "market_data", "ok", preuve="test",
                           prix={parametres["actifs"][0]: {"usd": self.points[-1][1]}})
        if capacite.nom == "historique":
            if self.echoue_historique:
                return echec("historique", "market_data", "CoinGecko injoignable : test")
            return succes("historique", "market_data", "ok", preuve="test",
                           points=self.points, actif=parametres.get("actif"))
        raise AssertionError(f"capacite inattendue : {capacite.nom}")


class FauxProvider(ModelProvider):
    def __init__(self, reponse="Interpretation de test.", leve=False):
        self.reponse = reponse
        self.leve = leve
        self.prompts_recus = []

    async def generate(self, prompt, system_prompt=None):
        self.prompts_recus.append(prompt)
        if self.leve:
            raise RuntimeError("modele indisponible")
        return self.reponse

    async def is_available(self):
        return True


class FauxRecherche:
    def __init__(self, resultats=None):
        self.resultats = resultats if resultats is not None else [
            {"title": "Le bitcoin en hausse", "body": "Contenu externe non fiable.",
             "href": "https://exemple.test/article"},
        ]
        self.appels = []

    def search(self, query, max_results=3, recent=False):
        self.appels.append(query)
        return self.resultats


def _registre(connecteur):
    registre = RegistreConnecteurs()
    registre.declarer("market_data", lambda: connecteur)
    return registre


class TestExtraireActif:
    def test_nom_complet_reconnu(self):
        assert extraire_actif("analyse le bitcoin") == "bitcoin"

    def test_ticker_reconnu(self):
        assert extraire_actif("analyse le BTC") == "bitcoin"

    def test_aucun_actif_rend_none(self):
        assert extraire_actif("quel temps fait-il") is None


class TestAucunActifReconnu:
    @pytest.mark.asyncio
    async def test_repond_sans_appeler_le_connecteur(self, portefeuille):
        connecteur = FauxConnecteurMarketData()
        agent = FinanceAgent(provider=FauxProvider(), registre=_registre(connecteur), portefeuille=portefeuille)
        resultat = await agent.run("quel temps fait-il aujourd'hui")
        assert resultat["status"] == "warning"
        assert connecteur.appels == []


class TestJamaisDeFabrication:
    """Le defaut precis de l'audit AutoHedge (docs/audits/autohedge_audit.md) :
    aucune donnee reelle -> aucun calcul, aucune interpretation inventee."""

    @pytest.mark.asyncio
    async def test_historique_indisponible_ne_consulte_jamais_le_modele(self, portefeuille):
        connecteur = FauxConnecteurMarketData(echoue_historique=True)
        provider = FauxProvider()
        agent = FinanceAgent(provider=provider, registre=_registre(connecteur), portefeuille=portefeuille)
        resultat = await agent.run("analyse le bitcoin")

        assert resultat["status"] == "error"
        assert resultat["analyse_financiere"]["market_state"] == "DONNEES_INDISPONIBLES"
        assert resultat["analyse_financiere"]["quant_analysis"] == {}
        assert resultat["analyse_financiere"]["risk_analysis"] == {}
        # Le point qui compte : le modele n'a JAMAIS ete appele.
        assert provider.prompts_recus == []


class TestAnalyseComplete:
    @pytest.mark.asyncio
    async def test_analyse_avec_donnees_reelles(self, portefeuille):
        # Serie croissante : tendance HAUSSIERE garantie (SMA20 > SMA50).
        points = [(i * 1000, 100.0 + i) for i in range(60)]
        connecteur = FauxConnecteurMarketData(points=points)
        provider = FauxProvider(reponse="Le bitcoin monte regulierement.")
        recherche = FauxRecherche()
        agent = FinanceAgent(provider=provider, registre=_registre(connecteur), recherche=recherche,
                              portefeuille=portefeuille)

        resultat = await agent.run("analyse le bitcoin")

        assert resultat["status"] == "success"
        analyse = resultat["analyse_financiere"]
        assert analyse["asset"] == "bitcoin"
        assert analyse["trend"] == "HAUSSIERE"
        assert analyse["quant_analysis"]["points"] == 60
        assert analyse["risk_analysis"]["niveau_global"] is not None
        assert analyse["interpretation"] == "Le bitcoin monte regulierement."
        assert resultat["response"] == "Le bitcoin monte regulierement."
        # La recherche a bien ete utilisee, et sa provenance conservee.
        assert recherche.appels
        assert analyse["sources"] == ["https://exemple.test/article"]

    @pytest.mark.asyncio
    async def test_le_prompt_d_interpretation_porte_les_vrais_chiffres(self, portefeuille):
        """Le modele ne DEVINE pas la tendance : il la recoit deja calculee."""
        points = [(i * 1000, 100.0 + i) for i in range(60)]
        connecteur = FauxConnecteurMarketData(points=points)
        provider = FauxProvider()
        agent = FinanceAgent(provider=provider, registre=_registre(connecteur), recherche=FauxRecherche(),
                              portefeuille=portefeuille)

        await agent.run("analyse le bitcoin")

        assert provider.prompts_recus
        prompt = provider.prompts_recus[0]
        assert "HAUSSIERE" in prompt
        assert "N'invente AUCUN chiffre" in prompt

    @pytest.mark.asyncio
    async def test_modele_indisponible_garde_les_chiffres_calcules(self, portefeuille):
        """Un modele en panne ne prive jamais des chiffres deja produits —
        seule l'interpretation en prose manque."""
        points = [(i * 1000, 100.0 + i) for i in range(60)]
        connecteur = FauxConnecteurMarketData(points=points)
        provider = FauxProvider(leve=True)
        agent = FinanceAgent(provider=provider, registre=_registre(connecteur), recherche=FauxRecherche(),
                              portefeuille=portefeuille)

        resultat = await agent.run("analyse le bitcoin")

        assert resultat["status"] == "success"
        analyse = resultat["analyse_financiere"]
        assert analyse["interpretation"] is None
        assert analyse["trend"] == "HAUSSIERE"  # le calcul, lui, est intact
        assert analyse["quant_analysis"]["points"] == 60
        assert "risque" in resultat["response"].lower()  # le repli sans modele

    @pytest.mark.asyncio
    async def test_recherche_en_panne_n_empeche_pas_l_analyse(self, portefeuille):
        class RechercheQuiLeve:
            def search(self, query, max_results=3, recent=False):
                raise RuntimeError("DDGS indisponible")

        points = [(i * 1000, 100.0 + i) for i in range(60)]
        connecteur = FauxConnecteurMarketData(points=points)
        agent = FinanceAgent(provider=FauxProvider(), registre=_registre(connecteur),
                              recherche=RechercheQuiLeve(), portefeuille=portefeuille)

        resultat = await agent.run("analyse le bitcoin")
        assert resultat["status"] == "success"

    @pytest.mark.asyncio
    async def test_court_historique_baisse_la_confiance_et_le_dit(self, portefeuille):
        # Juste assez pour un calcul (5 points), loin des 30 requis pour ELEVEE.
        points = [(i * 1000, 100.0 - i) for i in range(6)]
        connecteur = FauxConnecteurMarketData(points=points)
        agent = FinanceAgent(provider=FauxProvider(), registre=_registre(connecteur),
                              recherche=FauxRecherche(resultats=[]), portefeuille=portefeuille)

        resultat = await agent.run("analyse le bitcoin")
        analyse = resultat["analyse_financiere"]
        assert analyse["confidence"] in ("FAIBLE", "MOYENNE")
        assert any("court" in limite.lower() for limite in analyse["limitations"])


class TestExtraireOrdreSimule:
    def test_achat_explicite(self):
        assert extraire_ordre_simule("achete 0.5 bitcoin simule") == {"sens": "ACHAT", "quantite": 0.5}

    def test_vente_explicite(self):
        assert extraire_ordre_simule("vends 2 bitcoin en simulation") == {"sens": "VENTE", "quantite": 2.0}

    def test_sans_le_mot_simule_reste_none(self):
        # Sans "simule", ARENA ne doit JAMAIS lire un achat comme un ordre —
        # meme reel-sonnant, il reste une question d'analyse.
        assert extraire_ordre_simule("achete 0.5 bitcoin") is None

    def test_sans_quantite_reste_none(self):
        assert extraire_ordre_simule("simule un achat de bitcoin") is None

    def test_sans_sens_reste_none(self):
        assert extraire_ordre_simule("simule 0.5 bitcoin") is None


class TestOrdreSimuleViaLAgent:
    """Le module reveille (DEC-0078) : `core/finance/paper_trading.py` est
    desormais atteint depuis un vrai chemin de code, pas un import a vide."""

    @pytest.mark.asyncio
    async def test_achat_simule_debite_le_portefeuille_au_prix_reel(self, portefeuille):
        connecteur = FauxConnecteurMarketData(points=[(0, 100.0)])
        agent = FinanceAgent(provider=FauxProvider(), registre=_registre(connecteur), portefeuille=portefeuille)

        resultat = await agent.run("achete 2 bitcoin simule")

        assert resultat["status"] == "success"
        assert resultat["ordre_simule"]["transaction"]["prix"] == pytest.approx(100.0)
        assert portefeuille.positions()["bitcoin"].quantite == pytest.approx(2.0)
        # Le prix vient du connecteur (le dernier point de la serie), JAMAIS invente.
        assert connecteur.appels[0][0] == "prix"

    @pytest.mark.asyncio
    async def test_vente_a_decouvert_simulee_est_refusee(self, portefeuille):
        connecteur = FauxConnecteurMarketData(points=[(0, 100.0)])
        agent = FinanceAgent(provider=FauxProvider(), registre=_registre(connecteur), portefeuille=portefeuille)

        resultat = await agent.run("vends 1 bitcoin simule")

        assert resultat["status"] == "error"
        assert portefeuille.positions() == {}

    @pytest.mark.asyncio
    async def test_prix_indisponible_n_execute_aucun_ordre(self, portefeuille):
        connecteur = FauxConnecteurMarketData(echoue_prix=True)
        agent = FinanceAgent(provider=FauxProvider(), registre=_registre(connecteur), portefeuille=portefeuille)

        resultat = await agent.run("achete 1 bitcoin simule")

        assert resultat["status"] == "error"
        assert portefeuille.positions() == {}

    @pytest.mark.asyncio
    async def test_phrase_ordinaire_n_est_jamais_lue_comme_un_ordre(self, portefeuille):
        """« achete » sans « simule » doit rester une ANALYSE, jamais un ordre —
        meme accidentellement, ARENA ne doit jamais modifier une comptabilite,
        simulee ou non, sur une phrase ambigue."""
        points = [(i * 1000, 100.0 + i) for i in range(40)]
        connecteur = FauxConnecteurMarketData(points=points)
        agent = FinanceAgent(provider=FauxProvider(), registre=_registre(connecteur),
                              recherche=FauxRecherche(resultats=[]), portefeuille=portefeuille)

        resultat = await agent.run("dois-je acheter du bitcoin en ce moment")

        assert "ordre_simule" not in resultat
        assert portefeuille.positions() == {}


class TestAucunOrdreReel:
    """Garantie structurelle (mission §10) : FinanceAgent ne peut appeler
    aucune capacite d'ecriture, puisqu'il n'en existe aucune sur le
    connecteur qu'il consulte — verifie en lisant le code de l'agent."""

    def test_aucune_mention_d_execution_ou_de_cle_privee(self):
        import re

        import agents.finance.finance_agent as module
        with open(module.__file__, encoding="utf-8") as f:
            contenu = f.read().lower()
        for mot_interdit in ("execute_trade", "private_key", "wallet_key"):
            assert mot_interdit not in contenu
        # Mot entier seulement : "designerait"/"consigner" contiennent "signer"
        # en sous-chaine sans avoir aucun rapport avec signer une transaction.
        assert re.search(r"\bsigner\b", contenu) is None
