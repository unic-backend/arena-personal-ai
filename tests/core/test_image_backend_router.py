"""Le choix DIRECT vs COMFYUI pour l'image-generation canonique — mission
ARENA x COMFYUI (DEC-0087, §4). Purement deterministe, aucun reseau."""
from core.production.image_backend_router import backend_choisi, backend_de_secours


def test_sans_demande_explicite_le_defaut_est_hidream():
    assert backend_choisi(None) == "hidream"


def test_un_backend_explicite_est_toujours_respecte():
    assert backend_choisi("comfyui") == "comfyui"
    assert backend_choisi("un-nom-invente") == "un-nom-invente"


def test_le_secours_de_hidream_est_comfyui():
    assert backend_de_secours("hidream") == "comfyui"


def test_le_secours_de_comfyui_est_hidream():
    assert backend_de_secours("comfyui") == "hidream"


def test_un_backend_inconnu_n_a_pas_de_secours_devine():
    assert backend_de_secours("un-nom-invente") is None
