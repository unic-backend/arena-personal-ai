"""Le connecteur Case (DEC-0092) — un ordinateur Linux isole, persistant.

Comme `test_connecteur_github.py` : aucun test de cette premiere section
n'appelle une vraie instance Case, un `httpx.MockTransport` repond a sa
place. Ce qui compte : que le connecteur classe honnetement chaque reponse
reelle de Case (`{"error": {"code", "message"}}`), qu'un `423` (injection
d'identifiant en cours) ne se lise jamais comme un echec ordinaire, et qu'un
ordinateur introuvable/Case injoignable rendent des `ResultatAction` nommes,
jamais une exception qui remonte.

La seconde section (`TestContreUneVraieInstanceCase`, marquee `integration`)
parle a une VRAIE instance Case — deployee reellement dans cette session pour
auditer la mission (`docs/audits/case_audit.md`), jamais lancee par ce
fichier lui-meme. Desactivee par defaut (`pytest.ini`/`pyproject.toml`,
`-m 'not integration'`) : ailleurs, sans Case deploye, elle serait fausse.
"""
import os

import httpx
import pytest

from core.connectors.base import EtatSante
from core.connectors.case_computer import ConnecteurCaseComputer


def connecteur(reponses, journal_appels=None, **kwargs):
    def _repondre(requete: httpx.Request) -> httpx.Response:
        if journal_appels is not None:
            journal_appels.append(requete)
        return reponses(requete)
    client = httpx.Client(transport=httpx.MockTransport(_repondre))
    return ConnecteurCaseComputer(client=client, **kwargs)


def json_reponse(code: int, corps) -> httpx.Response:
    return httpx.Response(code, json=corps)


def connecteur_pret(reponses, journal_appels=None, **kwargs):
    """La sonde de sante (`GET /health`) est deja satisfaite — meme raison
    que `connecteur_pret` de github.py : `_conduire` l'appelle avant toute
    capacite, l'oublier fait echouer le test pour la mauvaise raison."""
    def _repondre(requete: httpx.Request) -> httpx.Response:
        if str(requete.url).endswith("/health"):
            return json_reponse(200, {"ok": True, "computers": 1, "docker": True,
                                      "max_running": 4, "running": 0, "max_ram_mb": 8192,
                                      "ram_mb": 0})
        return reponses(requete)
    return connecteur(_repondre, journal_appels=journal_appels, **kwargs)


# --- Sante --------------------------------------------------------------------------

class TestSante:
    def test_sans_url_configuree_la_sonde_part_quand_meme_vers_le_defaut_local(self, monkeypatch):
        """Par defaut USMAN_CASE_URL vaut http://127.0.0.1:8787/v1 (deploiement
        local attendu) : la sonde part reellement vers cette adresse plutot
        que de supposer une absence — c'est l'echec reseau qui doit rendre
        EN_PANNE, jamais une deduction sans avoir essaye."""
        monkeypatch.delenv("USMAN_CASE_URL", raising=False)
        appelee = []

        def _constate(requete):
            appelee.append(str(requete.url))
            raise httpx.ConnectError("refuse")
        c = connecteur(_constate)

        sante = c.sonder()

        assert appelee == ["http://127.0.0.1:8787/health"]
        assert sante.etat is EtatSante.EN_PANNE

    def test_case_injoignable_est_en_panne(self, monkeypatch):
        monkeypatch.setenv("USMAN_CASE_URL", "http://127.0.0.1:1/v1")

        def _refuse(_requete):
            raise httpx.ConnectError("refuse")
        c = ConnecteurCaseComputer(client=httpx.Client(
            transport=httpx.MockTransport(_refuse)))

        sante = c.sonder()

        assert sante.etat is EtatSante.EN_PANNE
        assert "injoignable" in sante.message.lower()

    def test_repond_sans_jeton_valide_est_non_configure(self, monkeypatch):
        """`/health` sans jeton (ou jeton refuse) ne rend que {"ok": true} —
        SECURITY.md de Case : porte ouverte, inventaire reserve au porteur."""
        c = connecteur(lambda _r: json_reponse(200, {"ok": True}))

        sante = c.sonder()

        assert sante.etat is EtatSante.NON_CONFIGURE
        assert "jeton" in sante.ce_qui_manque.lower() or "token" in sante.ce_qui_manque.lower()

    def test_repond_avec_inventaire_est_operationnel(self):
        c = connecteur(lambda _r: json_reponse(200, {
            "ok": True, "computers": 2, "docker": True, "max_running": 4,
            "running": 1, "max_ram_mb": 8192, "ram_mb": 2048}))

        sante = c.sonder()

        assert sante.etat is EtatSante.OPERATIONNEL
        assert "2 ordinateur" in sante.message

    def test_docker_injoignable_depuis_cased_se_lit_dans_le_message(self):
        """cased lui-meme sait dire si SON docker est joignable (health.docker)
        — ne pas le cacher : c'est le signal reel derriere `ImageNotFound`/
        `create_failed` plus loin dans la boucle."""
        c = connecteur(lambda _r: json_reponse(200, {
            "ok": True, "computers": 0, "docker": False, "max_running": 4,
            "running": 0, "max_ram_mb": 8192, "ram_mb": 0}))

        sante = c.sonder()

        assert "INJOIGNABLE" in sante.message

    def test_la_sonde_est_reutilisee_pendant_sa_duree_de_validite(self, monkeypatch):
        appels = []

        def _compter(requete):
            appels.append(requete)
            return json_reponse(200, {"ok": True, "computers": 0, "docker": True,
                                      "max_running": 4, "running": 0, "max_ram_mb": 1,
                                      "ram_mb": 0})
        c = connecteur(_compter)

        c.sonder()
        c.sonder()

        assert len(appels) == 1


