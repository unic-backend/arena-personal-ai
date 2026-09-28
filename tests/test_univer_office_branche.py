"""Dioumtoukay -> registre -> Univer : le connecteur n'est jamais dormant."""

import pytest

from agents.dioumtoukay.dioumtoukay_agent import DioumtoukayAgent, analyser_action
from core.actions.resultat import succes


class FauxUniver:
    def __init__(self):
        self.appels = []

    def executer(self, capacite, **parametres):
        self.appels.append((capacite, parametres))
        return succes(
            action=capacite,
            cible="univer_office",
            message="Office exécuté.",
            preuve="preuve-office",
            fichier=parametres.get("fichier", ""),
            worktree=parametres.get("worktree", ""),
            unit=parametres.get("unit", ""),
        )


class FauxRegistre:
    def __init__(self, connecteur):
        self.connecteur = connecteur
        self.demandes = []

    def obtenir(self, nom):
        self.demandes.append(nom)
        return self.connecteur if nom == "office_univer" else None


def _agent(connecteur):
    agent = object.__new__(DioumtoukayAgent)
    agent.registre_connecteurs = FauxRegistre(connecteur)
    return agent


@pytest.mark.asyncio
async def test_action_office_statut_appelle_reellement_le_connecteur():
    univer = FauxUniver()
    agent = _agent(univer)
    action = analyser_action(
        "ACTION: office_statut\n"
        "CHEMIN: budget.univer\n"
    )

    assert action is not None
    resultat = await agent._executer_action(action, github_distant=False)

    assert resultat.ok is True
    assert agent.registre_connecteurs.demandes == ["office_univer"]
    assert univer.appels == [
        ("statut", {"fichier": "budget.univer", "worktree": ""})
    ]


@pytest.mark.asyncio
async def test_action_office_executer_transporte_worktree_unit_et_code_sans_shell():
    univer = FauxUniver()
    agent = _agent(univer)
    code = 'workbook.getActiveSheet().getRange("A1").setValue("UniC");'
    action = analyser_action(
        "ACTION: office_executer\n"
        "CHEMIN: devis.univer\n"
        "WORKTREE_ID: wt-123\n"
        "UNIT_ID: unit-456\n"
        "CONTENU:\n"
        f"{code}\n"
        "FIN\n"
    )

    assert action is not None
    resultat = await agent._executer_action(action, github_distant=True)

    assert resultat.ok is True
    assert univer.appels == [
        (
            "executer",
            {
                "fichier": "devis.univer",
                "worktree": "wt-123",
                "unit": "unit-456",
                "code": code,
            },
        )
    ]
