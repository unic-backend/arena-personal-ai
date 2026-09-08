"""Le connecteur GitHub (DEC-0073) — le premier de ce dépôt.

Aucun test n'appelle le vrai GitHub : un `httpx.MockTransport` répond à sa
place. Ce qui compte le plus ici n'est pas « le connecteur marche » mais
**« la garde tient »** : une Pull Request ne doit jamais partir sans
confirmation, et ne doit jamais partir prête à fusionner.
"""
import json

import httpx
import pytest

from core.actions.resultat import Statut
from core.connectors.base import EtatSante
from core.connectors.github import ConnecteurGitHub


def connecteur(reponses, journal_appels=None, **kwargs):
    """Un connecteur dont chaque requête est répondue par `reponses(requete)`."""
    def _repondre(requete: httpx.Request) -> httpx.Response:
        if journal_appels is not None:
            journal_appels.append(requete)
        return reponses(requete)
    client = httpx.Client(transport=httpx.MockTransport(_repondre))
    return ConnecteurGitHub(client=client, **kwargs)


def json_reponse(code: int, corps) -> httpx.Response:
    return httpx.Response(code, json=corps)


def connecteur_pret(reponses, journal_appels=None, **kwargs):
    """Comme `connecteur()`, avec la sonde de santé déjà satisfaite.

    `executer()` appelle toujours `GET /user` avant la capacité demandée
    (contrat `Connecteur._conduire`, étape 3) — l'oublier fait échouer
    l'action AVANT qu'elle atteigne le code testé, avec un message qui n'a
    rien à voir (mesuré en écrivant ce fichier : un `404` du mock sur
    `/user` se lisait comme un `404` de l'action elle-même).
    """
    def _repondre(requete: httpx.Request) -> httpx.Response:
        if str(requete.url).endswith("/user"):
            return json_reponse(200, {"login": "test"})
        return reponses(requete)
    return connecteur(_repondre, journal_appels=journal_appels, **kwargs)


# --- Santé -----------------------------------------------------------------------

def test_sans_jeton_non_configure(monkeypatch):
    monkeypatch.delenv("USMAN_GITHUB_TOKEN", raising=False)
    c = connecteur(lambda r: json_reponse(200, {"login": "x"}))
    sante = c.sonder()
    assert sante.etat is EtatSante.NON_CONFIGURE
    assert "USMAN_GITHUB_TOKEN" in sante.ce_qui_manque


def test_jeton_valide_operationnel(monkeypatch):
    monkeypatch.setenv("USMAN_GITHUB_TOKEN", "un-jeton")
    c = connecteur(lambda r: json_reponse(200, {"login": "ousmane"}))
    sante = c.sonder()
    assert sante.etat is EtatSante.OPERATIONNEL
    assert "ousmane" in sante.message


def test_jeton_refuse_non_configure(monkeypatch):
    monkeypatch.setenv("USMAN_GITHUB_TOKEN", "un-mauvais-jeton")
    c = connecteur(lambda r: json_reponse(401, {"message": "Bad credentials"}))
    sante = c.sonder()
    assert sante.etat is EtatSante.NON_CONFIGURE


def test_panne_reseau_en_panne(monkeypatch):
    monkeypatch.setenv("USMAN_GITHUB_TOKEN", "un-jeton")
    def _echoue(r):
        raise httpx.ConnectError("injoignable", request=r)
    c = connecteur(_echoue)
    sante = c.sonder()
    assert sante.etat is EtatSante.EN_PANNE


def test_la_sonde_ne_leve_jamais_pour_le_registre(monkeypatch):
    """Le contrat de base.py : sonder() peut lever, sante() jamais."""
    monkeypatch.setenv("USMAN_GITHUB_TOKEN", "un-jeton")
    def _casse(r):
        raise RuntimeError("n'importe quoi")
    c = connecteur(_casse)
    sante = c.sante()
    assert sante.etat is EtatSante.EN_PANNE


# --- lire_fichier -----------------------------------------------------------------

def test_lire_fichier(monkeypatch):
    import base64
    monkeypatch.setenv("USMAN_GITHUB_TOKEN", "t")
    contenu = base64.b64encode(b"print('hello')").decode()
    c = connecteur_pret(lambda r: json_reponse(200, {"content": contenu, "sha": "abc123"}))
    resultat = c.executer("lire_fichier", depot="unic-backend/arena-personal-ai",
                          chemin="README.md")
    assert resultat.statut is Statut.SUCCES
    assert resultat.detail["contenu"] == "print('hello')"
    assert resultat.preuve == "abc123"


