"""Le menu est court ; les capacités, elles, restent toutes joignables.

Décision du propriétaire, 2026-08-26 : LibreChat ne propose plus que
`arena-core` et `arena-coder`. Sa raison — *« les utilisateurs ne connaissent
pas des modèles, ils ouvrent le premier qui apparaît et pensent que c'est celui
qui fait tout »*.

Le danger d'un menu court n'est pas le menu : c'est qu'une capacité devienne
**inatteignable** parce que le seul chemin vers elle était son nom. Ces tests
tiennent l'inverse : pour chaque nom retiré du menu, une intention existe, elle
est déclarée spécialisée, et l'aiguillage appelle bien l'agent correspondant.

Ils vérifient aussi qu'aucun secret ne revient en clair — ces deux fichiers en
ont déjà porté deux fois.
"""
import re
from pathlib import Path

import pytest
import yaml

from apps.backend.config import AGENTS_SPECIALISES
from apps.backend.routers import chat as routeur_chat
from apps.backend.routers.chat import ChatRequest, dispatch_request

RACINE = Path(__file__).resolve().parent.parent
LIBRECHAT = RACINE / "librechat.yaml"
COMPOSE = RACINE / "docker-compose.yml"

MENU_ATTENDU = {"arena-core", "arena-coder"}

VARIABLES_SECRETES = (
    "ARENA_API_KEY", "CREDS_KEY", "JWT_SECRET", "JWT_REFRESH_SECRET", "WEBUI_SECRET_KEY",
)

# Chaque nom retiré du menu, et l'intention qui doit le remplacer depuis
# `arena-core`. Le nom de l'objet est celui que l'aiguillage doit appeler.
CAPACITES_SANS_ENTREE_DE_MENU = {
    "arena-swe-agent": ("SWE_FIX", "swe_agent"),
    "arena-repo-engineer": ("REPO_ENGINEERING", "repo_engineer"),
    "arena-deep-research": ("DEEP_RESEARCH", "researcher_agent"),
    "arena-fresh": ("FRESH_INFO", "fresh_agent"),
    "arena-browser": ("BROWSER", "browser_agent"),
    "arena-studio": ("STUDIO", "lancer_studio"),
}


def menu_de_librechat() -> set[str]:
    config = yaml.safe_load(LIBRECHAT.read_text(encoding="utf-8"))
    return set(config["endpoints"]["custom"][0]["models"]["default"])


class TestMenuCourt:
    def test_le_menu_ne_propose_que_deux_entrees(self):
        assert menu_de_librechat() == MENU_ATTENDU

    @pytest.mark.parametrize("modele,attendu", sorted(CAPACITES_SANS_ENTREE_DE_MENU.items()))
    def test_chaque_capacite_retiree_a_une_intention(self, modele, attendu):
        intention, _ = attendu
        assert intention in AGENTS_SPECIALISES, (
            f"{modele} n'est plus dans le menu et {intention} n'est pas aiguillée : "
            "la capacité est devenue inatteignable"
        )


class TestRienN_estDevenuInatteignable:
    """La preuve par l'exécution : l'aiguillage appelle bien l'agent attendu."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("modele,attendu", sorted(CAPACITES_SANS_ENTREE_DE_MENU.items()))
    async def test_l_intention_atteint_le_bon_agent(self, modele, attendu, monkeypatch):
        intention, nom_objet = attendu
        appels = []

        async def _double_async(*args, **kw):
            appels.append(nom_objet)
            return {"response": "atteint", "agent": nom_objet}

        cible = getattr(routeur_chat, nom_objet)
        if nom_objet == "lancer_studio":
            monkeypatch.setattr(routeur_chat, nom_objet, _double_async)
        else:
            monkeypatch.setattr(cible, "run", _double_async)

        resultat = await dispatch_request(ChatRequest(prompt="peu importe"), intent=intention)

        assert appels == [nom_objet], f"{intention} n'a pas atteint {nom_objet}"
        assert resultat.get("response") == "atteint"

    @pytest.mark.asyncio
    async def test_les_documents_restent_interrogeables(self, monkeypatch):
        """RAG_DOCS passe par un outil, pas par un agent : cas à part."""
        monkeypatch.setattr(
            routeur_chat.lightrag_tool, "query", lambda prompt, mode=None: "extrait de document"
        )
        resultat = await dispatch_request(ChatRequest(prompt="dans mes documents"), intent="RAG_DOCS")
        assert resultat["response"] == "extrait de document"

    @pytest.mark.asyncio
    async def test_le_graphe_reste_interrogeable(self, monkeypatch):
        monkeypatch.setattr(
            routeur_chat.graphrag_tool, "query_global", lambda prompt: {"response": "liens trouvés"}
        )
        resultat = await dispatch_request(ChatRequest(prompt="graphrag"), intent="GRAPHRAG")
        assert resultat["response"] == "liens trouvés"


class TestAucunSecretEnClair:
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
        assert not COMPOSE.read_text(encoding="utf-8").lstrip().startswith("version:")
