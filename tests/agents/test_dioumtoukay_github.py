"""Dioumtoukay ouvre une Pull Request et lit l'état de CI, via le connecteur
GitHub (DEC-0073) — jusqu'ici, seul `git` en shell nu.

**La garde qui compte le plus** : `ouvrir_pr` passe par la même confirmation
que n'importe quelle autre écriture externe. Dioumtoukay ne peut pas la
contourner en l'appelant — il hérite du même `connecteur.executer()` que
`/connectors/github/...` appellerait.
"""
import pytest

from agents.dioumtoukay.dioumtoukay_agent import DioumtoukayAgent
from core.actions.resultat import ResultatAction, a_confirmer, echec, succes
from tools.atelier import Atelier


class ModeleScripte:
    def __init__(self, *reponses: str):
        self.reponses = list(reponses)

    async def is_available(self) -> bool:
        return True

    async def generate(self, prompt: str, system_prompt: str = None) -> str:
        return self.reponses.pop(0) if self.reponses else "ACTION: terminer\nCONTENU:\nfini\nFIN"


class FauxConnecteurGitHub:
    """Un `Connecteur.executer()` factice : rend d'avance ce qu'on lui donne,
    et garde une trace de chaque appel — jamais le vrai réseau."""

    def __init__(self, resultat: ResultatAction):
        self.resultat = resultat
        self.appels = []

    def executer(self, capacite, **parametres):
        self.appels.append((capacite, parametres))
        return self.resultat


@pytest.fixture
def bac(tmp_path):
    return tmp_path


def agent(bac, reponses, connecteur_github=None, depot_github_defaut=None):
    return DioumtoukayAgent(
        provider=ModeleScripte(*reponses),
        atelier=Atelier(racine=bac),
        connecteur_github=connecteur_github,
        depot_github_defaut=depot_github_defaut,
    )


# --- espace GitHub distant : le PC peut etre eteint -------------------------------