def test_lire_fichier_absent(monkeypatch):
    monkeypatch.setenv("USMAN_GITHUB_TOKEN", "t")
    c = connecteur_pret(lambda r: json_reponse(404, {"message": "Not Found"}))
    resultat = c.executer("lire_fichier", depot="o/r", chemin="absent.py")
    assert resultat.statut is Statut.ECHEC
    assert "introuvable" in resultat.message


def test_lire_fichier_sans_parametres(monkeypatch):
    monkeypatch.setenv("USMAN_GITHUB_TOKEN", "t")
    c = connecteur_pret(lambda r: json_reponse(200, {}))
    resultat = c.executer("lire_fichier")
    assert resultat.statut is Statut.ECHEC


# --- chercher_code ------------------------------------------------------------------

def test_chercher_code(monkeypatch):
    monkeypatch.setenv("USMAN_GITHUB_TOKEN", "t")
    c = connecteur_pret(lambda r: json_reponse(200, {
        "total_count": 2,
        "items": [{"path": "a.py", "html_url": "https://x/a"},
                 {"path": "b.py", "html_url": "https://x/b"}],
    }))
    resultat = c.executer("chercher_code", depot="o/r", terme="def calculer")
    assert resultat.statut is Statut.SUCCES
    assert len(resultat.detail["occurrences"]) == 2


# --- creer_branche (ALLOWED — même risque que git push sous DEC-0038) --------------

def test_creer_branche_va_directement_au_reseau_sans_confirmation(monkeypatch):
    monkeypatch.setenv("USMAN_GITHUB_TOKEN", "t")
    appels = []
    def _repondre(r):
        if "git/ref/heads/main" in str(r.url):
            return json_reponse(200, {"object": {"sha": "sha-de-base"}})
        return json_reponse(201, {"ref": "refs/heads/nouvelle"})
    c = connecteur_pret(_repondre, journal_appels=appels)
    resultat = c.executer("creer_branche", depot="o/r", nom_branche="nouvelle")
    assert resultat.statut is Statut.SUCCES
    # La sonde de sante (/user), lire la base, puis creer la ref — trois
    # requetes, aucune mise en attente entre elles.
    assert len(appels) == 3
    assert appels[-1].method == "POST"


def test_creer_branche_qui_existe_deja(monkeypatch):
    monkeypatch.setenv("USMAN_GITHUB_TOKEN", "t")
    def _repondre(r):
        if "git/ref/heads/main" in str(r.url):
            return json_reponse(200, {"object": {"sha": "s"}})
        return json_reponse(422, {"message": "Reference already exists"})
    c = connecteur_pret(_repondre)
    resultat = c.executer("creer_branche", depot="o/r", nom_branche="deja-la")
    assert resultat.statut is Statut.ECHEC
    assert "existe deja" in resultat.message


# --- creer_pull_request : LA garde qui compte le plus -------------------------------

