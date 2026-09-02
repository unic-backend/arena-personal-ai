"""L'assistant metier d'UniC Plaquiste : devis, mails, argumentaire, planning.

Ce que cet agent a de particulier, et qui n'est pas une precaution de style :
**il ne fabrique jamais un prix**. Les tarifs viennent de
`config/unic_plaquiste.yaml`, tire des devis reels du proprietaire. Un article
absent de cette grille n'a pas de prix — l'assistant le dit et demande, au lieu
d'ecrire un chiffre plausible dans un document qui part chez un client.

Un devis faux coute plus cher qu'un devis en retard.
"""
import base64
import io
import json
import logging
import re
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from agents.plaquiste.archives import exemple_demande, extraits_pour, formater
from agents.plaquiste.calcul_materiaux import Calcul, quantites_pour
from agents.plaquiste.calcul_materiaux import formater as formater_calcul
from agents.plaquiste.controle_prix import avertissement, verifier_prix
from agents.plaquiste.metre import lire_demande
from agents.plaquiste.metre_plan import (
    chemin_dans,
    demande_non_calculable_depuis_le_plan,
    demande_un_plafond,
    depuis_marques,
    depuis_mesure,
    faces_du_mur,
    formater_marques,
    lire_hauteur,
    surface_murs_m2,
)
from agents.plaquiste.metre_plan import formater as formater_plan
from apps.backend.config import BASE_DIR
from apps.backend.pieces_jointes import DepotPiecesJointes
from core.agent.base_agent import BaseAgent
from core.connectors.registre import RegistreConnecteurs
from core.fichier_suivi import FichierSuivi, date_de
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
#:
#: La meme phrase exacte que DEMANDE_DE_DOCUMENT pour chaque type, jamais le
#: mot nu : un mot nu laissait « genere le devis, comme la facture de la
#: semaine derniere » produire une FACTURE alors que le devis etait ce qui
#: avait ete demande — l'anti-motif que DEMANDE_DE_DOCUMENT s'interdit deja,
#: reintroduit ici par megarde une premiere fois puis corrige pour chaque type.
TYPES_DE_DOCUMENT = (
    (re.compile(r"genere le bon de commande|génère le bon de commande", re.IGNORECASE),
     "BON DE COMMANDE"),
    (re.compile(r"genere le bon de livraison|génère le bon de livraison", re.IGNORECASE),
     "BON DE LIVRAISON"),
    (re.compile(r"genere la facture|génère la facture", re.IGNORECASE), "FACTURE"),
)


def type_document_demande(texte: str) -> str:
    """DEVIS par defaut — le cas le plus frequent, jamais un type devine."""
    for motif, type_document in TYPES_DE_DOCUMENT:
        if motif.search(texte or ""):
            return type_document
    return "DEVIS"

#: Ce qui demande un DECOMPTE de marques annotees (menuiseries) sur un plan —
#: DEC-0022. Ne declenche PAS lui-meme la mesure de surface : un plan mesure
#: pour ses m2 et un plan compte pour ses portes/fenetres sont deux demandes
#: differentes, jamais confondues.
DEMANDE_DE_DECOMPTE = re.compile(
    r"\bcombien de (?:portes?|fenetres?|fenêtres?|menuiseries?)\b"
    r"|\bcompter? les (?:portes?|fenetres?|fenêtres?)\b"
    r"|\bnombre de (?:portes?|fenetres?|fenêtres?)\b",
    re.IGNORECASE)

#: La question posee au modele de vision (DEC-0022) — jamais habillee en
#: mesure : le prompt lui-meme demande une IMPRESSION, et dit que le modele
#: peut se tromper. Sert le meme decompte que `DEMANDE_DE_DECOMPTE` ; le
#: decompte deterministe (OpenTakeoff) et cet avis visuel sont deux signaux
#: differents, jamais fondus en un seul chiffre.
DEMANDE_VISUELLE_OUVERTURES = (
    "Regarde ce plan de construction. Decris ce que tu vois comme portes et "
    "fenetres : leur nombre approximatif et, si possible, leur emplacement. "
    "Sois clair sur le fait que c'est une lecture visuelle, pas un comptage "
    "certain — dis-le si tu n'es pas sur, et n'invente rien que tu ne vois pas."
)

#: Ce qu'il faut connaitre pour adresser un devis. Jamais devine dans la phrase.
DESTINATAIRE = ("client", "lieu", "objet")

#: Une demande de DEMONSTRATION. Demande du proprietaire le 02/09/2026 : « si
#: je lui demande juste un devis demonstration il me pose des tas de questions
#: [...] il faut enlever ses menottes ».
#:
#: Il avait raison, et le defaut est reel : les trois questions (client, lieu,
#: objet) existent pour proteger un document qui PART CHEZ UN CLIENT. Un devis
#: qu'il demande pour VOIR a quoi ca ressemble ne part chez personne — les
#: poser la ne protege rien, elles ne font que barrer la route.
#:
#: Ce qui reste protege, et ce n'est pas negociable : le document produit se
#: NOMME demonstration, sur le PDF, a la place meme du nom du client. Le
#: danger n'a jamais ete de fabriquer un exemple ; il a toujours ete qu'un
#: exemple soit pris pour un vrai. Un document qui annonce ce qu'il est ne
#: peut pas etre confondu.
#:
#: « exemple » seul n'est pas un declencheur : le mot est trop courant («
#: donne-moi un exemple de finition »). Il faut qu'il accompagne le document.
DEMANDE_DE_DEMONSTRATION = re.compile(
    r"\b(d[ée]monstration|d[ée]mo\b"
    r"|(devis|facture|document|bon de commande|bon de livraison)\s+"
    r"(de\s+)?(test|exemple|fictif|type|mod[èe]le)"
    r"|(exemple|mod[èe]le|test)\s+(de\s+)?(devis|facture)"
    r"|pour\s+voir\s+(a\s+quoi|à\s+quoi|ce\s+que)"
    r")",
    re.IGNORECASE)

