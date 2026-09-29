"""La sonde LibreOffice convertit pour de vrai (29/09/2026).

Mesure du jour : dans le conteneur de travail, `soffice` existe et rend 0 a
une conversion sans rien ecrire. L'ancienne sonde (le binaire est-il sur le
PATH ?) l'annoncait disponible. Ces tests remplacent `soffice` par un faux
programme qui, selon le cas, ecrit un vrai PDF ou n'ecrit rien."""
import stat
import sys
from pathlib import Path

import pytest

from core.production.conversion import moteurs as m

ECRIT_UN_PDF = '''
import sys
from pathlib import Path
arguments = sys.argv[1:]
Path(sys.argv[0]).parent.joinpath("appels").open("a").write("x")
dossier = Path(arguments[arguments.index("--outdir") + 1])
entree = Path(arguments[-1])
(dossier / (entree.stem + ".pdf")).write_bytes(b"%PDF-1.4 essai")
'''

N_ECRIT_RIEN = '''
import sys
from pathlib import Path
Path(sys.argv[0]).parent.joinpath("appels").open("a").write("x")
print("Error: source file could not be loaded", file=sys.stderr)
'''


def _faux_soffice(tmp_path: Path, corps: str) -> Path:
    script = tmp_path / "soffice"
    script.write_text(f"#!{sys.executable}\n{corps}")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def _appels(script: Path) -> int:
    fichier = script.parent / "appels"
    return len(fichier.read_text()) if fichier.exists() else 0


@pytest.fixture(autouse=True)
def _sonde_neuve():
    m.oublier_sonde_soffice()
    yield
    m.oublier_sonde_soffice()


def test_un_libreoffice_qui_convertit_est_disponible(monkeypatch, tmp_path):
    script = _faux_soffice(tmp_path, ECRIT_UN_PDF)
    monkeypatch.setattr(m, "_binaire_soffice", lambda: str(script))

    ok, info = m.soffice_disponible()

    assert ok is True, info
    assert "conversion d'essai réussie" in info


def test_un_libreoffice_qui_rend_0_sans_rien_ecrire_n_est_pas_disponible(monkeypatch, tmp_path):
    script = _faux_soffice(tmp_path, N_ECRIT_RIEN)
    monkeypatch.setattr(m, "_binaire_soffice", lambda: str(script))

    ok, info = m.soffice_disponible()

    assert ok is False
    assert "n'a rien produit" in info and "could not be loaded" in info


def test_un_fichier_qui_n_est_pas_un_pdf_ne_compte_pas(monkeypatch, tmp_path):
    corps = ECRIT_UN_PDF.replace(
        'b"%PDF-1.4 essai"', 'b"pas un pdf"')
    script = _faux_soffice(tmp_path, corps)
    monkeypatch.setattr(m, "_binaire_soffice", lambda: str(script))

    assert m.soffice_disponible()[0] is False


def test_la_sonde_est_gardee_puis_refaite(monkeypatch, tmp_path):
    script = _faux_soffice(tmp_path, ECRIT_UN_PDF)
    monkeypatch.setattr(m, "_binaire_soffice", lambda: str(script))
    horloge = [1000.0]
    monkeypatch.setattr(m, "_maintenant", lambda: horloge[0])

    m.soffice_disponible()
    m.soffice_disponible()
    assert _appels(script) == 1, "la matrice ne relance pas LibreOffice a chaque couple"

    horloge[0] += m.VALIDITE_SONDE_OK + 1
    m.soffice_disponible()
    assert _appels(script) == 2, "une sonde perimee est refaite"


def test_un_echec_est_resonde_bien_plus_tot_qu_une_reussite(monkeypatch, tmp_path):
    script = _faux_soffice(tmp_path, N_ECRIT_RIEN)
    monkeypatch.setattr(m, "_binaire_soffice", lambda: str(script))
    horloge = [1000.0]
    monkeypatch.setattr(m, "_maintenant", lambda: horloge[0])

    m.soffice_disponible()
    horloge[0] += m.VALIDITE_SONDE_KO + 1
    m.soffice_disponible()

    assert m.VALIDITE_SONDE_KO < m.VALIDITE_SONDE_OK
    assert _appels(script) == 2, "un LibreOffice repare est vu dans la minute"


def test_sans_binaire_rien_n_est_lance(monkeypatch):
    monkeypatch.setattr(m, "_binaire_soffice", lambda: None)

    ok, info = m.soffice_disponible()

    assert ok is False and "PATH" in info


def test_une_conversion_refuse_un_libreoffice_qui_ne_convertit_pas(monkeypatch, tmp_path):
    script = _faux_soffice(tmp_path, N_ECRIT_RIEN)
    monkeypatch.setattr(m, "_binaire_soffice", lambda: str(script))
    source = tmp_path / "a.docx"
    source.write_bytes(b"PK")

    with pytest.raises(m.MoteurEchec, match="conversion d'essai"):
        m.convertir_office(source, tmp_path / "a.pdf", "docx")
