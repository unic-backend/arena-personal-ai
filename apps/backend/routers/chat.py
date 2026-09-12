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
from pydantic import BaseModel, Field

from agents.video_analyzer.video_analyzer_agent import demande_de_suivi
from apps.backend.config import AGENTS_SPECIALISES, MEDIA_DIR
from apps.backend.prompts import prompt_avec_methode
from apps.backend.runtime import (
    audio_agent,
    browser_agent,
    coder_agent,
    dioumtoukay_agent,
    editor_agent,
    email_agent,
    executive_agent,
    fast_provider,
    finance_agent,
    formel_agent,
    fresh_agent,
    graphrag_tool,
    lightrag_tool,
    memory,
    montage_agent,
    orchestrator,
    plaquiste_agent,
    publisher_agent,
    reasoning_engine,
    registre,
    repo_engineer,
    researcher_agent,
    social_agent,
    subtitle_agent,
    swe_agent,
    trend_agent,
    ui_agent,
    video_agent,
    video_production_agent,
    vision_agent,
)
from apps.backend.security import limiter_debit, validate_media_path, verify_api_key
from apps.backend.studio import lancer_studio
from core.architecture.plan import executer as executer_architecture
from core.context.recherche_unifiee import MOTS_MEMOIRE
from tools.documents.indexer import (
    DOSSIER_DOCUMENTS,
    FICHIER_INVENTAIRE,
    Rapport,
    indexer_documents,
)
from tools.rag.lightrag_tool import est_un_echec as lightrag_echec

logger = logging.getLogger("usman.backend")

router = APIRouter()


class ChatRequest(BaseModel):
    prompt: str
    session_id: Optional[str] = "default"
    video_path: Optional[str] = None
    region: Optional[str] = "Sénégal"
    attachments: List[str] = Field(default_factory=list)
    # Les deux champs suivants ne servent qu'a PLAQUISTE (chapitre metier,
    # capture deterministe du destinataire d'un devis — DEC a venir) :
    # `history` porte les tours precedents, structures ; `message_actuel`
    # porte la derniere phrase seule, distincte de `prompt` qui devient le
    # fil entier aplati pour cette seule intention (voir pwa_gateway.py).
    # Vides pour tout le reste de l'API, qui continue de ne lire que `prompt`.
    history: List[Dict[str, str]] = Field(default_factory=list)
    message_actuel: Optional[str] = None


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


#: Ou ARENA va chercher les rushes du proprietaire. Ses fichiers a lui : ce
#: qu il a televerse, ce qui est arrive, et les extraits deja decoupes.
#: `media/rendered` n en est pas : remonter ses propres rendus dans
#: l inventaire ferait boucler un montage sur lui-meme.
DOSSIERS_MONTABLES = ("source", "incoming", "clips", "downloads")

#: Ce qu une timeline sait poser. Une extension absente d ici n entre pas dans
#: l inventaire : le modele ne doit pas apprendre le nom d un fichier que le
#: montage refuserait ensuite.
EXTENSIONS_MONTABLES = frozenset({
    ".mp4", ".mov", ".mkv", ".webm", ".avi",
    ".jpg", ".jpeg", ".png", ".webp",
    ".mp3", ".wav", ".m4a", ".aac",
})


#: Ce que Faceplugin sait lire. Sous-ensemble strict de `EXTENSIONS_MONTABLES` :
#: lui envoyer un `.mp4` echouerait dans le moteur, apres coup.
EXTENSIONS_IMAGES = frozenset({".jpg", ".jpeg", ".png", ".webp"})

#: Ce qui distingue « compose-moi un design system » d'une simple question de
#: style. Le moteur repond aux deux, mais pas avec la meme chose.
FORMES_DESIGN_SYSTEM = (
    "design system", "design-system", "systeme de design", "système de design",
    "charte graphique", "identite visuelle", "identité visuelle",
)


