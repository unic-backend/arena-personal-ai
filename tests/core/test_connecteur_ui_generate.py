"""Le connecteur de generation d'interface garde-t-il sa seule vraie ligne ?

Contexte (DEC-0050) : OpenUI (wandb/openui, Apache-2.0) verifie reel — son
depot n'a PAS change de forme (contrairement a KrillinAI/OpenCreator), mais
sa vraie capacite est une TECHNIQUE de prompt cote client
(`frontend/src/api/openai.ts::systemPrompt`), pas son serveur FastAPI qui
exige une connexion GitHub. Ce module reprend la technique ; le serveur
d'OpenUI n'est jamais lance.

Deux familles de tests :
1. **Logique pure** (`core/production/ui_generation.py`) : extraction de
   code, garde de script externe.
2. **Connecteur** : jamais d'ecriture avec un script hors liste fermee —
   sabotage-verifie.
"""
import pytest

from core.actions.resultat import Statut
from core.connectors.base import EtatSante
from core.connectors.ui_generate import ConnecteurUiGenerate
from core.production.ui_generation import (
    DOMAINES_SCRIPT_AUTORISES,
    extraire_code,
    prompt_systeme,
    valider_scripts_externes,
)


class TestExtraireCode:
    def test_un_bloc_html_est_extrait(self):
        reponse = "Voici :\n```html\n<!doctype html><body>Bonjour</body>\n```\nVoila."
        code = extraire_code(reponse)
        assert code == "<!doctype html><body>Bonjour</body>"

    def test_un_bloc_react_est_extrait(self):
        reponse = "```react\nfunction App() { return <div>x</div>; }\n```"
        assert "function App" in extraire_code(reponse)

    def test_sans_bloc_de_code_rend_none(self):
        assert extraire_code("Je ne peux pas generer ca.") is None

    def test_reponse_vide_rend_none(self):
        assert extraire_code("") is None

    def test_bloc_vide_rend_none(self):
        assert extraire_code("```html\n\n```") is None


class TestValiderScriptsExternes:
    def test_tailwind_cdn_autorise(self):
        assert valider_scripts_externes(
            '<script src="https://cdn.tailwindcss.com"></script>') == []

    @pytest.mark.parametrize("domaine", sorted(DOMAINES_SCRIPT_AUTORISES))
    def test_chaque_domaine_de_la_liste_est_accepte(self, domaine):
        assert valider_scripts_externes(f'<script src="https://{domaine}/x.js"></script>') == []

    def test_un_domaine_hors_liste_est_refuse(self):
        problemes = valider_scripts_externes(
            '<script src="https://evil.example.com/payload.js"></script>')
        assert len(problemes) == 1
        assert "evil.example.com" in problemes[0]

    def test_plusieurs_scripts_certains_hors_liste(self):
        code = (
            '<script src="https://cdn.tailwindcss.com"></script>'
            '<script src="https://tracker.ads.example/beacon.js"></script>'
        )
        problemes = valider_scripts_externes(code)
        assert len(problemes) == 1
        assert "tracker.ads.example" in problemes[0]

    def test_aucun_script_est_sans_probleme(self):
        assert valider_scripts_externes("<body><h1>Bonjour</h1></body>") == []

    def test_sous_domaine_non_liste_est_refuse(self):
        """`evil.cdn.tailwindcss.com.attacker.test` ne doit pas passer parce
        que la chaine contient le nom du domaine autorise."""
        problemes = valider_scripts_externes(
            '<script src="https://cdn.tailwindcss.com.attacker.test/x.js"></script>')
        assert len(problemes) == 1


class TestPromptSysteme:
    def test_html_demande_le_cdn_tailwind(self):
        assert "cdn.tailwindcss.com" in prompt_systeme("html")

    def test_framework_different_de_html_est_mentionne(self):
        assert "react" in prompt_systeme("react").lower()


PARAMETRES_MINIMAUX = {"code": "<!doctype html><body>Bonjour</body>", "framework": "html",
                       "titre": "Test"}


class TestExecutionReelle:
    def test_genere_un_vrai_fichier(self, tmp_path):
        connecteur = ConnecteurUiGenerate(dossier=tmp_path)
        resultat = connecteur.executer_confirmee("generer", **PARAMETRES_MINIMAUX)
        assert resultat.statut is Statut.SUCCES, resultat.message
        chemin = tmp_path
        fichiers = list(chemin.glob("ui-test-*.html"))
        assert len(fichiers) == 1
        assert fichiers[0].read_text(encoding="utf-8") == PARAMETRES_MINIMAUX["code"]

    def test_framework_inconnu_est_un_echec(self, tmp_path):
        connecteur = ConnecteurUiGenerate(dossier=tmp_path)
        resultat = connecteur.executer_confirmee(
            "generer", code="x", framework="rust", titre="t")
        assert resultat.statut is Statut.ECHEC

    def test_code_vide_est_un_echec(self, tmp_path):
        connecteur = ConnecteurUiGenerate(dossier=tmp_path)
        resultat = connecteur.executer_confirmee("generer", code="", framework="html", titre="t")
        assert resultat.statut is Statut.ECHEC

    def test_un_script_externe_refuse_bloque_toute_l_ecriture(self, tmp_path):
        """Aucun fichier ne doit exister, meme partiellement, quand un
        script externe est refuse — pas un avertissement a cote d'un
        fichier ecrit quand meme."""
        connecteur = ConnecteurUiGenerate(dossier=tmp_path)
        code = '<script src="https://evil.example.com/x.js"></script>'
        resultat = connecteur.executer_confirmee(
            "generer", code=code, framework="html", titre="t")
        assert resultat.statut is Statut.ECHEC
        assert list(tmp_path.glob("*.html")) == []

    def test_code_trop_volumineux_est_un_echec(self, tmp_path):
        connecteur = ConnecteurUiGenerate(dossier=tmp_path)
        enorme = "x" * 3_000_000
        resultat = connecteur.executer_confirmee(
            "generer", code=enorme, framework="html", titre="t")
        assert resultat.statut is Statut.ECHEC

    def test_url_seulement_si_ecrit_dans_rendered_dir(self, tmp_path, monkeypatch):
        import core.connectors.ui_generate as module
        monkeypatch.setattr(module, "RENDERED_DIR", tmp_path)
        connecteur = ConnecteurUiGenerate()
        resultat = connecteur.executer_confirmee("generer", **PARAMETRES_MINIMAUX)
        assert resultat.statut is Statut.SUCCES, resultat.message
        assert resultat.detail["url"].startswith("/media/rendered/")

    def test_pas_d_url_hors_rendered_dir(self, tmp_path):
        connecteur = ConnecteurUiGenerate(dossier=tmp_path / "ailleurs")
        resultat = connecteur.executer_confirmee("generer", **PARAMETRES_MINIMAUX)
        assert resultat.statut is Statut.SUCCES, resultat.message
        assert "url" not in resultat.detail

    def test_sonde_toujours_operationnelle(self):
        assert ConnecteurUiGenerate().sonder().etat is EtatSante.OPERATIONNEL


class TestLaVraiePolitiqueLivree:
    def test_generer_reste_sous_write_files_dans_le_depot_reel(self):
        from core.permissions.politique import FICHIER_POLITIQUE, PolitiqueDePermissions

        regle = PolitiqueDePermissions(chemin=FICHIER_POLITIQUE).regle("ui_generate", "document")
        assert regle is not None, "ui_generate.document a disparu de la politique livree"
        assert regle.get("decision") == "ALLOWED"
        assert regle.get("interrupteur") == "WRITE_FILES"
