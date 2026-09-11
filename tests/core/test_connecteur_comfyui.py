"""ComfyUI : moteur d'execution de workflows generatifs approuves.

Mission ARENA x COMFYUI (DEC-0087). Le contrat HTTP est celui de ComfyUI
lui-meme (`GET /system_stats`, `POST /prompt`, `GET /history/{id}`,
`POST /interrupt`, `POST /free`, `GET /models/{folder}`) — audite dans
`docs/audits/comfyui_audit.md`, jamais suppose.

Aucun test n'appelle un vrai serveur ComfyUI : `_get`/`_post`/`_get_brut`
sont monkeypatches sur le module.
"""
from pathlib import Path

import pytest

import core.connectors.comfyui as comfyui_module
from core.actions.resultat import Statut
from core.connectors.base import EtatSante
from core.connectors.comfyui import GENERATIONS_PAR_MINUTE, ComfyUIConnector

#: Materiel genereux (H100-like) — de quoi tenir text_to_image confortablement.
STATS_GENEREUX = {
    "system": {"ram_total": 64 * 1024 * 1024 * 1024, "ram_free": 50 * 1024 * 1024 * 1024,
              "comfyui_version": "0.3.99"},
    "devices": [{"name": "H100", "type": "cuda", "index": 0,
                "vram_total": 80 * 1024 * 1024 * 1024, "vram_free": 75 * 1024 * 1024 * 1024}],
}

#: Materiel reel du proprietaire (RTX A2000 12 Go, 32 Go RAM).
STATS_A2000 = {
    "system": {"ram_total": 32 * 1024 * 1024 * 1024, "ram_free": 28 * 1024 * 1024 * 1024,
              "comfyui_version": "0.3.99"},
    "devices": [{"name": "NVIDIA RTX A2000", "type": "cuda", "index": 0,
                "vram_total": 12 * 1024 * 1024 * 1024, "vram_free": 200 * 1024 * 1024}],
}

CHECKPOINTS_DISPONIBLES = ["v1-5-pruned-emaonly.safetensors"]


def faux_get(reponses, journal=None):
    def _appeler(chemin, parametres):
        if journal is not None:
            journal.append(("GET", chemin, dict(parametres)))
        for cle, valeur in reponses.items():
            if chemin.startswith(cle):
                if isinstance(valeur, Exception):
                    raise valeur
                return valeur
        raise AssertionError(f"chemin non prevu : {chemin}")
    return _appeler


def faux_post(reponse=None, journal=None):
    def _appeler(chemin, charge):
        if journal is not None:
            journal.append(("POST", chemin, charge))
        if isinstance(reponse, Exception):
            raise reponse
        return reponse if reponse is not None else {"prompt_id": "p1", "number": 1, "node_errors": {}}
    return _appeler


@pytest.fixture
def brancher(monkeypatch):
    """Branche `_get`/`_post`/`_get_brut` sur le module — jamais l'instance,
    car le connecteur les appelle en module-level (`_get(...)`, pas
    `self._get`)."""
    def _faire(get_reponses=None, post_reponse=None, journal=None, get_brut=None):
        monkeypatch.setattr(comfyui_module, "_get",
                            faux_get(get_reponses or {"system_stats": STATS_GENEREUX,
                                                      "models/checkpoints": CHECKPOINTS_DISPONIBLES},
                                     journal))
        monkeypatch.setattr(comfyui_module, "_post", faux_post(post_reponse, journal))
        if get_brut is not None:
            monkeypatch.setattr(comfyui_module, "_get_brut", get_brut)
    return _faire


@pytest.fixture
def connecteur(brancher):
    brancher()
    return ComfyUIConnector()


# --- Le coeur de la mission : jamais d'envoi sans confirmation, jamais sans materiel ---

