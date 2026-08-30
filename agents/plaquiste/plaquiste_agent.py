"""L'assistant metier d'UniC Plaquiste : devis, mails, argumentaire, planning.

Ce que cet agent a de particulier, et qui n'est pas une precaution de style :
**il ne fabrique jamais un prix**. Les tarifs viennent de
`config/unic_plaquiste.yaml`, tire des devis reels du proprietaire. Un article
absent de cette grille n'a pas de prix — l'assistant le dit et demande, au lieu
d'ecrire un chiffre plausible dans un document qui part chez un client.

Un devis faux coute plus cher qu'un devis en retard.
"""
import base64
import logging
import re
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from agents.plaquiste.archives import exemple_demande, extraits_pour, formater
from agents.plaquiste.calcul_materiaux import formater as formater_calcul
from agents.plaquiste.calcul_materiaux import quantites_pour
from agents.plaquiste.controle_prix import avertissement, verifier_prix
from agents.plaquiste.metre import lire_demande
from agents.plaquiste.metre_plan import (
    chemin_dans,
    demande_non_calculable_depuis_le_plan,
    demande_un_plafond,
    depuis_mesure,
    faces_du_mur,
    lire_hauteur,
    surface_murs_m2,
)
from agents.plaquiste.metre_plan import formater as formater_plan
from apps.backend.config import BASE_DIR
from apps.backend.pieces_jointes import DepotPiecesJointes
from core.agent.base_agent import BaseAgent
from core.connectors.registre import RegistreConnecteurs
from core.memory.memory_manager import MemoryManager
from core.memory.personnelle import MemoirePersonnelle, Nature, TypeSouvenir
from core.memory.recuperation import formater as formater_souvenirs
from core.memory.recuperation import recuperer
from core.models.base import ModelProvider

logger = logging.getLogger("usman.agent.plaquiste")

FICHIER_METIER = Path(__file__).resolve().parents[2] / "config" / "unic_plaquiste.yaml"

MOIS = ("janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet",
        "aout", "septembre", "octobre", "novembre", "decembre")

#: Ce qui demande un FICHIER, et pas seulement un texte de devis. Le mot
#: « devis » seul ne suffit pas : il est dans presque toutes ses phrases, et
#: proposer un document a chaque fois transformerait la confirmation en reflexe.
#: Meme regle pour facture, bon de commande et bon de livraison : la phrase
#: exacte, jamais le mot seul.
DEMANDE_DE_DOCUMENT = re.compile(
    r"\b(pdf|document|imprim\w*|edite|édite|genere le devis|génère le devis"
    r"|genere la facture|génère la facture"
    r"|genere le bon de commande|génère le bon de commande"
    r"|genere le bon de livraison|génère le bon de livraison)\b",
    re.IGNORECASE)

#: Le type de document a produire, une fois qu'un FICHIER est deja demande
#: (DEMANDE_DE_DOCUMENT ci-dessus, qui seule declenche une ecriture). Le
#: renderer (`devis_pdf.py`) accepte deja `type_document` librement ; seule
#: l'orchestration manquait. « Bon de commande »/« bon de livraison » avant
#: « facture » : une phrase qui cite plusieurs mots doit garder le plus
#: specifique.
TYPES_DE_DOCUMENT = (
    (re.compile(r"bon de commande", re.IGNORECASE), "BON DE COMMANDE"),
    (re.compile(r"bon de livraison", re.IGNORECASE), "BON DE LIVRAISON"),
    (re.compile(r"facture", re.IGNORECASE), "FACTURE"),
)


def type_document_demande(texte: str) -> str:
    """DEVIS par defaut — le cas le plus frequent, jamais un type devine."""
    for motif, type_document in TYPES_DE_DOCUMENT:
        if motif.search(texte or ""):
            return type_document
    return "DEVIS"

#: Ce qu'il faut connaitre pour adresser un devis. Jamais devine dans la phrase.
DESTINATAIRE = ("client", "lieu", "objet")

#: Ce qui demande QUAND, et non combien. « planifie », « suis-je libre »,
#: « quel creneau » : la reponse est dans son agenda, pas dans sa grille de prix.
DEMANDE_D_AGENDA = re.compile(
    r"\b(planifi\w*|agenda|cr[ée]neau\w*|disponibilit[ée]s?|dispo\w*"
    r"|suis[- ]je libre|libre\s+(?:quand|le|ce|cette|lundi|mardi|mercredi|jeudi"
    r"|vendredi|samedi)|quand\s+(?:puis|peux|est-ce)\w*)\b",
    re.IGNORECASE)

