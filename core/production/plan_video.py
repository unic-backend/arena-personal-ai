"""Traduire un objectif Video en graphe de production — sans jamais laisser
le modele piloter directement les capacites reelles.

Meme discipline que `core/montage/planificateur.py`, deja verifiee sur le
montage : une capacite hors de la liste fermee est refusee et nommee,
jamais devinee. Un plan invalide n'est jamais remplace par un plan par
defaut — le refus se rapporte avec sa raison, il ne se simule pas.
"""
from __future__ import annotations

import json
from typing import Any, List, Mapping, Tuple

from core.production.etat_projet import EtapeProjet

#: La liste fermee des capacites reelles qu'un projet Video peut composer
#: (DEC-0037). « vision » et « transcription » sont des LECTURES ; « wangp »,
#: « moneyprinter » et « narration » sont des ECRITURES qui passent par la
#: file de confirmation existante (`core/actions/attente.py`, verrouillee) —
#: rien n'est confirme a la place du proprietaire. « montage » assemble ce
#: que les etapes precedentes ont reellement produit.
CAPACITES_VIDEO: Tuple[str, ...] = (
    "vision", "transcription", "wangp", "moneyprinter", "narration", "montage",
)


class PlanRefuse(Exception):
    """Le graphe propose ne tient pas, et on dit pourquoi. Aucun repli."""


def extraire_json(texte: str) -> Any:
    """Le premier objet ou tableau JSON du texte du modele.

    Meme fonction que `core/montage/planificateur.py:extraire_json` —
    reecrite ici plutot que reimportee : les deux modules restent
    independants, et un futur changement du format de montage ne doit pas
    silencieusement affecter celui du projet Video.
    """
    for ouvrant, fermant in (("[", "]"), ("{", "}")):
        debut, fin = texte.find(ouvrant), texte.rfind(fermant)
        if debut != -1 and fin > debut:
            try:
                return json.loads(texte[debut:fin + 1])
            except json.JSONDecodeError:
                continue
    raise PlanRefuse("Le modele n'a pas rendu de JSON lisible.")


def valider_graphe(
    brut: Any,
    capacites_autorisees: Tuple[str, ...] = CAPACITES_VIDEO,
) -> Tuple[List[EtapeProjet], List[str]]:
    """Transforme ce que le modele a produit en graphe executable.

    Args:
        brut: le JSON deja parse — une liste d'etapes, ou un objet portant
            une cle `etapes`/`graphe`.
        capacites_autorisees: le sous-ensemble ouvert pour CE projet — le
            mode TEAM (choix explicite du proprietaire) restreint la liste
            fermee par defaut, il ne l'elargit jamais.

    Returns:
        `(etapes, refus)`. Les etapes sont sures : capacite dans la liste
        fermee, id unique, dependances citees comme de simples chaines
        (une reference vers un id inconnu n'est jamais devinee — l'executeur
        la traite deja comme "jamais resolue", explicitement, sans boucler).
        `refus` nomme chaque ligne ecartee et sa raison.

    Raises:
        PlanRefuse: si la forme d'ensemble n'est pas un plan, ou si aucune
            etape ne survit.
    """
    if isinstance(brut, Mapping):
        brut = brut.get("etapes", brut.get("graphe"))
    if not isinstance(brut, list):
        raise PlanRefuse("Le plan doit etre une liste d'etapes.")

    etapes: List[EtapeProjet] = []
    ids_connus: set = set()
    refus: List[str] = []

    for numero, ligne in enumerate(brut, start=1):
        if not isinstance(ligne, Mapping):
            refus.append(f"#{numero} : ce n'est pas une etape ({type(ligne).__name__}).")
            continue

        id_etape = str(ligne.get("id") or "").strip()
        if not id_etape:
            refus.append(f"#{numero} : aucun id.")
            continue
        if id_etape in ids_connus:
            refus.append(f"#{numero} {id_etape} : id deja utilise dans ce plan.")
            continue

        capacite = str(ligne.get("capacite") or "").strip()
        if capacite not in capacites_autorisees:
            refus.append(f"#{numero} {id_etape} : capacite refusee « {capacite or '(aucune)'} ».")
            continue

        parametres = ligne.get("parametres") or {}
        if not isinstance(parametres, Mapping):
            refus.append(f"#{numero} {id_etape} : les parametres doivent etre un objet.")
            continue

        depend_de_brut = ligne.get("depend_de") or []
        if not isinstance(depend_de_brut, list):
            refus.append(f"#{numero} {id_etape} : depend_de doit etre une liste.")
            continue

        etapes.append(EtapeProjet(
            id=id_etape, capacite=capacite, parametres=dict(parametres),
            depend_de=tuple(str(d) for d in depend_de_brut),
            facultative=bool(ligne.get("facultative", False)),
        ))
        ids_connus.add(id_etape)

    etapes = _sans_montage_sur_ecriture_directe(etapes, refus)

    if not etapes:
        raise PlanRefuse(
            "Aucune etape exploitable dans le plan. " + (
                " ".join(refus) if refus else "Il etait vide."))
    return etapes, refus


