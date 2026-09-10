"""Le connecteur Browser : une seule capacité, deux moteurs — Lightpanda
tenté en premier quand configuré et sain, repli automatique et silencieux
sur le moteur existant (Chromium/Playwright) sur tout échec.
"""
import importlib.util
import sys
import types
from typing import Any, Dict, Optional

import pytest

import core.connectors.browser as module
from core.actions.resultat import Statut
from core.connectors.base import EtatSante
from core.connectors.browser import ConnecteurBrowser, ResultatNavigation, classer_resultat

#: La VRAIE règle du moteur de base, capturée avant que la fixture autouse
#: ne la remplace par un double. Sans cette référence, aucun test de ce
#: fichier ne peut vérifier que `_verifier_moteur_de_base` consulte
#: réellement `_verifier_navigateur_installe` — et un sabotage du
#: branchement passait inaperçu (mesuré le 07/09/2026).
_MOTEUR_DE_BASE_REEL = module._verifier_moteur_de_base

#: `playwright` n'est PAS installé sur le CI — volontairement, comme tout
#: paquet lourd de ce dépôt. Les deux tests qui interrogent sa vraie
#: résolution de chemins sont donc sautés là-bas ; **sauter n'est pas
#: passer**, et le rapport de pytest le dit. Le test qui compte vraiment —
#: celui du BRANCHEMENT, qui attrape le sabotage — n'a besoin d'aucun paquet
#: et tourne partout.
_SANS_PLAYWRIGHT = pytest.mark.skipif(
    importlib.util.find_spec("playwright") is None,
    reason="playwright absent : sa résolution de chemins ne peut pas être mesurée ici")


#: Champs par defaut d'une reponse SUCCES cote `BrowserUseTool` (mission
#: Fuji-Web : signaux deterministes consommes par `classer_resultat`) —
#: un test qui veut un echec/une non-verification les ecrase explicitement.
_SIGNAUX_SUCCES_VERIFIE = {"succes_declare": True, "erreurs": [], "nombre_etapes": 1,
                          "max_etapes": 25, "etapes": [], "urls_visitees": []}


class FauxOutil:
    """Remplace `BrowserUseTool` — note les appels, rend un résultat scripté
    par moteur (`cdp_url is None` -> chromium, sinon -> lightpanda)."""

    def __init__(self, reponse_chromium=None, reponse_lightpanda=None, delai=0.0):
        self.appels = []
        self._chromium = {**_SIGNAUX_SUCCES_VERIFIE, "status": "success", "task": "x",
                          "result": "ok (chromium)", "moteur": "chromium",
                          **(reponse_chromium or {})}
        self._lightpanda = {**_SIGNAUX_SUCCES_VERIFIE, "status": "success", "task": "x",
                            "result": "ok (lightpanda)", "moteur": "lightpanda",
                            **(reponse_lightpanda or {})}

    async def run_task(self, tache: str, cdp_url: Optional[str] = None, **kw: Any) -> Dict[str, Any]:
        self.appels.append((tache, cdp_url))
        self.derniers_kwargs = kw
        return self._lightpanda if cdp_url else self._chromium


@pytest.fixture(autouse=True)
def _sans_lightpanda_par_defaut(monkeypatch):
    monkeypatch.delenv("LIGHTPANDA_CDP_URL", raising=False)


@pytest.fixture(autouse=True)
def _moteur_de_base_disponible_par_defaut(monkeypatch):
    """La CI hors ligne (`.github/workflows/ci.yml`) n'installe jamais
    browser-use/Playwright — volontairement, comme tout paquet lourd testé
    par un connecteur plutôt que par lui-même. Ces tests visent le ROUTAGE
    du connecteur, jamais la présence réelle du paquet tiers ; seul
    `test_non_configure_sans_browser_use` réapplique explicitement le vrai
    comportement d'absence."""
    monkeypatch.setattr(module, "_verifier_moteur_de_base", lambda: None)


class TestSante:
    def test_operationnel_quand_browser_use_installe(self):
        assert ConnecteurBrowser(outil=FauxOutil()).sonder().etat is EtatSante.OPERATIONNEL

    def test_non_configure_sans_browser_use(self, monkeypatch):
        monkeypatch.setattr(module, "_verifier_moteur_de_base",
                            lambda: "No module named 'browser_use'")
        assert ConnecteurBrowser(outil=FauxOutil()).sonder().etat is EtatSante.NON_CONFIGURE

    def test_un_navigateur_absent_rend_la_sonde_non_configuree(self, monkeypatch):
        """Le refus du navigateur doit remonter jusqu'à la santé, pas rester
        dans une fonction que personne ne consulte."""
        monkeypatch.setattr(
            module, "_verifier_moteur_de_base",
            lambda: "aucun navigateur dans /x : "
                    "« playwright install chromium » n'a jamais été lancé.")
        sante = ConnecteurBrowser(outil=FauxOutil()).sonder()
        assert sante.etat is EtatSante.NON_CONFIGURE
        assert "playwright install chromium" in sante.message


