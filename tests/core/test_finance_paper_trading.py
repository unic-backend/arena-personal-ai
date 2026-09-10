"""Le portefeuille simule : comptabilite deterministe, en SQLite reel (base
temporaire, jamais `data/database/memory.db`).

Le test de redemarrage (`TestPersistance`) est celui que la mission demande
explicitement (§25, "restart test passes") : un nouveau `PortefeuilleSimule`
sur le MEME fichier doit retrouver exactement l'etat laisse par le precedent.
"""
import pytest

from core.finance.paper_trading import SOLDE_INITIAL_DEFAUT, PortefeuilleSimule


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test_finance.db")


class TestCompteInitial:
    def test_solde_initial_par_defaut(self, db_path):
        p = PortefeuilleSimule(db_path=db_path)
        assert p.solde_especes() == pytest.approx(SOLDE_INITIAL_DEFAUT)
        assert p.positions() == {}

    def test_solde_initial_personnalise(self, db_path):
        p = PortefeuilleSimule(db_path=db_path, solde_initial=5000.0)
        assert p.solde_especes() == pytest.approx(5000.0)

    def test_reouverture_ne_reinitialise_pas_le_solde(self, db_path):
        PortefeuilleSimule(db_path=db_path, solde_initial=5000.0)
        # Un second constructeur, solde_initial DIFFERENT : ignore, parce que
        # le compte existe deja — sinon rouvrir effacerait l'historique.
        p2 = PortefeuilleSimule(db_path=db_path, solde_initial=999.0)
        assert p2.solde_especes() == pytest.approx(5000.0)


class TestAchat:
    def test_achat_debite_le_solde_et_ouvre_la_position(self, db_path):
        p = PortefeuilleSimule(db_path=db_path, solde_initial=10000.0)
        resultat = p.acheter("bitcoin", quantite=2.0, prix=100.0)
        assert resultat.reussi
        assert p.solde_especes() == pytest.approx(9800.0)
        position = p.positions()["bitcoin"]
        assert position.quantite == pytest.approx(2.0)
        assert position.prix_moyen_achat == pytest.approx(100.0)

    def test_achat_au_dela_du_solde_est_refuse(self, db_path):
        p = PortefeuilleSimule(db_path=db_path, solde_initial=100.0)
        resultat = p.acheter("bitcoin", quantite=10.0, prix=100.0)
        assert not resultat.reussi
        assert p.solde_especes() == pytest.approx(100.0)  # rien n'a bouge
        assert p.positions() == {}

    def test_achat_supplementaire_pondere_le_prix_moyen(self, db_path):
        p = PortefeuilleSimule(db_path=db_path, solde_initial=100000.0)
        p.acheter("bitcoin", quantite=1.0, prix=100.0)
        p.acheter("bitcoin", quantite=1.0, prix=200.0)
        position = p.positions()["bitcoin"]
        assert position.quantite == pytest.approx(2.0)
        assert position.prix_moyen_achat == pytest.approx(150.0)  # (100+200)/2

    def test_quantite_ou_prix_negatif_est_refuse(self, db_path):
        p = PortefeuilleSimule(db_path=db_path)
        assert not p.acheter("bitcoin", quantite=-1.0, prix=100.0).reussi
        assert not p.acheter("bitcoin", quantite=1.0, prix=0.0).reussi


class TestVente:
    def test_vente_credite_le_solde_et_reduit_la_position(self, db_path):
        p = PortefeuilleSimule(db_path=db_path, solde_initial=10000.0)
        p.acheter("bitcoin", quantite=2.0, prix=100.0)
        resultat = p.vendre("bitcoin", quantite=1.0, prix=150.0)
        assert resultat.reussi
        assert resultat.transaction.pnl_realise == pytest.approx(50.0)  # (150-100)*1
        assert p.solde_especes() == pytest.approx(10000.0 - 200.0 + 150.0)
        assert p.positions()["bitcoin"].quantite == pytest.approx(1.0)

    def test_vente_a_decouvert_est_refusee(self, db_path):
        p = PortefeuilleSimule(db_path=db_path, solde_initial=10000.0)
        resultat = p.vendre("bitcoin", quantite=1.0, prix=100.0)
        assert not resultat.reussi
        assert "insuffisante" in resultat.message.lower()

    def test_vente_partielle_puis_vente_du_reste(self, db_path):
        p = PortefeuilleSimule(db_path=db_path, solde_initial=10000.0)
        p.acheter("bitcoin", quantite=2.0, prix=100.0)
        p.vendre("bitcoin", quantite=1.0, prix=100.0)
        # La position tombe a zero et disparait des positions actives.
        p.vendre("bitcoin", quantite=1.0, prix=100.0)
        assert "bitcoin" not in p.positions()


