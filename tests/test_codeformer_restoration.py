"""Contrat de restauration CodeFormer sans charger les poids de 500+ Mo.

Le CLI externe est double uniquement aux frontieres subprocess ; toutes les
validations, la copie d'artefact et la provenance sont celles de production.
"""
from __future__ import annotations

import asyncio
import io
from pathlib import Path

import pytest
from PIL import Image

from agents.image_restoration.image_restoration_agent import ImageRestorationAgent
from apps.backend.pieces_jointes import DepotPiecesJointes
from core.restoration import codeformer
from core.restoration.codeformer import (
    ConfigurationCodeFormer,
    ErreurRestauration,
    ServiceCodeFormer,
)


def image_png(taille=(64, 64), couleur="navy") -> bytes:
    tampon = io.BytesIO()
    Image.effect_noise(taille, 80).convert("RGB").save(tampon, format="PNG")
    return tampon.getvalue()


@pytest.fixture
def moteur(tmp_path) -> tuple[ServiceCodeFormer, Path]:
    racine = tmp_path / "CodeFormer"
    (racine / "weights" / "CodeFormer").mkdir(parents=True)
    (racine / "weights" / "facelib").mkdir(parents=True)
    (racine / "inference_codeformer.py").write_text("# double", encoding="utf-8")
    python = racine / "python"
    python.write_text("double", encoding="utf-8")
    for chemin in (
        racine / "weights" / "CodeFormer" / "codeformer.pth",
        racine / "weights" / "facelib" / "detection_Resnet50_Final.pth",
        racine / "weights" / "facelib" / "parsing_parsenet.pth",
    ):
        chemin.write_bytes(b"poids-double")
    configuration = ConfigurationCodeFormer(
        racine=racine, python=python, sorties=tmp_path / "rendered" / "restorations",
        timeout_secondes=0.1, pixels_max=1_000_000, cote_max=1000,
        licence_acceptee=True, verifier_runtime=False, verifier_revision=False,
    )
    return ServiceCodeFormer(configuration), racine


class ProcessusReussi:
    returncode = 0

    def __init__(self, commande):
        self.commande = commande

    async def communicate(self):
        sortie = Path(self.commande[self.commande.index("--output_path") + 1])
        produit = sortie / "final_results" / "source.png"
        produit.parent.mkdir(parents=True)
        Image.effect_noise((128, 128), 90).convert("RGB").save(produit, format="PNG")
        return b"ok", b""

    def kill(self):
        self.returncode = -9


async def processus_reussi(*commande, **_kwargs):
    return ProcessusReussi(commande)


async def test_image_valide_produit_un_artefact_verifie_et_une_provenance(moteur, monkeypatch):
    service, _ = moteur
    monkeypatch.setattr(codeformer.asyncio, "create_subprocess_exec", processus_reussi)

    resultat = await service.restaurer(image_png(), nom_source="portrait.png")

    assert resultat.sortie.is_file()
    assert resultat.sortie.stat().st_size > 512
    assert resultat.url.startswith("/media/rendered/restorations/restauration-")
    assert resultat.provenance.is_file()
    assert '"operation": "image_restoration"' in resultat.provenance.read_text(encoding="utf-8")


async def test_agent_rend_un_artefact_structure_dans_le_flux_existant(moteur, monkeypatch):
    service, _ = moteur
    monkeypatch.setattr(codeformer.asyncio, "create_subprocess_exec", processus_reussi)
    depot = DepotPiecesJointes()
    piece = depot.deposer("portrait.png", image_png())
    agent = ImageRestorationAgent(service, depot)

    reponse = await agent.run("Restaure cette photo", {"attachments": [piece.identifiant]})

    assert reponse["status"] == "success"
    assert reponse["document"]["statut"] == "SUCCESS"
    assert reponse["document"]["type"] == "image/png"
    assert reponse["document"]["url"] == reponse["restoration"]["url"]


def test_absence_de_configuration_n_empeche_pas_le_service_de_naitre(tmp_path):
    service = ServiceCodeFormer(ConfigurationCodeFormer(
        racine=None, python=None, sorties=tmp_path, licence_acceptee=True))
    etat = service.etat()
    assert etat.disponible is False
    assert "ROOT" in etat.raison


async def test_image_corrompue_est_refusee_avant_le_moteur(moteur, monkeypatch):
    service, _ = moteur
    appele = False

    async def interdit(*args, **kwargs):
        nonlocal appele
        appele = True

    monkeypatch.setattr(codeformer.asyncio, "create_subprocess_exec", interdit)
    with pytest.raises(ErreurRestauration, match="corrompu"):
        await service.restaurer(b"pas une image", nom_source="mensonge.png")
    assert appele is False


async def test_modele_manquant_rend_la_capacite_indisponible(moteur):
    service, racine = moteur
    (racine / "weights" / "CodeFormer" / "codeformer.pth").unlink()

    with pytest.raises(ErreurRestauration, match="Poids manquants"):
        await service.restaurer(image_png(), nom_source="portrait.png")


