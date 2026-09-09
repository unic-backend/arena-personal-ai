"""Connecteur `pdf` — fusionner, scinder, réordonner, supprimer/extraire des
pages, pivoter, extraire texte/images, lire/écrire un manifeste PDFx.

Mission « PDFx » (09/09/2026) — voir `docs/audits/pdfx_audit.md`. Un seul
moteur, `pypdf`, déjà une dépendance ARENA. Chaque capacité écrit toujours
un fichier NEUF sous `media/rendered/documents/` — jamais le fichier
source, jamais le chemin de l'appelant : aucune de ces opérations ne peut
détruire un document existant, contrairement à `file_organization`
(DEC-0075) qui déplace/supprime en place.

**`extraire_texte` ne duplique aucun système.** Il délègue à
`tools/documents/reader.py::lire_document()` — le seul lecteur documentaire
d'ARENA — et enveloppe le résultat avec `core/security/trust.py`, comme
`core/production/organisation/inspection.py` (DEC-0075) : le texte d'un PDF
reste une DONNÉE, jamais une instruction (mission §19).
"""
from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from apps.backend.config import RENDERED_DIR
from core.actions.resultat import ResultatAction, echec, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante, _maintenant
from core.production.documents_pdf import operations, securite, validation
from core.production.documents_pdf.operations import OperationPdfEchouee

logger = logging.getLogger("usman.connecteurs.pdf")

DOCUMENTS_DIR_NOM = "documents"


def _nom_sortie(base: str, extension: str = "pdf") -> str:
    base = (base or "document")[:60]
    return f"{base}-{int(time.time())}-{uuid.uuid4().hex[:8]}.{extension}"


