"""Raisonner en plusieurs etapes, avec critique et revision optionnelles.

Le moteur enchainait plan, calcul, synthese. Il tourne sur
`core/execution/coordination.py`, qui garde l'etat : quelle etape, combien
de tentatives, ce qui a ete abandonne et pourquoi.

**Ce que ca change, concretement :**

1. **Le calcul est facultatif.** Un bac a sable absent n'emporte plus la
   reponse : l'etape est marquee `ABANDONNEE`, sa raison est gardee, et la
   synthese se fait avec ce qu'on a — en le disant.

2. **La synthese est verifiee.** Une reponse vide n'est pas une reponse :
   le controle est declare, et l'etape est retentee avant d'etre declaree
   ratee.

3. **Rien n'est retente sans fin.** Deux tentatives pour ce qui depend d'un
   service, **une seule** pour le calcul : rejouer un code deterministe
   rend la meme erreur, et fait perdre le temps de deux executions.

4. **L'etat sort avec la reponse.** `coordination` porte les etapes reelles,
   pour que l'interface montre ce qui s'est passe au lieu de le deviner.

5. **En mode `approfondie`, la reponse est critiquee.** Une etape
   independante verifie que la synthese repond vraiment a la question et
   rend un verdict (`OK`/`KO`), une raison, et un score de confiance. Si le
   verdict est `KO`, une etape de revision re-genere la synthese avec le
   feedback. Les deux etapes sont facultatives : ni un critique muet, ni
   une revision vide ne peuvent emporter une reponse deja produite.

**Ce que ca ne fait pas.** Le mode `standard` reste le comportement
historique : pas de critique, pas de revision, deux appels au modele dans
le cas simple. Le mode `approfondie` en fait deux de plus. C'est un choix
explicite de l'appelant, jamais un defaut silencieux.
"""
import logging
import re
from typing import Any, Dict, Optional, Tuple

from core.execution.coordination import Coordination, Etape, EtatEtape
from core.models.base import ModelProvider
from tools.code.sandbox_interpreter import SandboxInterpreterTool

logger = logging.getLogger("usman.core.reasoning")

#: Un service peut tomber une fois. Deux tentatives, pas plus.
ESSAIS_MODELE = 2

#: Le calcul, lui, n'est PAS retente : le meme code rend la meme erreur, et on
#: aurait paye deux executions pour la meme reponse.
ESSAIS_CALCUL = 1

#: La critique et la revision sont des appels de modele : deux tentatives
#: suffisent a absorber une panne breve. Au-dela, on garde la synthese
#: originale plutot que de faire attendre la reponse.
ESSAIS_CRITIQUE = 2
ESSAIS_REVISION = 2

BLOC_PYTHON = re.compile(r"```python\n?(.*?)```", re.DOTALL)

#: Le verdict de la critique : trois lignes, format strict, parsable.
VERDICT_RE = re.compile(r"VERDICT\s*:\s*(OK|KO)", re.IGNORECASE)
RAISON_RE = re.compile(r"RAISON\s*:\s*(.*?)(?:\n|$)", re.IGNORECASE)
CONFIANCE_RE = re.compile(r"CONFIANCE\s*:\s*([0-9]*\.?[0-9]+)", re.IGNORECASE)

PROFONDEURS = ("standard", "approfondie")


def _non_vide(sortie: Any) -> Tuple[bool, str]:
    """Une reponse vide n'est pas une reponse."""
    return (bool(str(sortie or "").strip()), "le modele n'a rien rendu")


def _calcul_reussi(sortie: Any) -> Tuple[bool, str]:
    """Le bac a sable dit lui-meme s'il a execute. On ne le suppose pas."""
    if not isinstance(sortie, dict):
        return False, "le bac a sable n'a rien rendu d'exploitable"
    if sortie.get("success"):
        return True, ""
    return False, str(sortie.get("stderr") or "execution refusee")[:200]


def _critique_exploitable(sortie: Any) -> Tuple[bool, str]:
    """La critique doit rendre un verdict. Un texte informe n'en est pas un."""
    if not isinstance(sortie, dict):
        return False, "la critique n'a rien rendu d'exploitable"
    if sortie.get("ok") is None:
        return False, "la critique n'a pas rendu de verdict lisible"
    return True, ""