class TestGardePullRequest:
    """DEC-0073 : deux gardes redondantes, chacune vérifiée séparément."""

    def test_sans_confirmation_rien_ne_part_sur_le_reseau(self, monkeypatch):
        """La garde ARENA : CONFIRMATION doit arrêter l'action AVANT le
        premier appel HTTP — pas seulement avant l'écriture."""
        monkeypatch.setenv("USMAN_GITHUB_TOKEN", "t")
        appels = []
        c = connecteur(lambda r: json_reponse(201, {"number": 1, "html_url": "https://x"}),
                      journal_appels=appels)
        resultat = c.executer("creer_pull_request", depot="o/r", titre="Fix",
                              tete="branche-du-fix")
        assert resultat.statut is Statut.A_CONFIRMER
        assert appels == [], "une requete est partie AVANT confirmation"

    def test_le_message_dit_brouillon_avant_de_confirmer(self, monkeypatch):
        """Ce qu'il lit avant de dire oui doit annoncer le brouillon — sinon
        il confirme en croyant ouvrir une PR prête."""
        monkeypatch.setenv("USMAN_GITHUB_TOKEN", "t")
        c = connecteur(lambda r: json_reponse(201, {"number": 1, "html_url": "https://x"}))
        resultat = c.executer("creer_pull_request", depot="o/r", titre="Fix",
                              tete="branche-du-fix")
        assert "brouillon" in resultat.message

    def test_confirmee_part_reellement_en_brouillon(self, monkeypatch):
        """La garde Open SWE : `draft` doit être `True` dans le corps envoyé
        à GitHub, quoi que le modèle ait demandé — sinon une PR prête à
        fusionner s'ouvre sur son dépôt public (DEC-0039) sur une seule
        confirmation."""
        monkeypatch.setenv("USMAN_GITHUB_TOKEN", "t")
        corps_envoyes = []
        def _repondre(r):
            if r.method == "POST" and "/pulls" in str(r.url):
                corps_envoyes.append(json.loads(r.content))
                return json_reponse(201, {"number": 7, "html_url": "https://x/pull/7"})
            return json_reponse(200, {})
        c = connecteur_pret(_repondre)
        resultat = c.executer_confirmee("creer_pull_request", depot="o/r",
                                        titre="Fix", tete="branche-du-fix")
        assert resultat.statut is Statut.SUCCES
        assert len(corps_envoyes) == 1
        assert corps_envoyes[0]["draft"] is True
        assert resultat.detail["numero"] == 7

    def test_github_refuse_la_creation(self, monkeypatch):
        monkeypatch.setenv("USMAN_GITHUB_TOKEN", "t")
        c = connecteur_pret(lambda r: json_reponse(422, {"message": "No commits between main and x"}))
        resultat = c.executer_confirmee("creer_pull_request", depot="o/r",
                                        titre="Fix", tete="x")
        assert resultat.statut is Statut.ECHEC


# --- etat_ci : le meme repli qu'Open SWE (SUCCESS/PENDING/FAILURE) -----------------

@pytest.mark.parametrize("courses, attendu", [
    ([], "en_attente"),
    ([{"status": "completed", "conclusion": "success"}], "succes"),
    ([{"status": "completed", "conclusion": "success"},
     {"status": "completed", "conclusion": "failure"}], "echec"),
    ([{"status": "in_progress", "conclusion": None}], "en_cours"),
])
def test_etat_ci(monkeypatch, courses, attendu):
    monkeypatch.setenv("USMAN_GITHUB_TOKEN", "t")
    c = connecteur_pret(lambda r: json_reponse(200, {"check_runs": courses}))
    resultat = c.executer("etat_ci", depot="o/r", ref="abc123")
    assert resultat.statut is Statut.SUCCES
    assert resultat.detail["resume"] == attendu


# --- commentaires_pr : deux appels reels, sur le meme client injecte --------------

def test_commentaires_pr_fusionne_revue_et_discussion(monkeypatch):
    """Deux appels HTTP dans la meme execution, sur le client injecte : la
    regression a surveiller est un client ferme apres le premier appel
    (bug reel du premier jet de ce fichier, corrige avant tout test)."""
    monkeypatch.setenv("USMAN_GITHUB_TOKEN", "t")
    def _repondre(r):
        if "/pulls/" in str(r.url):
            return json_reponse(200, [{"user": {"login": "reviewer"},
                                       "body": "corrige ça", "path": "a.py"}])
        return json_reponse(200, [{"user": {"login": "owner"}, "body": "merci"}])
    c = connecteur_pret(_repondre)
    resultat = c.executer("commentaires_pr", depot="o/r", numero=3)
    assert resultat.statut is Statut.SUCCES
    genres = {c["genre"] for c in resultat.detail["commentaires"]}
    assert genres == {"revue", "discussion"}


# --- Capacités déclarées -------------------------------------------------------------

def test_les_six_capacites_sont_declarees():
    c = ConnecteurGitHub()
    noms = set(c.capacites())
    assert noms == {"lire_fichier", "chercher_code", "creer_branche",
                    "creer_pull_request", "etat_ci", "commentaires_pr"}


def test_une_capacite_non_declaree_natteint_jamais_le_reseau(monkeypatch):
    monkeypatch.setenv("USMAN_GITHUB_TOKEN", "t")
    appels = []
    c = connecteur_pret(lambda r: json_reponse(200, {}), journal_appels=appels)
    resultat = c.executer("supprimer_le_depot", depot="o/r")
    assert resultat.statut is Statut.NON_IMPLEMENTE
    assert appels == []
