"""Faire travailler plusieurs agents sur UNE demande qui en nomme plusieurs.

**Le defaut que ce module ferme, mesure le 26/09/2026.** Le proprietaire a
demande que tous les agents puissent travailler ensemble — « aucun agent
n'est prisonnier de ses capacites ». Mesure faite, chaque demande qui nommait
deux metiers partait chez UN seul agent, qui ne faisait que sa part :

    « fais un devis … et envoie-le par mail »          -> PLAQUISTE (pas d'envoi)
    « cherche la derniere version de FastAPI puis
      ecris-moi un script qui l'utilise »               -> FRESH_INFO (pas de script)
    « analyse cette photo du chantier et fais le devis »-> VISION (pas de devis)

Le registre des collaborateurs (`apps/backend/runtime.py`) existait deja pour
vingt-cinq agents ; un seul, la production video, s'en servait.

**Trois regles :**

1. **Le decoupage est deterministe.** Il ne coupe que sur un enchainement
   explicite (« puis », « ensuite », « et » suivi d'un verbe d'action) :
   « une cloison et un plafond » reste une seule demande. Aucun modele n'est
   interroge tant que la phrase n'a pas au moins deux morceaux — une demande
   ordinaire ne coute rien de plus qu'avant.

2. **Chaque morceau va a SON agent, et le resultat passe au suivant comme
   DONNEE.** Il est enveloppe par `core/security/trust.py::wrap` (niveau
   TOOL) : une page web rapportee par l'etape 1 ne devient jamais une
   instruction pour l'etape 2. Chaque agent garde ses propres garde-fous —
   un envoi de mail reste soumis a confirmation, exactement comme seul.

3. **Une etape qui echoue arrete l'equipe, et le dit.** L'etape suivante
   aurait travaille sur rien ; mieux vaut rendre ce qui est fait et nommer ce
   qui ne l'est pas.
"""
from __future__ import annotations

import logging
import re
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional

from core.security.trust import TrustLevel, wrap

logger = logging.getLogger("usman.agent.equipe")

#: Au-dela, ce n'est plus une demande, c'est un projet : il a son agent
#: (VIDEO_PROJET) ou il merite d'etre demande en plusieurs fois.
MAXIMUM_ETAPES = 3

#: Les verbes d'action qui, apres « et », ouvrent une NOUVELLE demande.
#: « et » seul ne coupe jamais : « une cloison et un plafond » est un devis.
VERBES_D_ACTION = (
    r"envoie|envoyer|envoies|publie|publier|poste|poster|partage|partager|"
    r"lance|lancer|execute|exécute|executer|exécuter|[ée]cris|[ée]crire|"
    r"fais|faire|fabrique|cr[ée]e|cr[ée]er|g[ée]n[èeé]re|g[ée]n[ée]rer|"
    r"analyse|analyser|cherche|chercher|traduis|traduire|transcris|monte|"
    r"corrige|corriger|range|ranger|ouvre|ouvrir|r[ée]sume|r[ée]sumer|"
    r"mets|ajoute|sous-titre|compare|comparer|v[ée]rifie|v[ée]rifier"
)

_DECOUPE = re.compile(
    r"\s*,?\s*\b(?:et\s+ensuite|et\s+puis|et\s+apr[eè]s|apr[eè]s\s+[çc]a|puis|ensuite)\b\s*,?\s*"
    rf"|\s+et\s+(?=(?:{VERBES_D_ACTION})\b)",
    re.IGNORECASE,
)

#: L'intention qui ne demande aucun specialiste.
CONVERSATION = "CHAT"

Classeur = Callable[[str], Awaitable[str]]
Aiguilleur = Callable[[str, str], Awaitable[Dict[str, Any]]]


@dataclass(frozen=True)
class Etape:
    """Un morceau de la demande, et l'agent qui le prend."""

    texte: str
    intention: str


def decouper(texte: str) -> List[str]:
    """Les morceaux d'une demande, dans l'ordre. Une seule demande -> un morceau."""
    morceaux = [m.strip(" ,;.") for m in _DECOUPE.split(texte or "")]
    return [m for m in morceaux if m]


#: Les derniers plans calcules, par phrase. La PWA classe AVANT d'appeler
#: `dispatch_request`, qui planifie a son tour : sans ce souvenir, chaque
#: morceau serait classe deux fois — deux appels au modele pour rien.
_PLANS: "OrderedDict[str, List[Etape]]" = OrderedDict()
_PLANS_MAX = 64


