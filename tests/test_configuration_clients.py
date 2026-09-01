"""Aucune capacité n'est devenue injoignable, et aucune clé morte n'est réclamée.

Il y avait un menu, dans `librechat.yaml` : quatre entrées, décidées par le
propriétaire. Le danger d'un menu court n'était pas le menu, c'était qu'une
capacité devienne **inatteignable** parce que le seul chemin vers elle était son
nom. Ces tests tiennent l'inverse, et ils le tiennent encore : pour chaque
capacité sans entrée de menu, une intention existe, elle est déclarée
spécialisée, et l'aiguillage appelle bien l'agent correspondant.

**Le 2026-08-28, LibreChat et Open WebUI sont retirés du dépôt** — le
propriétaire a sa propre interface. Ces deux clients étaient les derniers à
réclamer `CREDS_KEY`, `JWT_SECRET`, `JWT_REFRESH_SECRET` et `WEBUI_SECRET_KEY`,
quatre valeurs qui ont fuité dans l'historique public. La dernière classe de ce
fichier vérifie que plus rien, dans ce que le système lit, ne les redemande :
c'est ce qui rend cette fuite définitivement sans effet.
"""
from pathlib import Path

import pytest

from apps.backend.config import AGENTS_SPECIALISES
from apps.backend.routers import chat as routeur_chat
from apps.backend.routers.chat import ChatRequest, dispatch_request

RACINE = Path(__file__).resolve().parent.parent

#: Les quatre clés qui n'ouvrent plus rien. Les remettre dans un fichier lu par
#: le système, c'est redonner de la valeur a des valeurs publiquement connues.
CLES_MORTES = ("CREDS_KEY", "JWT_SECRET", "JWT_REFRESH_SECRET", "WEBUI_SECRET_KEY")

#: Les clients tiers retirés. Leurs fichiers ne doivent pas revenir sans que
#: quelqu'un le décide — et le décide en connaissance de la fuite.
FICHIERS_RETIRES = ("librechat.yaml", "docker-compose.yml")

#: Ce que le système lit vraiment au démarrage. Les documents (`docs/`,
#: `documents/`) sont exclus : ils PARLENT des clés mortes, c'est leur rôle.
DOSSIERS_LUS = ("apps", "core", "tools", "agents", "config")

# Chaque nom retiré du menu, et l'intention qui doit le remplacer depuis
# `usman-chat`. Le nom de l'objet est celui que l'aiguillage doit appeler.
CAPACITES_SANS_ENTREE_DE_MENU = {
    "usman-fix": ("SWE_FIX", "swe_agent"),
    "usman-repo": ("REPO_ENGINEERING", "repo_engineer"),
    "usman-research": ("DEEP_RESEARCH", "researcher_agent"),
    "usman-fresh": ("FRESH_INFO", "fresh_agent"),
    "usman-browser": ("BROWSER", "browser_agent"),
}


class TestMenuCourt:
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


class TestLesClesMortesNeServentPlus:
    """Quatre valeurs publiquement connues ne doivent plus rien ouvrir."""

    @pytest.mark.parametrize("fichier", FICHIERS_RETIRES)
    def test_les_clients_tiers_ne_sont_pas_revenus(self, fichier):
        assert not (RACINE / fichier).exists(), (
            f"{fichier} est de retour : il réclame des clés qui ont fuité en public")

    @pytest.mark.parametrize("cle", CLES_MORTES)
    def test_le_fichier_d_exemple_ne_les_redemande_pas(self, cle):
        """Une ligne `CLE=` dans `.env.example` invite à la remplir."""
        lignes = (RACINE / ".env.example").read_text(encoding="utf-8").splitlines()
        reglages = [ligne for ligne in lignes if not ligne.lstrip().startswith("#")]

        assert not any(ligne.startswith(f"{cle}=") for ligne in reglages), (
            f"{cle} est de nouveau proposée au remplissage")

    @pytest.mark.parametrize("cle", CLES_MORTES)
    def test_aucun_code_du_systeme_ne_les_lit(self, cle):
        coupables = [
            chemin.relative_to(RACINE)
            for dossier in DOSSIERS_LUS
            for chemin in (RACINE / dossier).rglob("*")
            if chemin.is_file() and chemin.suffix in {".py", ".yaml", ".yml"}
            and "__pycache__" not in chemin.parts
            and cle in chemin.read_text(encoding="utf-8", errors="ignore")
        ]

        assert coupables == [], f"{cle} est encore lue par : {coupables}"

    def test_la_cle_qui_reste_protege_bien_quelque_chose(self):
        """`USMAN_API_KEY`, elle, ouvre ARENA : sans elle, la passerelle refuse."""
        from apps.backend import security

        assert "USMAN_API_KEY" in (RACINE / ".env.example").read_text(encoding="utf-8")
        assert security.cle_presentee_valide.__doc__


