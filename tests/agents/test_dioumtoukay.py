"""Dioumtoukay agit vraiment — et il dit la vérité sur ce qu'il a fait.

Demande du propriétaire, 02/09/2026 : « il doit être comme claude code entrer
dans mon terminal mon github et travailler sur le projet ». **DEC-0038**.

Ce fichier ne teste **aucun garde-fou** : il n'y en a pas, c'est sa décision, et
un test qui vérifierait qu'un chemin est interdit contredirait cette décision.

Ce qu'il tient est ce qui reste vrai quoi qu'il arrive :

- `test_il_agit_vraiment` — sans lui, l'agent redevient `RepoEngineerAgent`,
  qui analyse et ne touche à rien. C'est exactement ce que le propriétaire ne
  voulait plus.
- `test_un_echec_de_commande_apparait_dans_le_rapport` — un échec fondu dans une
  conclusion rassurante est pire qu'une panne : il ne va pas voir.
- `test_sans_moteur_il_ne_raconte_aucun_travail` — un compte-rendu vide se lit
  comme un travail terminé.
- `test_il_s_arrete` — un agent autonome qui boucle sans fin est la première
  façon dont il devient nuisible.
"""
import pytest

from agents.dioumtoukay.dioumtoukay_agent import (
    TOURS_MAX,
    DioumtoukayAgent,
    analyser_action,
)
from core.actions.journal import JournalDesActions
from core.memory.personnelle import MemoirePersonnelle
from core.memory.recuperation import recuperer
from tools.atelier import Atelier


class ModeleScripte:
    """Un moteur qui rend des actions écrites d'avance.

    L'agent est testé sur ce qu'il FAIT des réponses, pas sur la qualité d'un
    modèle : la seule chose mesurable ici est la boucle.
    """

    def __init__(self, *reponses: str, disponible: bool = True):
        self.reponses = list(reponses)
        self.vues = []
        self._disponible = disponible

    async def is_available(self) -> bool:
        return self._disponible

    async def generate(self, prompt: str, system_prompt: str = None) -> str:
        self.vues.append(prompt)
        return self.reponses.pop(0) if self.reponses else "ACTION: terminer\nCONTENU:\nfini\nFIN"


@pytest.fixture
def bac(tmp_path):
    return tmp_path


def agent(bac, *reponses, disponible=True):
    return DioumtoukayAgent(provider=ModeleScripte(*reponses, disponible=disponible),
                            atelier=Atelier(racine=bac))


# --- Lire l'action demandée ---------------------------------------------------------

class TestLireLAction:
    def test_une_action_simple(self):
        action = analyser_action("ACTION: lister\nCHEMIN: .")

        assert action.nom == "lister"
        assert action.champs["CHEMIN"] == "."

    def test_un_contenu_multiligne_est_garde_entier(self):
        action = analyser_action(
            "ACTION: ecrire\nCHEMIN: a.py\nCONTENU:\nligne un\nligne deux\nFIN")

        assert action.contenu == "ligne un\nligne deux"

    def test_une_action_inconnue_est_refusee(self):
        """Deviner ce qu'il voulait dire lui apprendrait à écrire n'importe quoi."""
        assert analyser_action("ACTION: supprimer_tout\nCHEMIN: /") is None

    def test_une_reponse_sans_action_est_refusee(self):
        assert analyser_action("Je vais regarder ton fichier, un instant.") is None


# --- Il agit -------------------------------------------------------------------------

