"""Surface HTTP d'Usman : ce qui est ouvert, ce qui est fermé.

Ces tests tournent hors ligne : ils mesurent l'authentification et le CORS, pas
les réponses du modèle. Le test qui a besoin d'Ollama porte le marqueur
`integration`.
"""
import pytest
from fastapi.testclient import TestClient

from apps.backend import main
from apps.backend import security as securite

CLE_DE_TEST = "cle-de-test"
ROUTES_METIER = ["/api/upload", "/api/process-video", "/api/chat", "/api/chat/stream"]


@pytest.fixture
def client(monkeypatch) -> TestClient:
    """Client HTTP avec une clé API connue ; les erreurs applicatives deviennent des 500."""
    monkeypatch.setattr(securite, "USMAN_API_KEY", CLE_DE_TEST)
    return TestClient(main.app, raise_server_exceptions=False)


@pytest.fixture
def entetes() -> dict:
    return {"Authorization": f"Bearer {CLE_DE_TEST}"}


def test_health_repond_et_annonce_l_etat_d_ollama(client):
    res = client.get("/health")

    assert res.status_code == 200
    corps = res.json()
    # « healthy » ou « degraded » selon qu'Ollama tourne : les deux sont des
    # réponses justes. Exiger « healthy » ferait échouer le test sur une machine
    # sans Ollama, ce qui ne dit rien sur l'API.
    assert corps["status"] in {"healthy", "degraded"}
    assert corps["ollama_available"] is (corps["status"] == "healthy")
    assert len(corps["agents_active"]) > 0


@pytest.mark.parametrize("route", ROUTES_METIER)
def test_les_routes_metier_exigent_la_cle(client, route):
    assert client.post(route, json={"prompt": "x"}).status_code == 401


@pytest.mark.parametrize("route", ROUTES_METIER)
def test_une_mauvaise_cle_est_refusee(client, route):
    res = client.post(route, json={"prompt": "x"}, headers={"Authorization": "Bearer faux"})

    assert res.status_code == 401


@pytest.mark.parametrize("route", ROUTES_METIER)
def test_avec_la_bonne_cle_l_authentification_n_est_plus_la_cause_du_refus(
    client, entetes, route
):
    assert client.post(route, json={"prompt": "x"}, headers=entetes).status_code != 401


def test_la_passerelle_v1_exige_la_cle(client, entetes):
    assert client.get("/v1/models").status_code == 401
    assert client.get("/v1/models", headers=entetes).status_code == 200


def test_sans_cle_configuree_la_passerelle_est_desactivee(monkeypatch, entetes):
    """Une clé vide ne doit pas ouvrir l'accès : elle doit le fermer."""
    monkeypatch.setattr(securite, "USMAN_API_KEY", "")
    client_sans_cle = TestClient(main.app, raise_server_exceptions=False)

    assert client_sans_cle.get("/v1/models", headers=entetes).status_code == 500


