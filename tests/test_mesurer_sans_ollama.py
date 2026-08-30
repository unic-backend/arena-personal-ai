"""La mesure « sans Ollama » mesure-t-elle, ou suppose-t-elle ?

DEC-0021 envoie ARENA sur un serveur sans carte graphique. `scripts/
mesurer_sans_ollama.py` existe pour savoir ce que le routeur y devient — et un
script de mesure qui inventerait une réponse serait pire qu'aucun script.

`test_l_absence_locale_est_reelle_jamais_simulee` est le test qui porte la
règle : le fournisseur local doit pointer vers un port mort, pas vers un objet
qui lève ce qu'on lui a dit de lever.
"""
import asyncio
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "scripts"))
sys.path.insert(0, str(RACINE))

from mesurer_sans_ollama import OLLAMA_ABSENT, SCENES, mesurer  # noqa: E402


class RouteurDouble:
    """Un routeur de test : il décide, il ne joint rien."""

    def __init__(self, candidats, raison, distants=None):
        self._candidats_rendus = candidats
        self._raison = raison
        self.distants = distants if distants is not None else {"groq": object()}

    def _candidats(self, classement):
        return list(self._candidats_rendus), self._raison

    async def generate(self, prompt):
        raise RuntimeError("Aucun fournisseur n'a pu repondre.")


# --- Le test qui porte la règle ----------------------------------------------------

def test_l_absence_locale_est_reelle_jamais_simulee():
    """Le port 1 n'écoute pas. C'est ce que vit un serveur sans Ollama."""
    assert OLLAMA_ABSENT.startswith("http://127.0.0.1:")
    assert OLLAMA_ABSENT.rsplit(":", 1)[1] not in ("11434", "0"), (
        "l'adresse mesurée est celle d'un Ollama vivant : l'absence n'est plus mesurée")


# --- Ce que la mesure rapporte -----------------------------------------------------

def test_un_echec_est_rapporte_avec_son_type_jamais_en_reponse():
    routeur = RouteurDouble(["local"], "SENSIBLE reste sur sa machine en HYBRIDE")

    mesure = asyncio.run(mesurer(routeur, "Prepare le devis du client Dupont."))

    assert mesure["issue"] == "RuntimeError"
    assert mesure["detail"], "un échec sans détail n'apprend rien"


def test_la_decision_du_routeur_est_rapportee_avec_sa_raison():
    routeur = RouteurDouble(["groq", "local"], "PRIVE autorise en HYBRIDE, groq d'abord")

    mesure = asyncio.run(mesurer(routeur, "Qu'est-ce qu'une cloison ?"))

    assert mesure["candidats"] == ["groq", "local"]
    assert mesure["raison"] == "PRIVE autorise en HYBRIDE, groq d'abord"
    assert mesure["niveau"] in ("PUBLIC", "PRIVE", "SENSIBLE", "TRES_SENSIBLE")


def test_aucune_phrase_du_proprietaire_ne_sert_de_banc_d_essai():
    """Même règle que `comparer_fournisseurs.py` : les scènes sont écrites ici."""
    interdits = ("Fast Group", "UniC", "Saer", "Ousmane", "Uthman")
    for _, prompt in SCENES:
        assert not any(mot in prompt for mot in interdits), (
            f"une donnée réelle est entrée dans le banc d'essai : {prompt!r}")


def test_les_trois_scenes_couvrent_les_niveaux_qui_changent_le_routage():
    """PUBLIC/PRIVE partent au cloud, SENSIBLE non : c'est là que tout se joue."""
    from core.models.confidentialite import classer

    niveaux = {classer(prompt).niveau.value for _, prompt in SCENES}

    assert "SENSIBLE" in niveaux, "sans scène sensible, la mesure rate le cas qui casse"
    assert len(niveaux) >= 2, "un seul niveau mesuré ne montre aucun aiguillage"
