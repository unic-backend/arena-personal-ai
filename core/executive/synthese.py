"""Detecter le desaccord, puis synthetiser — jamais moyenner (mission §8/§9/
§10/§30/§31).

**Le desaccord est detecte STRUCTURELLEMENT**, avant tout appel modele : deux
roles dont la `Position` s'oppose (un FAVORABLE, un DEFAVORABLE) sur la meme
question forment un desaccord reel, jamais suppose. La synthese (un seul
appel modele) recoit cette liste deja calculee — elle doit en rendre compte,
jamais l'aplatir en une moyenne.

**Verification deterministe (§31).** Avant de rendre la synthese, ce module
relit le texte produit et verifie qu'aucun chiffre de marge/risque qu'il cite
ne CONTREDIT ce que les roles ont reellement calcule. Ce n'est pas une
verification exhaustive — c'est un filet, pas une preuve — mais elle est
reelle : elle relit le texte, elle ne le suppose pas correct.
"""
from __future__ import annotations

import logging
import re
from typing import List, Optional

from core.executive.contrat import AnalyseSpecialiste, DecisionExecutive, Desaccord, Position
from core.models.base import ModelProvider

logger = logging.getLogger("usman.executive.synthese")

#: Positions qui s'opposent directement — un FAVORABLE et un CONDITIONNEL ne
#: sont pas un desaccord (le second n'exclut pas le premier), mais un
#: FAVORABLE et un DEFAVORABLE le sont toujours.
_OPPOSEES = {
    frozenset({Position.FAVORABLE, Position.DEFAVORABLE}),
}


def detecter_desaccords(analyses: List[AnalyseSpecialiste]) -> List[Desaccord]:
    """Compare chaque paire de roles DISPONIBLES (jamais un role en echec,
    qui n'a rien conclu) — O(n^2) sur au plus quatre roles, negligeable."""
    disponibles = [a for a in analyses if a.disponible]
    desaccords: List[Desaccord] = []
    for i, a in enumerate(disponibles):
        for b in disponibles[i + 1:]:
            paire = frozenset({a.position, b.position})
            if paire in _OPPOSEES:
                desaccords.append(Desaccord(
                    role_a=a.role, position_a=a.position, role_b=b.role, position_b=b.position,
                    remarque=f"{a.domaine} et {b.domaine} concluent a l'oppose l'un de l'autre.",
                ))
    return desaccords


def _confiance_globale(analyses: List[AnalyseSpecialiste]) -> str:
    """La confiance globale ne peut pas depasser la plus faible des
    confiances individuelles disponibles — un seul role incertain rend
    toute la decision incertaine, jamais noyee dans une moyenne."""
    disponibles = [a for a in analyses if a.disponible]
    if not disponibles:
        return "FAIBLE"
    ordre = {"FAIBLE": 0, "MOYENNE": 1, "ELEVEE": 2}
    pire = min(disponibles, key=lambda a: ordre.get(a.confiance, 0))
    return pire.confiance


#: Motif d'un pourcentage dans un texte libre — sert a la verification §31.
_MOTIF_POURCENT = re.compile(r"(-?\d+(?:[.,]\d+)?)\s*%")


def verifier_coherence_chiffree(texte_synthese: str, analyses: List[AnalyseSpecialiste]) -> Optional[str]:
    """Rend un avertissement si un pourcentage cite dans la synthese ne
    correspond a AUCUN pourcentage reellement calcule par un role — jamais
    une preuve d'exactitude totale, un filet contre le chiffre invente.

    Une synthese qui ne cite aucun pourcentage n'est pas suspecte : elle n'a
    simplement rien a verifier de ce type."""
    cites = {round(float(m.group(1).replace(",", ".")), 1) for m in _MOTIF_POURCENT.finditer(texte_synthese)}
    if not cites:
        return None
    calcules = set()
    for analyse in analyses:
        for preuve in analyse.preuves:
            for m in _MOTIF_POURCENT.finditer(preuve):
                calcules.add(round(float(m.group(1).replace(",", ".")), 1))
    inconnus = cites - calcules
    if not inconnus:
        return None
    return (
        f"Verification : {len(inconnus)} pourcentage(s) cite(s) dans la synthese "
        f"({sorted(inconnus)}) ne correspondent a aucun calcul rendu par un role — "
        "a relire avant de s'y fier."
    )