async def test_dependance_optionnelle_manquante_est_rapportee(moteur, monkeypatch):
    service, _ = moteur

    class ProcessusSansTorch(ProcessusReussi):
        returncode = 1

        async def communicate(self):
            return b"", b"ModuleNotFoundError: No module named 'torch'"

    async def sans_torch(*commande, **_kwargs):
        return ProcessusSansTorch(commande)

    monkeypatch.setattr(codeformer.asyncio, "create_subprocess_exec", sans_torch)
    with pytest.raises(ErreurRestauration, match="ModuleNotFoundError"):
        await service.restaurer(image_png(), nom_source="portrait.png")


def test_cpu_est_un_repli_explicitement_signale(moteur, monkeypatch):
    service, _ = moteur
    monkeypatch.setattr(codeformer, "mesurer_gpu", lambda: None)

    etat = service.etat()

    assert etat.device == "cpu"
    assert etat.cpu_lent is True
    assert etat.disponible is True


async def test_l_original_reste_strictement_inchange(moteur, monkeypatch):
    service, _ = moteur
    monkeypatch.setattr(codeformer.asyncio, "create_subprocess_exec", processus_reussi)
    original = image_png()
    avant = bytes(original)

    await service.restaurer(original, nom_source="portrait.png")

    assert original == avant


@pytest.mark.parametrize("fidelity", [-0.01, 1.01, True, "pas-un-nombre"])
async def test_fidelity_hors_limites_est_refusee(moteur, fidelity):
    service, _ = moteur
    with pytest.raises(ErreurRestauration, match="fidelity"):
        await service.restaurer(image_png(), nom_source="portrait.png", fidelity=fidelity)


async def test_image_pathologique_est_refusee_avant_inference(moteur, monkeypatch):
    service, _ = moteur
    service.configuration = ConfigurationCodeFormer(
        **{**service.configuration.__dict__, "pixels_max": 100}
    )
    appele = False

    async def interdit(*args, **kwargs):
        nonlocal appele
        appele = True

    monkeypatch.setattr(codeformer.asyncio, "create_subprocess_exec", interdit)
    with pytest.raises(ErreurRestauration, match="trop grande"):
        await service.restaurer(image_png((20, 20)), nom_source="grande.png")
    assert appele is False


async def test_identifiant_de_piece_n_est_jamais_un_chemin(moteur, tmp_path):
    service, _ = moteur
    depot = DepotPiecesJointes()
    agent = ImageRestorationAgent(service, depot)
    secret = tmp_path / "secret.png"
    secret.write_bytes(image_png())

    resultat = await agent.run("Restaure cette photo", {"attachments": [str(secret), "../../secret.png"]})

    assert resultat["status"] == "error"
    assert "autorisee" in resultat["response"]


async def test_sortie_corrompue_n_est_jamais_exposee(moteur, monkeypatch):
    service, _ = moteur

    class ProcessusCorrompu(ProcessusReussi):
        async def communicate(self):
            sortie = Path(self.commande[self.commande.index("--output_path") + 1])
            produit = sortie / "final_results" / "source.png"
            produit.parent.mkdir(parents=True)
            produit.write_bytes(b"faux")
            return b"ok", b""

    async def corrompu(*commande, **_kwargs):
        return ProcessusCorrompu(commande)

    monkeypatch.setattr(codeformer.asyncio, "create_subprocess_exec", corrompu)
    with pytest.raises(ErreurRestauration, match="rendu CodeFormer est absent"):
        await service.restaurer(image_png(), nom_source="portrait.png")
    assert not list(service.configuration.sorties.glob("*.png"))


async def test_timeout_tue_le_processus_et_ne_publie_rien(moteur, monkeypatch):
    service, _ = moteur

    class ProcessusLent(ProcessusReussi):
        async def communicate(self):
            if self.returncode == -9:
                return b"", b"tue"
            await asyncio.sleep(1)
            return b"", b""

    processus = ProcessusLent(())

    async def lent(*commande, **_kwargs):
        processus.commande = commande
        return processus

    monkeypatch.setattr(codeformer.asyncio, "create_subprocess_exec", lent)
    with pytest.raises(ErreurRestauration, match="delai"):
        await service.restaurer(image_png(), nom_source="portrait.png")
    assert processus.returncode == -9
    assert not list(service.configuration.sorties.glob("*.png"))


async def test_executions_concurrentes_sont_bornees(moteur, monkeypatch):
    service, _ = moteur
    actifs = 0
    maximum = 0

    async def double(*args, **kwargs):
        nonlocal actifs, maximum
        actifs += 1
        maximum = max(maximum, actifs)
        await asyncio.sleep(0.02)
        actifs -= 1
        # Cette frontiere est doublee ici pour mesurer exclusivement le verrou.
        return "ok"

    monkeypatch.setattr(service, "_executer", double)
    await asyncio.gather(*(
        service.restaurer(image_png(), nom_source=f"p-{i}.png") for i in range(3)
    ))
    assert maximum == 1
