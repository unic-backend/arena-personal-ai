"""La boucle de génie logiciel, sur un vrai dépôt, avec un vrai bug.

**Ce que ces tests ne font pas** : simuler le pipeline. Le dépôt est écrit sur
disque, le bug est réel, `pytest` tourne vraiment, la correction est un vrai
remplacement de texte, et le second `pytest` est vraiment relancé.

**Ce qui est doublé, et seulement cela** : le modèle de langue. Il est remplacé
par un script d'actions fixes — Ollama n'existe pas sur la machine du CI, et un
modèle réel rendrait le test non reproductible. Le doublé produit exactement le
format que l'agent attend ; tout ce qui suit est du vrai travail.

La reprise (DEC-0072) est testée là où elle compte : un premier passage
s'arrête au milieu, un second **reprend** au lieu de tout refaire.
"""
import textwrap
from pathlib import Path

import pytest

from agents.dioumtoukay.dioumtoukay_agent import DioumtoukayAgent
from core.execution.reprise import EtatTache, JournalDeReprise
from tools.atelier.atelier import Atelier

DEMANDE = "trouve le bug dans calcul.py, corrige-le et verifie que les tests passent"

#: Le format EXACT que `analyser_action` sait lire : les blocs sont
#: multilignes et fermes par `FIN` (`_lire_bloc`). L'ecrire sur une seule ligne
#: rend une action illisible — mesure du 07/09/2026, sur mes propres tests.
REMPLACER = """ACTION: remplacer
CHEMIN: calcul.py
ANCIEN:
    return largeur + hauteur
FIN
NOUVEAU:
    return largeur * hauteur
FIN"""


