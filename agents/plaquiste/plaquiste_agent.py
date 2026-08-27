"""L'assistant metier d'UniC Plaquiste : devis, mails, argumentaire, planning.

Ce que cet agent a de particulier, et qui n'est pas une precaution de style :
**il ne fabrique jamais un prix**. Les tarifs viennent de
`config/unic_plaquiste.yaml`, tire des devis reels du proprietaire. Un article
absent de cette grille n'a pas de prix — l'assistant le dit et demande, au lieu
d'ecrire un chiffre plausible dans un document qui part chez un client.

Un devis faux coute plus cher qu'un devis en retard.
"""
import logging
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from agents.plaquiste.archives import exemple_demande, extraits_pour, formater
from agents.plaquiste.controle_prix import avertissement, verifier_prix
from core.agent.base_agent import BaseAgent
from core.memory.memory_manager import MemoryManager
from core.models.base import ModelProvider

logger = logging.getLogger("usman.agent.plaquiste")

FICHIER_METIER = Path(__file__).resolve().parents[2] / "config" / "unic_plaquiste.yaml"

MOIS = ("janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet",
        "aout", "septembre", "octobre", "novembre", "decembre")


def date_du_jour() -> date:
    """Date lue sur la machine. Isolee pour que les tests la fixent."""
    return date.today()


def date_en_toutes_lettres(jour: date) -> str:
    """« 27 aout 2026 », la forme utilisee dans ses documents."""
    return f"{jour.day} {MOIS[jour.month - 1]} {jour.year}"


def numero_du_jour(jour: date, suffixe: str = "XXX") -> str:
    """Numerotation maison : UC-AAAA-MMJJ-CLI."""
    return f"UC-{jour.year}-{jour.month:02d}{jour.day:02d}-{suffixe}"


def charger_metier(chemin: Path = FICHIER_METIER) -> Dict[str, Any]:
    """Lit les connaissances metier. Rend {} si le fichier manque, sans lever.

    Un fichier absent n'empeche pas le serveur de demarrer : l'agent le signale
    et refuse de chiffrer, ce qui est plus sur qu'un demarrage impossible.
    """
    try:
        return yaml.safe_load(chemin.read_text(encoding="utf-8")) or {}
    except Exception as erreur:
        logger.error("Connaissances metier illisibles (%s) : aucun chiffrage possible.", erreur)
        return {}


def _grille(metier: Dict[str, Any]) -> Dict[str, int]:
    """Reunit materiaux et portes en une seule grille de prix."""
    grille = dict(metier.get("prix_materiaux") or {})
    grille.update(metier.get("prix_portes") or {})
    return grille


def metiers_evoques(demande: str, metier: Dict[str, Any]) -> List[str]:
    """Rend les metiers cites qui ne sont pas les siens.

    Electricite, plomberie, climatisation : le proprietaire ne les fait pas, et
    ses documents les excluent depuis toujours. L'assistant ne les chiffre donc
    jamais de lui-meme — mais il ne fait pas semblant de ne pas comprendre : il
    dit que ce n'est pas son corps de metier.

    « Dormant, reveille seulement si demande » : la capacite n'est pas retiree,
    elle attend. La liste vit dans le fichier metier, pas ici.
    """
    texte = (demande or "").lower()
    return [mot for mot in (metier.get("metiers_hors_perimetre") or []) if mot in texte]


def articles_sans_prix(demande: str, metier: Dict[str, Any]) -> List[str]:
    """Rend les articles connus **absents** de la demande. Utilitaire de test.

    Sert a verifier qu'un article cite par le client existe bien dans la grille
    avant de le chiffrer.
    """
    connus = {nom.lower() for nom in _grille(metier)}
    mots = demande.lower()
    return sorted(nom for nom in connus if nom not in mots)


