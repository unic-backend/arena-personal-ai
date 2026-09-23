from pathlib import Path
from unittest.mock import patch

from core.connectors.agent_reach import ConnecteurAgentReach
from core.connectors.base import EtatSante


class Proc:
    def __init__(self, code=0, out="{}", err=""):
        self.returncode = code
        self.stdout = out
        self.stderr = err


def test_agent_reach_is_read_only_and_measured():
    caps = ConnecteurAgentReach().capacites()
    assert set(caps) == {"doctor", "search", "read"}
    assert all(not cap.ecriture for cap in caps.values())


@patch("core.connectors.agent_reach.shutil.which", return_value="/bin/agent-reach")
@patch("core.connectors.agent_reach.ConnecteurAgentReach._run")
def test_doctor_must_really_answer(run, _which):
    run.return_value = Proc(out='{"twitter":{"status":"ok"}}')
    health = ConnecteurAgentReach().sonder()
    assert health.etat is EtatSante.OPERATIONNEL
    assert run.call_args.args[1:] == ("doctor", "--json")


def test_runtime_and_researcher_are_wired_to_agent_reach():
    import apps.backend.runtime as runtime
    from agents.researcher import researcher_agent

    runtime_source = Path(runtime.__file__).read_text(encoding="utf-8")
    researcher_source = Path(researcher_agent.__file__).read_text(encoding="utf-8")
    assert '"agent_reach"' in runtime_source
    assert "ConnecteurAgentReach" in runtime_source
    assert 'registre.executer(' in researcher_source
    assert '"agent_reach", "search"' in researcher_source
