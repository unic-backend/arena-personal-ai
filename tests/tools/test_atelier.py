"""Les mains de Dioumtoukay : elles font, et elles laissent une trace.

Ce fichier ne teste **pas** des garde-fous : il n'y en a pas, et c'est la
décision du propriétaire, enregistrée en DEC-0038 après qu'on lui ait présenté
ce qu'elle coûte. Un test qui vérifierait qu'un chemin est interdit
contredirait sa décision.

Ce qu'il tient est ce qui reste vrai quoi qu'il arrive :

- `test_un_code_de_sortie_non_nul_est_un_echec_rapporte` — le défaut mesuré le
  01/09/2026 dans `tools/docker_local.py` : `docker run` rendait un code non
  nul **sans lever**, donc l'échec se déguisait en autre chose.
- `TestToutLaisseUneTrace` — un agent qui agit sans trace ne peut pas être
  corrigé quand il se trompe.
"""
from pathlib import Path

import pytest

from core.actions.journal import JournalDesActions
from tools.atelier import Atelier, Resultat


@pytest.fixture
def bac(tmp_path):
    return tmp_path


@pytest.fixture
def journal(tmp_path):
    return JournalDesActions(db_path=str(tmp_path / "journal.db"))


@pytest.fixture
def atelier(bac, journal):
    return Atelier(racine=bac, journal=journal)


# --- Les fichiers -----------------------------------------------------------------

class TestLesFichiers:
    def test_ecrire_puis_relire(self, atelier):
        atelier.ecrire("projet/notes.txt", "bonjour")

        assert atelier.lire("projet/notes.txt").sortie == "bonjour"

    def test_ecrire_cree_les_dossiers_manquants(self, atelier, bac):
        atelier.ecrire("a/b/c/fichier.txt", "x")

        assert (bac / "a" / "b" / "c" / "fichier.txt").exists()

    def test_lister_rend_dossiers_et_fichiers(self, atelier):
        atelier.ecrire("dossier/un.txt", "x")
        atelier.ecrire("dossier/sous/deux.txt", "y")

        sortie = atelier.lister("dossier").sortie

        assert "f  un.txt" in sortie
        assert "d  sous" in sortie

    def test_deplacer_range_vraiment(self, atelier, bac):
        atelier.ecrire("vrac/photo.jpg", "x")

        atelier.deplacer("vrac/photo.jpg", "photos/2026/photo.jpg")

        assert (bac / "photos" / "2026" / "photo.jpg").exists()
        assert not (bac / "vrac" / "photo.jpg").exists()

    def test_un_fichier_absent_se_dit(self, atelier):
        resultat = atelier.lire("nexiste-pas.txt")

        assert resultat.ok is False
        assert "Lecture impossible" in resultat.message

    def test_un_chemin_absolu_est_suivi(self, atelier, tmp_path):
        """« entrer dans mes fichiers du pc » : la racine est un point de
        depart, pas une prison. DEC-0038."""
        ailleurs = tmp_path.parent / f"hors-{tmp_path.name}.txt"
        try:
            atelier.ecrire(str(ailleurs), "hors de la racine")

            assert ailleurs.read_text() == "hors de la racine"
        finally:
            ailleurs.unlink(missing_ok=True)


# --- Le terminal --------------------------------------------------------------------

class TestLeTerminal:
    def test_une_commande_rend_sa_sortie(self, atelier):
        resultat = atelier.executer(["python", "-c", "print('depuis le terminal')"])

        assert resultat.ok
        assert "depuis le terminal" in resultat.sortie
        assert resultat.code == 0

    def test_un_code_de_sortie_non_nul_est_un_echec_rapporte(self, atelier):
        """Le défaut du 01/09/2026 : un code non nul SANS exception, donc un
        échec qui se déguise en autre chose."""
        resultat = atelier.executer(["python", "-c", "import sys; sys.exit(3)"])

        assert resultat.ok is False
        assert resultat.code == 3

    def test_l_erreur_de_la_commande_est_rendue_telle_quelle(self, atelier):
        resultat = atelier.executer(
            ["python", "-c", "import sys; print('probleme', file=sys.stderr)"])

        assert "probleme" in resultat.erreur

    def test_une_commande_introuvable_se_nomme(self, atelier):
        resultat = atelier.executer(["commande-qui-nexiste-pas-du-tout"])

        assert resultat.ok is False
        assert "introuvable" in resultat.message

    def test_une_commande_bloquee_est_arretee_et_dite(self, atelier):
        resultat = atelier.executer(
            ["python", "-c", "import time; time.sleep(30)"], delai=0.5)

        assert resultat.ok is False
        assert "arretee" in resultat.message

    def test_aucune_commande_ne_lance_rien(self, atelier):
        assert atelier.executer([]).ok is False

    def test_la_commande_est_une_liste_jamais_du_shell(self, atelier, bac):
        """Un nom de fichier avec un `;` ne doit pas devenir deux commandes.

        Ce n'est pas une restriction de ce qu'il peut lancer — c'est ce qui
        empeche un accident sur un nom de fichier.
        """
        temoin = bac / "ne-doit-pas-exister.txt"

        atelier.executer(["python", "-c", "print('x')", f"; touch {temoin}"])

        assert not temoin.exists()


