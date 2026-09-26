"""Faire travailler les agents ensemble : lead, table ronde, projet (DEC-0146).

Tout ce module choisit ses agents DANS LE REGISTRE, par competence
(`RegistreCapacites.rechercher`) : aucun nom d'agent n'y figure. Qu'il y ait
5 agents ou 100, et qu'un agent ait ete ajoute hier, la selection se fait
sur ce que chacun declare savoir faire.

**Le lead** d'une tache est l'agent le plus competent pour elle parmi ceux
qui savent consulter (un `BaseAgent` dote d'un modele). Il n'est pas le meme
pour toutes les taches.

**La table ronde** invite les agents pertinents pour le probleme, les fait
parler en paralelle, tour apres tour, chacun voyant ce que les autres ont dit ;
un participant peut ecrire `[[INVITER:<competence>|<pourquoi>]]` pour faire
entrer un agent qui manque. Le lead synthetise une solution commune.

**Un projet** est decoupe en sous-taches par le lead (JSON ferme, sinon
decoupage deterministe), chaque sous-tache est confiee a l'agent competent,
et l'execution passe par `core/execution/coordination.py` : dependances,
paralelisme par vagues, etats ecrits — l'ordonnanceur existant, pas un second.

Toutes les communications passent par `BaseAgent.transmettre` : memes
garde-fous (boucle, profondeur, budget, delai) et meme espace de travail
partage (`core/agent/espace_de_travail.py`).

**Une synthese ne s'invente rien** (DEC-0147) : sa consigne lui interdit de
citer un agent absent ou d'ajouter un chiffre que personne n'a donne, et
`core/agent/verification_synthese.py` relit ce qu'elle a ecrit et signale
sous elle ce qui manque de source — sans rien corriger.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.agent.base_agent import BaseAgent
from core.agent.equipe import decouper
from core.agent.espace_de_travail import ESPACES
from core.agent.message import MessageAgent, tache_racine
from core.agent.verification_synthese import agents_ayant_travaille, verifier_synthese
from core.execution.coordination import Coordination, Etape
from core.models.routeur import cause_lisible
from core.security.trust import TrustLevel, wrap

logger = logging.getLogger("usman.agent.collaboration")

#: Ce qu'un participant ecrit pour faire entrer un agent qui manque.
DEMANDE_D_INVITATION = re.compile(r"\[\[\s*INVITER\s*:\s*([^|\]]+?)\s*\|\s*(.+?)\s*\]\]",
                                  re.DOTALL | re.IGNORECASE)

#: Bornes d'une table ronde — assez pour debattre, pas assez pour exploser
#: le budget de la demande (`core/agent/message.py::TACHES_MAX_PAR_RACINE`).
PARTICIPANTS_MAX = 5
INVITES_MAX = 3
TOURS = 2

#: Un projet au-dela n'est plus decoupe en taches mais en projets.
SOUS_TACHES_MAX = 6


# --- Le lead ------------------------------------------------------------------

def _peut_mener(agent: Any) -> bool:
    return isinstance(agent, BaseAgent) and getattr(agent, "provider", None) is not None


def choisir_lead(registre: Any, tache: str, exclure: tuple = ()) -> BaseAgent:
    """L'agent le plus competent pour `tache` parmi ceux qui savent mener.

    Aucun lead n'est fixe : la competence decide. Si aucun agent n'a de mot
    en commun avec la tache, le premier agent capable de mener (dans l'ordre
    d'inscription) prend la main — jamais un agent nomme ici.
    """
    for fiche in registre.rechercher(tache, nombre=len(registre.espaces()), exclure=exclure):
        agent = registre.obtenir(fiche.id)
        if _peut_mener(agent):
            return agent
    for cle in registre.espaces():
        agent = registre.obtenir(cle)
        if cle not in exclure and _peut_mener(agent):
            return agent
    raise LookupError("Aucun agent de l'ecosysteme ne sait mener une collaboration.")


def _texte(resultat: Dict[str, Any]) -> str:
    return str((resultat or {}).get("response") or "").strip()


def _a_echoue(resultat: Dict[str, Any]) -> bool:
    return str((resultat or {}).get("status", "")).lower() == "error" or not _texte(resultat)


# --- La table ronde -------------------------------------------------------------

@dataclass
class TableRonde:
    """Ce qui s'est dit autour de la table, et ce qui en est sorti."""

    probleme: str
    lead: str
    participants: List[str]
    invites: List[Dict[str, str]] = field(default_factory=list)
    tours: List[List[Dict[str, str]]] = field(default_factory=list)
    synthese: str = ""
    project_id: str = ""
    verification: Dict[str, Any] = field(default_factory=dict)

    def transcription(self) -> str:
        lignes = []
        for numero, tour in enumerate(self.tours, 1):
            for intervention in tour:
                lignes.append(f"[Tour {numero}] {intervention['agent']} : {intervention['texte']}")
        return "\n".join(lignes)

    def en_dict(self) -> Dict[str, Any]:
        return {"probleme": self.probleme, "lead": self.lead,
                "participants": self.participants, "invites": self.invites,
                "tours": self.tours, "synthese": self.synthese,
                "project_id": self.project_id, "verification": self.verification}


def _consigne_de_table(probleme: str, tour: int, autour: List[str]) -> str:
    """La consigne d'un tour (DEC-0148).

    Mesure du 26/09/2026 : la consigne unique demandait au premier tour de
    « repondre a ce que les autres ont dit » alors que personne n'avait parle.
    Le plaquiste a obei en inventant les positions de finance, tendances et
    orchestrator. Le premier tour dit donc que personne n'a parle ; les
    suivants renvoient au seul debat reel.
    """
    if tour == 1:
        consigne = ("Tu parles au premier tour : personne n'a encore rien dit. N'attribue "
                    "aucune position, aucun chiffre ni aucune remarque a un autre agent.")
    else:
        consigne = ("Reponds uniquement aux interventions reelles du debat joint : "
                    "n'attribue a un agent que ce qu'il y a ecrit. Conteste ce qui te "
                    "parait faux, propose une alternative si tu en as une.")
    return (
        f"Table ronde, tour {tour}. Autour de la table : {', '.join(autour)}. "
        f"Probleme pose : {probleme}\n\n"
        f"Donne TON analyse selon ta specialite. {consigne} "
        "S'il manque autour de la table une competence dont le probleme a besoin, "
        "ajoute une ligne [[INVITER:<competence>|<pourquoi>]].")


async def tenir_table_ronde(registre: Any, probleme: str, lead: Optional[BaseAgent] = None,
                            participants_max: int = PARTICIPANTS_MAX,
                            tours: int = TOURS, project_id: str = "") -> TableRonde:
    """Reunit les agents pertinents pour `probleme`, les fait debattre, synthetise.

    Les participants sont choisis par competence ; leur nombre depend de ce
    que le probleme touche (au moins deux si deux agents ont un rapport avec
    lui). Un participant peut en faire inviter un autre en cours de route.
    """
    # Les voix d'abord : les plus competents pour le probleme. Le lead est
    # choisi ENSUITE parmi les autres — il coordonne et synthetise ; s'il
    # etait le plus competent et ecarte de la table, elle resterait vide.
    choisis = [f.id for f in registre.rechercher(probleme, nombre=max(2, participants_max))]
    lead = lead or choisir_lead(registre, probleme, exclure=tuple(choisis))
    cle_lead = lead._mon_identifiant()
    choisis = [cle for cle in choisis if cle != cle_lead]
    table = TableRonde(probleme=probleme, lead=cle_lead, participants=choisis)
    if not choisis:
        table.synthese = ("Aucun agent de l'ecosysteme n'a de competence liee a ce "
                          "probleme : aucune table ronde n'a ete tenue.")
        return table

    with tache_racine(probleme, project_id=project_id) as racine:
        table.project_id = racine.project_id
        espace = ESPACES.pour(racine.project_id)
        fil = espace.discussion(probleme)
        for numero in range(1, max(1, tours) + 1):
            deja_dit = table.transcription()
            contexte = (wrap(deja_dit, TrustLevel.TOOL, "table ronde").text
                        if deja_dit else "")
            # Ceux qui parlent A CE TOUR : un invite entre au tour suivant.
            parlants = list(table.participants)
            reponses = await lead.deleguer_en_parallele(
                [{"destinataire": cle,
                  "requete": _consigne_de_table(probleme, numero, [cle_lead, *parlants])}
                 for cle in parlants],
                contexte={"contexte": contexte, "project_id": racine.project_id})
            interventions = []
            for cle, resultat in zip(parlants, reponses, strict=True):
                texte = _texte(resultat) or "(aucune intervention)"
                interventions.append({"agent": cle, "texte": DEMANDE_D_INVITATION.sub("", texte).strip()})
                for competence, raison in DEMANDE_D_INVITATION.findall(texte):
                    _inviter(registre, table, cle_lead, competence, raison, par=cle)
            table.tours.append(interventions)
            fil["interventions"].extend({"tour": numero, **i} for i in interventions)
        fil["participants"] = list(table.participants)

        debat = f"Probleme : {probleme}\n\nDebat de la table ronde :\n{table.transcription()}"
        synthese = await _synthetiser(
            lead, debat,
            "Fusionne les analyses en UNE solution commune : ce qui fait consensus, "
            "ce qui reste en desaccord et pourquoi, la proposition retenue."
            + _REGLES_DE_SYNTHESE.format(presents=", ".join([cle_lead, *table.participants])))
        table.synthese, table.verification = _verifier(
            synthese, [debat], registre, espace, racine.root_task_id,
            {cle_lead, *table.participants})
        espace.decider(cle_lead, table.synthese)
        ESPACES.sauver(racine.project_id)
    return table


def _inviter(registre: Any, table: TableRonde, cle_lead: str, competence: str,
             raison: str, par: str) -> None:
    """Fait entrer l'agent le plus competent pour `competence`, s'il manque."""
    if len(table.invites) >= INVITES_MAX:
        return
    deja = set(table.participants) | {cle_lead}
    candidats = registre.rechercher(competence, nombre=1, exclure=tuple(deja))
    if not candidats:
        logger.info("Table ronde : aucun agent pour « %s » (demande de %s).", competence, par)
        return
    table.participants.append(candidats[0].id)
    table.invites.append({"agent": candidats[0].id, "competence": competence.strip(),
                          "raison": raison.strip(), "par": par})


#: Ce que toute synthese d'equipe s'interdit (DEC-0147). Mesure : sans ces
#: regles, une synthese reelle attribuait une position a un agent absent et
#: posait un exemple chiffre calcule de tete, faux.
_REGLES_DE_SYNTHESE = (
    "\n\nRegles strictes : ne cite que ces agents : {presents}. N'ajoute aucun "
    "chiffre, prix, taux, quantite ou calcul que les intervenants n'ont pas donne ; "
    "s'il manque un chiffre pour conclure, dis qu'il manque au lieu de l'estimer.")


def _verifier(synthese: str, sources: List[str], registre: Any, espace: Any,
              root_task_id: str, presents: set) -> tuple:
    """(synthese suivie de ses signalements, verification en dict)."""
    verification = verifier_synthese(
        synthese, sources, registre,
        presents | agents_ayant_travaille(espace, root_task_id))
    avertissement = verification.avertissement()
    if avertissement:
        logger.warning("Synthese signalee : %s", verification.en_dict())
    return (f"{synthese}\n\n{avertissement}" if avertissement else synthese,
            verification.en_dict())


async def _synthetiser(lead: BaseAgent, matiere: str, consigne: str) -> str:
    """La synthese du lead. Sans modele joignable : la matiere elle-meme,
    annoncee comme telle — jamais une synthese inventee."""
    try:
        return (await lead.rediger(prompt=f"{matiere}\n\n{consigne}")).strip()
    except Exception as erreur:  # noqa: BLE001 — le travail des autres reste rendu
        logger.warning("Synthese impossible par %s : %s", lead.name, erreur)
        return f"(Synthese indisponible : {cause_lisible(erreur)})\n{matiere}"


# --- Le projet ---------------------------------------------------------------

@dataclass
class SousTache:
    objectif: str
    competence: str
    depend_de: List[int] = field(default_factory=list)
    agent: str = ""
    etat: str = "a_faire"
    resultat: str = ""


_CONSIGNE_DECOUPAGE = (
    "Decoupe ce projet en sous-taches confiables a des specialistes differents. "
    "Reponds UNIQUEMENT par un tableau JSON, au plus {maximum} elements, de la forme "
    '[{{"objectif": "...", "competence": "...", "depend_de": [0]}}] ou "competence" '
    "nomme le savoir-faire necessaire et \"depend_de\" les indices (a partir de 0) des "
    "sous-taches dont celle-ci a besoin.\n\nProjet : {projet}")


def _lire_decoupage(brut: str) -> List[SousTache]:
    """Le JSON du lead, valide ; une liste vide s'il est inexploitable."""
    debut, fin = brut.find("["), brut.rfind("]")
    if debut < 0 or fin <= debut:
        return []
    try:
        donnees = json.loads(brut[debut:fin + 1])
    except ValueError:
        return []
    taches = []
    for element in donnees[:SOUS_TACHES_MAX] if isinstance(donnees, list) else []:
        if not isinstance(element, dict) or not str(element.get("objectif") or "").strip():
            continue
        dependances = [d for d in element.get("depend_de") or []
                       if isinstance(d, int) and 0 <= d < len(taches)]
        taches.append(SousTache(objectif=str(element["objectif"]).strip(),
                                competence=str(element.get("competence") or element["objectif"]),
                                depend_de=dependances))
    return taches


async def decomposer(lead: BaseAgent, projet: str) -> List[SousTache]:
    """Les sous-taches du projet : celles du lead si son JSON est valide,
    sinon le decoupage deterministe de la phrase (chaque etape attend la
    precedente, puisque « puis » dit un ordre)."""
    try:
        brut = await lead.provider.generate(
            prompt=_CONSIGNE_DECOUPAGE.format(maximum=SOUS_TACHES_MAX, projet=projet))
        taches = _lire_decoupage(str(brut or ""))
    except Exception as erreur:  # noqa: BLE001 — le repli existe pour ca
        logger.warning("Decoupage par %s impossible : %s", lead.name, erreur)
        taches = []
    if len(taches) >= 2:
        return taches
    morceaux = decouper(projet)[:SOUS_TACHES_MAX]
    return [SousTache(objectif=m, competence=m, depend_de=[i - 1] if i else [])
            for i, m in enumerate(morceaux)]


async def conduire_projet(registre: Any, projet: str, lead: Optional[BaseAgent] = None,
                          project_id: str = "", parallelisme: int = 4) -> Dict[str, Any]:
    """Decoupe, attribue, execute (en parallele quand les dependances le
    permettent) et synthetise un projet — avec les agents reellement presents."""
    lead = lead or choisir_lead(registre, projet)
    cle_lead = lead._mon_identifiant()
    sous_taches = await decomposer(lead, projet)
    for tache in sous_taches:
        candidats = registre.rechercher(tache.competence or tache.objectif, nombre=1,
                                        exclure=(cle_lead,))
        if not candidats:
            candidats = registre.rechercher(tache.objectif, nombre=1, exclure=(cle_lead,))
        tache.agent = candidats[0].id if candidats else ""

    with tache_racine(projet, project_id=project_id) as racine:
        espace = ESPACES.pour(racine.project_id)
        espace.verser(cle_lead, f"Projet : {projet}", nature="objectif")

        def etape(indice: int, tache: SousTache) -> Etape:
            async def appel(acquis: Dict[str, Any]) -> Dict[str, Any]:
                if not tache.agent:
                    raise RuntimeError(f"aucun agent competent pour « {tache.competence} »")
                apports = "\n".join(
                    f"- {sous_taches[d].objectif} : {_texte(acquis.get(f't{d}') or {})}"
                    for d in tache.depend_de)
                resultat = await lead.transmettre(MessageAgent(
                    sender="", recipient=tache.agent, objective=tache.objectif,
                    context=wrap(apports, TrustLevel.TOOL, "sous-taches precedentes").text
                    if apports else "",
                    requirements=f"Fait partie du projet : {projet}",
                    expected_output="Le resultat de cette sous-tache, directement utilisable.",
                    project_id=racine.project_id))
                if _a_echoue(resultat):
                    raise RuntimeError(_texte(resultat) or "resultat vide")
                return resultat
            return Etape(nom=f"t{indice}", appel=appel, facultative=True,
                         depend_de=tuple(f"t{d}" for d in tache.depend_de))

        execution = await Coordination(projet, [etape(i, t) for i, t in enumerate(sous_taches)]
                                       ).executer_parallele(parallelisme=parallelisme)
        for indice, tache in enumerate(sous_taches):
            trace = execution.trace_de(f"t{indice}")
            tache.etat = trace.etat.value if trace else "NOT_REACHED"
            tache.resultat = _texte(trace.resultat) if trace and isinstance(trace.resultat, dict) \
                else (trace.raison if trace else "")

        faites = "\n\n".join(f"{i + 1}. {t.objectif} ({t.agent or 'aucun agent'}, {t.etat}) :\n{t.resultat}"
                             for i, t in enumerate(sous_taches))
        matiere = f"Projet : {projet}\n\nSous-taches :\n{faites}"
        presents = {cle_lead, *(t.agent for t in sous_taches if t.agent)}
        synthese = await _synthetiser(
            lead, matiere,
            "Assemble ces resultats en un livrable unique. Dis clairement ce qui "
            "n'a pas pu etre fait."
            + _REGLES_DE_SYNTHESE.format(presents=", ".join(sorted(presents))))
        synthese, verification = _verifier(
            synthese, [matiere], registre, espace, racine.root_task_id, presents)
        espace.decider(cle_lead, synthese)
        ESPACES.sauver(racine.project_id)

    return {
        "projet": projet, "lead": cle_lead, "project_id": racine.project_id,
        "sous_taches": [t.__dict__ for t in sous_taches],
        "trace": execution.to_dict(), "synthese": synthese, "verification": verification,
        "agents": sorted({t.agent for t in sous_taches if t.agent}),
    }
