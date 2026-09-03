"""Le connecteur UI/UX Pro Max : lecture pure, résultats mesurés.

Le moteur est **MIT** et tient en Python pur — aucune dépendance hors
bibliothèque standard. Il vit malgré tout hors du dépôt, par la convention de
tous les moteurs externes ici (`test_moteurs_externes_restent_dehors.py`).

Deux points tiennent tout le reste :

- **Aucune écriture.** Le moteur sait persister un design system sur le disque
  (`--persist`) ; cette option n'est pas exposée. Une capacité de raisonnement
  qui demanderait des droits d'écriture « au cas où » les élargirait sans usage.
- **Rien n'est composé à la place du moteur.** Un design system vide se
  rapporte vide ; il ne se remplit pas de valeurs plausibles.
"""
import subprocess
from pathlib import Path

import pytest

from core.connectors import ui_ux_pro_max as module
from core.connectors.base import EtatSante
from core.connectors.ui_ux_pro_max import DOMAINES, ConnecteurUiUxProMax

RACINE = Path(__file__).resolve().parent.parent
MOTEUR = RACINE / "tools" / "design" / "ui_ux_pro_max" / "src" / "ui-ux-pro-max" / "scripts" / "search.py"

moteur_reel = pytest.mark.skipif(
    not MOTEUR.is_file(),
    reason="UI/UX Pro Max non installe : mesure impossible, donc non simulee")


def _cap(nom):
    return ConnecteurUiUxProMax().capacites()[nom]


def _reponse(charge: str) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=charge, stderr="")


@pytest.fixture
def installe(monkeypatch, tmp_path):
    moteur = tmp_path / "search.py"
    moteur.write_text("")
    monkeypatch.setattr(module, "UIUX_ROOT", tmp_path)
    monkeypatch.setattr(module, "UIUX_SEARCH", moteur)
    return tmp_path


class TestSonde:
    def test_moteur_absent_nest_pas_une_panne(self, monkeypatch, tmp_path):
        monkeypatch.setattr(module, "UIUX_ROOT", tmp_path / "nulle_part")
        sante = ConnecteurUiUxProMax().sonder()

        assert sante.etat == EtatSante.NON_CONFIGURE
        assert sante.ce_qui_manque

    def test_un_script_sans_ses_donnees_est_une_panne(self, installe, monkeypatch):
        """**Le contrôle qui compte.** Le moteur lit une douzaine de CSV : un
        dépôt à moitié copié garderait `search.py` sans ses tables, et conclure
        « opérationnel » de sa seule présence annoncerait une capacité qui
        échouerait au premier appel."""
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: _reponse(""))

        assert ConnecteurUiUxProMax().sonder().etat == EtatSante.EN_PANNE


class TestRefus:
    def test_sans_moteur_rien_nest_tente(self, monkeypatch, tmp_path):
        monkeypatch.setattr(module, "UIUX_SEARCH", tmp_path / "nulle_part.py")
        lance = []
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: lance.append(a))

        resultat = ConnecteurUiUxProMax()._executer(_cap("chercher"), requete="dashboard")

        assert resultat.statut.value == "NOT_CONFIGURED"
        assert lance == []

    def test_un_domaine_inconnu_est_refuse_avec_la_liste(self, installe, monkeypatch):
        """Refusé ici plutôt que par le moteur : la liste fermée est connue
        d'avance, et nommer les domaines valables est plus utile qu'un code de
        sortie."""
        lance = []
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: lance.append(a))

        resultat = ConnecteurUiUxProMax()._executer(
            _cap("chercher"), requete="x", domaine="inexistant")

        assert resultat.statut.value != "SUCCESS"
        assert "style" in resultat.message
        assert lance == []

    def test_un_design_system_vide_se_rapporte_vide(self, installe, monkeypatch):
        """Rien n'est composé à la place du moteur."""
        monkeypatch.setattr(subprocess, "run",
                            lambda *a, **k: _reponse('{"design_system": {}}'))

        resultat = ConnecteurUiUxProMax()._executer(
            _cap("design_system"), requete="site vitrine")

        assert resultat.statut.value != "SUCCESS"

    def test_une_demande_vide_est_refusee(self, installe):
        resultat = ConnecteurUiUxProMax()._executer(_cap("chercher"), requete="   ")

        assert resultat.statut.value != "SUCCESS"


