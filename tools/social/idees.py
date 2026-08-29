"""Des idees de publication : ses piliers croises avec des formats.

`content-matrix` (source : `charlie947/social-media-skills`, MIT) annonce
« 32+ post ideas from pillars x formats ». C'est une combinatoire, pas une
generation : elle se calcule, donc elle se calcule ici — sans appeler un modele,
sans rien inventer, et elle rend exactement le nombre qu'elle promet.

**Trois regles :**

1. **Aucun pilier n'est invente.** Les piliers viennent de sa voix. Sans
   piliers, aucune idee : on demande.
2. **Le compte est reel.** `len(idees)` est le nombre d'idees rendues, pas une
   promesse arrondie.
3. **Ce qui a deja ete publie ne revient pas.** Un sujet deja traite est ecarte,
   et le dire est plus utile que de le proposer une seconde fois.
"""
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Sequence

#: Les formats, tires des cadres de la source et de ce qu'un artisan peut
#: reellement raconter. Chacun porte la question a laquelle la publication repond.
FORMATS: Dict[str, str] = {
    "chantier": "Ce qu'un chantier precis a appris",
    "erreur": "Une erreur commise, et ce qu'elle a coute",
    "avant_apres": "L'etat de depart, l'etat d'arrivee",
    "idee_recue": "Ce que les gens croient, et pourquoi c'est faux",
    "methode": "Comment on s'y prend, etape par etape",
    "chiffre": "Un chiffre reel, et ce qu'il dit",
    "coulisses": "Ce que le client ne voit pas",
    "question": "Une question qu'on lui pose souvent",
}


@dataclass(frozen=True)
class Idee:
    """Une idee : un pilier, un format, et la phrase qui les croise."""

    pilier: str
    format: str
    angle: str

    @property
    def sujet(self) -> str:
        return f"{self.angle} — {self.pilier}"

    def to_dict(self) -> Dict[str, Any]:
        return {"pilier": self.pilier, "format": self.format,
                "angle": self.angle, "sujet": self.sujet}


def _normaliser(texte: str) -> str:
    return " ".join((texte or "").lower().split())


def matrice(piliers: Sequence[str],
            deja_publies: Iterable[str] = (),
            formats: Dict[str, str] = FORMATS) -> List[Idee]:
    """Croise ses piliers avec les formats. Rend ce qui reste a ecrire.

    Args:
        piliers: ses sujets, tires de sa voix. Vides, la matrice est vide.
        deja_publies: les sujets deja traites — ils ne reviennent pas.

    Returns:
        Une idee par couple (pilier, format), moins ce qui a deja ete publie.
    """
    ecartes = {_normaliser(sujet) for sujet in deja_publies}
    idees: List[Idee] = []
    for pilier in piliers:
        if not (pilier or "").strip():
            continue
        for nom, angle in formats.items():
            idee = Idee(pilier=pilier.strip(), format=nom, angle=angle)
            if any(_normaliser(pilier) in vu and nom in vu for vu in ecartes):
                continue
            idees.append(idee)
    return idees


def resume(idees: Sequence[Idee]) -> Dict[str, Any]:
    """Le compte reel, et la repartition. Aucun arrondi."""
    par_pilier: Dict[str, int] = {}
    for idee in idees:
        par_pilier[idee.pilier] = par_pilier.get(idee.pilier, 0) + 1
    return {"total": len(idees), "par_pilier": par_pilier,
            "formats": sorted({idee.format for idee in idees})}
