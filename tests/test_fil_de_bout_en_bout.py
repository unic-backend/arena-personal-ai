"""Une phrase du propriétaire, et tout ce qu'elle a causé — en un seul endroit.

**Le trou mesuré le 20/09/2026** : `/api/actions` savait déjà répondre « quels
OUTILS ont tourné pour cette phrase ? », parce que le journal des actions porte
le fil de la demande. Mais « quel MODÈLE y a répondu, par quel FOURNISSEUR, en
combien de temps ? » n'avait aucune réponse : les statistiques de routage
n'écrivaient pas ce fil. Les deux moitiés de l'histoire vivaient dans deux
magasins que rien ne reliait.

Trois tests portent l'étape :

- `test_un_passage_porte_le_fil_de_la_demande_sans_qu_on_le_lui_passe` : le
  mécanisme est le même que celui du journal des actions, donc **aucun appelant
  n'a eu à changer**. Si ça cesse d'être vrai, chaque site d'appel devient une
  occasion d'oublier.
- `test_le_fil_relie_les_outils_ET_les_modeles` : c'est exactement ce qui
  manquait.
- `test_une_base_ecrite_avant_la_colonne_se_relit_sans_rien_inventer` : les
  anciennes lignes gardent `None`, ce qui est vrai. Leur attribuer une demande
  serait une trace fabriquée.
"""
import sqlite3

import pytest
from fastapi.testclient import TestClient

from apps.backend import main
from apps.backend import security as securite
from core.models.statistiques import Passage, StatistiquesRoutage
from core.observabilite.fil import nouveau_fil

CLE_DE_TEST = "cle-de-test"


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setattr(securite, "USMAN_API_KEY", CLE_DE_TEST)
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.fixture
def entetes() -> dict:
    return {"Authorization": f"Bearer {CLE_DE_TEST}"}


@pytest.fixture
def stats(tmp_path):
    return StatistiquesRoutage(db_path=str(tmp_path / "memoire.db"))


def _passage(**kw):
    defauts = {"type_tache": "CHAT", "fournisseur": "groq",
               "modele": "openai/gpt-oss-120b", "succes": True}
    defauts.update(kw)
    return Passage(**defauts)


# --- Le fil descend tout seul ---------------------------------------------------

def test_un_passage_porte_le_fil_de_la_demande_sans_qu_on_le_lui_passe(stats):
    """Même mécanisme que le journal des actions : `fil_courant` en valeur par
    défaut. Aucun site d'appel n'a eu à changer — donc aucun ne peut oublier."""
    with nouveau_fil("demande-abc"):
        passage = _passage()

    assert passage.requete == "demande-abc"
    assert passage.to_dict()["requete"] == "demande-abc"


def test_hors_demande_le_fil_reste_inconnu(stats):
    """Une tâche de fond, une ligne de commande, un test : `None` se lit
    « hors demande ». Un identifiant fabriqué se lirait « demande introuvable »."""
    assert _passage().requete is None


def test_le_fil_retrouve_exactement_les_appels_de_cette_demande(stats):
    with nouveau_fil("demande-abc"):
        stats.enregistrer(_passage(modele="pour-abc"))
    with nouveau_fil("demande-xyz"):
        stats.enregistrer(_passage(modele="pour-xyz"))
    stats.enregistrer(_passage(modele="hors-demande"))

    retenus = stats.passages(fil="demande-abc")

    assert [p.modele for p in retenus] == ["pour-abc"]


def test_un_fil_sans_appel_rend_une_liste_vide_pas_une_erreur(stats):
    assert stats.passages(fil="jamais-vu") == []


def test_les_deux_filtres_se_combinent(stats):
    with nouveau_fil("demande-abc"):
        stats.enregistrer(_passage(type_tache="CHAT", modele="chat"))
        stats.enregistrer(_passage(type_tache="MONTAGE", modele="montage"))

    retenus = stats.passages(fil="demande-abc", type_tache="MONTAGE")

    assert [p.modele for p in retenus] == ["montage"]


# --- Une base d'avant la colonne -------------------------------------------------

