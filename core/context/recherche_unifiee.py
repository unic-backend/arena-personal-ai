"""La recherche unifiée : une question fait appel à ce qui est pertinent —
code, mémoire, internet —, jamais aux trois par réflexe, jamais aux trois
en séquence quand elles peuvent tourner ensemble.

Mission « intégration unifiée » (06/09/2026, Claude Context + OpenViking +
Agent-Reach) : « ARENA reste le cerveau et l'orchestrateur principal » —
ni Claude Context, ni OpenViking, ni la couche internet (déjà existante,
DEC-0017) ne deviennent des systèmes indépendants. Ce module est le SEUL
endroit qui les compose, et il ne remplace ni n'invente aucun système de
permissions, de registre ou de routage parallèle : chaque source reste un
appel ORDINAIRE (`registre.executer(...)`, ou un agent déjà existant),
donc chaque appel reste soumis aux permissions/confirmations déjà en place.

**Pourquoi une heuristique par mots-clés, pas un modèle** : la même
discipline que `agents/orchestrator/orchestrator_agent.py` (modèle, puis
repli mots-clés) serait ici un COÛT (un aller-retour modèle) pour une
décision qui se lit déjà dans la question elle-même — « le pipeline vidéo
plante » ne demande pas un modèle pour savoir qu'il s'agit de code. Une
question mixte demande plusieurs sources ; c'est le cas normal, pas une
exception.

**Provenance, jamais fusionnée dans un bloc anonyme** (mission §7) : chaque
résultat conserve sa source (`"codebase"`, `"openviking_memory"`, `"web"`)
et l'agent qui consomme cette réponse peut donc distinguer « je sais
parce que » de « je suppose que ». Une source qui échoue (non configurée,
en panne) n'efface pas les autres — exactement la garde que DEC-0017 avait
déjà posée en parallélisant `DeepResearcherAgent`.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("usman.context.recherche_unifiee")

#: Signaux qui orientent vers le code — Claude Context (`core/connectors/
#: claude_context.py`) et, en repli, Graphify (DEC-0046) restent hors de ce
#: module : celui-ci ne choisit qu'ENTRE les trois sources de la mission.
MOTS_CODE = (
    "code", "fonction", "implement", "classe", "connecteur", "fichier",
    "module", "pipeline", "bug", "erreur dans", "où est", "ou est",
    "architecture", "agent ", "capacité", "capacite",
)

#: Signaux qui orientent vers la mémoire/l'expérience — OpenViking.
MOTS_MEMOIRE = (
    "déjà résolu", "deja resolu", "expérience", "experience", "souvenir",
    "la dernière fois", "la derniere fois", "historique", "précédemment",
    "precedemment", "décision", "decision", "on avait", "nous avions",
)

#: Signaux qui orientent vers internet — la couche existante (DEC-0017 :
#: `FreshInfoAgent`/`DeepResearcherAgent`), jamais Agent-Reach (refusé,
#: DEC-0017, reconfirmé DEC-0058).
MOTS_INTERNET = (
    "dernière version", "derniere version", "internet", "sur le web",
    "documentation officielle", "actualité", "actualite", "aujourd'hui",
    "en ligne", "recherche web", "vérifie si", "verifie si",
)


def sources_pertinentes(question: str) -> List[str]:
    """Les sources que la question appelle, dans un ordre stable — jamais
    devinées au-delà de ce que le texte contient réellement."""
    texte = (question or "").lower()
    trouvees = []
    if any(mot in texte for mot in MOTS_CODE):
        trouvees.append("code")
    if any(mot in texte for mot in MOTS_MEMOIRE):
        trouvees.append("memoire")
    if any(mot in texte for mot in MOTS_INTERNET):
        trouvees.append("internet")
    return trouvees


async def _executer_connecteur(registre: Any, nom: str, capacite: str, **parametres: Any) -> Any:
    """Un appel `registre.executer(...)`, synchrone ou pas — même garde que
    `VideoProductionAgent._executer_drift`, avec une différence load-bearing
    ICI : le registre réel est SYNCHRONE et BLOQUANT (httpx, sous-processus).
    L'appeler directement dans une coroutine bloquerait la boucle asyncio
    entière le temps de l'appel — exactement le défaut que DEC-0017 avait
    corrigé pour `DeepResearcherAgent` (trois recherches lancées en
    séquence malgré un `asyncio.gather` de façade). Mesuré par sabotage
    ici aussi (`tests/core/test_recherche_unifiee.py::TestParallelisme`) :
    un simple appel direct fait retomber ce test en séquentiel.
    """
    if inspect.iscoroutinefunction(registre.executer):
        return await registre.executer(nom, capacite, **parametres)
    return await asyncio.to_thread(registre.executer, nom, capacite, **parametres)


def _corps(resultat: Any) -> Dict[str, Any]:
    """`ResultatAction.to_dict()` si c'en est un, sinon le dict tel quel —
    même traduction que `_depuis_resultat_action` dans production_agent.py."""
    return resultat.to_dict() if hasattr(resultat, "to_dict") else dict(resultat or {})


async def _depuis_code(registre: Any, chemin_code: str, question: str) -> Dict[str, Any]:
    corps = _corps(await _executer_connecteur(
        registre, "claude_context", "rechercher", chemin=chemin_code, requete=question))
    statut = corps.get("statut", corps.get("status"))
    favorable = statut in ("SUCCESS", "PARTIAL")
    return {
        "source": "codebase", "favorable": favorable,
        "resume": corps.get("message") or corps.get("response") or "",
        "resultats": (corps.get("detail") or {}).get("resultats") or [],
    }


async def _depuis_memoire(registre: Any, question: str, session_id: Optional[str]) -> Dict[str, Any]:
    parametres: Dict[str, Any] = {"requete": question}
    if session_id:
        parametres["session_id"] = session_id
    corps = _corps(await _executer_connecteur(registre, "openviking", "contexte", **parametres))
    statut = corps.get("statut", corps.get("status"))
    favorable = statut in ("SUCCESS", "PARTIAL")
    detail = corps.get("detail") or {}
    return {
        "source": "openviking_memory", "favorable": favorable,
        "resume": corps.get("message") or corps.get("response") or "",
        "rendu": detail.get("rendu") or "", "entrees": detail.get("entrees") or [],
    }


async def _depuis_internet(fresh_info_agent: Any, question: str) -> Dict[str, Any]:
    resultat = await fresh_info_agent.run(question)
    favorable = resultat.get("status") in ("success", "warning") and bool(resultat.get("sources"))
    return {
        "source": "web", "favorable": favorable,
        "resume": resultat.get("response") or "",
        "sources": resultat.get("sources") or [],
    }


async def rechercher_unifie(
    question: str, *,
    registre: Any = None,
    fresh_info_agent: Any = None,
    chemin_code: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Fait appel à ce qui est pertinent pour `question`, en parallèle, et
    fusionne avec provenance.

    Args:
        registre: le registre des connecteurs (pour `claude_context` et
            `openviking`) — absent, ces deux sources sont sautées, jamais
            simulées.
        fresh_info_agent: l'agent internet déjà existant (DEC-0017) — absent,
            la source `internet` est sautée.
        chemin_code: le dossier à interroger via Claude Context — sans lui,
            la source `code` est sautée même si la question l'appelle (un
            index sans dossier ne veut rien dire).
        session_id: transmis à OpenViking pour l'expansion de requête et la
            déduplication entre tours, quand une session existe.

    Returns:
        `{"status", "sources_interrogees", "resultats", "response"}`.
        `resultats` est une liste, une entrée par source réellement
        interrogée, chacune portant sa `source` — jamais un bloc fusionné
        qui perdrait la provenance.
    """
    demandees = sources_pertinentes(question)
    if not demandees:
        return {
            "status": "warning", "sources_interrogees": [], "resultats": [],
            "response": "Aucune source pertinente identifiée pour cette question.",
        }

    taches: Dict[str, Any] = {}
    if "code" in demandees and registre is not None and chemin_code:
        taches["code"] = _depuis_code(registre, chemin_code, question)
    if "memoire" in demandees and registre is not None:
        taches["memoire"] = _depuis_memoire(registre, question, session_id)
    if "internet" in demandees and fresh_info_agent is not None:
        taches["internet"] = _depuis_internet(fresh_info_agent, question)

    if not taches:
        return {
            "status": "warning", "sources_interrogees": [], "resultats": [],
            "response": (
                f"Source(s) identifiée(s) ({', '.join(demandees)}) mais aucune n'est "
                "disponible ici (registre ou agent internet non branché)."),
        }

    bruts = await asyncio.gather(*taches.values(), return_exceptions=True)

    resultats: List[Dict[str, Any]] = []
    for nom_source, brut in zip(taches, bruts, strict=True):
        if isinstance(brut, Exception):
            logger.warning("Source %s en échec : %s", nom_source, brut)
            resultats.append({
                "source": {"code": "codebase", "memoire": "openviking_memory",
                          "internet": "web"}[nom_source],
                "favorable": False, "resume": f"Erreur : {brut}",
            })
        else:
            resultats.append(brut)

    favorables = [r for r in resultats if r.get("favorable")]
    lignes = [f"[{r['source']}] {r['resume']}" for r in resultats if r.get("resume")]
    return {
        "status": "success" if favorables else "warning",
        "sources_interrogees": list(taches),
        "resultats": resultats,
        "response": "\n\n".join(lignes) or "Aucune source n'a rendu de résultat exploitable.",
    }
