"""Un prix altéré dans un devis part chez un client et engage l'entreprise.

L'instruction système dit au modèle de ne jamais changer un prix. C'est une
consigne, pas une garantie. Ce contrôle lit ce qui a été écrit et le compare à
la grille du propriétaire.

Il est volontairement étroit : il ne signale que ce qu'il peut prouver. Un
contrôle qui crie à tort est un contrôle qu'on éteint.
"""
import pytest

from agents.plaquiste.controle_prix import Anomalie, avertissement, verifier_prix
from agents.plaquiste.plaquiste_agent import charger_metier

METIER = charger_metier()


class TestCeQuiEstSignale:
    def test_un_prix_unitaire_altere_est_detecte(self):
        anomalies = verifier_prix("Plaque standard BA13 | 6 000 | 10 | 60 000 FCFA", METIER)

        assert len(anomalies) == 1
        assert anomalies[0].article == "Plaque standard BA13"
        assert anomalies[0].prix_attendu == 4500

    def test_plusieurs_lignes_fausses_sont_toutes_signalees(self):
        texte = (
            "Plaque standard BA13 | 6 000 | 10 | 60 000\n"
            "Sac enduit | 15 000 | 2 | 30 000\n"
        )
        assert len(verifier_prix(texte, METIER)) == 2

    def test_le_tarif_de_main_oeuvre_est_surveille_aussi(self):
        anomalies = verifier_prix("Main-d'oeuvre (m2) | 8 000 | 486 m2", METIER)
        assert anomalies and anomalies[0].prix_attendu == 5000


class TestCeQuiNEstPasSignale:
    """Les faux positifs. C'est ici que se joue l'utilité du contrôle."""

    def test_un_prix_juste_ne_declenche_rien(self):
        assert verifier_prix("Plaque standard BA13 | 4 500 | 815 | 3 667 500 FCFA", METIER) == []

    def test_un_total_multiple_du_prix_unitaire_ne_declenche_rien(self):
        """« 45 000 » pour 10 plaques à 4 500 est juste, pas une altération."""
        assert verifier_prix("Plaque standard BA13 : total 45 000 FCFA", METIER) == []

    def test_une_phrase_sans_chiffre_ne_declenche_rien(self):
        assert verifier_prix("Nous posons des plaques standard BA13 de qualite.", METIER) == []

    def test_une_quantite_seule_ne_declenche_rien(self):
        """815 plaques : c'est une quantité, pas un prix."""
        assert verifier_prix("Plaque standard BA13 : 815 unites, 4 500 l'unite", METIER) == []

    def test_un_article_absent_de_la_grille_n_est_pas_juge(self):
        """On ne connaît pas son prix : on ne peut rien affirmer dessus."""
        assert verifier_prix("Spot LED encastre | 12 000 | 8 | 96 000", METIER) == []

    def test_une_reponse_vide_ne_declenche_rien(self):
        assert verifier_prix("", METIER) == []

    def test_sans_grille_aucun_jugement_n_est_porte(self):
        assert verifier_prix("Plaque standard BA13 | 6 000", {}) == []


class TestAvertissement:
    def test_sans_anomalie_rien_n_est_ajoute(self):
        assert avertissement([]) == ""

    def test_le_message_nomme_l_article_et_le_prix_attendu(self):
        message = avertissement([Anomalie("Plaque standard BA13", 4500, "ligne fautive")])

        assert "Plaque standard BA13" in message
        assert "4500" in message
        assert "vérifier avant d'envoyer" in message

    def test_le_message_dit_qu_il_ne_corrige_pas(self):
        """Corriger seul un montant dans un document commercial serait pire."""
        message = avertissement([Anomalie("X", 1000, "l")])
        assert "Je ne corrige pas moi-même" in message


class TestChaineComplete:
    async def test_un_modele_qui_altere_un_prix_est_signale_a_l_utilisateur(self):
        from agents.plaquiste.plaquiste_agent import PlaquisteAgent

        class ModeleQuiAltere:
            async def generate(self, prompt, system_prompt=None, **kw):
                return "Plaque standard BA13 | 6 000 | 10 | 60 000 FCFA"

        res = await PlaquisteAgent(provider=ModeleQuiAltere(), metier=METIER).run("devis")

        assert res["prix_alteres"], "le prix altere n'a pas ete signale"
        assert "vérifier avant d'envoyer" in res["response"]

    async def test_un_modele_correct_ne_declenche_aucun_avertissement(self):
        from agents.plaquiste.plaquiste_agent import PlaquisteAgent

        class ModeleCorrect:
            async def generate(self, prompt, system_prompt=None, **kw):
                return "Plaque standard BA13 | 4 500 | 815 | 3 667 500 FCFA"

        res = await PlaquisteAgent(provider=ModeleCorrect(), metier=METIER).run("devis")

        assert res["prix_alteres"] == []
        assert "vérifier avant d'envoyer" not in res["response"]

    @pytest.mark.parametrize("article,prix", [
        ("Plaque hydrofuge", 7000),
        ("Rails 48 mm", 1500),
        ("Sac enduit", 12000),
        ("Peinture en eau Gylatex (coloris)", 11500),
    ])
    def test_chaque_article_de_la_grille_est_surveille(self, article, prix):
        faux = f"{article} | {prix + 1000} | 1 | {prix + 1000}"
        assert verifier_prix(faux, METIER), f"{article} n'est pas surveille"


def test_la_limite_du_multiple_est_connue():
    """Un prix multiple exact du vrai passe inaperçu. Mesuré, assumé, visible.

    « 9 000 » pour une plaque à 4 500 n'est pas détecté : la règle du multiple
    existe pour ne pas confondre un total avec un prix unitaire. La lever ferait
    crier le contrôle sur tous les totaux justes.

    Ce test ne valide pas ce comportement : il l'empêche de disparaître en
    silence. Le jour où le contrôle comprendra les colonnes, il échouera — et
    c'est ainsi qu'on saura que la limite est levée.
    """
    assert verifier_prix("Plaque standard BA13 | 9 000 | 1 | 9 000", METIER) == []