class TestIlAgitVraiment:
    @pytest.mark.asyncio
    async def test_il_agit_vraiment(self, bac):
        """Le test qui sépare cet agent de `RepoEngineerAgent`, qui ne touche à rien."""
        rendu = await agent(
            bac,
            "ACTION: ecrire\nCHEMIN: note.txt\nCONTENU:\nbonjour\nFIN",
            "ACTION: terminer\nCONTENU:\nfichier ecrit\nFIN",
        ).run("ecris-moi une note")

        assert (bac / "note.txt").read_text() == "bonjour"
        assert rendu["status"] == "success"

    @pytest.mark.asyncio
    async def test_il_lance_vraiment_une_commande(self, bac):
        rendu = await agent(
            bac,
            "ACTION: executer\nCOMMANDE: python -c \"print('depuis le terminal')\"",
            "ACTION: terminer\nCONTENU:\nlance\nFIN",
        ).run("lance une commande")

        assert "depuis le terminal" in rendu["actions"][0]["sortie"]

    @pytest.mark.asyncio
    async def test_il_voit_le_resultat_reel_avant_d_agir_encore(self, bac):
        """Sans le retour, il travaille sur ce qu'il imaginait — c'est toute la
        différence entre agir et raconter."""
        moteur = ModeleScripte(
            "ACTION: executer\nCOMMANDE: python -c \"print('la vraie sortie')\"",
            "ACTION: terminer\nCONTENU:\nvu\nFIN",
        )
        await DioumtoukayAgent(provider=moteur, atelier=Atelier(racine=bac)).run("vas-y")

        assert "la vraie sortie" in moteur.vues[1]

    @pytest.mark.asyncio
    async def test_une_action_illisible_lui_est_renvoyee(self, bac):
        moteur = ModeleScripte(
            "Je vais d'abord reflechir a la meilleure approche.",
            "ACTION: terminer\nCONTENU:\nok\nFIN",
        )
        await DioumtoukayAgent(provider=moteur, atelier=Atelier(racine=bac)).run("vas-y")

        assert "illisible" in moteur.vues[1].lower()


# --- Il dit la vérité ------------------------------------------------------------------

class TestIlDitLaVerite:
    @pytest.mark.asyncio
    async def test_un_echec_de_commande_apparait_dans_le_rapport(self, bac):
        """Un échec fondu dans une conclusion rassurante ne le fait pas aller voir."""
        rendu = await agent(
            bac,
            "ACTION: executer\nCOMMANDE: python -c \"import sys; sys.exit(4)\"",
            "ACTION: terminer\nCONTENU:\nc'est fait\nFIN",
        ).run("lance les tests")

        assert rendu["actions"][0]["ok"] is False
        assert rendu["actions"][0]["code"] == 4
        assert "1 en echec" in rendu["response"]

    @pytest.mark.asyncio
    async def test_sans_moteur_il_ne_raconte_aucun_travail(self, bac):
        rendu = await agent(bac, disponible=False).run("range mes fichiers")

        assert rendu["status"] == "NOT_CONFIGURED"
        assert rendu["actions"] == []
        assert "ollama" in rendu["response"].lower()

    @pytest.mark.asyncio
    async def test_un_moteur_qui_tombe_ne_devient_pas_un_succes(self, bac):
        class MoteurCasse:
            async def is_available(self):
                return True

            async def generate(self, prompt, system_prompt=None):
                raise RuntimeError("le moteur a coupe")

        rendu = await DioumtoukayAgent(provider=MoteurCasse(),
                                       atelier=Atelier(racine=bac)).run("vas-y")

        assert rendu["status"] != "success"
        assert "le moteur a coupe" in rendu["response"]

    @pytest.mark.asyncio
    async def test_il_s_arrete(self, bac):
        """Une boucle sans fin est la première façon dont un agent devient nuisible."""
        boucle = ["ACTION: lister\nCHEMIN: ."] * (TOURS_MAX + 5)

        rendu = await agent(bac, *boucle).run("tourne en rond")

        assert len(rendu["actions"]) == TOURS_MAX
        assert rendu["status"] == "partial"
        assert str(TOURS_MAX) in rendu["response"]


# --- Ce que mini-SWE-agent a fait mesurer ici (06/09/2026) ---------------------------
#
# TOURS_MAX bornait deja les tours, mais rien ne detectait un moteur qui ne
# produit jamais le format demande (il consommait tout le budget sans qu'une
# seule action ne parte), et rien ne bornait le TEMPS (douze tours sur des
# commandes lentes autorisent une session de plusieurs dizaines de minutes).
# Concepts verifies dans le code source de mini-SWE-agent
# (`AgentConfig.max_consecutive_format_errors`, `wall_time_limit_seconds`) —
# jamais son code, jamais un deuxieme systeme de limites : les memes
# compteurs que `TOURS_MAX`, dans la meme boucle.

