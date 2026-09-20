from dataclasses import dataclass

from apps.backend.image_routing import doit_forcer_vision, intention_avec_image


@dataclass
class Piece:
    lisible: bool
    est_image: bool


def lecteur(pieces):
    return lambda identifiant: pieces.get(identifiant)


def test_phrase_courte_avec_image_force_vision():
    lire = lecteur({"img": Piece(lisible=True, est_image=True)})
    assert intention_avec_image("regarde ça", ["img"], lire, "CHAT") == "VISION"


def test_question_elliptique_avec_image_force_vision():
    lire = lecteur({"img": Piece(lisible=True, est_image=True)})
    assert intention_avec_image("et celle-ci ?", ["img"], lire, "CHAT") == "VISION"


def test_document_seul_ne_force_pas_vision():
    lire = lecteur({"doc": Piece(lisible=True, est_image=False)})
    assert intention_avec_image("regarde ça", ["doc"], lire, "CHAT") == "CHAT"


def test_image_invalide_ne_force_pas_vision():
    lire = lecteur({"img": Piece(lisible=False, est_image=True)})
    assert doit_forcer_vision("regarde ça", ["img"], lire) is False


def test_piece_expiree_ou_absente_ne_force_pas_vision():
    assert doit_forcer_vision("regarde ça", ["absente"], lecteur({})) is False


def test_action_specialisee_n_est_pas_volee_par_vision():
    lire = lecteur({"img": Piece(lisible=True, est_image=True)})
    assert intention_avec_image("publie cette image", ["img"], lire, "SOCIAL") == "SOCIAL"


def test_sans_piece_garde_intention_initiale():
    assert intention_avec_image("bonjour", [], lecteur({}), "CHAT") == "CHAT"
