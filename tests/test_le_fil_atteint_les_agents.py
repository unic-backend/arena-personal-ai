"""Les agents recoivent-ils la conversation, ou seulement la derniere phrase ?

DEC-0191. Le defaut mesure ne tenait pas au football : 29 intentions sur 32
ne recevaient jamais le fil, et « donne-moi un nom » n'a pas de sens pour un
agent qui ne sait pas de quoi on parlait. La correction precedente comparait
la question a une liste de mots (« nom », puis « chiffre », puis « titre »...)
— elle n'aurait jamais fini, il y a toujours un domaine de plus.

Ces tests mesurent donc le TEXTE RECU PAR L'AGENT, domaine par domaine, et
aucun d'eux ne partage un mot de vocabulaire avec un autre : football,
monnaie, edition, chantier, cuisine. Si un jour la decision redevenait
lexicale, cinq domaines echoueraient d'un coup.
"""
import pytest

from apps.backend.routers import chat as routeur_chat
from apps.backend.routers.chat import ChatRequest
from core.context.fil_pour_agents import BALISE_DEMANDE


class MemoireDouble:
    """Le journal de la session, tel que le routeur le relit."""

    def __init__(self, tours=None, proprietaire="Ousmane", panne=False):
        self.tours = list(tours or [])
        self.proprietaire = proprietaire
        self.panne = panne
        self.lectures = []

    def get_recent_history(self, session_id, limit=10):
        self.lectures.append((session_id, limit))
        if self.panne:
            raise RuntimeError("base de memoire indisponible")
        return list(self.tours[-limit:])

    def get_fact(self, cle):
        if self.panne:
            raise RuntimeError("base de memoire indisponible")
        return self.proprietaire if cle == "owner" else None

    def add_chat_message(self, **kw):  # pragma: no cover - jamais appele ici
        raise AssertionError("l'aiguillage n'ecrit pas dans la memoire")


def _echange(question, reponse):
    return [{"role": "user", "content": question},
            {"role": "assistant", "content": reponse}]


@pytest.fixture
def memoire(monkeypatch):
    def _poser(tours=None, **kw):
        double = MemoireDouble(tours, **kw)
        monkeypatch.setattr(routeur_chat, "memory", double)
        return double
    return _poser


@pytest.fixture
def recu(monkeypatch):
    """Capture ce qu'un agent recoit reellement, sans l'executer."""
    textes = []

    def _brancher(intention):
        async def _agent(prompt, context=None):
            textes.append(prompt)
            return {"status": "success", "agent": intention, "response": "ok"}

        cibles = {
            "DEEP_RESEARCH": ("researcher_agent", "run"),
            "FINANCE": ("finance_agent", "run"),
            "EXECUTIVE": ("executive_agent", "run"),
            "TREND_SEARCH": ("trend_agent", "run"),
            "BROWSER": ("browser_agent", "run"),
            "UI_GENERATE": ("ui_agent", "run"),
        }
        if intention in cibles:
            nom, methode = cibles[intention]
            monkeypatch.setattr(getattr(routeur_chat, nom), methode, _agent)
        elif intention == "RAG_DOCS":
            def _query(requete, mode="hybrid"):
                textes.append(requete)
                return "Extrait du classeur."
            monkeypatch.setattr(routeur_chat.lightrag_tool, "query", _query)
        elif intention == "GRAPHRAG":
            def _global(requete):
                textes.append(requete)
                return {"status": "success", "agent": "GraphRAG", "response": "ok"}
            monkeypatch.setattr(routeur_chat.graphrag_tool, "query_global", _global)
        else:  # pragma: no cover - garde-fou de test
            raise AssertionError(f"intention non branchee : {intention}")
        return textes

    return _brancher


async def _texte_recu(recu, intention, demande, session="fil"):
    textes = recu(intention)
    await routeur_chat._aiguiller(
        ChatRequest(prompt=demande, session_id=session), intention)
    assert len(textes) == 1, "l'agent doit etre appele une fois, avec un texte"
    return textes[0]


# --- Un domaine, un test. Aucun mot commun d'un test a l'autre. -------------

