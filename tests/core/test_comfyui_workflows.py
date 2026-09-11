"""Le registre CONTROLE des workflows ComfyUI — mission ARENA x COMFYUI
(DEC-0087). Deterministe et testable SANS serveur (mission §9) : chaque
test tourne sans reseau, sans GPU.
"""
import base64

import pytest

from core.production.comfyui_workflows import (
    REGISTRE,
    EntreeWorkflow,
    ProfilRessourcesWorkflow,
    StatutWorkflow,
    construire_requete,
    lister,
    obtenir,
    valider_parametres,
)

#: Un base64 valide, assez long pour passer le controle de taille — jamais
#: une vraie image (le contenu n'est jamais ouvert par ce module, seule sa
#: FORME est verifiee ici ; `valider_image` du connecteur, apres
#: televersement, verifie le contenu reel).
IMAGE_B64 = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"x" * 200).decode()


def test_les_six_workflows_sont_stables():
    stables = sorted(i for i, w in REGISTRE.items() if w.statut is StatutWorkflow.STABLE)
    assert stables == sorted(REGISTRE)
    assert len(stables) == 6


def test_tous_les_workflows_stables_ont_un_gabarit():
    for identifiant, entree in REGISTRE.items():
        assert entree.implemente, f"{identifiant} est STABLE mais n'a pas de gabarit"


def test_lister_rend_le_catalogue_entier_sans_le_gabarit():
    catalogue = lister()

    assert len(catalogue) == len(REGISTRE)
    for entree in catalogue:
        assert "gabarit" not in entree
        assert "identifiant" in entree and "profil_ressources" in entree


def test_obtenir_workflow_inconnu_rend_none():
    assert obtenir("n-existe-pas") is None


@pytest.fixture
def workflow_candidat(monkeypatch):
    """Un faux workflow CANDIDATE, injecte dans le registre le temps d'un
    test — le registre reel n'en a plus (les six sont STABLE), mais la
    logique de refus « reconnu, pas implemente » reste une regle du module
    et merite sa propre couverture, independamment de l'etat du catalogue."""
    faux = EntreeWorkflow(
        identifiant="faux_candidat", version="0.0.0-candidate", statut=StatutWorkflow.CANDIDATE,
        objectif="test", noeuds_requis=(), modeles_requis=(),
        profil_ressources=ProfilRessourcesWorkflow(1, 1, 1, 1), gabarit=None,
    )
    registre_test = dict(REGISTRE)
    registre_test["faux_candidat"] = faux
    monkeypatch.setattr("core.production.comfyui_workflows.REGISTRE", registre_test)
    return faux


def test_un_workflow_candidate_n_a_pas_de_gabarit(workflow_candidat):
    assert workflow_candidat.gabarit is None
    assert workflow_candidat.implemente is False


def test_un_workflow_candidate_est_refuse_a_la_validation(workflow_candidat):
    resultat = valider_parametres("faux_candidat", {"prompt": "peu importe"})

    assert resultat.ok is False
    assert "pas implemente" in resultat.erreurs[0]


def test_construire_requete_sur_workflow_non_implemente_leve(workflow_candidat):
    with pytest.raises(ValueError):
        construire_requete("faux_candidat", {})


def test_un_workflow_inconnu_est_refuse_a_la_validation():
    resultat = valider_parametres("n-existe-pas", {})

    assert resultat.ok is False


# --- Validation deterministe — text_to_image ------------------------------------

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


# --- image_base64 : validation de forme, jamais de contenu ----------------------

def test_image_base64_absente_est_requise():
    resultat = valider_parametres("upscale", {"model_name": "x.pth"})

    assert resultat.ok is False
    assert any("image_source" in e for e in resultat.erreurs)


def test_image_base64_invalide_est_refusee():
    resultat = valider_parametres(
        "upscale", {"model_name": "x.pth", "image_source": "pas-du-base64!!!"})

    assert resultat.ok is False
    assert any("base64" in e for e in resultat.erreurs)


def test_image_base64_trop_grande_est_refusee():
    enorme = base64.b64encode(b"x" * (21 * 1024 * 1024)).decode()

    resultat = valider_parametres("upscale", {"model_name": "x.pth", "image_source": enorme})

    assert resultat.ok is False
    assert any("plafond" in e for e in resultat.erreurs)


