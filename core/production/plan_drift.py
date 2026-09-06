"""Traduire une demande de montage en opérations Drift — sans jamais laisser
le modèle deviner ce que Drift accepte.

Même discipline que `core/montage/planificateur.py` (montage interne
d'ARENA) et `core/production/plan_video.py` (graphe Video) : une opération
hors de ce que Drift annonce LUI-MÊME est refusée et nommée, jamais devinée.
La différence avec ces deux modules est la raison d'être de celui-ci : la
liste des opérations Drift n'est PAS fixée dans le code d'ARENA (Drift n'a
pas de version figée ici, ce n'est pas une bibliothèque importée) — elle
n'existe QUE dans le schéma que son serveur MCP rend, en direct, pour
CHAQUE toolbox (`toolbox({name})`, `core/connectors/drift.py`). Ce module ne
valide donc jamais contre une liste écrite ici, mais contre le schéma
RÉELLEMENT reçu au moment de l'appel.

**Ce qui EST fixé ici, et qui peut l'être sans deviner** : les dix noms de
toolboxes que Drift documente lui-même dans `docs/MCP.md` (media, timeline,
canvas, playback, text, effects, subtitles, audio, ai, scene). Un nom hors
de cette liste est refusé avant même d'interroger Drift — inutile d'aller
chercher un schéma pour un nom que Drift n'a jamais annoncé.

**Hypothèse explicite, non vérifiable sans son poste** (mission, §« Drift »,
06/09/2026 : la machine de développement ne fait pas tourner Drift, un
programme de bureau Qt) : `toolbox({name})` est supposé rendre une forme
proche de celle de MCP lui-même (`tools/list`) —
`{"tools": [{"name": str, "inputSchema": {"properties": {...},
"required": [...]}}]}`. Si la forme réelle diffère,
`_operations_de_la_toolbox` rend un dictionnaire vide plutôt que de lever :
toute opération proposée par le modèle est alors refusée, nommée, jamais
exécutée à l'aveugle — le mode d'échec est un refus, jamais une supposition.
À CONFIRMER sur sa machine, avec le VRAI Drift (`docs/CURRENT_TASK.md`).

**La substitution de média suit exactement `core/montage/planificateur.py`
::_resoudre_le_media** : le modèle ne cite jamais un chemin, seulement un
NOM de l'inventaire ouvert par l'appelant. Un paramètre dont le schéma
Drift nomme la clé avec "path"/"media"/"file"/"source"/"clip" est résolu
ainsi ; un nom hors inventaire est refusé.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Mapping, Tuple

logger = logging.getLogger("usman.production.plan_drift")

#: Les dix toolboxes documentées par Drift lui-même (`docs/MCP.md`). Un nom
#: hors de cette liste ne vaut même pas la peine d'interroger Drift.
TOOLBOXES_FERMEES: Tuple[str, ...] = (
    "media", "timeline", "canvas", "playback", "text", "effects",
    "subtitles", "audio", "ai", "scene",
)

#: Les clés de paramètre qui désignent un fichier — jamais un chemin cité
#: par le modèle, toujours un NOM résolu depuis l'inventaire de l'appelant.
CLES_MEDIA = ("path", "media", "media_path", "file", "clip_path", "source")


class PlanDriftRefuse(Exception):
    """Le plan Drift ne tient pas, et on dit pourquoi. Aucun repli."""


def extraire_json(texte: str) -> Any:
    """Le premier objet ou tableau JSON du texte du modèle.

    Réécrite ici plutôt que réimportée, même raison que dans
    `plan_video.py` : les deux formats restent indépendants.
    """
    for ouvrant, fermant in (("[", "]"), ("{", "}")):
        debut, fin = texte.find(ouvrant), texte.rfind(fermant)
        if debut != -1 and fin > debut:
            try:
                return json.loads(texte[debut:fin + 1])
            except json.JSONDecodeError:
                continue
    raise PlanDriftRefuse("Le modèle n'a pas rendu de JSON lisible.")


def _operations_de_la_toolbox(schema: Any) -> Dict[str, Dict[str, Any]]:
    """Les opérations réellement annoncées par Drift pour une toolbox, sous
    la forme `{nom: outil}`. Une forme inattendue rend un dictionnaire vide
    — jamais une exception qui ferait paraître Drift en panne pour un
    format simplement différent de l'hypothèse posée ci-dessus."""
    try:
        outils = schema.get("tools") or []
        return {str(outil["name"]): outil for outil in outils if isinstance(outil, Mapping) and outil.get("name")}
    except (AttributeError, TypeError, KeyError):
        return {}