#: Ce qui remplit les trois champs quand c'est une demonstration. Aucun n'est
#: un nom plausible : chacun DIT qu'il est fictif, et ces valeurs sont
#: imprimees telles quelles sur le PDF, a l'emplacement du client et du
#: chantier (`devis_pdf.py`). Un lecteur ne peut pas se tromper.
DESTINATAIRE_DEMONSTRATION = {
    "client": "DEMONSTRATION — client fictif",
    "lieu": "DEMONSTRATION — chantier fictif",
    "objet": ("DEVIS DE DEMONSTRATION — document non contractuel, "
              "aucun client reel, ne pas envoyer."),
}


def demande_de_demonstration(texte: str) -> bool:
    """Dit si la phrase demande un document d'exemple, pas un vrai document."""
    return bool(DEMANDE_DE_DEMONSTRATION.search(texte or ""))

#: Ce qui, dans une question posee par ARENA au tour precedent, designe
#: CHACUN des trois champs du destinataire. Trouve le 31/08/2026, en direct
#: avec le proprietaire : un devis se negocie sur plusieurs tours (« quel
#: est le nom du client ? » -> « c'est fann hock » deux tours plus tard),
#: et rien ne captait jamais cette reponse — DESTINATAIRE restait vide pour
#: toujours, quoi qu'il tape, puisque `context` n'est rempli par personne.
#:
#: La regle reste « LE CLIENT EST CELUI QU'ON TE DONNE » : cette capture est
#: DETERMINISTE (aucun modele n'intervient) et ne se declenche QUE quand la
#: reponse suit IMMEDIATEMENT une question qui demandait explicitement ce
#: champ precis — jamais devinee dans une phrase libre.
QUESTION_NOM_CLIENT = re.compile(r"nom (complet )?du client", re.IGNORECASE)
QUESTION_LIEU_CHANTIER = re.compile(
    r"lieu du chantier|adresse (exacte )?du chantier|o[uù] (se trouve|est) le chantier",
    re.IGNORECASE)
QUESTION_OBJET_DEVIS = re.compile(
    r"prestations? souhait|type de travaux|travaux souhait|objet du devis",
    re.IGNORECASE)

#: Une annonce EXPLICITE et LABELISEE — « le nom du client c'est X »,
#: « lieu de chantier c'est Y » — jamais un nom propre mentionne en passant.
#: Trouve le 31/08/2026, en direct avec le proprietaire : sa toute premiere
#: question ("hauteur sous plafond ?") ne demandait ni le client ni le
#: lieu, et pourtant il les a donnes de lui-meme dans la reponse suivante —
#: destinataire_depuis_l_historique() ne capte que ce qui SUIT une question
#: qui les demandait, donc rien n'etait capte alors qu'il l'avait clairement
#: dit. Le label ("le nom du client", "lieu de chantier") est ce qui rend
#: ceci sur : un nom propre seul, sans lui, n'est jamais capte.
#: Les lookaheads negatifs arretent la capture au prochain label connu —
#: ses phrases s'enchainent souvent sans ponctuation ("...cest Augustin
#: lieux de chantier cest almadie").
ANNONCE_NOM_CLIENT = re.compile(
    r"(?:nom du client|le client)\s*(?:c'?est|c est|:|s'appelle)\s+"
    r"((?:(?!lieu|chantier|objet|prestation).)+)",
    re.IGNORECASE)
ANNONCE_LIEU_CHANTIER = re.compile(
    r"(?:lieux? du chantier|lieux? de chantier|l'adresse du chantier|adresse du chantier)"
    r"\s*(?:c'?est|c est|:)\s+((?:(?!nom du client|le client|objet|prestation).)+)",
    re.IGNORECASE)
ANNONCE_OBJET_DEVIS = re.compile(
    r"(?:l'objet(?: du devis)?|objet du devis|les? prestations?(?: souhaitees?)?)"
    r"\s*(?:c'?est|c est|:)\s+((?:(?!nom du client|le client|lieu|chantier).)+)",
    re.IGNORECASE)

#: Tetes de phrase courantes a retirer d'une reponse captee — « C'est fann
#: hock » doit devenir « fann hock ». `c'?est` couvre aussi « cest », sans
#: apostrophe — frappe au telephone, mesure le 31/08/2026. Une tete non
#: reconnue reste telle quelle : mieux vaut une reponse avec sa tete de
#: phrase qu'une reponse coupee au mauvais endroit.
_TETE_DE_REPONSE = re.compile(r"^(c'?est|c est)\s+", re.IGNORECASE)


def _nettoyer_reponse_captee(texte: str) -> str:
    """Une reponse brute, debarrassee de sa tete de phrase la plus courante."""
    return _TETE_DE_REPONSE.sub("", (texte or "").strip()).strip()


