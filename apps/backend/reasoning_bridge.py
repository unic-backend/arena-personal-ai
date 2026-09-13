"""Point d'entree unique du raisonnement profond depuis le pipeline de chat.

Ce module existe pour une raison precise : `apps/backend/routers/chat.py`
fait plusieurs centaines de lignes, et chaque modification qu'on y fait
risque de casser une branche voisine. La critique et la revision du moteur
de raisonnement (13/09/2026) n'ont pas besoin d'etre visibles dans le
routeur — elles n'ont besoin que d'etre **branchees**. C'est ce que fait ce
module : il decide la profondeur, appelle le moteur, et prepare le resultat
dans la forme exacte que le routeur attendait deja.

**Ce que fait `resoudre_profondement` :**

1. Choisit la profondeur (`standard` ou `approfondie`) selon la demande.
2. Appelle `ReasoningEngine.solve_complex_task` avec cette profondeur.
3. Prepare `response` avec la note de calcul (comportement historique) ET,
   si la critique a rendu un verdict KO, une note de critique.
4. Expose `critique` et `profondeur` en clair dans le dictionnaire rendu,
   pour que la PWA et la passerelle OpenAI puissent les afficher.

**Ce que ce module ne fait PAS :**

- Il ne modifie pas le moteur de raisonnement. Il l'appelle.
- Il ne reformule pas la reponse. Il la transporte.
- Il ne decide pas a la place du routeur : le routeur passe par lui parce
  qu'il veut un raisonnement profond, ce module lui en donne un.

**Pourquoi `note_de_calcul` est dupliquee ici.** Elle vit dans `chat.py`
aujourd'hui. L'importer depuis ce module creerait un cycle (`chat.py`
importera ce bridge, qui importera `chat.py`). La fonction fait trois
lignes, elle ne depend d'aucun etat : la dupliquer est moins couteux que
de casser la frontiere des modules.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger("usman.backend.reasoning_bridge")


#: Ce que le moteur de raisonnement ecrit quand le calcul n'a PAS eu lieu.
#: Meme chaine que `CALCUL_REFUSE` dans `chat.py`, et pour la meme raison :
#: sans cette relecture, le modele pouvait presenter un resultat elegant
#: sans dire qu'aucun calcul ne l'avait verifie.
CALCUL_REFUSE = "Erreur calcul"


#: Ce qui, dans une demande, justifie de payer DEUX appels de modele en plus
#: (une critique, et une revision si la critique dit KO) plutot que de s'en
#: tenir au mode standard. Le mode approfondie n'est pas meilleur en soi :
#: il est plus sur, et plus cher. La question est de savoir si ca vaut la
#: peine pour CETTE demande.
#:
#: Les mots sont choisis pour etre non ambigus : « verifie » dans une phrase
#: ordinaire parle bien de verification, jamais d'autre chose.
MOTS_VERIFICATION = (
    "vérifie", "verifie", "vérifies", "verifies",
    "prouve", "prouves", "démontre", "demontre",
    "corrige", "corriges", "correction",
    "critique", "critiques", "relis", "relire",
    "revois", "revoir", "revision", "révision",
    "controle", "contrôle", "contrôler", "controler",
    "assure-toi", "assure toi", "assurez-vous", "assurez vous",
    "es-tu sûr", "es tu sur", "es-tu sur", "es tu sûr",
    "tu es sûr", "tu es sur",
    "sans erreur", "rigoureux", "rigoureuse",
    "double-check", "double check", "verifie bien",
)


def profondeur_pour(demande: str) -> str:
    """Choisit `standard` ou `approfondie` selon la demande.

    Regles deterministes, aucun appel modele :

    1. Un mot de verification (voir `MOTS_VERIFICATION`) -> `approfondie`.
    2. Une demande longue (>200 caracteres) -> `approfondie`. Une question
       longue porte souvent plusieurs contraintes, et la critique aide a
       detecter les contraintes oubliees.
    3. Sinon -> `standard`.

    L'objectif n'est pas d'etre fin, il est d'etre PREVISIBLE. Une demande
    qui contient « verifie » merite une critique ; une demande qui dit
    « combien font 12 % de 340 » n'en merite pas.
    """
    texte = (demande or "").lower()
    if any(mot in texte for mot in MOTS_VERIFICATION):
        return "approfondie"
    if len(demande or "") > 200:
        return "approfondie"
    return "standard"


def note_de_calcul(calcul: str) -> str:
    """Ce qu'il faut ajouter a la reponse quand le calcul a ete refuse.

    Chaine vide quand le calcul a eu lieu, ou quand il n'y avait pas de
    calcul a faire : on n'ajoute pas un avertissement a une reponse qui ne
    pretend rien calculer.

    Dupliquee depuis `chat.py` — voir la note en tete de module.
    """
    if not calcul or not calcul.startswith(CALCUL_REFUSE):
        return ""
    return ("\n\n⚠️ Le calcul n'a pas pu etre execute : "
            f"{calcul[len(CALCUL_REFUSE):].lstrip(' :')} "
            "Ce qui precede n'a donc ete verifie par aucun calcul.")


def note_de_critique(critique: Optional[Dict[str, Any]]) -> str:
    """Ce qu'il faut ajouter a la reponse quand la critique a dit KO.

    Chaine vide dans trois cas, tous volontaires :

    - `critique` est `None` : le mode standard n'a pas critique, rien a dire.
    - `critique["ok"]` est `True` : la critique a valide, aucun avertissement.
    - `critique["ok"]` est `None` : la critique n'a pas rendu de verdict
      exploitable. Le moteur l'a alors abandonnee, la synthese originale a
      ete conservee, et il n'y a rien a signaler a l'utilisateur — c'est un
      probleme interne, pas un probleme de sa reponse.

    Quand le verdict est `KO`, on ecrit la raison donnee par la critique, et
    la confiance si elle a ete chiffree. Rien n'est reformule.
    """
    if not critique:
        return ""
    if critique.get("ok") is not False:
        return ""
    raison = critique.get("raison") or "sans raison donnee"
    confiance = critique.get("confiance")
    if isinstance(confiance, (int, float)):
        return (f"\n\n🔍 Un relecteur independant a signale une insuffisance "
                f"(confiance {confiance:.2f}) : {raison}")
    return f"\n\n🔍 Un relecteur independant a signale une insuffisance : {raison}"


async def resoudre_profondement(
    demande: str,
    moteur: Optional[Any] = None,
) -> Dict[str, Any]:
    """Appelle le moteur de raisonnement et prepare le resultat pour le chat.

    Args:
        demande: la question de l'utilisateur, telle quelle.
        moteur: le moteur de raisonnement a utiliser. `None` = celui du
            runtime de production (`apps.backend.runtime.reasoning_engine`).
            Ce parametre existe pour les tests : ils peuvent passer un faux
            moteur au lieu de dependre d'Ollama.

    Returns:
        Un dictionnaire dans la forme exacte que `_aiguiller` attendait deja
        pour la branche DEEP_REASONING, augmente de deux cles :

        - `profondeur`: `"standard"` ou `"approfondie"`.
        - `critique`: le verdict de la critique, ou `None` en mode standard.

        Les cles historiques (`status`, `agent`, `plan`, `calcul`,
        `response`) sont preservees a l'identique. Aucun appelant existant
        n'a besoin de connaitre les deux nouvelles pour continuer a lire la
        reponse.
    """
    if moteur is None:
        # Import differe : le module reste importable meme quand le runtime
        # n'est pas disponible (utile aux tests, et evite un cycle a
        # l'import).
        from apps.backend.runtime import reasoning_engine as moteur  # type: ignore[no-redef]

    profondeur = profondeur_pour(demande)
    logger.info("Raisonnement profond en mode %s.", profondeur)

    raisonnement = await moteur.solve_complex_task(demande, profondeur=profondeur)

    calcul = raisonnement.get("calculation_result") or ""
    critique = raisonnement.get("critique")
    profondeur_effective = raisonnement.get("profondeur", profondeur)

    # La note de calcul d'abord (comportement historique inchange), la note
    # de critique ensuite. Un utilisateur qui voit les deux comprend qu'il y
    # a un probleme a deux niveaux : pas de verification, et verdict KO.
    reponse_finale = (
        str(raisonnement.get("final_response", ""))
        + note_de_calcul(calcul)
        + note_de_critique(critique)
    )

    resultat: Dict[str, Any] = {
        "status": raisonnement.get("status", "success"),
        "agent": "ReasoningEngine",
        "plan": raisonnement.get("plan", ""),
        # Le calcul voyage avec la reponse : sans lui, personne ne peut
        # verifier que le chiffre annonce vient d'une execution.
        "calcul": calcul,
        "response": reponse_finale,
        "profondeur": profondeur_effective,
    }
    # `critique` n'est ajoute que s'il y en a une : un mode standard qui
    # ecrirait `"critique": None` ferait croire qu'un verdict a ete rendu.
    if critique is not None:
        resultat["critique"] = critique
    return resultat