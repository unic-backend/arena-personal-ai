"""Le banc d'essai dit-il la vérité quand il n'a rien mesuré ?

Ce fichier existe à cause du point 24 de la mission : *« Do not claim 5x faster
unless measured. »* Un banc d'essai qui remplirait ses colonnes en l'absence de
mesure serait pire qu'aucun banc d'essai.

`test_moins_de_deux_fournisseurs_interdit_toute_conclusion` est le test qui
porte cette règle.
"""
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "scripts"))

from comparer_fournisseurs import ABSENT, ECHEC, rendre  # noqa: E402


def absent(modele="m"):
    return {"etat": ABSENT, "detail": "pas de cle, ou service injoignable", "modele": modele}


def mesure(premier=0.3, total=1.2):
    return {"etat": "MESURE", "modele": "modele-x", "scenes": {
        "courte": {"etat": "MESURE", "premier_mot_s": premier, "total_s": total,
                   "passages": 1}}}


# --- Le test qui porte la règle ----------------------------------------------------

def test_moins_de_deux_fournisseurs_interdit_toute_conclusion():
    """Comparer, c'est comparer deux choses. Une seule ne se compare à rien."""
    tableau = rendre({"ollama": mesure(), "groq": absent(), "deepinfra": absent()})

    assert "AUCUNE comparaison n'est possible" in tableau
    assert "Ne rien conclure" in tableau


def test_deux_fournisseurs_mesures_permettent_la_comparaison():
    tableau = rendre({"ollama": mesure(0.9, 4.0), "groq": mesure(0.2, 1.1)})

    assert "AUCUNE comparaison" not in tableau
    assert "2 fournisseur(s) mesure(s)" in tableau


# --- Ce qui n'a pas tourné se dit -----------------------------------------------------

def test_un_fournisseur_absent_reste_au_tableau():
    """Une colonne vide est une information ; une colonne inventée est un mensonge."""
    tableau = rendre({"groq": absent("llama-3.3")})

    assert ABSENT in tableau
    assert "llama-3.3" in tableau


def test_un_premier_mot_jamais_arrive_s_ecrit_unknown():
    """`None` veut dire « aucun mot n'est arrivé », pas « instantané »."""
    tableau = rendre({"ollama": {"etat": "MESURE", "modele": "m", "scenes": {
        "courte": {"etat": "MESURE", "premier_mot_s": None, "total_s": 2.0,
                   "passages": 1}}}})

    assert "UNKNOWN" in tableau
    assert "0.000s" not in tableau


def test_une_scene_en_echec_est_montree_telle_quelle():
    tableau = rendre({"groq": {"etat": "MESURE", "modele": "m", "scenes": {
        "courte": {"etat": ECHEC, "detail": "TimeoutException"}}}})

    assert ECHEC in tableau
    assert "TimeoutException" in tableau


def test_aucune_phrase_du_proprietaire_n_est_utilisee():
    """Un banc d'essai n'est pas un endroit où passe sa vie privée."""
    from comparer_fournisseurs import SCENES

    prompts = " ".join(prompt for _, prompt in SCENES).lower()

    assert "client" not in prompts
    assert "devis" not in prompts
    assert "fast group" not in prompts


class TestLaMesureQueLaMissionDemande:
    """Le banc rend-il exactement les champs réclamés, sans en inventer aucun ?

    La mission nomme : `provider`, `model`, `prompt`, `time_to_first_token`,
    `total_latency`, `tokens_per_second`, `success/failure`, `error`. Ces tests
    tiennent les deux bords : les champs sont là, **et** ceux qui n'ont pas été
    mesurés valent `None` plutôt qu'un zéro de remplissage.
    """

    def test_chaque_ligne_porte_les_champs_reclames(self):
        from comparer_fournisseurs import lignes_plates

        lignes = lignes_plates({"groq": mesure(0.2, 1.1)})

        assert lignes, "une mesure doit produire au moins une ligne"
        for ligne in lignes:
            for champ in ("fournisseur", "modele", "scene", "prompt", "succes",
                          "premier_mot_s", "total_s", "jetons_par_seconde",
                          "erreur"):
                assert champ in ligne, champ

    def test_un_fournisseur_absent_produit_une_ligne_qui_le_dit(self):
        """L'écarter ferait disparaître l'information la plus utile."""
        from comparer_fournisseurs import lignes_plates

        lignes = lignes_plates({"groq": absent("pas de cle")})

        assert len(lignes) == 1
        assert lignes[0]["succes"] is False
        assert lignes[0]["etat"] == "ABSENT"
        assert lignes[0]["premier_mot_s"] is None
        assert lignes[0]["total_s"] is None
        assert lignes[0]["jetons_par_seconde"] is None

    def test_le_prompt_voyage_avec_la_mesure(self):
        """Sans lui, deux mesures ne sont pas comparables et le banc n'est pas
        rejouable à l'identique."""
        from comparer_fournisseurs import PROMPTS, lignes_plates

        ligne = next(ligne for ligne in lignes_plates({"groq": mesure(0.2, 1.1)})
                     if ligne["scene"] is not None)

        assert ligne["prompt"] == PROMPTS[ligne["scene"]]

    async def test_un_debit_sans_jetons_annonces_reste_inconnu(self):
        """Diviser des morceaux de flux par une durée donnerait un chiffre qui
        ressemble à un débit sans en être un."""
        from comparer_fournisseurs import mesurer_un

        class SansJetons:
            derniere_mesure = None

            async def generate_stream(self, prompt):
                for mot in ("Bon", "jour"):
                    yield mot

        resultat = await mesurer_un(SansJetons(), "bonjour")

        assert resultat["etat"] == "MESURE"
        assert resultat["jetons_par_seconde"] is None
        assert resultat["morceaux"] == 2

    async def test_un_debit_est_rendu_quand_le_service_a_annonce_ses_jetons(self):
        from comparer_fournisseurs import mesurer_un

        from core.models.openai_compatible import Mesure

        class AvecJetons:
            def __init__(self):
                self.derniere_mesure = Mesure(fournisseur="x", modele="m")

            async def generate_stream(self, prompt):
                self.derniere_mesure.jetons_sortie = 40
                yield "Bonjour"
                self.derniere_mesure.fin = self.derniere_mesure.debut + 2.0

        resultat = await mesurer_un(AvecJetons(), "bonjour")

        assert resultat["jetons_par_seconde"] == 20.0

    async def test_un_echec_porte_son_erreur_nettoyee_et_aucune_mesure(self):
        """Un échec est un résultat : il a sa ligne, son erreur, et des
        mesures à `None` — jamais un `0.0` qui se lirait « instantané »."""
        from comparer_fournisseurs import ECHEC, mesurer_un

        from core.models.openai_compatible import Mesure

        class Casse:
            def __init__(self):
                self.derniere_mesure = Mesure(
                    fournisseur="x", modele="m",
                    erreur="ConnectError: [cle retiree]")

            async def generate_stream(self, prompt):
                raise ConnectionError("service injoignable")
                yield  # pragma: no cover — jamais atteint

        resultat = await mesurer_un(Casse(), "bonjour")

        assert resultat["etat"] == ECHEC
        assert "[cle retiree]" in resultat["erreur"]
        assert resultat["premier_mot_s"] is None
        assert resultat["total_s"] is None