def destinataire_depuis_l_historique(
    historique: List[Dict[str, str]], message_actuel: str,
) -> Dict[str, str]:
    """Le client/lieu/objet captes, de deux facons complementaires, tour
    apres tour dans l'ordre chronologique — un tour plus recent remplace
    ce qu'un tour plus ancien avait capte :

    1. la reponse suit DIRECTEMENT une question posee par ARENA qui
       demandait explicitement ce champ (QUESTION_NOM_CLIENT et les deux
       autres) ;
    2. le proprietaire l'annonce lui-meme, explicitement et de facon
       labelisee, sans attendre une question — `destinataire_annonce()`,
       verifiee sur CHAQUE tour utilisateur, pas seulement le dernier.
       Trouve le 31/08/2026, en direct avec le proprietaire : sa toute
       premiere reponse d'ARENA ne demandait ni le client ni le lieu, et il
       les a donnes des ce tour-la — un controle qui ne regarderait que le
       dernier message aurait rate cette annonce des qu'un tour la suit.

    `message_actuel` est ajoute comme le dernier tour utilisateur. Une
    question qui demande plusieurs champs a la fois (« le lieu du chantier
    et les prestations souhaitees ? ») recoit la meme reponse pour chacun —
    imparfait, mais `produire` n'ecrit qu'un fichier local que le
    proprietaire relit avant de l'envoyer : ce n'est jamais un envoi
    automatique a un client.
    """
    tours = list(historique) + [{"role": "user", "content": message_actuel}]
    valeurs: Dict[str, str] = {}
    for index, tour in enumerate(tours):
        if tour.get("role") != "user":
            continue
        texte = tour.get("content") or ""
        precedent = tours[index - 1] if index > 0 else {}
        if precedent.get("role") == "assistant":
            question = precedent.get("content") or ""
            reponse = _nettoyer_reponse_captee(texte)
            if reponse:
                if QUESTION_NOM_CLIENT.search(question):
                    valeurs["client"] = reponse
                if QUESTION_LIEU_CHANTIER.search(question):
                    valeurs["lieu"] = reponse
                if QUESTION_OBJET_DEVIS.search(question):
                    valeurs["objet"] = reponse
        valeurs.update(destinataire_annonce(texte))
    return valeurs


def destinataire_annonce(message_actuel: str) -> Dict[str, str]:
    """Le client/lieu/objet, quand le proprietaire les annonce lui-meme,
    explicitement et de facon labelisee, sans attendre qu'ARENA les ait
    demandes.

    Complement de `destinataire_depuis_l_historique()` : trouve le
    31/08/2026, en direct avec le proprietaire, dont la toute premiere
    reponse d'ARENA ne demandait ni le client ni le lieu — il les a donnes
    quand meme, spontanement, et rien ne les captait.

    La difference avec « jamais devine dans une phrase libre » est le
    label : « le client s'appelle Augustin » est capte, « j'ai vu Augustin
    hier » ne l'est jamais — aucun nom propre seul ne declenche ceci.
    """
    valeurs: Dict[str, str] = {}
    texte = message_actuel or ""
    trouve_client = ANNONCE_NOM_CLIENT.search(texte)
    if trouve_client:
        nettoye = _nettoyer_reponse_captee(trouve_client.group(1))
        if nettoye:
            valeurs["client"] = nettoye
    trouve_lieu = ANNONCE_LIEU_CHANTIER.search(texte)
    if trouve_lieu:
        nettoye = _nettoyer_reponse_captee(trouve_lieu.group(1))
        if nettoye:
            valeurs["lieu"] = nettoye
    trouve_objet = ANNONCE_OBJET_DEVIS.search(texte)
    if trouve_objet:
        nettoye = _nettoyer_reponse_captee(trouve_objet.group(1))
        if nettoye:
            valeurs["objet"] = nettoye
    return valeurs

#: Le 31/08/2026, le proprietaire est revenu sur son propre choix du meme
#: jour (« il les redit clairement, je les capture ») : la capture
#: deterministe ci-dessus exige un mot-cle labelise ("le nom du client
#: c'est ..."), et une phrase naturelle comme "Fais un devis pour Augustin
#: a Almadie" n'etait jamais captee. Prevenu explicitement du risque reel —
#: le modele peut se tromper de nom ou de lieu, et rien ne le detecterait
#: avant l'envoi — il a choisi quand meme de laisser le modele comprendre.
#:
#: `_destinataire_par_modele()` n'intervient qu'en dernier recours : APRES
#: la capture deterministe ci-dessus (qui reste prioritaire quand elle
#: trouve quelque chose), et seulement pour un champ ENCORE manquant au
#: moment ou un document est reellement demande. Chaque champ ainsi compris
#: est signale dans la reponse — jamais silencieux, pour qu'il le verifie
#: avant de confirmer un document qui part chez un client.
INSTRUCTION_EXTRACTION_DESTINATAIRE = (
    "Lis cet echange entre un plaquiste et son client. Extrais, uniquement "
    "s'ils sont clairement exprimes quelque part dans l'echange (pas "
    "forcement dans le dernier message) :\n"
    "- le nom du client\n"
    "- le lieu du chantier\n"
    "- l'objet des travaux (ce qui doit etre fait)\n\n"
    "Reponds en JSON strict, rien d'autre autour :\n"
    '{"client": "...", "lieu": "...", "objet": "..."}\n\n'
    "Si un champ n'est pas clairement donne, mets une chaine vide \"\" pour "
    "ce champ. N'INVENTE JAMAIS un nom, un lieu ou un objet qui ne serait "
    "pas explicitement present dans le texte. Ne devine rien a partir du "
    "style d'ecriture ou d'un contexte suppose."
)


def _extraire_json(texte: str) -> str:
    """Le premier bloc `{...}` plausible d'une reponse de modele.

    Le modele ne rend pas toujours du JSON pur malgre la consigne — parfois
    entoure de texte ou de balises ```json```. `json.loads("{}")` rend un
    dict vide plutot que de lever quand rien n'est trouve.
    """
    trouve = re.search(r"\{.*\}", texte or "", re.DOTALL)
    return trouve.group(0) if trouve else "{}"

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


def date_du_metier(chemin: Optional[Path] = None) -> Optional[float]:
    """Date de derniere modification du fichier metier, `None` s'il est absent.

    Garde comme point d'entree nomme : `core/fichier_suivi.date_de` fait le
    travail, cette fonction porte le defaut du chemin metier.
    """
    return date_de(chemin or FICHIER_METIER)