def test_une_origine_inconnue_est_refusee_par_le_cors(client):
    res = client.options(
        "/api/chat",
        headers={
            "Origin": "https://site-inconnu.example",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert res.headers.get("access-control-allow-origin") is None


def test_les_interfaces_locales_sont_autorisees_par_le_cors(client):
    for origine in main.ALLOWED_ORIGINS:
        res = client.options(
            "/api/chat",
            headers={
                "Origin": origine,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )

        assert res.headers.get("access-control-allow-origin") == origine


def test_l_etoile_n_est_jamais_une_origine_autorisee():
    assert "*" not in main.ALLOWED_ORIGINS


class TestLeCorsCorrespondAuxVraiesRequetes:
    """Audit f7f0478, etape 11 : la politique CORS ne couvrait pas ce que le

    client envoie reellement. Mesure le 12/09/2026 : Starlette rend un `400`
    au PREFLIGHT lui-meme quand une methode ou un en-tete demande n'est pas
    autorise — le navigateur bloque alors la vraie requete avant qu'elle ne
    parte, sans qu'aucun log applicatif ne le montre.
    """

    def test_le_flux_avec_ses_vrais_en_tetes_passe_le_preflight(self, client):
        """`remoteTransport.ts` envoie X-Usman-Run-ID et Last-Event-ID sur ce flux."""
        res = client.options(
            "/api/chat/stream",
            headers={
                "Origin": main.ALLOWED_ORIGINS[0],
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers":
                    "x-usman-run-id,last-event-id,authorization,content-type",
            },
        )

        assert res.status_code == 200, (
            f"le preflight echoue lui-meme : {res.status_code} {res.text}")
        autorises = {h.strip().lower() for h in
                     res.headers.get("access-control-allow-headers", "").split(",")}
        assert {"x-usman-run-id", "last-event-id"} <= autorises

    def test_la_suppression_memoire_passe_le_preflight(self, client):
        """`DELETE /api/memory/{id}` existe (memory.py) mais DELETE n'etait pas autorise."""
        res = client.options(
            "/api/memory/un-identifiant",
            headers={
                "Origin": main.ALLOWED_ORIGINS[0],
                "Access-Control-Request-Method": "DELETE",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )

        assert res.status_code == 200, (
            f"le preflight echoue lui-meme : {res.status_code} {res.text}")
        methodes = {m.strip().upper() for m in
                    res.headers.get("access-control-allow-methods", "").split(",")}
        assert "DELETE" in methodes

    def test_une_origine_inconnue_reste_refusee_meme_avec_les_bons_en_tetes(self, client):
        """Elargir les en-tetes/methodes ne doit pas elargir les origines."""
        res = client.options(
            "/api/memory/un-identifiant",
            headers={
                "Origin": "https://site-inconnu.example",
                "Access-Control-Request-Method": "DELETE",
                "Access-Control-Request-Headers": "x-usman-run-id",
            },
        )

        assert res.headers.get("access-control-allow-origin") is None


@pytest.mark.integration
def test_le_chat_repond_reellement(client, entetes, ollama_en_ligne):
    res = client.post(
        "/api/chat",
        json={"prompt": "Confirme que l'API Usman est fonctionnelle en une phrase courte."},
        headers=entetes,
    )

    assert res.status_code == 200
    assert res.json()["status"] == "success"


class TestSanteNAnnoncePasPlusQueCeQuiExiste:
    """`/health` a menti deux fois, dans les deux sens.

    D'abord en annonçant `ReasoningEngine` sans chemin pour l'atteindre
    (corrigé en 08/2026). Puis, l'inverse : la même liste écrite à la main
    taisait six agents bien vivants — `PlaquisteAgent` compris, l'assistant
    devis du propriétaire (mesuré le 01/09/2026).

    Une liste figée dérive toujours. Ces tests exigent qu'elle soit dérivée.
    """

    def test_chaque_agent_construit_est_annonce(self, client):
        import apps.backend.runtime as runtime
        from core.agent.base_agent import BaseAgent

        construits = {o.name for o in vars(runtime).values() if isinstance(o, BaseAgent)}
        annonces = set(client.get("/health").json()["agents_active"])

        manquants = sorted(construits - annonces)
        assert not manquants, f"agents construits mais tus par /health : {manquants}"

    def test_aucun_nom_annonce_ne_sort_de_nulle_part(self, client):
        """L'inverse : rien d'annoncé qui ne soit ni un agent ni un moteur connu."""
        import apps.backend.runtime as runtime
        from core.agent.base_agent import BaseAgent

        construits = {o.name for o in vars(runtime).values() if isinstance(o, BaseAgent)}
        connus = construits | set(runtime.MOTEURS_NON_AGENTS)
        annonces = set(client.get("/health").json()["agents_active"])

        inventes = sorted(annonces - connus)
        assert not inventes, f"/health annonce ce qui n'existe pas : {inventes}"

    def test_les_trois_moteurs_non_agents_sont_vraiment_atteignables(self):
        """Ils n'ont pas de classe commune : leur présence se vérifie autrement.

        **La garde a suivi son sujet le 13/09/2026** (DEC-0101). Elle lisait la
        source de `dispatch_request` ; le corps de l'aiguillage a été déplacé
        dans `_aiguiller` pour poser le type de tâche sans réindenter
        cent-quatre-vingts lignes. La garde s'est donc mise à lire une enveloppe
        de six lignes — **elle est devenue aveugle**, et c'est elle qui l'a dit.

        Elle n'est pas affaiblie : elle lit désormais la fonction qui contient
        réellement l'aiguillage, **et** vérifie que `dispatch_request` lui
        délègue. Le jour où quelqu'un coupe la délégation, elle tombe aussi.

        **Ce qu'elle ne voit pas, et ne voyait pas davantage avant** : c'est un
        contrôle *textuel*. Elle attrape un moteur supprimé, renommé ou sorti de
        l'aiguillage ; elle n'attrape pas une branche `if` désactivée qui
        laisserait l'appel dans du code mort. Mesuré le 13/09/2026 en
        remplaçant `if intent == "DEEP_REASONING"` par `if False` : la suite
        reste verte. Le dire ici vaut mieux que laisser croire à une garde
        comportementale.
        """
        import inspect

        import apps.backend.routers.chat as chat
        import apps.backend.runtime as runtime

        source = inspect.getsource(chat._aiguiller)
        for objet in ("reasoning_engine", "lightrag_tool", "graphrag_tool"):
            assert hasattr(runtime, objet), f"{objet} n'existe plus dans runtime"
            assert objet in source, (
                f"{objet} est annoncé par /health mais plus aucun aiguillage ne l'atteint"
            )

        # Le maillon entre les deux : sans lui, la source lue ci-dessus ne
        # serait plus celle qu'une demande traverse.
        entree = inspect.getsource(chat.dispatch_request)
        assert "_aiguiller(" in entree, (
            "dispatch_request ne délègue plus à _aiguiller : la garde "
            "ci-dessus lirait du code que plus aucune demande n'atteint"
        )


class TestUnFluxNeMeurtPasEnSilence:
    """`/api/chat/stream` rendait `200` et **zéro ligne** quand Ollama tombait.

    L'exception remontait dans une réponse déjà commencée : le client
    recevait un flux vide, indistinguable d'une réponse vide, sans `[DONE]`
    et sans raison. `pwa_gateway.flux` tenait déjà la règle ; celui-ci non.
    Mesuré le 01/09/2026.
    """

    @pytest.fixture
    def fournisseur_en_panne(self, monkeypatch):
        import apps.backend.routers.chat as chat

        async def tombe(*_a, **_k):
            raise RuntimeError("Ollama ne repond pas")
            yield  # pragma: no cover - rend la fonction asynchrone génératrice

        monkeypatch.setattr(chat.fast_provider, "generate_stream", tombe)

        async def conversation(*_a, **_k):
            return "CHAT"

        monkeypatch.setattr(chat.orchestrator, "analyze_intent", conversation)

    def _lignes(self, client, entetes):
        with client.stream("POST", "/api/chat/stream", json={"prompt": "bonjour"},
                           headers=entetes) as reponse:
            return reponse.status_code, [ligne for ligne in reponse.iter_lines() if ligne]

    def test_la_panne_est_dite_au_client(self, client, entetes, fournisseur_en_panne):
        statut, lignes = self._lignes(client, entetes)
        assert statut == 200
        assert lignes, "flux vide : la panne est invisible pour le client"
        assert any('"type": "error"' in ligne for ligne in lignes)
        assert any("Ollama ne repond pas" in ligne for ligne in lignes)

    def test_le_flux_se_ferme_proprement(self, client, entetes, fournisseur_en_panne):
        """Sans `[DONE]`, l'interface attend indéfiniment."""
        _, lignes = self._lignes(client, entetes)
        assert lignes[-1].strip() == "data: [DONE]"

    def test_l_historique_ne_garde_pas_une_question_orpheline(
        self, client, entetes, fournisseur_en_panne, monkeypatch
    ):
        """Le tour du propriétaire est enregistré avant la génération."""
        import apps.backend.routers.chat as chat

        ecrits = []
        monkeypatch.setattr(chat.memory, "add_chat_message",
                            lambda **kw: ecrits.append((kw["role"], kw["content"])))
        self._lignes(client, entetes)

        roles = [role for role, _ in ecrits]
        assert roles.count("user") == roles.count("assistant"), (
            f"question sans réponse dans l'historique : {ecrits}"
        )
        reponse = [c for r, c in ecrits if r == "assistant"][0]
        assert "interrompu" in reponse, "une réponse fabriquée a été écrite en mémoire"


class TestChatNeMentPasSurUneReponseVide:
    """`status: success` avec une réponse vide est un mensonge indétectable.

    Mesuré le 01/09/2026 : `/api/chat` rendait
    `{"status": "success", ..., "response": ""}` quand l'agent s'arrêtait sans
    rien produire. Le client affichait une bulle vide et n'avait rien à dire au
    propriétaire.
    """

    def test_le_statut_suit_ce_qui_s_est_reellement_passe(
            self, client, entetes, monkeypatch):
        import apps.backend.routers.chat as chat

        async def muet(demande, intent=None):
            return {"response": "", "agent": "ResearcherAgent",
                    "intent": "DEEP_RESEARCH"}

        async def dispo():
            return True

        monkeypatch.setattr(chat, "dispatch_request", muet)
        monkeypatch.setattr(chat.fast_provider, "is_available", dispo)

        corps = client.post("/api/chat", headers=entetes,
                            json={"prompt": "cherche X"}).json()

        assert corps["status"] == "error"
        assert corps["response"].strip()
        assert "DEEP_RESEARCH" in corps["response"]

    def test_le_flux_specialise_ne_pousse_pas_un_jeton_vide(
            self, client, entetes, monkeypatch):
        """Quatrième surface, même trou : un jeton vide suivi de `[DONE]`."""
        import json as _json

        import apps.backend.routers.chat as chat

        async def muet(demande, intent=None):
            return {"response": "", "agent": "ResearcherAgent"}

        async def recherche(*_a, **_k):
            return "DEEP_RESEARCH"

        monkeypatch.setattr(chat, "dispatch_request", muet)
        monkeypatch.setattr(chat.orchestrator, "analyze_intent", recherche)

        texte = client.post("/api/chat/stream", headers=entetes,
                            json={"prompt": "cherche X"}).text
        charges = [_json.loads(ligne[5:].strip())
                   for ligne in texte.splitlines()
                   if ligne.startswith("data:") and "[DONE]" not in ligne]

        assert charges, "aucune trame reçue"
        assert charges[0]["token"].strip(), "un jeton vide est parti"
        assert "DEEP_RESEARCH" in charges[0]["token"]

    def test_le_flux_de_conversation_signale_une_generation_muette(
            self, client, entetes, monkeypatch):
        """Le routeur replie déjà (DEC-0032) ; si personne ne répond, on le dit."""
        import json as _json

        import apps.backend.routers.chat as chat

        async def rien(prompt, system_prompt=None):
            return
            yield  # pragma: no cover - rend la fonction asynchrone génératrice

        async def conversation(*_a, **_k):
            return "CHAT"

        monkeypatch.setattr(chat.fast_provider, "generate_stream", rien)
        monkeypatch.setattr(chat.orchestrator, "analyze_intent", conversation)

        texte = client.post("/api/chat/stream", headers=entetes,
                            json={"prompt": "bonjour"}).text
        charges = [_json.loads(ligne[5:].strip())
                   for ligne in texte.splitlines()
                   if ligne.startswith("data:") and "[DONE]" not in ligne]

        assert charges and charges[-1]["type"] == "error"
        assert charges[-1]["message"].strip()


class TestChaqueAgentConstruitEstAtteignable:
    """Construire un agent ne suffit pas : il faut un chemin qui l'appelle.

    `/health` a menti deux fois sur cette liste — d'abord en annonçant
    `ReasoningEngine` sans chemin pour l'atteindre, puis en taisant six agents
    bien vivants. Le correctif a rendu la liste **dérivée** de ce que `runtime`
    construit, ce qui règle le second sens et **pas le premier** : un agent
    construit et jamais câblé serait annoncé quand même.

    Ce test ferme l'autre sens. Il balaie tous les routeurs, pas trois :
    `ClipSelectorAgent` n'est atteint que par `/api/process-video`, et un
    balayage partiel le déclarait mort à tort — mesuré le 01/09/2026, sur
    moi-même.
    """

    @staticmethod
    def _tout_le_code_qui_appelle() -> str:
        """Les routeurs et le studio, lus en entier."""
        from pathlib import Path

        import apps.backend.runtime as runtime

        racine = Path(runtime.__file__).resolve().parent
        fichiers = sorted((racine / "routers").glob("*.py")) + [racine / "studio.py"]
        return "\n".join(f.read_text(encoding="utf-8") for f in fichiers if f.exists())

    def test_aucun_agent_construit_ne_dort(self):
        import apps.backend.runtime as runtime
        from core.agent.base_agent import BaseAgent

        code = self._tout_le_code_qui_appelle()
        endormis = sorted(
            nom for nom, objet in vars(runtime).items()
            if isinstance(objet, BaseAgent) and nom not in code
        )

        assert endormis == [], (
            "ces agents sont construits au demarrage, annonces par /health, "
            f"et aucun routeur ne les appelle : {endormis}"
        )

    def test_le_balayage_couvre_bien_plusieurs_routeurs(self):
        """Sans ça, le test au-dessus pourrait passer en ne lisant rien."""
        code = self._tout_le_code_qui_appelle()

        assert "dispatch_request" in code, "chat.py n'a pas ete lu"
        assert "clip_selector" in code, "media.py n'a pas ete lu"
        assert len(code) > 20_000, "le balayage est trop court pour etre complet"
