"""Produire un devis UniC Plaquiste : chiffrer d'abord, ecrire ensuite.

`agents/plaquiste/devis_pdf.py` sait rendre un devis a la charte de
l'entreprise depuis le premier jour, et **personne ne l'appelait** — mesure du
2026-08-28, il n'apparaissait dans aucun chemin de reponse. Le proprietaire
demandait un devis et recevait du texte.

Ce connecteur ferme la boucle du metier : dimensions lues dans la phrase →
quantites calculees depuis ses ratios reels → lignes chiffrees depuis sa grille
de prix → document PDF.

**Quatre regles :**

1. **Chiffrer ne coute rien, produire est une ecriture.** Voir le total avant
   d'ecrire un fichier est libre ; ecrire le document qui partira chez un
   client demande une confirmation.

2. **Aucun prix ne vient de l'appelant.** Les prix sortent de la grille du
   fichier metier, et un article absent de la grille est **nomme**, jamais
   chiffre au jugé. C'est deja la regle de `chiffrer()` ; ce connecteur ne
   l'affaiblit pas.

3. **Le nom du client n'est jamais devine.** Sans client, sans lieu et sans
   objet, rien n'est produit : un devis adresse a la mauvaise personne est pire
   qu'un devis absent.

4. **Le fichier existe, ou il n'y a pas de succes.** La preuve du succes est le
   chemin du PDF ecrit, verifie sur le disque.
"""
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from agents.plaquiste.calcul_materiaux import quantites_pour
from agents.plaquiste.devis_pdf import Devis, Ligne, chiffrer, construire
from agents.plaquiste.metre import lire_demande
from agents.plaquiste.plaquiste_agent import MetierSuivi
from core.actions.resultat import ResultatAction, echec, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante

logger = logging.getLogger("usman.connecteurs.devis")

#: Ou les documents sont ecrits. Un devis produit doit se retrouver.
DOSSIER_DEVIS = Path("data") / "devis"


def lignes_depuis_parametres(brutes: List[Dict[str, Any]]) -> List[Ligne]:
    """Des postes deja calcules ailleurs (metre d'un plan mesure, par exemple),
    fournis tels quels par l'appelant.

    Mesure du 30/08/2026 : sans ce chemin, `produire` ne savait relire une
    demande QUE depuis la phrase tapee (`lignes_depuis` ci-dessous) — un devis
    demande apres la mesure d'un PLAN echouait a la confirmation avec
    « aucune dimension lue », alors que le plan en donnait une. L'appelant
    (`PlaquisteAgent`) a deja le metre calcule ; il n'a plus a le faire
    redire par une phrase.
    """
    return [Ligne(designation=str(brute["designation"]), quantite=brute["quantite"])
            for brute in brutes]


def lignes_depuis(demande_texte: str, metier: Dict[str, Any]) -> List[Ligne]:
    """Les postes du devis, calcules depuis les dimensions lues.

    Rend une liste vide quand aucune dimension n'est reconnue : un devis sans
    metre ne s'invente pas. Reste le chemin de repli quand l'appelant n'a
    fourni aucune ligne deja calculee (voir `lignes_depuis_parametres`).
    """
    dimensions = lire_demande(demande_texte)
    if dimensions is None:
        return []
    calcul = quantites_pour(
        dimensions.surface, metier, faces=dimensions.faces,
        parois=dimensions.parois, deja_developpee=dimensions.deja_developpee)
    return [Ligne(designation=besoin.article, quantite=besoin.quantite)
            for besoin in calcul.besoins]