class TestLaSondeNAnnoncePasUnNavigateurAbsent:
    """**Défaut mesuré le 07/09/2026**, sur demande de vérification.

    `_verifier_moteur_de_base` ne testait que l'import de `browser_use` et
    `langchain_openai`. En pointant `PLAYWRIGHT_BROWSERS_PATH` sur un dossier
    vide, la sonde annonçait encore « Navigation autonome disponible (Chromium
    local) » — et un lancement réel échouait aussitôt
    (`Executable doesn't exist at ...`). `pip install playwright` n'installe
    aucun navigateur : `playwright install chromium` est une seconde étape.
    """

    @_SANS_PLAYWRIGHT
    def test_un_dossier_de_navigateurs_vide_est_refuse(self, monkeypatch, tmp_path):
        monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path))
        erreur = module._verifier_navigateur_installe()
        assert erreur is not None, (
            "un dossier sans le moindre navigateur s'est déclaré prêt à naviguer")
        assert "playwright install chromium" in erreur, (
            "un refus doit nommer la commande qui le répare")

    @_SANS_PLAYWRIGHT
    def test_l_emplacement_vient_de_playwright_jamais_devine(self, monkeypatch, tmp_path):
        """Le chemin annoncé doit être celui que Playwright résout lui-même —
        il diffère entre Linux, macOS et le Windows du propriétaire."""
        monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path))
        erreur = module._verifier_navigateur_installe()
        assert str(tmp_path) in erreur, (
            "la sonde a ignoré PLAYWRIGHT_BROWSERS_PATH : elle devine un chemin")

    @staticmethod
    def _paquets_importables(monkeypatch):
        """Fait réussir `import browser_use` / `import langchain_openai` sans
        les installer.

        Le CI ne les a pas — volontairement — et ce test-ci doit tourner
        **là-bas aussi** : c'est lui qui attrape le sabotage. Substituer les
        modules plutôt que la fonction testée garde la vraie règle en jeu.
        """
        for nom in ("browser_use", "langchain_openai"):
            if nom not in sys.modules:
                monkeypatch.setitem(sys.modules, nom, types.ModuleType(nom))

    def test_le_moteur_de_base_consulte_vraiment_le_navigateur(self, monkeypatch):
        """**Le test qui manquait.** Les deux d'au-dessus vérifient la règle
        du navigateur ; celui-ci vérifie qu'elle est BRANCHÉE.

        Sans lui, retirer l'appel à `_verifier_navigateur_installe` dans
        `_verifier_moteur_de_base` laissait les quinze tests de ce fichier au
        vert — sabotage mesuré le 07/09/2026, exactement la même faute que
        celle trouvée le même jour sur le filtre de clonage vocal : un test
        qui remplace la fonction qu'il prétend vérifier ne vérifie rien.
        """
        self._paquets_importables(monkeypatch)
        appele = []

        def refus():
            appele.append(True)
            return "aucun navigateur : « playwright install chromium » manque."

        monkeypatch.setattr(module, "_verifier_navigateur_installe", refus)

        erreur = _MOTEUR_DE_BASE_REEL()

        assert appele, (
            "`_verifier_moteur_de_base` ne consulte pas le navigateur : "
            "les paquets Python suffisent de nouveau à s'annoncer prêt")
        assert erreur is not None and "playwright install chromium" in erreur

    def test_des_paquets_absents_priment_sur_le_navigateur(self, monkeypatch):
        """L'ordre compte : sans `browser_use`, inutile de chercher un
        navigateur — c'est le paquet qu'il faut installer d'abord, et c'est
        son message que le propriétaire doit lire."""
        monkeypatch.setattr(module, "_verifier_navigateur_installe",
                            lambda: pytest.fail(
                                "le navigateur a été sondé alors que le paquet manque"))
        for nom in ("browser_use", "langchain_openai"):
            monkeypatch.setitem(sys.modules, nom, None)  # force l'ImportError

        assert _MOTEUR_DE_BASE_REEL() is not None


