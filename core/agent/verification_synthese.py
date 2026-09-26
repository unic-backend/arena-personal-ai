"""Ce qu'une synthese d'equipe affirme, confronte a ce qui a ete dit (DEC-0147).

La synthese d'une table ronde ou d'un projet est ecrite par le modele du lead.
Mesure du 26/09/2026, sur une table ronde reelle du proprietaire (« budget des
cloisons », participants plaquiste et finance) : la synthese attribuait une
position a « recherche », absent de la table, et posait un exemple chiffre
calcule de tete — 417 plaques pour 250 m2 (250 / 0,6) quand les ratios du
proprietaire en donnent 241, un TTC faux de 6 782 FCFA, une marge degressive
et une majoration de 5 % que personne n'avait proposees.

La consigne de synthese interdit desormais tout cela. Une consigne n'est pas
une garantie : ce module relit la synthese et SIGNALE, sans rien corriger —
meme discipline que `agents/plaquiste/controle_prix.py`. Deux controles,
volontairement etroits (un controle qui crie a tort est un controle qu'on
eteint) :

1. **Agents cites absents** : un nom d'agent du registre ecrit comme un nom
   (seul entre parenthèses, en gras, dans une liste « a / b ») alors qu'il n'a
   ni participe ni recu de tache pendant cette demande.
2. **Chiffres sans source** : un montant (>= 100) ou un pourcentage que
   personne n'a donne — ni l'enonce, ni un participant. Un calcul fait par la
   synthese elle-meme y tombe aussi : il n'est pas faux pour autant, il n'est
   pas VERIFIE, et c'est ce qui est dit.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Set

from core.agent.decouverte import normaliser

# Separateurs de milliers admis : espace, espaces insecables (U+00A0, U+202F),
# espace fine (U+2009) et point — la meme convention que le controle des prix
# du plaquiste, pour qu'un « 4 500 » ecrit par un modele soit bien 4500.
_SEPARATEURS = "    ."
_MONTANT = re.compile(rf"(?<![\d,])\d{{1,3}}(?:[{_SEPARATEURS}]\d{{3}})+(?![\d])|(?<![\d,.])\d{{3,}}(?![\d])")
_POURCENTAGE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:%|pour\s?cent)", re.IGNORECASE)
# Une date n'est pas un chiffre du debat : « 26/09/2026 » ne doit rien signaler.
_DATE = re.compile(r"\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b")
# Ce qui peut porter un NOM : le contenu d'une parenthese ou d'un gras.
_PORTEURS_DE_NOM = re.compile(r"\(([^()\n]{1,80})\)|\*\*([^*\n]{1,80})\*\*")
_SEPARATEURS_DE_NOMS = re.compile(r"\s*(?:/|,|&|\bet\b|\+)\s*")

#: Montants en dessous : quantites, numeros de section, dimensions.
MONTANT_MINIMUM = 100
#: Au-dela, la liste est resumee : le signal doit rester lisible.
CHIFFRES_AFFICHES = 12


@dataclass
class Verification:
    """Ce que la synthese affirme sans l'avoir recu du debat."""

    agents_absents: List[str] = field(default_factory=list)
    chiffres_non_verifies: List[str] = field(default_factory=list)

    @property
    def propre(self) -> bool:
        return not self.agents_absents and not self.chiffres_non_verifies

    def en_dict(self) -> Dict[str, Any]:
        return {"agents_absents": list(self.agents_absents),
                "chiffres_non_verifies": list(self.chiffres_non_verifies)}

    def avertissement(self) -> str:
        """Le bloc ajoute sous la synthese ; vide si rien n'est a signaler."""
        if self.propre:
            return ""
        lignes = ["---", "**Verification automatique de la synthese**"]
        if self.agents_absents:
            lignes.append(
                "- Agents cites qui n'ont pas participe : "
                f"{', '.join(self.agents_absents)}. Ce qui leur est attribue n'a pas "
                "ete dit pendant ce travail.")
        if self.chiffres_non_verifies:
            montres = self.chiffres_non_verifies[:CHIFFRES_AFFICHES]
            reste = len(self.chiffres_non_verifies) - len(montres)
            lignes.append(
                "- Chiffres qu'aucun participant n'a donnes (ajoutes ou calcules par la "
                f"synthese), a verifier avant tout usage : {', '.join(montres)}"
                + (f" et {reste} autre(s)" if reste > 0 else "") + ".")
        return "\n".join(lignes)


def _montants(texte: str) -> Dict[int, str]:
    """{valeur: forme ecrite} des montants du texte, dates exclues."""
    trouves: Dict[int, str] = {}
    for brut in _MONTANT.findall(_DATE.sub(" ", texte)):
        valeur = int(re.sub(rf"[{_SEPARATEURS}]", "", brut))
        if valeur >= MONTANT_MINIMUM:
            trouves.setdefault(valeur, brut.strip())
    return trouves


def _pourcentages(texte: str) -> Dict[float, str]:
    return {float(brut.replace(",", ".")): f"{brut} %" for brut in _POURCENTAGE.findall(texte)}


def _noms_ecrits(texte: str) -> Set[str]:
    """Les fragments ecrits comme des noms : seuls dans une parenthese ou un
    gras, ou elements d'une liste « a / b » a cet endroit."""
    noms = set()
    for entre_parentheses, en_gras in _PORTEURS_DE_NOM.findall(texte):
        for fragment in _SEPARATEURS_DE_NOMS.split(entre_parentheses or en_gras):
            fragment = normaliser(fragment).strip(" .:;-")
            if fragment:
                noms.add(fragment)
    return noms


def _appellations(registre: Any, cle: str) -> Set[str]:
    """Les formes sous lesquelles un agent peut etre nomme : sa cle, et son
    nom d'instance avec ou sans le suffixe « Agent »."""
    formes = {normaliser(cle), normaliser(cle.replace("_", " "))}
    fiche = registre.fiche(cle) if hasattr(registre, "fiche") else None
    nom = normaliser(getattr(fiche, "name", "") or "")
    if nom:
        formes |= {nom, re.sub(r"\s*agent$", "", nom)}
    return {f for f in formes if f}


def verifier_synthese(synthese: str, sources: Iterable[str], registre: Any,
                      presents: Iterable[str]) -> Verification:
    """Confronte `synthese` a ce qui a ete dit (`sources`) et a qui l'a dit.

    `presents` : les cles des agents qui ont reellement travaille pendant la
    demande — participants, lead, et tout agent consulte en chemin.
    """
    verification = Verification()
    presents = set(presents)

    noms = _noms_ecrits(synthese)
    for cle in registre.espaces():
        if cle not in presents and noms & _appellations(registre, cle):
            verification.agents_absents.append(cle)

    source = "\n".join(str(s or "") for s in sources)
    connus = set(_montants(source))
    for valeur, forme in _montants(synthese).items():
        if valeur not in connus:
            verification.chiffres_non_verifies.append(forme)
    taux_connus = set(_pourcentages(source))
    for valeur, forme in _pourcentages(synthese).items():
        if valeur not in taux_connus:
            verification.chiffres_non_verifies.append(forme)
    return verification


def agents_ayant_travaille(espace: Any, root_task_id: str) -> Set[str]:
    """Les agents qui ont recu une tache sous cette racine, lus dans l'espace
    de travail — un agent consulte en chemin par un participant y figure."""
    return {t.recipient for t in espace.taches.values() if t.root_task_id == root_task_id}
