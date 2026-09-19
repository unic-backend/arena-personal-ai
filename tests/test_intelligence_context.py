"""Regressions: ARENA doit comprendre les renvois au fil et relire les demandes complexes."""
from apps.backend.services.orchestrator import (
    ToolTrace,
    _besoin_du_fil,
    _besoin_relecture,
    _budget_historique,
)
from core.memory.conversation import tours_anterieurs


class Journal:
    def __init__(self, tours):
        self.tours = tours

    def get_recent_history(self, session_id, limit):
        return self.tours[-limit:]


def test_references_courtes_reclament_le_fil():
    assert _besoin_du_fil("continue")
    assert _besoin_du_fil("vérifie ça")
    assert _besoin_du_fil("comme avant")
    assert _besoin_du_fil("et pourquoi ?")
    assert not _besoin_du_fil("Explique-moi le fonctionnement général des transformateurs électriques industriels")


def test_demande_complexe_declenche_relecture():
    assert _besoin_relecture("Fais un diagnostic profond de cette architecture", [])
    assert _besoin_relecture("bonjour", [ToolTrace(name="web", ok=False, error="timeout")])
    assert not _besoin_relecture("bonjour", [])


def test_reference_au_fil_recoit_plus_de_budget():
    assert _budget_historique("continue", 24000) > _budget_historique(
        "Explique la photosynthèse en une phrase complète", 24000)


def test_tours_anterieurs_restitue_ce_que_client_a_coupe():
    journal = Journal([
        {"role": "user", "content": "Mon chantier fait 23 metres."},
        {"role": "assistant", "content": "D'accord, je garde 23 metres."},
        {"role": "user", "content": "Les montants sont espaces de 40 cm."},
    ])
    deja = [{"role": "user", "content": "Les montants sont espaces de 40 cm."}]
    tours = tours_anterieurs(journal, "conversation-1", deja, "continue")
    assert [t["content"] for t in tours] == [
        "Mon chantier fait 23 metres.",
        "D'accord, je garde 23 metres.",
    ]