class TestEspaceGitHubDistant:
    def test_reperes_disent_qu_un_serveur_sans_git_doit_utiliser_github(self, bac):
        a = agent(
            bac,
            [],
            connecteur_github=FauxConnecteurGitHub(
                succes("x", "x", "ok", preuve="x")
            ),
            depot_github_defaut="unic-backend/arena-personal-ai",
        )

        reperes = a._reperes("corrige le projet")

        assert "AUCUN checkout git local" in reperes
        assert "github_branche_creer" in reperes
        assert "unic-backend/arena-personal-ai" in reperes

    @pytest.mark.asyncio
    async def test_liste_le_depot_distant_par_defaut(self, bac):
        connecteur = FauxConnecteurGitHub(succes(
            "lister", "unic-backend/arena-personal-ai",
            "2 entree(s) dans apps.", preuve="2",
            entrees=[{"chemin": "apps/backend"}, {"chemin": "apps/pwa"}],
        ))
        a = agent(
            bac,
            [
                "ACTION: github_lister\nREF: main\nCHEMIN: apps",
                "ACTION: terminer\nCONTENU:\nfini\nFIN",
            ],
            connecteur_github=connecteur,
            depot_github_defaut="unic-backend/arena-personal-ai",
        )

        await a.run("explore le depot")

        assert connecteur.appels[0] == (
            "lister",
            {
                "depot": "unic-backend/arena-personal-ai",
                "chemin": "apps",
                "ref": "main",
            },
        )

    @pytest.mark.asyncio
    async def test_lit_puis_ecrit_sur_le_depot_par_defaut(self, bac):
        connecteur = FauxConnecteurGitHub(succes(
            "ecrire_fichier", "unic-backend/arena-personal-ai",
            "apps/pwa/src/App.tsx mis a jour sur fix-mobile.",
            preuve="commit-2", sha="blob-2",
        ))
        a = agent(
            bac,
            [
                "ACTION: github_lire\nREF: fix-mobile\nCHEMIN: apps/pwa/src/App.tsx",
                "ACTION: github_ecrire\nBRANCHE: fix-mobile\n"
                "CHEMIN: apps/pwa/src/App.tsx\nSHA: blob-1\n"
                "MESSAGE: fix: mobile\nCONTENU:\nnouveau contenu\nFIN",
                "ACTION: terminer\nCONTENU:\nfini\nFIN",
            ],
            connecteur_github=connecteur,
            depot_github_defaut="unic-backend/arena-personal-ai",
        )

        resultat = await a.run("corrige le frontend depuis mon telephone")

        assert resultat["status"] == "success"
        assert connecteur.appels[0] == (
            "lire_fichier",
            {
                "depot": "unic-backend/arena-personal-ai",
                "chemin": "apps/pwa/src/App.tsx",
                "ref": "fix-mobile",
            },
        )
        assert connecteur.appels[1] == (
            "ecrire_fichier",
            {
                "depot": "unic-backend/arena-personal-ai",
                "chemin": "apps/pwa/src/App.tsx",
                "branche": "fix-mobile",
                "contenu": "nouveau contenu",
                "sha_attendu": "blob-1",
                "message": "fix: mobile",
            },
        )

    @pytest.mark.asyncio
    async def test_cree_une_branche_distante_sans_depot_repete(self, bac):
        connecteur = FauxConnecteurGitHub(succes(
            "creer_branche", "unic-backend/arena-personal-ai",
            "Branche fix-mobile creee.", preuve="abc",
        ))
        a = agent(
            bac,
            [
                "ACTION: github_branche_creer\nNOM: fix-mobile\nDEPUIS: main",
                "ACTION: terminer\nCONTENU:\nfini\nFIN",
            ],
            connecteur_github=connecteur,
            depot_github_defaut="unic-backend/arena-personal-ai",
        )

        await a.run("cree une branche distante")

        assert connecteur.appels[0] == (
            "creer_branche",
            {
                "depot": "unic-backend/arena-personal-ai",
                "nom_branche": "fix-mobile",
                "depuis": "main",
            },
        )

    @pytest.mark.asyncio
    async def test_ecriture_distante_exige_branche_et_chemin(self, bac):
        connecteur = FauxConnecteurGitHub(succes(
            "x", "x", "ne doit jamais etre lu", preuve="x",
        ))
        a = agent(
            bac,
            [
                "ACTION: github_ecrire\nCHEMIN: a.py\nCONTENU:\nx\nFIN",
                "ACTION: terminer\nCONTENU:\nfini\nFIN",
            ],
            connecteur_github=connecteur,
            depot_github_defaut="o/r",
        )

        resultat = await a.run("modifie le fichier")

        assert connecteur.appels == []
        assert resultat["actions"][0]["ok"] is False
        assert "BRANCHE" in resultat["actions"][0]["message"]


# --- ouvrir_pr ------------------------------------------------------------------

