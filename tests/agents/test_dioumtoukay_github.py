"""Dioumtoukay ouvre une Pull Request et lit l'état de CI, via le connecteur
GitHub (DEC-0073) — jusqu'ici, seul `git` en shell nu.

**La garde qui compte le plus** : `ouvrir_pr` passe par la même confirmation
que n'importe quelle autre écriture externe. Dioumtoukay ne peut pas la
contourner en l'appelant — il hérite du même `connecteur.executer()` que
`/connectors/github/...` appellerait.
"""
import pytest

from agents.dioumtoukay.dioumtoukay_agent import Action, DioumtoukayAgent
from core.actions.resultat import ResultatAction, a_confirmer, echec, succes
from tools.atelier import Atelier


class ModeleScripte:
    def __init__(self, *reponses: str):
        self.reponses = list(reponses)
        self.system_prompts = []

    async def is_available(self) -> bool:
        return True

    async def generate(self, prompt: str, system_prompt: str = None) -> str:
        self.system_prompts.append(system_prompt or "")
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
        assert "Ce que contient la racine" not in reperes

    @pytest.mark.asyncio
    async def test_un_lister_local_est_redirige_vers_github_sur_railway(self, bac):
        connecteur = FauxConnecteurGitHub(succes(
            "lister", "unic-backend/arena-personal-ai",
            "2 entree(s) dans apps/pwa.", preuve="2",
            entrees=[{"chemin": "apps/pwa/src"}, {"chemin": "apps/pwa/index.html"}],
        ))
        a = agent(
            bac,
            [],
            connecteur_github=connecteur,
            depot_github_defaut="unic-backend/arena-personal-ai",
        )
        chemin_image = str(bac / "apps" / "pwa")

        resultat = await a._executer_action(
            Action(nom="lister", champs={"CHEMIN": chemin_image}),
            github_distant=True,
        )

        assert resultat.ok is True
        assert connecteur.appels == [(
            "lister",
            {
                "depot": "unic-backend/arena-personal-ai",
                "chemin": "apps/pwa",
                "ref": "",
            },
        )]

    @pytest.mark.asyncio
    async def test_mode_distant_envoie_une_consigne_compacte_au_modele(self, bac):
        modele = ModeleScripte("ACTION: terminer\nCONTENU:\nfini\nFIN")
        connecteur = FauxConnecteurGitHub(succes("x", "x", "ok", preuve="x"))
        a = DioumtoukayAgent(
            provider=modele,
            atelier=Atelier(racine=bac),
            connecteur_github=connecteur,
            depot_github_defaut="unic-backend/arena-personal-ai",
        )

        resultat = await a.run("explore le depot")

        assert resultat["status"] == "success"
        assert modele.system_prompts
        consigne = modele.system_prompts[0]
        assert "mode GitHub distant" in consigne
        assert "ACTION: github_lister" in consigne
        assert "STANDARD DE TRAVAIL" in consigne
        assert "cause racine" in consigne
        assert "ACTION: ordinateur_creer" not in consigne
        assert "ACTION: git_pousser" not in consigne

    @pytest.mark.asyncio
    async def test_un_resultat_de_listing_reste_visible_si_le_modele_tombe_apres(self, bac):
        class ModeleQuiTombe(ModeleScripte):
            async def generate(self, prompt: str, system_prompt: str = None) -> str:
                self.system_prompts.append(system_prompt or "")
                if self.reponses:
                    return self.reponses.pop(0)
                raise RuntimeError("429 temporaire")

        modele = ModeleQuiTombe("ACTION: github_lister\nCHEMIN: apps/pwa\nREF: main")
        connecteur = FauxConnecteurGitHub(succes(
            "lister", "unic-backend/arena-personal-ai",
            "2 entree(s) dans apps/pwa.", preuve="2",
            entrees=[
                {"chemin": "apps/pwa/src"},
                {"chemin": "apps/pwa/index.html"},
            ],
        ))
        a = DioumtoukayAgent(
            provider=modele,
            atelier=Atelier(racine=bac),
            connecteur_github=connecteur,
            depot_github_defaut="unic-backend/arena-personal-ai",
        )

        resultat = await a.run("donne-moi les fichiers dans apps/pwa")

        assert resultat["status"] == "partial"
        assert "apps/pwa/src" in resultat["response"]
        assert "apps/pwa/index.html" in resultat["response"]
        assert "429 temporaire" in resultat["response"]

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
    async def test_recherche_github_explicite_respecte_le_dossier(self, bac):
        connecteur = FauxConnecteurGitHub(succes(
            "chercher_code", "unic-backend/arena-personal-ai",
            "1 occurrence(s) de 'Composer'.", preuve="1",
            occurrences=[{"chemin": "apps/pwa/src/Composer.tsx"}],
        ))
        a = agent(
            bac,
            [
                "ACTION: github_chercher\nTEXTE: Composer\nCHEMIN: apps/pwa",
                "ACTION: terminer\nCONTENU:\nTrouve.\nFIN",
            ],
            connecteur_github=connecteur,
            depot_github_defaut="unic-backend/arena-personal-ai",
        )

        await a.run("cherche Composer dans apps/pwa")

        assert connecteur.appels[0] == (
            "chercher_code",
            {
                "depot": "unic-backend/arena-personal-ai",
                "terme": "Composer",
                "chemin": "apps/pwa",
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


# --- qualite d'execution et rendu humain -----------------------------------------

class TestQualiteExecution:
    @pytest.mark.asyncio
    async def test_refuse_de_terminer_juste_apres_une_ecriture(self, bac):
        a = agent(bac, [
            "ACTION: ecrire\nCHEMIN: note.txt\nCONTENU:\nversion 2\nFIN",
            "ACTION: terminer\nCONTENU:\nc est bon\nFIN",
            "ACTION: lire\nCHEMIN: note.txt",
            "ACTION: terminer\nCONTENU:\nFichier relu et verifie.\nFIN",
        ])

        resultat = await a.run("mets note.txt a jour et verifie le resultat")

        assert resultat["status"] == "success"
        assert [acte["action"] for acte in resultat["actions"]] == ["ecrire", "lire"]
        assert "Fichier relu et verifie." in resultat["response"]
        assert (bac / "note.txt").read_text() == "version 2"

    @pytest.mark.asyncio
    async def test_deux_conclusions_sans_preuve_restent_partielles(self, bac):
        a = agent(bac, [
            "ACTION: ecrire\nCHEMIN: note.txt\nCONTENU:\nversion 2\nFIN",
            "ACTION: terminer\nCONTENU:\nc est bon\nFIN",
            "ACTION: terminer\nCONTENU:\ntoujours bon\nFIN",
        ])

        resultat = await a.run("modifie note.txt")

        assert resultat["status"] == "partial"
        assert "reste non verifie" in resultat["response"]

    @pytest.mark.asyncio
    async def test_listing_github_est_lisible_sans_sha_ni_repr_python(self, bac):
        connecteur = FauxConnecteurGitHub(succes(
            "lister", "unic-backend/arena-personal-ai",
            "3 entree(s) dans apps/pwa.", preuve="3",
            entrees=[
                {"nom": "index.html", "chemin": "apps/pwa/index.html",
                 "type": "file", "sha": "secret-tech-1", "taille": 120},
                {"nom": "package.json", "chemin": "apps/pwa/package.json",
                 "type": "file", "sha": "secret-tech-2", "taille": 240},
                {"nom": "src", "chemin": "apps/pwa/src",
                 "type": "dir", "sha": "secret-tech-3", "taille": 0},
            ],
            chemin="apps/pwa", ref="main",
        ))
        a = agent(
            bac,
            [
                "ACTION: github_lister\nCHEMIN: apps/pwa\nREF: main",
                "ACTION: terminer\nCONTENU:\nVoici le contenu demande.\nFIN",
            ],
            connecteur_github=connecteur,
            depot_github_defaut="unic-backend/arena-personal-ai",
        )

        resultat = await a.run("liste apps/pwa")

        texte = resultat["response"]
        assert texte.startswith("Voici le contenu demande.")
        assert "apps/pwa/index.html" in texte
        assert "apps/pwa/package.json" in texte
        assert "secret-tech-" not in texte
        assert "'sha':" not in texte
        assert "'taille':" not in texte

    def test_detail_imbrique_ne_redevient_jamais_un_repr_python(self):
        texte = DioumtoukayAgent._detail_lisible({
            "preuve": {
                "etapes": [
                    {"nom": "tests", "etat": "success"},
                    {"nom": "build", "etat": "success"},
                ],
                "brut": b"abc",
            },
        })

        assert "{'nom':" not in texte
        assert "nom: tests" in texte
        assert "etat: success" in texte
        assert "3 octet(s)" in texte

    def test_journal_modele_compacte_les_anciennes_sorties_sans_perdre_la_derniere(self):
        journal = [
            f"> ACTION lire : ancien-{i}\nSORTIE:\n" + ("x" * 12_000)
            for i in range(6)
        ]
        journal.append("> ACTION etat_ci : derniere-preuve\nSORTIE:\nsucces")

        compact = DioumtoukayAgent._journal_pour_modele(journal)

        assert "derniere-preuve" in compact
        assert "Etapes plus anciennes (resumees)" in compact
        assert len(compact) < len("\n\n".join(journal))
        assert len(compact) < 50_000


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
