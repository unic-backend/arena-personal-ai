"""Passerelle vers l'interface PWA du proprietaire.

Son application React parle un protocole precis, deja ecrit et deja teste chez
lui. Deux facons de les relier existaient : reecrire son `remoteTransport.ts`
pour appeler les routes d'ARENA, ou apprendre a ARENA le langage que son app
parle. **C'est la seconde qui est retenue.**

Pourquoi : son interface fonctionne ; la casser pour l'adapter serait payer en
risque ce qu'on gagne en confort. Et le depot connait deja ce motif —
`openai_gateway.py` fait exactement cela pour LibreChat.

Le protocole, releve dans son code (`src/lib/activity/`) :

- `POST /agent/stream` — corps JSON `{text, locale, history, attachments,
  connectors, run_id, persona, memories}`, reponse en `text/event-stream`.
- Chaque trame est `data: <json>` suivie d'une ligne vide. Le JSON vaut
  `{"type":"token","text":...}`, `{"type":"done","meta":...}` ou
  `{"type":"error","message":...}`.
- **Le flux doit se terminer par `done` ou par `error`.** Son client considere
  une fermeture sans l'un des deux comme une coupure et relance la requete —
  jusqu'a trois fois. Un flux qui s'arrete en silence devient trois reponses.

**Ce qui n'est pas applique, et n'est pas fait semblant d'etre applique :**
`connectors` et `attachments` arrivent dans la requete et ne sont pas
encore utilises. Ils sont journalises, jamais ignores en silence : une interface
qui offre un reglage sans effet est pire qu'une interface qui ne l'offre pas.
`POST /files` le declare franchement plutot que d'accepter un fichier qui
n'irait nulle part.

**La memoire est appliquee** depuis le 2026-08-27, et elle vient de deux
endroits qui ne se confondent pas dans le prompt :

- **la memoire d'ARENA** (`core/memory/`), persistante, ou chaque souvenir porte
  sa source et ou une supposition reste marquee comme telle. Elle est
  interrogee par la question posee, avec un budget de caracteres — jamais
  chargee en entier ;
- **les notes de l'interface** (`memories`), que le proprietaire a tapees
  lui-meme et activees. Elles n'ont pas de source parce qu'il en est la source.

Les melanger ferait passer une note tapee vite pour un fait sourcé.

`persona`, lui, **est applique** depuis le 2026-08-27 : ses instructions
s'ajoutent au prompt systeme d'ARENA. Elles s'y **ajoutent** et ne le remplacent
pas — le reglage de ton du proprietaire ne doit pas pouvoir effacer les regles
de la plateforme. Elles ne s'appliquent qu'a la conversation : un agent
specialise (devis, recherche, code) a ses propres consignes, et un ton
« concis » ne doit pas raccourcir un devis.
"""
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from apps.backend.config import AGENTS_SPECIALISES
from apps.backend.prompts import get_arena_system_prompt
from apps.backend.routers.chat import ChatRequest, dispatch_request
from apps.backend.runtime import fast_provider, memoire_personnelle, memory, orchestrator
from apps.backend.security import limiter_debit, verify_api_key
from core.memory.recuperation import formater as formater_souvenirs
from core.memory.recuperation import recuperer

logger = logging.getLogger("usman.backend.pwa")

router = APIRouter()

# Champs que l'interface envoie et qu'ARENA ne sait pas encore honorer. Ecrits
# ici pour que le journal les nomme un par un, plutot qu'un vague « ignore ».
CHAMPS_NON_APPLIQUES = ("connectors", "attachments")

# Budget de la memoire dans le prompt. Volontairement modeste : ce qui est
# retrouve doit aider la reponse, pas la ralentir. Un prompt qui grossit avec
# la memoire finit par ne plus tenir.
BUDGET_MEMOIRE = 1200

# Nombre maximal de notes de l'interface reprises. Elles viennent du navigateur.
NOTES_INTERFACE_MAX = 20

TITRE_MEMOIRE_ARENA = "Ce dont je me souviens et qui se rapporte a la demande (chaque ligne porte sa source) :"
TITRE_NOTES_INTERFACE = "Notes que le proprietaire a saisies lui-meme dans son interface :"

# Longueur maximale des instructions de persona ajoutees au prompt systeme.
# Elles viennent du navigateur : sans plafond, un reglage colle par megarde
# pousserait la conversation hors de la fenetre du modele.
PERSONA_MAX_CARACTERES = 2000