class TestIlSArreteAussiSurLesReponsesIllisibles:
    @pytest.mark.asyncio
    async def test_illisibles_d_affilee_arretent_avant_tours_max(self, bac):
        from agents.dioumtoukay.dioumtoukay_agent import ILLISIBLES_CONSECUTIVES_MAX

        illisibles = ["n'importe quoi, pas une action"] * ILLISIBLES_CONSECUTIVES_MAX

        rendu = await agent(bac, *illisibles).run("vas-y")

        assert rendu["actions"] == [], "aucune action n'a pu partir d'un moteur illisible"
        assert rendu["status"] == "partial"
        assert "illisible" in rendu["response"].lower()

    @pytest.mark.asyncio
    async def test_une_action_propre_reinitialise_le_compteur(self, bac):
        """Illisible, puis une action propre, puis illisible : deux illisibles
        NON consecutives ne doivent pas declencher l'arret anticipe."""
        from agents.dioumtoukay.dioumtoukay_agent import ILLISIBLES_CONSECUTIVES_MAX

        assert ILLISIBLES_CONSECUTIVES_MAX >= 2, "le test suppose au moins deux"
        rendu = await agent(
            bac,
            "n'importe quoi",
            "ACTION: lister\nCHEMIN: .",
            "n'importe quoi",
            "ACTION: terminer\nCONTENU:\nfini\nFIN",
        ).run("vas-y")

        assert rendu["status"] == "success"
        assert len(rendu["actions"]) == 1


class TestIlSArreteAussiSurLeTemps:
    @pytest.mark.asyncio
    async def test_le_temps_ecoule_arrete_le_travail(self, bac, monkeypatch):
        import agents.dioumtoukay.dioumtoukay_agent as module

        monkeypatch.setattr(module, "DUREE_MAX_SECONDES", 0)
        boucle = ["ACTION: lister\nCHEMIN: ."] * 5

        rendu = await agent(bac, *boucle).run("vas-y")

        assert rendu["actions"] == [], "le temps est deja ecoule avant le premier tour"
        assert rendu["status"] == "partial"
        assert "minute" in rendu["response"].lower()


# --- Le branchement --------------------------------------------------------------------
#
# Sans ces trois-la, tout le reste est decoratif : des mains que rien ne peut
# atteindre depuis l'interface.

def test_l_intention_existe_et_est_confiee_a_un_agent():
    from agents.orchestrator.orchestrator_agent import INTENTIONS
    from apps.backend.config import AGENTS_SPECIALISES

    assert "ATELIER" in INTENTIONS
    assert "ATELIER" in AGENTS_SPECIALISES


def test_l_espace_de_l_interface_mene_a_l_atelier():
    from agents.orchestrator.orchestrator_agent import INTENTION_PAR_ESPACE

    assert INTENTION_PAR_ESPACE["dioumtoukay"] == "ATELIER"


def test_le_chat_appelle_vraiment_l_agent():
    """Le branchement lui-même. Une intention routee vers rien repond a cote."""
    import inspect

    from apps.backend.routers import chat

    assert "dioumtoukay_agent.run(" in inspect.getsource(chat)


@pytest.mark.parametrize("phrase", [
    "range mon dossier telechargements",
    "lance les tests du projet et corrige ce qui casse",
    "va voir mon depot et dis-moi ce qui a change",
    "ouvre mon terminal et fais un git status",
])
def test_ses_phrases_partent_bien_a_l_atelier(phrase):
    """Le repli hors ligne est le SEUL classificateur quand Ollama est eteint —
    et c'est justement la que « corrige le bug du projet » partait ecrire un
    script dans un bac a sable, donc nulle part."""
    from agents.orchestrator.orchestrator_agent import OrchestratorAgent

    classe = OrchestratorAgent.__new__(OrchestratorAgent)

    assert classe._classer_par_mots_cles(phrase) == "ATELIER"


