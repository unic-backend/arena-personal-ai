"""Decouvrir les agents reellement presents, et ce qu'ils savent faire.

**Le defaut que ce module ferme (DEC-0145).** Le registre des collaborateurs
etait rempli par une liste ecrite a la main dans `apps/backend/runtime.py`
(`_equipe`) : un agent ajoute demain n'y serait entre que si quelqu'un pensait
a l'y ajouter, et la liste des outils consultables etait tenue de meme.

Ici, rien n'est nomme. Un espace de noms (le module qui compose l'application)
est parcouru ; tout ce qui s'y trouve et qui EST un agent y est pris :

- toute instance de `BaseAgent` ;
- tout objet qui expose un `run` asynchrone ET declare un `identifiant` — un
  outil (documents, raisonnement...) qui accepte d'etre consulte.

Chaque agent se decrit lui-meme : `identifiant`, `description`, `competences`
(facultatives), `version`. Ce qui n'est pas declare est deduit de ce que
l'objet porte vraiment (ses outils, sa memoire, son modele) — jamais invente.
"""
from __future__ import annotations

import inspect
import math
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Tuple

#: Les mots qui ne disent rien d'une competence.
_MOTS_VIDES = frozenset("""
    agent agents avec dans des les une pour par sur est aux son ses qui que
    the and for with from this that your mes mon ma ton tes leur plus tout
    tous toute toutes fait faire etre avoir cette ces lui elle ils elles
    """.split())


def normaliser(texte: str) -> str:
    """Minuscules, sans accents : « Vidéo » et « video » sont le meme mot."""
    decompose = unicodedata.normalize("NFKD", str(texte or ""))
    return "".join(c for c in decompose if not unicodedata.combining(c)).lower()


def mots(texte: str) -> List[str]:
    """Les mots porteurs d'un texte, normalises."""
    return [m for m in re.findall(r"[a-z0-9]+", normaliser(texte))
            if len(m) >= 3 and m not in _MOTS_VIDES]


def identifiant_de(objet: Any) -> str:
    """L'identifiant que l'agent declare, ou celui deduit de son nom.

    `CoderAgent` sans declaration devient `coder` : un agent ajoute sans
    y penser reste joignable, sous un nom stable. Le nom de l'INSTANCE passe
    avant celui de la classe : deux agents crees dynamiquement a partir d'une
    meme classe, sous deux noms, restent deux agents.
    """
    declare = getattr(objet, "identifiant", None)
    if isinstance(declare, str) and declare.strip():
        return declare.strip()
    nom = getattr(objet, "name", None)
    if not (isinstance(nom, str) and re.fullmatch(r"[A-Za-z][A-Za-z0-9]*", nom or "")):
        nom = type(objet).__name__.lstrip("_") or "agent"
    if nom.endswith("Agent") and len(nom) > len("Agent"):
        nom = nom[: -len("Agent")]
    return re.sub(r"(?<!^)(?=[A-Z])", "_", nom).lower()


def est_un_agent(objet: Any) -> bool:
    """Vrai pour un `BaseAgent`, ou un outil qui se declare consultable."""
    from core.agent.base_agent import BaseAgent

    if inspect.isclass(objet) or inspect.ismodule(objet):
        return False
    if isinstance(objet, BaseAgent):
        return True
    run = getattr(objet, "run", None)
    return (inspect.iscoroutinefunction(run)
            and isinstance(getattr(objet, "identifiant", None), str))


@dataclass
class FicheAgent:
    """Ce que le registre sait d'un agent — lu sur l'agent, jamais suppose."""

    id: str
    name: str
    description: str
    capabilities: Tuple[str, ...]
    skills: Tuple[str, ...]
    tools: Tuple[str, ...]
    status: str
    availability: str
    memory: str
    permissions: str
    interface: str
    version: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def en_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def mots_cles(self) -> Tuple[List[str], List[str]]:
        """(mots forts, mots faibles) : l'identifiant et les competences
        declarees pesent plus que la description."""
        forts = mots(self.id.replace("_", " ")) + [m for c in self.capabilities for m in mots(c)]
        faibles = mots(self.description) + mots(self.name)
        return forts, faibles