def test_une_generation_ne_part_jamais_sans_confirmation(connecteur):
    resultat = connecteur.executer(
        "generer", workflow_id="text_to_image", prompt="un chat",
        ckpt_name="v1-5-pruned-emaonly.safetensors")

    assert resultat.statut is Statut.A_CONFIRMER
    assert not resultat.a_eu_lieu


def test_le_materiel_insuffisant_refuse_avant_tout_envoi(brancher):
    journal = []
    brancher(get_reponses={"system_stats": STATS_A2000, "models/checkpoints": CHECKPOINTS_DISPONIBLES},
             journal=journal)
    connecteur = ComfyUIConnector()

    resultat = connecteur.executer_confirmee(
        "generer", workflow_id="text_to_image", prompt="un chat",
        ckpt_name="v1-5-pruned-emaonly.safetensors")

    assert resultat.statut is Statut.NON_CONFIGURE
    assert not any(appel[0] == "POST" and appel[1] == "prompt" for appel in journal), (
        "aucune requete /prompt ne doit partir sur un materiel insuffisant")
    assert "materiel insuffisant" in resultat.message.lower()


def test_un_checkpoint_absent_refuse_avant_tout_envoi(brancher):
    journal = []
    brancher(get_reponses={"system_stats": STATS_GENEREUX, "models/checkpoints": ["autre.safetensors"]},
             journal=journal)
    connecteur = ComfyUIConnector()

    resultat = connecteur.executer_confirmee(
        "generer", workflow_id="text_to_image", prompt="un chat",
        ckpt_name="v1-5-pruned-emaonly.safetensors")

    assert resultat.statut is Statut.NON_CONFIGURE
    assert not any(appel[0] == "POST" and appel[1] == "prompt" for appel in journal)
    assert "checkpoint" in resultat.message.lower() or "v1-5" in str(resultat.detail)


def test_un_workflow_inconnu_est_refuse(connecteur):
    resultat = connecteur.executer_confirmee("generer", workflow_id="ne-existe-pas", prompt="x")

    assert resultat.statut is Statut.ECHEC


def test_un_workflow_candidate_est_refuse_jamais_envoye(connecteur, brancher):
    journal = []
    brancher(journal=journal)
    connecteur = ComfyUIConnector()

    resultat = connecteur.executer_confirmee(
        "generer", workflow_id="upscale", prompt="peu importe")

    assert resultat.statut is Statut.ECHEC
    assert "pas encore implemente" in resultat.message
    assert not any(a[0] == "POST" and a[1] == "prompt" for a in journal), (
        "un workflow non implemente ne doit jamais atteindre /prompt")


def test_des_parametres_invalides_ne_partent_pas(connecteur):
    resultat = connecteur.executer_confirmee(
        "generer", workflow_id="text_to_image", prompt="", ckpt_name="x.safetensors")

    assert resultat.statut is Statut.ECHEC


# --- Ce qui part reellement quand tout tient ------------------------------------------

def test_la_generation_confirmee_construit_le_json_api_officiel(brancher):
    journal = []
    brancher(journal=journal)
    connecteur = ComfyUIConnector()

    resultat = connecteur.executer_confirmee(
        "generer", workflow_id="text_to_image", prompt="un chat cyberpunk",
        ckpt_name="v1-5-pruned-emaonly.safetensors", seed=7, width=768, height=768)

    assert resultat.statut is Statut.SUCCES
    assert resultat.preuve == "p1"
    appel_prompt = next(a for a in journal if a[0] == "POST" and a[1] == "prompt")
    graphe = appel_prompt[2]["prompt"]
    assert graphe["3"]["class_type"] == "KSampler"
    assert graphe["3"]["inputs"]["seed"] == 7
    assert graphe["4"]["inputs"]["ckpt_name"] == "v1-5-pruned-emaonly.safetensors"
    assert graphe["5"]["inputs"]["width"] == 768
    assert graphe["6"]["inputs"]["text"] == "un chat cyberpunk"


