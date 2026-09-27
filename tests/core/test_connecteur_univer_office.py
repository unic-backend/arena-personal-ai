"""Connecteur Univer Office : contrat, sécurité et cycle de staging."""

from pathlib import Path

import yaml

from core.actions.resultat import Statut
from core.connectors.univer_office import (
    TAILLE_CODE_MAX,
    ConnecteurUniverOffice,
)


def _fake_univer(tmp_path: Path) -> Path:
    script = tmp_path / "univer-fake"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "if '--version' in sys.argv:\n"
        "    print('univer-cli 0.5.0')\n"
        "    raise SystemExit(0)\n"
        "print(json.dumps({'ok': True}))\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def test_sonde_execute_reellement_le_binaire(tmp_path):
    connecteur = ConnecteurUniverOffice(
        dossier=tmp_path / "workspace",
        dossier_rendus=tmp_path / "rendus",
        binaire=str(_fake_univer(tmp_path)),
        racines_import=[tmp_path],
    )

    sante = connecteur.sonder()

    assert sante.etat.value == "OPERATIONAL"
    assert "0.5.0" in sante.message


def test_source_reseau_refusee_avant_univer(tmp_path):
    connecteur = ConnecteurUniverOffice(
        dossier=tmp_path / "workspace",
        binaire=str(_fake_univer(tmp_path)),
        racines_import=[tmp_path],
    )

    resultat = connecteur._executer(
        connecteur.capacites()["importer"],
        source="https://exemple.test/devis.xlsx",
        nom="devis",
    )

    assert resultat.statut is Statut.ECHEC
    assert "réseau" in resultat.message


def test_un_fichier_univer_ne_peut_pas_sortir_du_workspace(tmp_path):
    connecteur = ConnecteurUniverOffice(
        dossier=tmp_path / "workspace",
        binaire=str(_fake_univer(tmp_path)),
        racines_import=[tmp_path],
    )
    dehors = tmp_path.parent / "dehors.univer"

    resultat = connecteur._executer(
        connecteur.capacites()["statut"],
        fichier=str(dehors),
    )

    assert resultat.statut is Statut.ECHEC
    assert "espace Univer" in resultat.message


def test_code_facade_trop_long_refuse_avant_execution(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    fichier = workspace / "x.univer"
    fichier.write_bytes(b"x")
    connecteur = ConnecteurUniverOffice(
        dossier=workspace,
        binaire=str(_fake_univer(tmp_path)),
        racines_import=[tmp_path],
    )

    resultat = connecteur._executer(
        connecteur.capacites()["executer"],
        fichier=str(fichier),
        worktree="wt-1",
        unit="unit-1",
        code="x" * (TAILLE_CODE_MAX + 1),
    )

    assert resultat.statut is Statut.ECHEC
    assert "trop long" in resultat.message


def test_import_reussi_supprime_seulement_le_staging_pwa(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    staging = workspace / "imports"
    staging.mkdir(parents=True)
    source = staging / "budget.xlsx"
    source.write_bytes(b"xlsx")
    connecteur = ConnecteurUniverOffice(
        dossier=workspace,
        dossier_rendus=tmp_path / "rendus",
        binaire=str(_fake_univer(tmp_path)),
        racines_import=[tmp_path],
    )

    def lancer(args, **_kwargs):
        cible = Path(args[1])
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_bytes(b"sqlite-univer")
        return {"unitId": "unit-1"}, None

    monkeypatch.setattr(connecteur, "_lancer", lancer)

    resultat = connecteur._executer(
        connecteur.capacites()["importer"],
        source=str(source),
        nom="budget",
        type="sheet",
    )

    assert resultat.statut is Statut.SUCCES
    assert not source.exists()
    assert Path(resultat.preuve).is_file()
    assert resultat.detail["staging_supprime"] is True


def test_import_reussi_ne_supprime_pas_une_source_deja_durable(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    source = tmp_path / "durable.xlsx"
    source.write_bytes(b"xlsx")
    connecteur = ConnecteurUniverOffice(
        dossier=workspace,
        dossier_rendus=tmp_path / "rendus",
        binaire=str(_fake_univer(tmp_path)),
        racines_import=[tmp_path],
    )

    def lancer(args, **_kwargs):
        cible = Path(args[1])
        cible.parent.mkdir(parents=True, exist_ok=True)
        cible.write_bytes(b"sqlite-univer")
        return {"unitId": "unit-1"}, None

    monkeypatch.setattr(connecteur, "_lancer", lancer)

    resultat = connecteur._executer(
        connecteur.capacites()["importer"],
        source=str(source),
        nom="budget",
        type="sheet",
    )

    assert resultat.statut is Statut.SUCCES
    assert source.exists()
    assert resultat.detail["staging_supprime"] is False


def test_politique_ne_laisse_pas_execute_et_merge_partir_sans_confirmation():
    politique = yaml.safe_load(
        Path("config/permissions_services.yaml").read_text(encoding="utf-8")
    )
    office = politique["services"]["office_univer"]

    assert office["read"]["decision"] == "ALLOWED"
    assert office["document"]["interrupteur"] == "WRITE_FILES"
    assert office["execute"]["decision"] == "CONFIRMATION"
    assert office["execute"]["interrupteur"] == "EXECUTE_COMMANDS"
    assert office["merge"]["decision"] == "CONFIRMATION"
    assert office["destroy"]["decision"] == "CONFIRMATION"
