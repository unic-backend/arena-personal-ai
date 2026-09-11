"""Le registre CONTROLE des workflows ComfyUI — mission ARENA x COMFYUI
(DEC-0087). Deterministe et testable SANS serveur (mission §9) : chaque
test tourne sans reseau, sans GPU.
"""
from core.production.comfyui_workflows import (
    REGISTRE,
    StatutWorkflow,
    construire_requete,
    lister,
    obtenir,
    valider_parametres,
)


def test_text_to_image_est_le_seul_workflow_stable():
    stables = [i for i, w in REGISTRE.items() if w.statut is StatutWorkflow.STABLE]
    assert stables == ["text_to_image"]


def test_les_workflows_candidats_n_ont_pas_de_gabarit():
    for identifiant, entree in REGISTRE.items():
        if entree.statut is StatutWorkflow.CANDIDATE:
            assert entree.gabarit is None, f"{identifiant} candidate ne doit pas avoir de gabarit"
            assert entree.implemente is False


def test_lister_rend_le_catalogue_entier_sans_le_gabarit():
    catalogue = lister()

    assert len(catalogue) == len(REGISTRE)
    for entree in catalogue:
        assert "gabarit" not in entree
        assert "identifiant" in entree and "profil_ressources" in entree


def test_obtenir_workflow_inconnu_rend_none():
    assert obtenir("n-existe-pas") is None


# --- Validation deterministe -----------------------------------------------------

def test_prompt_requis_absent_est_une_erreur():
    resultat = valider_parametres("text_to_image", {"ckpt_name": "x.safetensors"})

    assert resultat.ok is False
    assert any("prompt" in e for e in resultat.erreurs)


def test_ckpt_name_requis_absent_est_une_erreur():
    resultat = valider_parametres("text_to_image", {"prompt": "un chat"})

    assert resultat.ok is False
    assert any("ckpt_name" in e for e in resultat.erreurs)


def test_les_defauts_s_appliquent_quand_rien_n_est_fourni():
    resultat = valider_parametres(
        "text_to_image", {"prompt": "un chat", "ckpt_name": "x.safetensors"})

    assert resultat.ok is True
    assert resultat.parametres["width"] == 512
    assert resultat.parametres["height"] == 512
    assert resultat.parametres["steps"] == 20
    assert resultat.parametres["negative_prompt"] == ""


def test_un_seed_absent_est_tire_reellement_et_rendu():
    resultat = valider_parametres(
        "text_to_image", {"prompt": "un chat", "ckpt_name": "x.safetensors"})

    assert isinstance(resultat.parametres["seed"], int)


def test_un_seed_fourni_est_respecte_a_l_identique():
    resultat = valider_parametres(
        "text_to_image", {"prompt": "un chat", "ckpt_name": "x.safetensors", "seed": 42})

    assert resultat.parametres["seed"] == 42


def test_une_largeur_hors_bornes_est_refusee():
    resultat = valider_parametres(
        "text_to_image",
        {"prompt": "un chat", "ckpt_name": "x.safetensors", "width": 9999})

    assert resultat.ok is False
    assert any("width" in e for e in resultat.erreurs)


def test_un_type_incoercible_est_refuse():
    resultat = valider_parametres(
        "text_to_image",
        {"prompt": "un chat", "ckpt_name": "x.safetensors", "steps": "beaucoup"})

    assert resultat.ok is False


def test_un_parametre_inconnu_est_refuse():
    resultat = valider_parametres(
        "text_to_image",
        {"prompt": "un chat", "ckpt_name": "x.safetensors", "parametre_invente": 1})

    assert resultat.ok is False
    assert any("parametre_invente" in e for e in resultat.erreurs)


def test_un_workflow_candidate_est_refuse_a_la_validation():
    resultat = valider_parametres("upscale", {"prompt": "peu importe"})

    assert resultat.ok is False
    assert "pas implemente" in resultat.erreurs[0]


def test_un_workflow_inconnu_est_refuse_a_la_validation():
    resultat = valider_parametres("n-existe-pas", {})

    assert resultat.ok is False


# --- Construction du gabarit — determinisme -----------------------------------------

def test_construire_requete_est_deterministe():
    parametres = {"prompt": "un chat", "negative_prompt": "flou", "width": 512, "height": 512,
                 "steps": 20, "cfg": 8.0, "seed": 5, "ckpt_name": "x.safetensors"}

    premiere = construire_requete("text_to_image", parametres)
    seconde = construire_requete("text_to_image", parametres)

    assert premiere == seconde


def test_construire_requete_place_le_prompt_au_bon_noeud():
    parametres = {"prompt": "un phare breton", "negative_prompt": "flou", "width": 512,
                 "height": 512, "steps": 20, "cfg": 8.0, "seed": 5, "ckpt_name": "x.safetensors"}

    requete = construire_requete("text_to_image", parametres)

    assert requete["6"]["inputs"]["text"] == "un phare breton"
    assert requete["7"]["inputs"]["text"] == "flou"
    assert requete["9"]["class_type"] == "SaveImage"


def test_construire_requete_sur_workflow_non_implemente_leve():
    import pytest

    with pytest.raises(ValueError):
        construire_requete("upscale", {})
