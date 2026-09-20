"""Écrire un journal sans jamais le laisser à moitié écrit.

Ce module a été extrait le 20/09/2026 : trois journaux durables du dépôt
(reprise de tâches, projets de production, file de travaux) portaient la même
dizaine de lignes recopiées. Trois copies d'une règle, c'est trois endroits où
la corriger.

Le test qui porte l'étape est
`test_l_ecriture_passe_par_un_remplacement_atomique` : une écriture directe
interrompue laisserait un journal illisible — dans le seul moment où il sert.
"""
import json

import pytest

from core.execution.journal_disque import ecrire_json_atomique, lire_json


def test_l_ecriture_passe_par_un_remplacement_atomique(tmp_path, monkeypatch):
    """Le fichier final n'est jamais ouvert en écriture : il est REMPLACÉ.

    Le test le prouve en surveillant `os.replace` — sans lui, une écriture
    coupée en deux laisserait un JSON tronqué.
    """
    import core.execution.journal_disque as module

    remplacements = []
    vrai_replace = module.os.replace

    def espion(source, cible):
        remplacements.append((str(source), str(cible)))
        return vrai_replace(source, cible)

    monkeypatch.setattr(module.os, "replace", espion)
    cible = tmp_path / "journal.json"

    assert ecrire_json_atomique(cible, {"a": 1}) is True
    assert len(remplacements) == 1
    assert remplacements[0][1] == str(cible)
    assert json.loads(cible.read_text(encoding="utf-8")) == {"a": 1}


def test_le_fichier_provisoire_vit_dans_le_meme_dossier(tmp_path, monkeypatch):
    """`os.replace` n'est atomique qu'à l'intérieur d'un même système de fichiers.

    Un temporaire dans `/tmp` casserait la garantie sans qu'aucun test ne le
    voie, parce que le résultat resterait correct sur une machine où les deux
    dossiers partagent le même disque.
    """
    import core.execution.journal_disque as module

    dossiers = []
    vrai = module.tempfile.NamedTemporaryFile

    def espion(*args, **kw):
        dossiers.append(kw.get("dir"))
        return vrai(*args, **kw)

    monkeypatch.setattr(module.tempfile, "NamedTemporaryFile", espion)
    cible = tmp_path / "sous" / "journal.json"
    ecrire_json_atomique(cible, {"a": 1})

    assert dossiers == [str(cible.parent)]


def test_le_dossier_est_cree_au_besoin(tmp_path):
    cible = tmp_path / "pas" / "encore" / "la" / "journal.json"

    assert ecrire_json_atomique(cible, {"a": 1}) is True
    assert cible.is_file()


def test_une_valeur_non_serialisable_ne_fait_pas_perdre_tout_le_journal(tmp_path):
    """Refuser l'écriture pour une seule valeur exotique perdrait TOUT le reste."""
    cible = tmp_path / "journal.json"

    assert ecrire_json_atomique(cible, {"ok": 1, "bizarre": object()}) is True
    relu = json.loads(cible.read_text(encoding="utf-8"))
    assert relu["ok"] == 1
    assert isinstance(relu["bizarre"], str)


def test_une_ecriture_impossible_se_rapporte_sans_lever(tmp_path, monkeypatch):
    """Disque plein, dossier en lecture seule : le travail continue."""
    import core.execution.journal_disque as module

    def refuse(*args, **kw):
        raise OSError("No space left on device")

    monkeypatch.setattr(module.tempfile, "NamedTemporaryFile", refuse)

    assert ecrire_json_atomique(tmp_path / "journal.json", {"a": 1}) is False


# --- Lecture ---------------------------------------------------------------------

def test_un_fichier_absent_rend_le_defaut(tmp_path):
    assert lire_json(tmp_path / "rien.json") == {}
    assert lire_json(tmp_path / "rien.json", {"vide": True}) == {"vide": True}


def test_un_json_casse_rend_le_defaut_sans_lever(tmp_path):
    cible = tmp_path / "journal.json"
    cible.write_text("{ceci n'est pas du json", encoding="utf-8")

    assert lire_json(cible) == {}


def test_un_json_valide_mais_pas_un_objet_rend_le_defaut(tmp_path):
    """Une liste au lieu d'un objet : lisible, mais pas ce qu'on attendait.

    La rendre telle quelle ferait planter l'appelant sur un `.get()` bien plus
    loin, avec une trace qui ne dirait pas d'où vient le problème.
    """
    cible = tmp_path / "journal.json"
    cible.write_text("[1, 2, 3]", encoding="utf-8")

    assert lire_json(cible) == {}


def test_ce_qui_est_ecrit_se_relit(tmp_path):
    cible = tmp_path / "journal.json"
    ecrire_json_atomique(cible, {"travaux": [{"id": "t1"}]})

    assert lire_json(cible) == {"travaux": [{"id": "t1"}]}


@pytest.mark.parametrize("contenu", [{}, {"a": []}, {"a": {"b": None}}])
def test_un_aller_retour_ne_change_rien(tmp_path, contenu):
    cible = tmp_path / "journal.json"
    ecrire_json_atomique(cible, contenu)

    assert lire_json(cible) == contenu