class DevisConnector(Connecteur):
    """Chiffrage et production du devis PDF d'UniC Plaquiste."""

    service = "plaquiste"
    nom = "devis"

    def __init__(self, metier: Optional[Dict[str, Any]] = None,
                 dossier: Optional[Path] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        # Meme suivi que l'agent : un prix change dans le fichier metier est
        # vu au chiffrage suivant, pas au prochain redemarrage du serveur.
        self._metier_injecte = metier
        self._metier_suivi = None if metier is not None else MetierSuivi()

        self.dossier = Path(dossier) if dossier else DOSSIER_DEVIS

    @property
    def metier(self) -> Dict[str, Any]:
        """Les connaissances metier, relues si le fichier a change."""
        if self._metier_injecte is not None:
            return self._metier_injecte
        return self._metier_suivi.actuel()

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "chiffrer": Capacite(
                nom="chiffrer", action="read",
                description="Chiffre un devis depuis les dimensions, sans rien ecrire.",
                ecriture=False),
            "produire": Capacite(
                nom="produire", action="document",
                description="Ecrit le devis PDF a la charte UniC Plaquiste.",
                ecriture=True),
        }

    def sonder(self) -> Sante:
        """La grille de prix est-elle la ? Sans elle, rien ne se chiffre."""
        from core.connectors.base import _maintenant

        grille = dict((self.metier or {}).get("prix_materiaux") or {})
        if not grille:
            return Sante(
                etat=EtatSante.NON_CONFIGURE,
                message="Aucune grille de prix : config/unic_plaquiste.yaml est vide ou absent.",
                ce_qui_manque="config/unic_plaquiste.yaml avec sa section prix_materiaux",
                mesure_le=_maintenant())
        return Sante(
            etat=EtatSante.OPERATIONNEL,
            message=f"Grille de prix chargee : {len(grille)} article(s).",
            mesure_le=_maintenant())

    def authentifier(self) -> bool:
        """Vrai : tout est local, il n'y a aucun identifiant a presenter."""
        return True

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        texte = str(parametres.get("demande") or "")
        lignes_brutes = parametres.get("lignes")
        lignes = (lignes_depuis_parametres(lignes_brutes) if lignes_brutes
                  else lignes_depuis(texte, self.metier))
        if not lignes:
            return echec(
                action=capacite.nom, cible=self.nom,
                message=("Aucune dimension lue dans la demande : je ne chiffre rien. "
                         "Donne une surface ou des parois avec leurs cotes."))

        devis = Devis(
            client=str(parametres.get("client") or ""),
            lieu=str(parametres.get("lieu") or ""),
            objet=str(parametres.get("objet") or ""),
            lignes=lignes,
            main_oeuvre_m2=parametres.get("main_oeuvre_m2"),
            # Le renderer (devis_pdf.py) accepte deja un type libre ; seul
            # l'appelant decide. "DEVIS" par defaut : tous les appelants
            # existants (avant l'orchestration d'une facture) n'y touchent pas.
            type_document=str(parametres.get("type_document") or "DEVIS"),
        )
        calcul = chiffrer(devis, self.metier)

        if capacite.nom == "chiffrer":
            return succes(
                action=capacite.nom, cible=self.nom,
                message=(f"{len(lignes)} poste(s), total {calcul['total']} FCFA "
                         f"({len(calcul['articles_sans_prix'])} sans prix)."),
                preuve=f"{calcul['total']} FCFA sur {len(lignes)} poste(s)",
                chiffrage=calcul)

        # Produire : le document part chez un client. Sans destinataire, non.
        manquants = [nom for nom in ("client", "lieu", "objet") if not getattr(devis, nom)]
        if manquants:
            return echec(
                action=capacite.nom, cible=self.nom,
                message=("Rien n'est produit : il manque " + ", ".join(manquants)
                         + ". Un devis adresse a la mauvaise personne est pire "
                           "qu'un devis absent."))

        self.dossier.mkdir(parents=True, exist_ok=True)
        sortie = self.dossier / f"{devis.numero.replace('/', '-')}.pdf"
        try:
            construire(devis, self.metier, sortie)
        except Exception as erreur:  # noqa: BLE001 — l'echec se rapporte
            logger.info("Devis non produit : %s", erreur)
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"Le document n'a pas pu etre ecrit : {type(erreur).__name__}.")

        if not sortie.exists():
            return echec(action=capacite.nom, cible=self.nom,
                         message="Le rendu s'est termine sans laisser de fichier.")

        return succes(
            action=capacite.nom, cible=self.nom,
            message=(f"{devis.type_document.capitalize()} {devis.numero} ecrit pour "
                     f"{devis.client} ({calcul['total']} FCFA)."),
            preuve=str(sortie),
            chiffrage=calcul, octets=sortie.stat().st_size)
