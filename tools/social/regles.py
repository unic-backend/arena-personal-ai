"""Les regles d'une publication, verifiables par une machine.

Ces regles viennent de `charlie947/social-media-skills` (MIT), dont les
competences `post-formatter`, `post-writer` et `hook-generator` les enoncent en
prose a l'usage d'un modele. **Une consigne n'est pas une garantie** : ce depot
l'a appris avec le controle des prix d'un devis. Elles sont donc reecrites ici
en code qui COMPTE, et le resultat d'un modele est relu avant d'etre montre.

C'est toute la difference entre « le prompt demande 20 lignes maximum » et
« la publication en fait 24, et on le dit ».

**Quatre regles sur les regles :**

1. **Chaque infraction se nomme et se situe.** « Ligne 7 : 82 caracteres, la
   limite est 55. » Un « ce n'est pas conforme » n'aide personne a corriger.

2. **Aucune correction automatique.** On mesure, on rapporte. Reecrire le texte
   du proprietaire sans le lui dire serait pire que l'infraction.

3. **Ce qui n'est pas mesurable n'est pas une regle ici.** « Vocabulaire de
   niveau 6e » et « zero jargon » restent dans l'instruction donnee au modele :
   les compter serait inventer une mesure.

4. **Les seuils sont ceux de la source**, cites, pas devines. Les changer se
   fait ici, en un seul endroit.
"""
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

#: Attribution. La source est un depot MIT, et ce module en derive.
SOURCE = "charlie947/social-media-skills (MIT) — regles de post-formatter, "\
         "post-writer et hook-generator, reecrites en verifications"

# --- Les seuils, tels que la source les enonce ---------------------------------
LIGNES_MAX = 20
MOTS_MIN = 150
MOTS_MAX = 300
CARACTERES_LIGNE = 55
#: Jusqu'a 4 lignes ont droit d'etre des mini-paragraphes.
CARACTERES_PARAGRAPHE = 110
PARAGRAPHES_MAX = 4
#: Le crochet et sa ligne de contraste.
CARACTERES_ACCROCHE = 50
CARACTERES_ACCROCHE_SEULE = 40

#: Ce que la source interdit explicitement.
TIRET_CADRATIN = re.compile(r"[—–]")
EMOJI = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF]")
#: Le seul symbole tolere, et seulement dans l'appel a l'action.
RECYCLAGE = "♻"

#: Les cinq cadres de la source, avec leurs etapes.
CADRES: Dict[str, List[str]] = {
    "PAS": ["Probleme", "Agitation", "Solution"],
    "AIDA": ["Attention", "Interet", "Desir", "Action"],
    "BAB": ["Avant", "Apres", "Pont"],
    "STAR": ["Situation", "Tache", "Action", "Resultat"],
    "SLAY": ["Histoire", "Lecon", "Conseil applicable", "Toi"],
}

#: Les six formes de crochet de la source.
FORMES_D_ACCROCHE = (
    "chiffre en tete", "contre-courant", "transformation personnelle",
    "autorite empruntee", "aveu", "choc a venir",
)


@dataclass(frozen=True)
class Infraction:
    """Une regle franchie, nommee et situee. Jamais un « non conforme » seul."""

    regle: str
    detail: str
    ligne: Optional[int] = None

    def __str__(self) -> str:
        ou = f"ligne {self.ligne} : " if self.ligne else ""
        return f"{ou}{self.detail}"

    def to_dict(self) -> Dict[str, Any]:
        return {"regle": self.regle, "detail": self.detail, "ligne": self.ligne}


@dataclass(frozen=True)
class Controle:
    """Ce que la relecture a trouve. Vide, la publication respecte les regles."""

    infractions: List[Infraction] = field(default_factory=list)
    mots: int = 0
    lignes: int = 0

    @property
    def conforme(self) -> bool:
        return not self.infractions

    def rendre(self) -> str:
        """Lisible par le proprietaire, pas par une machine."""
        if self.conforme:
            return f"Conforme : {self.lignes} ligne(s), {self.mots} mot(s)."
        lignes = [f"{len(self.infractions)} point(s) a corriger "
                  f"({self.lignes} ligne(s), {self.mots} mot(s)) :"]
        lignes += [f"- {infraction}" for infraction in self.infractions]
        return "\n".join(lignes)

    def to_dict(self) -> Dict[str, Any]:
        return {"conforme": self.conforme, "mots": self.mots, "lignes": self.lignes,
                "infractions": [i.to_dict() for i in self.infractions]}


def _lignes_utiles(texte: str) -> List[str]:
    """Les lignes qui portent quelque chose. Les blancs separent, ils ne comptent pas."""
    return [ligne.strip() for ligne in (texte or "").splitlines() if ligne.strip()]