def _proprietes_de(outil: Mapping[str, Any]) -> Tuple[set, set]:
    """`(proprietes_connues, requises)` lues sur le schéma JSON de l'outil.
    Une forme inattendue rend deux ensembles vides — même repli que
    `_operations_de_la_toolbox`."""
    try:
        schema_entree = outil.get("inputSchema") or {}
        proprietes = set((schema_entree.get("properties") or {}).keys())
        requises = set(schema_entree.get("required") or [])
        return proprietes, requises
    except (AttributeError, TypeError):
        return set(), set()


def _resoudre_medias(
    parametres: Dict[str, Any], medias_autorises: Mapping[str, str],
) -> Tuple[Dict[str, Any], List[str]]:
    """Substitue un chemin réel à chaque paramètre qui désigne un média —
    le modèle ne cite qu'un NOM, jamais un chemin. Rend `(parametres,
    erreurs)` : une erreur non vide signifie que l'opération est refusée."""
    resolus: Dict[str, Any] = {}
    erreurs: List[str] = []
    for cle, valeur in parametres.items():
        if cle not in CLES_MEDIA:
            resolus[cle] = valeur
            continue
        nom = str(valeur or "").strip()
        if not nom or nom not in medias_autorises:
            disponibles = ", ".join(sorted(medias_autorises)) or "aucun"
            erreurs.append(f"{cle} : « {nom or '(vide)'} » absent de l'inventaire ({disponibles}).")
            continue
        resolus[cle] = medias_autorises[nom]
    return resolus, erreurs


