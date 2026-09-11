"""Decision de strategie ComfyUI — mission ARENA x COMFYUI (DEC-0087).

Meme discipline que `test_hidream_strategie.py` : aucun GPU requis, chaque
decision est verifiee contre un `Materiel` construit a la main.
"""
from core.production.comfyui_strategie import StrategieComfyUI, decider_strategie
from core.production.comfyui_workflows import REGISTRE, ProfilRessourcesWorkflow
from core.production.materiel import EtatDisque, EtatGpu, EtatRam

PROFIL_TEXT_TO_IMAGE = REGISTRE["text_to_image"].profil_ressources

DISQUE_AMPLE = EtatDisque(chemin="/data", libre_mo=200 * 1024, mesure_le="x")


def _gpu(vram_libre_go: float, nom: str = "GPU") -> EtatGpu:
    return EtatGpu(nom=nom, vram_totale_mo=int(vram_libre_go * 1024) + 512,
                   vram_libre_mo=int(vram_libre_go * 1024), mesure_le="x")


def _ram(disponible_go: float, totale_go: float = 32) -> EtatRam:
    return EtatRam(totale_mo=int(totale_go * 1024), disponible_mo=int(disponible_go * 1024),
                   mesure_le="x")


def test_disque_non_mesurable_est_unsupported():
    decision = decider_strategie(PROFIL_TEXT_TO_IMAGE, _gpu(20), _ram(20), None)

    assert decision.strategie is StrategieComfyUI.UNSUPPORTED
    assert "disque" in decision.raison


def test_disque_insuffisant_est_unsupported():
    disque = EtatDisque(chemin="/data", libre_mo=1, mesure_le="x")

    decision = decider_strategie(PROFIL_TEXT_TO_IMAGE, _gpu(20), _ram(20), disque)

    assert decision.strategie is StrategieComfyUI.UNSUPPORTED


def test_vram_confortable_rend_local_fast():
    decision = decider_strategie(PROFIL_TEXT_TO_IMAGE, _gpu(20, "RTX 4090"), _ram(16), DISQUE_AMPLE)

    assert decision.strategie is StrategieComfyUI.LOCAL_FAST


def test_vram_entre_minimum_et_confortable_rend_local_supported():
    # confortable=6 Go, minimum=4 Go : viser une VRAM utilisable ~4.5 Go
    decision = decider_strategie(PROFIL_TEXT_TO_IMAGE, _gpu(5.3), _ram(16), DISQUE_AMPLE)

    assert decision.strategie is StrategieComfyUI.LOCAL_SUPPORTED


def test_vram_sous_minimum_mais_ram_suffisante_rend_local_offload():
    decision = decider_strategie(PROFIL_TEXT_TO_IMAGE, _gpu(3.0), _ram(16), DISQUE_AMPLE)

    assert decision.strategie is StrategieComfyUI.LOCAL_OFFLOAD


def test_vram_sous_le_plancher_offload_est_unsupported_sans_serveur_distant():
    decision = decider_strategie(PROFIL_TEXT_TO_IMAGE, _gpu(0.5), _ram(16), DISQUE_AMPLE)

    assert decision.strategie is StrategieComfyUI.UNSUPPORTED


def test_vram_sous_le_plancher_offload_avec_serveur_distant_rend_remote_recommended():
    decision = decider_strategie(
        PROFIL_TEXT_TO_IMAGE, _gpu(0.5), _ram(16), DISQUE_AMPLE, worker_distant_configure=True)

    assert decision.strategie is StrategieComfyUI.REMOTE_RECOMMENDED


def test_ram_totale_insuffisante_refuse_meme_avec_vram():
    decision = decider_strategie(PROFIL_TEXT_TO_IMAGE, _gpu(20), _ram(2, totale_go=4), DISQUE_AMPLE)

    assert decision.strategie is not StrategieComfyUI.LOCAL_FAST
    assert decision.strategie is not StrategieComfyUI.LOCAL_SUPPORTED


def test_aucune_carte_visible_est_unsupported_sans_serveur_distant():
    decision = decider_strategie(PROFIL_TEXT_TO_IMAGE, None, _ram(16), DISQUE_AMPLE)

    assert decision.strategie is StrategieComfyUI.UNSUPPORTED
    assert "aucune carte" in decision.raison


def test_le_materiel_reel_du_proprietaire_rtx_a2000_est_mesure_pas_suppose():
    """RTX A2000 12 Go, 32 Go RAM (mission §13) — 200 Mo libres seulement
    (le pire cas, GPU deja occupe par autre chose) doit refuser proprement,
    jamais planter."""
    gpu = EtatGpu(nom="NVIDIA RTX A2000", vram_totale_mo=12288, vram_libre_mo=200, mesure_le="x")
    ram = EtatRam(totale_mo=32768, disponible_mo=28000, mesure_le="x")

    decision = decider_strategie(PROFIL_TEXT_TO_IMAGE, gpu, ram, DISQUE_AMPLE)

    assert decision.strategie in (StrategieComfyUI.UNSUPPORTED, StrategieComfyUI.LOCAL_OFFLOAD)


def test_le_materiel_reel_du_proprietaire_avec_vram_libre_tient_confortablement():
    """Meme carte, VRAM effectivement libre (rien d'autre charge) : le
    workflow leger text_to_image doit tenir — contrairement a HiDream."""
    gpu = EtatGpu(nom="NVIDIA RTX A2000", vram_totale_mo=12288, vram_libre_mo=11000, mesure_le="x")
    ram = EtatRam(totale_mo=32768, disponible_mo=28000, mesure_le="x")

    decision = decider_strategie(PROFIL_TEXT_TO_IMAGE, gpu, ram, DISQUE_AMPLE)

    assert decision.strategie is StrategieComfyUI.LOCAL_FAST


def test_decision_porte_toujours_une_raison_non_vide():
    profil = ProfilRessourcesWorkflow(
        vram_confortable_mo=1, vram_minimum_mo=1, ram_totale_minimum_mo=1, disque_modele_mo=1)

    decision = decider_strategie(profil, None, None, None)

    assert decision.raison
