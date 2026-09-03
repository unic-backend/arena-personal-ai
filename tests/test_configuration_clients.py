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

#: Les paquets qui portent du code source ARENA — même liste que
#: `scripts/orphelins.py`. Un balayage doit s'y limiter, jamais partir de la
#: racine du dépôt : au-delà vivent `data/`, `.venv/` et d'autres dossiers
#: générés à l'exécution, pas toujours vides, pas toujours lisibles.
PAQUETS_SOURCE = ("apps", "core", "agents", "tools", "social")

#: Reutilise depuis `scripts/orphelins.py` : une seule liste des moteurs
#: externes, pour que les deux balayages ne divergent pas.
from scripts.orphelins import MOTEURS_EXTERNES  # noqa: E402

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
        """Écrire le port est permis — l'écrire sans lire la variable ne l'est pas.

        Le balayage se limite aux paquets sources (`scripts/orphelins.py` tient
        déjà cette liste) au lieu de parcourir tout le dépôt depuis sa racine.
        Mesuré le 01/09/2026 sur la machine du propriétaire : un `rglob` depuis
        la racine descend dans `data/`, ignoré par `.gitignore` mais bien
        présent sur le disque — un cache d'embeddings y écrit des chemins que
        Windows refuse de lire (`OSError: [Errno 22] Invalid argument`). Cette
        machine n'a pas ce dossier, donc le défaut n'y était pas visible.
        """
        coupables = []
        for paquet in PAQUETS_SOURCE:
            for chemin in (RACINE / paquet).rglob("*.py"):
                relatif = chemin.relative_to(RACINE).as_posix()
                if "__pycache__" in relatif or relatif in self.AUTORISES:
                    continue
                # Les moteurs externes vivent sous `tools/` sans etre notre
                # code. Le `.venv` du SDK Faceplugin apporte sympy et pygments,
                # qui contiennent « 11434 » dans des tables de tests et de
                # caracteres (mesure du 03/09/2026) : cinq faux coupables qu'on
                # ne peut ni corriger ni versionner.
                if any(relatif.startswith(m) for m in MOTEURS_EXTERNES):
                    continue
                source = chemin.read_text(encoding="utf-8")
                if "11434" in source and "OLLAMA_BASE_URL" not in source:
                    coupables.append(relatif)

        assert coupables == [], (
            "ces fichiers ignorent OLLAMA_BASE_URL : " + ", ".join(coupables))

    def test_le_navigateur_suit_la_configuration(self, monkeypatch):
        import importlib

        monkeypatch.setenv("OLLAMA_BASE_URL", "http://ailleurs:11500")
        # `CHAT_LOCAL_MODEL` depuis le 02/09/2026, `CODER_LOCAL_MODEL` avant.
        # Le navigateur LIT et raisonne, il n'ecrit pas de code : il suit donc
        # le modele de conversation, comme le moteur documentaire. Ce que ce
        # test tient n'a pas bouge d'un pouce — un modele change dans `.env`
        # doit etre suivi par l'outil ; seule la variable qui le gouverne a
        # change, avec la separation conversation/code.
        monkeypatch.setenv("CHAT_LOCAL_MODEL", "un-autre-modele")
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


class TestComparaisonDeCleATempsConstant:
    """Un secret se compare avec `compare_digest`, jamais avec `==`.

    Ce n'est pas un défaut mesuré — le canal est étroit et le serveur est
    personnel. C'est la façon standard de comparer un secret, et elle ne coûte
    rien. `==` s'arrête au premier caractère qui diffère : le temps de réponse
    dépend alors du nombre de caractères devinés juste.

    Ces tests fixent le **comportement**, qui ne change pas, et le fait que la
    comparaison passe bien par `compare_digest`.
    """

    def test_la_bonne_cle_est_acceptee(self, monkeypatch):
        from apps.backend import security

        monkeypatch.setattr(security, "USMAN_API_KEY", "la-vraie-cle")

        assert security.cle_presentee_valide("Bearer la-vraie-cle") is True

    @pytest.mark.parametrize("presentee", [
        None, "", "la-vraie-cle", "Bearer ", "Bearer la-vraie-cl",
        "Bearer la-vraie-clef", "bearer la-vraie-cle",
    ])
    def test_tout_le_reste_est_refuse(self, monkeypatch, presentee):
        from apps.backend import security

        monkeypatch.setattr(security, "USMAN_API_KEY", "la-vraie-cle")

        assert security.cle_presentee_valide(presentee) is False

    def test_sans_cle_configuree_rien_n_est_valide(self, monkeypatch):
        from apps.backend import security

        monkeypatch.setattr(security, "USMAN_API_KEY", "")

        assert security.cle_presentee_valide("Bearer ") is False
        assert security.cle_presentee_valide("Bearer nimporte") is False

    def test_un_en_tete_non_ascii_ne_fait_pas_tomber_la_passerelle(self, monkeypatch):
        """`compare_digest` lève sur du non-ASCII : ce n'est pas la clé, c'est tout."""
        from apps.backend import security

        monkeypatch.setattr(security, "USMAN_API_KEY", "la-vraie-cle")

        assert security.cle_presentee_valide("Bearer clé-accentuée") is False

    def test_la_comparaison_passe_par_compare_digest(self, monkeypatch):
        """Le branchement, pas seulement le comportement."""
        import secrets

        from apps.backend import security

        appels = []
        vrai = secrets.compare_digest
        monkeypatch.setattr(
            security.secrets, "compare_digest",
            lambda a, b: appels.append(1) or vrai(a, b))
        monkeypatch.setattr(security, "USMAN_API_KEY", "la-vraie-cle")

        security.cle_presentee_valide("Bearer la-vraie-cle")

        assert appels, "la comparaison est repassee sur `==`"