def test_image_base64_valide_traverse_intacte():
    resultat = valider_parametres(
        "upscale", {"model_name": "x.pth", "image_source": IMAGE_B64})

    assert resultat.ok is True
    assert resultat.parametres["image_source"] == IMAGE_B64


# --- Construction du gabarit — determinisme, text_to_image -----------------------

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


# --- Les cinq workflows nouvellement implementes ---------------------------------

CAS_VALIDES = {
    "image_to_image": {
        "prompt": "un chat", "ckpt_name": "x.safetensors", "image_source": IMAGE_B64,
    },
    "upscale": {"image_source": IMAGE_B64, "model_name": "4x.pth"},
    "controlnet_image": {
        "prompt": "un chat", "ckpt_name": "x.safetensors", "image_source": IMAGE_B64,
        "control_net_name": "cn.safetensors",
    },
    "character_image": {
        "prompt": "un chat", "ckpt_name": "x.safetensors", "lora_name": "l.safetensors",
    },
    "image_to_video": {"image_source": IMAGE_B64, "ckpt_name": "svd.safetensors"},
}


@pytest.mark.parametrize("workflow_id,parametres", sorted(CAS_VALIDES.items()))
def test_chaque_nouveau_workflow_valide_et_se_construit(workflow_id, parametres):
    resultat = valider_parametres(workflow_id, parametres)
    assert resultat.ok is True, resultat.erreurs

    requete = construire_requete(workflow_id, resultat.parametres)

    assert requete  # au moins un noeud
    for noeud in requete.values():
        assert "class_type" in noeud and "inputs" in noeud


@pytest.mark.parametrize("workflow_id", sorted(CAS_VALIDES))
def test_chaque_nouveau_workflow_declare_ses_verifications_de_modele(workflow_id):
    entree = obtenir(workflow_id)
    assert entree.verification_modeles, f"{workflow_id} ne declare aucun modele a verifier"
    for parametre in entree.verification_modeles:
        assert parametre in entree.schema_entree


def test_image_to_image_utilise_le_denoise_demande():
    resultat = valider_parametres("image_to_image", {
        **CAS_VALIDES["image_to_image"], "denoise": 0.4,
    })
    requete = construire_requete("image_to_image", resultat.parametres)

    noeud_ksampler = next(n for n in requete.values() if n["class_type"] == "KSampler")
    assert noeud_ksampler["inputs"]["denoise"] == 0.4


def test_upscale_ne_declare_ni_prompt_ni_checkpoint():
    entree = obtenir("upscale")
    assert "prompt" not in entree.schema_entree
    assert "ckpt_name" not in entree.schema_entree


def test_controlnet_image_utilise_controlnetapplyadvanced_jamais_le_deprecie():
    resultat = valider_parametres("controlnet_image", CAS_VALIDES["controlnet_image"])
    requete = construire_requete("controlnet_image", resultat.parametres)

    types = {n["class_type"] for n in requete.values()}
    assert "ControlNetApplyAdvanced" in types
    assert "ControlNetApply" not in types


def test_character_image_ne_prend_aucune_image_de_reference():
    entree = obtenir("character_image")
    assert not any(p.type == "image_base64" for p in entree.schema_entree.values())


def test_image_to_video_produit_un_save_animated_webp():
    resultat = valider_parametres("image_to_video", CAS_VALIDES["image_to_video"])
    requete = construire_requete("image_to_video", resultat.parametres)

    types = {n["class_type"] for n in requete.values()}
    assert "SaveAnimatedWEBP" in types
    assert "ImageOnlyCheckpointLoader" in types


def test_les_gabarits_nouveaux_sont_deterministes():
    for workflow_id, parametres in CAS_VALIDES.items():
        resultat = valider_parametres(workflow_id, parametres)
        assert resultat.ok is True, (workflow_id, resultat.erreurs)
        premiere = construire_requete(workflow_id, resultat.parametres)
        seconde = construire_requete(workflow_id, resultat.parametres)
        assert premiere == seconde, workflow_id