def test_une_reponse_sans_prompt_id_n_est_pas_une_preuve(brancher):
    brancher(post_reponse={"number": 1})
    connecteur = ComfyUIConnector()

    resultat = connecteur.executer_confirmee(
        "generer", workflow_id="text_to_image", prompt="un chat",
        ckpt_name="v1-5-pruned-emaonly.safetensors")

    assert resultat.statut is Statut.ECHEC
    assert "prompt_id" in resultat.message


# --- Etat, avec relecture reelle avant de confirmer un succes ----------------------

def test_une_tache_absente_de_l_historique_n_est_pas_terminee(brancher):
    brancher(get_reponses={"system_stats": STATS_GENEREUX, "history/p1": {}})
    connecteur = ComfyUIConnector()

    resultat = connecteur.executer("etat_travail", job_id="p1")

    donnees = resultat.detail["donnees"]
    assert donnees["done"] is False


def test_etat_travail_rouvre_le_fichier_avant_de_confirmer_le_succes(tmp_path, brancher, monkeypatch):
    monkeypatch.setattr(comfyui_module, "OUTPUT_DIR", str(tmp_path))
    historique = {
        "p1": {
            "prompt": [1, "p1", {"4": {"class_type": "CheckpointLoaderSimple",
                                       "inputs": {"ckpt_name": "v1-5.safetensors"}}}],
            "outputs": {"9": {"images": [{"filename": "n-existe-pas.png", "subfolder": "",
                                          "type": "output"}]}},
            "status": {"status_str": "success", "completed": True, "messages": []},
        }
    }
    brancher(get_reponses={"system_stats": STATS_GENEREUX, "history/p1": historique})
    connecteur = ComfyUIConnector()

    resultat = connecteur.executer("etat_travail", job_id="p1")

    donnees = resultat.detail["donnees"]
    assert donnees["result"]["success"] is False
    assert donnees["result"]["generated_files"] == []


def test_etat_travail_confirme_un_vrai_fichier_et_ecrit_sa_provenance(tmp_path, brancher, monkeypatch):
    from PIL import Image

    from core.production.artefact_image import lire_provenance

    (tmp_path / "sortie").mkdir()
    fichier = tmp_path / "sortie" / "arena_00001_.png"
    Image.new("RGB", (768, 768)).save(fichier)
    monkeypatch.setattr(comfyui_module, "OUTPUT_DIR", str(tmp_path))

    historique = {
        "p1": {
            "prompt": [1, "p1", {"4": {"class_type": "CheckpointLoaderSimple",
                                       "inputs": {"ckpt_name": "v1-5.safetensors"}}}],
            "outputs": {"9": {"images": [{"filename": "arena_00001_.png", "subfolder": "sortie",
                                          "type": "output"}]}},
            "status": {"status_str": "success", "completed": True, "messages": []},
        }
    }
    brancher(get_reponses={"system_stats": STATS_GENEREUX, "history/p1": historique})
    connecteur = ComfyUIConnector()

    resultat = connecteur.executer("etat_travail", job_id="p1")

    donnees = resultat.detail["donnees"]
    assert donnees["result"]["success"] is True
    assert donnees["result"]["generated_files"] == [str(fichier)]

    provenance = lire_provenance(fichier)
    assert provenance is not None
    assert provenance["modele"] == "v1-5.safetensors"
    assert provenance["fournisseur"] == "comfyui"


def test_etat_travail_telecharge_via_view_si_pas_de_dossier_partage(tmp_path, brancher, monkeypatch):
    import io

    from PIL import Image

    tampon = io.BytesIO()
    Image.new("RGB", (512, 512)).save(tampon, format="PNG")
    contenu = tampon.getvalue()

    monkeypatch.setattr(comfyui_module, "OUTPUT_DIR", "")
    monkeypatch.setattr(comfyui_module, "RENDERED_DIR", tmp_path)

    historique = {
        "p1": {
            "prompt": [1, "p1", {}],
            "outputs": {"9": {"images": [{"filename": "arena_00001_.png", "subfolder": "",
                                          "type": "output"}]}},
            "status": {"status_str": "success", "completed": True, "messages": []},
        }
    }
    brancher(get_reponses={"system_stats": STATS_GENEREUX, "history/p1": historique},
             get_brut=lambda chemin, parametres: contenu)
    connecteur = ComfyUIConnector()

    resultat = connecteur.executer("etat_travail", job_id="p1")

    donnees = resultat.detail["donnees"]
    assert donnees["result"]["success"] is True
    assert len(donnees["result"]["generated_files"]) == 1
    assert donnees["result"]["generated_files"][0].startswith(str(tmp_path))


