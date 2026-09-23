from pathlib import Path
from unittest.mock import patch

from core.connectors.base import EtatSante
from core.connectors.hyperframes import ConnecteurHyperframes


class FauxProcess:
    def __init__(self, code=0, out="{}", err=""):
        self.returncode = code
        self.stdout = out
        self.stderr = err


def test_hyperframes_declares_real_check_and_render_capabilities():
    caps = ConnecteurHyperframes().capacites()
    assert set(caps) == {"verifier", "rendre"}
    assert caps["verifier"].ecriture is False
    assert caps["rendre"].ecriture is True


@patch("core.connectors.hyperframes.shutil.which")
@patch("core.connectors.hyperframes._commande")
def test_health_is_measured_with_doctor(command, which):
    which.side_effect = lambda name: f"/usr/bin/{name}"
    command.side_effect = [FauxProcess(out="v24.0.0"), FauxProcess(out='{"ok":true}')]
    health = ConnecteurHyperframes().sonder()
    assert health.etat is EtatSante.OPERATIONNEL
    assert any("doctor" in call.args for call in command.call_args_list)


def test_video_planner_and_agent_really_route_hyperframes():
    from core.production.plan_video import CAPACITES_VIDEO
    from agents.video import production_agent

    assert "hyperframes_render" in CAPACITES_VIDEO
    source = Path(production_agent.__file__).read_text(encoding="utf-8")
    assert 'registre.executer("hyperframes", "rendre"' in source
    assert 'capacite == "hyperframes_render"' in source


def test_runtime_registers_hyperframes_connector():
    import apps.backend.runtime as runtime
    source = Path(runtime.__file__).read_text(encoding="utf-8")
    assert '"hyperframes"' in source
    assert "ConnecteurHyperframes" in source