# --- Lister / etat ------------------------------------------------------------------

class TestListerEtEtat:
    def test_lister_rend_les_ordinateurs_reels(self):
        c = connecteur_pret(lambda _r: json_reponse(200, {"computers": [
            {"id": "c1", "state": "running"}, {"id": "c2", "state": "asleep"}]}))

        resultat = c.executer("lister")

        assert resultat.statut.value == "SUCCESS"
        assert len(resultat.detail["ordinateurs"]) == 2

    def test_etat_sans_computer_id_est_refuse(self):
        c = connecteur_pret(lambda _r: json_reponse(200, {}))

        resultat = c.executer("etat")

        assert resultat.statut.value == "FAILED"
        assert "computer_id" in resultat.message

    def test_etat_d_un_ordinateur_absent_rend_un_echec_nomme(self):
        c = connecteur_pret(lambda _r: json_reponse(
            404, {"error": {"code": "not_found", "message": "no computer c9"}}))

        resultat = c.executer("etat", computer_id="c9")

        assert resultat.statut.value == "FAILED"
        assert "introuvable" in resultat.message.lower()


# --- Creer ----------------------------------------------------------------------------

class TestCreer:
    def test_creer_reussit_rend_l_identifiant(self):
        c = connecteur_pret(lambda _r: json_reponse(
            201, {"id": "c-abc123", "state": "running", "name": "test"}))

        resultat = c.executer("creer", nom="test")

        assert resultat.statut.value == "SUCCESS"
        assert resultat.preuve == "c-abc123"

    def test_creer_sans_image_de_bureau_rend_l_erreur_reelle_de_case(self):
        """Mesure REELLEMENT (docs/audits/case_audit.md) contre une instance
        Case sans image de bureau construite (contrainte disque de cette
        session) : Case rend `create_failed` / `ImageNotFound`, jamais une
        exception. Ce test fixe ce comportement precis, observe pour de vrai."""
        c = connecteur_pret(lambda _r: json_reponse(
            400, {"error": {"code": "create_failed",
                            "message": "create failed: ImageNotFound"}}))

        resultat = c.executer("creer", nom="arena-test")

        assert resultat.statut.value == "FAILED"
        assert "ImageNotFound" in resultat.message


# --- Dormir / reveiller ---------------------------------------------------------------

class TestCycleDeVie:
    def test_dormir_puis_reveiller(self):
        journal = []
        c = connecteur_pret(lambda r: json_reponse(200, {"id": "c1", "state": "asleep"}),
                            journal_appels=journal)

        resultat = c.executer("dormir", computer_id="c1")

        assert resultat.statut.value == "SUCCESS"
        assert any(str(r.url).endswith("/computers/c1/sleep") for r in journal)

    def test_reveiller(self):
        journal = []
        c = connecteur_pret(lambda r: json_reponse(200, {"id": "c1", "state": "running"}),
                            journal_appels=journal)

        resultat = c.executer("reveiller", computer_id="c1")

        assert resultat.statut.value == "SUCCESS"
        assert any(str(r.url).endswith("/computers/c1/wake") for r in journal)


