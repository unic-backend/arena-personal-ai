"""Tests de sécurité et d'isolation pour Edit-Banana."""
from __future__ import annotations

import asyncio
import io
from pathlib import Path

import pytest
from PIL import Image

from core.diagramme.edit_banana import (
    ConfigurationEditBanana,
    ErreurEditBanana,
    ServiceEditBanana,
)


def _png_bytes(dimensions=(100, 100)) -> bytes:
    tampon = io.BytesIO()
    Image.new("RGB", dimensions, color=(255, 255, 255)).save(tampon, format="PNG")
    return tampon.getvalue()


@pytest.fixture
def service_configure(tmp_path) -> ServiceEditBanana:
    racine = tmp_path / "Edit-Banana"
    racine.mkdir(parents=True)
    (racine / "main.py").write_text("# double CLI", encoding="utf-8")
    (racine / "requirements.txt").write_text("torch\n", encoding="utf-8")
    (racine / "models").mkdir(parents=True)
    (racine / "models" / "sam3.pt").write_bytes(b"poids-sam3")

    python_bin = racine / ".venv" / "bin" / "python"
    python_bin.parent.mkdir(parents=True)
    python_bin.write_text("#!/bin/sh\n", encoding="utf-8")
    python_bin.chmod(0o755)

    config = ConfigurationEditBanana(
        racine=racine,
        python=python_bin,
        sam3_checkpoint=racine / "models" / "sam3.pt",
        sorties=tmp_path / "rendered" / "diagrams",
        timeout_secondes=0.2,
        pixels_max=500_000,
        cote_max=1000,
        licence_acceptee=True,
        verifier_runtime=False,
        verifier_revision=False,
    )
    return ServiceEditBanana(config)


async def test_image_corrompue_refusee_avant_subprocess(service_configure, monkeypatch):
    appele = False

    async def interdit(*args, **kwargs):
        nonlocal appele
        appele = True

    monkeypatch.setattr(asyncio, "create_subprocess_exec", interdit)

    with pytest.raises(ErreurEditBanana, match="corrompu|valide"):
        await service_configure.convertir(b"pas-du-tout-une-image", nom_source="fake.png")

    assert appele is False


async def test_image_trop_grande_refusee(service_configure, monkeypatch):
    appele = False

    async def interdit(*args, **kwargs):
        nonlocal appele
        appele = True

    monkeypatch.setattr(asyncio, "create_subprocess_exec", interdit)

    image_geante = _png_bytes(dimensions=(1200, 1200))
    with pytest.raises(ErreurEditBanana, match="trop grande"):
        await service_configure.convertir(image_geante, nom_source="giant.png")

    assert appele is False


async def test_fichier_source_inexistant_refuse(service_configure):
    with pytest.raises(ErreurEditBanana, match="introuvable"):
        await service_configure.convertir(Path("/tmp/nonexistent_image_12345.png"))


async def test_original_reste_strictement_inchange(service_configure, tmp_path, monkeypatch):
    original_fichier = tmp_path / "original_diagram.png"
    donnees_initiales = _png_bytes((100, 100))
    original_fichier.write_bytes(donnees_initiales)

    class ProcessusMock:
        returncode = 0

        def __init__(self, commande):
            self.commande = commande

        async def communicate(self):
            out_dir = Path(self.commande[self.commande.index("--output") + 1])
            out_dir.mkdir(parents=True, exist_ok=True)
            res_file = out_dir / "input_diagram.drawio"
            res_file.write_text(
                '<mxfile><diagram><mxGraphModel><root><mxCell id="0"/><mxCell id="1" parent="0"/></root></mxGraphModel></diagram></mxfile>',
                encoding="utf-8",
            )
            return b"ok", b""

        def kill(self):
            pass

    async def mock_subp(*cmd, **kwargs):
        return ProcessusMock(cmd)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_subp)

    await service_configure.convertir(original_fichier)
    assert original_fichier.read_bytes() == donnees_initiales


async def test_timeout_tue_processus_et_nettoie_sorties(service_configure, monkeypatch, tmp_path):
    class ProcessusLent:
        returncode = 0
        tue = False

        async def communicate(self):
            await asyncio.sleep(1.0)
            return b"", b""

        def kill(self):
            self.tue = True
            self.returncode = -9

    proc = ProcessusLent()

    async def mock_subp(*cmd, **kwargs):
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_subp)

    with pytest.raises(ErreurEditBanana, match="délai"):
        await service_configure.convertir(_png_bytes((50, 50)), nom_source="slow.png")

    assert proc.tue is True
    # Aucun fichier publié
    sorties_crees = list(service_configure.configuration.sorties.glob("*.drawio"))
    assert len(sorties_crees) == 0
