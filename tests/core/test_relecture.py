"""Usman se relit — et il reste rapide.

Sa demande du 02/09/2026 portait deux exigences dans la même phrase : « qu'il
se relise avant de répondre » **et** « il doit être rapide dans les
réflexions ». Les deux ensemble excluent une seconde passe par le modèle, qui
doublerait l'attente. D'où : contrôles déterministes uniquement.

`test_la_relecture_est_instantanee` est le test qui tient la seconde exigence
— celle qu'on oublie en ajoutant des contrôles.
`test_un_prix_altere_dans_le_chat_general_est_signale` porte la correction :
`controle_prix` existait depuis le 27/08/2026 et ne tournait **que** dans
l'agent devis ; la conversation générale citait ses tarifs sans aucune
vérification.
"""
import time

import pytest

from agents.plaquiste.plaquiste_agent import FICHIER_METIER, charger_metier
from core.relecture import Relecture, avec_la_relecture, relire

METIER = charger_metier(FICHIER_METIER)

JUSTE = "La plaque standard BA13 est a 4 500 FCFA l'unite."
ALTERE = "La plaque standard BA13 est a 5 200 FCFA l'unite."


# --- Les deux exigences, ensemble ---------------------------------------------

def test_un_prix_altere_dans_le_chat_general_est_signale():
    """La correction : le chat général n'était vérifié par rien."""
    relecture = relire(ALTERE, METIER)

    assert relecture.a_trouve_quelque_chose
    assert relecture.anomalies[0].prix_attendu == 4500
    assert "4500 attendu" in relecture.note


def test_la_relecture_est_instantanee():
    """L'exigence qu'on oublie : « il doit être rapide ».

    Un seuil large exprès — ce test tient l'ordre de grandeur (aucun appel de
    modèle, aucune sortie de la machine), pas une performance de machine.
    """
    depart = time.perf_counter()
    for _ in range(20):
        relire(ALTERE, METIER)
    millisecondes = (time.perf_counter() - depart) * 1000

    assert millisecondes < 500, (
        f"20 relectures ont pris {millisecondes:.0f} ms : trop lent pour être invisible")


def test_la_relecture_n_appelle_aucun_modele():
    """La garantie derrière la vitesse, tenue sur le module lui-même."""
    import inspect

    import core.relecture as module

    source = inspect.getsource(module)
    for interdit in ("generate", "provider", "await ", "async def"):
        assert interdit not in source, (
            f"« {interdit} » dans la relecture : elle n'est plus instantanée")


# --- Ce qu'elle ne fait pas ------------------------------------------------------

def test_un_prix_juste_ne_declenche_rien():
    assert relire(JUSTE, METIER).a_trouve_quelque_chose is False
    assert avec_la_relecture(JUSTE, METIER) == JUSTE


def test_elle_ne_corrige_jamais_la_reponse():
    """« Je ne corrige pas moi-même : c'est ton document et ton tarif. »"""
    rendu = avec_la_relecture(ALTERE, METIER)

    assert rendu.startswith(ALTERE), "la réponse a été modifiée"
    assert "5 200" in rendu, "le chiffre qu'il a vu a disparu"
    assert "4500 attendu" in rendu


def test_la_reponse_part_entiere_meme_quand_la_relecture_trouve():
    """Une réponse retenue parce qu'un contrôle a douté est une réponse perdue."""
    rendu = avec_la_relecture(ALTERE, METIER)

    assert len(rendu) > len(ALTERE)
    assert ALTERE in rendu


# --- Ce qui ne doit jamais emporter la réponse -------------------------------------

@pytest.mark.parametrize("reponse,metier", [
    ("", METIER),
    ("une reponse", {}),
    ("", {}),
])
def test_sans_matiere_la_relecture_se_tait(reponse, metier):
    assert relire(reponse, metier) == Relecture()


def test_une_relecture_qui_casse_rend_la_reponse_intacte(monkeypatch):
    """Le propriétaire préfère une réponse non relue à pas de réponse."""
    import core.relecture as module

    monkeypatch.setattr(module, "verifier_prix",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("grille cassee")))

    assert relire(ALTERE, METIER) == Relecture()
    assert avec_la_relecture(ALTERE, METIER) == ALTERE


# --- Le branchement ----------------------------------------------------------------

def test_le_chat_general_relit_vraiment():
    """Sans cet appel, tout le reste est décoratif."""
    import inspect

    from apps.backend.routers import pwa_gateway

    assert "relire(" in inspect.getsource(pwa_gateway), (
        "la passerelle ne relit pas : le chat général redevient non vérifié")


def test_la_grille_de_relecture_est_relue_quand_le_fichier_change():
    """Un prix changé dans le YAML doit être vu au tour suivant, pas au
    prochain redémarrage — le défaut réparé le 01/09/2026."""
    from apps.backend.routers.pwa_gateway import metier_pour_relecture

    grille = metier_pour_relecture()

    assert grille.get("prix_materiaux"), "la relecture travaille sans grille"
    assert grille["prix_materiaux"]["Plaque standard BA13"] == 4500