def _veut_un_design_system(demande: str) -> bool:
    """Vrai si la demande reclame un systeme complet, pas une recherche."""
    texte = demande.lower()
    return any(forme in texte for forme in FORMES_DESIGN_SYSTEM)


def images_analysables(video_path: Optional[str] = None) -> List[str]:
    """Ses images, et elles seules — meme discipline que `medias_montables`."""
    return [c for c in medias_montables(video_path)
            if Path(c).suffix.lower() in EXTENSIONS_IMAGES]


def _issue_en_reponse(issue: Any) -> Dict[str, Any]:
    """Un `ResultatAction` de connecteur, dans la forme que rend ce routeur.

    Reutilise la structure existante plutot que d'en inventer une : `status`,
    `response`, et le detail du connecteur. Rien n'est reformule — un resultat
    qui se ferait embellir en passant ici ne serait plus le sien.
    """
    favorable = issue.statut.value in {"SUCCESS", "PARTIAL", "NEEDS_CONFIRMATION"}
    return {
        "status": "success" if favorable else "error",
        "response": issue.message,
        "statut_connecteur": issue.statut.value,
        "detail": issue.detail or {},
    }


def _contexte_openviking(prompt: str, session_id: str) -> Optional[str]:
    """Un souvenir pertinent, injecte dans la conversation ordinaire — jamais
    interroge par reflexe, seulement quand la phrase le demande elle-meme
    ("on a deja regle ca", `MOTS_MEMOIRE`, `core/context/recherche_unifiee.py`).

    C'etait la capacite qu'OpenViking apportait (DEC-0058) sans qu'aucun
    chemin de conversation reel ne l'appelle jamais : reachable pour
    `scripts/orphelins.py` via `/api/contexte/rechercher`, mais aucune
    phrase d'Ousmane ne pouvait l'atteindre. C'est ici, dans le CHAT
    ordinaire — le seul chemin que chaque message sans intention metier
    emprunte — qu'elle sert reellement.

    Un service absent ou en panne ne casse jamais la conversation :
    `registre.executer` rend NON_CONFIGURE/FAILED sans lever, et ce
    contexte est alors silencieusement omis, comme le reste de cette
    integration (DEC-0002 : une capacite absente se rapporte, jamais
    simulee).
    """
    if not any(mot in prompt.lower() for mot in MOTS_MEMOIRE):
        return None
    issue = registre.executer("openviking", "contexte", requete=prompt, session_id=session_id)
    if issue.statut.value not in {"SUCCESS", "PARTIAL"}:
        return None
    rendu = (issue.detail or {}).get("rendu")
    return f"[Contexte pertinent de vos echanges precedents]\n{rendu}" if rendu else None


def _analyse_de_visages(demande: str, images: List[str]) -> Dict[str, Any]:
    """Choisit la capacite Faceplugin d'apres la demande, puis l'execute.

    **Aucune image n'est inventee.** Sans image dans son inventaire, on le dit
    au lieu de fabriquer un chemin : le moteur echouerait de toute facon, mais
    plus tard et moins clairement.

    « Comparer » demande deux images : avec une seule, on refuse ici plutot
    que de comparer une image avec elle-meme, ce qui rendrait 100 et se lirait
    comme un resultat.
    """
    texte = demande.lower()
    if not images:
        return {"status": "error",
                "response": "Aucune image dans tes fichiers : dépose-les d'abord."}

    if any(f in texte for f in ("compare", "même personne", "meme personne")):
        if len(images) < 2:
            return {"status": "error",
                    "response": "Comparer demande deux images ; il n'y en a qu'une."}
        return _issue_en_reponse(registre.executer(
            "faceplugin", "comparer", image=images[0], image2=images[1]))

    if any(f in texte for f in ("caracteristique", "caractéristique", "gabarit")):
        capacite = "caracteristiques"
    elif any(f in texte for f in ("repere", "repère", "landmark", "points du visage")):
        capacite = "reperes"
    else:
        capacite = "detecter"
    return _issue_en_reponse(registre.executer("faceplugin", capacite, image=images[0]))


