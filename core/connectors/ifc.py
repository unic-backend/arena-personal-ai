"""Connecteur IFC — lecture d'un fichier IFC via IfcOpenShell, jamais un
second moteur BIM concurrent.

IfcOpenShell (IfcOpenShell/IfcOpenShell, LGPL-3.0-or-later) est utilise en
BIBLIOTHEQUE PYTHON, comme txtai ou Graphify : ce connecteur n'importe et
n'appelle que son API publique (`core/production/ifc_lecture.py`), aucune de
ses lignes n'est copiee ici. L'obligation LGPL est tenue par construction :
c'est un paquet PyPI installe tel quel, jamais vendore.

**Lecture seule.** Les trois capacites n'ecrivent jamais rien : un fichier
IFC est ouvert en memoire, interroge, ferme. Rien n'est modifie, rien n'est
exporte — DXF/IFC en sortie (section 4 de la mission) restent
`SUGGESTION — NON IMPLEMENTEE` tant qu'un besoin reel ne les demande pas.
"""
import logging
from pathlib import Path
from typing import Any, Dict

from core.actions.resultat import ResultatAction, echec, non_configure, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante, _maintenant
from core.production.ifc_lecture import TYPES_IFC, elements, niveaux, ouvrir, surface_totale

logger = logging.getLogger("usman.connecteurs.ifc")

CE_QUI_MANQUE = (
    "IfcOpenShell n'est pas installe : pip install ifcopenshell "
    "(LGPL-3.0-or-later, wheels precompiles, aucun compilateur requis)."
)

#: Au-dela, on refuse plutot que de laisser un fichier enorme bloquer le
#: processus pendant l'analyse — aucun chantier de plaquiste n'approche
#: cette taille avec un IFC correctement exporte.
TAILLE_MAX_OCTETS = 200 * 1024 * 1024


class ConnecteurIfc(Connecteur):
    """Ouvre et interroge un fichier IFC — niveaux, elements, metre des murs."""

    service = "ifc"
    nom = "ifc"

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "analyser": Capacite(
                nom="analyser", action="read",
                description="Ouvre un fichier IFC et resume ses niveaux et le compte de ses elements.",
                ecriture=False),
            "elements": Capacite(
                nom="elements", action="read",
                description="Liste les elements d'un type IFC (mur, porte, fenetre...), filtres par niveau.",
                ecriture=False),
            "metre": Capacite(
                nom="metre", action="read",
                description=(
                    "Somme la surface des murs depuis les quantites deja calculees "
                    "dans le fichier IFC — jamais une geometrie recalculee."),
                ecriture=False),
        }

    def authentifier(self) -> bool:
        """Vrai : une lecture de fichier local, aucun identifiant a presenter."""
        return True

    def sonder(self) -> Sante:
        try:
            import ifcopenshell  # noqa: F401
        except ImportError:
            return Sante(etat=EtatSante.NON_CONFIGURE, message="IfcOpenShell n'est pas installe.",
                         ce_qui_manque=CE_QUI_MANQUE, mesure_le=_maintenant())
        return Sante(etat=EtatSante.OPERATIONNEL,
                     message="IfcOpenShell est installe.", mesure_le=_maintenant())

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        chemin = str(parametres.get("chemin") or "").strip()
        if not chemin:
            return echec(action=capacite.nom, cible=self.nom,
                         message="Aucun chemin de fichier IFC fourni.")

        fichier_chemin = Path(chemin)
        if not fichier_chemin.is_file():
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"Aucun fichier a ce chemin : {chemin}")
        if fichier_chemin.suffix.lower() != ".ifc":
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"Ce fichier n'est pas un .ifc : {chemin}")
        taille = fichier_chemin.stat().st_size
        if taille > TAILLE_MAX_OCTETS:
            return echec(action=capacite.nom, cible=self.nom,
                         message=(f"Fichier IFC trop volumineux ({taille // (1024 * 1024)} Mo, "
                                  f"plafond {TAILLE_MAX_OCTETS // (1024 * 1024)} Mo)."))

        try:
            fichier = ouvrir(chemin)
        except ImportError:
            return non_configure(action=capacite.nom, cible=self.nom, ce_qui_manque=CE_QUI_MANQUE)
        except Exception as erreur:  # noqa: BLE001 — un fichier corrompu est un echec, jamais un crash
            return echec(action=capacite.nom, cible=self.nom,
                         message=f"Fichier IFC illisible : {erreur}")

        if capacite.nom == "analyser":
            return self._analyser(fichier, chemin)
        if capacite.nom == "elements":
            return self._elements(fichier, chemin, parametres)
        return self._metre(fichier, chemin, parametres)

    def _analyser(self, fichier: Any, chemin: str) -> ResultatAction:
        niveaux_trouves = niveaux(fichier)
        comptes = {mot: len(elements(fichier, type_ifc))
                  for mot, type_ifc in TYPES_IFC.items() if mot != "niveau"}
        elements_par_niveau: Dict[str, Dict[str, int]] = {}
        for mot, type_ifc in TYPES_IFC.items():
            if mot == "niveau":
                continue
            for element in elements(fichier, type_ifc):
                cle = element.niveau or "niveau inconnu"
                elements_par_niveau.setdefault(cle, {}).setdefault(mot, 0)
                elements_par_niveau[cle][mot] += 1
        return succes(
            action="analyser", cible=self.nom,
            message=(f"{len(niveaux_trouves)} niveau(x) : "
                     + ", ".join(f"{n} {mot}(s)" for mot, n in comptes.items())),
            preuve=chemin,
            niveaux=niveaux_trouves, comptes=comptes,
            elements_par_niveau=elements_par_niveau,
        )

    def _elements(self, fichier: Any, chemin: str, parametres: Dict[str, Any]) -> ResultatAction:
        mot = str(parametres.get("type") or "").strip().lower()
        type_ifc = TYPES_IFC.get(mot)
        if type_ifc is None:
            return echec(action="elements", cible=self.nom,
                        message=(f"Type inconnu : {mot!r}. Connus : "
                                 + ", ".join(sorted(TYPES_IFC)) + "."))
        niveau = parametres.get("niveau")
        trouves = elements(fichier, type_ifc, niveau=niveau)
        return succes(
            action="elements", cible=self.nom,
            message=f"{len(trouves)} {mot}(s) trouve(s)" + (f" au niveau {niveau}" if niveau else "") + ".",
            preuve=chemin,
            elements=[e.__dict__ for e in trouves],
        )

    def _metre(self, fichier: Any, chemin: str, parametres: Dict[str, Any]) -> ResultatAction:
        niveau = parametres.get("niveau")
        murs = elements(fichier, "IfcWall", niveau=niveau)
        resultat = surface_totale(murs)
        return succes(
            action="metre", cible=self.nom,
            message=(f"{resultat['surface_m2']:g} m2 chiffres sur "
                     f"{resultat['elements_chiffres']}/{len(murs)} mur(s)."),
            preuve=chemin,
            murs=len(murs), **resultat,
        )