class TestSansLightpandaConfigure:
    def test_le_moteur_existant_est_utilise_directement(self):
        outil = FauxOutil()
        connecteur = ConnecteurBrowser(outil=outil)

        resultat = connecteur.executer("naviguer", tache="visite https://example.com")

        assert resultat.statut is Statut.SUCCES
        assert resultat.detail["moteur"] == "chromium"
        assert resultat.detail["repli"] is False
        assert outil.appels == [("visite https://example.com", None)]

    def test_aucune_tache_est_un_echec(self):
        outil = FauxOutil()
        resultat = ConnecteurBrowser(outil=outil).executer("naviguer")

        assert resultat.statut is Statut.ECHEC
        assert outil.appels == []


class TestAvecLightpandaSainEtConfigure:
    def test_lightpanda_est_tente_en_premier(self, monkeypatch):
        monkeypatch.setenv("LIGHTPANDA_CDP_URL", "ws://127.0.0.1:9222")
        import core.connectors.browser as module
        monkeypatch.setattr(module, "_lightpanda_sain", lambda url: True)

        outil = FauxOutil()
        resultat = ConnecteurBrowser(outil=outil).executer("naviguer", tache="visite https://example.com")

        assert resultat.statut is Statut.SUCCES
        assert resultat.detail["moteur"] == "lightpanda"
        assert resultat.detail["repli"] is False
        assert outil.appels == [("visite https://example.com", "ws://127.0.0.1:9222")]

    def test_echec_lightpanda_retombe_sur_le_moteur_existant(self, monkeypatch):
        monkeypatch.setenv("LIGHTPANDA_CDP_URL", "ws://127.0.0.1:9222")
        import core.connectors.browser as module
        monkeypatch.setattr(module, "_lightpanda_sain", lambda url: True)

        outil = FauxOutil(reponse_lightpanda={
            "status": "error", "task": "x", "error": "connexion refusée", "moteur": "lightpanda"})
        resultat = ConnecteurBrowser(outil=outil).executer("naviguer", tache="visite https://example.com")

        assert resultat.statut is Statut.SUCCES, resultat.message
        assert resultat.detail["moteur"] == "chromium"
        assert resultat.detail["repli"] is True
        # Les deux moteurs ont bien été essayés, dans cet ordre.
        assert outil.appels == [
            ("visite https://example.com", "ws://127.0.0.1:9222"),
            ("visite https://example.com", None),
        ]

    def test_les_deux_moteurs_en_echec_reste_un_echec_honnete(self, monkeypatch):
        monkeypatch.setenv("LIGHTPANDA_CDP_URL", "ws://127.0.0.1:9222")
        import core.connectors.browser as module
        monkeypatch.setattr(module, "_lightpanda_sain", lambda url: True)

        outil = FauxOutil(
            reponse_lightpanda={"status": "error", "error": "connexion refusée", "moteur": "lightpanda"},
            reponse_chromium={"status": "error", "error": "chromium introuvable", "moteur": "chromium"})
        resultat = ConnecteurBrowser(outil=outil).executer("naviguer", tache="x")

        assert resultat.statut is Statut.ECHEC
        assert "chromium introuvable" in resultat.message


class TestAvecLightpandaConfigureMaisInjoignable:
    def test_lightpanda_non_sain_n_est_jamais_tente(self, monkeypatch):
        """La sonde Lightpanda répond faux (non joignable) : le connecteur
        ne perd pas de temps à essayer, il va direct au moteur existant."""
        monkeypatch.setenv("LIGHTPANDA_CDP_URL", "ws://127.0.0.1:9222")
        import core.connectors.browser as module
        monkeypatch.setattr(module, "_lightpanda_sain", lambda url: False)

        outil = FauxOutil()
        resultat = ConnecteurBrowser(outil=outil).executer("naviguer", tache="visite https://example.com")

        assert resultat.statut is Statut.SUCCES
        assert resultat.detail["moteur"] == "chromium"
        assert outil.appels == [("visite https://example.com", None)]


class TestSondeLightpandaReelle:
    """`_lightpanda_sain` elle-même, contre un faux serveur HTTP — jamais
    de vrai réseau dans les tests."""

    def test_sain_quand_json_version_repond_200(self, monkeypatch):
        import core.connectors.browser as module

        class FausseReponse:
            status_code = 200

        class FauxClient:
            def __init__(self, **kw):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def get(self, url):
                assert url == "http://127.0.0.1:9222/json/version"
                return FausseReponse()

        monkeypatch.setattr(module.httpx, "Client", FauxClient)
        assert module._lightpanda_sain("ws://127.0.0.1:9222") is True

    def test_non_sain_quand_injoignable(self, monkeypatch):
        import httpx

        import core.connectors.browser as module

        class ClientQuiEchoue:
            def __init__(self, **kw):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def get(self, url):
                raise httpx.ConnectError("refusé")

        monkeypatch.setattr(module.httpx, "Client", ClientQuiEchoue)
        assert module._lightpanda_sain("ws://127.0.0.1:9222") is False


