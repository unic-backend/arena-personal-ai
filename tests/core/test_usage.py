"""Le compteur d'usage cloud : ce qu'il compte doit survivre, et rester exact.

Deux defauts confirmes contre l'audit (f7f0478437a633668e569fd3a367980a5139e49a,
etape 10), tous les deux dans `CompteurUsage` sans `db_path` (le seul mode qui
existait avant ce correctif) :

1. **Rien ne survit a un redemarrage.** Le compte du jour vivait dans
   `self.appels`, une simple liste Python — un redemarrage du serveur
   remettait tout a zero, rouvrant un budget deja epuise juste avant l'arret.
2. **Le cache d'affichage n'est pas le compte reel.** `APPELS_GARDES` (500)
   bornait aussi bien le cache que le calcul du jour : au-dela de 500 appels
   dans la MEME journee, les plus anciens du jour disparaissaient du compte
   avant meme que le plafond ne soit atteint — un proprietaire configurant un
   grand quota (`AI_MAX_CLOUD_REQUESTS_PER_DAY` > 500) ne voyait jamais son
   propre plafond se fermer.

`CompteurUsage(db_path=...)` regle les deux : le compte du jour se lit dans
SQLite, jamais dans la liste bornee.
"""
from core.models.usage import Appel, CompteurUsage


def test_sans_base_le_compteur_reste_purement_en_memoire(tmp_path):
    """Comportement d'avant, inchange : personne ne doit dependre d'une base."""
    compteur = CompteurUsage(requetes_par_jour=200, budget_journalier=1.0)

    for _ in range(3):
        compteur.enregistrer(Appel(fournisseur="groq", modele="m"))

    assert compteur.requetes_aujourdhui == 3
    assert compteur.db_path is None


def test_le_plafond_survit_a_un_redemarrage(tmp_path):
    """Le defaut confirme : sans base, ce test echoue (la 2e instance repart a zero)."""
    base = str(tmp_path / "usage.db")
    avant_redemarrage = CompteurUsage(
        requetes_par_jour=1, budget_journalier=0, db_path=base)
    avant_redemarrage.enregistrer(Appel(fournisseur="groq", modele="m"))

    assert avant_redemarrage.verdict().autorise is False, (
        "le plafond doit deja etre ferme avant le redemarrage")

    # « Redemarrage » : une toute nouvelle instance, pointee sur la meme base
    # — exactement ce que fait `apps/backend/runtime.py` au prochain lancement
    # du processus.
    apres_redemarrage = CompteurUsage(
        requetes_par_jour=1, budget_journalier=0, db_path=base)

    verdict = apres_redemarrage.verdict()
    assert verdict.autorise is False, (
        "le redemarrage a rouvert un budget deja epuise avant l'arret")
    assert "plafond atteint" in verdict.raison
    assert apres_redemarrage.requetes_aujourdhui == 1


def test_le_compte_du_jour_reste_exact_au_dela_du_cache_borne(tmp_path, monkeypatch):
    """Un grand quota ne doit jamais se rouvrir parce que le cache d'affichage a tourne."""
    import core.models.usage as usage

    monkeypatch.setattr(usage, "APPELS_GARDES", 5)
    base = str(tmp_path / "usage.db")
    # Quota volontairement plus grand que le cache borne : c'est exactement
    # le cas ou l'ancien code se trompait.
    compteur = CompteurUsage(requetes_par_jour=8, budget_journalier=0, db_path=base)

    for _ in range(8):
        compteur.enregistrer(Appel(fournisseur="groq", modele="m"))

    assert compteur.requetes_aujourdhui == 8, (
        "le compte du jour ne doit pas etre tronque par le cache d'affichage")
    assert compteur.verdict().autorise is False, "le plafond de 8 doit etre atteint"
    assert len(compteur.appels) == 5, "le cache d'affichage, lui, reste borne"


def test_sans_tarif_le_cout_persiste_reste_inconnu(tmp_path):
    """`None` n'est pas `0.0`, meme relu depuis la base."""
    base = str(tmp_path / "usage.db")
    compteur = CompteurUsage(db_path=base)
    compteur.enregistrer(Appel(fournisseur="groq", modele="inconnu",
                               jetons_entree=10, jetons_sortie=5))

    relu = CompteurUsage(db_path=base)
    assert relu.cout_aujourdhui is None


def test_la_base_ne_grossit_pas_sans_fin(tmp_path):
    """Les jours trop anciens sont purges — jamais aujourd'hui."""
    import sqlite3

    base = str(tmp_path / "usage.db")
    compteur = CompteurUsage(db_path=base)
    with sqlite3.connect(base) as connexion:
        connexion.execute(
            "INSERT INTO usage_cloud_appels "
            "(fournisseur, modele, jour, horodatage, classement, "
            " jetons_entree, jetons_sortie, secondes, repli, succes) "
            "VALUES ('groq', 'm', '2020-01-01', '2020-01-01T00:00:00', '', "
            " NULL, NULL, NULL, 0, 1)")
        connexion.commit()

    compteur.enregistrer(Appel(fournisseur="groq", modele="m"))

    with sqlite3.connect(base) as connexion:
        restants = connexion.execute(
            "SELECT COUNT(*) FROM usage_cloud_appels WHERE jour = '2020-01-01'"
        ).fetchone()[0]
    assert restants == 0, "un jour vieux de plusieurs annees ne doit pas s'accumuler"


def test_des_enregistrements_reellement_concurrents_ne_s_ecrasent_pas(tmp_path):
    """La meme discipline que le test de collision d'upload (etape 8) : de vrais threads."""
    import concurrent.futures

    base = str(tmp_path / "usage.db")
    compteur = CompteurUsage(requetes_par_jour=0, budget_journalier=0, db_path=base)

    def _un_appel(index):
        compteur.enregistrer(Appel(fournisseur="groq", modele=f"m{index}"))

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executeur:
        list(executeur.map(_un_appel, range(20)))

    assert compteur.requetes_aujourdhui == 20, (
        "un enregistrement concurrent ne doit ni se perdre ni doubler")