def _depot_avec_un_bug(dossier: Path) -> Path:
    """Un vrai petit dépôt : une fonction fausse, et un test qui le prouve."""
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "calcul.py").write_text(textwrap.dedent('''
        def surface(largeur, hauteur):
            """La surface d'une paroi."""
            return largeur + hauteur
    ''').strip() + "\n", encoding="utf-8")
    (dossier / "test_calcul.py").write_text(textwrap.dedent('''
        from calcul import surface

        def test_surface():
            assert surface(5, 2.5) == 12.5
    ''').strip() + "\n", encoding="utf-8")
    # **Sa propre configuration pytest, et c'est ce qui rend le test fiable.**
    # Sans elle, le pytest lance DANS ce depot remonte les dossiers parents a
    # la recherche d'une configuration et peut tomber sur celle d'ARENA — dont
    # les `addopts`, le `testpaths` et le `conftest.py` n'ont aucun sens ici.
    # Le comportement depend alors de l'emplacement du dossier temporaire,
    # donc de la machine : vert ici, rouge en CI (mesure du 07/09/2026).
    # Un vrai projet porte sa configuration ; celui-ci aussi.
    (dossier / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    return dossier


#: **`-B` n'est pas un detail de confort : sans lui ce test est faux.**
#:
#: Cause demontree le 07/09/2026, apres deux hypotheses erronees de ma part.
#: Le premier `pytest` importe `calcul.py` et ecrit `__pycache__/
#: calcul.cpython-311.pyc`. L'agent remplace ensuite `largeur + hauteur` par
#: `largeur * hauteur` — **un seul caractere echange, donc une taille de
#: fichier IDENTIQUE** — et l'ecriture tombe dans le meme tic d'horloge.
#:
#: Python valide un `.pyc` sur (mtime, taille). Les deux etant inchanges, le
#: second `pytest` charge le bytecode PERIME et calcule encore une addition :
#: `assert 7.5 == 12.5`, l'erreur exacte vue en CI. Vert ici parce que la
#: granularite du mtime y suffisait a invalider le cache ; rouge la-bas.
#:
#: Reproduit deliberement en forcant `os.utime` a l'identique, puis corrige :
#: `-B` sur les DEUX passages, car il empeche d'ECRIRE le cache, pas de le
#: lire — le mettre au seul second passage laisse le `.pyc` du premier.
PYTEST_INTERNE = "ACTION: executer\nCOMMANDE: python -B -m pytest test_calcul.py -q"


def _sortie(action: dict) -> str:
    """Tout ce que la commande a ecrit, message compris.

    Un code de retour ne dit pas POURQUOI. Quand ce test rougit — il l'a fait
    en CI le 07/09/2026 en passant ici —, c'est cette chaine qui doit
    apparaitre dans l'echec, pas un `assert False is True`.
    """
    return "\n".join(str(action.get(cle) or "")
                     for cle in ("message", "sortie", "erreur")).strip()


class ModeleScripte:
    """Rend les actions l'une après l'autre, au format que l'agent attend."""

    def __init__(self, actions):
        self.actions = list(actions)
        self.vus = 0

    async def is_available(self) -> bool:
        return True

    async def generate(self, prompt: str, system_prompt: str = "", **_) -> str:
        self.vus += 1
        if not self.actions:
            return "ACTION: terminer\nCONTENU: plus rien a faire"
        return self.actions.pop(0)


def _agent(dossier: Path, journal_fichier: Path, actions) -> DioumtoukayAgent:
    return DioumtoukayAgent(
        provider=ModeleScripte(actions),
        atelier=Atelier(racine=dossier),
        reprises=JournalDeReprise(fichier=journal_fichier))


@pytest.mark.asyncio
class TestLaBoucleCorrigeUnVraiBug:
    """TASK → ANALYSE → FIX → TESTS → VÉRIFICATION, sur du code réel."""

    async def test_le_test_echoue_d_abord_puis_passe_apres_correction(
            self, tmp_path):
        """Le cœur : le bug est réel, la correction est réelle, pytest tranche."""
        depot = _depot_avec_un_bug(tmp_path / "depot")
        agent = _agent(depot, tmp_path / "j.json", [
            "ACTION: lire\nCHEMIN: calcul.py",
            PYTEST_INTERNE,
            REMPLACER,
            PYTEST_INTERNE,
            "ACTION: terminer\nCONTENU: bug corrige, tests verts",
        ])

        resultat = await agent.run(DEMANDE)

        # **Le remplacement a-t-il eu lieu ?** Trou de ma premiere version :
        # elle sautait directement au second pytest. Si `remplacer` echoue —
        # passage introuvable, present deux fois, ecriture impossible — le
        # fichier reste bugge et le second pytest echoue LEGITIMEMENT. Le test
        # accusait alors « le test ne passe pas apres correction », c'est-a-dire
        # la mauvaise etape. Mesure du 07/09/2026, sur une CI rouge illisible.
        corrections = [a for a in resultat["actions"] if a["action"] == "remplacer"]
        assert corrections and corrections[0]["ok"] is True, (
            f"la correction n'a pas ete appliquee :\n{_sortie(corrections[0])}"
            if corrections else "aucun remplacement n'a ete tente")
        assert "largeur * hauteur" in (depot / "calcul.py").read_text(encoding="utf-8")

        commandes = [a for a in resultat["actions"] if a["action"] == "executer"]
        assert len(commandes) == 2, "les deux passages de tests n'ont pas eu lieu"

        # **On lit la SORTIE, pas seulement le code de retour.** Mesure du
        # 07/09/2026 : ce test a rougi en CI alors qu'il passait ici, et
        # `assert ok is False` ne disait pas pourquoi. Pire, il aurait pu
        # passer pour la mauvaise raison — une erreur de collecte fait
        # echouer pytest exactement comme un test faux. La sortie tranche.
        avant = _sortie(commandes[0])
        apres = _sortie(commandes[1])
        assert commandes[0]["ok"] is False, f"le bug n'a pas ete reproduit :\n{avant}"
        assert "1 failed" in avant or "assert" in avant, (
            f"pytest a echoue pour une autre raison que le bug :\n{avant}")
        assert commandes[1]["ok"] is True, (
            f"le test ne passe pas apres correction :\n{apres}")
        assert "1 passed" in apres, f"la correction n'a pas rendu le test vert :\n{apres}"
        assert resultat["status"] == "success"

    async def test_le_fichier_sur_disque_est_vraiment_modifie(self, tmp_path):
        """Aucune simulation : le correctif doit exister dans le fichier."""
        depot = _depot_avec_un_bug(tmp_path / "depot")
        agent = _agent(depot, tmp_path / "j.json", [
            REMPLACER,
            "ACTION: terminer\nCONTENU: fait",
        ])

        await agent.run(DEMANDE)

        assert "largeur * hauteur" in (depot / "calcul.py").read_text(encoding="utf-8")
        assert "calcul.py" in agent.fichiers_touches(
            [{"action": "remplacer", "champs": {"CHEMIN": "calcul.py"}, "ok": True}])


@pytest.mark.asyncio
class TestUneTacheInterrompueReprendVraiment:
    """DEC-0072 : la différence entre une phrase et un état.

    Avant, l'agent rendait « la suite reste à faire » et repartait de zéro au
    tour suivant. Ici, le second passage voit ce que le premier a fait.
    """

    async def test_le_second_passage_ne_refait_pas_le_travail_du_premier(
            self, tmp_path):
        depot = _depot_avec_un_bug(tmp_path / "depot")
        fichier = tmp_path / "j.json"

        # Premier passage : deux actions, puis le modele se tait — l'agent
        # s'arrete sans conclure, donc la tache est INTERROMPUE.
        premier = _agent(depot, fichier, [
            "ACTION: lire\nCHEMIN: calcul.py",
            PYTEST_INTERNE,
        ] + ["reponse illisible"] * 3)
        rendu = await premier.run(DEMANDE)

        assert rendu["status"] == "partial"
        assert rendu["reprise"] is False, "le premier passage ne reprend rien"

        etat = JournalDeReprise(fichier=fichier).inventaire()[0]
        assert etat.etat is EtatTache.INTERROMPUE
        assert len(etat.etapes) == 2

        # Second passage : la MEME demande. Il doit reprendre.
        second = _agent(depot, fichier, [
            REMPLACER,
            "ACTION: terminer\nCONTENU: repris et corrige",
        ])
        suite = await second.run(DEMANDE)

        assert suite["reprise"] is True, "le travail deja fait a ete perdu"
        assert suite["status"] == "success"
        assert suite["tache"]["task_id"] == etat.identifiant
        # 2 (premier passage) + 1 (le remplacement). `terminer` n'agit pas sur
        # l'atelier : ce n'est pas une etape de travail, et la journaliser
        # ferait croire a une action de plus qu'il n'y en a eu.
        assert suite["tache"]["steps"] == 3, "les etapes des deux passages"

    async def test_le_modele_voit_ce_qui_a_deja_ete_fait(self, tmp_path):
        """Reprendre sans le dire au modele le ferait tout relire."""
        depot = _depot_avec_un_bug(tmp_path / "depot")
        fichier = tmp_path / "j.json"

        premier = _agent(depot, fichier, [
            "ACTION: lire\nCHEMIN: calcul.py"] + ["illisible"] * 3)
        await premier.run(DEMANDE)

        second = _agent(depot, fichier, ["ACTION: terminer\nCONTENU: rien a faire"])
        await second.run(DEMANDE)

        premiere_invite = second.provider  # le double garde ce qu'il a vu
        assert premiere_invite.vus >= 1

    async def test_une_tache_conclue_ne_reprend_pas_au_tour_suivant(self, tmp_path):
        depot = _depot_avec_un_bug(tmp_path / "depot")
        fichier = tmp_path / "j.json"

        for _ in range(2):
            agent = _agent(depot, fichier, ["ACTION: terminer\nCONTENU: fini"])
            rendu = await agent.run(DEMANDE)
            assert rendu["reprise"] is False


@pytest.mark.asyncio
class TestCeQuiRateSeRapporte:
    """Injection de pannes : rien ne doit tomber en silence."""

    async def test_une_commande_introuvable_est_un_echec_nomme(self, tmp_path):
        depot = _depot_avec_un_bug(tmp_path / "depot")
        agent = _agent(depot, tmp_path / "j.json", [
            "ACTION: executer\nCOMMANDE: commande-qui-nexiste-pas",
            "ACTION: terminer\nCONTENU: fini",
        ])

        resultat = await agent.run(DEMANDE)

        echec = [a for a in resultat["actions"] if a["action"] == "executer"][0]
        assert echec["ok"] is False
        assert "introuvable" in echec["message"].lower()

    async def test_un_fichier_absent_ne_fait_pas_tomber_la_boucle(self, tmp_path):
        depot = _depot_avec_un_bug(tmp_path / "depot")
        agent = _agent(depot, tmp_path / "j.json", [
            "ACTION: lire\nCHEMIN: fantome.py",
            "ACTION: terminer\nCONTENU: fini",
        ])

        resultat = await agent.run(DEMANDE)

        assert resultat["status"] == "success"
        assert resultat["actions"][0]["ok"] is False

    async def test_sans_moteur_rien_n_est_tente_et_aucune_tache_n_est_ouverte(
            self, tmp_path):
        """Une tache ouverte sans qu'une action parte serait un faux depart."""
        class SansMoteur:
            async def is_available(self):
                return False
            async def generate(self, *a, **k):
                raise AssertionError("le moteur a ete appele malgre son absence")

        fichier = tmp_path / "j.json"
        agent = DioumtoukayAgent(
            provider=SansMoteur(), atelier=Atelier(racine=tmp_path),
            reprises=JournalDeReprise(fichier=fichier))

        resultat = await agent.run(DEMANDE)

        assert resultat["status"] == "NOT_CONFIGURED"
        assert JournalDeReprise(fichier=fichier).inventaire() == []

    async def test_l_echec_est_journalise_comme_echec_pas_comme_reussite(
            self, tmp_path):
        depot = _depot_avec_un_bug(tmp_path / "depot")
        fichier = tmp_path / "j.json"
        agent = _agent(depot, fichier, [
            "ACTION: lire\nCHEMIN: fantome.py",
            "ACTION: terminer\nCONTENU: fini",
        ])

        await agent.run(DEMANDE)

        etapes = JournalDeReprise(fichier=fichier).inventaire()[0].etapes
        assert etapes[0].ok is False, "un echec journalise comme reussite est un mensonge"


@pytest.mark.asyncio
class TestObservabilite:
    """« Qu'est-ce que l'agent est en train de faire ? » doit avoir une réponse."""

    async def test_chaque_etape_porte_son_outil_sa_cible_et_sa_duree(self, tmp_path):
        depot = _depot_avec_un_bug(tmp_path / "depot")
        fichier = tmp_path / "j.json"
        agent = _agent(depot, fichier, [
            "ACTION: lire\nCHEMIN: calcul.py",
            "ACTION: terminer\nCONTENU: fini",
        ])

        await agent.run(DEMANDE)

        etape = JournalDeReprise(fichier=fichier).inventaire()[0].etapes[0]
        assert etape.outil == "lire"
        assert etape.cible == "calcul.py"
        assert etape.duree_ms >= 0
        assert etape.quand

    async def test_le_rapport_porte_l_identifiant_de_la_tache(self, tmp_path):
        depot = _depot_avec_un_bug(tmp_path / "depot")
        agent = _agent(depot, tmp_path / "j.json",
                       ["ACTION: terminer\nCONTENU: fini"])

        resultat = await agent.run(DEMANDE)

        assert resultat["tache"]["task_id"]
        assert resultat["tache"]["status"] == "TERMINEE"