# --- Executer une commande --------------------------------------------------------------

class TestExecuterCommande:
    def test_commande_reussie(self):
        c = connecteur_pret(lambda _r: json_reponse(
            200, {"exit_code": 0, "stdout": "bonjour\n", "stderr": ""}))

        resultat = c.executer("executer_commande", computer_id="c1", commande="echo bonjour")

        assert resultat.statut.value == "SUCCESS"
        assert resultat.detail["sortie"] == "bonjour\n"

    def test_commande_en_echec_reste_un_echec_pas_une_exception(self):
        c = connecteur_pret(lambda _r: json_reponse(
            200, {"exit_code": 1, "stdout": "", "stderr": "not found\n"}))

        resultat = c.executer("executer_commande", computer_id="c1", commande="false")

        assert resultat.statut.value == "FAILED"
        assert resultat.detail["code"] == 1

    def test_injection_d_identifiant_en_cours_423_nomme_precisement(self):
        """SECURITY.md : deskd rend 423 pendant l'injection d'un identifiant —
        aucune action ne doit passer, et le compte-rendu doit dire pourquoi,
        jamais le confondre avec un echec ordinaire de la commande."""
        c = connecteur_pret(lambda _r: httpx.Response(423, json={}))

        resultat = c.executer("executer_commande", computer_id="c1", commande="ls")

        assert resultat.statut.value == "FAILED"
        assert "423" in resultat.message
        assert "identifiant" in resultat.message.lower()


# --- Fichiers --------------------------------------------------------------------------

class TestFichiers:
    def test_ecrire_puis_lire(self):
        stockage = {}

        def _repondre(requete: httpx.Request) -> httpx.Response:
            if requete.method == "PUT" and "/files" in str(requete.url):
                stockage["contenu"] = requete.content
                return httpx.Response(201, json={})
            if requete.method == "GET" and "/files" in str(requete.url):
                return httpx.Response(200, content=stockage.get("contenu", b""))
            return json_reponse(200, {"ok": True, "computers": 0, "docker": True,
                                      "max_running": 4, "running": 0, "max_ram_mb": 1, "ram_mb": 0})
        c = ConnecteurCaseComputer(client=httpx.Client(transport=httpx.MockTransport(_repondre)))

        ecriture = c.executer("ecrire_fichier", computer_id="c1",
                              chemin="/home/agent/arena_persistence_test.txt",
                              contenu="ARENA-OK")
        lecture = c.executer("lire_fichier", computer_id="c1",
                             chemin="/home/agent/arena_persistence_test.txt")

        assert ecriture.statut.value == "SUCCESS"
        assert lecture.statut.value == "SUCCESS"
        assert lecture.detail["contenu"] == b"ARENA-OK"

    def test_fichier_introuvable(self):
        c = connecteur_pret(lambda _r: json_reponse(
            404, {"error": {"code": "not_found", "message": "no such file"}}))

        resultat = c.executer("lire_fichier", computer_id="c1", chemin="/fantome.txt")

        assert resultat.statut.value == "FAILED"


# --- Navigation / capture ----------------------------------------------------------------

class TestNavigationEtCapture:
    def test_naviguer_reussit(self):
        c = connecteur_pret(lambda _r: json_reponse(
            200, {"ok": True, "snapshot": {"title": "Exemple"}}))

        resultat = c.executer("naviguer", computer_id="c1", url="https://example.com")

        assert resultat.statut.value == "SUCCESS"

    def test_naviguer_page_refusee_par_case_reste_un_echec(self):
        c = connecteur_pret(lambda _r: json_reponse(
            200, {"ok": False, "error": "net::ERR_NAME_NOT_RESOLVED"}))

        resultat = c.executer("naviguer", computer_id="c1", url="https://n-existe-pas.invalide")

        assert resultat.statut.value == "FAILED"

    def test_capture_ecran_rend_les_octets_png(self):
        octets_png_factices = b"\x89PNG\r\n\x1a\n" + b"x" * 20
        c = connecteur_pret(lambda _r: httpx.Response(
            200, content=octets_png_factices, headers={"content-type": "image/png"}))

        resultat = c.executer("capture_ecran", computer_id="c1")

        assert resultat.statut.value == "SUCCESS"
        assert resultat.detail["png"] == octets_png_factices