def compter_mots(texte: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", texte or ""))


def verifier_publication(texte: str, autoriser_emoji: bool = False,
                         cta_attendu: bool = True) -> Controle:
    """Relit une publication et rend ce qui ne va pas.

    Args:
        texte: la publication a relire.
        autoriser_emoji: sa voix peut en autoriser. Par defaut, la source les
            interdit hors du symbole de partage.
        cta_attendu: la source demande un appel a l'action de cloture.

    Returns:
        Le controle. `conforme` ne veut pas dire « bonne publication » — il veut
        dire « aucune regle mesurable n'est franchie ». Le reste est un jugement,
        et il appartient au proprietaire.
    """
    lignes = _lignes_utiles(texte)
    mots = compter_mots(texte)
    infractions: List[Infraction] = []

    if not lignes:
        return Controle([Infraction("vide", "la publication est vide")], 0, 0)

    if len(lignes) > LIGNES_MAX:
        infractions.append(Infraction(
            "lignes_max", f"{len(lignes)} lignes, la limite est {LIGNES_MAX}"))
    if mots < MOTS_MIN:
        infractions.append(Infraction("mots_min", f"{mots} mots, le minimum est {MOTS_MIN}"))
    if mots > MOTS_MAX:
        infractions.append(Infraction("mots_max", f"{mots} mots, le maximum est {MOTS_MAX}"))

    # L'accroche et sa ligne de contraste sont plus courtes que le reste.
    for index, limite in ((0, CARACTERES_ACCROCHE), (1, CARACTERES_ACCROCHE)):
        if len(lignes) > index and len(lignes[index]) > limite:
            infractions.append(Infraction(
                "accroche", f"{len(lignes[index])} caracteres, la limite est {limite}",
                ligne=index + 1))

    # Le corps : une phrase par ligne, sauf quelques mini-paragraphes.
    paragraphes = 0
    for index, ligne in enumerate(lignes[2:], start=3):
        if len(ligne) <= CARACTERES_LIGNE:
            continue
        paragraphes += 1
        if len(ligne) > CARACTERES_PARAGRAPHE:
            infractions.append(Infraction(
                "ligne_trop_longue",
                f"{len(ligne)} caracteres, le maximum d'un paragraphe est "
                f"{CARACTERES_PARAGRAPHE}", ligne=index))
    if paragraphes > PARAGRAPHES_MAX:
        infractions.append(Infraction(
            "paragraphes", f"{paragraphes} mini-paragraphes, le maximum est "
                           f"{PARAGRAPHES_MAX}"))

    for index, ligne in enumerate(lignes, start=1):
        if TIRET_CADRATIN.search(ligne):
            infractions.append(Infraction("tiret_cadratin",
                                          "tiret cadratin interdit", ligne=index))
        if not autoriser_emoji:
            trouves = [c for c in EMOJI.findall(ligne) if c != RECYCLAGE]
            if trouves:
                infractions.append(Infraction(
                    "emoji", f"emoji interdit ({trouves[0]})", ligne=index))

    if cta_attendu and RECYCLAGE not in texte:
        infractions.append(Infraction(
            "cta", f"aucun appel a l'action de cloture ({RECYCLAGE} attendu)"))

    return Controle(infractions, mots, len(lignes))


def verifier_accroche(texte: str) -> Controle:
    """Relit un crochet : deux lignes, 40 caracteres chacune, pas de question.

    Les regles viennent de `hook-generator`, qui dit « 40 characters maximum per
    line. Count them. » — c'est exactement ce que fait cette fonction.
    """
    lignes = _lignes_utiles(texte)
    infractions: List[Infraction] = []

    if len(lignes) != 2:
        infractions.append(Infraction(
            "deux_lignes", f"{len(lignes)} ligne(s), un crochet en fait 2"))

    for index, ligne in enumerate(lignes, start=1):
        if len(ligne) > CARACTERES_ACCROCHE_SEULE:
            infractions.append(Infraction(
                "longueur", f"{len(ligne)} caracteres, la limite est "
                            f"{CARACTERES_ACCROCHE_SEULE}", ligne=index))
        if TIRET_CADRATIN.search(ligne):
            infractions.append(Infraction("tiret_cadratin",
                                          "tiret cadratin interdit", ligne=index))

    if lignes and lignes[0].endswith("?"):
        infractions.append(Infraction(
            "question", "la premiere ligne ne pose pas de question", ligne=1))

    return Controle(infractions, compter_mots(texte), len(lignes))


def instruction_de_cadre(cadre: str) -> str:
    """L'ossature d'un cadre, a poser dans l'instruction du modele.

    Un cadre inconnu rend une chaine vide : on n'invente pas une structure.
    """
    etapes = CADRES.get((cadre or "").upper())
    if not etapes:
        return ""
    return " -> ".join(etapes)
