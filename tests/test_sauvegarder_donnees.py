"""La sauvegarde protège-t-elle vraiment, ou copie-t-elle juste un fichier ?

VOLET « ARENA en ligne », phase 3.2. `data/database/memory.db` porte tout —
mémoire, journal, tâches, entités — et rien ne le sauvegardait jusqu'ici. Le
volume du paquet déployable (phase 3.1) protège d'un rebuild du conteneur ;
il ne protège ni d'un fichier corrompu, ni d'une écriture interrompue, ni d'un
`rm -rf data`.

`test_une_copie_corrompue_n_est_jamais_declaree_ok` est le test qui porte la
garantie centrale : une sauvegarde qui ne se restaure pas n'est pas une
sauvegarde, quel que soit ce que son nom de fichier prétend.
"""
import sqlite3
import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE / "scripts"))

from sauvegarder_donnees import sauvegarder  # noqa: E402


def base_reelle(chemin: Path) -> Path:
    """Une vraie base SQLite, avec une table et une ligne — pas un fichier vide."""
    connexion = sqlite3.connect(str(chemin))
    connexion.execute("CREATE TABLE souvenirs (id INTEGER PRIMARY KEY, texte TEXT)")
    connexion.execute("INSERT INTO souvenirs (texte) VALUES ('234 plaques BA13')")
    connexion.commit()
    connexion.close()
    return chemin


# --- Le test qui porte la garantie centrale --------------------------------------

def test_une_copie_corrompue_n_est_jamais_declaree_ok(tmp_path):
    """Une copie tronquée doit être détectée, jamais rapportée comme un succès.

    `sqlite3.Connection` est un type C immuable, hors de portée d'un
    monkeypatch : la fonction de copie est donc remplacée à l'appel, exactement
    comme `sonde=` dans `scripts/doctor.py`.
    """
    source = base_reelle(tmp_path / "memory.db")
    dossier = tmp_path / "sauvegardes"

    def copie_tronquee(source_, cible):
        # Simule une copie interrompue : le fichier existe, il est inutilisable.
        cible.write_bytes(b"pas du sqlite")

    rapport = sauvegarder(source, dossier, copier=copie_tronquee)

    assert rapport.ok is False
    assert not list(dossier.glob("*.db")), "la copie corrompue est restée sur le disque"


# --- Ce qu'une sauvegarde réussie garantit -----------------------------------------

def test_la_sauvegarde_se_relit_et_contient_les_memes_donnees(tmp_path):
    source = base_reelle(tmp_path / "memory.db")

    rapport = sauvegarder(source, tmp_path / "sauvegardes")

    assert rapport.ok is True
    assert rapport.chemin is not None and rapport.chemin.exists()
    connexion = sqlite3.connect(str(rapport.chemin))
    ligne = connexion.execute("SELECT texte FROM souvenirs").fetchone()
    assert ligne == ("234 plaques BA13",), "la copie ne contient pas les données source"


def test_un_succes_sans_chemin_ne_se_construit_pas():
    import pytest
    from sauvegarder_donnees import RapportSauvegarde

    with pytest.raises(ValueError):
        RapportSauvegarde(ok=True, message="pretendu succes")


def test_source_absente_est_rapportee_jamais_une_exception(tmp_path):
    rapport = sauvegarder(tmp_path / "n-existe-pas.db", tmp_path / "sauvegardes")

    assert rapport.ok is False
    assert "n-existe-pas.db" in rapport.message


# --- La rétention garde un nombre fini de copies -----------------------------------

def test_la_retention_garde_les_plus_recentes_pas_les_plus_anciennes(tmp_path):
    source = base_reelle(tmp_path / "memory.db")
    dossier = tmp_path / "sauvegardes"
    dossier.mkdir()
    # Trois fausses sauvegardes déjà en place, plus vieilles que celle à venir.
    for horodatage in ("20260101-000000", "20260102-000000", "20260103-000000"):
        base_reelle(dossier / f"memory-{horodatage}.db")

    rapport = sauvegarder(source, dossier, garder=2)

    restantes = sorted(p.name for p in dossier.glob("*.db"))
    assert len(restantes) == 2, f"la rétention n'a pas réduit à 2 : {restantes}"
    assert "20260101-000000" not in " ".join(restantes), "la plus ancienne aurait dû partir"
    assert len(rapport.supprimees) == 2


def test_une_retention_de_zero_ne_garde_aucune_ancienne_sauvegarde(tmp_path):
    source = base_reelle(tmp_path / "memory.db")
    dossier = tmp_path / "sauvegardes"
    dossier.mkdir()
    base_reelle(dossier / "memory-20260101-000000.db")

    rapport = sauvegarder(source, dossier, garder=0)

    # garder=0 retire tout SAUF celle qui vient d'être écrite (le glob la voit aussi) :
    # la règle documentée est « garder N après celle-ci ».
    restantes = list(dossier.glob("*.db"))
    assert len(restantes) == 1
    assert restantes[0] == rapport.chemin
