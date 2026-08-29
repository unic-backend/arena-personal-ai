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
