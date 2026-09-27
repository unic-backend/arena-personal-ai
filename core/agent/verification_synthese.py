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


# --- Une reponse sourcee, confrontee aux sources qu'elle a recues (DEC-0150) ---
#
# La synthese d'une recherche web promet de s'en tenir a ses sources. Nuit du
# 26 au 27/09/2026, six PR ont resserre ce qui ENTRE dans la synthese (sujet,
# evenement, extraction) ; rien ne relisait ce qui en SORT. Un modele qui
# « complete » une liste de buteurs avec un nom de memoire passait tel quel.
# Ce controle compare la reponse au texte exact que le modele a recu : un nom
# propre ou un chiffre qui n'y figure pas n'a pas pu venir de ces sources.

#: Mots qui ouvrent une phrase francaise sans etre un nom propre.
_DEBUTS_DE_PHRASE = frozenset(normaliser(m) for m in (
    "le la les l un une des du de d en au aux ce cet cette ces c il elle ils elles on nous "
    "je tu vous oui non aucun aucune pour par sur dans avec sans mais donc ainsi cependant "
    "toutefois neanmoins enfin puis ensuite alors voici voila selon source sources reponse "
    "note attention remarque resultat score buteur buteurs match date lieu quel quelle quels "
    "quelles qui que quoi comment pourquoi quand ou apres avant lors pendant depuis malgre "
    "grace contre entre chaque tous toutes tout plusieurs certains certaines seul seule meme "
    "cela ceci ca est sa son ses leur leurs notre nos votre vos mon ma mes premier premiere "
    "deuxieme troisieme dernier derniere derniers dernieres autre autres aussi encore deja "
    "malheureusement heureusement actuellement recemment officiellement finalement "
    "concernant quant pas plus moins tres bien car si comme lorsque parce puisque d'apres "
    "d’apres a y sont etait ont avait sera il y en resume conclusion information "
    "informations detail details verification").split())

_MOT_CAPITALISE = re.compile(r"(?<![\w'’])([A-ZÀ-ÖØ-Þ][\wÀ-ÿ'’-]{2,})")
_FIN_DE_PHRASE = re.compile(r"(?:^|[.!?]\s+|\n\s*(?:[-*•>|]\s*|\d+[.)]\s*|#+\s*)*)$")
_SCORE = re.compile(r"(?<![\d,])(\d{1,2})\s*(?:[-–—:]|\bà\b)\s*(\d{1,2})(?![\d,])")
_NOMBRE = re.compile(rf"(?<![\d,])\d{{1,3}}(?:[{_SEPARATEURS}]\d{{3}})+(?!\d)|(?<![\d,])\d+(?!\d)")
_CITATION = re.compile(r"\[\d+(?:\s*[,-]\s*\d+)*\]")
#: Au-dela, les elements sans source sont resumes.
ELEMENTS_AFFICHES = 10


def _nombres(texte: str) -> set:
    valeurs = set()
    for brut in _NOMBRE.findall(_DATE.sub(lambda m: " ".join(re.split(r"[/.-]", m.group(0))), texte)):
        try:
            valeurs.add(int(re.sub(rf"[{_SEPARATEURS}]", "", brut)))
        except ValueError:
            continue
    return valeurs


def _scores(texte: str) -> set:
    return {tuple(sorted((int(a), int(b)))) for a, b in _SCORE.findall(texte)}


def _mots_des_sources(texte: str) -> set:
    return set(re.findall(r"[a-z0-9]+", normaliser(texte)))


def _nom_connu(nom: str, mots_sources: set) -> bool:
    """Le nom figure dans les sources — ou sa forme dans une autre langue :
    « Seville » pour « Sevilla », « Barcelone » pour « Barcelona » partagent
    tout sauf leur terminaison."""
    forme = normaliser(nom)
    parties = [p for p in re.findall(r"[a-z0-9]+", forme) if len(p) >= 3]
    if not parties:
        return True
    for partie in parties:
        if partie in mots_sources:
            continue
        prefixe = max(5, len(partie) - 2)
        if len(partie) >= 5 and any(
                len(mot) >= 5 and mot[:prefixe] == partie[:prefixe] for mot in mots_sources):
            continue
        return False
    return True


def elements_sans_source(reponse: str, sources: Iterable[str]) -> List[str]:
    """Les noms propres et les chiffres de `reponse` absents de `sources`.

    `sources` doit etre ce que le modele a RECU (question et extraits), pas
    les pages entieres : un nom present dans une page mais absent de
    l'extrait n'a pas pu venir de l'extrait.

    Etroit par construction : un mot capitalise en debut de phrase n'est
    compte que s'il n'est pas un mot courant ; un chiffre isole d'un seul
    signe est ignore (hors score) ; les numeros de citation [1] aussi.
    """
    corpus = "\n".join(str(s or "") for s in sources)
    mots_sources = _mots_des_sources(corpus)
    nombres_sources = _nombres(corpus)
    scores_sources = _scores(corpus)
    texte = _CITATION.sub(" ", str(reponse or "")).replace("**", "").replace("__", "")

    manquants: List[str] = []

    def signaler(element: str) -> None:
        if element not in manquants:
            manquants.append(element)

    for trouve in _MOT_CAPITALISE.finditer(texte):
        nom = trouve.group(1).strip("'’-")
        en_tete = bool(_FIN_DE_PHRASE.search(texte[:trouve.start()]))
        if en_tete and normaliser(nom).strip("'’") in _DEBUTS_DE_PHRASE:
            continue
        if normaliser(nom).split("'")[0] in _DEBUTS_DE_PHRASE and en_tete:
            continue
        if not _nom_connu(nom, mots_sources):
            signaler(nom)

    for a, b in _SCORE.findall(texte):
        paire = tuple(sorted((int(a), int(b))))
        if paire not in scores_sources:
            signaler(f"{a}-{b}")
    sans_scores = _SCORE.sub(" ", texte)
    for valeur in sorted(_nombres(sans_scores), key=lambda v: sans_scores.find(str(v))):
        if valeur >= 10 and valeur not in nombres_sources:
            signaler(str(valeur))
    return manquants


def avertissement_sources(manquants: List[str]) -> str:
    """Le bloc ajoute sous une reponse sourcee ; vide si tout a une source."""
    if not manquants:
        return ""
    montres = manquants[:ELEMENTS_AFFICHES]
    reste = len(manquants) - len(montres)
    return ("---\n**Verification automatique** : ces elements de la reponse ne "
            f"figurent dans aucune source lue : {', '.join(montres)}"
            + (f" et {reste} autre(s)" if reste > 0 else "")
            + ". Ne les tiens pas pour acquis.")