class ConnecteurPdf(Connecteur):
    """Manipule des PDF page par page — jamais un deuxième moteur PDF
    (pas de PyMuPDF, pas de pdf-lib, pas d'Electron)."""

    service = "pdf"
    nom = "pdf"

    def __init__(self, dossier: Optional[Path] = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.dossier = (Path(dossier) if dossier else RENDERED_DIR) / DOCUMENTS_DIR_NOM

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "fusionner": Capacite(
                nom="fusionner", action="document",
                description="Concatène plusieurs PDF en un seul, en manifeste PDFx si demandé.",
                ecriture=True),
            "demonter": Capacite(
                nom="demonter", action="document",
                description="Récupère les documents d'origine d'un PDFx (ou le document unique d'un PDF ordinaire).",
                ecriture=True),
            "scinder": Capacite(
                nom="scinder", action="document",
                description="Découpe un PDF en plusieurs fichiers, par groupes de pages explicites.",
                ecriture=True),
            "reordonner": Capacite(
                nom="reordonner", action="document",
                description="Réécrit un PDF avec ses pages dans un nouvel ordre.",
                ecriture=True),
            "supprimer_pages": Capacite(
                nom="supprimer_pages", action="document",
                description="Réécrit un PDF sans certaines pages.",
                ecriture=True),
            "extraire_pages": Capacite(
                nom="extraire_pages", action="document",
                description="Écrit un nouveau PDF avec seulement les pages demandées.",
                ecriture=True),
            "pivoter_pages": Capacite(
                nom="pivoter_pages", action="document",
                description="Réécrit un PDF avec certaines pages pivotées (multiples de 90°).",
                ecriture=True),
            "extraire_texte": Capacite(
                nom="extraire_texte", action="lecture",
                description="Le texte d'un PDF, via le lecteur documentaire existant.",
                ecriture=False),
            "extraire_images": Capacite(
                nom="extraire_images", action="document",
                description="Écrit sur disque les images embarquées dans un PDF.",
                ecriture=True),
            "manifeste": Capacite(
                nom="manifeste", action="lecture",
                description="Lit le manifeste PDFx d'un fichier, s'il en a un.",
                ecriture=False),
        }

    def authentifier(self) -> bool:
        return True

    def sonder(self) -> Sante:
        try:
            import pypdf  # noqa: F401
        except ImportError as erreur:
            return Sante(etat=EtatSante.NON_CONFIGURE, message="pypdf n'est pas installé.",
                        ce_qui_manque=f"pip install pypdf ({erreur})", mesure_le=_maintenant())
        return Sante(etat=EtatSante.OPERATIONNEL, message="pypdf installé.", mesure_le=_maintenant())

    # --- Garde commune ---------------------------------------------------------------

    def _ouvrir(self, chemin: Any) -> Any:
        """`(chemin résolu, None)` ou `(None, ResultatAction d'échec)`."""
        resolu, raison = securite.chemin_source_est_sur(str(chemin or ""))
        if raison:
            return None, echec(self.nom, self.nom, f"Fichier refusé : {raison}.")
        taille_invalide = securite.taille_acceptable(resolu)
        if taille_invalide:
            return None, echec(self.nom, self.nom, f"Fichier refusé : {taille_invalide}.")
        incoherent = securite.format_source_coherent(resolu)
        if incoherent:
            return None, echec(self.nom, self.nom, f"Fichier refusé : {incoherent}.")
        return resolu, None

    def _url(self, sortie: Path) -> Optional[str]:
        if self.dossier.parent == RENDERED_DIR:
            return f"/media/rendered/{DOCUMENTS_DIR_NOM}/{sortie.name}"
        return None

    # --- fusionner ---------------------------------------------------------------

    def _fusionner(self, fichiers: Any, titre: Any, noms: Any, format_pdfx: Any) -> ResultatAction:
        if not isinstance(fichiers, list) or not fichiers:
            return echec("fusionner", self.nom, "`fichiers` doit être une liste non vide.")

        resolus: List[Path] = []
        for f in fichiers:
            resolu, erreur = self._ouvrir(f)
            if erreur:
                return erreur
            resolus.append(resolu)

        self.dossier.mkdir(parents=True, exist_ok=True)
        sortie = self.dossier / _nom_sortie(str(titre).strip() if titre else "fusion")
        try:
            detail = operations.fusionner(
                resolus, sortie, titre=str(titre or ""),
                noms=list(noms) if isinstance(noms, list) else None,
                format_pdfx=bool(format_pdfx))
        except OperationPdfEchouee as erreur:
            return echec("fusionner", self.nom, str(erreur))

        raison_invalide = validation.verifier(sortie, detail["total_pages"])
        if raison_invalide:
            sortie.unlink(missing_ok=True)
            return echec("fusionner", self.nom, f"Sortie invalide : {raison_invalide}.")

        extra: Dict[str, Any] = {"documents": detail["documents"], "total_pages": detail["total_pages"],
                                 "format_pdfx": bool(format_pdfx)}
        url = self._url(sortie)
        if url:
            extra["url"] = url
        return succes(
            "fusionner", self.nom,
            message=f"{len(resolus)} fichier(s) fusionnés en « {sortie.name} » "
                    f"({detail['total_pages']} page(s))"
                    + (", format PDFx." if format_pdfx else "."),
            preuve=str(sortie), **extra)

    # --- demonter ------------------------------------------------------------------

    def _demonter(self, fichier: Any) -> ResultatAction:
        resolu, erreur = self._ouvrir(fichier)
        if erreur:
            return erreur

        dossier_sortie = self.dossier / f"demonte-{resolu.stem}-{int(time.time())}"
        try:
            resultats = operations.demonter(resolu, dossier_sortie)
        except OperationPdfEchouee as erreur:
            return echec("demonter", self.nom, str(erreur))

        for r in resultats:
            raison_invalide = validation.verifier(Path(r["fichier"]), r["pages"])
            if raison_invalide:
                return echec("demonter", self.nom,
                            f"Sortie invalide pour « {r['name']} » : {raison_invalide}.")

        return succes(
            "demonter", self.nom,
            message=f"« {resolu.name} » démonté en {len(resultats)} document(s).",
            preuve=str(dossier_sortie), documents=resultats)

    # --- scinder ---------------------------------------------------------------------

    def _scinder(self, fichier: Any, groupes: Any) -> ResultatAction:
        resolu, erreur = self._ouvrir(fichier)
        if erreur:
            return erreur
        if not isinstance(groupes, list) or not groupes:
            return echec("scinder", self.nom, "`groupes` doit être une liste non vide de listes de pages.")

        try:
            n = operations.nombre_de_pages(resolu)
        except OperationPdfEchouee as erreur:
            return echec("scinder", self.nom, str(erreur))
        for groupe in groupes:
            invalide = securite.indices_valides(list(groupe), n)
            if invalide:
                return echec("scinder", self.nom, f"Groupe refusé : {invalide}.")

        dossier_sortie = self.dossier / f"scinde-{resolu.stem}-{int(time.time())}"
        try:
            resultats = operations.scinder(resolu, [list(g) for g in groupes], dossier_sortie)
        except OperationPdfEchouee as erreur:
            return echec("scinder", self.nom, str(erreur))

        for r in resultats:
            raison_invalide = validation.verifier(Path(r["fichier"]), r["pages"])
            if raison_invalide:
                return echec("scinder", self.nom, f"Sortie invalide : {raison_invalide}.")

        return succes(
            "scinder", self.nom,
            message=f"« {resolu.name} » scindé en {len(resultats)} fichier(s).",
            preuve=str(dossier_sortie), fichiers=resultats)

    # --- reordonner / supprimer_pages / extraire_pages / pivoter_pages -------------

    def _operation_pages(self, capacite: str, fichier: Any, pages_brut: Any,
                         extra_params: Dict[str, Any]) -> ResultatAction:
        resolu, erreur = self._ouvrir(fichier)
        if erreur:
            return erreur
        if not isinstance(pages_brut, list) or not pages_brut:
            return echec(capacite, self.nom, "`pages` (ou `ordre`) doit être une liste non vide d'indices.")

        try:
            n = operations.nombre_de_pages(resolu)
        except OperationPdfEchouee as erreur:
            return echec(capacite, self.nom, str(erreur))
        invalide = securite.indices_valides(list(pages_brut), n)
        if invalide:
            return echec(capacite, self.nom, f"Refusé : {invalide}.")

        self.dossier.mkdir(parents=True, exist_ok=True)
        sortie = self.dossier / _nom_sortie(resolu.stem)
        fonction = {
            "reordonner": lambda: operations.reordonner(resolu, list(pages_brut), sortie),
            "supprimer_pages": lambda: operations.supprimer_pages(resolu, list(pages_brut), sortie),
            "extraire_pages": lambda: operations.extraire_pages(resolu, list(pages_brut), sortie),
            "pivoter_pages": lambda: operations.pivoter_pages(
                resolu, list(pages_brut), int(extra_params.get("degres", 90)), sortie),
        }[capacite]

        try:
            n_pages_sortie = fonction()
        except OperationPdfEchouee as erreur:
            return echec(capacite, self.nom, str(erreur))

        raison_invalide = validation.verifier(sortie)
        if raison_invalide:
            sortie.unlink(missing_ok=True)
            return echec(capacite, self.nom, f"Sortie invalide : {raison_invalide}.")

        detail: Dict[str, Any] = {"pages_sortie": n_pages_sortie, "pages_source": n}
        url = self._url(sortie)
        if url:
            detail["url"] = url
        return succes(capacite, self.nom,
                     message=f"« {resolu.name} » -> « {sortie.name} » ({n_pages_sortie} page(s)).",
                     preuve=str(sortie), **detail)

    # --- extraire_texte --------------------------------------------------------------

    def _extraire_texte(self, fichier: Any) -> ResultatAction:
        resolu, erreur = self._ouvrir(fichier)
        if erreur:
            return erreur

        from tools.documents.reader import lire_document
        document = lire_document(resolu)
        if not document.lu:
            return echec("extraire_texte", self.nom,
                        f"Document non lu ({document.statut}) : {document.raison or 'raison inconnue'}.")

        from core.security.trust import TrustLevel, wrap
        enveloppe = wrap(document.texte, TrustLevel.DOCUMENT, origin=resolu.name)
        return succes("extraire_texte", self.nom,
                     message=f"Texte extrait de « {resolu.name} » ({document.caracteres} caractère(s)).",
                     preuve=resolu.name, texte=enveloppe.text,
                     motifs_suspects=enveloppe.suspicions)

    # --- extraire_images -------------------------------------------------------------

    def _extraire_images(self, fichier: Any) -> ResultatAction:
        resolu, erreur = self._ouvrir(fichier)
        if erreur:
            return erreur

        dossier_sortie = self.dossier / f"images-{resolu.stem}-{int(time.time())}"
        try:
            resultats = operations.extraire_images(resolu, dossier_sortie)
        except OperationPdfEchouee as erreur:
            return echec("extraire_images", self.nom, str(erreur))

        reussites = [r for r in resultats if "fichier" in r]
        return succes(
            "extraire_images", self.nom,
            message=f"{len(reussites)} image(s) extraite(s) de « {resolu.name} ».",
            preuve=str(dossier_sortie), images=resultats)

    # --- manifeste ---------------------------------------------------------------------

    def _manifeste(self, fichier: Any) -> ResultatAction:
        resolu, erreur = self._ouvrir(fichier)
        if erreur:
            return erreur

        try:
            manifeste = operations.lire_manifeste(resolu)
        except OperationPdfEchouee as erreur:
            return echec("manifeste", self.nom, str(erreur))

        if manifeste is None:
            return succes("manifeste", self.nom,
                         message=f"« {resolu.name} » n'a pas de manifeste PDFx — "
                                 f"document unique (SPEC.md : un PDF ordinaire est un PDFx valide).",
                         preuve=resolu.name, a_un_manifeste=False)
        return succes("manifeste", self.nom,
                     message=f"« {resolu.name} » : {len(manifeste['documents'])} document(s) au manifeste.",
                     preuve=resolu.name, a_un_manifeste=True, manifeste=manifeste)

    # --- Dispatch --------------------------------------------------------------------

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        if capacite.nom == "fusionner":
            return self._fusionner(parametres.get("fichiers"), parametres.get("titre"),
                                   parametres.get("noms"), parametres.get("format_pdfx"))
        if capacite.nom == "demonter":
            return self._demonter(parametres.get("fichier"))
        if capacite.nom == "scinder":
            return self._scinder(parametres.get("fichier"), parametres.get("groupes"))
        if capacite.nom in ("reordonner", "supprimer_pages", "extraire_pages", "pivoter_pages"):
            champ = "ordre" if capacite.nom == "reordonner" else "pages"
            return self._operation_pages(capacite.nom, parametres.get("fichier"),
                                         parametres.get(champ), parametres)
        if capacite.nom == "extraire_texte":
            return self._extraire_texte(parametres.get("fichier"))
        if capacite.nom == "extraire_images":
            return self._extraire_images(parametres.get("fichier"))
        if capacite.nom == "manifeste":
            return self._manifeste(parametres.get("fichier"))
        return echec(capacite.nom, self.nom, "Capacité non câblée.")