class TestLaVraiePolitiqueLivree:
    def test_naviguer_reste_gouverne_dans_le_depot_reel(self):
        from core.permissions.politique import FICHIER_POLITIQUE, PolitiqueDePermissions

        regle = PolitiqueDePermissions(chemin=FICHIER_POLITIQUE).regle("browser", "browse")
        assert regle is not None, "browser.browse a disparu de la politique livrée"
        assert regle.get("decision") == "ALLOWED"
        assert regle.get("interrupteur") == "SEARCH_WEB"


class TestClasserResultat:
    """La classification deterministe (mission Fuji-Web §7) : un succes
    auto-declare par browser_use ne devient jamais un succes ARENA sans
    verification."""

    def test_succes_declare_sans_erreur_est_verifie(self):
        assert classer_resultat(True, False, 3, 25) is ResultatNavigation.VERIFIE

    def test_succes_declare_avec_erreurs_n_est_pas_verifie(self):
        assert classer_resultat(True, True, 3, 25) is ResultatNavigation.NON_VERIFIE

    def test_echec_declare_est_un_echec(self):
        assert classer_resultat(False, False, 3, 25) is ResultatNavigation.ECHEC

    def test_aucun_done_appele_est_incomplet(self):
        assert classer_resultat(None, False, 25, 25) is ResultatNavigation.INCOMPLET


class TestVerificationDansLExecution:
    """`_executer` classe reellement le resultat — jamais un succes qui ne
    fait que reprendre `status: success` sans regarder les autres signaux."""

    def test_succes_verifie_devient_succes(self):
        outil = FauxOutil(reponse_chromium={"succes_declare": True, "erreurs": []})
        resultat = ConnecteurBrowser(outil=outil).executer("naviguer", tache="x")
        assert resultat.statut is Statut.SUCCES
        assert resultat.detail["verification"] == "VERIFIED_SUCCESS"

    def test_succes_declare_avec_erreurs_devient_partiel_jamais_succes_plein(self):
        outil = FauxOutil(reponse_chromium={
            "succes_declare": True, "erreurs": ["element introuvable au pas 2"]})
        resultat = ConnecteurBrowser(outil=outil).executer("naviguer", tache="x")
        assert resultat.statut is Statut.PARTIEL
        assert resultat.detail["verification"] == "UNVERIFIED_SUCCESS"

    def test_plafond_de_pas_atteint_sans_done_est_un_echec_honnete(self):
        outil = FauxOutil(reponse_chromium={
            "succes_declare": None, "nombre_etapes": 25, "max_etapes": 25})
        resultat = ConnecteurBrowser(outil=outil).executer("naviguer", tache="x")
        assert resultat.statut is Statut.ECHEC
        assert resultat.detail["verification"] == "INCOMPLETE"

    def test_max_steps_est_transmis_a_l_outil(self):
        outil = FauxOutil()
        ConnecteurBrowser(outil=outil).executer("naviguer", tache="x", max_steps=10)
        assert outil.derniers_kwargs["max_steps"] == 10

    def test_sensitive_data_et_allowed_domains_sont_transmis(self):
        outil = FauxOutil()
        ConnecteurBrowser(outil=outil).executer(
            "naviguer", tache="x",
            sensitive_data={"x_pw": "secret"}, allowed_domains=["exemple.test"],
            fichiers_autorises=["/tmp/x.pdf"])
        assert outil.derniers_kwargs["sensitive_data"] == {"x_pw": "secret"}
        assert outil.derniers_kwargs["allowed_domains"] == ["exemple.test"]
        assert outil.derniers_kwargs["available_file_paths"] == ["/tmp/x.pdf"]

    def test_sans_parametres_optionnels_le_plafond_par_defaut_s_applique(self):
        outil = FauxOutil()
        ConnecteurBrowser(outil=outil).executer("naviguer", tache="x")
        assert outil.derniers_kwargs["max_steps"] == module.MAX_ETAPES_DEFAUT


class TestJamaisLightpandaImporte:
    """La frontière de licence (AGPL-3.0-only) : ce module ne doit jamais
    importer quoi que ce soit du dépôt Lightpanda — seulement l'appeler
    par son propre serveur CDP, en HTTP/WebSocket."""

    def test_aucun_import_lightpanda(self):
        import core.connectors.browser as module
        with open(module.__file__, encoding="utf-8") as f:
            contenu = f.read()
        assert "import lightpanda" not in contenu.lower()