def test_une_phrase_de_son_metier_ne_part_pas_a_l_atelier():
    """« mon projet » est dans la liste ; « fais-moi un devis » ne doit pas y tomber."""
    from agents.orchestrator.orchestrator_agent import OrchestratorAgent

    classe = OrchestratorAgent.__new__(OrchestratorAgent)

    assert classe._classer_par_mots_cles("fais-moi un devis pour 40 m2 de cloison") \
        == "PLAQUISTE"


# --- Ce que la version du 02/09/2026 (après-midi) ajoute ----------------------------
#
# Le propriétaire : « bien améliorer dioumtoukay pour qu'il soit fort dans ses
# travail […] savoir corriger des fail des bug des erreur ». Quatre manques
# mesurés sur la version précédente, un test chacun.

class TestIlCorrigeSansToutReecrire:
    """Le manque le plus coûteux : `ecrire` remplaçait TOUT le fichier."""

    @pytest.mark.asyncio
    async def test_il_corrige_une_ligne_sans_toucher_au_reste(self, bac):
        (bac / "code.py").write_text("def f():\n    return FAUX\n\ndef g():\n    return 2\n")

        await agent(
            bac,
            "ACTION: remplacer\nCHEMIN: code.py\nANCIEN:\n    return FAUX\nFIN\n"
            "NOUVEAU:\n    return 1\nFIN",
            "ACTION: terminer\nCONTENU:\ncorrige\nFIN",
        ).run("corrige le bug")

        assert (bac / "code.py").read_text() == (
            "def f():\n    return 1\n\ndef g():\n    return 2\n")

    @pytest.mark.asyncio
    async def test_un_remplacement_sans_ancien_ne_reecrit_rien(self, bac):
        """Sans le passage visé, écrire reviendrait à écrire au hasard."""
        (bac / "code.py").write_text("intact\n")

        rendu = await agent(
            bac,
            "ACTION: remplacer\nCHEMIN: code.py\nNOUVEAU:\nn'importe quoi\nFIN",
            "ACTION: terminer\nCONTENU:\nfini\nFIN",
        ).run("corrige")

        assert rendu["actions"][0]["ok"] is False
        assert (bac / "code.py").read_text() == "intact\n"

    def test_les_deux_blocs_sont_lus_separement(self):
        action = analyser_action(
            "ACTION: remplacer\nCHEMIN: a.py\nANCIEN:\nvieux\nFIN\nNOUVEAU:\nneuf\nFIN")

        assert action.blocs["ANCIEN"] == "vieux"
        assert action.blocs["NOUVEAU"] == "neuf"

    def test_l_indentation_d_un_bloc_est_du_code_pas_de_la_mise_en_page(self):
        action = analyser_action(
            "ACTION: ecrire\nCHEMIN: a.py\nCONTENU:\ndef f():\n    return 1\nFIN")

        assert action.contenu == "def f():\n    return 1"


class TestIlTrouveAvantDeCorriger:
    @pytest.mark.asyncio
    async def test_il_peut_chercher_dans_les_fichiers(self, bac):
        (bac / "un.py").write_text("def calculer_total():\n    pass\n")

        rendu = await agent(
            bac,
            "ACTION: chercher\nTEXTE: def calculer_total\nCHEMIN: .",
            "ACTION: terminer\nCONTENU:\ntrouve\nFIN",
        ).run("ou est calculer_total ?")

        assert "un.py" in rendu["actions"][0]["sortie"]