# --- Detruire ---------------------------------------------------------------------------

class TestDetruire:
    """`destroy` est CONFIRMATION (config/permissions_services.yaml) : une
    destruction de donnees persistantes ne part jamais sans accord — meme
    logique que `demolir` (architecture_3d) et `create_pull_request` (github)."""

    def test_detruire_seul_demande_confirmation_rien_ne_part(self):
        appelee = []

        def _constate(requete):
            appelee.append(requete)
            return httpx.Response(204)
        c = connecteur_pret(_constate)

        resultat = c.executer("detruire", computer_id="c1")

        assert resultat.statut.value == "NEEDS_CONFIRMATION"
        # La sonde de sante (`/health`) est la seule requete partie ; DELETE
        # n'a jamais ete envoyee — la destruction reelle attend l'accord.
        assert not any(r.method == "DELETE" for r in appelee)

    def test_detruire_confirmee_reussit_reellement(self):
        c = connecteur_pret(lambda _r: httpx.Response(204))

        resultat = c.executer_confirmee("detruire", computer_id="c1")

        assert resultat.statut.value == "SUCCESS"

    def test_detruire_confirmee_sur_un_ordinateur_absent_est_nommee(self):
        c = connecteur_pret(lambda _r: json_reponse(
            404, {"error": {"code": "not_found", "message": "no computer c9"}}))

        resultat = c.executer_confirmee("detruire", computer_id="c9")

        assert resultat.statut.value == "FAILED"


# --- Confidentialite ---------------------------------------------------------------------

class TestConfidentialite:
    def test_aucune_capacite_ne_manipule_d_identifiant(self):
        """Mission ARENA x CASE §22-24 : ce connecteur ne doit JAMAIS recevoir
        ni transmettre un mot de passe. Verifie que la surface declaree ne
        porte aucune capacite de gestion d'identifiants — cette
        responsabilite reste entierement du cote de Case (Drive UI, `/fill`,
        `bin/case cred add`), jamais dans ce qu'un modele peut appeler."""
        c = ConnecteurCaseComputer()

        noms = set(c.capacites().keys())

        assert not any("credential" in n or "identifiant" in n or "mot_de_passe" in n
                      for n in noms)
        assert not any("login" in n or "connexion" in n for n in noms)


# --- Contre une vraie instance Case --------------------------------------------------------

@pytest.mark.integration
class TestContreUneVraieInstanceCase:
    """Parle a une VRAIE instance Case. Suppose `USMAN_CASE_URL`/
    `USMAN_CASE_TOKEN` deja pointes sur un `cased` reellement lance — cette
    classe n'en demarre aucun (voir `docs/audits/case_audit.md` pour la
    procedure reelle de deploiement local suivie pendant l'audit)."""

    @pytest.fixture(autouse=True)
    def _skip_sans_case_reel(self):
        if not os.getenv("USMAN_CASE_URL"):
            pytest.skip("USMAN_CASE_URL non configure : aucune instance Case reelle a joindre.")

    def test_la_sonde_reussit_reellement(self):
        c = ConnecteurCaseComputer()
        sante = c.sonder()
        assert sante.etat is EtatSante.OPERATIONNEL, sante.message

    def test_lister_reussit_reellement(self):
        c = ConnecteurCaseComputer()
        resultat = c.executer("lister")
        assert resultat.statut.value == "SUCCESS", resultat.message

    def test_creer_sans_image_de_bureau_echoue_honnetement(self):
        """La mesure reelle qui a motive `TestCreer::
        test_creer_sans_image_de_bureau_rend_l_erreur_reelle_de_case` :
        cette instance Case n'a pas l'image de bureau construite (disque de
        cette session, voir l'audit) — la creation doit echouer, jamais
        simuler un succes."""
        c = ConnecteurCaseComputer()
        resultat = c.executer("creer", nom="arena-pytest-integration")
        assert resultat.statut.value == "FAILED"