#: Ce qu'il faut connaitre pour POSER un rendez-vous. Jamais lu dans la phrase :
#: une date devinee met une equipe sur la route un mauvais jour.
RENDEZ_VOUS = ("titre", "debut", "fin")

#: Combien de creneaux libres sont montres. Au-dela, la liste cesse d'aider.
CRENEAUX_MONTRES = 6


def date_du_jour() -> date:
    """Date lue sur la machine. Isolee pour que les tests la fixent."""
    return date.today()


def date_en_toutes_lettres(jour: date) -> str:
    """« 27 aout 2026 », la forme utilisee dans ses documents."""
    return f"{jour.day} {MOIS[jour.month - 1]} {jour.year}"


def numero_du_jour(jour: date, suffixe: str = "XXX") -> str:
    """Numerotation maison : UC-AAAA-MMJJ-CLI."""
    return f"UC-{jour.year}-{jour.month:02d}{jour.day:02d}-{suffixe}"


def chemin_hors_du_depot(chemin: str) -> bool:
    """Faux si le chemin tombe dans le depot d'ARENA lui-meme — a refuser.

    `chemin_dans()` lit un chemin absolu **ecrit dans la phrase**, sans autre
    controle : le proprietaire designe ainsi un plan pose n'importe ou sur sa
    machine, par conception (DEC-0012). Mais rien n'empechait alors une phrase
    de designer `.env`, `config/unic_plaquiste.yaml` ou tout autre fichier du
    depot lui-meme — le seul endroit ou ARENA garde ses propres secrets. Ce
    n'est pas un chemin qu'un plan de chantier a une seule raison de designer.
    """
    try:
        resolu = Path(chemin).resolve()
        resolu.relative_to(BASE_DIR.resolve())
    except (ValueError, OSError):
        return True
    return False


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
                 metier: Optional[Dict[str, Any]] = None,
                 registre: Optional[RegistreConnecteurs] = None,
                 pieces_jointes: Optional[DepotPiecesJointes] = None,
                 memoire_personnelle: Optional[MemoirePersonnelle] = None):
        super().__init__(
            name="PlaquisteAgent",
            description="Assistant metier d'UniC Plaquiste : devis, mails, planning.",
            provider=provider,
            memory=memory,
        )
        # Injectable pour les tests ; lu au demarrage sinon.
        self.metier = metier if metier is not None else charger_metier()
        # Sans registre, l'agent redige mais ne produit aucun fichier. C'est un
        # etat annonce dans la reponse, pas un silence.
        self.registre = registre
        # Sans depot, un plan envoye par piece jointe (upload PWA) reste
        # invisible : seul un chemin tape en texte peut encore etre mesure.
        self.pieces_jointes = pieces_jointes
        # Sans memoire personnelle, une mesure de plan n'est jamais retenue :
        # le proprietaire devra renvoyer le meme plan s'il y revient plus tard.
        self.memoire_personnelle = memoire_personnelle

    def _lire_l_agenda(self, texte: str) -> Optional[Dict[str, Any]]:
        """Les creneaux libres, quand la demande porte sur QUAND.

        Rien n'est estime : les creneaux viennent de son agenda reel. Sans
        connecteur, ou sans identifiants Google, l'etat est rapporte tel quel —
        jamais un agenda vide, qui se lirait « ta semaine est libre ».

        Returns:
            Le compte-rendu, ou `None` quand la demande ne parle pas de dates.
        """
        if not DEMANDE_D_AGENDA.search(texte or ""):
            return None
        if self.registre is None:
            return {"statut": "NOT_CONFIGURED",
                    "message": ("Je peux chiffrer, pas regarder ton agenda : aucun "
                                "connecteur n'est branche sur cet agent.")}

        resultat = self.registre.executer("calendrier", "creneaux")
        if not resultat.a_eu_lieu:
            return {"statut": resultat.statut.value, "message": resultat.message,
                    "creneaux": []}

        creneaux = (resultat.detail or {}).get("donnees") or []
        return {"statut": resultat.statut.value, "message": resultat.message,
                "creneaux": creneaux[:CRENEAUX_MONTRES],
                # Ce que l'agenda n'a pas su lire se dit : c'est peut-etre ce
                # qui remplit le jour qu'on vient d'annoncer libre.
                "illisibles": (resultat.detail or {}).get("illisibles", 0)}

    def _poser_le_rendez_vous(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Soumet la pose d'un rendez-vous. **Rien n'est ecrit ici.**

        Le titre et les heures viennent du contexte de la conversation, jamais
        d'une lecture de la phrase : une date devinee met une equipe sur la
        route un mauvais jour.

        Returns:
            Le compte-rendu, ou `None` quand aucun rendez-vous n'est demande.
        """
        if not any(context.get(nom) for nom in RENDEZ_VOUS):
            return None
        if self.registre is None:
            return {"statut": "NOT_CONFIGURED",
                    "message": "Aucun connecteur d'agenda n'est branche sur cet agent."}

        manquants = [nom for nom in RENDEZ_VOUS if not context.get(nom)]
        if manquants:
            return {"statut": "INCOMPLET", "manquants": manquants,
                    "message": ("Rien n'est pose dans l'agenda : il manque "
                                + ", ".join(manquants) + ".")}

        resultat = self.registre.executer(
            "calendrier", "creer", titre=context["titre"], debut=context["debut"],
            fin=context["fin"], lieu=context.get("lieu"))
        return {"statut": resultat.statut.value, "message": resultat.message,
                "preuve": resultat.preuve}

    def _proposer_le_document(self, texte: str,
                              context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Soumet la production du PDF quand un fichier est explicitement demande.

        Rien n'est ecrit ici : `produire` est une action a confirmer, et le
        proprietaire garde la main. Le destinataire vient du contexte de la
        conversation, jamais d'une lecture de la phrase — un devis adresse a la
        mauvaise personne est pire qu'un devis absent.

        Returns:
            Le compte-rendu de la soumission, ou `None` quand aucun document
            n'a ete demande.
        """
        if not DEMANDE_DE_DOCUMENT.search(texte or ""):
            return None
        if self.registre is None:
            return {"statut": "NOT_CONFIGURED",
                    "message": ("Je peux rediger le devis, pas ecrire le fichier : "
                                "aucun connecteur n'est branche sur cet agent.")}

        destinataire = {nom: str(context.get(nom) or "").strip() for nom in DESTINATAIRE}
        manquants = [nom for nom, valeur in destinataire.items() if not valeur]
        if manquants:
            return {"statut": "INCOMPLET", "manquants": manquants,
                    "message": ("Le PDF n'est pas lance : il manque "
                                + ", ".join(manquants)
                                + ". Je ne devine pas le destinataire d'un devis.")}

        resultat = self.registre.executer(
            "devis", "produire", demande=texte,
            type_document=type_document_demande(texte), **destinataire)
        return {"statut": resultat.statut.value, "message": resultat.message,
                "preuve": resultat.preuve}

    def _mesurer_depuis(self, chemin: str, texte: str) -> Dict[str, Any]:
        """Le coeur de la mesure, une fois qu'un vrai chemin sur disque existe.

        Partage par les deux origines d'un plan (chemin tape en texte, ou
        piece jointe ecrite brievement le temps de cet appel) : la mesure et
        l'export ne doivent pas exister en double.
        """
        resultat = self.registre.executer("opentakeoff", "mesurer", chemin=chemin)
        if not resultat.a_eu_lieu:
            return {"statut": resultat.statut.value, "chemin": chemin, "message": resultat.message}

        metre = depuis_mesure(chemin, resultat.detail or {})
        export = None
        # Le chemin lui-meme finit en ".pdf" : le retirer avant de tester,
        # sinon CHAQUE plan declenche l'export — mesure sur ce module
        # (`\bpdf\b` matche le "pdf" de l'extension, pas seulement le mot).
        if DEMANDE_DE_DOCUMENT.search(texte.replace(chemin, "")):
            resultat_export = self.registre.executer("opentakeoff", "exporter", chemin=chemin)
            export = {"statut": resultat_export.statut.value, "message": resultat_export.message,
                      "preuve": resultat_export.preuve}

        return {
            "statut": resultat.statut.value,
            "chemin": chemin,
            "resume": formater_plan(metre),
            "surface_totale_m2": metre.surface_totale_m2,
            "perimetre_total_ml": metre.perimetre_total_ml,
            "complet": metre.complet,
            "export": export,
        }

    def _piece_plan_pdf(self, identifiants: Optional[List[str]]):
        """La premiere piece jointe qui porte un PDF, ou None.

        `pdf_base64` n'existe que pour un `.pdf` deja recu par la passerelle
        (`apps/backend/pieces_jointes.py`) — jamais relu, jamais devine.
        """
        if not identifiants or self.pieces_jointes is None:
            return None
        for identifiant in identifiants:
            piece = self.pieces_jointes.lire(identifiant)
            if piece is not None and piece.pdf_base64:
                return piece
        return None

    def _mesurer_la_piece_jointe(self, piece, texte: str) -> Dict[str, Any]:
        """Ecrit brievement les octets deja recus, mesure, efface tout de suite.

        La seule fenetre ou un plan envoye par upload touche le disque : le
        temps de cet appel, jamais plus. Meme regle de vie privee que
        `apps/backend/pieces_jointes.py`, juste reportee au moment ou la
        mesure est reellement demandee plutot qu'a l'upload — OpenTakeoff est
        un processus externe, il ne peut pas lire des octets en memoire.
        """
        dossier = Path(tempfile.mkdtemp(prefix="arena-plan-"))
        chemin_temp = dossier / (piece.nom or "plan.pdf")
        try:
            chemin_temp.write_bytes(base64.b64decode(piece.pdf_base64))
            resultat = self._mesurer_depuis(str(chemin_temp), texte)
        finally:
            chemin_temp.unlink(missing_ok=True)
            dossier.rmdir()
        # Le chemin rapporte est celui du fichier envoye, jamais le chemin
        # temporaire — qui n'existe deja plus, et n'a aucun sens pour lui.
        resultat["chemin"] = piece.nom
        return resultat

    def _mesurer_le_plan(self, texte: str,
                         identifiants_pieces: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """Mesure un plan PDF, tape en chemin ou envoye par piece jointe.

        Mesurer est une lecture : rien n'est ecrit de facon durable. Le
        rapport et le plan marque ne sont soumis, derriere la meme
        confirmation que le devis PDF, que si la demande demande AUSSI un
        fichier (`DEMANDE_DE_DOCUMENT`) — « analyse ce plan » ne doit pas
        ecrire deux fichiers sur sa machine sans qu'il l'ait demande.

        Returns:
            Le compte-rendu, ou `None` quand aucun plan n'a ete trouve —
            ni chemin tape, ni piece jointe PDF.
        """
        chemin = chemin_dans(texte)
        if chemin is not None:
            if not chemin_hors_du_depot(chemin):
                logger.warning("Chemin de plan refuse (dans le depot d'ARENA) : %s", chemin)
                return {"statut": "REFUSE", "chemin": chemin,
                        "message": "Ce chemin n'est pas ouvert : il tombe dans le depot d'ARENA."}
            if self.registre is None:
                return {"statut": "NOT_CONFIGURED", "chemin": chemin,
                        "message": ("Je peux chiffrer, pas ouvrir un plan : aucun "
                                    "connecteur n'est branche sur cet agent.")}
            return self._mesurer_depuis(chemin, texte)

        piece = self._piece_plan_pdf(identifiants_pieces)
        if piece is None:
            return None
        if self.registre is None:
            return {"statut": "NOT_CONFIGURED", "chemin": piece.nom,
                    "message": ("Je peux chiffrer, pas ouvrir un plan : aucun "
                                "connecteur n'est branche sur cet agent.")}
        return self._mesurer_la_piece_jointe(piece, texte)

    def _retenir_la_mesure(self, plan: Dict[str, Any], context: Dict[str, Any]) -> None:
        """Garde les CHIFFRES mesures pour qu'il puisse reprendre le meme plan
        plus tard sans le renvoyer. Jamais l'image du plan — seulement ce
        qu'OpenTakeoff en a mesure, deja un texte, deja sans donnee brute.

        Best-effort : une memoire qui echoue ne doit pas faire perdre la
        reponse de ce tour.
        """
        if self.memoire_personnelle is None or not plan.get("resume"):
            return
        projet = str(context.get("lieu") or context.get("client") or "").strip() or None
        try:
            self.memoire_personnelle.retenir(
                contenu=f"Plan {plan['chemin']} mesure : {plan['resume']}",
                type=TypeSouvenir.EPISODIQUE, nature=Nature.FAIT,
                source=f"OpenTakeoff, plan {plan['chemin']}",
                projet=projet,
                metadonnees={
                    "surface_totale_m2": plan.get("surface_totale_m2"),
                    "perimetre_total_ml": plan.get("perimetre_total_ml"),
                },
            )
        except Exception as erreur:  # noqa: BLE001 — une memoire ratee n'annule pas la reponse
            logger.warning("Mesure de plan non retenue en memoire : %s", erreur)

    def _plans_deja_mesures(self, texte: str) -> str:
        """Ce qu'un plan mesure il y a des jours peut rappeler a cette question.

        Lexical seulement (`recuperer`, pas d'embeddings) : cet agent n'a
        jamais eu d'index semantique, et lui en donner un pour ce seul usage
        deviendrait un second systeme de recherche a cote de celui du chat.
        """
        if self.memoire_personnelle is None:
            return ""
        resultats = recuperer(self.memoire_personnelle, texte, type=TypeSouvenir.EPISODIQUE)
        # `formater_souvenirs([])` dirait "Aucun souvenir pertinent." — un bruit
        # ajoute a chaque reponse. Rien de pertinent ne doit rien ajouter du tout.
        return formater_souvenirs(resultats) if resultats else ""

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

        # Un plan mesure il y a des jours : les chiffres restent disponibles
        # sans qu'il ait besoin de renvoyer le fichier. Jamais injecte quand
        # rien ne se rapporte a la question — pas un reflexe a chaque reponse.
        plans_connus = self._plans_deja_mesures(user_input)
        if plans_connus:
            instruction = (
                f"{instruction}\n\nPLANS DEJA MESURES (des tours precedents, "
                f"pas de ce message) :\n{plans_connus}\nCe sont des mesures reelles, "
                "pas une opinion. Reprends-les si la question s'y rapporte, "
                "ne les recalcule pas."
            )

        # Le metre se CALCULE. Jusqu'au 2026-08-28, `calcul_materiaux` n'etait
        # appele par personne et le modele inventait les quantites — alors que
        # les ratios sortent de son devis reel. Quand des dimensions sont lues,
        # le calcul est fait ici et depose dans l'instruction comme un fait.
        # Quand rien n'est lu, rien n'est injecte : pas de chiffre fabrique.
        demande = lire_demande(user_input)
        metre = None
        source_lu = ""
        if demande is not None:
            metre = quantites_pour(
                demande.surface, self.metier, faces=demande.faces,
                parois=demande.parois, deja_developpee=demande.deja_developpee)
            source_lu = demande.lu
            instruction = (
                f"{instruction}\n\n{formater_calcul(metre)}\n\n"
                "Ces quantites viennent d'etre calculees a partir de ses ratios reels. "
                "Reprends-les telles quelles : ne les recalcule pas, ne les arrondis pas, "
                "n'en ajoute aucune. Lecture des dimensions : "
                f"{demande.lu}."
            )

        # Un plan PDF : mesure par OpenTakeoff, jamais devine. Priorite aux
        # dimensions dictees en texte (plus explicites). Trois issues ensuite
        # (metre_plan.py, corrige le 29/08/2026 sur indication du proprietaire :
        # « la surface d'un mur, c'est largeur x hauteur ») :
        #   1. plafond PLAT nomme -> sa surface au sol EST sa surface, sans hauteur ;
        #   2. mur nomme ou non (cloison/separation/doublage/habillage/coffre),
        #      UNE hauteur donnee -> perimetre mesure x hauteur, faces selon le mot ;
        #   3. rampant, ou un mur SANS hauteur -> rien n'est chiffre.
        plan = self._mesurer_le_plan(user_input, (context or {}).get("attachments"))
        if plan is not None:
            self._retenir_la_mesure(plan, context or {})
        hauteur = lire_hauteur(user_input)
        if metre is None and plan is not None and plan.get("surface_totale_m2") \
                and demande_un_plafond(user_input):
            metre = quantites_pour(plan["surface_totale_m2"], self.metier, faces=1)
            source_lu = f"plafond mesure sur {plan['chemin']} : {plan['resume']}"
            instruction = (
                f"{instruction}\n\n{formater_calcul(metre)}\n\n"
                "Ces quantites viennent d'etre calculees a partir de ses ratios reels, "
                f"sur une surface MESUREE (pas dictee) : {plan['resume']} "
                "Reprends-les telles quelles : ne les recalcule pas, ne les arrondis pas, "
                "n'en ajoute aucune."
            )
        elif metre is None and plan is not None and plan.get("perimetre_total_ml") \
                and hauteur and not demande_non_calculable_depuis_le_plan(user_input):
            faces = faces_du_mur(user_input)
            surface = surface_murs_m2(plan["perimetre_total_ml"], hauteur)
            metre = quantites_pour(surface, self.metier, faces=faces)
            source_lu = (f"mur mesure sur {plan['chemin']} : perimetre "
                         f"{plan['perimetre_total_ml']:g} ml x hauteur {hauteur:g} m")
            instruction = (
                f"{instruction}\n\n{formater_calcul(metre)}\n\n"
                "Ces quantites viennent d'etre calculees a partir de ses ratios reels, "
                f"sur une surface MESUREE : {surface:g} m2 = perimetre "
                f"{plan['perimetre_total_ml']:g} ml (mesure sur le plan) x hauteur "
                f"{hauteur:g} m (donnee dans la demande). "
                "ATTENTION a le dire : ce perimetre est celui de TOUT le contour "
                "de chaque piece mesuree — s'il inclut des murs qui ne sont pas a "
                "poser, dis-lui de corriger la longueur avant de faire confiance "
                "au chiffre. Reprends les quantites telles quelles : ne les "
                "recalcule pas, ne les arrondis pas, n'en ajoute aucune."
            )
        elif plan is not None and plan.get("resume") \
                and demande_non_calculable_depuis_le_plan(user_input):
            instruction = (
                f"{instruction}\n\nUN RAMPANT SUIT LA PENTE DU TOIT : sa surface "
                "n'est deductible d'AUCUNE mesure de ce plan (ni la surface au "
                "sol, ni le perimetre x une hauteur verticale — il faut la "
                f"longueur le long de la pente). Ce que le plan a mesure : "
                f"{plan['resume']}\nDis-le-lui, et demande cette longueur en "
                "texte comme d'habitude si tu veux la chiffrer."
            )
        elif plan is not None and plan.get("resume"):
            instruction = (
                f"{instruction}\n\nCE QUE LE PLAN DONNE (mesure reelle, pas une opinion) :\n"
                f"{plan['resume']}\nReprends ces chiffres tels quels s'ils sont demandes ; "
                "n'en calcule aucune quantite de materiaux sans qu'il ait precise ce qui "
                "est a poser."
            )
        elif plan is not None:
            instruction = (
                f"{instruction}\n\nLE PLAN {plan['chemin']} N'A PAS PU ETRE MESURE : "
                f"{plan.get('message', '')}\nDis-le-lui tel quel, n'invente aucune surface."
            )

        # L'agenda : ses creneaux reels entrent dans l'instruction comme des
        # faits. Sans cela, le modele proposait des jours au hasard.
        agenda = self._lire_l_agenda(user_input)
        if agenda and agenda.get("creneaux"):
            lignes = "\n".join(f"- du {c['debut']} au {c['fin']}"
                                for c in agenda["creneaux"])
            instruction = (
                f"{instruction}\n\nCRENEAUX REELLEMENT LIBRES dans son agenda :\n"
                f"{lignes}\n"
                "Ces creneaux viennent de son agenda. Propose uniquement ceux-la, "
                "tels quels. N'en invente aucun autre et ne deplace aucune heure.")
        elif agenda:
            instruction = (
                f"{instruction}\n\nSON AGENDA N'EST PAS LISIBLE : {agenda['message']}\n"
                "Ne propose aucune date : dis-lui que tu ne peux pas voir son agenda.")

        # Le rendez-vous : soumis a confirmation, jamais pose d'autorite.
        rendez_vous = self._poser_le_rendez_vous(context or {})

        # Le document PDF : soumis a confirmation, jamais ecrit d'autorite.
        # Fait avant la generation pour que la reponse puisse le dire.
        document = self._proposer_le_document(user_input, context or {})

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
            # Le metre calcule voyage avec la reponse : il doit etre verifiable
            # sans relire le prompt.
            "metre": {
                "lu": source_lu,
                "surface_developpee": metre.surface_developpee,
                "parois": metre.parois,
                "parois_estimees": metre.parois_estimees,
                "quantites": {b.article: b.quantite for b in metre.besoins},
            } if metre is not None else None,
            "hors_perimetre": hors_metier,
            # Ce qu'un plan PDF joint a rendu. `None` quand aucun chemin de
            # plan n'a ete lu dans la demande.
            "plan": plan,
            # Ce qu'il est advenu du fichier demande. `None` quand aucun ne
            # l'etait — jamais un statut inventé pour remplir le champ.
            "document": document,
            # Ce que son agenda a repondu, et ce qu'il est advenu d'un rendez-vous
            # demande. `None` quand la demande ne parlait pas de dates.
            "agenda": agenda,
            "rendez_vous": rendez_vous,
            "response": (reponse + avertissement(anomalies)
                         + (f"\n\n{document['message']}" if document else "")
                         + (f"\n\n{rendez_vous['message']}" if rendez_vous else "")
                         + (f"\n\n{plan['export']['message']}"
                            if plan and plan.get("export") else "")),
        }
