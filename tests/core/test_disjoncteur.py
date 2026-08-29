"""`Disjoncteur` : coupe court apres des echecs consecutifs REELS, jamais sur
la foi d'un refus de permission ou d'un service non configure.
"""
import pytest

from core.actions.resultat import a_confirmer, echec, non_configure, non_implemente, succes
from core.execution.disjoncteur import Disjoncteur


class TestFermeParDefaut:
    def test_rien_ne_bloque_avant_le_premier_echec(self):
        disjoncteur = Disjoncteur(seuil=3)

        assert disjoncteur.avant_execution("svc", "cap", {}) is None

    def test_l_etat_public_d_un_disjoncteur_neuf_est_ferme(self):
        disjoncteur = Disjoncteur()

        assert disjoncteur.etat_public("svc", "cap") == {"echecs_consecutifs": 0, "ouvert": False}


class TestOuverture:
    def test_s_ouvre_apres_le_seuil_d_echecs_consecutifs(self):
        disjoncteur = Disjoncteur(seuil=3)
        for _ in range(3):
            disjoncteur.apres_execution("svc", "cap", echec("cap", "svc", "en panne"))

        raison = disjoncteur.avant_execution("svc", "cap", {})

        assert raison is not None
        assert "svc.cap" in raison
        assert "3 echec" in raison

    def test_pas_encore_ouvert_avant_le_seuil(self):
        disjoncteur = Disjoncteur(seuil=3)
        disjoncteur.apres_execution("svc", "cap", echec("cap", "svc", "en panne"))
        disjoncteur.apres_execution("svc", "cap", echec("cap", "svc", "en panne"))

        assert disjoncteur.avant_execution("svc", "cap", {}) is None

    def test_un_succes_reel_remet_le_compteur_a_zero(self):
        disjoncteur = Disjoncteur(seuil=3)
        disjoncteur.apres_execution("svc", "cap", echec("cap", "svc", "en panne"))
        disjoncteur.apres_execution("svc", "cap", echec("cap", "svc", "en panne"))
        disjoncteur.apres_execution("svc", "cap", succes("cap", "svc", "ok", "preuve"))
        disjoncteur.apres_execution("svc", "cap", echec("cap", "svc", "en panne"))

        # Un seul echec depuis la remise a zero : encore ferme.
        assert disjoncteur.avant_execution("svc", "cap", {}) is None

    @pytest.mark.parametrize("resultat_sans_effet", [
        non_configure("cap", "svc", "une cle manquante"),
        a_confirmer("cap", "svc", "pret, en attente"),
        non_implemente("cap", "svc", "pas encore ecrit"),
    ])
    def test_ce_qui_n_a_rien_tente_contre_le_service_ne_compte_pas(self, resultat_sans_effet):
        """NOT_CONFIGURED / NEEDS_CONFIRMATION / NOT_IMPLEMENTED ne disent rien
        de la sante du service exterieur : ni echec, ni remise a zero."""
        disjoncteur = Disjoncteur(seuil=2)
        disjoncteur.apres_execution("svc", "cap", echec("cap", "svc", "en panne"))

        disjoncteur.apres_execution("svc", "cap", resultat_sans_effet)
        disjoncteur.apres_execution("svc", "cap", resultat_sans_effet)
        disjoncteur.apres_execution("svc", "cap", resultat_sans_effet)

        # Toujours un seul VRAI echec enregistre : le seuil de 2 n'est pas atteint.
        assert disjoncteur.avant_execution("svc", "cap", {}) is None
        assert disjoncteur.etat_public("svc", "cap")["echecs_consecutifs"] == 1


class TestRepos:
    def test_se_referme_de_lui_meme_apres_le_repos(self, monkeypatch):
        import core.execution.disjoncteur as module

        horloge = {"t": 1000.0}
        monkeypatch.setattr(module.time, "monotonic", lambda: horloge["t"])

        disjoncteur = Disjoncteur(seuil=2, repos_secondes=30.0)
        disjoncteur.apres_execution("svc", "cap", echec("cap", "svc", "en panne"))
        disjoncteur.apres_execution("svc", "cap", echec("cap", "svc", "en panne"))
        assert disjoncteur.avant_execution("svc", "cap", {}) is not None

        horloge["t"] += 30.1  # le repos est passe
        assert disjoncteur.avant_execution("svc", "cap", {}) is None

    def test_encore_dans_le_repos_reste_ouvert(self, monkeypatch):
        import core.execution.disjoncteur as module

        horloge = {"t": 1000.0}
        monkeypatch.setattr(module.time, "monotonic", lambda: horloge["t"])

        disjoncteur = Disjoncteur(seuil=2, repos_secondes=30.0)
        disjoncteur.apres_execution("svc", "cap", echec("cap", "svc", "en panne"))
        disjoncteur.apres_execution("svc", "cap", echec("cap", "svc", "en panne"))

        horloge["t"] += 10.0  # pas encore les 30s
        assert disjoncteur.avant_execution("svc", "cap", {}) is not None


class TestIndependanceParCapacite:
    def test_un_connecteur_en_echec_n_en_coupe_pas_un_autre(self):
        disjoncteur = Disjoncteur(seuil=2)
        for _ in range(2):
            disjoncteur.apres_execution("plaquiste", "mesurer", echec("mesurer", "plaquiste", "en panne"))

        assert disjoncteur.avant_execution("plaquiste", "mesurer", {}) is not None
        assert disjoncteur.avant_execution("opentakeoff", "mesurer", {}) is None

    def test_deux_capacites_du_meme_connecteur_sont_independantes(self):
        disjoncteur = Disjoncteur(seuil=2)
        for _ in range(2):
            disjoncteur.apres_execution("opentakeoff", "mesurer", echec("mesurer", "opentakeoff", "en panne"))

        assert disjoncteur.avant_execution("opentakeoff", "mesurer", {}) is not None
        assert disjoncteur.avant_execution("opentakeoff", "exporter", {}) is None


class TestConstruction:
    def test_un_seuil_sous_1_est_refuse(self):
        with pytest.raises(ValueError):
            Disjoncteur(seuil=0)
