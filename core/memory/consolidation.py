"""Consolider la memoire : dire une chose une fois, sans en perdre aucune.

Retenir deux fois la meme phrase produit deux souvenirs. Le prompt les porte
tous les deux, et ARENA se repete. La consolidation regroupe ce qui est
identique, compte les occurrences, et rend un resume court.

**Elle ne supprime rien.** Un doublon a sa propre date et sa propre source ;
les effacer pour gagner deux lignes de prompt detruit une information qu'on ne
saura plus reconstituer. Le groupe garde tout, le rendu montre une ligne.

**Quatre regles :**

1. **Un groupe ne traverse jamais une nature.** « Il prefere le BA13 » dit par
   le proprietaire et deduit par ARENA sont deux souvenirs, pas un. Regrouper
   les deux ferait d'une supposition un fait par simple ressemblance — ce que
   `confirmer()` est le seul chemin autorise a faire.

2. **Un groupe ne traverse ni le type, ni le projet, ni la source.** Deux
   chantiers peuvent porter la meme phrase sans porter le meme sens, et deux
   origines differentes sont deux preuves differentes.

3. **L'importance d'un groupe est le maximum de celles qu'il contient**, jamais
   une valeur calculee. Repeter une chose la rend plus frequente, pas plus
   vraie : le nombre d'occurrences le dit, l'importance ne bouge pas.

4. **Le budget est une limite dure**, comme a la recuperation. Un groupe de plus
   qui ferait deborder n'est pas tronque : il n'est pas rendu.
"""
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from core.memory.personnelle import MemoirePersonnelle, Nature, Souvenir, TypeSouvenir
from core.memory.recuperation import normaliser, rendre_ligne

logger = logging.getLogger("usman.memoire.consolidation")

#: Budget par defaut d'un resume. Plus large qu'une recuperation : un resume
#: repond a « qu'est-ce que tu sais de ce chantier », pas a une question precise.
BUDGET_RESUME = 3000

#: L'ordre des sections. Les faits d'abord, les suppositions apres, et jamais
#: melanges : c'est l'ordre de lecture qui protege le lecteur.
ORDRE_NATURES = [
    Nature.FAIT,
    Nature.PREFERENCE,
    Nature.INFERENCE,
    Nature.CONTEXTE_TEMPORAIRE,
]

TITRES = {
    Nature.FAIT: "Faits",
    Nature.PREFERENCE: "Preferences",
    Nature.INFERENCE: "Suppositions (non confirmees)",
    Nature.CONTEXTE_TEMPORAIRE: "Contexte temporaire",
}


def empreinte(contenu: str) -> str:
    """La forme comparable d'un contenu : minuscules, sans accents ni ponctuation.

    « Plafond BA13 de 40 m2. » et « plafond ba13 de 40 m2 » sont la meme phrase.
    « Plafond BA13 de 41 m2 » ne l'est pas — les chiffres sont gardes.
    """
    return " ".join(re.findall(r"[a-z0-9]+", normaliser(contenu)))


#: Ce qui fait qu'on parle du meme souvenir. La nature en fait partie, et c'est
#: la clause qui empeche une supposition de rejoindre un fait.
Cle = Tuple[str, str, str, str, str]


def cle_de(souvenir: Souvenir) -> Cle:
    return (
        souvenir.nature.value,
        souvenir.type.value,
        souvenir.projet or "",
        souvenir.source,
        empreinte(souvenir.contenu),
    )


@dataclass(frozen=True)
class Groupe:
    """Un souvenir et ses doublons exacts, rassembles sans etre effaces."""

    representant: Souvenir
    doublons: List[Souvenir] = field(default_factory=list)

    @property
    def occurrences(self) -> int:
        """Le total reellement compte, y compris les reconfirmations."""
        return self.representant.occurrences + sum(d.occurrences for d in self.doublons)

    @property
    def importance(self) -> float:
        """Le maximum du groupe. Jamais une moyenne, jamais une prime a la repetition."""
        return max([self.representant.importance] + [d.importance for d in self.doublons])

    @property
    def nature(self) -> Nature:
        return self.representant.nature

    def rendre(self) -> str:
        """Une ligne. Le compte n'apparait que s'il y a vraiment eu repetition."""
        ligne = rendre_ligne(self.representant)
        return f"{ligne} (vu {self.occurrences} fois)" if self.occurrences > 1 else ligne