class TestLeDebitNeBloquePasUneConversation:
    """Le limiteur existe pour arrêter une boucle emballée, pas le propriétaire.

    Mesuré le 01/09/2026, sur de vrais appels HTTP : l'interface envoie **deux**
    requêtes par message (`/agent/stream` puis `/conversations/sync`), et le
    défaut était de dix par minute. Le **sixième** message d'une minute
    recevait `429` :

    ```
    message  5 -> /agent/stream 200 | /conversations/sync 200
    message  6 -> /agent/stream 429 | /conversations/sync 429
    ```

    Cinq messages par minute est un rythme de conversation ordinaire.
    """

    def test_la_limite_laisse_passer_une_conversation_rapide(self):
        from apps.backend import config

        messages = config.REQUETES_MAX // config.REQUETES_PAR_MESSAGE
        par_minute = messages * 60 / config.FENETRE_SECONDES

        assert par_minute >= 20, (
            f"la limite n'autorise que {par_minute:.0f} message(s) par minute ; "
            "quelqu'un qui tape vite serait bloque par son propre serveur"
        )

    def test_la_limite_arrete_quand_meme_une_boucle_emballee(self):
        """Une boucle tape des centaines de fois par seconde, pas une."""
        from apps.backend import config

        par_seconde = config.REQUETES_MAX / config.FENETRE_SECONDES

        assert par_seconde <= 5, (
            f"{par_seconde:.0f} requetes/s laisse passer une boucle emballee"
        )

    def test_l_exemple_et_le_code_proposent_la_meme_limite(self):
        """Une correction qui ne s'applique qu'à moitié est pire que rien."""
        from apps.backend import config

        for ligne in (RACINE / ".env.example").read_text(encoding="utf-8").splitlines():
            if ligne.startswith("USMAN_RATE_LIMIT_REQUESTS="):
                assert int(ligne.split("=", 1)[1]) == config.REQUETES_MAX
                return
        raise AssertionError("USMAN_RATE_LIMIT_REQUESTS absente de .env.example")


class TestUnModeleDeCodeNeTientPasUneConversation:
    """Le propriétaire ne programme pas. Ses devis non plus.

    Mesuré le 02/09/2026 : `fast_provider` portait `qwen2.5-coder:14b` — un
    modèle **spécialisé dans l'écriture de code** — et répondait à **tout** :
    la conversation (`pwa_gateway.py`), les devis, le courrier, et aussi
    `coder_agent`/`swe_agent`. Un seul modèle de programmation rédigeait donc
    ses devis clients et discutait en français avec lui.

    Il l'a signalé sans pouvoir le nommer : « il faut qu'il soit intelligent ».

    Ce que ces tests n'affirment PAS : qu'un modèle soit meilleur que l'autre.
    Aucune mesure comparée n'a été faite — sa machine n'est pas joignable
    d'ici. Ce qu'ils tiennent est plus simple, et c'est écrit dans le nom du
    modèle : un modèle de code n'est pas fait pour parler.
    """

    def test_la_conversation_n_est_pas_servie_par_le_modele_de_code(self):
        from apps.backend.config import MODELE_CODEUR, MODELE_CONVERSATION

        assert MODELE_CONVERSATION != MODELE_CODEUR
        assert "coder" not in MODELE_CONVERSATION.lower(), (
            f"le modèle qui parle est un modèle de code : {MODELE_CONVERSATION}")

    def test_le_modele_de_code_reste_celui_des_agents_qui_codent(self):
        """Le retirer remplacerait une erreur par l'autre."""
        from apps.backend.config import MODELE_CODEUR

        assert "coder" in MODELE_CODEUR.lower()

    def test_les_agents_recoivent_chacun_le_leur(self):
        from apps.backend.runtime import coder_agent, coder_provider, fast_provider, swe_agent

        assert coder_agent.provider is coder_provider
        assert swe_agent.provider is coder_provider
        assert coder_provider.model_name != fast_provider.model_name

    def test_l_ancien_nom_designe_bien_la_conversation(self):
        """Tout le projet importe `MODELE_RAPIDE` : il ne doit pas mentir."""
        from apps.backend.config import MODELE_CONVERSATION, MODELE_RAPIDE

        assert MODELE_RAPIDE == MODELE_CONVERSATION

    def test_le_proprietaire_garde_la_main_par_env(self, monkeypatch):
        """Un réglage qui ne se règle plus n'est pas un réglage."""
        import importlib

        monkeypatch.setenv("CHAT_LOCAL_MODEL", "un-modele-a-lui:7b")
        import apps.backend.config as config

        importlib.reload(config)
        try:
            assert config.MODELE_CONVERSATION == "un-modele-a-lui:7b"
        finally:
            monkeypatch.delenv("CHAT_LOCAL_MODEL", raising=False)
            importlib.reload(config)
