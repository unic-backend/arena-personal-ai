"""Le connecteur GitIngest protege-t-il ce qu'il ne doit jamais lire ?

Deux familles, comme pour Graphify (`test_connecteur_graphify.py`) et
OpenTakeoff :

1. **Le contrat, avec le VRAI moteur GitIngest** — c'est une bibliotheque pure
   Python, sans processus a lancer : contrairement a un moteur externe, il n'y
   a pas de raison de le simuler. Ces tests tournent sur un fixture jetable,
   jamais sur ce depot lui-meme ni un document client.
2. **Les gardes de securite** (chemins sensibles, jeton egare) : sabotables et
   verifies un par un.
"""
import subprocess
from pathlib import Path

import pytest

import core.connectors.gitingest as gitingest_mod
from core.actions.resultat import Statut
from core.connectors.base import ControleAcces, EtatSante
from core.connectors.gitingest import ConnecteurGitIngest
from core.permissions.permission_manager import PermissionManager
from core.permissions.politique import PolitiqueDePermissions


@pytest.fixture
def petit_depot(tmp_path: Path) -> Path:
    """Un depot jetable : README, un module, une config, un .gitignore reel."""
    (tmp_path / "README.md").write_text("# Fixture\n\nProjet fabrique pour le test.\n",
                                        encoding="utf-8")
    (tmp_path / "module.py").write_text(
        "def additionner(a, b):\n    return a + b\n", encoding="utf-8")
    (tmp_path / "config.yaml").write_text("nom: fixture\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("secret.txt\n", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("ne-doit-jamais-apparaitre\n", encoding="utf-8")

    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "-c", "user.email=t@t.t", "-c", "user.name=t",
                    "commit", "-q", "-m", "fixture"], cwd=tmp_path, check=True)
    return tmp_path


@pytest.fixture(autouse=True)
def _sans_jeton_ambiant(monkeypatch):
    """Aucun test d'ici ne doit dependre — ni souffrir — d'un GITHUB_TOKEN
    present par hasard dans l'environnement d'execution."""
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)


class TestCapacitesEtSante:
    def test_une_capacite_declaree(self):
        capacites = ConnecteurGitIngest().capacites()
        assert set(capacites) == {"ingerer"}
        assert capacites["ingerer"].ecriture is False

    def test_authentifier_toujours_vrai(self):
        assert ConnecteurGitIngest().authentifier() is True

    def test_sonde_operationnel_quand_installe(self):
        sante = ConnecteurGitIngest().sonder()
        assert sante.etat is EtatSante.OPERATIONNEL

    def test_sonde_non_configure_si_import_echoue(self, monkeypatch):
        import builtins
        reel = builtins.__import__

        def _import_qui_echoue(nom, *a, **kw):
            if nom == "gitingest":
                raise ImportError("simule")
            return reel(nom, *a, **kw)

        monkeypatch.setattr(builtins, "__import__", _import_qui_echoue)
        sante = ConnecteurGitIngest().sonder()
        assert sante.etat is EtatSante.NON_CONFIGURE


class TestGardesDeChemin:
    @pytest.mark.parametrize("chemin", [
        "~/.ssh", "~/.ssh/id_rsa", "~/.aws/credentials", "~/.gnupg",
        "/tmp/projet/.env", "/tmp/projet/credentials.json",
    ])
    def test_chemin_sensible_refuse(self, chemin):
        resultat = ConnecteurGitIngest().executer_confirmee("ingerer", source=chemin)
        assert resultat.statut is Statut.ECHEC
        assert "refuse" in resultat.message.lower()

    def test_chemin_introuvable_refuse_proprement(self, tmp_path):
        resultat = ConnecteurGitIngest().executer_confirmee(
            "ingerer", source=str(tmp_path / "n-existe-pas"))
        assert resultat.statut is Statut.ECHEC

    def test_aucune_source_est_un_echec_immediat(self):
        resultat = ConnecteurGitIngest().executer_confirmee("ingerer", source="")
        assert resultat.statut is Statut.ECHEC

    def test_une_url_n_est_pas_jugee_par_le_garde_de_chemin_local(self, monkeypatch):
        """`https://...` ne doit jamais passer par `_chemin_local_est_sur` —
        seul GitIngest lui-meme juge une URL (existence, jeton, branche)."""
        appele = {"oui": False}
        monkeypatch.setattr(gitingest_mod, "_chemin_local_est_sur",
                            lambda s: appele.__setitem__("oui", True))
        ConnecteurGitIngest().executer_confirmee("ingerer", source="https://exemple.test/x/y")
        assert appele["oui"] is False