# --- Git ---------------------------------------------------------------------------

def test_git_tourne_dans_le_depot(atelier):
    """Rien n'est interdit ici, `push` compris — DEC-0038."""
    racine_projet = str(Path(__file__).resolve().parent.parent.parent)

    resultat = atelier.executer(["git", "rev-parse", "--is-inside-work-tree"],
                                dossier=racine_projet)

    assert resultat.ok
    assert resultat.sortie.strip() == "true"


# --- La trace ------------------------------------------------------------------------

class TestToutLaisseUneTrace:
    """Ce n'est pas une autorisation à demander, c'est un compte-rendu à lire.

    Un agent qui agit sans trace ne peut pas être corrigé quand il se trompe,
    et c'est le propriétaire — pas l'agent — qui doit pouvoir dire ce qui
    s'est passé chez lui.
    """

    def test_chaque_action_est_journalisee(self, atelier, journal):
        atelier.ecrire("un.txt", "x")
        atelier.lire("un.txt")
        atelier.deplacer("un.txt", "deux.txt")
        atelier.lister(".")
        atelier.executer(["python", "-c", "print(1)"])

        actions = [e.action for e in journal.dernieres(limite=20)]

        for attendu in ("ecrire", "lire", "deplacer", "lister", "executer"):
            assert attendu in actions, f"« {attendu} » n'a laisse aucune trace"

    def test_un_echec_est_journalise_comme_un_echec(self, atelier, journal):
        atelier.executer(["python", "-c", "import sys; sys.exit(2)"])

        derniere = journal.dernieres(limite=1)[0]

        assert derniere.resultat == "FAILED"

    def test_la_trace_dit_qui_a_agi(self, atelier, journal):
        atelier.ecrire("un.txt", "x")

        assert journal.dernieres(limite=1)[0].outil == "dioumtoukay"

    def test_un_journal_en_panne_n_empeche_pas_le_travail(self, bac):
        """Il se plaint ; il ne bloque pas."""
        class JournalCasse:
            def enregistrer(self, action):
                raise RuntimeError("disque plein")

        atelier = Atelier(racine=bac, journal=JournalCasse())

        assert atelier.ecrire("un.txt", "x").ok is True

    def test_sans_journal_le_travail_se_fait_quand_meme(self, bac):
        atelier = Atelier(racine=bac)

        assert atelier.ecrire("un.txt", "x").ok is True


# --- Ce qui est rendu -----------------------------------------------------------------

def test_une_sortie_tres_longue_est_coupee_et_le_dit(atelier):
    """Une sortie tronquée en silence se lit comme une sortie complète — et
    c'est ainsi qu'on conclut faux sur un test qui a échoué plus bas."""
    from tools.atelier.atelier import SORTIE_MAX

    resultat = atelier.executer(
        ["python", "-c", f"print('a' * {SORTIE_MAX + 5000})"])

    assert "coupé" in resultat.sortie
    assert len(resultat.sortie) < SORTIE_MAX + 200


def test_le_resultat_est_transportable(atelier):
    corps = atelier.ecrire("un.txt", "x").to_dict()

    assert set(corps) == {"ok", "message", "sortie", "erreur", "code"}


def test_le_resultat_par_defaut_ne_pretend_rien():
    assert Resultat(False, "rien").code is None


def test_la_racine_par_defaut_est_le_dossier_courant():
    assert Atelier().racine == Path.cwd()


# --- Corriger sans tout réécrire -------------------------------------------------------
#
# La correction la plus importante de cette version. Avant, `ecrire` était la
# seule façon de modifier un fichier, et elle remplace TOUT : pour changer une
# ligne dans un fichier de six cents, le modèle devait les réécrire toutes de
# mémoire — et un modèle local de 14 milliards de paramètres ne restitue pas six
# cents lignes sans en abîmer une.

