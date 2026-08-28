"""Conversation et aiguillage vers les agents.

`dispatch_request` est le point ou une demande devient le travail d'un agent
precis. L'intention y est calculee une seule fois : elle coute un appel au
modele.
"""

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from agents.video_analyzer.video_analyzer_agent import demande_de_suivi
from apps.backend.config import AGENTS_SPECIALISES, MEDIA_DIR
from apps.backend.prompts import get_arena_system_prompt
from apps.backend.runtime import (
    browser_agent,
    coder_agent,
    editor_agent,
    email_agent,
    fast_provider,
    fresh_agent,
    graphrag_tool,
    lightrag_tool,
    memory,
    orchestrator,
    plaquiste_agent,
    publisher_agent,
    reasoning_engine,
    repo_engineer,
    researcher_agent,
    subtitle_agent,
    swe_agent,
    trend_agent,
    video_agent,
)
from apps.backend.security import limiter_debit, validate_media_path, verify_api_key
from apps.backend.studio import lancer_studio
from tools.documents.indexer import (
    DOSSIER_DOCUMENTS,
    FICHIER_INVENTAIRE,
    Rapport,
    indexer_documents,
)

logger = logging.getLogger("usman.backend")

router = APIRouter()


class ChatRequest(BaseModel):
    prompt: str
    session_id: Optional[str] = "default"
    video_path: Optional[str] = None
    region: Optional[str] = "Sénégal"


# Formulations par lesquelles l utilisateur reclame les sources. Decision du
# proprietaire, 2026-08-26 : la liste des adresses alourdit chaque reponse alors
# qu il ne la lit presque jamais. Elle n est donc plus affichee par defaut.
#
# La reponse continue de porter ses numeros [1], [2] : ils viennent du modele et
# disent sur quelle source chaque affirmation repose. Ce qui disparait, c est la
# liste d adresses en bas — jamais la tracabilite elle-meme, qui reste dans le
# champ `sources` de la reponse de l agent.
DEMANDES_DE_SOURCES = (
    "source", "sources", "référence", "reference", "d'où", "d ou", "d'ou",
    "lien", "liens", "url", "prouve", "preuve", "vérifiable", "verifiable",
)


def sources_demandees(question: str) -> bool:
    """Dit si l utilisateur a reclame les adresses de ses sources."""
    texte = (question or "").lower()
    return any(mot in texte for mot in DEMANDES_DE_SOURCES)


def formater_sources(sources: List[Dict[str, Any]], question: str = "") -> str:
    """Rend la liste des sources, uniquement si elle a ete demandee.

    Le format OpenAI n a pas de champ pour des sources : sans cela, le lecteur ne
    saurait pas d ou vient la reponse. Mais l afficher a chaque fois encombre —
    d ou le declenchement a la demande.
    """
    if not sources or not sources_demandees(question):
        return ""
    lignes = [f"[{s['index']}] {s['title']} — {s['url']}" for s in sources]
    return "\n\n**Sources**\n" + "\n".join(lignes)


#: Ce que le moteur de raisonnement ecrit quand le calcul n a PAS eu lieu.
#: Le prompt de synthese recoit deja cette phrase, mais une consigne n est pas
#: une garantie : sans cette relecture, le modele pouvait presenter un resultat
#: elegant sans dire qu aucun calcul ne l avait verifie.
CALCUL_REFUSE = "Erreur calcul"


def note_de_calcul(calcul: str) -> str:
    """Ce qu il faut ajouter a la reponse quand le calcul a ete refuse.

    Chaine vide quand le calcul a eu lieu, ou quand il n y en avait pas a faire :
    on n ajoute pas un avertissement a une reponse qui ne pretend rien calculer.
    """
    if not calcul or not calcul.startswith(CALCUL_REFUSE):
        return ""
    return ("\n\n⚠️ Le calcul n a pas pu etre execute : "
            f"{calcul[len(CALCUL_REFUSE):].lstrip(' :')} "
            "Ce qui precede n a donc ete verifie par aucun calcul.")


#: Ce qui demande d INDEXER ses documents, et non de les interroger.
#: « d apres mes documents, ... » est une question ; « indexe mes documents » est
#: un travail sur le classeur. Les deux arrivent par la meme intention RAG_DOCS,
#: et seule la phrase les separe.
DEMANDE_D_INDEXATION = re.compile(
    r"(indexe|indexer|indexation|r[ée]indexe|reindexer"
    r"|mets? [àa] jour (?:mes|les) documents"
    r"|prends? en compte (?:mes|les) (?:nouveaux )?documents)",
    re.IGNORECASE,
)


