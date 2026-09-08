"""La recherche unifiée : code + mémoire + internet, en parallèle, avec
provenance — jamais les trois par réflexe, jamais une source qui efface
les autres si elle échoue.
"""
import asyncio
import time

from core.context.recherche_unifiee import rechercher_unifie, sources_pertinentes


class RegistreDouble:
    """Un registre de test : dispatche par (connecteur, capacité), comme le
    vrai `RegistreConnecteurs.executer`, mais synchrone — pour vérifier que
    `_executer_connecteur` gère les deux formes (voir production_agent.py)."""

    def __init__(self, reponses=None, delai=0.0):
        self.appels = []
        self._reponses = reponses or {}
        self._delai = delai

    def executer(self, nom, capacite, **parametres):
        self.appels.append((nom, capacite, parametres))
        if self._delai:
            time.sleep(self._delai)
        return self._reponses.get((nom, capacite), {"statut": "ECHEC", "message": "non scripté"})


class RegistreAsyncDouble(RegistreDouble):
    """Même chose, mais `executer` est une coroutine — le registre réel ne
    l'est jamais, un double si, et `_executer_connecteur` doit gérer les deux."""

    async def executer(self, nom, capacite, **parametres):
        return super().executer(nom, capacite, **parametres)


class FreshInfoDouble:
    def __init__(self, reponse=None, delai=0.0):
        self.appels = []
        self._reponse = reponse or {
            "status": "success", "response": "La bibliothèque X est en version 2.1.",
            "sources": ["https://example.com/release-notes"],
        }
        self._delai = delai

    async def run(self, question, context=None):
        self.appels.append(question)
        if self._delai:
            await asyncio.sleep(self._delai)
        return self._reponse


class TestSourcesPertinentes:
    def test_une_question_de_code(self):
        assert sources_pertinentes("où est implémentée cette fonction ?") == ["code"]

    def test_une_question_de_memoire(self):
        assert sources_pertinentes("nous avions déjà résolu ce problème, comment ?") == ["memoire"]

    def test_une_question_internet(self):
        assert sources_pertinentes("trouve la dernière version de cette bibliothèque") == ["internet"]

    def test_une_question_mixte_code_et_internet(self):
        sources = sources_pertinentes(
            "cette erreur existe-t-elle dans la dernière version de la bibliothèque utilisée par ce module ?")
        assert set(sources) == {"code", "internet"}

    def test_une_question_ordinaire_ne_declenche_rien(self):
        assert sources_pertinentes("bonjour, comment vas-tu ?") == []


class TestRechercherUnifie:
    async def test_aucune_source_identifiee_ne_lance_aucun_appel(self):
        registre = RegistreDouble()
        resultat = await rechercher_unifie("bonjour", registre=registre)

        assert resultat["status"] == "warning"
        assert resultat["sources_interrogees"] == []
        assert registre.appels == []

    async def test_source_identifiee_mais_rien_de_branche(self):
        resultat = await rechercher_unifie("où est cette fonction ?", registre=None)

        assert resultat["status"] == "warning"
        assert "non branché" in resultat["response"] or "disponible" in resultat["response"]

    async def test_question_de_code_appelle_claude_context(self, tmp_path):
        registre = RegistreDouble(reponses={
            ("claude_context", "rechercher"): {
                "statut": "SUCCESS", "message": "2 résultat(s) pour « x » dans le dépôt.",
                "detail": {"resultats": [{"path": "core/permissions/controle.py"}]},
            },
        })

        resultat = await rechercher_unifie(
            "où est le contrôle de permission ?", registre=registre, chemin_code=str(tmp_path))

        assert resultat["status"] == "success"
        assert resultat["sources_interrogees"] == ["code"]
        assert resultat["resultats"][0]["source"] == "codebase"
        assert registre.appels[0][0] == "claude_context"

    async def test_question_de_code_sans_chemin_est_sautee(self, tmp_path):
        registre = RegistreDouble()

        resultat = await rechercher_unifie("où est cette fonction ?", registre=registre, chemin_code=None)

        assert resultat["sources_interrogees"] == []
        assert registre.appels == []

    async def test_question_de_memoire_appelle_openviking(self):
        registre = RegistreDouble(reponses={
            ("openviking", "contexte"): {
                "statut": "SUCCESS", "message": "1 élément assemblé.",
                "detail": {"rendu": "<memory>...</memory>", "entrees": [{"uri": "x"}]},
            },
        })

        resultat = await rechercher_unifie(
            "on avait déjà résolu ce problème, comment ?", registre=registre)

        assert resultat["resultats"][0]["source"] == "openviking_memory"
        assert registre.appels[0] == ("openviking", "contexte", {"requete": "on avait déjà résolu ce problème, comment ?"})

    async def test_session_id_est_transmis_a_openviking(self):
        registre = RegistreDouble(reponses={
            ("openviking", "contexte"): {"statut": "SUCCESS", "message": "ok", "detail": {}},
        })

        await rechercher_unifie("on avait déjà résolu ce souci", registre=registre, session_id="s-1")

        assert registre.appels[0][2]["session_id"] == "s-1"

    async def test_question_internet_appelle_l_agent_existant(self):
        agent = FreshInfoDouble()

        resultat = await rechercher_unifie(
            "trouve la dernière version de cette bibliothèque", fresh_info_agent=agent)

        assert resultat["status"] == "success"
        assert resultat["resultats"][0]["source"] == "web"
        assert agent.appels == ["trouve la dernière version de cette bibliothèque"]

    async def test_registre_asynchrone_est_gere(self, tmp_path):
        """Le registre réel est synchrone ; un double peut être asynchrone —
        même garde que `VideoProductionAgent._executer_drift`."""
        registre = RegistreAsyncDouble(reponses={
            ("claude_context", "rechercher"): {"statut": "SUCCESS", "message": "ok", "detail": {}},
        })

        resultat = await rechercher_unifie(
            "où est cette fonction ?", registre=registre, chemin_code=str(tmp_path))

        assert resultat["status"] == "success"