class TestIlSaitOuIlEst:
    """Sans repères, le premier tour partait à l'aveugle et dépensait deux ou
    trois actions à découvrir un dossier qu'une seule mesure donne."""

    @pytest.mark.asyncio
    async def test_il_voit_le_contenu_du_dossier_des_le_premier_tour(self, bac):
        (bac / "mon_projet").mkdir()
        moteur = ModeleScripte("ACTION: terminer\nCONTENU:\nvu\nFIN")

        await DioumtoukayAgent(provider=moteur, atelier=Atelier(racine=bac)).run("regarde")

        assert "mon_projet" in moteur.vues[0]

    @pytest.mark.asyncio
    async def test_les_reperes_sont_pris_une_seule_fois(self, bac):
        """Les refaire à chaque tour coûterait trois commandes réelles par tour
        pour redire ce que le journal du travail raconte déjà mieux."""
        journal = JournalDesActions(db_path=str(bac / "j.db"))
        moteur = ModeleScripte(
            "ACTION: lister\nCHEMIN: .",
            "ACTION: lister\nCHEMIN: .",
            "ACTION: terminer\nCONTENU:\nfini\nFIN",
        )
        await DioumtoukayAgent(provider=moteur,
                               atelier=Atelier(racine=bac, journal=journal)).run("vas-y")

        listers = [e for e in journal.dernieres(limite=50) if e.action == "lister"]
        assert len(listers) == 3, "un repere par tour au lieu d'un seul au depart"


class TestLeRapportNommeCeQuiAChange:
    @pytest.mark.asyncio
    async def test_les_fichiers_modifies_sont_nommes(self, bac):
        rendu = await agent(
            bac,
            "ACTION: ecrire\nCHEMIN: note.txt\nCONTENU:\nx\nFIN",
            "ACTION: terminer\nCONTENU:\nfait\nFIN",
        ).run("ecris")

        assert rendu["fichiers_modifies"] == ["note.txt"]
        assert "note.txt" in rendu["response"]

    def test_une_lecture_n_est_pas_une_modification(self):
        touches = DioumtoukayAgent.fichiers_touches([
            {"action": "lire", "ok": True, "champs": {"CHEMIN": "a.py"}}])

        assert touches == []

    def test_une_ecriture_ratee_n_est_pas_une_modification(self):
        """Dire « fichier modifié » d'un fichier intact serait la pire ligne du
        rapport."""
        touches = DioumtoukayAgent.fichiers_touches([
            {"action": "ecrire", "ok": False, "champs": {"CHEMIN": "a.py"}}])

        assert touches == []


class TestIlSeSouvientDeSonTravail:
    @pytest.mark.asyncio
    async def test_un_travail_qui_modifie_est_retenu(self, bac):
        memoire = MemoirePersonnelle(db_path=str(bac / "m.db"))
        await DioumtoukayAgent(
            provider=ModeleScripte("ACTION: ecrire\nCHEMIN: a.py\nCONTENU:\nx\nFIN",
                                   "ACTION: terminer\nCONTENU:\nfait\nFIN"),
            atelier=Atelier(racine=bac), memoire_longue=memoire,
        ).run("ecris a.py")

        assert recuperer(memoire, "Dioumtoukay a.py"), "aucun souvenir du travail"

    @pytest.mark.asyncio
    async def test_une_simple_lecture_ne_remplit_pas_la_memoire(self, bac):
        """Se souvenir d'une lecture ne sert personne."""
        memoire = MemoirePersonnelle(db_path=str(bac / "m.db"))
        (bac / "a.py").write_text("x")
        await DioumtoukayAgent(
            provider=ModeleScripte("ACTION: lire\nCHEMIN: a.py",
                                   "ACTION: terminer\nCONTENU:\nlu\nFIN"),
            atelier=Atelier(racine=bac), memoire_longue=memoire,
        ).run("lis a.py")

        assert recuperer(memoire, "Dioumtoukay") == []

    @pytest.mark.asyncio
    async def test_une_memoire_en_panne_n_emporte_pas_le_rapport(self, bac):
        class MemoireCassee:
            def retenir(self, **kw):
                raise RuntimeError("disque plein")

        rendu = await DioumtoukayAgent(
            provider=ModeleScripte("ACTION: ecrire\nCHEMIN: a.py\nCONTENU:\nx\nFIN",
                                   "ACTION: terminer\nCONTENU:\nfait\nFIN"),
            atelier=Atelier(racine=bac), memoire_longue=MemoireCassee(),
        ).run("ecris")

        assert rendu["status"] == "success"