class TestOuvrirPR:
    @pytest.mark.asyncio
    async def test_en_attente_de_confirmation_est_rapporte_comme_tel(self, bac):
        """La forme normale : le connecteur repond A_CONFIRMER, rien n'est
        parti, et Dioumtoukay le dit — il ne prétend pas avoir ouvert la PR."""
        connecteur = FauxConnecteurGitHub(a_confirmer(
            "creer_pull_request", "o/r",
            "Pret : Ouvre une Pull Request, en brouillon. Confirme avec l'identifiant abc123."))
        a = agent(bac, [
            "ACTION: ouvrir_pr\nDEPOT: o/r\nTETE: fix-bug\nBASE: main\n"
            "TITRE: Corrige le bug\nCONTENU:\nle detail\nFIN",
            "ACTION: terminer\nCONTENU:\nfini, en attente de confirmation\nFIN",
        ], connecteur_github=connecteur)

        resultat = await a.run("ouvre une PR pour mon correctif")

        assert connecteur.appels == [("creer_pull_request", {
            "depot": "o/r", "titre": "Corrige le bug", "tete": "fix-bug",
            "base": "main", "corps": "le detail"})]
        rendu = resultat["actions"][0]
        assert rendu["ok"] is True
        assert "abc123" in rendu["sortie"] or "abc123" in rendu["message"]

    @pytest.mark.asyncio
    async def test_sans_depot_ou_tete_rien_natteint_le_connecteur(self, bac):
        connecteur = FauxConnecteurGitHub(succes("x", "x", "ne doit jamais etre lu", preuve="x"))
        a = agent(bac, [
            "ACTION: ouvrir_pr\nTITRE: Sans depot ni tete",
            "ACTION: terminer\nCONTENU:\nfini\nFIN",
        ], connecteur_github=connecteur)

        resultat = await a.run("ouvre une PR")

        assert connecteur.appels == []
        assert resultat["actions"][0]["ok"] is False

    @pytest.mark.asyncio
    async def test_sans_connecteur_branche(self, bac):
        a = agent(bac, [
            "ACTION: ouvrir_pr\nDEPOT: o/r\nTETE: fix",
            "ACTION: terminer\nCONTENU:\nfini\nFIN",
        ], connecteur_github=None)

        resultat = await a.run("ouvre une PR")

        assert "n'est pas branche" in resultat["actions"][0]["message"]

    @pytest.mark.asyncio
    async def test_un_refus_de_permission_est_rapporte_pas_masque(self, bac):
        connecteur = FauxConnecteurGitHub(echec("creer_pull_request", "o/r",
                                                "GitHub refuse la creation (422) : rien a fusionner"))
        a = agent(bac, [
            "ACTION: ouvrir_pr\nDEPOT: o/r\nTETE: rien-de-nouveau",
            "ACTION: terminer\nCONTENU:\nfini\nFIN",
        ], connecteur_github=connecteur)

        resultat = await a.run("ouvre une PR")

        assert resultat["actions"][0]["ok"] is False
        assert "rien a fusionner" in resultat["actions"][0]["message"]


# --- etat_ci ---------------------------------------------------------------------

class TestEtatCI:
    @pytest.mark.asyncio
    async def test_le_resume_arrive_dans_le_rapport(self, bac):
        connecteur = FauxConnecteurGitHub(succes(
            "etat_ci", "o/r", "CI sur abc123 : echec (2 verification(s)).",
            preuve="echec", resume="echec",
            verifications=[{"nom": "tests", "statut": "completed", "conclusion": "failure"}]))
        a = agent(bac, [
            "ACTION: etat_ci\nDEPOT: o/r\nREF: abc123",
            "ACTION: terminer\nCONTENU:\nfini\nFIN",
        ], connecteur_github=connecteur)

        resultat = await a.run("la CI est verte ?")

        assert connecteur.appels == [("etat_ci", {"depot": "o/r", "ref": "abc123"})]
        assert "echec" in resultat["response"]

    @pytest.mark.asyncio
    async def test_sans_depot_ou_ref_rien_natteint_le_connecteur(self, bac):
        connecteur = FauxConnecteurGitHub(succes("x", "x", "ne doit jamais etre lu", preuve="x"))
        a = agent(bac, [
            "ACTION: etat_ci\nDEPOT: o/r",
            "ACTION: terminer\nCONTENU:\nfini\nFIN",
        ], connecteur_github=connecteur)

        await a.run("la CI est verte ?")

        assert connecteur.appels == []


# --- La garde qui compte le plus --------------------------------------------------

def test_une_ecriture_github_reussie_compte_comme_fichier_modifie():
    rendu = [{
        "action": "github_ecrire",
        "ok": True,
        "champs": {"CHEMIN": "apps/backend/config.py"},
    }]

    assert DioumtoukayAgent.fichiers_touches(rendu) == ["apps/backend/config.py"]


def test_ouvrir_pr_et_etat_ci_ne_modifient_rien_dans_le_rapport():
    """Une PR en attente de confirmation n'a encore RIEN change sur le disque
    ni sur GitHub : elle ne doit jamais apparaitre parmi les fichiers modifies."""
    from agents.dioumtoukay.dioumtoukay_agent import ACTIONS_QUI_MODIFIENT
    assert "ouvrir_pr" not in ACTIONS_QUI_MODIFIENT
    assert "etat_ci" not in ACTIONS_QUI_MODIFIENT
