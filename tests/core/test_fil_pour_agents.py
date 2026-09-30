"""Le bloc de contexte : ce qu'il contient, ce qu'il coupe, ce qu'il promet.

DEC-0191. Ce module ne decide rien : il pose le fil devant la demande. Les
tests d'aiguillage (`tests/test_le_fil_atteint_les_agents.py`) mesurent le
texte que l'agent recoit vraiment ; ceux-ci tiennent le contrat du bloc
lui-meme, borne par borne.
"""
from core.context.fil_pour_agents import (
    BALISE_DEBUT_CONTEXTE,
    BALISE_DEMANDE,
    BALISE_FIN_CONTEXTE,
    CONSIGNE_DE_LECTURE,
    demande_avec_le_fil,
    tours_sous_les_bornes,
)
from core.memory.conversation import BUDGET_TOURS_ANTERIEURS

PROPRIETAIRE = "Ousmane"


def _tours(nombre, taille=20, depart=0):
    return [
        {"role": "user" if rang % 2 == 0 else "assistant",
         "content": f"t{depart + rang:02d}" + "x" * taille}
        for rang in range(nombre)
    ]


def test_la_demande_est_recopiee_mot_pour_mot_et_lue_en_dernier():
    """Aucune reecriture : ni resume, ni completion, ni ponctuation ajoutee."""
    demande = "donne-moi un nom"
    texte = demande_avec_le_fil(demande, _tours(4), PROPRIETAIRE, maximum=6)

    assert texte.endswith("\n" + demande)
    assert texte.count(demande) == 1


def test_le_bloc_dit_que_le_fil_est_du_contexte_et_la_demande_la_seule():
    texte = demande_avec_le_fil("combien", _tours(2), PROPRIETAIRE, maximum=6)

    assert BALISE_DEBUT_CONTEXTE in texte
    assert BALISE_FIN_CONTEXTE in texte
    assert CONSIGNE_DE_LECTURE in texte
    assert BALISE_DEMANDE in texte
    # L'ordre compte : le contexte d'abord, la demande en dernier.
    assert texte.index(BALISE_FIN_CONTEXTE) < texte.index(BALISE_DEMANDE)
    assert "CONTEXTE" in BALISE_DEBUT_CONTEXTE
    assert "seule" in BALISE_DEMANDE


def test_sans_aucun_tour_la_demande_part_seule_sans_bloc_vide():
    """Un bloc de contexte vide ferait croire que la conversation commence."""
    assert demande_avec_le_fil("un titre", [], PROPRIETAIRE, maximum=6) == "un titre"
    assert demande_avec_le_fil("un titre", None, PROPRIETAIRE, maximum=6) == "un titre"


def test_un_tour_vide_n_occupe_pas_une_place():
    """« Usman: » sans rien derriere n'apprend rien et prendrait un tour."""
    tours = [{"role": "user", "content": "   "},
             {"role": "assistant", "content": ""},
             {"role": "user", "content": "je parle de Bitcoin"}]
    retenus = tours_sous_les_bornes(tours, PROPRIETAIRE, maximum=6)

    assert [t["content"] for t in retenus] == ["je parle de Bitcoin"]


def test_la_borne_de_tours_garde_les_plus_recents():
    retenus = tours_sous_les_bornes(_tours(10), PROPRIETAIRE, maximum=6)

    assert len(retenus) == 6
    assert retenus[0]["content"].startswith("t04")
    assert retenus[-1]["content"].startswith("t09")


def test_le_budget_coupe_les_plus_vieux_tours_d_abord():
    """Deux bornes, pas une : sous la borne de tours, le budget tranche."""
    tours = _tours(6, taille=200)
    retenus = tours_sous_les_bornes(tours, PROPRIETAIRE, maximum=6,
                                    budget_caracteres=500)

    assert 0 < len(retenus) < 6
    assert retenus[-1]["content"].startswith("t05"), "le plus recent reste"
    assert all(not t["content"].startswith("t00") for t in retenus)
    rendu = demande_avec_le_fil("combien", tours, PROPRIETAIRE, maximum=6,
                                budget_caracteres=500)
    assert "t00" not in rendu and "t05" in rendu


def test_le_budget_ne_laisse_jamais_de_trou_dans_le_fil():
    """On s'arrete au premier tour trop gros : un fil troue se lit comme un
    fil continu, et le modele en deduit des enchainements qui n'ont pas eu
    lieu (meme regle que `core/memory/conversation.tours_anterieurs`)."""
    tours = [
        {"role": "user", "content": "A" * 20},
        {"role": "assistant", "content": "B" * 400},
        {"role": "user", "content": "C" * 20},
    ]
    retenus = tours_sous_les_bornes(tours, PROPRIETAIRE, maximum=6,
                                    budget_caracteres=120)

    assert [t["content"][0] for t in retenus] == ["C"], (
        "le tour A, plus court, ne doit pas sauter par-dessus B")


def test_un_seul_tour_plus_gros_que_le_budget_laisse_passer_la_demande():
    tours = [{"role": "user", "content": "x" * (BUDGET_TOURS_ANTERIEURS + 1)}]

    assert tours_sous_les_bornes(tours, PROPRIETAIRE, maximum=6) == []
    assert demande_avec_le_fil("un titre", tours, PROPRIETAIRE, maximum=6) == "un titre"


def test_le_cout_compte_le_nom_de_celui_qui_parle():
    """Le budget porte sur le texte REELLEMENT envoye, prefixe compris."""
    tours = [{"role": "user", "content": "x" * 30}]
    court = tours_sous_les_bornes(tours, "Ou", maximum=6, budget_caracteres=35)
    long = tours_sous_les_bornes(tours, "Ousmane-le-proprietaire", maximum=6,
                                 budget_caracteres=35)

    assert len(court) == 1 and long == []


def test_un_maximum_nul_ne_joint_rien():
    assert tours_sous_les_bornes(_tours(4), PROPRIETAIRE, maximum=0) == []


def test_le_fil_est_rendu_par_la_fonction_commune_de_la_memoire():
    """Un second rendu donnerait deux memoires a ARENA (DEC-0191)."""
    from core.memory.conversation import rendre_le_fil

    tours = _tours(2)
    texte = demande_avec_le_fil("combien", tours, PROPRIETAIRE, maximum=6)

    assert rendre_le_fil(tours, PROPRIETAIRE) in texte