def grouper(souvenirs: List[Souvenir]) -> List[Groupe]:
    """Rassemble les souvenirs identiques, en gardant le plus ancien pour representant.

    Le plus ancien, parce que c'est lui qui porte la premiere date : un souvenir
    consolide ne doit pas paraitre plus recent qu'il ne l'est.
    """
    paquets: Dict[Cle, List[Souvenir]] = {}
    for souvenir in souvenirs:
        paquets.setdefault(cle_de(souvenir), []).append(souvenir)

    groupes: List[Groupe] = []
    for membres in paquets.values():
        ordonnes = sorted(membres, key=lambda s: s.cree_le or "")
        groupes.append(Groupe(representant=ordonnes[0], doublons=ordonnes[1:]))
    return groupes


@dataclass(frozen=True)
class Resume:
    """Ce que la memoire sait d'un projet, dit une fois par chose."""

    projet: Optional[str]
    groupes: List[Groupe]
    lus: int
    ecartes_budget: int = 0

    @property
    def doublons_rassembles(self) -> int:
        """Combien de lignes le regroupement a evite au prompt."""
        return sum(len(groupe.doublons) for groupe in self.groupes)

    def par_nature(self, nature: Nature) -> List[Groupe]:
        return [groupe for groupe in self.groupes if groupe.nature is nature]

    def rendre(self) -> str:
        """Le bloc lisible. Vide, il le dit — il n'invente pas une phrase."""
        if not self.groupes:
            ou = f" sur {self.projet}" if self.projet else ""
            return f"Rien en memoire{ou}."

        lignes: List[str] = []
        for nature in ORDRE_NATURES:
            groupes = self.par_nature(nature)
            if not groupes:
                continue
            lignes.append(f"{TITRES[nature]} :")
            lignes += [groupe.rendre() for groupe in groupes]
            lignes.append("")
        return "\n".join(lignes).strip()


def taille(groupes: List[Groupe]) -> int:
    """Le cout reel en caracteres des lignes rendues."""
    return sum(len(groupe.rendre()) + 1 for groupe in groupes)


def resumer(
    memoire: MemoirePersonnelle,
    projet: Optional[str] = None,
    type: Optional[TypeSouvenir] = None,
    budget_caracteres: int = BUDGET_RESUME,
    limite_lecture: int = 500,
    maintenant: Optional[datetime] = None,
) -> Resume:
    """Resume ce que la memoire sait, sans repetition et sans melange de natures.

    Args:
        memoire: la memoire a resumer.
        projet: restreint a un projet. `None` prend tout.
        type: restreint a un type de souvenir.
        budget_caracteres: taille maximale du rendu. **Limite dure.**
        limite_lecture: combien de souvenirs sont lus au maximum.
        maintenant: pour que les tests fixent l'heure.

    Returns:
        Le resume. Les contextes temporaires perimes n'y sont pas : `souvenirs()`
        les ecarte deja, et un contexte perime affirme avec l'aplomb d'un fait
        est exactement ce qu'on ne veut pas mettre dans un prompt.
    """
    lus = memoire.souvenirs(projet=projet, type=type, limite=limite_lecture)
    if maintenant is not None:
        lus = [souvenir for souvenir in lus if not souvenir.est_perime(maintenant)]

    groupes = grouper(lus)
    # L'ordre du rendu vient des sections ; a l'interieur, l'importance decide.
    groupes.sort(key=lambda groupe: (groupe.importance, groupe.occurrences), reverse=True)

    retenus: List[Groupe] = []
    ecartes = 0
    total = 0
    for groupe in groupes:
        cout = len(groupe.rendre()) + 1
        if total + cout > budget_caracteres:
            ecartes += 1
            continue  # jamais tronque : pas rendu
        retenus.append(groupe)
        total += cout

    logger.debug("Resume : %s souvenir(s) lus, %s groupe(s) rendus, %s ecarte(s), %s caracteres.",
                 len(lus), len(retenus), ecartes, total)
    return Resume(projet=projet, groupes=retenus, lus=len(lus), ecartes_budget=ecartes)
