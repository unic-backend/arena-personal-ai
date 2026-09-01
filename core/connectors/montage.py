"""Le connecteur de montage : la timeline d'ARENA, atteignable depuis une phrase.

Sans ce fichier, `core/montage/` serait exactement ce que la mission
interdit — un moteur ecrit, teste, et que rien ne fait tourner. Il donne au
montage sa place dans l'architecture existante : declare dans le registre,
soumis a la meme politique de permission que le reste, et **derriere la meme
confirmation** que le devis PDF ou l'envoi d'un courrier.

**Trois regles, toutes heritees du projet :**

1. **Composer ne coute rien, rendre est une ecriture.** Batir une timeline
   et la relire est libre ; produire un fichier video demande une
   confirmation du proprietaire.

2. **Le succes est le fichier, pas la commande.** `rendre()` re-sonde sa
   sortie avec ffprobe et compare la duree obtenue a celle du projet
   (`core/montage/rendu.py`). Un `SUCCES` sans preuve ne se construit pas
   (`core/actions/resultat.py`).

3. **Le plan de montage vient de l'appelant, jamais d'une invention.** Ce
   connecteur n'ecrit aucune timeline de lui-meme : il execute celle qu'on
   lui donne, operation par operation, et refuse celles qui ne tiennent pas.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.actions.resultat import ResultatAction, echec, non_configure, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante
from core.montage.operations import Montage
from core.montage.projet import Projet
from core.montage.rendu import rendre

logger = logging.getLogger("usman.connecteurs.montage")

#: Ou les videos montees sont ecrites. Une video produite doit se retrouver.
DOSSIER_RENDUS = Path("data") / "montages"

CE_QUI_MANQUE = ("ffmpeg, introuvable sur cette machine. Sans lui, ARENA peut "
                 "batir une timeline mais ne peut rien rendre.")


class ConnecteurMontage(Connecteur):
    """Batir une timeline, la relire, et la rendre en video."""

    service = "video_montage"
    nom = "montage"

    def __init__(self, dossier: Optional[Path] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.dossier = Path(dossier) if dossier else DOSSIER_RENDUS

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "composer": Capacite(
                nom="composer", action="read",
                description="Bâtit une timeline depuis une suite d'opérations, sans rien écrire.",
                ecriture=False),
            "rendre": Capacite(
                nom="rendre", action="document",
                description="Rend la timeline en fichier vidéo, vérifié après écriture.",
                ecriture=True),
        }

    def sonder(self) -> Sante:
        """ffmpeg est-il la ? Sans lui, aucun rendu — et on le dit."""
        from core.connectors.base import _maintenant

        binaire = shutil.which("ffmpeg")
        if not binaire:
            return Sante(etat=EtatSante.NON_CONFIGURE,
                         message="ffmpeg absent : la timeline se bâtit, rien ne se rend.",
                         ce_qui_manque=CE_QUI_MANQUE, mesure_le=_maintenant())
        return Sante(etat=EtatSante.OPERATIONNEL,
                     message=f"ffmpeg présent ({binaire}) : montage et rendu possibles.",
                     mesure_le=_maintenant())

    def authentifier(self) -> bool:
        """Vrai : tout est local, il n'y a aucun identifiant a presenter."""
        return True

    # --- Le coeur -------------------------------------------------------------------

    def _appliquer(self, operations: List[Dict[str, Any]]) -> tuple:
        """Rejoue une suite d'operations. Rend `(Montage, erreurs)`.

        Une operation qui echoue N'ARRETE PAS les suivantes : le compte-rendu
        les nomme toutes. Un modele qui se trompe sur une ligne doit voir
        laquelle, pas perdre tout son plan.
        """
        montage = Montage()
        erreurs: List[str] = []
        for numero, brute in enumerate(operations, start=1):
            nom = str(brute.get("operation") or "")
            methode = getattr(montage, nom, None)
            if nom.startswith("_") or not callable(methode) or nom not in OPERATIONS_OUVERTES:
                erreurs.append(f"#{numero} : opération inconnue « {nom} »")
                continue
            parametres = {c: v for c, v in brute.items() if c != "operation"}
            try:
                resultat = methode(**parametres)
            except TypeError as erreur:
                erreurs.append(f"#{numero} {nom} : paramètres invalides ({erreur})")
                continue
            if not resultat.ok:
                erreurs.append(f"#{numero} {nom} : {resultat.message}")
        return montage, erreurs

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        operations = parametres.get("operations")
        if not isinstance(operations, list) or not operations:
            return echec(action=capacite.nom, cible=self.nom,
                         message="Aucune opération de montage fournie : rien à faire.")

        montage, erreurs = self._appliquer(operations)
        if montage.projet is None:
            return echec(action=capacite.nom, cible=self.nom,
                         message="Aucun projet n'a été créé : " + (
                             erreurs[0] if erreurs else "plan vide."))

        resume = montage.resumer()
        if capacite.nom == "composer":
            return succes(
                action=capacite.nom, cible=self.nom, message=resume.message,
                preuve=f"{montage.projet.duree_ms} ms sur {len(montage.projet.pistes)} piste(s)",
                projet=montage.projet.to_dict(), erreurs=erreurs, **resume.detail)

        # Rendre : le fichier part sur le disque, donc derriere confirmation.
        if montage.projet.duree_ms <= 0:
            return echec(action=capacite.nom, cible=self.nom,
                         message="La timeline est vide : il n'y a rien à rendre.",
                         erreurs=erreurs)
        if not shutil.which("ffmpeg"):
            return non_configure(action=capacite.nom, cible=self.nom,
                                 ce_qui_manque=CE_QUI_MANQUE)

        self.dossier.mkdir(parents=True, exist_ok=True)
        sortie = self.dossier / f"{montage.projet.identifiant}.mp4"
        rendu = rendre(montage.projet, sortie)
        # `to_dict()` porte deja `ok` et `message` : les splatter ici les
        # ferait entrer en collision avec les arguments explicites de
        # `echec`/`succes`. Seuls les champs MESURES sur le fichier voyagent.
        mesures = {c: v for c, v in rendu.to_dict().items()
                   if c not in ("ok", "message")}
        if not rendu.ok:
            return echec(action=capacite.nom, cible=self.nom, message=rendu.message,
                         erreurs=erreurs, **mesures)

        # Le projet est ecrit a cote de la video : le proprietaire peut le
        # relire, le modifier, et demander un nouveau rendu sans repartir de zero.
        chemin_projet = sortie.with_suffix(".json")
        montage.projet.ecrire(chemin_projet)
        return succes(
            action=capacite.nom, cible=self.nom, message=rendu.message,
            preuve=rendu.chemin, projet_json=str(chemin_projet),
            erreurs=erreurs, **mesures)


#: Les operations qu'un appelant a le droit de demander. Liste fermee : un
#: modele ne doit pas pouvoir appeler n'importe quelle methode de `Montage`
#: en devinant son nom — c'est la « couche d'operations structurees » que la
#: mission exige, et elle ne vaut que si elle est vraiment fermee.
OPERATIONS_OUVERTES = frozenset({
    "creer_projet", "importer_media", "ajouter_piste", "ajouter_clip",
    "ajouter_texte", "couper_clip", "retirer_element", "definir_format",
})


def projet_depuis(donnees: Dict[str, Any]) -> Projet:
    """Relit un projet rendu precedemment, pour le reprendre.

    Le montage reste editable entre deux tours : c'est ce que la mission
    demande par « preserve an editable project representation ».
    """
    return Projet.depuis_dict(donnees)