def medias_montables(video_path: Optional[str] = None) -> List[str]:
    """Les fichiers que le modele a le droit de monter, et eux seuls.

    L inventaire est construit ICI, cote serveur, jamais depuis la reponse du
    modele : c est la moitie backend de la garantie que
    `core/montage/planificateur.py` tient de son cote.
    """
    chemins: List[str] = []
    for dossier in DOSSIERS_MONTABLES:
        racine = MEDIA_DIR / dossier
        if not racine.is_dir():
            continue
        for fichier in sorted(racine.iterdir()):
            if fichier.is_file() and fichier.suffix.lower() in EXTENSIONS_MONTABLES:
                chemins.append(str(fichier))

    # Un fichier explicitement designe par le proprietaire entre aussi, a
    # condition de rester dans media/ — `validate_media_path` leve sinon.
    if video_path:
        chemins.append(str(validate_media_path(video_path)))
    return chemins


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


def a_produit_un_texte(contenu: Optional[str]) -> bool:
    """Un agent a-t-il reellement rendu quelque chose ?

    Separe de `garantir_un_texte` parce que l'appelant a besoin des deux
    reponses : le texte a montrer, et de quoi choisir le bon statut. Une
    reponse vide annoncee `success` est un mensonge que le client ne peut pas
    detecter.
    """
    return bool(contenu and contenu.strip())