# --- Securite chemins : mission §31, un service exterieur ne dicte jamais ---
# --- ou un fichier atterrit sur ce disque -------------------------------------

def test_un_subfolder_qui_tente_une_evasion_est_refuse(tmp_path, brancher, monkeypatch):
    """Le fichier hors base est une VRAIE image valide (pas un leurre
    trop petit) : sans le controle de chemin, `valider_image` la
    confirmerait — c'est bien `_chemin_contenu`, seul, qui doit refuser ici
    (verifie par sabotage, voir DEC-0087)."""
    from PIL import Image

    monkeypatch.setattr(comfyui_module, "OUTPUT_DIR", str(tmp_path))
    hors_de_la_base = tmp_path.parent / "hors-base.png"
    Image.new("RGB", (512, 512)).save(hors_de_la_base)

    historique = {
        "p1": {
            "prompt": [1, "p1", {}],
            "outputs": {"9": {"images": [
                {"filename": hors_de_la_base.name, "subfolder": "../", "type": "output"}]}},
            "status": {"status_str": "success", "completed": True, "messages": []},
        }
    }
    brancher(get_reponses={"system_stats": STATS_GENEREUX, "history/p1": historique},
             get_brut=lambda chemin, parametres: (_ for _ in ()).throw(
                 AssertionError("ne doit jamais telecharger : le chemin local est refuse avant")))
    connecteur = ComfyUIConnector()

    resultat = connecteur.executer("etat_travail", job_id="p1")

    donnees = resultat.detail["donnees"]
    assert donnees["result"]["success"] is False
    assert donnees["result"]["generated_files"] == []


def test_un_nom_de_fichier_traverse_n_echappe_pas_au_telechargement(tmp_path, brancher, monkeypatch):
    import io

    from PIL import Image

    tampon = io.BytesIO()
    Image.new("RGB", (512, 512)).save(tampon, format="PNG")

    monkeypatch.setattr(comfyui_module, "OUTPUT_DIR", "")
    monkeypatch.setattr(comfyui_module, "RENDERED_DIR", tmp_path)

    historique = {
        "p1": {
            "prompt": [1, "p1", {}],
            "outputs": {"9": {"images": [
                {"filename": "../../../etc/passwd", "subfolder": "", "type": "output"}]}},
            "status": {"status_str": "success", "completed": True, "messages": []},
        }
    }
    brancher(get_reponses={"system_stats": STATS_GENEREUX, "history/p1": historique},
             get_brut=lambda chemin, parametres: tampon.getvalue())
    connecteur = ComfyUIConnector()

    resultat = connecteur.executer("etat_travail", job_id="p1")

    donnees = resultat.detail["donnees"]
    assert donnees["result"]["success"] is True
    fichier_ecrit = Path(donnees["result"]["generated_files"][0])
    # Le fichier ecrit reste SOUS tmp_path, jamais remonte par le `../../..`
    # du nom annonce.
    assert fichier_ecrit.resolve().parent == tmp_path.resolve()
    assert fichier_ecrit.name != "passwd"