def test_une_base_ecrite_avant_la_colonne_se_relit_sans_rien_inventer(tmp_path):
    """`ADD COLUMN` est la seule migration nécessaire, et les anciennes lignes
    gardent `None` — ce qui est vrai : elles n'ont jamais eu de fil."""
    chemin = tmp_path / "ancienne.db"
    connexion = sqlite3.connect(chemin)
    connexion.execute("""
        CREATE TABLE routage_passages (
            horodatage TEXT NOT NULL, type_tache TEXT NOT NULL,
            fournisseur TEXT NOT NULL, modele TEXT NOT NULL,
            succes INTEGER NOT NULL, repli INTEGER NOT NULL,
            secondes REAL, classement TEXT NOT NULL)
    """)
    connexion.execute(
        "INSERT INTO routage_passages VALUES ('2026-01-01', 'CHAT', 'groq', "
        "'vieux-modele', 1, 0, 1.0, 'PUBLIC')")
    connexion.commit()
    connexion.close()

    stats = StatistiquesRoutage(db_path=str(chemin))
    anciens = stats.passages()

    assert [p.modele for p in anciens] == ["vieux-modele"]
    assert anciens[0].requete is None
    # Et elle n'est attribuee a AUCUNE demande : ce serait une trace fabriquee.
    assert stats.passages(fil="n-importe-quoi") == []


def test_la_colonne_est_ajoutee_a_une_base_existante(tmp_path):
    chemin = tmp_path / "ancienne.db"
    connexion = sqlite3.connect(chemin)
    connexion.execute("""
        CREATE TABLE routage_passages (
            horodatage TEXT NOT NULL, type_tache TEXT NOT NULL,
            fournisseur TEXT NOT NULL, modele TEXT NOT NULL,
            succes INTEGER NOT NULL, repli INTEGER NOT NULL,
            secondes REAL, classement TEXT NOT NULL)
    """)
    connexion.commit()
    connexion.close()

    stats = StatistiquesRoutage(db_path=str(chemin))
    with nouveau_fil("apres-migration"):
        assert stats.enregistrer(_passage()) is True

    assert [p.requete for p in stats.passages()] == ["apres-migration"]


# --- La route qui réunit les deux moitiés ----------------------------------------

class TestLaRouteDuFil:
    @pytest.fixture(autouse=True)
    def _brancher(self, monkeypatch, stats):
        from apps.backend.routers import actions as routeur_actions

        monkeypatch.setattr(routeur_actions, "statistiques_routage", stats)
        self.stats = stats

    def test_le_fil_relie_les_outils_ET_les_modeles(self, client, entetes):
        """C'est exactement ce qui manquait : les deux moitiés d'une même
        histoire, sous un seul identifiant.

        Le journal des actions est le vrai, pas un double : c'est justement le
        raccord entre les deux magasins qui est éprouvé ici.
        """
        with nouveau_fil("demande-abc"):
            self.stats.enregistrer(_passage(modele="pour-abc", secondes=1.25))

        corps = client.get("/api/observability/fil/demande-abc",
                           headers=entetes).json()

        assert corps["connu"] is True
        assert [m["modele"] for m in corps["modeles"]] == ["pour-abc"]
        assert corps["resume"]["appels_modele"] == 1
        assert corps["resume"]["secondes_modeles"] == 1.25
        # Le rendu des actions a la MEME forme que `/api/actions`.
        assert isinstance(corps["actions"], list)

    def test_une_demande_inconnue_n_est_pas_une_erreur(self, client, entetes):
        """Un 404 laisserait croire à une panne là où la vérité est « rien
        n'a été enregistré sous ce fil »."""
        reponse = client.get("/api/observability/fil/jamais-vu", headers=entetes)

        assert reponse.status_code == 200
        corps = reponse.json()
        assert corps["connu"] is False
        assert corps["modeles"] == []
        # `None`, jamais `0.0` : aucun appel n'a rendu de duree.
        assert corps["resume"]["secondes_modeles"] is None

    def test_la_route_exige_la_cle(self, client):
        assert client.get("/api/observability/fil/abc").status_code == 401

    def test_un_repli_et_un_echec_se_comptent(self, client, entetes):
        with nouveau_fil("demande-abc"):
            self.stats.enregistrer(_passage(succes=False, fournisseur="groq"))
            self.stats.enregistrer(_passage(repli=True, fournisseur="local"))

        corps = client.get("/api/observability/fil/demande-abc",
                           headers=entetes).json()

        assert corps["resume"]["echecs_modele"] == 1
        assert corps["resume"]["replis"] == 1