class TestFusionAvecProvenance:
    async def test_une_source_en_echec_n_efface_pas_les_autres(self, tmp_path):
        """Mesuré comme la garde de DEC-0017 (DeepResearcherAgent) : une
        panne d'une branche ne doit jamais faire disparaître les autres."""
        registre = RegistreDouble(reponses={
            ("claude_context", "rechercher"): {"statut": "ECHEC", "message": "Claude Context indisponible"},
        })
        agent = FreshInfoDouble()

        resultat = await rechercher_unifie(
            "où est cette fonction, et existe-t-elle dans la dernière version en ligne ?",
            registre=registre, fresh_info_agent=agent, chemin_code=str(tmp_path))

        assert resultat["status"] == "success", resultat["response"]
        sources = {r["source"] for r in resultat["resultats"]}
        assert sources == {"codebase", "web"}
        favorable = {r["source"]: r["favorable"] for r in resultat["resultats"]}
        assert favorable["codebase"] is False
        assert favorable["web"] is True

    async def test_une_exception_dans_une_source_ne_fait_pas_tomber_les_autres(self, tmp_path):
        class RegistreQuiLeve:
            def executer(self, nom, capacite, **parametres):
                raise RuntimeError("connecteur explosé")

        agent = FreshInfoDouble()
        resultat = await rechercher_unifie(
            "où est cette fonction, et existe-t-elle en ligne ?",
            registre=RegistreQuiLeve(), fresh_info_agent=agent, chemin_code=str(tmp_path))

        assert resultat["status"] == "success"
        sources = {r["source"]: r for r in resultat["resultats"]}
        assert "explosé" in sources["codebase"]["resume"]
        assert sources["web"]["favorable"] is True


class TestParallelisme:
    async def test_les_sources_tournent_en_parallele_pas_en_sequence(self, tmp_path):
        registre = RegistreDouble(
            reponses={("claude_context", "rechercher"): {"statut": "SUCCESS", "message": "ok", "detail": {}}},
            delai=0.1)
        agent = FreshInfoDouble(delai=0.1)

        depart = time.perf_counter()
        await rechercher_unifie(
            "où est cette fonction, et existe-t-elle en ligne ?",
            registre=registre, fresh_info_agent=agent, chemin_code=str(tmp_path))
        duree = time.perf_counter() - depart

        assert duree < 0.18, "les deux sources ont tourné en séquence, pas en parallèle"


class TestSmokeBoutEnBout:
    """Mission §17 : code -> mémoire -> internet -> fusion -> provenance,
    sur une question qui appelle réellement les trois."""

    async def test_smoke_les_trois_sources_collaborent(self, tmp_path):
        registre = RegistreDouble(reponses={
            ("claude_context", "rechercher"): {
                "statut": "SUCCESS", "message": "1 résultat pour « pipeline vidéo » dans le dépôt.",
                "detail": {"resultats": [{"path": "agents/video/production_agent.py", "score": 0.87}]},
            },
            ("openviking", "contexte"): {
                "statut": "SUCCESS", "message": "1 élément de contexte assemblé.",
                "detail": {"rendu": "<memory>Le pipeline vidéo avait déjà échoué sur un délai réseau.</memory>",
                          "entrees": [{"uri": "viking://user/default/memories/events/pipeline.md"}]},
            },
        })
        agent = FreshInfoDouble(reponse={
            "status": "success",
            "response": "Aucun changement récent connu en amont sur ce composant.",
            "sources": ["https://github.com/exemple/depot/releases"],
        })

        resultat = await rechercher_unifie(
            "pourquoi le pipeline vidéo fonctionne mal, on avait déjà résolu ça comment, "
            "et y a-t-il un changement récent en ligne à ce sujet ?",
            registre=registre, fresh_info_agent=agent, chemin_code=str(tmp_path), session_id="sess-42")

        assert resultat["status"] == "success"
        assert set(resultat["sources_interrogees"]) == {"code", "memoire", "internet"}
        sources_rendues = {r["source"] for r in resultat["resultats"]}
        assert sources_rendues == {"codebase", "openviking_memory", "web"}
        assert all(r.get("favorable") for r in resultat["resultats"])
        assert "production_agent.py" in resultat["response"] or any(
            "production_agent.py" in str(r) for r in resultat["resultats"])
        appel_memoire = next(a for a in registre.appels if a[0] == "openviking")
        assert appel_memoire[2].get("session_id") == "sess-42"