def demande_d_indexation(question: str) -> bool:
    """Dit si la phrase demande d indexer le classeur plutot que de l interroger."""
    return bool(DEMANDE_D_INDEXATION.search(question or ""))


def message_indexation(rapport: Rapport) -> str:
    """Ce qui s est reellement passe, en une phrase. Aucun compte n est refait ici.

    Le rapport ne porte que des noms de fichiers et des comptes — jamais le
    contenu des documents, qui porte des noms de clients et des montants.
    """
    if rapport.statut == "REFUSE":
        return f"Rien n a ete indexe. {rapport.raison}"
    if rapport.statut == "RIEN_A_FAIRE":
        return (f"Tes documents sont deja indexes : {len(rapport.inchanges)} inchange(s), "
                "rien a refaire.")
    return f"Indexation terminee — {rapport}"


async def indexer_ses_documents(
    moteur: Any = None,
    dossier: Optional[Path | str] = None,
    inventaire: Optional[Path | str] = None,
    verifier: bool = True,
) -> Dict[str, Any]:
    """Indexe son classeur sur demande, et rend ce qui s est vraiment passe.

    L indexation lit des fichiers et fait travailler Ollama : elle part dans un
    fil separe, sinon elle gelerait la boucle du serveur — donc toutes les
    conversations, pas seulement celle-ci.

    Les parametres sont injectables pour les tests ; en production, ce sont ceux
    de l indexeur, et le moteur est LightRAG.
    """
    rapport = await asyncio.to_thread(
        indexer_documents,
        lightrag_tool if moteur is None else moteur,
        DOSSIER_DOCUMENTS if dossier is None else dossier,
        FICHIER_INVENTAIRE if inventaire is None else inventaire,
        verifier,
    )
    logger.info("Indexation des documents : %s", rapport.resume())
    return {"response": message_indexation(rapport), "agent": "IndexeurDocuments",
            "indexation": rapport.resume()}


async def dispatch_request(request: ChatRequest, intent: Optional[str] = None) -> Dict[str, Any]:
    """Aiguille la demande vers l'agent choisi.

    `intent` permet a l'appelant de transmettre une classification deja faite :
    elle coute un appel au modele, inutile de la refaire.
    """
    session_id = request.session_id or "default"
    if intent is None:
        intent = await orchestrator.analyze_intent(request.prompt)
    logger.info(f"Intention détectée par Usman: {intent}")

    if intent == "DEEP_REASONING":
        # Jusqu ici, « resous cette equation » recevait une passe du modele
        # rapide et un chiffre sorti de sa tete. Le moteur de raisonnement
        # planifie, EXECUTE le calcul en bac a sable, puis redige a partir du
        # resultat obtenu — et quand le bac a sable refuse, la reponse le dit.
        raisonnement = await reasoning_engine.solve_complex_task(request.prompt)
        calcul = raisonnement.get("calculation_result") or ""
        result = {
            "status": raisonnement.get("status", "success"),
            "agent": "ReasoningEngine",
            "plan": raisonnement.get("plan", ""),
            # Le calcul voyage avec la reponse : sans lui, personne ne peut
            # verifier que le chiffre annonce vient d une execution.
            "calcul": calcul,
            "response": raisonnement.get("final_response", "") + note_de_calcul(calcul),
        }
    elif intent == "FRESH_INFO":
        result = await fresh_agent.run(request.prompt)
    elif intent == "STUDIO":
        result = await lancer_studio(video_agent, editor_agent, subtitle_agent)
    elif intent == "EMAIL":
        # Son courrier : lecture et tri, ou brouillon soumis a confirmation.
        # Le contexte porte le destinataire quand il y en a un — il n'est jamais
        # lu dans la phrase.
        result = await email_agent.run(request.prompt, context={"session_id": session_id})
    elif intent == "PLAQUISTE":
        result = await plaquiste_agent.run(request.prompt)
    elif intent == "BROWSER":
        result = await browser_agent.run(request.prompt)
    elif intent == "SWE_FIX":
        result = await swe_agent.run(request.prompt)
    elif intent == "REPO_ENGINEERING":
        result = await repo_engineer.run(request.prompt)
    elif intent == "RAG_DOCS":
        # Ses documents restent hors de l index tant que personne ne les y met.
        # Jusqu ici, aucune phrase ne declenchait l indexation : le moteur ne
        # pouvait repondre que sur ce qui n avait jamais ete indexe.
        if demande_d_indexation(request.prompt):
            result = await indexer_ses_documents()
        else:
            result = {"response": lightrag_tool.query(request.prompt, mode="hybrid"),
                      "agent": "LightRAG"}
    elif intent == "GRAPHRAG":
        result = graphrag_tool.query_global(request.prompt)
    elif intent == "DEEP_RESEARCH":
        result = await researcher_agent.run(request.prompt)
    elif intent == "CODE_EXECUTION":
        result = await coder_agent.run(request.prompt)
    elif intent == "TREND_SEARCH":
        result = await trend_agent.run(request.prompt, context={"region": request.region})
    elif intent == "VIDEO_ANALYSIS":
        # « ou en est ma video ? » ne parle d aucun fichier. Reclamer un chemin
        # ici renvoyait une erreur a une question parfaitement claire.
        if demande_de_suivi(request.prompt):
            result = await video_agent.run(request.prompt)
        else:
            raw_path = request.video_path or str(MEDIA_DIR / "source" / "test_video.mp4")
            v_path = validate_media_path(raw_path)
            result = await video_agent.run(request.prompt, context={"video_path": str(v_path)})
    elif "PUBLI" in request.prompt.upper() or "POSTER" in request.prompt.upper():
        result = await publisher_agent.run(request.prompt, context={"video_path": request.video_path})
    else:
        result = await orchestrator.run(
            user_input=request.prompt,
            context={"session_id": session_id, "intent": intent},
        )

    # L'aiguilleur sait quelle branche il a prise ; sans cela, la reponse annoncait
    # « CHAT » meme quand un agent specialise avait repondu.
    result["intent"] = intent

    memory.add_chat_message(session_id=session_id, role="user", content=request.prompt)
    memory.add_chat_message(session_id=session_id, role="assistant", content=result["response"])
    return result