def garantir_un_texte(contenu: Optional[str], source: str,
                      alternative: str = "") -> str:
    """Empeche qu'une reponse vide parte comme si c'etait une reponse.

    Chaque branche d'aiguillage lit `.get("response", "")`. Un agent qui
    echoue renvoie un dictionnaire sans cette cle, donc la chaine vide — et
    `"" is not None` est vrai. LibreChat affichait alors **une bulle
    entierement vide**, sans texte ni erreur. Observe le 2026-08-26 sur
    `usman-research`.

    Le garde n'existait que sur la passerelle OpenAI. Mesure du 01/09/2026 :
    la PWA rendait `{"type": "token", "text": ""}` puis `done`, et
    `/api/chat` rendait `{"status": "success", "response": ""}` — la meme
    bulle vide, sur les deux autres surfaces, dont celle que le proprietaire
    utilise. D'ou son deplacement ici, ou les trois surfaces l'atteignent.

    Args:
        source: ce qui n'a rien produit — un agent, une intention, un modele.
        alternative: quoi essayer a la place, quand l'appelant en connait une.
            Vide par defaut : « choisis usman-chat » ne veut rien dire sur une
            interface sans menu de modeles.
    """
    if a_produit_un_texte(contenu):
        return contenu

    logger.warning("« %s » n'a produit aucun texte", source)
    return (
        f"`{source}` n'a produit aucune réponse.\n\n"
        "Ce n'est pas un refus : l'agent s'est arrêté sans rien renvoyer. "
        "Les journaux du serveur disent à quelle étape. "
        f"Reformule la demande{alternative}."
    )


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
        # Le session_id porte l'historique : sans lui, une question elliptique
        # ("Celle de 2006 ?" apres une question sur une coupe du monde) part en
        # recherche telle quelle et cherche le mauvais sujet.
        result = await fresh_agent.run(request.prompt, context={"session_id": session_id})
    elif intent == "STUDIO":
        result = await lancer_studio(video_agent, editor_agent, subtitle_agent)
    elif intent == "EMAIL":
        # Son courrier : lecture et tri, ou brouillon soumis a confirmation.
        # Le contexte porte le destinataire quand il y en a un — il n'est jamais
        # lu dans la phrase.
        result = await email_agent.run(request.prompt, context={"session_id": session_id})
    elif intent == "SOCIAL":
        # Ses reseaux : la capacite est choisie par l'agent a partir de sa
        # phrase — il n'a jamais a nommer une competence.
        result = await social_agent.run(request.prompt, context={"session_id": session_id})
    elif intent == "PLAQUISTE":
        # Sans les pieces jointes, un plan envoye par upload PWA reste invisible :
        # seul un chemin tape en texte peut alors etre mesure. `historique` et
        # `message_actuel` alimentent la capture deterministe du destinataire
        # d'un devis (nom du client, lieu) — jamais devinee dans une phrase
        # libre, seulement quand elle repond a une question posee au tour
        # precedent (agents/plaquiste/plaquiste_agent.py).
        result = await plaquiste_agent.run(request.prompt, context={
            "attachments": request.attachments,
            "historique": request.history,
            "message_actuel": request.message_actuel,
        })
    elif intent == "BROWSER":
        result = await browser_agent.run(request.prompt)
    elif intent == "ARCHITECTURE_3D":
        # DEC-0070 : **aucun agent ici**, et c'est voulu. La mission interdit
        # d'en creer un quand la capacite se suffit : la phrase devient un
        # plan deterministe (`core/architecture/plan.py`, sans modele), et le
        # plan devient des appels au connecteur, qui applique permissions,
        # confirmation et journal. Un modele peut produire le meme plan sans
        # rien changer en aval — c'est ce qui rend la capacite agnostique.
        result = executer_architecture(registre, request.prompt, session=session_id)
    elif intent == "PREUVE_FORMELLE":
        # Lean tranche, jamais le modele (DEC-0067). L'agent est mince : il
        # traduit la phrase en capacite du connecteur `formel` et rend le
        # verdict tel quel — un `status` de succes ici veut dire qu'un
        # binaire a compile la preuve, pas qu'un modele l'a affirmee.
        result = await formel_agent.run(request.prompt)
    elif intent == "SWE_FIX":
        result = await swe_agent.run(request.prompt)
    elif intent == "REPO_ENGINEERING":
        result = await repo_engineer.run(request.prompt)
    elif intent == "ATELIER":
        # Dioumtoukay AGIT : il ouvre les fichiers, lance les commandes, touche
        # au depot. C'est ce qui le separe de `repo_engineer` juste au-dessus,
        # qui lit et propose sans jamais rien modifier. DEC-0038.
        result = await dioumtoukay_agent.run(request.prompt, context={
            "session_id": session_id,
        })
    elif intent == "RAG_DOCS":
        # Ses documents restent hors de l index tant que personne ne les y met.
        # Jusqu ici, aucune phrase ne declenchait l indexation : le moteur ne
        # pouvait repondre que sur ce qui n avait jamais ete indexe.
        if demande_d_indexation(request.prompt):
            result = await indexer_ses_documents()
        else:
            reponse_docs = lightrag_tool.query(request.prompt, mode="hybrid")
            # Un moteur documentaire absent rend une phrase d'erreur, pas une
            # reponse : l'annoncer sans statut la faisait lire comme un resultat.
            result = {"response": reponse_docs, "agent": "LightRAG",
                      "status": "error" if lightrag_echec(reponse_docs) else "success"}
    elif intent == "GRAPHRAG":
        result = graphrag_tool.query_global(request.prompt)
    elif intent == "VISION":
        result = await vision_agent.run(request.prompt, context={"attachments": request.attachments})
    elif intent == "AUDIO":
        # Meme inventaire que le montage : ses fichiers, et rien d autre.
        # `medias_montables` couvre deja l audio (mp3, wav, m4a...) en plus
        # de la video, et la transcription lit les deux.
        result = await audio_agent.run(
            request.prompt, context={"medias": medias_montables(request.video_path)})
    elif intent == "MONTAGE":
        # L inventaire ouvert au modele : ses propres fichiers, et rien
        # d autre. `validate_media_path` tient deja la frontiere du dossier
        # media/ — le planificateur, lui, empeche le modele de nommer un
        # chemin du tout (`core/montage/planificateur.py`).
        result = await montage_agent.run(
            request.prompt, context={"medias": medias_montables(request.video_path)})
    elif intent == "VIDEO_PROJET":
        # Meme inventaire que MONTAGE et AUDIO : ses fichiers reels, jamais
        # un chemin cite par le modele (core/production/plan_video.py fait
        # deja la meme substitution par index, cote serveur).
        result = await video_production_agent.run(
            request.prompt, context={"references": medias_montables(request.video_path)})
    elif intent == "DEEP_RESEARCH":
        result = await researcher_agent.run(request.prompt)
    elif intent == "CODE_EXECUTION":
        result = await coder_agent.run(request.prompt)
    elif intent == "TREND_SEARCH":
        result = await trend_agent.run(request.prompt, context={"region": request.region})
    elif intent == "FINANCE":
        # Donnees reelles -> calcul deterministe -> risque -> interpretation
        # (agents/finance/finance_agent.py). Jamais d'ordre reel : aucune
        # capacite d'ecriture n'existe sur le connecteur market_data.
        result = await finance_agent.run(request.prompt)
    elif intent == "EXECUTIVE":
        # Executive Intelligence (mission ARENA x OPENEXECUTIVE, DEC-0086) :
        # coordonne les specialistes existants d'ARENA, jamais un second
        # agent-plateforme. Recommande seulement — aucune action consequente
        # n'est executee ici (core/executive/moteur.py).
        result = await executive_agent.run(request.prompt)
    elif intent == "VISAGE":
        # Analyse de visages par le SDK Faceplugin, via le registre — jamais
        # en direct : c'est le registre qui applique la permission, et deux de
        # ces quatre capacites sont de la biometrie, donc soumises a
        # confirmation (`config/permissions_services.yaml`).
        #
        # Les images viennent de SON inventaire, comme pour le montage et la
        # vision. Le modele ne nomme aucun chemin : il ne peut donc pas faire
        # analyser un fichier qu'il aurait invente.
        result = _analyse_de_visages(request.prompt, images_analysables(request.video_path))
    elif intent == "DESIGN_UI":
        # Intelligence de design (UI/UX Pro Max). Lecture pure : la demande
        # EST la requete, il n'y a aucun fichier a designer ni rien a ecrire.
        capacite = "design_system" if _veut_un_design_system(request.prompt) else "chercher"
        issue = registre.executer("ui_ux_pro_max", capacite, requete=request.prompt)
        result = _issue_en_reponse(issue)
    elif intent == "UI_GENERATE":
        # Generer une interface EN CODE, distinct de DESIGN_UI (decider a
        # quoi ca doit ressembler, sans rien ecrire) — DEC-0050.
        result = await ui_agent.run(request.prompt)
    elif intent == "VIDEO_ANALYSIS":
        # « ou en est ma video ? » ne parle d aucun fichier. Reclamer un chemin
        # ici renvoyait une erreur a une question parfaitement claire.
        if demande_de_suivi(request.prompt):
            result = await video_agent.run(request.prompt)
        elif request.video_path:
            v_path = validate_media_path(request.video_path)
            result = await video_agent.run(request.prompt, context={"video_path": str(v_path)})
        else:
            # Aucun chemin fourni : jamais de repli sur un fichier de test
            # (`test_video.mp4`) qui ferait analyser une video qui n'est pas
            # la sienne comme si elle l'etait (audit externe, commit
            # f7f0478). `VideoAnalyzerAgent.run` sait deja repondre
            # honnetement a l'absence de video ("Aucune video valide fournie
            # pour l'analyse") — ce chemin lui laisse simplement le faire.
            result = await video_agent.run(request.prompt, context={})
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
        intention = result.get("intent", "CHAT")
        # Une reponse vide annoncee `success` est un mensonge que le client ne
        # peut pas detecter : il affiche une bulle vide et n'a rien a dire au
        # proprietaire. Le statut suit ce qui s'est reellement passe.
        vide = not a_produit_un_texte(result.get("response"))
        return {
            "status": "error" if vide else "success",
            "model": fast_provider.model_name,
            "intent": intention,
            "agent": result.get("agent", "OrchestratorAgent"),
            "sources": result.get("sources", []),
            "response": garantir_un_texte(result.get("response"), intention),
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
        # Quatrieme surface, meme trou : un agent muet envoyait un jeton vide
        # suivi de `[DONE]`. Le garde est le meme partout depuis le 01/09/2026.
        texte = garantir_un_texte(result.get("response"), intent)
        async def text_gen():
            yield f"data: {json.dumps({'token': texte, 'intent': intent})}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(text_gen(), media_type="text/event-stream")
    else:
        history = memory.get_recent_history(session_id=session_id, limit=6)
        memory.add_chat_message(session_id=session_id, role="user", content=request.prompt)

        system_prompt = prompt_avec_methode(request.prompt, intent)

        prompt_lines = []
        contexte_memoire = _contexte_openviking(request.prompt, session_id)
        if contexte_memoire:
            prompt_lines.append(contexte_memoire)
        for msg in history:
            role_label = memory.get_fact("owner") or "Ousmane" if msg["role"] == "user" else "Usman"
            prompt_lines.append(f"{role_label}: {msg['content']}")
        prompt_lines.append(f"{memory.get_fact('owner') or 'Ousmane'}: {request.prompt}")
        prompt_lines.append("Usman:")
        full_prompt = "\n".join(prompt_lines)

        async def token_generator():
            """Le flux finit toujours, meme quand la generation tombe.

            Sans le `try`, une panne du fournisseur (Ollama eteint) faisait
            remonter l'exception DANS la reponse deja commencee : le client
            recevait un `200` et **zero ligne** — un flux vide indistinguable
            d'une reponse vide. Mesure du 01/09/2026. `pwa_gateway.flux` tient
            deja cette regle ; celui-ci ne la tenait pas.
            """
            full_reply = ""
            try:
                async for token in fast_provider.generate_stream(full_prompt, system_prompt):
                    full_reply += token
                    yield f"data: {json.dumps({'token': token, 'intent': intent})}\n\n"
            except Exception as souci:  # noqa: BLE001 - le flux doit finir proprement
                logger.error("Flux /api/chat/stream interrompu : %s", souci, exc_info=True)
                yield "data: " + json.dumps(
                    {"type": "error",
                     "message": f"ARENA n'a pas pu terminer : {souci}"}) + "\n\n"
                # Le tour du proprietaire est deja en memoire (ligne au-dessus) :
                # sans reponse, l'historique garderait une question orpheline.
                # On y ecrit ce qui s'est reellement passe, jamais une reponse
                # fabriquee.
                memory.add_chat_message(
                    session_id=session_id, role="assistant",
                    content=f"[interrompu : {type(souci).__name__}]")
                yield "data: [DONE]\n\n"
                return

            if not a_produit_un_texte(full_reply):
                # Un flux qui se ferme sans un mot : le client afficherait une
                # bulle vide. Le routeur replie deja quand un fournisseur rend
                # du vide (DEC-0032) ; s'il n'en restait aucun, on le dit.
                texte_vide = garantir_un_texte(full_reply, intent)
                yield "data: " + json.dumps(
                    {"type": "error", "message": texte_vide}) + "\n\n"
                memory.add_chat_message(session_id=session_id, role="assistant",
                                        content="[aucune reponse produite]")
                yield "data: [DONE]\n\n"
                return

            memory.add_chat_message(session_id=session_id, role="assistant", content=full_reply.strip())
            yield "data: [DONE]\n\n"

        return StreamingResponse(token_generator(), media_type="text/event-stream")