class MetierSuivi:
    """Les connaissances metier, relues quand le fichier change.

    Le defaut repare, mesure le 01/09/2026 : la grille etait lue **une fois**,
    a la construction de l'agent — lui-meme un singleton cree au demarrage du
    serveur (`apps/backend/runtime.py`). Le proprietaire changeait le prix de
    la plaque BA13 dans `config/unic_plaquiste.yaml`, et ARENA continuait de
    chiffrer a l'ancien prix jusqu'au prochain redemarrage. Rien ne le disait.

    C'est le pire mode d'echec de ce depot, et il est ecrit ailleurs dans ces
    memes fichiers : **un mauvais prix sur un document qui part chez un
    client**.

    La mecanique de relecture vit dans `core/fichier_suivi.py` : la meme forme
    de defaut a ete trouvee quatre fois dans la meme nuit.
    """

    def __init__(self, chemin: Optional[Path] = None):
        # Resolu ici, pas dans la signature : un defaut d'argument est evalue
        # a l'import, donc fige a la valeur qu'avait la constante au chargement
        # du module — la meme famille de defaut que celui repare ici.
        self._suivi = FichierSuivi(chemin or FICHIER_METIER, charger_metier,
                                   nom="Grille de prix")

    @property
    def chemin(self) -> Path:
        return self._suivi.chemin

    def actuel(self) -> Dict[str, Any]:
        """Les connaissances a jour. Relit le fichier si sa date a change."""
        return self._suivi.actuel()


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


def lignes_presence_en_ligne(entreprise: Dict[str, Any]) -> List[str]:
    """Application, reseaux sociaux et fiche Google Maps — s'ils sont renseignes.

    Partagee avec `apps.backend.prompts` : un seul endroit decide du format,
    pour que le devis et la conversation generale disent la meme chose.
    Chaque ligne est absente plutot que vide si l'information ne l'est pas
    dans `config/unic_plaquiste.yaml` — jamais un lien invente.
    """
    lignes: List[str] = []
    applications = entreprise.get("applications") or []
    if applications:
        lignes.append(f"Application(s) : {', '.join(applications)}.")
    if fiche := entreprise.get("fiche_google_maps"):
        lignes.append(f"Fiche Google Maps : {fiche}.")
    reseaux = entreprise.get("reseaux_sociaux") or {}
    if reseaux:
        detail = " · ".join(f"{nom.capitalize()} {lien}" for nom, lien in reseaux.items())
        lignes.append(f"Reseaux sociaux : {detail}.")
    return lignes


#: Le regime NORMAL : un devis part chez quelqu'un, donc on ne devine personne.
#: Inchange depuis le 31/08/2026 — les formulations exactes des trois questions
#: sont lues par `destinataire_depuis_l_historique`, les reecrire casserait
#: l'association entre la question posee et la reponse suivante.
BLOC_VRAI_CLIENT = (
    "LE CLIENT EST CELUI QU'ON TE DONNE.",
    "Tu n'inventes ni nom, ni adresse, ni chantier, et tu ne reprends jamais "
    "ceux d'une affaire passee. S'il te manque le nom du client, le lieu "
    "du chantier ou les prestations souhaitees, tu les demandes EXACTEMENT "
    "ainsi, une question par ligne, au lieu de les supposer : « Quel est "
    "le nom du client ? », « Quel est le lieu du chantier ? », « Quelles "
    "sont les prestations souhaitees ? ». Ces formulations exactes sont "
    "lues par un systeme automatique qui associe ta prochaine reponse au "
    "bon champ — une autre formulation ferait echouer cette association "
    "et tout redemander.",
)

#: Le regime DEMONSTRATION. Le proprietaire veut VOIR un devis, pas en envoyer
#: un : les trois questions ne protegent alors plus rien et ne font que barrer
#: la route (demande du 02/09/2026, « enleve ses menottes »).
#:
#: Ce qui ne bouge pas d'un pouce : les PRIX. Ils viennent de la grille, comme
#: toujours. C'est le destinataire qui est fictif, jamais les chiffres — un
#: exemple qui montrerait de faux tarifs n'apprendrait rien de vrai sur ce que
#: l'entreprise facture.
BLOC_DEMONSTRATION = (
    "CETTE DEMANDE EST UNE DEMONSTRATION. TU NE POSES AUCUNE QUESTION.",
    "Le gerant veut voir a quoi ressemble un devis, il n'en envoie aucun. Tu "
    "produis donc le document TOUT DE SUITE, complet, sans demander le nom du "
    "client, le lieu du chantier ni les prestations : tu choisis toi-meme un "
    "cas realiste (par exemple des cloisons ou un faux plafond avec des "
    "surfaces plausibles) et tu le chiffres entierement.",
    "Tu ecris en tete du devis : « DEVIS DE DEMONSTRATION — document non "
    "contractuel, aucun client reel ». Le destinataire porte le meme mot : tu "
    "n'inventes JAMAIS un nom de personne ou d'entreprise, meme en "
    "demonstration — un faux nom plausible est exactement ce qui ferait "
    "prendre l'exemple pour un vrai devis.",
    "Les PRIX, eux, restent ceux de la grille ci-dessous, sans exception. Une "
    "demonstration montre les vrais tarifs de l'entreprise sur un cas invente, "
    "jamais l'inverse.",
)