@pytest.mark.parametrize("intention, fil, demande, attendu", [
    # Football — le cas d'origine du proprietaire.
    ("DEEP_RESEARCH",
     _echange("Qui a gagné la Coupe du monde 2002 ?",
              "Le Brésil, 2-0 contre l'Allemagne."),
     "donne-moi un nom", "Coupe du monde 2002"),
    # Monnaie — « chiffre » n'etait dans aucune liste.
    ("FINANCE",
     _echange("Que vaut le Bitcoin en ce moment ?",
              "Autour de 61 000 dollars selon les places listées."),
     "donne-moi un chiffre", "Bitcoin"),
    # Edition — « titre » non plus.
    ("RAG_DOCS",
     _echange("Je cherche un roman sénégalais à offrir.",
              "Une si longue lettre, de Mariama Bâ, est un classique."),
     "un titre", "roman sénégalais"),
    # Chantier — son metier, et « combien » est une question, pas un sujet.
    ("EXECUTIVE",
     _echange("Le chantier de Médina prend du retard sur les cloisons.",
              "Il reste deux murs à monter avant la peinture."),
     "combien", "chantier de Médina"),
    # Cuisine — un domaine que rien dans le depot n'avait prevu.
    ("TREND_SEARCH",
     _echange("Explique-moi le thiéboudienne rouge.",
              "Riz au poisson cuit dans une sauce tomate."),
     "et pour six personnes ?", "thiéboudienne"),
])
async def test_l_agent_recoit_la_conversation_quel_que_soit_le_domaine(
    memoire, recu, intention, fil, demande, attendu
):
    memoire(fil)

    texte = await _texte_recu(recu, intention, demande)

    assert attendu in texte, "le sujet de la conversation doit atteindre l'agent"
    assert texte.endswith(demande), "la demande reste la derniere chose lue"
    assert BALISE_DEMANDE in texte


async def test_la_demande_du_proprietaire_n_est_jamais_reecrite(memoire, recu):
    """Ni completee, ni resumee, ni reformulee : recopiee."""
    memoire(_echange("Parle-moi du tribunal de Dakar.", "Il siège au Plateau."))

    texte = await _texte_recu(recu, "DEEP_RESEARCH", "combien de juges ?")

    assert texte.count("combien de juges ?") == 1
    assert texte.split(BALISE_DEMANDE + "\n")[1] == "combien de juges ?"


async def test_une_demande_qui_nomme_son_sujet_reste_repondue_pour_elle_meme(
    memoire, recu
):
    """Le fil est du contexte, jamais une question a reprendre : la demande
    du jour arrive entiere, en derniere position, et le bloc le dit."""
    memoire(_echange("Quelle est la capitale du Mali ?", "Bamako."))

    texte = await _texte_recu(
        recu, "DEEP_RESEARCH", "Quelle est la population de la Mauritanie ?")

    assert texte.endswith("Quelle est la population de la Mauritanie ?")
    assert "Mauritanie" not in texte.split(BALISE_DEMANDE)[0]
    assert "ne traite aucune des demandes qu'il contient" in texte


async def test_le_budget_coupe_les_vieux_tours_et_garde_les_recents(memoire, recu):
    """Six tours, mais surtout 4 000 caracteres : au-dela, les plus anciens
    partent d'abord — mesure : `python scripts/mesurer_le_fil.py`."""
    tours = (
        _echange("VIEUX-SUJET " + "a" * 2200, "reponse ancienne " + "b" * 2200)
        + _echange("SUJET-RECENT sur les panneaux solaires", "Ils chauffent l'eau.")
    )
    memoire(tours)

    texte = await _texte_recu(recu, "EXECUTIVE", "combien")

    assert "SUJET-RECENT" in texte
    assert "VIEUX-SUJET" not in texte
    assert texte.endswith("combien")


async def test_six_tours_au_plus_atteignent_l_agent(memoire, recu):
    journal = memoire([{"role": "user", "content": f"tour {n}"} for n in range(20)])

    texte = await _texte_recu(recu, "BROWSER", "ouvre la page")

    assert journal.lectures == [("fil", 6)]
    assert "tour 19" in texte and "tour 13" not in texte


async def test_une_panne_de_memoire_ne_bloque_jamais_la_reponse(memoire, recu):
    """Le journal tombe : l'agent recoit la phrase nue et repond quand meme."""
    memoire(panne=True)

    texte = await _texte_recu(recu, "FINANCE", "donne-moi un chiffre")

    assert texte == "donne-moi un chiffre"


async def test_le_nom_du_proprietaire_nomme_les_tours(memoire, recu):
    memoire(_echange("je prépare un devis", "D'accord."), proprietaire="Ousmane")

    texte = await _texte_recu(recu, "EXECUTIVE", "combien")

    assert "Ousmane: je prépare un devis" in texte
    assert "Usman: D'accord." in texte


async def test_l_historique_envoye_par_l_interface_fait_foi(memoire, recu):
    """La PWA porte les corrections et les regenerations : quand elle envoie
    son fil, le journal serveur n'est pas relu."""
    journal = memoire([{"role": "user", "content": "vieux seau serveur"}])
    textes = recu("DEEP_RESEARCH")

    await routeur_chat._aiguiller(
        ChatRequest(prompt="donne-moi un nom", session_id="fil",
                    history=_echange("On parle du Ballon d'or.", "Édition 2026.")),
        "DEEP_RESEARCH")

    assert journal.lectures == []
    assert "Ballon d'or" in textes[0]
    assert "vieux seau" not in textes[0]