def test_une_tache_en_echec_porte_sa_raison(brancher):
    historique = {"p1": {"prompt": [1, "p1", {}], "outputs": {},
                        "status": {"status_str": "error", "completed": True,
                                  "messages": ["CUDA out of memory"]}}}
    brancher(get_reponses={"system_stats": STATS_GENEREUX, "history/p1": historique})
    connecteur = ComfyUIConnector()

    resultat = connecteur.executer("etat_travail", job_id="p1")

    donnees = resultat.detail["donnees"]
    assert donnees["done"] is True
    assert donnees["result"]["success"] is False


def test_l_etat_sans_identifiant_ne_regarde_rien(connecteur):
    resultat = connecteur.executer("etat_travail", job_id="")

    assert resultat.statut is Statut.ECHEC


# --- Sante, annulation, dechargement -----------------------------------------------

def test_le_serveur_eteint_donne_la_commande_de_lancement(brancher):
    brancher(get_reponses={"system_stats": ConnectionError("refuse")})
    connecteur = ComfyUIConnector()

    sante = connecteur.sante()

    assert sante.etat is EtatSante.NON_CONFIGURE
    assert "COMFYUI_URL" in sante.ce_qui_manque


def test_annuler_travail_appelle_interrupt(brancher):
    journal = []
    brancher(journal=journal)
    connecteur = ComfyUIConnector()

    resultat = connecteur.executer("annuler_travail", job_id="p1")

    assert resultat.statut is Statut.SUCCES
    appel = next(a for a in journal if a[0] == "POST" and a[1] == "interrupt")
    assert appel[2]["prompt_id"] == "p1"


def test_decharger_appelle_free(brancher):
    journal = []
    brancher(journal=journal)
    connecteur = ComfyUIConnector()

    resultat = connecteur.executer("decharger")

    assert resultat.statut is Statut.SUCCES
    appel = next(a for a in journal if a[0] == "POST" and a[1] == "free")
    assert appel[2]["unload_models"] is True


def test_decharger_sans_serveur_est_honnete(brancher):
    brancher(get_reponses={"system_stats": STATS_GENEREUX})
    connecteur = ComfyUIConnector()

    import core.connectors.comfyui as mod

    def _echoue(chemin, charge):
        raise ConnectionError("refuse")
    import pytest as _pytest  # noqa: F401 — juste pour clarte locale, pas utilise en assert
    _orig = mod._post
    mod._post = _echoue
    try:
        resultat = connecteur.executer("decharger")
    finally:
        mod._post = _orig

    assert resultat.statut is Statut.NON_CONFIGURE


# --- Catalogue et capacites declarees -----------------------------------------------

def test_lister_workflows_rend_le_catalogue_reel(connecteur):
    resultat = connecteur.executer("lister_workflows")

    identifiants = {w["identifiant"] for w in resultat.detail["donnees"]["workflows"]}
    assert "text_to_image" in identifiants
    assert "upscale" in identifiants  # CANDIDATE, mais listee


def test_les_capacites_declarees(connecteur):
    capacites = connecteur.capacites()

    assert set(capacites) == {
        "capacites", "lister_workflows", "generer", "etat_travail",
        "annuler_travail", "decharger",
    }
    assert capacites["generer"].quota_par_minute == GENERATIONS_PAR_MINUTE
    assert capacites["generer"].ecriture is True
    assert capacites["decharger"].ecriture is True


def test_le_service_declare_est_image_generation(connecteur):
    assert connecteur.service == "image_generation"


def test_la_regle_exige_bien_une_confirmation():
    from pathlib import Path

    import yaml
    racine = Path(__file__).resolve().parents[2]
    regles = yaml.safe_load(
        (racine / "config" / "permissions_services.yaml").read_text(encoding="utf-8"))

    assert regles["services"]["image_generation"]["generate"]["decision"] == "CONFIRMATION"
    assert regles["services"]["image_generation"]["unload"]["decision"] == "ALLOWED"


@pytest.mark.parametrize("interdite", ["supprimer", "delete", "pipeline"])
def test_capacite_hors_liste_n_existe_pas(connecteur, interdite):
    assert connecteur.executer(interdite).statut is Statut.NON_IMPLEMENTE
