"""Dioumtoukay -> registre -> Univer : le connecteur n'est jamais dormant."""

import pytest

from agents.dioumtoukay.dioumtoukay_agent import DioumtoukayAgent, analyser_action
from core.actions.resultat import a_confirmer, succes


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



class FauxUniverExport:
    def executer(self, capacite, **parametres):
        if capacite == "exporter":
            return succes(
                action=capacite,
                cible="univer_office",
                message="Export XLSX créé.",
                preuve="/tmp/rapport.xlsx",
                fichier="/tmp/rapport.xlsx",
                url="/media/rendered/office/rapport.xlsx",
                taille_octets=1234,
            )
        raise AssertionError(capacite)


class FauxUniverConfirmation:
    def executer(self, capacite, **parametres):
        return a_confirmer(
            action=capacite,
            cible="univer_office",
            message="Confirmation requise.",
            fichier=parametres.get("fichier", ""),
        )


def test_export_office_conserve_les_donnees_structurees_et_le_lien():
    agent = _agent(FauxUniverExport())

    resultat = agent._via_univer(
        "exporter",
        fichier="rapport.univer",
        unit="unit-1",
        format="xlsx",
        nom="rapport",
    )
    acte = {
        "action": "office_exporter",
        "champs": {"CHEMIN": "rapport.univer"},
        **resultat.to_dict(),
    }

    assert resultat.ok is True
    assert resultat.donnees["url"] == "/media/rendered/office/rapport.xlsx"
    assert DioumtoukayAgent.documents_produits([acte]) == [{
        "statut": "SUCCESS",
        "url": "/media/rendered/office/rapport.xlsx",
        "message": "Export XLSX créé.",
        "fichier": "/tmp/rapport.xlsx",
    }]


def test_action_en_attente_n_est_pas_comptee_comme_fichier_modifie():
    agent = _agent(FauxUniverConfirmation())

    resultat = agent._via_univer(
        "executer",
        fichier="budget.univer",
        worktree="wt-1",
        unit="unit-1",
        code="return 1;",
    )
    acte = {
        "action": "office_executer",
        "champs": {"CHEMIN": "budget.univer"},
        **resultat.to_dict(),
    }

    assert resultat.ok is True
    assert resultat.donnees["statut"] == "NEEDS_CONFIRMATION"
    assert DioumtoukayAgent.fichiers_touches([acte]) == []
    assert DioumtoukayAgent._mutations_non_verifiees([acte]) == []


def test_inspection_du_meme_worktree_valide_une_modification_office():
    mutation = {
        "ok": True,
        "action": "office_executer",
        "champs": {
            "CHEMIN": "budget.univer",
            "WORKTREE_ID": "wt-1",
            "UNIT_ID": "unit-1",
        },
        "donnees": {"statut": "SUCCESS", "fichier": "/app/data/univer/budget.univer"},
    }
    verification = {
        "ok": True,
        "action": "office_inspecter",
        "champs": {
            "CHEMIN": "budget.univer",
            "WORKTREE_ID": "wt-1",
            "UNIT_ID": "unit-1",
        },
        "sortie": "A1: 135000",
        "donnees": {"statut": "SUCCESS", "fichier": "/app/data/univer/budget.univer"},
    }

    assert DioumtoukayAgent._preuve_positive(mutation, verification) is True


def test_inspection_d_un_autre_worktree_ne_valide_pas_la_modification():
    mutation = {
        "ok": True,
        "action": "office_executer",
        "champs": {
            "CHEMIN": "budget.univer",
            "WORKTREE_ID": "wt-1",
            "UNIT_ID": "unit-1",
        },
        "donnees": {"statut": "SUCCESS", "fichier": "/app/data/univer/budget.univer"},
    }
    verification = {
        "ok": True,
        "action": "office_inspecter",
        "champs": {
            "CHEMIN": "budget.univer",
            "WORKTREE_ID": "wt-2",
            "UNIT_ID": "unit-1",
        },
        "sortie": "A1: ancien",
        "donnees": {"statut": "SUCCESS", "fichier": "/app/data/univer/budget.univer"},
    }

    assert DioumtoukayAgent._preuve_positive(mutation, verification) is False