TITRE_PERSONA = "Preferences du proprietaire (elles completent les regles ci-dessus, sans les remplacer) :"


class DemandeAgent(BaseModel):
    """Le corps envoye par `remoteTransport.ts`.

    Tous les champs sauf `text` sont facultatifs : l'interface peut evoluer sans
    que la passerelle refuse une requete pour un champ qu'elle ne connait pas.
    """

    text: str
    locale: Optional[str] = None
    history: List[Dict[str, str]] = Field(default_factory=list)
    attachments: List[str] = Field(default_factory=list)
    connectors: Any = None
    run_id: Optional[str] = None
    persona: Optional[Dict[str, Any]] = None
    memories: Any = None


def trame(charge: Dict[str, Any]) -> str:
    """Une trame SSE : `data: <json>` puis une ligne vide."""
    return f"data: {json.dumps(charge, ensure_ascii=False)}\n\n"


def jeton(texte: str) -> str:
    return trame({"type": "token", "text": texte})


def fin(meta: Optional[Dict[str, Any]] = None) -> str:
    """La trame que son client attend pour savoir que c'est fini."""
    return trame({"type": "done", "meta": meta or {}})


def erreur(message: str) -> str:
    return trame({"type": "error", "message": message})


def _signaler_non_applique(demande: DemandeAgent) -> None:
    """Journalise ce que la requete portait et qu'ARENA n'utilise pas encore."""
    presents = [
        nom for nom in CHAMPS_NON_APPLIQUES
        if getattr(demande, nom, None) not in (None, [], {}, "")
    ]
    if presents:
        logger.info(
            "PWA : champs recus et non appliques -> %s. Ils ne sont pas perdus, "
            "ils ne sont pas encore honores.", ", ".join(presents),
        )


def instructions_persona(persona: Optional[Dict[str, Any]]) -> str:
    """Les preferences du proprietaire, prêtes a etre ajoutees au prompt systeme.

    Son interface les compose deja (`buildPersonaPrompt`) et les envoie dans
    `persona.instructions`. On ne les recompose pas ici : deux endroits qui
    fabriquent le meme texte finissent par le fabriquer differemment.

    Rend une chaine vide s'il n'y a rien a dire — un titre suivi du vide
    encombrerait chaque requete pour rien.
    """
    if not persona:
        return ""
    brut = str(persona.get("instructions") or "").strip()
    if not brut:
        return ""
    if len(brut) > PERSONA_MAX_CARACTERES:
        logger.warning(
            "Persona tronque : %s caracteres recus, %s conserves.",
            len(brut), PERSONA_MAX_CARACTERES,
        )
        brut = brut[:PERSONA_MAX_CARACTERES]
    return brut


def souvenirs_pertinents(question: str) -> str:
    """Ce que la memoire d'ARENA sait et qui se rapporte a la question.

    Une memoire illisible ne fait pas tomber la conversation : elle rend une
    chaine vide et le signale. Repondre sans souvenir vaut mieux que ne pas
    repondre.
    """
    try:
        resultats = recuperer(memoire_personnelle, question, budget_caracteres=BUDGET_MEMOIRE)
    except Exception as souci:  # noqa: BLE001 - la memoire ne bloque jamais la reponse
        logger.error("Memoire illisible, la reponse continue sans elle : %s", souci)
        return ""
    if not resultats:
        return ""
    return f"{TITRE_MEMOIRE_ARENA}\n{formater_souvenirs(resultats)}"


def notes_interface(memoires: Any) -> str:
    """Les notes que le proprietaire a tapees et activees dans son interface.

    Elles n'ont pas de source parce qu'il en est la source. C'est pour cela
    qu'elles sont annoncees separement des souvenirs d'ARENA : melanger les deux
    ferait passer une note tapee vite pour un fait verifie.
    """
    if not isinstance(memoires, list) or not memoires:
        return ""
    lignes = []
    for note in memoires[:NOTES_INTERFACE_MAX]:
        contenu = str((note or {}).get("content") or "").strip() if isinstance(note, dict) else ""
        if not contenu:
            continue
        categorie = str((note or {}).get("category") or "").strip()
        lignes.append(f"- {f'[{categorie}] ' if categorie else ''}{contenu}")
    if not lignes:
        return ""
    return f"{TITRE_NOTES_INTERFACE}\n" + "\n".join(lignes)