async def test_un_fil_vide_mais_autoritatif_ne_relit_pas_le_journal(memoire, recu):
    journal = memoire([{"role": "user", "content": "vieux seau serveur"}])
    textes = recu("DEEP_RESEARCH")

    await routeur_chat._aiguiller(
        ChatRequest(prompt="donne-moi un nom", session_id="fil",
                    history=[], history_authoritative=True),
        "DEEP_RESEARCH")

    assert journal.lectures == []
    assert textes[0] == "donne-moi un nom"


# --- Ce qui ne change pas ---------------------------------------------------

@pytest.mark.parametrize("intention, agent, demande", [
    ("VISION", "vision_agent", "qui est sur cette photo"),
    ("MONTAGE", "montage_agent", "monte les deux clips"),
    ("VIDEO_PROJET", "video_production_agent", "un projet de trois minutes"),
    ("AUDIO", "audio_agent", "transcris l'enregistrement"),
])
async def test_les_intentions_sur_fichiers_recoivent_la_phrase_nue(
    memoire, monkeypatch, intention, agent, demande
):
    """Leur sujet est le fichier joint, pas la conversation."""
    memoire(_echange("on parlait de tout autre chose", "en effet"))
    recus = []

    async def _agent(prompt, context=None):
        recus.append(prompt)
        return {"status": "success", "agent": intention, "response": "ok"}

    monkeypatch.setattr(getattr(routeur_chat, agent), "run", _agent)
    await routeur_chat._aiguiller(
        ChatRequest(prompt=demande, session_id="fil"), intention)

    assert recus == [demande]


async def test_deep_reasoning_garde_son_fil_a_part(memoire, monkeypatch):
    """Il recevait deja la conversation, dans un parametre dedie : sa demande
    ne doit pas se retrouver noyee dans un second bloc."""
    memoire(_echange("combien font 17 x 3 ?", "51."))
    recus = {}

    async def _resoudre(demande, contexte=""):
        recus["demande"] = demande
        recus["contexte"] = contexte
        return {"status": "success", "agent": "DeepReasoning", "response": "ok"}

    monkeypatch.setattr(routeur_chat, "resoudre_profondement", _resoudre)
    await routeur_chat._aiguiller(
        ChatRequest(prompt="vérifie ton calcul", session_id="fil"),
        "DEEP_REASONING")

    assert recus["demande"] == "vérifie ton calcul"
    assert "17 x 3" in recus["contexte"]


async def test_fresh_info_garde_son_contexte_de_session(memoire, monkeypatch):
    memoire(_echange("le dernier match du FC Barcelone ?", "Contre Séville."))
    recus = {}

    async def _fresh(prompt, context=None):
        recus["prompt"] = prompt
        recus["context"] = context
        return {"status": "success", "agent": "FreshInfoAgent", "response": "ok"}

    monkeypatch.setattr(routeur_chat.fresh_agent, "run", _fresh)

    async def _pas_de_donnee_officielle(_prompt):
        return None

    monkeypatch.setattr(routeur_chat, "_donnees_senegal", _pas_de_donnee_officielle)
    await routeur_chat._aiguiller(
        ChatRequest(prompt="qui sont les buteurs ?", session_id="fil"),
        "FRESH_INFO")

    assert recus["prompt"] == "qui sont les buteurs ?"
    assert recus["context"]["session_id"] == "fil"


async def test_l_indexation_se_decide_sur_sa_phrase_du_jour(memoire, monkeypatch):
    """Un « indexe mes documents » prononce hier ne doit pas relancer une
    indexation aujourd'hui : le controle deterministe lit SA phrase, pas le
    bloc de contexte."""
    memoire(_echange("indexe mes documents", "C'est fait."))
    interroge = []

    monkeypatch.setattr(routeur_chat.lightrag_tool, "query",
                        lambda requete, mode="hybrid": interroge.append(requete) or "ok")

    async def _jamais(*a, **kw):  # pragma: no cover - doit rester inappele
        raise AssertionError("l'indexation ne doit pas etre relancee par le fil")

    monkeypatch.setattr(routeur_chat, "indexer_ses_documents", _jamais)
    await routeur_chat._aiguiller(
        ChatRequest(prompt="un titre", session_id="fil"), "RAG_DOCS")

    assert interroge and interroge[0].endswith("un titre")