#: Une capacite d'ECRITURE : elle passe par la file de confirmation
#: existante (`core/actions/attente.py`, verrouillee — DEC-0013). Sa
#: soumission rend `NEEDS_CONFIRMATION`, jamais un fichier immediatement
#: disponible : WanGP/MoneyPrinterTurbo generent en arriere-plan (le
#: `preuve` d'une soumission est un identifiant de tache, pas un chemin —
#: `core/connectors/wan2gp.py`/`moneyprinter.py`), et VoiceStudio n'ecrit
#: son fichier reel qu'une fois la confirmation passee
#: (`core/connectors/audio_voix.py`).
CAPACITES_ECRITURE = frozenset({"wangp", "moneyprinter", "narration"})


def _sans_montage_sur_ecriture_directe(
    etapes: List[EtapeProjet], refus: List[str],
) -> List[EtapeProjet]:
    """Refuse un montage qui dependrait directement d'une ecriture.

    Le fichier reel d'une generation ou d'une narration n'existe qu'APRES
    confirmation du proprietaire (jamais dans le meme passage) — le
    detecter ici, au moment du plan, vaut mieux qu'un montage qui echouerait
    plus tard faute de media, sans que la vraie raison soit dite.
    """
    capacite_par_id = {etape.id: etape.capacite for etape in etapes}
    gardees: List[EtapeProjet] = []
    for etape in etapes:
        ecritures = [f"{d} ({capacite_par_id[d]})" for d in etape.depend_de
                     if capacite_par_id.get(d) in CAPACITES_ECRITURE]
        if etape.capacite == "montage" and ecritures:
            refus.append(
                f"{etape.id} : ne peut pas dependre de {', '.join(ecritures)} "
                "— une ecriture (generation ou narration) passe par "
                "confirmation, son fichier reel n'existe qu'apres, jamais "
                "dans le meme passage.")
            continue
        gardees.append(etape)
    return gardees


def prompt_de_planification(
    objectif: str,
    references: List[str],
    capacites_autorisees: Tuple[str, ...] = CAPACITES_VIDEO,
) -> str:
    """Le prompt qui demande un graphe, et rien d'autre.

    Les references figurent par NOM seul (index dans la liste), jamais par
    chemin : le modele ne doit designer aucun fichier qu'on ne lui a pas
    ouvert — meme discipline que `core/montage/planificateur.py`.
    """
    liste_refs = "\n".join(f"- ref{i}" for i in range(len(references))) or "- (aucune reference)"
    liste_capacites = "\n".join(f"- {c}" for c in capacites_autorisees)

    return f"""Tu composes un projet video a partir de plusieurs capacites reelles.
Reponds UNIQUEMENT par un tableau JSON d'etapes, sans prose autour.

Chaque etape :
{{"id": str, "capacite": str, "parametres": {{...}}, "depend_de": [str, ...], "facultative": bool}}

Capacites autorisees, et elles seules :
{liste_capacites}

N'utilise QUE ce qui est reellement necessaire a l'objectif — ne compose pas
une capacite qui ne sert a rien ici. Une etape ne depend que d'un id
d'etape de CE plan.

References disponibles (cite-les par nom, jamais par chemin) :
{liste_refs}

Objectif du proprietaire :
{objectif}

JSON :"""