def prompt_systeme(
    persona: Optional[Dict[str, Any]] = None,
    question: str = "",
    memoires: Any = None,
) -> str:
    """Le prompt systeme d'ARENA, complete par les preferences du proprietaire.

    L'ordre n'est pas indifferent : les regles d'ARENA d'abord, les preferences
    ensuite, annoncees comme des preferences. Un reglage de ton ne doit pas
    pouvoir effacer ce que la plateforme s'interdit.
    """
    blocs = [get_arena_system_prompt()]

    preferences = instructions_persona(persona)
    if preferences:
        blocs.append(f"{TITRE_PERSONA}\n{preferences}")

    notes = notes_interface(memoires)
    if notes:
        blocs.append(notes)

    souvenirs = souvenirs_pertinents(question) if question else ""
    if souvenirs:
        blocs.append(souvenirs)

    return "\n\n".join(blocs)


def _prompt_conversation(demande: DemandeAgent, proprietaire: str) -> str:
    """Reconstruit le fil a partir de l'historique envoye par l'interface.

    L'historique vient du navigateur : c'est lui qui fait foi pour cette
    conversation-la. La memoire d'ARENA garde sa propre trace en parallele.
    """
    lignes = [
        f"{proprietaire if tour.get('role') == 'user' else 'Usman'}: {tour.get('content', '')}"
        for tour in demande.history
    ]
    lignes.append(f"{proprietaire}: {demande.text}")
    lignes.append("Usman:")
    return "\n".join(lignes)


@router.post("/agent/stream", dependencies=[Depends(verify_api_key), Depends(limiter_debit)])
async def flux_agent(demande: DemandeAgent):
    """Repond a l'interface PWA, en direct, dans son protocole.

    Le flux se termine **toujours** par `done` ou `error` : sans cela son client
    relance la requete jusqu'a trois fois, et une reponse devient trois.
    """
    _signaler_non_applique(demande)
    session = demande.run_id or "pwa"
    proprietaire = memory.get_fact("owner") or "Ousmane"

    async def flux():
        try:
            if not await fast_provider.is_available():
                yield erreur(
                    "Ollama est hors-ligne. Demarre-le (ollama serve) : ARENA ne "
                    "fabrique pas de reponse sans son modele."
                )
                return

            intention = await orchestrator.analyze_intent(demande.text)

            # Un agent specialise rend une reponse complete, pas un flux. On la
            # rend d'un bloc plutot que de la decouper en faux jetons.
            if intention in AGENTS_SPECIALISES:
                # Un agent specialise a ses propres consignes. Un ton « concis »
                # ne doit pas raccourcir un devis ni une recherche sourcee.
                if instructions_persona(demande.persona):
                    logger.info(
                        "Persona non applique : la demande part vers l'agent %s, "
                        "qui a ses propres consignes.", intention,
                    )
                resultat = await dispatch_request(
                    ChatRequest(prompt=demande.text, session_id=session), intent=intention
                )
                yield jeton(resultat["response"])
                yield fin({
                    "provider": "arena",
                    "model": fast_provider.model_name,
                    "sources": resultat.get("sources", []),
                    "query": intention,
                })
                return

            memory.add_chat_message(session_id=session, role="user", content=demande.text)
            complet = ""
            async for morceau in fast_provider.generate_stream(
                _prompt_conversation(demande, proprietaire),
                prompt_systeme(demande.persona, demande.text, demande.memories),
            ):
                complet += morceau
                yield jeton(morceau)

            memory.add_chat_message(
                session_id=session, role="assistant", content=complet.strip()
            )
            yield fin({
                "provider": "arena",
                "model": fast_provider.model_name,
                "query": intention,
            })

        except Exception as souci:  # noqa: BLE001 - le flux doit finir proprement
            logger.error("Flux PWA interrompu : %s", souci, exc_info=True)
            yield erreur(f"ARENA n'a pas pu terminer : {souci}")

    return StreamingResponse(flux(), media_type="text/event-stream")


@router.post("/files", dependencies=[Depends(verify_api_key)])
async def envoyer_fichiers():
    """Declare que les pieces jointes ne sont pas traitees ici.

    Son interface televerse les fichiers avant d'envoyer le message. ARENA n'a
    pas encore de chaine qui les lit. Accepter le fichier et rendre un
    identifiant donnerait une piece jointe que rien ne lira — c'est la forme la
    plus discrete du mensonge : ca marche, et ca ne fait rien.
    """
    raise HTTPException(
        status_code=501,
        detail=(
            "Les pieces jointes ne sont pas encore traitees par ARENA. Rien n'a "
            "ete enregistre. Envoie ton message sans fichier en attendant."
        ),
    )
