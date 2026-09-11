"""La couche de contexte metier (mission §11) — jamais UniC Plaquiste en dur.

`agents/plaquiste/chemins.py::fichier_metier()` resout deja `config/
metier.yaml` sans nommer aucune entreprise (decision du proprietaire du
02/09/2026 : « ce projet est libre comme bonjour »). Ce module ne fait que
LIRE ce meme fichier generique et en extraire le profil d'entreprise — c'est
deja la couche que la mission demande : un plombier ou un imprimeur qui pose
son propre `metier.yaml` obtient exactement le meme comportement, sans une
seule ligne de code a changer ici.

**Rien n'est invente.** Un champ absent du fichier reste `None` (ou une liste
vide) — jamais une valeur plausible. `disponible` dit honnetement si un
contexte a pu etre charge du tout.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import yaml

from agents.plaquiste.chemins import fichier_metier


@dataclass(frozen=True)
class ContexteAffaires:
    """Le profil d'entreprise disponible pour l'analyse executive — jamais
    plus que ce que `config/metier.yaml` declare reellement."""

    disponible: bool
    raison_indisponible: Optional[str] = None
    nom: Optional[str] = None
    specialite: Optional[str] = None
    devise: Optional[str] = None
    grille_tarifaire_chargee: bool = False
    nombre_articles_grille: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "available": self.disponible, "reason_unavailable": self.raison_indisponible,
            "name": self.nom, "specialty": self.specialite, "currency": self.devise,
            "pricing_grid_loaded": self.grille_tarifaire_chargee,
            "pricing_grid_items": self.nombre_articles_grille,
        }

    def bloc_pour_prompt(self) -> str:
        """Le bloc a injecter dans une invite — vide si aucun contexte
        n'est disponible, jamais un profil devine."""
        if not self.disponible:
            return f"Aucun contexte metier disponible ({self.raison_indisponible})."
        morceaux = []
        if self.nom:
            morceaux.append(f"Entreprise : {self.nom}")
        if self.specialite:
            morceaux.append(f"Specialite : {self.specialite}")
        if self.devise:
            morceaux.append(f"Devise : {self.devise}")
        morceaux.append(
            f"Grille tarifaire : {'chargee, ' + str(self.nombre_articles_grille) + ' article(s)' if self.grille_tarifaire_chargee else 'non chargee'}."
        )
        return "\n".join(morceaux)


def _compter_articles(donnees: Dict[str, Any]) -> int:
    """Compte les articles de toute section tarifaire du fichier, quelle que
    soit sa forme reelle (liste, ou imbriquee par categorie) et quel que soit
    son nom exact — `config/metier.yaml` d'UniC Plaquiste porte
    `prix_materiaux`/`prix_portes`/`main_oeuvre`, un autre metier porterait un
    autre nom. Toute cle dont le nom contient "prix" ou "tarif" est comptee ;
    jamais suppose a un seul nom de section, qui ne vaudrait que pour UNE
    entreprise (mission §11)."""
    total = 0
    for cle, valeur in donnees.items():
        if "prix" not in cle and "tarif" not in cle:
            continue
        if isinstance(valeur, list):
            total += len(valeur)
        elif isinstance(valeur, dict):
            total += len(valeur)
    return total


def charger_contexte_affaires() -> ContexteAffaires:
    """Le contexte de l'entreprise configuree sur cette machine.

    Un fichier absent ou illisible rend un contexte marque indisponible,
    jamais un profil vide presente comme un vrai resultat de lecture."""
    chemin = fichier_metier()
    if not chemin.is_file():
        return ContexteAffaires(disponible=False, raison_indisponible=f"{chemin} n'existe pas")
    try:
        donnees = yaml.safe_load(chemin.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as erreur:
        return ContexteAffaires(disponible=False, raison_indisponible=f"lecture impossible : {erreur}")
    if not isinstance(donnees, dict):
        return ContexteAffaires(disponible=False, raison_indisponible="format inattendu (pas un mapping)")

    entreprise = donnees.get("entreprise") or {}
    nombre_articles = _compter_articles(donnees)
    return ContexteAffaires(
        disponible=True,
        nom=entreprise.get("nom"),
        specialite=entreprise.get("specialite") or entreprise.get("accroche"),
        devise=entreprise.get("devise"),
        grille_tarifaire_chargee=nombre_articles > 0,
        nombre_articles_grille=nombre_articles,
    )


def preuves_documentaires(question: str, lightrag_query: Optional[Any] = None) -> List[str]:
    """Extraits de documents metier reellement indexes (RAG), pertinents a
    la question — jamais une donnee inventee (mission §12/§19). Rend une
    liste vide, jamais une erreur, quand le moteur documentaire est absent
    ou en echec : l'absence de preuve reste une absence, pas un blocage."""
    if lightrag_query is None:
        return []
    try:
        reponse = lightrag_query(question)
    except Exception:  # noqa: BLE001 — un moteur documentaire en panne ne bloque jamais l'analyse
        return []
    if not reponse or not str(reponse).strip():
        return []
    return [str(reponse).strip()]
