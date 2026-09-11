"""Memoire de decision — la memoire d'ARENA deja existante, jamais une
seconde (mission §15/§16/§44).

`MemoryManager.set_fact`/`list_facts` (categorie `executive_decision`) est le
SEUL stockage utilise ici. Ce module n'ecrit que ce que la mission demande :
la decision, sa raison, les hypotheses et le niveau de confiance — jamais la
transcription complete de la deliberation (les `AnalyseSpecialiste` entieres
ne sont PAS stockees), et jamais une chaine de raisonnement cachee.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.executive.contrat import DecisionExecutive
from core.memory.memory_manager import MemoryManager

logger = logging.getLogger("usman.executive.memoire")

CATEGORIE = "executive_decision"

#: Un resume est tronque a cette longueur — la memoire garde de quoi se
#: rappeler une decision, jamais de quoi la rejouer mot pour mot.
LONGUEUR_RESUME_MAX = 400


def _resume(decision: DecisionExecutive) -> str:
    texte = decision.recommandation or decision.reponse or ""
    return texte[:LONGUEUR_RESUME_MAX]


def enregistrer_decision(memory: Optional[MemoryManager], decision: DecisionExecutive) -> Optional[str]:
    """Ecrit un enregistrement concis. Rend la cle ecrite, ou `None` si
    aucune memoire n'est branchee — une memoire absente ne doit jamais
    bloquer la reponse a l'utilisateur (§28, meme discipline)."""
    if memory is None:
        return None
    cle = f"executive_decision:{datetime.now(timezone.utc).isoformat(timespec='microseconds')}"
    valeur = {
        "question": decision.question,
        "summary": _resume(decision),
        "confidence": decision.confiance,
        "specialists_consulted": list(decision.roles_consultes),
        "disagreements": len(decision.desaccords),
        "assumptions": list(decision.hypotheses)[:5],
        "missing_information": list(decision.informations_manquantes)[:5],
    }
    try:
        memory.set_fact(CATEGORIE, cle, valeur)
    except Exception as erreur:  # noqa: BLE001 — un echec d'ecriture memoire ne bloque jamais la reponse
        logger.warning("Enregistrement de decision executive impossible : %s", erreur)
        return None
    return cle


def decisions_recentes(memory: Optional[MemoryManager], limite: int = 5) -> List[Dict[str, Any]]:
    """Les dernieres decisions enregistrees — jamais plus que `limite`, pour
    ne pas gonfler un prompt futur avec un historique sans fin (mission §15)."""
    if memory is None:
        return []
    try:
        return memory.list_facts(CATEGORIE, limit=limite)
    except Exception as erreur:  # noqa: BLE001
        logger.warning("Lecture des decisions executives recentes impossible : %s", erreur)
        return []


def bloc_decisions_recentes(memory: Optional[MemoryManager], limite: int = 5) -> str:
    """Le bloc a injecter dans un prompt de synthese, ou une chaine vide
    quand rien n'est disponible — jamais un historique invente."""
    recentes = decisions_recentes(memory, limite)
    if not recentes:
        return ""
    lignes = ["Decisions executives recentes (resume seul) :"]
    for enregistrement in recentes:
        valeur = enregistrement.get("value") or {}
        if isinstance(valeur, dict):
            lignes.append(f"- {valeur.get('question', '?')} -> {valeur.get('summary', '')}")
    return "\n".join(lignes)