def _bloc_analyses(analyses: List[AnalyseSpecialiste]) -> str:
    morceaux = []
    for a in analyses:
        if not a.disponible:
            morceaux.append(f"## {a.domaine} : INDISPONIBLE ({a.erreur})")
            continue
        morceaux.append(f"## {a.domaine} — position : {a.position.value}, confiance : {a.confiance}")
        for c in a.constats:
            morceaux.append(f"- [{c.nature.value}] {c.texte}")
        if a.hypotheses:
            morceaux.append("Hypotheses : " + "; ".join(a.hypotheses))
        if a.risques:
            morceaux.append("Risques : " + "; ".join(a.risques))
        if a.inconnues:
            morceaux.append("Inconnues : " + "; ".join(a.inconnues))
        if a.actions_recommandees:
            morceaux.append("Actions recommandees : " + "; ".join(a.actions_recommandees))
    return "\n".join(morceaux)


PROMPT_SYNTHESE = """Tu es l'Executive Intelligence d'ARENA. Une question d'affaires a ete \
soumise a plusieurs roles specialises, DEJA executes — leurs conclusions suivent. Tu ne \
recalcules RIEN : tu SYNTHETISES.

Question : {question}

Analyses des roles :
{analyses}

Desaccords structurels detectes (ne les efface jamais, explique-les) :
{desaccords}

Ecris une recommandation executive en francais, de la longueur adaptee a la complexite \
reelle de la question (une question simple merite une reponse courte). Regles strictes :
- N'invente AUCUN chiffre absent des analyses ci-dessus.
- Distingue explicitement un FAIT/CALCUL d'une INFERENCE ou d'une HYPOTHESE.
- Si les roles sont en desaccord, PRESERVE le desaccord — ne le moyenne jamais.
- Nomme ce qui est INCONNU plutot que de le deviner.
- Termine par les prochaines actions concretes, si la question l'appelle."""


async def synthetiser(
    question: str, analyses: List[AnalyseSpecialiste], provider: Optional[ModelProvider],
) -> DecisionExecutive:
    """Le point d'entree unique de ce module : detecte les desaccords, appelle
    le modele UNE fois pour la synthese, verifie, et rend la decision
    structuree (§10) — jamais le gabarit complet pour une question simple."""
    desaccords = detecter_desaccords(analyses)
    roles_consultes = [a.role for a in analyses]

    if not analyses:
        return DecisionExecutive(
            question=question, simple=True,
            reponse="Aucun role specialise n'a ete convoque pour cette question — "
                    "elle ne semble pas appeler une decision d'affaires structuree.",
            confiance="FAIBLE",
        )

    texte_desaccords = "\n".join(d.remarque for d in desaccords) or "(aucun)"
    prompt = PROMPT_SYNTHESE.format(
        question=question, analyses=_bloc_analyses(analyses), desaccords=texte_desaccords,
    )

    reponse_modele: Optional[str] = None
    if provider is not None:
        try:
            reponse_modele = (await provider.generate(prompt=prompt)).strip()
        except Exception as erreur:  # noqa: BLE001 — §28 : la synthese degrade, elle ne casse pas
            logger.warning("Synthese executive indisponible : %s", erreur)

    if not reponse_modele:
        # Repli sans modele : les constats bruts, jamais une phrase inventee
        # (meme discipline que FinanceAgent._resume_sans_interpretation).
        reponse_modele = "Synthese automatique indisponible — resume brut des roles :\n" + _bloc_analyses(analyses)

    verification = verifier_coherence_chiffree(reponse_modele, analyses)

    preuves_cles = [p for a in analyses if a.disponible for p in a.preuves][:8]
    risques = [r for a in analyses if a.disponible for r in a.risques]
    hypotheses = [h for a in analyses if a.disponible for h in a.hypotheses]
    inconnues = [i for a in analyses if a.disponible for i in a.inconnues]
    actions = [act for a in analyses if a.disponible for act in a.actions_recommandees]

    return DecisionExecutive(
        question=question, simple=False, reponse=reponse_modele,
        recommandation=reponse_modele,
        preuves_cles=preuves_cles, risques=risques, alternatives=[],
        hypotheses=hypotheses, informations_manquantes=inconnues,
        confiance=_confiance_globale(analyses), prochaines_actions=actions,
        roles_consultes=roles_consultes, desaccords=desaccords, analyses=analyses,
        verification=verification,
    )