def _analyser_critique(texte: str) -> Dict[str, Any]:
    """Extrait verdict, raison, confiance d'une reponse de critique.

    Robustesse d'abord : si le modele ne respecte pas le format, on declare
    `ok = None` plutot que d'inventer un verdict. `_critique_exploitable`
    rejettera alors l'etape et la synthese originale sera conservee.
    """
    if not texte:
        return {"ok": None, "raison": "critique vide", "confiance": None}

    verdict = VERDICT_RE.search(texte)
    if verdict is None:
        return {"ok": None, "raison": texte.strip()[:200], "confiance": None}

    ok = verdict.group(1).upper() == "OK"

    raison_match = RAISON_RE.search(texte)
    raison = raison_match.group(1).strip()[:200] if raison_match else ""

    confiance: Optional[float] = None
    confiance_match = CONFIANCE_RE.search(texte)
    if confiance_match is not None:
        try:
            valeur = float(confiance_match.group(1))
            confiance = max(0.0, min(1.0, valeur))
        except ValueError:
            confiance = None

    return {"ok": ok, "raison": raison, "confiance": confiance}


class ReasoningEngine:
    """Raisonnement profond : plan, calcul, synthese.

    En mode `approfondie`, ajoute une critique independante et, si la
    critique le demande, une revision de la synthese. Les deux etapes sont
    facultatives : une critique muette ou une revision vide ne peut jamais
    emporter une reponse deja produite.
    """

    def __init__(self, provider: ModelProvider) -> None:
        self.provider = provider
        self.interpreter = SandboxInterpreterTool()

    async def solve_complex_task(
        self,
        user_prompt: str,
        profondeur: str = "standard",
    ) -> Dict[str, Any]:
        """Conduit les etapes et rend l'etat complet de la tache.

        `profondeur` :
        - "standard" : plan, calcul (facultatif), synthese.
        - "approfondie" : + critique (facultative) + revision (facultative,
          declenchee seulement si la critique dit KO).
        """
        if profondeur not in PROFONDEURS:
            raise ValueError(
                f"profondeur inconnue : {profondeur!r}. "
                f"Attendu : {', '.join(PROFONDEURS)}."
            )

        logger.info(
            "Raisonnement profond (%s) sur : %s", profondeur, user_prompt[:60]
        )

        plan_prompt = (
            "Tu es un moteur de raisonnement logique de haut niveau.\n"
            "Analyse la question suivante et décompose la résolution en 3 étapes claires.\n"
            "Si la question implique des maths, des statistiques ou des données, écris un script Python "
            "avec sympy/numpy/math pour calculer la réponse exacte.\n\n"
            f"Question: {user_prompt}\n\n"
            "Plan et Script Python (si nécessaire) dans des balises ```python ... ```:"
        )

        async def planifier() -> str:
            return await self.provider.generate(prompt=plan_prompt)

        def calculer(acquis: Dict[str, Any]) -> Dict[str, Any]:
            """N'est lancee que si le plan porte du code. Sinon, rien a executer."""
            trouve = BLOC_PYTHON.search(acquis.get("plan") or "")
            if not trouve:
                # Pas de code : ce n'est pas un echec, il n'y a rien a faire.
                return {"success": True, "stdout": "", "sans_code": True}
            logger.info("Execution du code de verification dans le bac a sable.")
            return self.interpreter.execute_python_code(trouve.group(1).strip())

        async def synthetiser(acquis: Dict[str, Any]) -> str:
            calcul = acquis.get("calcul") or {}
            sortie = calcul.get("stdout", "") if calcul.get("success") else ""
            return await self.provider.generate(prompt=(
                "Tu es Usman. Présente la solution finale de manière élégante, "
                "claire et irréprochable.\n"
                f"Question originale : {user_prompt}\n"
                f"Raisonnement & Plan : {acquis.get('plan', '')}\n"
                f"Résultat des calculs exacts dans le Bac à Sable : {sortie}\n\n"
                "Solution Finale Sublime :"))

        async def critiquer(acquis: Dict[str, Any]) -> Dict[str, Any]:
            """Verdict independant sur la synthese : format strict, parsable.

            La critique recoit l'etat REEL du calcul, et son verdict est
            ensuite RELU par du code deterministe : si le calcul a echoue
            mais que la critique a rendu OK, le verdict est force a KO.
            Le modele propose, le Python dispose ? la regle absolue
            ? un calcul echoue ne peut pas produire un verdict OK ? n'est
            pas une consigne dans un prompt, c'est une invariante du code.
            """
            synthese = acquis.get("synthese", "")
            plan = acquis.get("plan", "")
            calcul = acquis.get("calcul") or {}

            if calcul.get("sans_code"):
                etat_calcul = (
                    "Aucun code n'a ete propose par le plan : il n'y avait "
                    "rien a executer, et ce n'est pas un echec."
                )
            elif calcul.get("success"):
                sortie = (calcul.get("stdout") or "").strip()
                etat_calcul = (
                    "Le code a ete execute avec succes dans le bac a sable. "
                    f"Sortie :\n{sortie[:1000]}"
                )
            else:
                raison = calcul.get("stderr") or "raison non precisee"
                etat_calcul = (
                    "ATTENTION : l'execution du code a ECHOUE ou a ete "
                    f"refusee. Raison : {raison[:300]}\n"
                    "Aucun resultat de calcul n'est disponible. Si la solution "
                    "proposee affirme des valeurs calculees ou verifiees par "
                    "execution, ce sont des valeurs NON verifiees, et le "
                    "VERDICT doit etre KO."
                )

            verdict_brut = await self.provider.generate(prompt=(
                "Tu es un critique rigoureux, sec, sans complaisance.\n"
                "Verifie si la solution proposee repond vraiment a la question, "
                "sans erreur, sans approximation, sans esquive.\n\n"
                f"Question : {user_prompt}\n\n"
                f"Plan propose :\n{plan[:1500]}\n\n"
                f"Etat reel du calcul :\n{etat_calcul}\n\n"
                f"Solution proposee :\n{synthese}\n\n"
                "Regle absolue : si le calcul a ete refuse ou a echoue, et que "
                "la solution pretend avoir verifie des valeurs par calcul, "
                "alors le VERDICT est KO.\n\n"
                "Reponds STRICTEMENT dans ce format, sur exactement trois lignes :\n"
                "VERDICT: OK ou KO\n"
                "RAISON: une phrase courte\n"
                "CONFIANCE: un nombre entre 0 et 1\n"
            ))
            analyse = _analyser_critique(verdict_brut)

            # --- Controle deterministe : le modele propose, le Python dispose.
            # Un LLM suit une regle absolue la plupart du temps, pas toujours.
            # Mesure du 13/09/2026 : deux runs identiques, une critique OK
            # puis une critique KO, sur le meme etat de calcul echoue. La
            # seule facon fiable de tenir l'invariante est de la verifier
            # en code, pas de la demander en prose.
            calcul_a_echoue = (
                not calcul.get("sans_code")
                and not calcul.get("success")
            )
            if calcul_a_echoue and analyse.get("ok") is True:
                analyse["ok"] = False
                # Message court et clair, pas de jargon interne : il sera
                # lu par un humain dans l'interface, ou consigne dans un
                # log. ? correction deterministe ? et ? Raison initiale ?
                # ne veulent rien dire pour le lecteur ? la seule chose qui
                # compte est que le calcul n'a pas tourne.
                analyse["raison"] = (
                    "le calcul a echoue, la reponse n'a pas ete verifiee"
                )
                analyse["force_ko"] = True

            analyse["verdict_brut"] = verdict_brut[:500]
            return analyse

        async def reviser(acquis: Dict[str, Any]) -> str:
            """Re-synthese uniquement si la critique a dit KO. Sinon, identite.

            La revision recoit l'etat REEL du calcul, comme la critique. Sans
            cela, elle peut reformuler la reponse sans corriger le fond, et
            continuer d'affirmer que des valeurs ont ete verifiees par
            execution ? c'est exactement ce qui a ete observe le 13/09/2026 :
            la revision avait garde la phrase ? les substitutions effectuees
            dans le code montrent que... ? alors qu'aucun code n'avait tourne.
            """
            synthese = acquis.get("synthese", "")
            critique = acquis.get("critique") or {}
            if critique.get("ok") is not False:
                # OK, ou pas de verdict exploitable : on conserve la synthese.
                return synthese

            calcul = acquis.get("calcul") or {}

            # Le calcul a-t-il eu lieu ? La reponse doit s'y conformer.
            if calcul.get("sans_code"):
                contrainte_calcul = (
                    "Aucun code n'a ete propose : il n'y a rien a executer. "
                    "Tu peux presenter un raisonnement, mais ne pretend pas "
                    "avoir calcule ou verifie par execution."
                )
            elif calcul.get("success"):
                sortie = (calcul.get("stdout") or "").strip()
                contrainte_calcul = (
                    "Le code a ete execute avec succes. Sortie :\n"
                    f"{sortie[:1000]}"
                )
            else:
                raison = calcul.get("stderr") or "raison non precisee"
                contrainte_calcul = (
                    "ATTENTION : le code a ECHOUE ou a ete refuse. Raison : "
                    f"{raison[:300]}\n"
                    "Tu NE DOIS PAS affirmer que des valeurs ont ete calculees "
                    "ou verifiees par execution. Presente ce que tu peux "
                    "demontrer par le raisonnement seul, et dis clairement, "
                    "dans la reponse elle-meme, que la verification par "
                    "execution n'a pas pu etre faite."
                )

            logger.info(
                "Revision demandee par la critique : %s",
                critique.get("raison", ""),
            )
            return await self.provider.generate(prompt=(
                "Tu es Usman. La solution precedente a ete jugee insuffisante "
                "par un relecteur independant.\n"
                f"Question originale : {user_prompt}\n\n"
                f"Solution precedente :\n{synthese}\n\n"
                f"Motif de la critique : {critique.get('raison', '')}\n\n"
                f"CONTRAINTE IMPERATIVE sur ce que tu peux affirmer :\n"
                f"{contrainte_calcul}\n\n"
                "Produis une solution corrigee qui respecte cette contrainte. "
                "Ne mentionne ni la critique, ni le processus de revision : "
                "rends directement la nouvelle solution, en etant honnete sur "
                "ce qui a ete verifie et ce qui ne l'a pas ete :"))

        etapes = [
            Etape("plan", planifier, essais_max=ESSAIS_MODELE, verifier=_non_vide),
            # Facultative : un bac a sable absent ne doit pas emporter la reponse.
            Etape("calcul", calculer, essais_max=ESSAIS_CALCUL, facultative=True,
                  verifier=_calcul_reussi, depend_de=("plan",)),
            Etape("synthese", synthetiser, essais_max=ESSAIS_MODELE,
                  verifier=_non_vide, depend_de=("plan",)),
        ]

        if profondeur == "approfondie":
            etapes.append(Etape(
                "critique", critiquer,
                essais_max=ESSAIS_CRITIQUE,
                facultative=True,
                verifier=_critique_exploitable,
                depend_de=("synthese",),
            ))
            etapes.append(Etape(
                "revision", reviser,
                essais_max=ESSAIS_REVISION,
                facultative=True,
                verifier=_non_vide,
                depend_de=("synthese", "critique"),
            ))

        coordination = Coordination(f"raisonnement : {user_prompt[:40]}", etapes)
        etat = await coordination.executer()

        # --- Calcul : format historique conserve (le routeur de chat lit
        # --- "Erreur calcul" pour avertir que rien n'a ete calcule).
        trace_calcul = etat.trace_de("calcul")
        calcul = trace_calcul.resultat if trace_calcul else None
        if trace_calcul is not None and trace_calcul.etat is EtatEtape.ABANDONNEE:
            resultat_calcul = f"Erreur calcul : {trace_calcul.raison}"
        elif isinstance(calcul, dict) and not calcul.get("sans_code"):
            resultat_calcul = calcul.get("stdout", "")
        else:
            resultat_calcul = ""

        # --- Synthese finale : la revision l'emporte si elle a abouti.
        trace_revision = etat.trace_de("revision")
        if (trace_revision is not None
                and trace_revision.etat is EtatEtape.REUSSIE
                and isinstance(trace_revision.resultat, str)
                and trace_revision.resultat.strip()):
            final_response = trace_revision.resultat.strip()
        else:
            final_response = str(etat.resultats.get("synthese", "")).strip()

        # --- Critique : exposee telle quelle, sans reformulation.
        critique_finale: Optional[Dict[str, Any]] = None
        trace_critique = etat.trace_de("critique")
        if (trace_critique is not None
                and trace_critique.etat is EtatEtape.REUSSIE
                and isinstance(trace_critique.resultat, dict)):
            brut = trace_critique.resultat
            critique_finale = {
                "ok": brut.get("ok"),
                "raison": brut.get("raison", ""),
                "confiance": brut.get("confiance"),
            }

        return {
            "status": "success" if etat.aboutie else "error",
            "plan": str(etat.resultats.get("plan", "")).strip(),
            "calculation_result": resultat_calcul,
            "final_response": final_response,
            "profondeur": profondeur,
            "critique": critique_finale,
            # L'etat reel des etapes, pour que l'interface montre ce qui s'est
            # passe au lieu de l'inventer.
            "coordination": etat.to_dict(),
        }
