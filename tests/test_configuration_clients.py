"""Les clients voient-ils réellement les modèles que l'API sert ?

`librechat.yaml` déclare `fetch: false` : LibreChat n'affiche que la liste
écrite dans ce fichier, et ignore ce que `/v1/models` répond. Les deux listes
sont donc deux vérités séparées, et elles ont déjà divergé — `arena-fresh` a
été servi par l'API pendant toute une journée sans jamais apparaître dans le
menu. Mesuré le 2026-08-26.

Ces tests tiennent les deux côtés ensemble, et vérifient qu'aucun secret ne
revient en clair dans les fichiers de configuration.
"""
import asyncio
import re
from pathlib import Path

import pytest
import yaml

from apps.backend.routers import openai_gateway

RACINE = Path(__file__).resolve().parent.parent
LIBRECHAT = RACINE / "librechat.yaml"
COMPOSE = RACINE / "docker-compose.yml"

VARIABLES_SECRETES = (
    "ARENA_API_KEY", "CREDS_KEY", "JWT_SECRET", "JWT_REFRESH_SECRET", "WEBUI_SECRET_KEY",
)


def modeles_de_l_api() -> set[str]:
    return {modele["id"] for modele in asyncio.run(openai_gateway.list_openai_models())["data"]}


def modeles_de_librechat() -> set[str]:
    config = yaml.safe_load(LIBRECHAT.read_text(encoding="utf-8"))
    return set(config["endpoints"]["custom"][0]["models"]["default"])


class TestListesDeModeles:
    def test_librechat_montre_exactement_ce_que_l_api_sert(self):
        api, librechat = modeles_de_l_api(), modeles_de_librechat()
        assert librechat == api, (
            f"invisibles dans LibreChat : {sorted(api - librechat)} · "
            f"annoncés mais inexistants : {sorted(librechat - api)}"
        )

    def test_le_studio_est_dans_le_menu(self):
        assert "arena-studio" in modeles_de_librechat()

    def test_l_information_fraiche_est_dans_le_menu(self):
        """Le cas qui a échoué : servi par l'API, absent du menu."""
        assert "arena-fresh" in modeles_de_librechat()


class TestAucunSecretEnClair:
    """Ces deux fichiers ont déjà porté des clés en clair. Deux fois."""

    def test_librechat_lit_sa_cle_dans_l_environnement(self):
        config = yaml.safe_load(LIBRECHAT.read_text(encoding="utf-8"))
        cle = config["endpoints"]["custom"][0]["apiKey"]
        assert cle == "${ARENA_API_KEY}", f"clé écrite en dur : {cle[:4]}…"

    @pytest.mark.parametrize("variable", VARIABLES_SECRETES)
    def test_compose_ne_fixe_aucune_valeur_en_dur(self, variable):
        texte = COMPOSE.read_text(encoding="utf-8")
        for ligne in re.findall(rf"^\s*-\s*{variable}=(.*)$", texte, flags=re.M):
            assert ligne.strip().startswith("${"), (
                f"{variable} porte une valeur en dur dans docker-compose.yml"
            )

    def test_compose_ne_declare_plus_l_attribut_version(self):
        """Docker Compose l'ignore et prévient à chaque commande."""
        assert not COMPOSE.read_text(encoding="utf-8").lstrip().startswith("version:")
