"""L'agent de preuve : le modele propose, Lean tranche, ARENA rapporte.

Cet agent est **mince, et c'est voulu**. Il ne raisonne pas a la place du
moteur existant (`core/reasoning/reasoning_engine.py`, inchange) et n'est
pas un second moteur de mathematiques : il traduit une phrase en capacite
du connecteur `formel`, exactement comme `agents/audio/audio_agent.py`
traduit « lis-moi ce texte » en `parler`.

**La relation ne s'inverse jamais :**

    le modele  : « je propose cette preuve »
    Lean       : « je l'accepte / je la refuse »
    ARENA      : « voici le verdict, et d'ou il vient »

Le mot « verifie » ne sort donc **jamais** d'une phrase du modele : il
sort du `ResultatAction` du connecteur, qui l'a lui-meme lu dans la sortie
du binaire.

**Deux chemins, une seule capacite :**

1. La demande porte deja du Lean (bloc ```lean, ou une source qui declare
   un `theorem`) : on verifie ce qui est donne, sans rien demander a un
   modele. C'est le chemin qui marche meme sans Ollama.
2. La demande est en francais (« prouve formellement que... ») : le modele
   ecrit un candidat, Lean le juge. En cas de refus, **une seule**
   correction est tentee, avec le diagnostic reel de Lean — puis on
   s'arrete. Une boucle de reparation sans borne couterait des tours de
   modele pour une preuve qui, souvent, ne tient pas.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

from core.agent.base_agent import BaseAgent
from core.memory.memory_manager import MemoryManager
from core.models.base import ModelProvider

logger = logging.getLogger("usman.agent.formel")

CONNECTEUR = "formel"

#: Une seule correction apres un refus. Le modele qui n'a pas trouve la
#: preuve du premier coup la trouve rarement au troisieme, et chaque tour
#: coute un appel modele plus une compilation.
CORRECTIONS_MAX = 1

BLOC_LEAN = re.compile(r"```(?:lean4?)?\s*\n(.*?)```", re.DOTALL)

#: Ce qui, dans une source, dit qu'elle est deja du Lean exploitable.
DECLARE_UN_THEOREME = re.compile(r"\b(?:theorem|lemma|example)\b")

CONSIGNE_LEAN = (
    "Tu ecris du Lean 4 (sans Mathlib : seule la bibliotheque standard est "
    "disponible). Rends UNIQUEMENT un bloc ```lean contenant un `theorem` "
    "nomme et sa demonstration complete.\n"
    "Interdits absolus : `sorry`, `admit`, tout axiome ajoute — une preuve "
    "trouee compile et sera REJETEE.\n"
)


def source_lean(phrase: str) -> Optional[str]:
    """Le Lean contenu dans la demande, ou `None` s'il n'y en a pas.

    Un bloc ```lean prime ; sinon, une phrase qui declare elle-meme un
    theoreme est prise telle quelle. Rien n'est devine au-dela.
    """
    bloc = BLOC_LEAN.search(phrase or "")
    if bloc and DECLARE_UN_THEOREME.search(bloc.group(1)):
        return bloc.group(1).strip()
    if DECLARE_UN_THEOREME.search(phrase or "") and ":=" in (phrase or ""):
        return (phrase or "").strip()
    return None


class FormelAgent(BaseAgent):
    """Verifier une preuve — en passant par le connecteur, jamais en direct."""

    def __init__(
        self,
        provider: ModelProvider,
        memory: Optional[MemoryManager] = None,
        registre: Any = None,
    ):
        super().__init__(
            name="FormelAgent",
            description="Vérification formelle : Lean accepte ou rejette, le modèle ne tranche jamais.",
            provider=provider,
            memory=memory,
        )
        self.registre = registre

    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if self.registre is None:
            return self._erreur("Le connecteur de vérification formelle n'est pas branché sur cet agent.")

        contexte = context or {}
        donnee = str(contexte.get("source_lean") or "").strip() or source_lean(user_input)

        if donnee:
            return self._depuis(self._verifier(donnee), source=donnee, tentatives=1)
        return await self._ecrire_puis_verifier(user_input)

    # --- Les deux chemins -------------------------------------------------------

    def _verifier(self, source: str) -> Any:
        """Le SEUL endroit qui produit un verdict. Toujours le connecteur."""
        return self.registre.executer(CONNECTEUR, "verifier", source=source)

    async def _ecrire_puis_verifier(self, demande: str) -> Dict[str, Any]:
        """Le modele propose, Lean juge, une correction au plus."""
        try:
            brut = await self.provider.generate(
                prompt=f"{CONSIGNE_LEAN}\nÉnoncé à démontrer : {demande}\n")
        except Exception as erreur:  # noqa: BLE001 — l'echec du modele se nomme
            logger.warning("Le modele n'a pas repondu : %s", erreur)
            return self._erreur(f"Le moteur n'a pas répondu : {erreur}")

        candidat = source_lean(brut) or ""
        if not candidat:
            return self._erreur(
                "Le modèle n'a pas produit de théorème Lean exploitable : "
                "rien n'a été vérifié.")

        resultat = self._verifier(candidat)
        tentatives = 1

        for _ in range(CORRECTIONS_MAX):
            if resultat.statut.value == "SUCCESS":
                break
            diagnostic = str(resultat.detail.get("diagnostics") or resultat.message)[:1500]
            try:
                brut = await self.provider.generate(prompt=(
                    f"{CONSIGNE_LEAN}\nÉnoncé : {demande}\n\n"
                    f"Ta preuve précédente a été REJETÉE par Lean :\n{candidat}\n\n"
                    f"Diagnostic exact de Lean :\n{diagnostic}\n\n"
                    "Corrige la preuve. Rends uniquement le bloc ```lean corrigé."))
            except Exception as erreur:  # noqa: BLE001
                logger.warning("Correction impossible : %s", erreur)
                break
            corrige = source_lean(brut)
            if not corrige or corrige == candidat:
                break
            candidat, tentatives = corrige, tentatives + 1
            resultat = self._verifier(candidat)

        return self._depuis(resultat, source=candidat, tentatives=tentatives)

    # --- Traduction -------------------------------------------------------------

    def _depuis(self, resultat: Any, source: str, tentatives: int) -> Dict[str, Any]:
        """Rend le verdict du connecteur, sans jamais l'adoucir."""
        statut = resultat.statut.value
        reponse: Dict[str, Any] = {
            "agent": self.name,
            "action": "verifier",
            "response": resultat.message,
            "source_lean": source,
            "tentatives": tentatives,
            **resultat.detail,
        }
        if statut == "SUCCESS":
            reponse["status"] = "success"
            reponse["preuve"] = resultat.preuve
        elif statut in ("NOT_CONFIGURED", "NEEDS_CONFIRMATION"):
            # Lean absent ou permission a donner : un etat, pas une panne — et
            # surtout pas une preuve verifiee.
            reponse["status"] = "warning"
        else:
            reponse["status"] = "error"
        return reponse

    def _erreur(self, message: str) -> Dict[str, Any]:
        return {"status": "error", "agent": self.name, "response": message}
