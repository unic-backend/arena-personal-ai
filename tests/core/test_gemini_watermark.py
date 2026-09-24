from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from core.production import gemini_watermark as gwr


def _image(path: Path) -> None:
    Image.new("RGB", (64, 64), "white").save(path)


def test_nettoyage_invoque_cli_et_valide_sortie(tmp_path, monkeypatch):
    source = tmp_path / "source.png"
    sortie = tmp_path / "clean.png"
    _image(source)

    def run(cmd, **kwargs):
        assert cmd[:2] == ["gwr", "remove"]
        assert "--json" in cmd
        _image(sortie)
        return SimpleNamespace(returncode=0, stdout='{"status":"success"}', stderr="")

    monkeypatch.setattr(gwr.subprocess, "run", run)
    resultat = gwr.retirer_filigrane_gemini(source, sortie)

    assert resultat.ok is True
    assert resultat.sortie == sortie.resolve()
    assert resultat.details == {"status": "success"}


def test_nettoyage_refuse_succes_sans_image_reelle(tmp_path, monkeypatch):
    source = tmp_path / "source.png"
    sortie = tmp_path / "clean.png"
    _image(source)

    monkeypatch.setattr(
        gwr.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout="{}", stderr=""),
    )
    resultat = gwr.retirer_filigrane_gemini(source, sortie)

    assert resultat.ok is False
    assert "invalide" in resultat.erreur
    assert not sortie.exists()


def test_nettoyage_echec_moteur_ne_laisse_pas_artefact(tmp_path, monkeypatch):
    source = tmp_path / "source.png"
    sortie = tmp_path / "clean.png"
    _image(source)
    sortie.write_bytes(b"ancien")

    monkeypatch.setattr(
        gwr.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=2, stdout="", stderr="watermark unsupported"),
    )
    resultat = gwr.retirer_filigrane_gemini(source, sortie)

    assert resultat.ok is False
    assert "unsupported" in resultat.erreur
    assert not sortie.exists()