class TestLesModelesParDefautNeDiverguentPas:
    """`.env.example` et `config.py` proposent-ils le même modèle distant ?

    Mesuré le 30/08/2026 sur la machine du propriétaire : `GROQ_MODEL` valait
    `llama-3.3-70b-versatile` des deux côtés — **un modèle retiré du catalogue
    Groq**. Chaque appel rendait `HTTPStatusError`, indiscernable d'une clé
    refusée, et il a fallu interroger `/v1/models` pour comprendre. Un défaut
    mort coûte une heure à celui qui branche le fournisseur pour la première
    fois.

    Ce test ne peut pas vérifier qu'un modèle existe encore — le catalogue est
    en ligne et bouge. Il vérifie ce qui se vérifie hors ligne : que les deux
    valeurs restent la même, pour qu'une correction ne s'applique jamais à
    moitié.
    """

    def _valeur_dans_exemple(self, cle: str) -> str:
        for ligne in (RACINE / ".env.example").read_text(encoding="utf-8").splitlines():
            if ligne.startswith(f"{cle}="):
                return ligne.split("=", 1)[1].strip()
        raise AssertionError(f"{cle} est absente de .env.example")

    def test_le_modele_groq_est_le_meme_des_deux_cotes(self):
        from apps.backend import config

        assert config.GROQ_MODELE == self._valeur_dans_exemple("GROQ_MODEL")

    def test_le_modele_deepinfra_est_le_meme_des_deux_cotes(self):
        from apps.backend import config

        assert config.DEEPINFRA_MODELE == self._valeur_dans_exemple("DEEPINFRA_MODEL")

    def test_le_modele_groq_retire_du_catalogue_ne_revient_pas(self):
        """`llama-3.3-70b-versatile` n'existe plus chez Groq — mesure du 30/08/2026."""
        from apps.backend import config

        assert config.GROQ_MODELE != "llama-3.3-70b-versatile"
        assert "llama-3.3-70b-versatile" not in (
            RACINE / ".env.example").read_text(encoding="utf-8").replace(
                "# ", "").split("GROQ_MODEL=")[-1].splitlines()[0]


class TestAucuneAdresseOllamaEcriteEnDur:
    """`OLLAMA_BASE_URL` doit gouverner **tout** ce qui parle à Ollama.

    Mesuré le 01/09/2026 : `BrowserUseTool` et `LightRAGTool` écrivaient
    `http://127.0.0.1:11434` et `qwen2.5-coder:14b` en dur. Un Ollama déplacé,
    ou un modèle changé dans `.env`, laissait tout marcher **sauf** la
    navigation et les documents — avec une erreur nommant une adresse que le
    propriétaire n'avait jamais configurée.
    """

    #: Deux exceptions, et elles ne sont pas des oublis :
    #: - `ollama_provider.py` : le défaut d'un argument, que l'appelant remplace
    #:   toujours par la valeur configurée (`runtime.py`).
    #: - `graphrag_tool.py` : `host.docker.internal`, une autre adresse pour un
    #:   autre réseau — celle de l'hôte vue depuis un conteneur.
    AUTORISES = {
        "core/models/ollama_provider.py",
        "tools/rag/graphrag_tool.py",
    }

    def test_personne_d_autre_n_ecrit_l_adresse_en_dur(self):
        """Écrire le port est permis — l'écrire sans lire la variable ne l'est pas."""
        coupables = []
        for chemin in RACINE.rglob("*.py"):
            relatif = chemin.relative_to(RACINE).as_posix()
            if relatif.startswith(("tests/", ".venv/")) or "__pycache__" in relatif:
                continue
            if relatif in self.AUTORISES:
                continue
            source = chemin.read_text(encoding="utf-8")
            if "11434" in source and "OLLAMA_BASE_URL" not in source:
                coupables.append(relatif)

        assert coupables == [], (
            "ces fichiers ignorent OLLAMA_BASE_URL : " + ", ".join(coupables))

    def test_le_navigateur_suit_la_configuration(self, monkeypatch):
        import importlib

        monkeypatch.setenv("OLLAMA_BASE_URL", "http://ailleurs:11500")
        monkeypatch.setenv("CODER_LOCAL_MODEL", "un-autre-modele")
        import apps.backend.config as config
        import tools.browser.browser_use_tool as navigateur
        importlib.reload(config)
        importlib.reload(navigateur)
        try:
            outil = navigateur.BrowserUseTool()
            assert outil.provider.base_url == "http://ailleurs:11500"
            assert outil.provider.model_name == "un-autre-modele"
        finally:
            monkeypatch.undo()
            importlib.reload(config)
            importlib.reload(navigateur)