class TestPermissions:
    def test_la_capacite_est_en_lecture_seule(self):
        for capacite in ConnecteurUiUxProMax().capacites().values():
            assert capacite.ecriture is False, (
                "une capacite de raisonnement ne demande pas de droits d'ecriture")
            assert capacite.action == "read"

    def test_le_service_nautorise_que_la_lecture(self):
        import yaml
        regles = yaml.safe_load(
            (RACINE / "config" / "permissions_services.yaml").read_text(encoding="utf-8"))
        service = regles["services"]["design_ui"]

        assert set(service) == {"read"}, (
            "une action d'ecriture est apparue sur une capacite de lecture")
        assert service["read"]["decision"] == "ALLOWED"

    def test_loption_decriture_du_moteur_nest_pas_exposee(self):
        """`--persist` écrit des fichiers. Le connecteur ne doit jamais la
        passer, sinon la capacité écrirait sans confirmation."""
        source = (RACINE / "core" / "connectors" / "ui_ux_pro_max.py").read_text(encoding="utf-8")
        code = [ligne for ligne in source.splitlines()
                if not ligne.strip().startswith("#")]

        assert not any('"--persist"' in ligne or "'--persist'" in ligne for ligne in code)


class TestMoteurReel:
    """Le moteur, pour de vrai. Sauté s'il n'est pas installé — jamais simulé."""

    @moteur_reel
    def test_le_moteur_repond(self):
        assert ConnecteurUiUxProMax().sonder().etat == EtatSante.OPERATIONNEL

    @moteur_reel
    @pytest.mark.parametrize("domaine,requete", [
        ("style", "dashboard"), ("color", "blue trust"),
        ("typography", "sans serif"), ("ux", "form validation"),
        ("landing", "conversion"), ("chart", "time series"),
    ])
    def test_chaque_domaine_annonce_rend_vraiment_des_resultats(self, domaine, requete):
        """Un domaine déclaré mais muet serait une capacité annoncée sans
        exister — le défaut que ce dépôt refuse partout.

        Les requêtes sont **en anglais** : les données du moteur le sont, et
        « dashboard » sur le domaine `ux` rendait zéro alors que le domaine
        fonctionne très bien (mesure du 03/09/2026). Le premier essai de ce
        test accusait le moteur d'un défaut qui était dans sa question.
        """
        resultat = ConnecteurUiUxProMax()._executer(
            _cap("chercher"), requete=requete, domaine=domaine, max_resultats=2)

        assert resultat.statut.value == "SUCCESS"
        assert (resultat.detail or {})["resultats"], f"{domaine} ne rend rien"

    @moteur_reel
    def test_zero_resultat_nomme_la_cause_probable(self):
        """Un zéro muet se lirait « il n'existe rien sur ce sujet »."""
        resultat = ConnecteurUiUxProMax()._executer(
            _cap("chercher"), requete="accessibilité formulaire",
            domaine="ux", max_resultats=2)

        assert (resultat.detail or {})["resultats"] == []
        assert "anglais" in resultat.message

    @moteur_reel
    def test_un_design_system_porte_ses_sections(self):
        resultat = ConnecteurUiUxProMax()._executer(
            _cap("design_system"), requete="application de gestion de chantier",
            projet="UniC")

        systeme = (resultat.detail or {}).get("design_system") or {}
        for section in ("style", "colors", "typography"):
            assert section in systeme, f"section « {section} » absente"

    @moteur_reel
    def test_les_domaines_declares_sont_ceux_du_moteur(self):
        """La liste fermée du connecteur doit refléter le moteur installé, pas
        une liste recopiée qui aurait dérivé."""
        # Le moteur a lui aussi un module `core` : un `import core` ordinaire
        # rendait celui d'ARENA, deja charge (« cannot import name CSV_CONFIG
        # from core »). On charge donc son fichier par son CHEMIN, sous un nom
        # qui n'entre en collision avec rien.
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "_uiux_core_du_moteur", MOTEUR.parent / "core.py")
        module_moteur = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module_moteur)

        assert set(DOMAINES) == set(module_moteur.CSV_CONFIG)