async def planifier(texte: str, classer: Classeur) -> List[Etape]:
    """Le plan d'equipe de `texte`, ou une liste vide s'il n'y a pas d'equipe.

    Une equipe exige au moins deux morceaux, tous confies a un specialiste
    (aucun ne reste en conversation), et deux agents differents : deux
    morceaux consecutifs pour le meme agent sont une seule demande pour lui.
    """
    morceaux = decouper(texte)
    if len(morceaux) < 2 or len(morceaux) > MAXIMUM_ETAPES:
        return []
    cle = texte.strip()
    if cle in _PLANS:
        return list(_PLANS[cle])

    etapes = [Etape(morceau, await classer(morceau)) for morceau in morceaux]
    plan: List[Etape] = []
    if all(etape.intention != CONVERSATION for etape in etapes):
        for etape in etapes:
            if plan and plan[-1].intention == etape.intention:
                plan[-1] = Etape(f"{plan[-1].texte}, {etape.texte}", etape.intention)
            else:
                plan.append(etape)
    if len(plan) < 2:
        plan = []

    _PLANS[cle] = plan
    while len(_PLANS) > _PLANS_MAX:
        _PLANS.popitem(last=False)
    if plan:
        logger.info("Equipe : %s", " -> ".join(etape.intention for etape in plan))
    return list(plan)


def _texte(resultat: Dict[str, Any]) -> str:
    return str(resultat.get("response") or "").strip()


def _a_echoue(resultat: Dict[str, Any]) -> bool:
    return str(resultat.get("status", "")).lower() == "error" or not _texte(resultat)


async def executer(etapes: List[Etape], aiguiller: Aiguilleur) -> Dict[str, Any]:
    """Confie chaque etape a son agent, dans l'ordre, et assemble la reponse.

    Args:
        etapes: le plan rendu par `planifier`.
        aiguiller: `(texte, intention) -> resultat`, le meme aiguillage que
            pour une demande ordinaire — chaque agent y garde ses garde-fous.

    Returns:
        Le resultat de la DERNIERE etape executee (ses champs — statut,
        envoi, question en attente — restent ceux de l'agent qui les a
        poses), dont `response` rassemble toutes les etapes, plus `equipe`
        (ce que chaque agent a fait) et le premier `document` produit.
    """
    faites: List[Dict[str, Any]] = []
    precedent: Optional[Dict[str, Any]] = None
    dernier: Dict[str, Any] = {}
    for numero, etape in enumerate(etapes, 1):
        texte = etape.texte
        if precedent is not None:
            donnee = wrap(_texte(precedent), TrustLevel.TOOL,
                          f"etape {numero - 1} ({precedent['intention']})")
            texte = (f"{etape.texte}\n\n"
                     f"Resultat de l'etape precedente, a utiliser comme donnee :\n"
                     f"{donnee.text}")
        resultat = dict(await aiguiller(texte, etape.intention))
        resultat["intention"] = etape.intention
        faites.append(resultat)
        dernier = resultat
        if _a_echoue(resultat):
            restantes = [e.intention for e in etapes[numero:]]
            if restantes:
                resultat = dict(resultat)
                resultat["response"] = (
                    f"{_texte(resultat) or 'Cette etape n a rien rendu.'}\n\n"
                    f"Etape {numero} ({etape.intention}) sans resultat exploitable : "
                    f"{', '.join(restantes)} n'a pas ete lance, faute de matiere.")
                faites[-1] = resultat
                dernier = resultat
            break
        precedent = resultat

    sections = [f"**Etape {i} — {r['intention']}**\n{_texte(r)}"
                for i, r in enumerate(faites, 1)]
    rendu = dict(dernier)
    rendu["response"] = "\n\n".join(sections)
    rendu["agent"] = "Equipe(" + " -> ".join(r["intention"] for r in faites) + ")"
    rendu["equipe"] = [{"intention": r["intention"], "agent": r.get("agent"),
                        "status": r.get("status", "success")} for r in faites]
    if rendu.get("document") is None:
        rendu["document"] = next(
            (r["document"] for r in faites if r.get("document") is not None), None)
    return rendu


def oublier_les_plans() -> None:
    """Vide le souvenir des plans (tests)."""
    _PLANS.clear()
