"""Verifie qu'un devis genere n'a pas altere les prix du proprietaire.

L'instruction systeme dit au modele de ne jamais inventer un prix. C'est une
consigne, pas une garantie : un modele peut l'ignorer, et le devis part chez un
client. Ce module lit ce qui a ete ecrit et le compare a la grille.

Il ne corrige rien. Il signale, avec la ligne fautive et le prix attendu — le
proprietaire tranche. Corriger automatiquement un montant dans un document
commercial serait pire que le signaler.

**Limite connue, mesuree et non corrigee** : un prix qui est un multiple
exact du vrai passe inapercu — « 9 000 » pour une plaque a 4 500. La regle du
multiple existe pour ne pas confondre un total avec un prix unitaire, et la
lever ferait crier le controle sur tous les totaux justes. Distinguer les deux
demanderait de comprendre les colonnes du tableau, pas seulement la ligne.
`test_la_limite_du_multiple_est_connue` fige cette limite pour qu'elle reste
visible au lieu d'etre oubliee.

**Le controle est volontairement etroit.** Il ne flague que ce qu'il peut
prouver : un article de la grille, cite avec des chiffres, dont aucun ne
correspond a son prix. Un texte sans chiffre ne declenche rien ; une ligne qui
porte le bon prix quelque part non plus, meme accompagnee de la quantite et du
total. Un controle qui crie a tort est un controle qu'on eteint.
"""
import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List

logger = logging.getLogger("usman.agent.plaquiste.controle")

# Un montant est un nombre d'au moins trois chiffres, espaces ou points de
# milliers admis : « 4 500 », « 3 667 500 », « 4.500 ».
MONTANT = re.compile(r"\b\d{1,3}(?:[  .]\d{3})+\b|\b\d{3,}\b")

# En dessous, ce sont des quantites, des dimensions ou des dates, pas des prix.
MONTANT_MINIMUM = 100


@dataclass
class Anomalie:
    """Un article de la grille cite avec un prix qui n'est pas le sien."""

    article: str
    prix_attendu: int
    ligne: str

    def __str__(self) -> str:
        return f"{self.article} : {self.prix_attendu} attendu — « {self.ligne.strip()[:90]} »"


def _montants(ligne: str) -> List[int]:
    """Rend les nombres de la ligne qui peuvent etre des montants."""
    valeurs = []
    for trouve in MONTANT.findall(ligne):
        try:
            valeur = int(re.sub(r"[  .]", "", trouve))
        except ValueError:
            continue
        if valeur >= MONTANT_MINIMUM:
            valeurs.append(valeur)
    return valeurs


def _grille(metier: Dict[str, Any]) -> Dict[str, int]:
    grille = dict(metier.get("prix_materiaux") or {})
    grille.update(metier.get("prix_portes") or {})
    if (mo := metier.get("main_oeuvre", {})).get("tarif_m2"):
        grille["Main-d'oeuvre (m2)"] = mo["tarif_m2"]
    return grille


def verifier_prix(reponse: str, metier: Dict[str, Any]) -> List[Anomalie]:
    """Rend les articles cites avec un prix absent de la grille.

    Liste vide = rien de prouvable. Ce n'est pas « le devis est juste » : c'est
    « aucun prix altere n'a ete detecte ». La nuance compte, et le message
    rendu par l'agent la garde.
    """
    if not reponse or not metier:
        return []

    grille = _grille(metier)
    anomalies: List[Anomalie] = []

    for ligne in reponse.splitlines():
        montants = _montants(ligne)
        if not montants:
            continue
        bas = ligne.lower()
        for article, attendu in grille.items():
            if article.lower() not in bas:
                continue
            # Le prix juste peut etre accompagne de la quantite et du total :
            # il suffit qu'un multiple du prix figure sur la ligne — le prix
            # lui-meme en est un. Une ligne « BA13 | 4 500 | 815 | 3 667 500 »
            # passe donc, et c'est voulu.
            if any(m % attendu == 0 for m in montants):
                continue
            anomalies.append(Anomalie(article, attendu, ligne))

    if anomalies:
        logger.warning("%d prix altere(s) detecte(s) dans un document genere.", len(anomalies))
    return anomalies


def avertissement(anomalies: List[Anomalie]) -> str:
    """Message a joindre au document. Chaine vide s'il n'y a rien a dire."""
    if not anomalies:
        return ""
    lignes = [
        "",
        "---",
        "⚠️ **Prix à vérifier avant d'envoyer ce document.**",
        "Ces articles figurent dans ta grille avec un autre prix :",
        "",
    ]
    lignes += [f"- {a}" for a in anomalies]
    lignes.append("")
    lignes.append("Je ne corrige pas moi-même : c'est ton document et ton tarif.")
    return "\n".join(lignes)
