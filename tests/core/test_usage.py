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


# --- Le plafond par requete : ce qu'il vaut vraiment -------------------------
# Trouve le 12/09/2026 en diagnostic de l'etape 10 : `CLOUD_COUT_MAX_PAR_REQUETE`
# (`AI_MAX_COST_PER_REQUEST=0.02`) etait declare dans `config.py` ET documente
# dans `.env.example`, et lu par ZERO ligne de code. Un reglage qui se lit comme
# une protection sans en etre une est pire qu'un reglage absent.


def test_sans_tarif_le_plafond_par_requete_se_declare_non_verifiable(tmp_path):
    """La seule reponse honnete : le cout d'une requete n'est pas calculable.

    `TARIFS` est vide par defaut, et le cout depend des jetons de SORTIE,
    inconnus avant la reponse. Dire « respecte » serait faux ; afficher
    `0 $` de depense serait pire.
    """
    compteur = CompteurUsage(cout_max_par_requete=0.02)
    compteur.enregistrer(Appel(fournisseur="groq", modele="inconnu",
                               jetons_entree=10_000, jetons_sortie=10_000))

    resume = compteur.resume()
    assert resume["cout_max_par_requete"] == 0.02, "le reglage doit etre visible"
    assert resume["controle_cout_par_requete"] == "NON_VERIFIABLE"
    assert resume["depassements_par_requete_aujourdhui"] == 0, (
        "un appel dont le cout est inconnu n'est ni un depassement ni un respect")
    assert resume["cout_aujourdhui"] is None, "`None` n'est pas `0.0`"


def test_a_zero_le_plafond_par_requete_est_un_choix_ecrit(tmp_path):
    compteur = CompteurUsage(cout_max_par_requete=0.0)

    assert compteur.resume()["controle_cout_par_requete"] == "DESACTIVE"
    assert compteur.resume()["cout_max_par_requete"] is None


def test_avec_un_tarif_le_depassement_est_constate_apres_coup(tmp_path, monkeypatch):
    """Avec un tarif reel, le depassement devient mesurable — mais APRES la
    reponse, jamais avant : personne ne connait les jetons de sortie d'une
    reponse qui n'a pas encore ete ecrite. L'etat le dit tel quel."""
    import core.models.usage as usage

    monkeypatch.setitem(usage.TARIFS, "modele-cher", {"entree": 1000.0, "sortie": 3000.0})
    compteur = CompteurUsage(cout_max_par_requete=0.02)
    # Les tarifs sont en dollars par MILLION de jetons : 10k entree + 10k
    # sortie a 1000/3000 font 10 + 30 = 40 $, tres au-dela des 0,02 $.
    compteur.enregistrer(Appel(fournisseur="groq", modele="modele-cher",
                               jetons_entree=10_000, jetons_sortie=10_000))
    # Et un appel reellement bon marche : 1 + 1 jeton, soit 0,004 $, sous le
    # plafond — il ne doit pas compter comme un depassement.
    compteur.enregistrer(Appel(fournisseur="groq", modele="modele-cher",
                               jetons_entree=1, jetons_sortie=1))

    resume = compteur.resume()
    assert resume["controle_cout_par_requete"] == "MESURE_APRES_COUP"
    assert resume["depassements_par_requete_aujourdhui"] == 1, (
        f"un seul des deux appels depasse le plafond : {resume}")
    assert resume["cout_aujourdhui"] is not None, "avec un tarif, le cout se calcule"