def composer_instruction(metier: Dict[str, Any]) -> str:
    """Compose l'instruction systeme a partir des seules donnees du fichier.

    Rien n'est ecrit en dur ici : changer un prix se fait dans le YAML, et la
    prochaine reponse en tient compte.
    """
    if not metier:
        return (
            "Tu es l'assistant d'UniC Plaquiste. Les connaissances metier sont "
            "introuvables : tu ne dois chiffrer aucun devis ni annoncer aucun "
            "prix. Dis-le clairement et demande a ce que le fichier "
            "config/unic_plaquiste.yaml soit retabli."
        )

    e = metier.get("entreprise", {})
    conventions = metier.get("conventions", {})
    grille = _grille(metier)
    mo = metier.get("main_oeuvre", {})
    engagements = metier.get("engagements", {})

    jour = date_du_jour()
    lignes = [
        f"Tu es l'assistant metier de {e.get('nom', 'UniC Plaquiste')}, "
        f"{e.get('specialite', '')}.",
        "",
        f"DATE DU JOUR, lue sur la machine : {date_en_toutes_lettres(jour)}.",
        f"Tout document que tu rediges porte cette date, et le numero "
        f"{numero_du_jour(jour)} ou le suffixe du client remplace XXX.",
        "Tu n'ecris jamais une autre date : un devis mal date est un devis "
        "juridiquement fragile.",
        "",
        "LE CLIENT EST CELUI QU'ON TE DONNE.",
        "Tu n'inventes ni nom, ni adresse, ni chantier, et tu ne reprends jamais "
        "ceux d'une affaire passee. S'il te manque le nom du client ou le lieu "
        "du chantier, tu les demandes en une ligne au lieu de les supposer.",
        f"Gerant : {e.get('gerant', '')}. {e.get('adresse', '')}.",
        f"Telephone {e.get('telephone', '')} — {e.get('site', '')}.",
        f"NINEA {e.get('ninea', '')} | RCCM {e.get('rccm', '')}.",
        "",
        "REGLE ABSOLUE — LES PRIX :",
        "Tu n'inventes jamais un prix. Tu utilises uniquement la grille ci-dessous.",
        "Si un article demande n'y figure pas, tu ecris « prix a confirmer » et tu",
        "demandes le tarif au gerant. Un devis faux coute plus cher qu'un devis en retard.",
        "",
        f"Grille de prix ({e.get('devise', 'FCFA')}) :",
    ]
    lignes += [f"- {nom} : {prix}" for nom, prix in grille.items()]

    if mo.get("tarif_m2"):
        lignes += [
            "",
            f"Main-d'oeuvre : {mo['tarif_m2']} {e.get('devise', 'FCFA')}/m2. "
            f"{mo.get('libelle', '')}",
        ]

    lignes += [
        "",
        "REGLES DE CHIFFRAGE :",
        f"- {conventions.get('regle_surface', '')}",
        f"- {conventions.get('mention_prix_unitaire', '')}",
        f"- Numerotation des documents : {conventions.get('numerotation', '')}.",
        "",
        "NE SONT JAMAIS INCLUS, sauf demande explicite :",
    ]
    lignes += [f"- {x}" for x in metier.get("exclusions_habituelles", [])]

    hors = metier.get("metiers_hors_perimetre") or []
    if hors:
        lignes += [
            "",
            "CE QUI N'EST PAS SON METIER : " + ", ".join(hors) + ".",
            "Tu ne chiffres jamais ces postes de toi-meme et tu ne les ajoutes",
            "dans aucun tableau. Si le client en parle, tu dis en une ligne que",
            "ce n'est pas le corps de metier d'UniC Plaquiste et tu poursuis sur",
            "le placo. Tu ne les traites que si le gerant te le demande",
            "explicitement.",
        ]

    lignes += [
        "",
        "TON ET ENGAGEMENT :",
        engagements.get("qualite", ""),
        engagements.get("geste_commercial", ""),
        "",
        "Tu rediges en francais, de maniere claire, professionnelle et chaleureuse.",
        "Pour un mail ou une lettre client : transparent, detaille poste par poste,",
        "jamais de promesse que le chantier ne peut pas tenir.",
    ]
    return "\n".join(ligne for ligne in lignes if ligne is not None)


class PlaquisteAgent(BaseAgent):
    """Devis, mails, argumentaire client et planification pour UniC Plaquiste."""

    def __init__(self, provider: ModelProvider, memory: Optional[MemoryManager] = None,
                 metier: Optional[Dict[str, Any]] = None):
        super().__init__(
            name="PlaquisteAgent",
            description="Assistant metier d'UniC Plaquiste : devis, mails, planning.",
            provider=provider,
            memory=memory,
        )
        # Injectable pour les tests ; lu au demarrage sinon.
        self.metier = metier if metier is not None else charger_metier()

    async def run(self, user_input: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        logger.info("PlaquisteAgent : %r", user_input[:60])

        if not self.metier:
            return {
                "status": "warning",
                "agent": self.name,
                "response": (
                    "Les connaissances metier d'UniC Plaquiste sont introuvables "
                    "(`config/unic_plaquiste.yaml`). Je ne chiffre rien tant qu'elles "
                    "ne sont pas retablies : un prix invente dans un devis client "
                    "coute plus cher qu'un devis en retard."
                ),
            }

        instruction = composer_instruction(self.metier)

        # Les archives ne s'ouvrent que si on les demande. Injectees a chaque
        # reponse, elles ramenaient le nom d'un ancien client et les details d'un
        # ancien chantier dans des affaires qui n'avaient rien a voir.
        extraits = extraits_pour(user_input) if exemple_demande(user_input) else []
        archives = formater(extraits)
        if archives:
            instruction = f"{instruction}\n\n{archives}"

        reponse = ((await self.provider.generate(prompt=user_input, system_prompt=instruction)) or "").strip()

        # L instruction dit au modele de ne pas alterer un prix. Ce controle-ci
        # verifie qu il ne l a pas fait : une consigne n est pas une garantie, et
        # le document part chez un client.
        anomalies = verifier_prix(reponse, self.metier)
        hors_metier = metiers_evoques(user_input, self.metier)
        if hors_metier:
            logger.info("Hors perimetre evoque : %s", ", ".join(hors_metier))

        return {
            "status": "success",
            "agent": self.name,
            "articles_connus": len(_grille(self.metier)),
            "extraits_archives": [e.source for e in extraits],
            "prix_alteres": [str(a) for a in anomalies],
            "hors_perimetre": hors_metier,
            "response": reponse + avertissement(anomalies),
        }