class TestRemplacerUnPassage:
    def test_seul_le_passage_vise_change(self, atelier, bac):
        atelier.ecrire("code.py", "avant\nLA LIGNE FAUSSE\napres\n")

        atelier.remplacer("code.py", "LA LIGNE FAUSSE", "la ligne juste")

        assert (bac / "code.py").read_text() == "avant\nla ligne juste\napres\n"

    def test_un_passage_introuvable_ne_touche_a_rien(self, atelier, bac):
        """Le modèle a cité de mémoire un texte absent du fichier. Écrire quand
        même mettrait la correction au mauvais endroit."""
        atelier.ecrire("code.py", "le vrai contenu\n")

        resultat = atelier.remplacer("code.py", "un texte qui n'y est pas", "x")

        assert resultat.ok is False
        assert "introuvable" in resultat.message
        assert (bac / "code.py").read_text() == "le vrai contenu\n"

    def test_un_passage_ambigu_est_refuse_avec_ce_qu_il_faut_faire(self, atelier, bac):
        """Rien ne dit lequel il visait. En choisir un serait deviner, et le
        rapport annoncerait une réussite."""
        atelier.ecrire("code.py", "total = 0\ntotal = 0\n")

        resultat = atelier.remplacer("code.py", "total = 0", "total = 1")

        assert resultat.ok is False
        assert "2 fois" in resultat.message
        assert (bac / "code.py").read_text() == "total = 0\ntotal = 0\n"

    def test_l_indentation_du_code_est_preservee(self, atelier, bac):
        atelier.ecrire("code.py", "def f():\n    return 1\n")

        atelier.remplacer("code.py", "    return 1", "    return 2")

        assert (bac / "code.py").read_text() == "def f():\n    return 2\n"

    def test_un_fichier_absent_se_dit(self, atelier):
        assert atelier.remplacer("nexiste-pas.py", "a", "b").ok is False

    def test_remplacer_laisse_une_trace(self, atelier, journal):
        atelier.ecrire("code.py", "a")
        atelier.remplacer("code.py", "a", "b")

        assert journal.dernieres(limite=1)[0].action == "remplacer"


# --- Trouver avant de corriger ---------------------------------------------------------

class TestChercher:
    def test_il_trouve_le_fichier_et_la_ligne(self, atelier):
        atelier.ecrire("un/deux.py", "x = 1\ndef calculer_total():\n    pass\n")

        sortie = atelier.chercher("def calculer_total").sortie

        assert "deux.py" in sortie
        assert ":2:" in sortie

    def test_rien_trouve_est_une_reponse_pas_un_echec(self, atelier):
        """« ce mot n'est nulle part » est exactement ce qu'il fallait savoir."""
        atelier.ecrire("un.py", "rien de special")

        resultat = atelier.chercher("introuvable_nulle_part")

        assert resultat.ok is True
        assert "aucune ligne" in resultat.message

    def test_la_recherche_est_litterale(self, atelier):
        """Un nom de fonction contient des points et des parenthèses ; les
        traiter comme un motif ferait trouver n'importe quoi."""
        atelier.ecrire("un.py", "a.b(c)\naxbyc\n")

        assert len(atelier.chercher("a.b(c)").sortie.splitlines()) == 1

    def test_sans_texte_il_ne_cherche_rien(self, atelier):
        assert atelier.chercher("").ok is False

    def test_le_repli_trouve_la_meme_chose_que_grep(self, atelier, bac):
        """Une machine sans `grep` ne doit pas rendre Dioumtoukay aveugle."""
        atelier.ecrire("un/deux.py", "x = 1\nle motif cherche\n")

        lignes = Atelier._chercher_ici_meme("le motif cherche", bac, 100)

        assert len(lignes) == 1
        assert lignes[0].endswith(":2:le motif cherche")

    def test_le_repli_saute_les_binaires_sans_tomber(self, atelier, bac):
        (bac / "image.png").write_bytes(b"\x89PNG\x00\x01\x02")
        atelier.ecrire("un.py", "le motif cherche")

        assert len(Atelier._chercher_ici_meme("le motif cherche", bac, 100)) == 1

    def test_chercher_laisse_une_trace(self, atelier, journal):
        atelier.chercher("quoi que ce soit")

        assert journal.dernieres(limite=1)[0].action == "chercher"


# --- La coupe garde la fin -------------------------------------------------------------

def test_une_sortie_coupee_garde_le_debut_ET_la_fin(atelier):
    """`pytest` écrit son verdict sur ses DERNIÈRES lignes. Ne garder que le
    début revenait à couper systématiquement la réponse à la question posée."""
    from tools.atelier.atelier import SORTIE_MAX

    programme = (f"print('DEBUT'); print('.' * {SORTIE_MAX + 5000}); "
                 "print('3 failed, 12 passed')")

    sortie = atelier.executer(["python", "-c", programme]).sortie

    assert "DEBUT" in sortie
    assert "3 failed, 12 passed" in sortie, "le verdict a ete coupe"