#: Les modules dont un attribut est un OUTIL de l'agent (et non une donnee).
_MODULES_OUTILS = ("tools.", "core.connectors", "core.reasoning", "core.execution")


def fiche_de(objet: Any) -> FicheAgent:
    """La fiche d'un agent, construite par introspection."""
    from core.agent.base_agent import BaseAgent

    ident = identifiant_de(objet)
    declarees = tuple(str(c) for c in (getattr(objet, "competences", None) or ()))
    outils = sorted(
        nom for nom, valeur in vars(objet).items()
        if not nom.startswith("_") and valeur is not None
        and type(valeur).__module__.startswith(_MODULES_OUTILS))
    est_agent = isinstance(objet, BaseAgent)
    memoire = "courte (fil de conversation)" if getattr(objet, "memory", None) else "aucune"
    appelle_un_modele = getattr(objet, "provider", None) is not None
    return FicheAgent(
        id=ident,
        name=str(getattr(objet, "name", "") or type(objet).__name__),
        description=str(getattr(objet, "description", "") or "").strip(),
        capabilities=declarees,
        skills=tuple(dict.fromkeys(m for c in declarees for m in mots(c))),
        tools=tuple(outils),
        status="actif",
        availability="disponible",
        memory=memoire,
        permissions=("celles de ses connecteurs (config/permissions_services.yaml)"
                     if "registre" in vars(objet) else "aucune action externe propre"),
        interface="run(user_input, context) -> dict",
        version=str(getattr(objet, "version", "") or "1"),
        metadata={
            "classe": type(objet).__name__,
            "module": type(objet).__module__,
            "peut_consulter": est_agent,
            "appelle_un_modele": appelle_un_modele,
        },
    )


def decouvrir(espace_de_noms: Mapping[str, Any]) -> List[Any]:
    """Les agents presents dans `espace_de_noms`, sans doublon, dans l'ordre.

    Un meme objet expose sous deux noms n'est compte qu'une fois.
    """
    vus: Dict[int, Any] = {}
    for valeur in list(espace_de_noms.values()):
        if est_un_agent(valeur) and id(valeur) not in vus:
            vus[id(valeur)] = valeur
    return list(vus.values())


def classer(besoin: str, fiches: Iterable[FicheAgent]) -> List[Tuple[FicheAgent, float]]:
    """Les fiches pertinentes pour `besoin`, de la plus a la moins pertinente.

    Deterministe et sans modele. Un mot du besoin qui est un mot fort de
    l'agent (identifiant, competence declaree) compte triple d'un mot de sa
    description ; un prefixe commun de cinq lettres (« document » /
    « documents ») compte comme le mot. Chaque mot est pondere par sa RARETE
    parmi les agents presents : « analyse », que presque tous portent, ne
    departage personne, « photo » si. Zero n'est jamais rendu : un agent sans
    rapport n'est pas un candidat.
    """
    demande = set(mots(besoin))
    fiches = list(fiches)
    if not demande or not fiches:
        return []

    def correspond(mot: str, ensemble: Iterable[str]) -> bool:
        return any(mot == m or (len(mot) >= 5 and len(m) >= 5 and mot[:5] == m[:5])
                   for m in ensemble)

    vocabulaires = [fiche.mots_cles() for fiche in fiches]
    rarete = {}
    for m in demande:
        porteurs = sum(1 for forts, faibles in vocabulaires if correspond(m, forts + faibles))
        rarete[m] = math.log(1 + len(fiches) / porteurs) if porteurs else 0.0

    resultats = []
    for fiche, (forts, faibles) in zip(fiches, vocabulaires, strict=True):
        score = sum(rarete[m] * (3.0 if correspond(m, forts) else 1.0 if correspond(m, faibles) else 0.0)
                    for m in demande)
        if score > 0:
            resultats.append((fiche, round(score, 4)))
    resultats.sort(key=lambda paire: (-paire[1], paire[0].id))
    return resultats