def valider_operations(
    brut: Any,
    toolboxes_chargees: Mapping[str, Any],
    medias_autorises: Mapping[str, str],
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Transforme ce que le modèle a produit en opérations Drift sûres.

    Args:
        brut: le JSON déjà parsé — une liste d'opérations, ou un objet
            portant une clé `operations`.
        toolboxes_chargees: `{nom_toolbox: schema}` — UNIQUEMENT les
            toolboxes réellement récupérées via `drift.boite_a_outils` dans
            ce tour. Une toolbox absente d'ici n'a jamais été vérifiée : ses
            opérations sont refusées, jamais supposées correctes.
        medias_autorises: `{nom: chemin}` — l'inventaire ouvert au modèle.

    Returns:
        `(operations, refus)`. `operations` sont sûres pour `apply({ops})` :
        toolbox connue de Drift, opération présente dans son VRAI schéma,
        paramètres connus de ce schéma, aucun chemin cité en clair.
    """
    if isinstance(brut, Mapping):
        brut = brut.get("operations", brut.get("ops"))
    if not isinstance(brut, list):
        raise PlanDriftRefuse("Le plan Drift doit être une liste d'opérations.")

    operations: List[Dict[str, Any]] = []
    refus: List[str] = []

    for numero, ligne in enumerate(brut, start=1):
        if not isinstance(ligne, Mapping):
            refus.append(f"#{numero} : ce n'est pas une opération ({type(ligne).__name__}).")
            continue

        toolbox = str(ligne.get("toolbox") or "").strip()
        if toolbox not in TOOLBOXES_FERMEES:
            refus.append(f"#{numero} : toolbox refusée « {toolbox or '(aucune)'} ».")
            continue
        schema = toolboxes_chargees.get(toolbox)
        if schema is None:
            refus.append(f"#{numero} {toolbox} : cette toolbox n'a jamais été chargée depuis Drift.")
            continue

        operation = str(ligne.get("operation") or "").strip()
        outils_connus = _operations_de_la_toolbox(schema)
        if operation not in outils_connus:
            connues = ", ".join(sorted(outils_connus)) or "aucune"
            refus.append(
                f"#{numero} {toolbox} : opération refusée « {operation or '(aucune)'} » "
                f"(annoncées par Drift : {connues}).")
            continue

        parametres = ligne.get("parametres") or {}
        if not isinstance(parametres, Mapping):
            refus.append(f"#{numero} {toolbox}.{operation} : les paramètres doivent être un objet.")
            continue

        proprietes, requises = _proprietes_de(outils_connus[operation])
        inconnus = sorted(set(parametres) - proprietes) if proprietes else []
        if inconnus:
            refus.append(f"#{numero} {toolbox}.{operation} : paramètre(s) inconnu(s) {', '.join(inconnus)}.")
            continue
        manquants = sorted(requises - set(parametres))
        if manquants:
            refus.append(f"#{numero} {toolbox}.{operation} : paramètre(s) requis manquant(s) {', '.join(manquants)}.")
            continue

        resolus, erreurs_media = _resoudre_medias(dict(parametres), medias_autorises)
        if erreurs_media:
            refus.append(f"#{numero} {toolbox}.{operation} : " + " ".join(erreurs_media))
            continue

        operations.append(_vers_forme_drift(toolbox, operation, resolus))

    if not operations:
        raise PlanDriftRefuse(
            "Aucune opération Drift exploitable dans le plan. " + (
                " ".join(refus) if refus else "Il était vide."))
    return operations, refus


def _vers_forme_drift(toolbox: str, operation: str, parametres: Dict[str, Any]) -> Dict[str, Any]:
    """La forme envoyée dans `apply({ops:[...]})`.

    **Non vérifiable sans le vrai Drift** (mission §« Drift », machine de
    développement sans Drift). Cette fonction est le SEUL endroit qui
    suppose la forme d'un élément de `ops` — si le format réel diverge
    (mesuré sur sa machine), c'est ici, et seulement ici, qu'un ajustement
    suffira. `SUGGESTION — À CONFIRMER SUR SA MACHINE`.
    """
    return {"toolbox": toolbox, "op": operation, "params": parametres}


def inventaire_depuis(chemins: List[str]) -> Dict[str, str]:
    """L'inventaire ouvert au modèle, à partir de fichiers qui existent.

    Même fonction que `core/montage/planificateur.py::inventaire_depuis` —
    réécrite ici pour la même raison d'indépendance des deux formats.
    """
    from pathlib import Path
    inventaire: Dict[str, str] = {}
    for brut in chemins:
        chemin = Path(brut)
        if chemin.is_file():
            inventaire[chemin.stem] = str(chemin.resolve())
    return inventaire


def prompt_de_planification(
    demande: str,
    toolboxes_schemas: Mapping[str, Any],
    inventaire: Mapping[str, str],
) -> str:
    """Le prompt qui demande un plan d'opérations Drift, et rien d'autre.

    Les opérations proposées au modèle sont EXACTEMENT celles que Drift a
    annoncées dans les schémas déjà chargés — jamais une liste écrite à la
    main qui pourrait diverger de la vraie version installée chez lui.
    """
    lignes_toolbox = []
    for toolbox in sorted(toolboxes_schemas):
        outils = _operations_de_la_toolbox(toolboxes_schemas[toolbox])
        for nom, outil in sorted(outils.items()):
            proprietes, requises = _proprietes_de(outil)
            detail = ", ".join(sorted(proprietes)) or "(sans paramètre)"
            lignes_toolbox.append(
                f"- {toolbox}.{nom}({detail})" + (f" — requis : {', '.join(sorted(requises))}" if requises else ""))
    liste_operations = "\n".join(lignes_toolbox) or "- (aucune opération chargée)"
    liste_medias = "\n".join(f"- {nom}" for nom in sorted(inventaire)) or "- (aucun média disponible)"

    return f"""Tu prépares une liste d'opérations de montage pour Drift.
Réponds UNIQUEMENT par un tableau JSON d'opérations, sans prose autour.

Chaque opération :
{{"toolbox": str, "operation": str, "parametres": {{...}}}}

Opérations RÉELLEMENT disponibles dans Drift, et elles seules — un nom hors
de cette liste sera refusé :
{liste_operations}

Ne cite AUCUN chemin de fichier : un paramètre qui désigne un média se
donne par son NOM, choisi dans cette liste :
{liste_medias}

Demande du propriétaire :
{demande}

JSON :"""