@router.post("/api/chat", dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def chat_endpoint(request: ChatRequest):
    try:
        if not await fast_provider.is_available():
            return {"status": "error", "model": fast_provider.model_name, "response": "❌ Ollama hors-ligne."}

        result = await dispatch_request(request)
        return {
            "status": "success",
            "model": fast_provider.model_name,
            "intent": result.get("intent", "CHAT"),
            "agent": result.get("agent", "OrchestratorAgent"),
            "sources": result.get("sources", []),
            "response": result["response"]
        }
    except Exception as e:
        logger.error(f"Erreur endpoint chat: {e}", exc_info=True)
        return {"status": "error", "model": "error", "response": f"❌ {str(e)}"}

@router.post("/api/chat/stream", dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def chat_stream_endpoint(request: ChatRequest):
    session_id = request.session_id or "default"
    intent = await orchestrator.analyze_intent(request.prompt)

    if intent in AGENTS_SPECIALISES:
        result = await dispatch_request(request, intent=intent)
        async def text_gen():
            yield f"data: {json.dumps({'token': result['response'], 'intent': intent})}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(text_gen(), media_type="text/event-stream")
    else:
        history = memory.get_recent_history(session_id=session_id, limit=6)
        memory.add_chat_message(session_id=session_id, role="user", content=request.prompt)

        system_prompt = get_arena_system_prompt()

        prompt_lines = []
        for msg in history:
            role_label = memory.get_fact("owner") or "Ousmane" if msg["role"] == "user" else "Usman"
            prompt_lines.append(f"{role_label}: {msg['content']}")
        prompt_lines.append(f"{memory.get_fact('owner') or 'Ousmane'}: {request.prompt}")
        prompt_lines.append("Usman:")
        full_prompt = "\n".join(prompt_lines)

        async def token_generator():
            full_reply = ""
            async for token in fast_provider.generate_stream(full_prompt, system_prompt):
                full_reply += token
                yield f"data: {json.dumps({'token': token, 'intent': intent})}\n\n"

            memory.add_chat_message(session_id=session_id, role="assistant", content=full_reply.strip())
            yield "data: [DONE]\n\n"

        return StreamingResponse(token_generator(), media_type="text/event-stream")
