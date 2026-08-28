"""Le projet s'appelle Usman depuis le 2026-08-26. Ce qui doit rester vrai.

Un renommage casse par les endroits qu'on oublie, pas par ceux qu'on change.
Deux dangers, et un test pour chacun :

- le `.env` du propriétaire porte encore les anciens noms. `reglage()` accepte
  les deux, en le disant dans les journaux — un repli silencieux devient
  permanent ;
- un nom d'agent ou de modèle laissé en `arena-` deviendrait injoignable.
"""
import logging
from pathlib import Path

import pytest

from apps.backend.config import reglage

RACINE = Path(__file__).resolve().parent.parent


class TestLectureDesReglages:
    def test_le_nouveau_nom_est_lu(self, monkeypatch):
        monkeypatch.setenv("USMAN_API_KEY", "valeur-neuve")
        assert reglage("API_KEY") == "valeur-neuve"

    def test_l_ancien_nom_depanne(self, monkeypatch):
        """Le .env du propriétaire n'est pas encore renommé : rien ne doit casser."""
        monkeypatch.delenv("USMAN_API_KEY", raising=False)
        monkeypatch.setenv("ARENA_API_KEY", "valeur-ancienne")
        assert reglage("API_KEY") == "valeur-ancienne"

    def test_le_nouveau_nom_l_emporte_sur_l_ancien(self, monkeypatch):
        monkeypatch.setenv("USMAN_API_KEY", "neuve")
        monkeypatch.setenv("ARENA_API_KEY", "ancienne")
        assert reglage("API_KEY") == "neuve"

    def test_le_repli_est_annonce_dans_les_journaux(self, monkeypatch, caplog):
        """Un repli qu'on ne voit pas devient permanent."""
        monkeypatch.delenv("USMAN_RATE_LIMIT_REQUESTS", raising=False)
        monkeypatch.setenv("ARENA_RATE_LIMIT_REQUESTS", "42")

        with caplog.at_level(logging.WARNING, logger="usman.config"):
            assert reglage("RATE_LIMIT_REQUESTS") == "42"

        assert "ARENA_RATE_LIMIT_REQUESTS" in caplog.text
        assert "USMAN_RATE_LIMIT_REQUESTS" in caplog.text

    def test_sans_rien_le_defaut_s_applique(self, monkeypatch):
        monkeypatch.delenv("USMAN_INEXISTANT", raising=False)
        monkeypatch.delenv("ARENA_INEXISTANT", raising=False)
        assert reglage("INEXISTANT", "repli") == "repli"

    def test_une_valeur_vide_reste_une_valeur(self, monkeypatch):
        """Vider volontairement une variable n'est pas la même chose que l'omettre."""
        monkeypatch.setenv("USMAN_API_KEY", "")
        monkeypatch.setenv("ARENA_API_KEY", "ancienne")
        assert reglage("API_KEY") == ""


class TestAucunNomOublie:
    """Le seul fichier de réglages que l'utilisateur lit encore.

    `docker-compose.yml` et `librechat.yaml` en faisaient partie jusqu'au
    2026-08-28. Ils sont retirés : le propriétaire a sa propre interface, et ces
    deux fichiers étaient les derniers à réclamer les quatre clés mortes.
    """

    @pytest.mark.parametrize("fichier", [".env.example"])
    def test_plus_aucune_variable_arena(self, fichier):
        texte = (RACINE / fichier).read_text(encoding="utf-8")
        restes = [ligne for ligne in texte.splitlines() if "ARENA_" in ligne]
        assert restes == [], f"variables non renommées dans {fichier} : {restes}"


class TestEncodage:
    """`.env.example` mélangeait UTF-8 et cp1252 : illisible pour un outil."""

    def test_le_fichier_d_exemple_est_lisible_en_utf8(self):
        (RACINE / ".env.example").read_text(encoding="utf-8")

    def test_les_accents_ne_sont_pas_abimes(self):
        texte = (RACINE / ".env.example").read_text(encoding="utf-8")
        assert "Désactivé" in texte
        assert "SÉCURITÉ" in texte
        assert "�" not in texte, "un caractère de remplacement subsiste"


class TestIdentifiantsDeModeles:
    """Les anciens identifiants doivent continuer de fonctionner."""

    def test_l_api_ne_sert_plus_aucun_nom_arena(self):
        import asyncio

        from apps.backend.routers import openai_gateway
        modeles = asyncio.run(openai_gateway.list_openai_models())
        restes = [m["id"] for m in modeles["data"] if m["id"].startswith("arena-")]
        assert restes == [], f"identifiants non renommés : {restes}"

    @pytest.mark.parametrize("ancien,neuf", [
        ("arena-core", "usman-chat"),
        ("arena-video", "usman-video"),
        ("arena-fresh", "usman-fresh"),
    ])
    def test_une_conversation_ouverte_hier_marche_encore(self, ancien, neuf):
        """LibreChat garde l'identifiant du modèle dans l'historique."""
        from apps.backend.routers.openai_gateway import ANCIENS_NOMS
        assert ANCIENS_NOMS[ancien] == neuf

    def test_la_detection_de_secrets_couvre_les_deux_noms(self):
        """Renommer une règle ne doit pas cesser de détecter une clé en dur.

        Le premier jet de ce test affirmait autre chose et a échoué — pour une
        bonne raison : la règle ne connaissait que `ARENA_API_KEY`. Une clé
        écrite en dur sous le nouveau nom serait passée inaperçue.
        """
        import tomllib
        config = tomllib.loads((RACINE / ".gitleaks.toml").read_text(encoding="utf-8"))
        regles = {r["id"]: r for r in config["rules"]}

        assert "usman-librechat-apikey" in regles
        assert "usman-compose-secret" in regles

        motif = regles["usman-compose-secret"]["regex"]
        assert "USMAN_API_KEY" in motif, "le nouveau nom n'est pas surveille"
        assert "ARENA_API_KEY" in motif, "l'ancien nom cesse d'etre surveille"