class TestValeurEtResume:
    def test_valeur_totale_especes_plus_positions_au_marche(self, db_path):
        p = PortefeuilleSimule(db_path=db_path, solde_initial=10000.0)
        p.acheter("bitcoin", quantite=2.0, prix=100.0)  # solde -> 9800
        valeur = p.valeur_totale({"bitcoin": 150.0})
        assert valeur == pytest.approx(9800.0 + 2.0 * 150.0)

    def test_position_sans_prix_n_est_pas_comptee_a_zero(self, db_path):
        p = PortefeuilleSimule(db_path=db_path, solde_initial=10000.0)
        p.acheter("bitcoin", quantite=2.0, prix=100.0)
        resume = p.resume(prix_actuels={})
        assert "bitcoin" in resume["positions_sans_prix"]
        # La valeur totale reste les especes seules : la position ignoree,
        # jamais comptee comme si elle valait 0.
        assert resume["valeur_totale"] == pytest.approx(9800.0)

    def test_pnl_non_realise(self, db_path):
        p = PortefeuilleSimule(db_path=db_path, solde_initial=10000.0)
        p.acheter("bitcoin", quantite=2.0, prix=100.0)
        resume = p.resume(prix_actuels={"bitcoin": 120.0})
        assert resume["pnl_non_realise"]["bitcoin"] == pytest.approx(40.0)  # (120-100)*2


class TestHistorique:
    def test_transactions_dans_l_ordre_du_plus_recent(self, db_path):
        p = PortefeuilleSimule(db_path=db_path, solde_initial=10000.0)
        p.acheter("bitcoin", quantite=1.0, prix=100.0)
        p.acheter("ethereum", quantite=1.0, prix=50.0)
        historique = p.historique()
        assert [t.actif for t in historique] == ["ethereum", "bitcoin"]


class TestPersistance:
    """« restart test passes » (mission §25) : un nouveau processus qui
    rouvre le MEME fichier retrouve l'etat exact."""

    def test_redemarrage_retrouve_le_solde_et_les_positions(self, db_path):
        p1 = PortefeuilleSimule(nom="test", db_path=db_path, solde_initial=10000.0)
        p1.acheter("bitcoin", quantite=2.0, prix=100.0)
        p1.vendre("bitcoin", quantite=0.5, prix=120.0)

        # Nouvelle instance, meme fichier, meme nom — simule un redemarrage.
        p2 = PortefeuilleSimule(nom="test", db_path=db_path)
        assert p2.solde_especes() == pytest.approx(p1.solde_especes())
        assert p2.positions()["bitcoin"].quantite == pytest.approx(1.5)
        assert len(p2.historique()) == 2

    def test_deux_portefeuilles_distincts_ne_se_melangent_pas(self, db_path):
        a = PortefeuilleSimule(nom="a", db_path=db_path, solde_initial=1000.0)
        b = PortefeuilleSimule(nom="b", db_path=db_path, solde_initial=2000.0)
        a.acheter("bitcoin", quantite=1.0, prix=100.0)
        assert a.solde_especes() == pytest.approx(900.0)
        assert b.solde_especes() == pytest.approx(2000.0)
        assert b.positions() == {}


class TestAucunEffetExterne:
    """La garantie de la mission (§10/§11) : ce module ne parle jamais a un
    service reel — verifie en lisant le fichier lui-meme, pas en le supposant."""

    def test_aucun_import_reseau(self):
        import core.finance.paper_trading as module
        with open(module.__file__, encoding="utf-8") as f:
            contenu = f.read()
        for mot_interdit in ("import httpx", "import requests", "solders", "wallet", "private_key"):
            assert mot_interdit not in contenu.lower()
