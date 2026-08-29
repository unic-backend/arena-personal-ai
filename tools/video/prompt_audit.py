"""Audit structurel d'un prompt image/video, avant de le confier a un generateur.

Une generation WanGP occupe la carte graphique plusieurs minutes. Un prompt mal
forme — sans sujet, sans duree, avec une camera verrouillee ET en mouvement
dans la meme phrase — la depense pour un resultat qu'il faudra recommencer.
Cet audit est **structurel et deterministe** : il verifie que les elements
attendus sont presents, il ne juge jamais si le resultat sera beau. Aucun
reseau, aucune ecriture, aucun modele appele — une regex peut tourner sur
cette machine comme sur la sienne.

Methode et liste de controles extraites de `Hell-Grind-AIGC-Skill`
(github.com/renmu2017/Hell-Grind-AIGC-Skill, MIT, Copyright (c) 2026
renmu2017) — un outil du meme nom (`audit_prompt.py`) y fait exactement ce
controle, en chinois/anglais, pour des prompts Codex. Les motifs sont
retraduits en francais/anglais ici (les generateurs d'image/video attendent
en general un prompt en anglais, mais Ousmane decrit souvent une scene en
francais) ; les categories de controle, les codes d'erreur et le bareme de
score sont conserves tels quels — c'est la partie deja eprouvee.

Voir DEC-0015 (`docs/DECISIONS.md`) pour ce qui a ete integre de ce depot et
ce qui ne l'a pas ete.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Pattern

# ─── Motifs : francais + anglais, un generateur video peut recevoir l'un ou l'autre ───

MOTIF_SUJET = re.compile(
    r"\b(?:sujet|personnage|personne|homme|femme|garçon|fille|foule|créature|"
    r"objet|produit|environnement|scène|"
    r"subject|character|person|people|man|woman|boy|girl|creature|monster|"
    r"prop|product|object|environment|scene)\b",
    re.IGNORECASE,
)
MOTIF_DUREE = re.compile(
    r"(?:durée totale|durée|duration)?\s*\d+(?:[.,]\d+)?\s*(?:secondes?|sec\b|s\b)",
    re.IGNORECASE,
)
MOTIF_CAMERA = re.compile(
    r"\b(?:caméra|cadrage|plan|objectif|zoom|travelling|panoramique|inclinaison|"
    r"grue|"
    r"camera|shot|framing|lens|dolly|push|pull|orbit|track|pan|tilt|crane|"
    r"handheld)\b",
    re.IGNORECASE,
)
MOTIF_FIN_CAMERA = re.compile(
    r"camera_end|cadrage final|plan final|fin sur|se termine sur|s'arrête sur|"
    r"\b(?:end frame|final frame|ends? (?:on|with|at)|settles? (?:on|at)|"
    r"finishes? (?:on|at))\b",
    re.IGNORECASE,
)
MOTIF_AUDIO = re.compile(
    r"\b(?:audio|dialogue|voix|musique|silence|ambiance|bruitage|bruit|"
    r"bande[- ]son(?:ore)?|sous-titre|"
    r"sound|voice|music|score|subtitle|silent|ambience|foley)\b",
    re.IGNORECASE,
)
MOTIF_QUANTITE = re.compile(
    r"\bexactement\b|\bprécisément\b|\bseulement\b|un seul|une seule|"
    r"\b(?:exactly|only|one|two|three|four|five)\b|\b\d+\s*(?:personnes?|"
    r"individus?)",
    re.IGNORECASE,
)
MOTIF_REFERENCE = re.compile(
    r"référence|image[_ -]?\d+|<<<[^>]+>>>|reference", re.IGNORECASE
)
MOTIF_PORTEE_REFERENCE = re.compile(
    r"h[ée]rite de|h[ée]rite uniquement|exclut|inherit|exclude|only inherit",
    re.IGNORECASE,
)
MOTIF_PLATEFORME = re.compile(
    r"adaptation plateforme|provider|model|seed|steps?|cfg|sampler|"
    r"intensité de mouvement",
    re.IGNORECASE,
)
MOTIF_LUMIERE = re.compile(
    r"lumière|éclairage|exposition|couleur|matière|météo|"
    r"lighting|exposure|color|material|weather",
    re.IGNORECASE,
)
MOTIF_ACTION = re.compile(
    r"action|regard|respiration|équilibre|contact|réaction|"
    r"eyeline|breath|weight|reaction",
    re.IGNORECASE,
)
MOTIF_CONTINUITE = re.compile(
    r"continuity|continuité|doit rester|change ici|ne doit pas apparaître|"
    r"must_hold|changes_here|must_not_appear",
    re.IGNORECASE,
)
MOTIF_IMMOBILE = re.compile(
    r"\bimmobile\b|ne bouge pas|position fixe|"
    r"\b(?:stand|remain|stay) completely still\b|\bno movement\b",
    re.IGNORECASE,
)
MOTIF_SUJET_EN_MOUVEMENT = re.compile(
    r"court sans arrêt|continue de courir|marche sans arrêt|se déplace sans "
    r"cesse|"
    r"\b(?:keeps? |continues? |constantly )?(?:running|walking|moving)\b",
    re.IGNORECASE,
)
MOTIF_CAMERA_VERROUILLEE = re.compile(
    r"cam[ée]ra verrouill[ée]e|cam[ée]ra fixe|position fixe de cam[ée]ra|"
    r"\blocked[- ]?off\b|\bstatic camera\b",
    re.IGNORECASE,
)
MOUVEMENTS_CAMERA: Dict[str, Pattern[str]] = {
    "orbite": re.compile(r"orbite|orbit", re.IGNORECASE),
    "avance": re.compile(r"avance vers|push(?:es)? in|dolly in", re.IGNORECASE),
    "recule": re.compile(r"recule|pull(?:s)? out|dolly out", re.IGNORECASE),
    "suit": re.compile(r"suit le sujet|track(?:s|ing)?|follow(?:s|ing)?", re.IGNORECASE),
    "panoramique": re.compile(r"panoramique|\bpans?\b|\bpanning\b", re.IGNORECASE),
    "inclinaison": re.compile(r"inclinaison|\btilts?\b|\btilting\b", re.IGNORECASE),
    "grue": re.compile(r"mouvement de grue|\bcrane\b|\bboom\b", re.IGNORECASE),
}
MOTIF_DUREE_TOTALE = re.compile(
    r"(?:dur[ée]e totale|dur[ée]e|duration)\s*[:=]?\s*(\d+(?:[.,]\d+)?)\s*"
    r"(?:secondes?|sec\b|s\b)",
    re.IGNORECASE,
)
MOTIF_PLAGE_TEMPORELLE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*[-–—]\s*(\d+(?:[.,]\d+)?)\s*(?:secondes?|sec\b|s\b)",
    re.IGNORECASE,
)
MOTIF_PARAMETRE_PRIVE = re.compile(
    r"\bseed\b|\bsteps?\b|\bcfg\b|\bsampler\b", re.IGNORECASE
)
MOTIF_ADAPTATEUR = re.compile(
    r"adaptation plateforme|provider adapter|adapter layer", re.IGNORECASE
)
MOTIF_DIALOGUE_EXACT = re.compile(
    r"dialogue exact|réplique exacte|dit\s*[«\"']|"
    r"exact (?:dialogue|line)|says?\s*[\"']",
    re.IGNORECASE,
)
MOTIF_LIMITE_DIALOGUE_VISUEL = re.compile(
    r"dialogue non visualisé|uniquement sonore|sans flashback|"
    r"dialogue.{0,20}(?:audio only|not visualized)|no flashback",
    re.IGNORECASE,
)
MOTIF_ABSTRAIT = re.compile(
    r"\b(?:haut de gamme|saisissant|cinématographique|épique|somptueux|"
    r"onirique|premium|cinematic|epic|stunning)\b",
    re.IGNORECASE,
)
MOTIF_CONCRET = re.compile(
    r"sujet|personnage|scène|accessoire|action|caméra|lumière|matière|"
    r"couleur|"
    r"subject|character|scene|prop|action|camera|light|material|color",
    re.IGNORECASE,
)
GROUPES_NEGATION_REDONDANTE: List[Pattern[str]] = [
    re.compile(r"sans musique|pas de musique|no score|no music", re.IGNORECASE),
    re.compile(r"sans personnage supplémentaire|n'ajoute personne|"
               r"no extra (?:people|characters)", re.IGNORECASE),
    re.compile(r"sans sous-titre|pas de sous-titre|no subtitles?", re.IGNORECASE),
    re.compile(r"sans tremblement|pas de tremblement|no jitter|no shake",
               re.IGNORECASE),
]

MODULES: Dict[str, Pattern[str]] = {
    "sujet": MOTIF_SUJET,
    "quantite": MOTIF_QUANTITE,
    "duree": MOTIF_DUREE,
    "camera": MOTIF_CAMERA,
    "fin_camera": MOTIF_FIN_CAMERA,
    "audio": MOTIF_AUDIO,
    "reference": MOTIF_REFERENCE,
    "portee_reference": MOTIF_PORTEE_REFERENCE,
    "lumiere_couleur_matiere": MOTIF_LUMIERE,
    "action_jeu": MOTIF_ACTION,
    "continuite": MOTIF_CONTINUITE,
    "adaptation_plateforme": MOTIF_PLATEFORME,
}

SUPPORTS_VALIDES = ("image", "video")


@dataclass(frozen=True)
class ProblemePrompt:
    """Un ecart structurel, avec de quoi le corriger — jamais un jugement de gout."""

    code: str
    gravite: str  # "erreur" | "avertissement"
    ligne: Optional[int]
    message: str
    correction: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AuditPrompt:
    """Le resultat d'un audit — `pret` conditionne l'envoi au generateur."""

    pret: bool
    score: int
    support: str
    problemes: List[ProblemePrompt] = field(default_factory=list)
    modules_detectes: List[str] = field(default_factory=list)
    hypotheses: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pret": self.pret,
            "score": self.score,
            "support": self.support,
            "problemes": [p.to_dict() for p in self.problemes],
            "modules_detectes": self.modules_detectes,
            "hypotheses": self.hypotheses,
        }


def _ligne_de(texte: str, motif: Pattern[str]) -> Optional[int]:
    for numero, ligne in enumerate(texte.splitlines(), start=1):
        if motif.search(ligne):
            return numero
    return None


def _modules_detectes(texte: str) -> List[str]:
    return [nom for nom, motif in MODULES.items() if motif.search(texte)]


def auditer_prompt(texte: str, support: str) -> AuditPrompt:
    """Audite un prompt image ou video. Ne modifie rien, n'appelle rien.

    Args:
        texte: le prompt tel qu'il serait envoye au generateur.
        support: `"image"` ou `"video"` — le controle de duree/audio/fin de
            camera ne s'applique qu'a `"video"`.

    Returns:
        `AuditPrompt`, avec `pret=True` seulement si aucune erreur bloquante
        n'a ete trouvee. Les avertissements n'empechent pas l'envoi.
    """
    if support not in SUPPORTS_VALIDES:
        raise ValueError(f"support inconnu : {support!r} (attendu : {SUPPORTS_VALIDES})")

    probleme: List[ProblemePrompt] = []
    hypotheses: List[str] = []
    stripped = (texte or "").strip()

    if not stripped:
        probleme.append(ProblemePrompt(
            "P-VIDE", "erreur", None,
            "Le prompt est vide.",
            "Decris l'intention et au moins un sujet ou environnement visible."))
    else:
        if not MOTIF_SUJET.search(stripped):
            probleme.append(ProblemePrompt(
                "P-SUJET-MANQUANT", "erreur", None,
                "Aucun sujet, objet ou environnement identifiable.",
                "Nomme ce qui doit apparaitre, et sa quantite exacte si elle compte."))
        if support == "video":
            if not MOTIF_DUREE.search(stripped):
                probleme.append(ProblemePrompt(
                    "P-DUREE-MANQUANTE", "erreur", None,
                    "La duree de la video n'est pas explicite.",
                    "Indique la duree totale en secondes et garde chaque temps fort dedans."))
            if not MOTIF_FIN_CAMERA.search(stripped):
                probleme.append(ProblemePrompt(
                    "P-FIN-CAMERA-MANQUANTE", "erreur",
                    _ligne_de(stripped, MOTIF_CAMERA),
                    "Aucun etat final de camera ou de cadrage explicite.",
                    "Ajoute un cadrage de fin ou une image finale clairement observable."))
            if not MOTIF_AUDIO.search(stripped):
                probleme.append(ProblemePrompt(
                    "P-AUDIO-MANQUANT", "erreur", None,
                    "Aucun dialogue, ambiance, effet, musique, sous-titre ou silence n'est precise.",
                    "Declare la bande son voulue, et inclus ou exclus explicitement musique/dialogue/sous-titres."))
        if MOTIF_REFERENCE.search(stripped) and not MOTIF_PORTEE_REFERENCE.search(stripped):
            probleme.append(ProblemePrompt(
                "P-PORTEE-REFERENCE", "avertissement",
                _ligne_de(stripped, MOTIF_REFERENCE),
                "Une reference est citee sans limite d'heritage.",
                "Precise ce que la reference transmet (identite, etat, matiere, cadrage, lumiere, couleur) et ce qu'elle exclut."))
        if MOTIF_IMMOBILE.search(stripped) and MOTIF_SUJET_EN_MOUVEMENT.search(stripped):
            probleme.append(ProblemePrompt(
                "P-CONFLIT-MOUVEMENT", "erreur",
                _ligne_de(stripped, MOTIF_IMMOBILE),
                "Le sujet doit rester immobile ET se deplacer sans cesse dans le meme prompt.",
                "Deplace l'un des deux vers un autre temps fort ou un autre sujet, ou retire l'un des deux."))
        mouvements_detectes = [nom for nom, motif in MOUVEMENTS_CAMERA.items()
                               if motif.search(stripped)]
        if ((MOTIF_CAMERA_VERROUILLEE.search(stripped) and mouvements_detectes)
                or len(mouvements_detectes) > 1):
            probleme.append(ProblemePrompt(
                "P-CONFLIT-CAMERA", "erreur",
                _ligne_de(stripped, MOTIF_CAMERA),
                "Le prompt contient plus d'une instruction de camera principale incompatible.",
                "Garde un seul mouvement de camera principal, ou decoupe en plans avec chacun son propre contrat de camera."))
        correspondance_totale = MOTIF_DUREE_TOTALE.search(stripped)
        plages = [(float(debut.replace(",", ".")), float(fin.replace(",", ".")))
                  for debut, fin in MOTIF_PLAGE_TEMPORELLE.findall(stripped)]
        if (correspondance_totale and plages
                and max(fin for _, fin in plages)
                > float(correspondance_totale.group(1).replace(",", ".")) + 1e-9):
            probleme.append(ProblemePrompt(
                "P-CHRONOLOGIE-DEPASSEE", "erreur",
                _ligne_de(stripped, MOTIF_PLAGE_TEMPORELLE),
                "Au moins un temps fort chronometre depasse la duree totale declaree.",
                "Raccourcis ou retire des temps forts, allonge la duree, ou decoupe en plusieurs plans."))
        if any(len(motif.findall(stripped)) > 1 for motif in GROUPES_NEGATION_REDONDANTE):
            probleme.append(ProblemePrompt(
                "P-NEGATION-REDONDANTE", "avertissement", None,
                "Des contraintes negatives equivalentes sont repetees.",
                "Garde une seule limite precise, associee a une consigne positive pour le resultat voulu."))
        if MOTIF_PARAMETRE_PRIVE.search(stripped) and not MOTIF_ADAPTATEUR.search(stripped):
            probleme.append(ProblemePrompt(
                "P-PLATEFORME-MELANGEE", "avertissement",
                _ligne_de(stripped, MOTIF_PARAMETRE_PRIVE),
                "Des parametres propres a un fournisseur apparaissent dans le prompt principal.",
                "Deplace seed/steps/cfg/sampler dans une section d'adaptation plateforme separee."))
        if (MOTIF_DIALOGUE_EXACT.search(stripped)
                and not MOTIF_LIMITE_DIALOGUE_VISUEL.search(stripped)):
            probleme.append(ProblemePrompt(
                "P-DIALOGUE-VISUALISATION", "avertissement",
                _ligne_de(stripped, MOTIF_DIALOGUE_EXACT),
                "Un dialogue exact est present sans limite empechant qu'il devienne une image.",
                "Si la replique evoque des personnes ou lieux hors champ, precise que le dialogue reste sonore, sans flashback ni sujet ajoute."))
        if (len(MOTIF_ABSTRAIT.findall(stripped)) >= 2
                and not MOTIF_CONCRET.search(stripped)):
            probleme.append(ProblemePrompt(
                "P-ABSTRAIT-SEUL", "avertissement",
                _ligne_de(stripped, MOTIF_ABSTRAIT),
                "Le prompt s'appuie sur des qualificatifs abstraits sans consigne visuelle ou sonore observable.",
                "Traduis l'intention en sujet, action, camera, lumiere motivee, matiere, couleur ou son."))
        if not MOTIF_PLATEFORME.search(stripped):
            hypotheses.append("aucune plateforme precisee ; aucun parametre propre a un fournisseur n'a ete suppose")

    erreurs = sum(1 for p in probleme if p.gravite == "erreur")
    avertissements = sum(1 for p in probleme if p.gravite == "avertissement")
    score = 0 if not stripped else max(0, min(100, 100 - erreurs * 15 - avertissements * 5))
    ordre_gravite = {"erreur": 0, "avertissement": 1}
    probleme.sort(key=lambda p: (ordre_gravite[p.gravite], p.ligne or 0, p.code))

    return AuditPrompt(
        pret=erreurs == 0,
        score=score,
        support=support,
        problemes=probleme,
        modules_detectes=_modules_detectes(stripped),
        hypotheses=hypotheses,
    )