def composer_instruction(metier: Dict[str, Any], demande: str = "") -> str:
    """Compose l'instruction systeme a partir des seules donnees du fichier.

    Rien n'est ecrit en dur ici : changer un prix se fait dans le YAML, et la
    prochaine reponse en tient compte.

    `demande` est la phrase du tour. Elle ne sert qu'a une chose : reconnaitre
    une demande de DEMONSTRATION, et lever alors les trois questions
    (client, lieu, prestations) qui n'ont aucun sens pour un document qui ne
    part chez personne. Vide par defaut — l'instruction reste celle d'un vrai
    devis, la plus prudente des deux.
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
        *(BLOC_DEMONSTRATION if demande_de_demonstration(demande) else BLOC_VRAI_CLIENT),
        "",
        "LE PDF N'EST PAS TON TRAVAIL — NE DIS JAMAIS QUE TU NE PEUX PAS EN CREER.",
        "Produire le fichier PDF est fait par un systeme separe, automatiquement, "
        "des que le nom du client et le lieu du chantier sont connus — et ce "
        "systeme ajoute lui-meme son propre message apres ta reponse pour dire ou "
        "ca en est. Tu ne proposes donc jamais de copier-coller le devis dans Word "
        "ou un autre logiciel : ce n'est ni vrai, ni utile. Redige le devis "
        "normalement, comme toujours ; le PDF suit tout seul.",
        f"Gerant : {e.get('gerant', '')}. {e.get('adresse', '')}.",
        f"Telephone {e.get('telephone', '')} — {e.get('site', '')}.",
        f"NINEA {e.get('ninea', '')} | RCCM {e.get('rccm', '')}.",
        *lignes_presence_en_ligne(e),
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


def _rendre_premiere_page(chemin: str) -> Optional[str]:
    """La premiere page d'un plan PDF, rendue en PNG et encodee en base64.

    Rend `None` si `pypdfium2` n'est pas installe ou que le rendu echoue —
    une capacite absente se rapporte, elle ne leve jamais. 200 DPI (contre
    300 pour l'OCR de `tools/documents/reader.py`, qui doit lire du texte
    fin) : ici la question porte sur des symboles visibles a l'oeil, une
    resolution plus legere suffit.
    """
    try:
        import pypdfium2 as pdfium
    except ImportError:
        return None
    document = None
    try:
        document = pdfium.PdfDocument(chemin)
        page = document[0]
        image = page.render(scale=200 / 72).to_pil()
        tampon = io.BytesIO()
        image.save(tampon, format="PNG")
        return base64.b64encode(tampon.getvalue()).decode("ascii")
    except Exception as erreur:  # noqa: BLE001 — un rendu rate est un etat, pas un crash
        logger.debug("Rendu de page impossible (%s) : %s", chemin, erreur)
        return None
    finally:
        # Meme defaut que `tools/documents/reader._ocr_page` (mesure le
        # 01/09/2026) : sans fermeture explicite, le fichier reste ouvert
        # jusqu'au ramasse-miettes — indetermine — et l'effacement qui suit
        # dans l'appelant echoue sous Windows (`PermissionError: [WinError
        # 32]`), invisible sur Linux ou `unlink()` efface un fichier ouvert.
        if document is not None:
            document.close()


class PlaquisteAgent(BaseAgent):
    """Devis, mails, argumentaire client et planification pour UniC Plaquiste."""

    def __init__(self, provider: ModelProvider, memory: Optional[MemoryManager] = None,
                 metier: Optional[Dict[str, Any]] = None,
                 registre: Optional[RegistreConnecteurs] = None,
                 pieces_jointes: Optional[DepotPiecesJointes] = None,
                 memoire_personnelle: Optional[MemoirePersonnelle] = None,
                 provider_vision: Optional[ModelProvider] = None):
        super().__init__(
            name="PlaquisteAgent",
            description="Assistant metier d'UniC Plaquiste : devis, mails, planning.",
            provider=provider,
            memory=memory,
        )
        # Injectable pour les tests ; suivi sur disque sinon, pour qu'un prix
        # change dans `config/unic_plaquiste.yaml` soit vu sans redemarrer.
        self._metier_injecte = metier
        self._metier_suivi = None if metier is not None else MetierSuivi()
        # Sans registre, l'agent redige mais ne produit aucun fichier. C'est un
        # etat annonce dans la reponse, pas un silence.
        self.registre = registre
        # Sans depot, un plan envoye par piece jointe (upload PWA) reste
        # invisible : seul un chemin tape en texte peut encore etre mesure.
        self.pieces_jointes = pieces_jointes
        # Sans memoire personnelle, une mesure de plan n'est jamais retenue :
        # le proprietaire devra renvoyer le meme plan s'il y revient plus tard.
        self.memoire_personnelle = memoire_personnelle
        # Le meme modele que VisionAgent (qwen3-vl:4b, DEC-0019), jamais
        # self.provider : celui-ci n'est pas forcement configure pour voir une
        # image. Sans lui, l'avis visuel (DEC-0022) est simplement absent —
        # le decompte deterministe (`compter_marques`) continue seul.
        self.provider_vision = provider_vision

    @property
    def metier(self) -> Dict[str, Any]:
        """Les connaissances metier, relues si le fichier a change sur le disque."""
        if self._metier_injecte is not None:
            return self._metier_injecte
        return self._metier_suivi.actuel()

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

    def _proposer_le_document(self, texte: str, context: Dict[str, Any],
                              metre: Optional[Calcul] = None) -> Optional[Dict[str, Any]]:
        """Soumet la production du PDF quand un fichier est explicitement demande.

        Rien n'est ecrit ici : `produire` est une action a confirmer, et le
        proprietaire garde la main. Le destinataire vient du contexte de la
        conversation, jamais d'une lecture de la phrase — un devis adresse a la
        mauvaise personne est pire qu'un devis absent.

        `metre` est le calcul deja fait par `run()` (dimensions dictees OU
        surface mesuree sur un plan) : quand il existe, ses lignes sont
        transmises telles quelles au connecteur, qui n'a plus a relire la
        phrase pour les retrouver. Mesure du 30/08/2026 : sans ca, un devis
        demande apres la mesure d'un PLAN echouait a la confirmation avec
        « aucune dimension lue » — le calcul affiche dans la reponse ne
        rejoignait jamais le PDF reellement ecrit.

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
        if manquants and demande_de_demonstration(texte):
            # Demonstration : ce qui manque est REMPLI, pas demande. Les valeurs
            # disent elles-memes qu'elles sont fictives et s'impriment a la
            # place du nom du client — le document ne peut pas passer pour vrai.
            for champ in manquants:
                destinataire[champ] = DESTINATAIRE_DEMONSTRATION[champ]
            manquants = []
        if manquants:
            return {"statut": "INCOMPLET", "manquants": manquants,
                    "message": ("Le PDF n'est pas lance : il manque "
                                + ", ".join(manquants)
                                + ". Je ne devine pas le destinataire d'un devis.")}

        parametres_lignes: Dict[str, Any] = {}
        if metre is not None:
            parametres_lignes["lignes"] = [
                {"designation": besoin.article, "quantite": besoin.quantite}
                for besoin in metre.besoins]

        resultat = self.registre.executer(
            "devis", "produire", demande=texte,
            type_document=type_document_demande(texte), **destinataire, **parametres_lignes)
        return {"statut": resultat.statut.value, "message": resultat.message,
                "preuve": resultat.preuve}

    async def _destinataire_par_modele(
        self, historique: List[Dict[str, str]], message_actuel: str,
    ) -> Dict[str, str]:
        """Le client/lieu/objet, compris par le modele lui-meme dans une
        phrase libre — INSTRUCTION_EXTRACTION_DESTINATAIRE ci-dessus, choix
        du proprietaire du 31/08/2026 apres avoir accepte le risque explicite
        d'un champ mal compris.

        Best-effort et jamais bloquant, meme pattern que
        `_avis_visuel_du_plan` pour le modele de vision : une reponse
        illisible ou un appel qui echoue rend simplement {}, jamais un
        crash. Appele seulement en dernier recours par `run()`, pour un
        champ que la capture deterministe n'a pas trouve.
        """
        tours = list(historique) + [{"role": "user", "content": message_actuel}]
        fil = "\n".join(
            f"{'Client' if tour.get('role') == 'user' else 'Plaquiste'} : "
            f"{tour.get('content') or ''}"
            for tour in tours)
        try:
            brut = await self.provider.generate(
                prompt=fil, system_prompt=INSTRUCTION_EXTRACTION_DESTINATAIRE)
            donnees = json.loads(_extraire_json(brut or ""))
        except Exception as erreur:  # noqa: BLE001 — une extraction ratee rend {}, jamais un crash
            logger.info("Extraction du destinataire par le modele impossible : %s", erreur)
            return {}
        if not isinstance(donnees, dict):
            return {}
        return {champ: str(donnees[champ]).strip() for champ in DESTINATAIRE
                if str(donnees.get(champ) or "").strip()}

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

    def _avec_la_piece_jointe(self, piece, executer) -> Dict[str, Any]:
        """Ecrit brievement les octets deja recus, appelle `executer(chemin)`,
        efface tout de suite.

        La seule fenetre ou un plan envoye par upload touche le disque : le
        temps de cet appel, jamais plus. Meme regle de vie privee que
        `apps/backend/pieces_jointes.py`, juste reportee au moment ou la
        capacite est reellement demandee plutot qu'a l'upload — OpenTakeoff
        est un processus externe, il ne peut pas lire des octets en memoire.
        """
        dossier = Path(tempfile.mkdtemp(prefix="arena-plan-"))
        chemin_temp = dossier / (piece.nom or "plan.pdf")
        try:
            chemin_temp.write_bytes(base64.b64decode(piece.pdf_base64))
            resultat = executer(str(chemin_temp))
        finally:
            chemin_temp.unlink(missing_ok=True)
            dossier.rmdir()
        # Le chemin rapporte est celui du fichier envoye, jamais le chemin
        # temporaire — qui n'existe deja plus, et n'a aucun sens pour lui.
        resultat["chemin"] = piece.nom
        return resultat

    def _avec_le_chemin_du_plan(self, texte: str, identifiants_pieces: Optional[List[str]],
                                executer) -> Optional[Dict[str, Any]]:
        """Resout un plan (chemin tape ou piece jointe PDF), puis appelle
        `executer(chemin)` avec un vrai chemin sur disque.

        Partagee par toute capacite qui a besoin d'ouvrir un plan — mesurer,
        compter les marques (DEC-0022) : la resolution (refus si le chemin
        tombe dans le depot, `NOT_CONFIGURED` sans registre, ecriture
        temporaire puis effacement pour une piece jointe) ne doit exister
        qu'une seule fois.

        Returns:
            Le compte-rendu de `executer`, ou `None` quand aucun plan n'a ete
            trouve — ni chemin tape, ni piece jointe PDF.
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
            return executer(chemin)

        piece = self._piece_plan_pdf(identifiants_pieces)
        if piece is None:
            return None
        if self.registre is None:
            return {"statut": "NOT_CONFIGURED", "chemin": piece.nom,
                    "message": ("Je peux chiffrer, pas ouvrir un plan : aucun "
                                "connecteur n'est branche sur cet agent.")}
        return self._avec_la_piece_jointe(piece, executer)

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
        return self._avec_le_chemin_du_plan(
            texte, identifiants_pieces, lambda chemin: self._mesurer_depuis(chemin, texte))

    def _compter_marques_depuis(self, chemin: str) -> Dict[str, Any]:
        """Recense les marques annotees (menuiseries) deja ecrites sur le plan.

        A la difference de `_mesurer_depuis`, aucune echelle n'est requise et
        aucune coordonnee n'est designee : `compter_marques` lit du texte deja
        sur le plan (voir `core/connectors/opentakeoff.py`).
        """
        resultat = self.registre.executer("opentakeoff", "compter_marques", chemin=chemin)
        if not resultat.a_eu_lieu:
            return {"statut": resultat.statut.value, "chemin": chemin, "message": resultat.message}

        marques = depuis_marques(chemin, resultat.detail or {})
        return {
            "statut": resultat.statut.value,
            "chemin": chemin,
            "resume": formater_marques(marques),
            "total": marques.total,
            "complet": marques.complet,
        }

    def _compter_les_marques_du_plan(self, texte: str,
                                     identifiants_pieces: Optional[List[str]] = None
                                     ) -> Optional[Dict[str, Any]]:
        """Recense les marques annotees d'un plan, sur demande EXPLICITE.

        Contrairement a `_mesurer_le_plan`, un chemin de plan present dans le
        texte ne suffit pas seul a declencher ce decompte : sans la garde
        `DEMANDE_DE_DECOMPTE`, chaque mention de plan lancerait un second
        appel OpenTakeoff pour rien — « analyse ce plan » ne compte pas les
        menuiseries s'il n'a rien demande de tel.

        Returns:
            Le compte-rendu, ou `None` quand aucun decompte n'a ete demande,
            ou qu'aucun plan n'a ete trouve.
        """
        if not DEMANDE_DE_DECOMPTE.search(texte or ""):
            return None
        return self._avec_le_chemin_du_plan(
            texte, identifiants_pieces, self._compter_marques_depuis)

    async def _avis_visuel_depuis(self, chemin: str) -> Optional[str]:
        """Ce que le modele de vision dit avoir vu — une IMPRESSION, jamais
        une mesure. `None` sans image rendue ou si l'appel echoue : un avis
        absent ne doit jamais faire perdre le decompte deterministe qui
        l'accompagne.
        """
        image_b64 = _rendre_premiere_page(chemin)
        if image_b64 is None:
            return None
        try:
            reponse = await self.provider_vision.generate(
                prompt=DEMANDE_VISUELLE_OUVERTURES, images=[image_b64])
        except Exception as erreur:  # noqa: BLE001 — un avis rate est une absence, pas un crash
            logger.info("Avis visuel impossible sur %s : %s", chemin, erreur)
            return None
        return (reponse or "").strip() or None

    async def _avis_visuel_du_plan(self, texte: str,
                                   identifiants_pieces: Optional[List[str]] = None
                                   ) -> Optional[str]:
        """L'avis du modele de vision sur les ouvertures d'un plan (DEC-0022).

        Chemin async separe de `_avec_le_chemin_du_plan` (synchrone, partage
        par la mesure et le decompte) : appeler un modele de vision exige un
        `await`, et faire de toute la chaine de resolution un chemin async
        pour ce seul appelant aurait touche la mesure de surface deja
        verifiee. La resolution du chemin (chemin tape, ou piece jointe
        ecrite brievement) est donc reprise ici, plus courte : aucun message
        REFUSE/NOT_CONFIGURED n'est produit sur ce chemin best-effort — sans
        modele de vision, ou sans plan trouve, l'avis est simplement absent.

        Returns:
            L'avis du modele, ou `None` sans `provider_vision` configure,
            sans decompte demande (meme garde que `_compter_les_marques_du_plan`),
            ou sans plan trouve.
        """
        if self.provider_vision is None or not DEMANDE_DE_DECOMPTE.search(texte or ""):
            return None

        chemin = chemin_dans(texte)
        if chemin is not None:
            if not chemin_hors_du_depot(chemin) or self.registre is None:
                return None
            return await self._avis_visuel_depuis(chemin)

        piece = self._piece_plan_pdf(identifiants_pieces)
        if piece is None or self.registre is None:
            return None
        dossier = Path(tempfile.mkdtemp(prefix="arena-plan-"))
        chemin_temp = dossier / (piece.nom or "plan.pdf")
        try:
            chemin_temp.write_bytes(base64.b64decode(piece.pdf_base64))
            return await self._avis_visuel_depuis(str(chemin_temp))
        finally:
            chemin_temp.unlink(missing_ok=True)
            dossier.rmdir()

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

        # `user_input` peut etre le FIL ENTIER aplati (PLAQUISTE seul,
        # pwa_gateway.py, DEC a venir) — voulu pour que le modele et
        # l'accumulation de FAITS (dimensions, materiaux) voient tout
        # l'echange. Mais un DECLENCHEUR D'ACTION (mesurer CE plan, produire
        # UN document, compter les ouvertures MAINTENANT) n'est pas un fait
        # qui s'accumule : le lire dans tout le fil le rend « collant » —
        # trouve le 31/08/2026, en diagnostic apres coup : un chemin de plan
        # cite tot dans la conversation restait le seul jamais mesure meme
        # apres qu'un second plan soit donne (chemin_dans fait un `.search`,
        # qui rend le PREMIER match, pas le dernier), et « genere le pdf »
        # dit une fois faisait retenter la production a chaque tour suivant,
        # meme sans rapport. `message_actuel` est le seul texte que ces
        # declencheurs doivent lire.
        message_actuel = (context or {}).get("message_actuel") or user_input

        # Le destinataire du devis (client/lieu/objet), capte de deux facons
        # complementaires — jamais devine dans une phrase libre au sens ou
        # « jamais un nom propre mentionne en passant sans etre labelise » :
        # destinataire_depuis_l_historique() capte de deux facons, tour par
        # tour : une reponse directe a une question, OU une annonce
        # explicite du proprietaire, meme sans question. Un champ deja
        # present dans `context` (une future saisie structuree, par
        # exemple) gagne toujours sur ce qui est capte ici. Fait tot :
        # `_retenir_la_mesure`, plus bas, tague le souvenir d'un plan
        # mesure avec ce meme `contexte` — un plan mesure le tour ou le nom
        # du client est justement donne doit pouvoir le retrouver.
        contexte = dict(context or {})
        capture = destinataire_depuis_l_historique(
            contexte.get("historique") or [], message_actuel)
        for champ, valeur in capture.items():
            contexte.setdefault(champ, valeur)

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

        instruction = composer_instruction(self.metier, user_input)

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
        # D'ou viennent ces cotes : de CE message, ou d'un tour precedent du
        # fil ? Les deux sont legitimes — il dicte souvent les dimensions a un
        # tour, puis demande le document au suivant. Mais depuis que le metre
        # calcule ici part directement dans le PDF (lignes deja calculees,
        # `_proposer_le_document`), des cotes reprises d'un tour precedent
        # peuvent etre celles d'un AUTRE chantier. Mesure du 31/08/2026 :
        # « finalement c'est un autre chantier, genere le devis » produisait un
        # devis aux quantites du chantier d'avant, sans rien dire. Le fil reste
        # lu ; ce qui change, c'est qu'il le dit avant la confirmation.
        cotes_d_un_tour_precedent = (
            demande is not None and lire_demande(message_actuel) is None)
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
        plan = self._mesurer_le_plan(message_actuel, (context or {}).get("attachments"))
        if plan is not None:
            self._retenir_la_mesure(plan, contexte)
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

        # Un decompte de menuiseries (DEC-0022) : seulement sur demande
        # explicite (DEMANDE_DE_DECOMPTE), jamais parce qu'un plan a ete
        # mesure — mesurer des m2 et compter des portes sont deux demandes
        # differentes. `compter_marques` lit du texte deja sur le plan
        # (un tag au-dessus d'une valeur, comme un tableau de menuiseries),
        # jamais une image : aucune coordonnee n'y est devinee.
        marques = self._compter_les_marques_du_plan(
            message_actuel, (context or {}).get("attachments"))
        if marques is not None and marques.get("resume"):
            instruction = (
                f"{instruction}\n\nDECOMPTE DE MENUISERIES DU PLAN (mesure reelle, "
                f"pas une opinion) :\n{marques['resume']}\nReprends ce chiffre tel "
                "quel s'il est demande ; ne recompte rien toi-meme."
            )
        elif marques is not None:
            instruction = (
                f"{instruction}\n\nLE DECOMPTE DE MENUISERIES DE {marques['chemin']} "
                f"N'A PAS PU ETRE FAIT : {marques.get('message', '')}\nDis-le-lui tel "
                "quel, n'invente aucun chiffre."
            )

        # L'avis visuel de Qwen3-VL sur les memes ouvertures (DEC-0022) : un
        # SECOND signal, jamais fondu avec le decompte deterministe ci-dessus.
        # Absent sans provider_vision configure, sans plan, ou si le rendu ou
        # l'appel echoue — best-effort, ne bloque jamais la reponse.
        avis_visuel = await self._avis_visuel_du_plan(
            message_actuel, (context or {}).get("attachments"))
        if avis_visuel:
            instruction = (
                f"{instruction}\n\nCE QUE LE MODELE DE VISION DIT AVOIR VU sur ce "
                f"plan (une IMPRESSION, jamais une mesure certaine) :\n{avis_visuel}\n"
                "Presente-le distinctement du decompte OpenTakeoff ci-dessus si les "
                "deux sont presents : l'un lit du texte deja ecrit sur le plan, "
                "l'autre regarde l'image et peut se tromper ou en manquer."
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
        rendez_vous = self._poser_le_rendez_vous(contexte)

        # Le document PDF : soumis a confirmation, jamais ecrit d'autorite.
        # Fait avant la generation pour que la reponse puisse le dire.
        #
        # Dernier recours avant de proposer le document : un champ encore
        # manquant apres la capture deterministe est tente par le modele
        # lui-meme (INSTRUCTION_EXTRACTION_DESTINATAIRE, choix du
        # proprietaire du 31/08/2026). Seulement quand un document est
        # reellement demande CE tour — un appel modele en plus a chaque
        # message serait du gaspillage pour un champ qui ne sert a rien
        # tant qu'aucun document n'est demande.
        compris_par_modele: List[str] = []
        if (DEMANDE_DE_DOCUMENT.search(message_actuel or "")
                and not demande_de_demonstration(message_actuel or "")):
            manquants_avant_modele = [
                champ for champ in DESTINATAIRE if not contexte.get(champ)]
            if manquants_avant_modele:
                compris = await self._destinataire_par_modele(
                    contexte.get("historique") or [], message_actuel)
                for champ, valeur in compris.items():
                    if not contexte.get(champ):
                        contexte[champ] = valeur
                        compris_par_modele.append(champ)

        document = self._proposer_le_document(message_actuel, contexte, metre)
        if document is not None and cotes_d_un_tour_precedent:
            # Jamais silencieux, meme regle que le destinataire ci-dessous :
            # un chiffre qui part chez un client se verifie avant, pas apres.
            document["cotes_reprises"] = source_lu
            document["message"] = (
                f"Cotes reprises d'un message precedent, pas de celui-ci : "
                f"{source_lu}. Verifie que c'est bien ce chantier avant de "
                f"confirmer.\n{document['message']}"
            )
        if document is not None and compris_par_modele:
            # Jamais silencieux : un champ devine par le modele doit se voir
            # avant qu'il confirme un document qui part chez un client.
            resume = ", ".join(f"{champ} = {contexte[champ]}" for champ in compris_par_modele)
            document["message"] = (
                f"Compris automatiquement dans ta phrase, verifie avant de confirmer : "
                f"{resume}.\n{document['message']}"
            )

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
            # Ce qu'un decompte de menuiseries a rendu. `None` quand aucun
            # decompte n'a ete demande (DEMANDE_DE_DECOMPTE).
            "marques": marques,
            # L'impression du modele de vision sur les memes ouvertures —
            # jamais une mesure. `None` sans modele configure ou sans decompte
            # demande.
            "avis_visuel_ouvertures": avis_visuel,
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