class TestLeVraiMoteur:
    """GitIngest est une bibliotheque pure Python : le vrai moteur tourne
    dans chaque test, sur un fixture jetable — jamais sur un document client."""

    def test_ingestion_locale_respecte_gitignore(self, petit_depot):
        resultat = ConnecteurGitIngest().executer_confirmee("ingerer", source=str(petit_depot))

        assert resultat.statut is Statut.SUCCES, resultat.message
        assert "secret.txt" not in resultat.detail["contenu"]
        assert "secret.txt" not in resultat.detail["arbre"]
        assert "additionner" in resultat.detail["contenu"]
        assert resultat.detail["octets_contenu"] > 0
        assert resultat.preuve == str(petit_depot)

    def test_ingestion_locale_depuis_une_boucle_asyncio_deja_active(self, petit_depot):
        """Le vrai chemin d'appel : `registre.executer(...)` est appele en
        clair depuis des routes/agents deja `async def` — verifie
        (`chat.py`, `plaquiste_agent.py`). `asyncio.run()` y leverait
        `RuntimeError: cannot be called from a running event loop`."""
        import asyncio

        async def _depuis_une_route():
            return ConnecteurGitIngest().executer_confirmee("ingerer", source=str(petit_depot))

        resultat = asyncio.run(_depuis_une_route())

        assert resultat.statut is Statut.SUCCES, resultat.message
        assert "additionner" in resultat.detail["contenu"]

    def test_un_jeton_errant_dans_l_environnement_ne_casse_pas_une_ingestion_locale(
        self, petit_depot, monkeypatch
    ):
        """Trouve le 04/09/2026 : `resolve_token()` (amont) relit
        `GITHUB_TOKEN` meme quand rien n'en a besoin, et leve si sa forme
        n'est pas celle d'un vrai jeton GitHub."""
        monkeypatch.setenv("GITHUB_TOKEN", "pas-un-vrai-jeton")

        resultat = ConnecteurGitIngest().executer_confirmee("ingerer", source=str(petit_depot))

        assert resultat.statut is Statut.SUCCES, resultat.message

    def test_source_invalide_est_un_echec_pas_un_crash(self, tmp_path):
        """Un dossier reel mais qui n'est ni une URL ni un depot Git valide
        pour GitIngest (ex. vide de tout fichier lisible) ne doit jamais
        lever hors du connecteur."""
        vide = tmp_path / "vide"
        vide.mkdir()
        resultat = ConnecteurGitIngest().executer_confirmee("ingerer", source=str(vide))
        assert resultat.statut in (Statut.SUCCES, Statut.ECHEC)  # jamais une exception


class TestLeDelaiEstConfigurable:
    """Mesure du 09/09/2026 : un appelant qui veut « un coup d'oeil rapide »
    (`RepoEngineerAgent`) n'a pas besoin d'attendre les 180 s par defaut
    avant que son repli sur l'arborescence ne se declenche."""

    def test_un_delai_plus_court_est_respecte(self, petit_depot, monkeypatch):
        import asyncio

        async def _lente(*args, **kwargs):
            await asyncio.sleep(1.0)
            return "resume", "arbre", "contenu"

        monkeypatch.setattr(gitingest_mod, "DELAI_SECONDES", 180.0)
        monkeypatch.setattr("gitingest.ingest_async", _lente)

        resultat = ConnecteurGitIngest().executer_confirmee(
            "ingerer", source=str(petit_depot), delai=0.2)

        assert resultat.statut is Statut.ECHEC
        assert "0" in resultat.message  # « a depasse 0 s » : le delai COURT, pas le defaut

    def test_un_delai_demande_ne_depasse_jamais_le_plafond(self, petit_depot, monkeypatch):
        """Demander plus que `DELAI_SECONDES` ne l'etend pas : le plafond
        reste le maximum absolu, jamais un appelant qui en decide seul."""
        import asyncio

        async def _lente(*args, **kwargs):
            await asyncio.sleep(1.0)
            return "resume", "arbre", "contenu"

        monkeypatch.setattr(gitingest_mod, "DELAI_SECONDES", 0.2)
        monkeypatch.setattr("gitingest.ingest_async", _lente)

        resultat = ConnecteurGitIngest().executer_confirmee(
            "ingerer", source=str(petit_depot), delai=9999)

        assert resultat.statut is Statut.ECHEC
        assert "0" in resultat.message  # plafonne a DELAI_SECONDES (0.2s), pas 9999

    def test_un_delai_invalide_retombe_sur_le_defaut(self, petit_depot):
        """Une valeur qui ne se convertit pas en nombre ne doit jamais faire
        lever le connecteur : elle retombe sur le comportement par defaut."""
        resultat = ConnecteurGitIngest().executer_confirmee(
            "ingerer", source=str(petit_depot), delai="pas-un-nombre")

        assert resultat.statut is Statut.SUCCES, resultat.message


class TestLeCoupeCircuitDePermission:
    def test_refuse_par_defaut_sans_politique(self, tmp_path):
        """Sans regle ecrite pour `gitingest.read`, `ControleAcces` refuse par
        defaut — la meme discipline que tout le reste de ce depot."""
        connecteur = ConnecteurGitIngest(acces=ControleAcces(
            permissions=PermissionManager(config_path=str(tmp_path / "booleens.yaml")),
            politique=PolitiqueDePermissions(chemin=tmp_path / "politique-vide.yaml")))

        resultat = connecteur.executer("ingerer", source=str(tmp_path))

        assert resultat.statut is Statut.REFUSE


class TestLaVraiePolitiqueLivree:
    def test_lecture_permise_dans_le_depot_reel(self):
        from core.permissions.politique import FICHIER_POLITIQUE, PolitiqueDePermissions

        regle = PolitiqueDePermissions(chemin=FICHIER_POLITIQUE).regle("gitingest", "read")

        assert regle is not None, "gitingest.read a disparu de la politique livree"
        assert regle.get("decision") == "ALLOWED"
