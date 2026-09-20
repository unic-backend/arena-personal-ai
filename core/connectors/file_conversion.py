"""Connecteur `file_conversion` — un fichier fourni, converti par le
meilleur moteur réellement disponible, jamais un deuxième moteur vidéo/PDF
parallèle à ce qu'ARENA a déjà.

Mission « File_Converter_Pro » (08/09/2026) — voir `docs/audits/
file_converter_pro_audit.md` pour l'audit complet, la comparaison, et ce qui
n'a délibérément PAS été repris. Ce connecteur est la SEULE porte d'entrée :
`core/production/conversion/` fait le travail (registre des moteurs, garde
de sécurité, validation réelle, lot en tâche de fond), rien de tout ça n'est
appelable en dehors de ce connecteur.

**Model-agnostic par construction** : ce connecteur ne connaît aucun modèle.
Il vit dans le registre (`RegistreConnecteurs`), atteignable par
`registre.executer("file_conversion", ...)` depuis n'importe quel agent qui
détient le registre — Dioumtoukay aujourd'hui, n'importe quel autre demain,
sans qu'aucun n'ait besoin de savoir que LibreOffice, Pillow ou ffmpeg
existent.

**Quatre règles :**

1. **La sortie n'est jamais le chemin de l'appelant.** Toujours un nom neuf
   sous `media/rendered/conversions/` — ferme l'écrasement ET la traversée
   de chemin en écriture sans avoir à les détecter (voir `securite.py`).

2. **Un succès exige un fichier relu, jamais un code de retour.**
   `validation.verifier()` rouvre la sortie dans son propre format avant
   qu'un `SUCCES` ne soit rendu — un moteur externe qui rend 0 sans écrire
   (mesuré chez LibreOffice, voir `moteurs.py`) devient un `ECHEC`, pas un
   succès silencieusement faux.

3. **Un format non enregistré et un format enregistré mais indisponible
   sont deux réponses différentes.** Le premier n'a pas de chemin de code
   (`NON_IMPLEMENTE`) ; le second manque une dépendance sur CETTE machine
   (`NON_CONFIGURE`, avec ce qui manque). Confondre les deux ferait
   chercher une clé API là où il fallait `apt install libreoffice-writer`.

4. **Le lot réutilise `convertir()`, jamais une deuxième logique.** Chaque
   fichier d'un lot passe par la même fonction que la conversion à l'unité —
   `core/production/conversion/lot.py` ne fait qu'itérer et rapporter la
   progression, en tâche de fond (`core/execution/travaux.py`, déjà
   existant : pas un second ordonnanceur).
"""
from __future__ import annotations

import logging
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from apps.backend.config import RENDERED_DIR
from core.actions.resultat import ResultatAction, echec, non_configure, non_implemente, succes
from core.connectors.base import Capacite, Connecteur, EtatSante, Sante, _maintenant
from core.execution.travaux import FileDeTravaux
from core.production.conversion import lot as lot_module
from core.production.conversion import registre, securite, validation
from core.production.conversion.moteurs import MoteurEchec, texte_vers_html

logger = logging.getLogger("usman.connecteurs.file_conversion")

CONVERSIONS_DIR_NOM = "conversions"

#: Les trois formats qu'ARENA sait ECRIRE sans appeler le moindre moteur :
#: le texte est déjà dans ce format, il ne reste qu'à le poser sur disque.
#: Tout le reste (`pdf`, `docx`…) part de l'un d'eux et passe par
#: `_convertir_un_fichier` — la même fonction que la conversion d'un fichier
#: fourni, jamais une deuxième implémentation.
FORMATS_TEXTE = ("md", "txt", "html")

#: Le format dans lequel un modèle écrit quand on ne lui dit rien : il
#: produit du markdown spontanément, et `md -> pdf` a un moteur ici.
FORMAT_SOURCE_DEFAUT = "md"

#: Un texte plus long que ça n'est pas une réponse, c'est une boucle. Le
#: plafond de `securite.TAILLE_MAX_DEFAUT_OCTETS` (300 Mo) protège la
#: conversion d'un fichier vidéo fourni ; il ne dit rien d'utile sur du
#: texte écrit par un modèle, où 5 Mo valent déjà des centaines de pages.
TEXTE_MAX_OCTETS = 5 * 1024 * 1024


#: Ce qu'un nom de fichier garde d'un titre : lettres, chiffres, tiret. Le
#: reste devient un tiret — accents compris, parce qu'un « é » dans un nom de
#: fichier téléchargé se transforme en mojibake selon le téléphone qui le
#: reçoit, et un document illisible dans la liste des téléchargements est un
#: document perdu.
_NON_RETENU = re.compile(r"[^a-z0-9]+")

#: Normalisation des accents avant le filtre : « Résumé » doit donner
#: « resume », pas « r-sum ».
_ACCENTS = str.maketrans(
    "àâäáãåçéèêëíìîïñóòôöõúùûüýÿ", "aaaaaaceeeeiiiinooooouuuuyy")


def _slug(titre: Any) -> str:
    """Un titre libre, réduit à un nom de fichier lisible dans une liste de
    téléchargements. Sans titre exploitable : « document »."""
    brut = str(titre or "").strip().lower().translate(_ACCENTS)
    propre = _NON_RETENU.sub("-", brut).strip("-")[:60].strip("-")
    return propre or "document"


def _nom_sortie(entree: Path, format_cible: str) -> str:
    """Un nom neuf, jamais celui d'un fichier existant — timestamp + id court
    suffisent, la lisibilité (garder le nom d'origine en préfixe) aide au
    tri manuel dans `media/rendered/conversions/`."""
    base = entree.stem[:60] or "fichier"
    return f"{base}-{int(time.time())}-{uuid.uuid4().hex[:8]}.{format_cible}"


class ConnecteurFileConversion(Connecteur):
    """Convertit un fichier fourni vers un autre format, via le meilleur
    moteur réellement disponible — jamais un moteur inventé pour l'occasion."""

    service = "file_conversion"
    nom = "file_conversion"

    def __init__(
        self, dossier: Optional[Path] = None,
        travaux: Optional[FileDeTravaux] = None, **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.dossier = (Path(dossier) if dossier else RENDERED_DIR) / CONVERSIONS_DIR_NOM
        # Sans file de fond, `convertir_lot` retombe sur une conversion
        # synchrone, fichier par fichier — plus lent pour l'appelant, jamais
        # un lot qui échoue à se soumettre pour autant.
        self.travaux = travaux

    def capacites(self) -> Dict[str, Capacite]:
        return {
            "convertir": Capacite(
                nom="convertir", action="document",
                description="Convertit un fichier fourni vers un autre format.",
                ecriture=True),
            "rediger": Capacite(
                nom="rediger", action="document",
                description="Écrit un texte dans un document téléchargeable "
                            "(PDF, DOCX, Markdown…) et rend son lien.",
                ecriture=True),
            "compresser": Capacite(
                nom="compresser", action="document",
                description="Regroupe plusieurs fichiers fournis dans une archive ZIP.",
                ecriture=True),
            "extraire": Capacite(
                nom="extraire", action="document",
                description="Extrait une archive ZIP fournie, avec garde anti zip-bomb/évasion.",
                ecriture=True),
            "convertir_lot": Capacite(
                nom="convertir_lot", action="document",
                description="Convertit plusieurs fichiers vers le même format, en tâche de fond.",
                ecriture=True),
            "etat_lot": Capacite(
                nom="etat_lot", action="lecture",
                description="Avancement d'une conversion en lot déjà soumise.",
                ecriture=False),
            "formats_disponibles": Capacite(
                nom="formats_disponibles", action="lecture",
                description="La matrice réelle des conversions possibles sur cette machine.",
                ecriture=False),
        }

    def authentifier(self) -> bool:
        return True  # aucun service distant, rien à authentifier

    def sonder(self) -> Sante:
        matrice = registre.matrice_disponibilite()
        disponibles = [ligne for ligne in matrice if ligne["disponible"]]
        if not disponibles:
            return Sante(
                etat=EtatSante.NON_CONFIGURE,
                message="Aucun moteur de conversion n'est disponible sur cette machine.",
                ce_qui_manque="au moins un de : LibreOffice, Pillow, WeasyPrint, ffmpeg "
                              "(zipfile, lui, est toujours présent — sa présence seule "
                              "ne devrait normalement jamais manquer)",
                mesure_le=_maintenant())
        return Sante(
            etat=EtatSante.OPERATIONNEL,
            message=f"{len(disponibles)}/{len(matrice)} couple(s) de formats déclarés "
                    f"ont un moteur disponible maintenant.",
            mesure_le=_maintenant())

    # --- Le coeur, partagé entre `convertir` et le lot -----------------------

    def _convertir_un_fichier(self, chemin: str, format_cible: str) -> ResultatAction:
        """Convertit UN fichier. Utilisé directement par `_executer('convertir', ...)`
        ET par `core.production.conversion.lot` pour chaque fichier d'un lot —
        jamais deux implémentations de la même conversion.
        """
        format_cible = str(format_cible or "").lower().lstrip(".")
        if not format_cible:
            return echec("convertir", self.nom, "`format_cible` est requis.")

        entree, raison = securite.chemin_source_est_sur(str(chemin or ""))
        if raison:
            return echec("convertir", self.nom, f"Fichier refusé : {raison}.")

        taille_invalide = securite.taille_acceptable(entree)
        if taille_invalide:
            return echec("convertir", self.nom, f"Fichier refusé : {taille_invalide}.")

        format_source = entree.suffix.lstrip(".").lower()
        if format_source == format_cible:
            return echec("convertir", self.nom,
                         f"Le fichier est déjà au format .{format_cible}.")

        moteurs = registre.moteurs_pour(format_source, format_cible)
        if not moteurs:
            return non_implemente(
                "convertir", self.nom,
                f"Aucun moteur ARENA ne convertit .{format_source} vers .{format_cible} "
                f"aujourd'hui. Rien n'a été tenté.")

        incoherence = securite.format_source_coherent(entree, format_source)
        if incoherence:
            return echec("convertir", self.nom, f"Fichier refusé : {incoherence}.")

        disponibles = [m for m in moteurs if m.disponible()[0]]
        if not disponibles:
            manques = "; ".join(f"{m.moteur_id} : {m.disponible()[1]}" for m in moteurs)
            return non_configure("convertir", self.nom, manques)

        self.dossier.mkdir(parents=True, exist_ok=True)
        sortie = self.dossier / _nom_sortie(entree, format_cible)

        erreurs_moteurs: List[str] = []
        for moteur in disponibles:
            try:
                moteur.convertir(entree, sortie)
            except MoteurEchec as erreur:
                erreurs_moteurs.append(f"{moteur.moteur_id} : {erreur}")
                sortie.unlink(missing_ok=True)
                continue
            except Exception as erreur:  # noqa: BLE001 — un moteur externe peut lever n'importe quoi
                erreurs_moteurs.append(f"{moteur.moteur_id} (erreur inattendue) : {erreur}")
                sortie.unlink(missing_ok=True)
                continue

            raison_invalide = validation.verifier(sortie, format_cible)
            if raison_invalide:
                erreurs_moteurs.append(f"{moteur.moteur_id} : sortie invalide ({raison_invalide})")
                sortie.unlink(missing_ok=True)
                continue

            taille_avant = entree.stat().st_size
            taille_apres = sortie.stat().st_size
            url = f"/media/rendered/{CONVERSIONS_DIR_NOM}/{sortie.name}" \
                if self.dossier.parent == RENDERED_DIR else None
            detail: Dict[str, Any] = {
                "moteur": moteur.moteur_id, "format_source": format_source,
                "format_cible": format_cible,
                "taille_avant_octets": taille_avant, "taille_apres_octets": taille_apres,
                "fallback_utilise": moteur is not disponibles[0],
            }
            if moteur.limites_qualite:
                detail["limites_qualite"] = moteur.limites_qualite
            if url:
                detail["url"] = url

            return succes(
                "convertir", self.nom,
                message=(f"« {entree.name} » converti en .{format_cible} via {moteur.moteur_id} "
                         f"({taille_avant} -> {taille_apres} octets)."),
                preuve=str(sortie), **detail)

        return echec("convertir", self.nom,
                     f"Tous les moteurs disponibles ont échoué : {'; '.join(erreurs_moteurs)}")

    def _rediger(
        self, texte: Any, format_cible: Any = None, titre: Any = None,
    ) -> ResultatAction:
        """Écrit un texte dans un document téléchargeable, et rend son lien.

        **Le chaînon qui manquait, mesuré le 20/09/2026.** Les moteurs PDF
        étaient tous là (`md -> pdf` par WeasyPrint, `docx -> pdf` par
        LibreOffice, mesurés disponibles), la route `/media/rendered/{nom:path}`
        savait servir le fichier, le connecteur `pdf` savait fusionner et
        scinder. **Mais les deux portes d'entrée partaient d'un fichier déjà
        fourni par le propriétaire.** Aucune capacité ne disait « prends ce
        texte et écris-le sur disque » — donc « fais-moi un PDF de ça » n'avait
        rien à appeler, et ARENA répondait en texte sans jamais pouvoir
        l'admettre.

        Quatre choses, dans cet ordre, et l'ordre compte :

        1. **Un texte vide est refusé avant d'écrire quoi que ce soit.** Un PDF
           d'une page blanche est un document raté qui se télécharge quand
           même — c'est-à-dire un échec déguisé en succès.
        2. **Un format sans moteur est refusé avant d'écrire, lui aussi.**
           Écrire le brouillon puis découvrir qu'on ne sait pas le convertir
           laisserait un fichier orphelin dans `media/rendered/`.
        3. **La conversion réutilise `_convertir_un_fichier`**, la fonction de
           la conversion à l'unité — donc la garde de sécurité, la validation
           qui rouvre le fichier, et le repli d'un moteur sur l'autre sont
           exactement les mêmes. Une deuxième implémentation serait une
           deuxième occasion de rendre un succès faux.
        4. **Le brouillon est détruit, qu'on ait réussi ou non.** Ce qui se
           télécharge est le document demandé, jamais le markdown intermédiaire
           qui a servi à le fabriquer.

        Args:
            texte: le contenu à écrire. Du markdown par défaut — c'est ce
                qu'un modèle produit spontanément.
            format_cible: `pdf` si rien n'est dit. `md`, `txt` et `html`
                s'écrivent directement, sans moteur.
            titre: donne son nom au fichier téléchargé. Sans lui, « document ».

        Returns:
            Un `SUCCES` portant `url` — le lien à ouvrir depuis le téléphone —
            et `preuve`, le chemin réel sur disque.
        """
        texte = texte if isinstance(texte, str) else ""
        if not texte.strip():
            return echec("rediger", self.nom,
                         "Aucun texte à écrire : un document vide n'est pas un document.")

        octets = len(texte.encode("utf-8"))
        if octets > TEXTE_MAX_OCTETS:
            return echec(
                "rediger", self.nom,
                f"Texte refusé : {octets} octets, plafond {TEXTE_MAX_OCTETS}. "
                f"Au-delà, ce n'est plus une réponse rédigée.")

        format_cible = str(format_cible or "pdf").lower().lstrip(".")

        if format_cible in FORMATS_TEXTE:
            self.dossier.mkdir(parents=True, exist_ok=True)
            return self._ecrire_document_texte(texte, _slug(titre), format_cible, octets)

        # Le format que le brouillon portera. `md` d'abord (WeasyPrint le rend
        # en PDF), `html` ensuite (LibreOffice en tire un DOCX) : ce n'est pas
        # une preference esthetique, c'est ce que la matrice des moteurs sait
        # reellement faire sur CETTE machine, relue a chaque appel.
        format_source = next(
            (f for f in (FORMAT_SOURCE_DEFAUT, "html")
             if registre.moteurs_pour(f, format_cible)), None)

        # Refuse AVANT d'ecrire : un brouillon ecrit pour un format qu'aucun
        # moteur ne sait rendre resterait sur le disque sans jamais servir.
        if format_source is None:
            return non_implemente(
                "rediger", self.nom,
                f"Aucun moteur ARENA n'écrit un document .{format_cible} "
                f"aujourd'hui. Rien n'a été écrit.")

        self.dossier.mkdir(parents=True, exist_ok=True)
        base = _slug(titre)

        # Le texte recu est du markdown. Quand le brouillon doit etre du HTML,
        # il est rendu par la MEME fonction que le chemin PDF — deux rendus du
        # meme markdown donneraient deux documents differents selon le format
        # demande, et l'ecart ne se verrait pas.
        contenu = (texte if format_source == FORMAT_SOURCE_DEFAUT
                   else texte_vers_html(texte, FORMAT_SOURCE_DEFAUT))

        # Un dossier a nous : le brouillon garde un nom propre (`rapport.md`),
        # donc le document rendu s'appelle `rapport-<horodatage>-<id>.pdf` et
        # pas `rapport-<horodatage>-<id>-<horodatage>-<id>.pdf`. C'est le nom
        # que le proprietaire voit dans ses telechargements.
        brouillon_dir = self.dossier / f".brouillon-{uuid.uuid4().hex[:12]}"
        try:
            brouillon_dir.mkdir(parents=True, exist_ok=True)
            source = brouillon_dir / f"{base}.{format_source}"
            source.write_text(contenu, encoding="utf-8")
        except OSError as erreur:
            shutil.rmtree(brouillon_dir, ignore_errors=True)
            return echec("rediger", self.nom, f"Brouillon impossible à écrire : {erreur}")

        try:
            resultat = self._convertir_un_fichier(str(source), format_cible)
        finally:
            # Meme si la conversion leve : rien ne reste derriere elle.
            shutil.rmtree(brouillon_dir, ignore_errors=True)

        if not resultat.a_eu_lieu:
            # Le statut de la conversion est la verite (NON_CONFIGURE quand une
            # dependance manque, ECHEC quand le moteur a rendu une sortie
            # invalide) ; seul le nom de l'action change, parce que c'est
            # `rediger` que l'appelant a demande.
            return ResultatAction(
                resultat.statut, "rediger", self.nom, resultat.message,
                detail=dict(resultat.detail))

        detail = dict(resultat.detail)
        # La taille du brouillon n'apprend rien a personne : ce qui compte est
        # le document rendu.
        detail.pop("taille_avant_octets", None)
        detail["octets_texte"] = octets
        taille = detail.get("taille_apres_octets")
        return succes(
            "rediger", self.nom,
            message=(f"Document « {Path(resultat.preuve).name} » écrit en .{format_cible} "
                     f"via {detail.get('moteur', 'moteur inconnu')}"
                     + (f" ({taille} octets)." if taille else ".")),
            preuve=resultat.preuve, **detail)

    def _ecrire_document_texte(
        self, texte: str, base: str, format_cible: str, octets: int,
    ) -> ResultatAction:
        """`md`, `txt` ou `html` : le texte EST déjà le document.

        Séparé du reste parce qu'aucun moteur n'intervient — mais la règle 2
        du connecteur tient quand même : le fichier est **relu** avant qu'un
        succès ne soit rendu. Un disque plein écrit un fichier tronqué sans
        lever, et un document tronqué qui se télécharge est pire qu'un échec.
        """
        sortie = self.dossier / f"{base}-{int(time.time())}-{uuid.uuid4().hex[:8]}.{format_cible}"
        try:
            sortie.write_text(texte, encoding="utf-8")
            relu = sortie.read_text(encoding="utf-8")
        except OSError as erreur:
            sortie.unlink(missing_ok=True)
            return echec("rediger", self.nom, f"Document impossible à écrire : {erreur}")

        if relu != texte:
            sortie.unlink(missing_ok=True)
            return echec(
                "rediger", self.nom,
                f"Document relu différent de ce qui a été écrit "
                f"({len(relu)} caractères relus contre {len(texte)} écrits).")

        url = f"/media/rendered/{CONVERSIONS_DIR_NOM}/{sortie.name}" \
            if self.dossier.parent == RENDERED_DIR else None
        detail: Dict[str, Any] = {
            "moteur": "ecriture_directe", "format_cible": format_cible,
            "taille_apres_octets": sortie.stat().st_size, "octets_texte": octets,
        }
        if url:
            detail["url"] = url
        return succes(
            "rediger", self.nom,
            message=f"Document « {sortie.name} » écrit ({octets} octets), sans conversion.",
            preuve=str(sortie), **detail)

    def _compresser(self, chemins: List[str]) -> ResultatAction:
        from core.production.conversion.moteurs import compresser_zip

        if not chemins:
            return echec("compresser", self.nom, "Aucun fichier fourni.")

        entrees: List[Path] = []
        for chemin in chemins:
            resolu, raison = securite.chemin_source_est_sur(str(chemin))
            if raison:
                return echec("compresser", self.nom, f"Fichier refusé : {raison} ({chemin}).")
            taille_invalide = securite.taille_acceptable(resolu)
            if taille_invalide:
                return echec("compresser", self.nom, f"Fichier refusé : {taille_invalide}.")
            entrees.append(resolu)

        self.dossier.mkdir(parents=True, exist_ok=True)
        sortie = self.dossier / _nom_sortie(Path("archive"), "zip")
        try:
            compresser_zip(entrees, sortie)
        except MoteurEchec as erreur:
            return echec("compresser", self.nom, str(erreur))

        raison_invalide = validation.verifier(sortie, "zip")
        if raison_invalide:
            sortie.unlink(missing_ok=True)
            return echec("compresser", self.nom, f"Archive invalide après écriture : {raison_invalide}.")

        url = f"/media/rendered/{CONVERSIONS_DIR_NOM}/{sortie.name}" \
            if self.dossier.parent == RENDERED_DIR else None
        detail: Dict[str, Any] = {"fichiers": len(entrees),
                                   "taille_octets": sortie.stat().st_size}
        if url:
            detail["url"] = url
        return succes(
            "compresser", self.nom,
            message=f"{len(entrees)} fichier(s) compressés dans « {sortie.name} ».",
            preuve=str(sortie), **detail)

    def _extraire(self, chemin: Any) -> ResultatAction:
        from core.production.conversion.moteurs import extraire_zip

        archive, raison = securite.chemin_source_est_sur(str(chemin or ""))
        if raison:
            return echec("extraire", self.nom, f"Archive refusée : {raison}.")
        taille_invalide = securite.taille_acceptable(archive)
        if taille_invalide:
            return echec("extraire", self.nom, f"Archive refusée : {taille_invalide}.")

        self.dossier.mkdir(parents=True, exist_ok=True)
        cible = self.dossier / f"extrait-{archive.stem}-{int(time.time())}-{uuid.uuid4().hex[:8]}"
        try:
            fichiers = extraire_zip(archive, cible)
        except MoteurEchec as erreur:
            return echec("extraire", self.nom, str(erreur))

        return succes(
            "extraire", self.nom,
            message=f"« {archive.name} » extrait : {len(fichiers)} fichier(s) dans « {cible.name} ».",
            preuve=str(cible), fichiers=[str(f) for f in fichiers])

    # --- Dispatch --------------------------------------------------------------

    def _executer(self, capacite: Capacite, **parametres: Any) -> ResultatAction:
        if capacite.nom == "convertir":
            return self._convertir_un_fichier(
                parametres.get("entree"), parametres.get("format_cible"))

        if capacite.nom == "rediger":
            return self._rediger(
                parametres.get("texte"),
                parametres.get("format_cible"),
                parametres.get("titre"))

        if capacite.nom == "compresser":
            return self._compresser(parametres.get("entrees") or [])

        if capacite.nom == "extraire":
            return self._extraire(parametres.get("entree"))

        if capacite.nom == "convertir_lot":
            return self._convertir_lot(
                parametres.get("entrees") or [], parametres.get("format_cible"))

        if capacite.nom == "etat_lot":
            return self._etat_lot(parametres.get("job_id"))

        if capacite.nom == "formats_disponibles":
            matrice = registre.matrice_disponibilite()
            disponibles = sum(1 for ligne in matrice if ligne["disponible"])
            return succes(
                "formats_disponibles", self.nom,
                message=f"{disponibles}/{len(matrice)} couple(s) de formats disponibles "
                        f"maintenant sur cette machine.",
                preuve=f"{disponibles}/{len(matrice)}", matrice=matrice)

        return non_implemente(capacite.nom, self.nom, "Capacité non câblée.")

    def _convertir_lot(self, chemins: List[str], format_cible: Any) -> ResultatAction:
        format_cible = str(format_cible or "").lower().lstrip(".")
        if not format_cible:
            return echec("convertir_lot", self.nom, "`format_cible` est requis.")

        raison = lot_module.lot_acceptable(chemins)
        if raison:
            return echec("convertir_lot", self.nom, f"Lot refusé : {raison}.")

        if self.travaux is None:
            # Pas de file de fond injectée : on convertit quand même, juste
            # sans progression observable pendant l'appel. Jamais un refus —
            # la mission (§6) demande que le lot marche, la tâche de fond
            # n'est qu'une amélioration de latence par-dessus.
            resultats = [
                {"entree": chemin, **self._convertir_un_fichier(chemin, format_cible).to_dict()}
                for chemin in chemins
            ]
            reussites = sum(1 for r in resultats if r.get("a_eu_lieu"))
            return succes(
                "convertir_lot", self.nom,
                message=f"{reussites}/{len(chemins)} fichier(s) convertis (synchrone, "
                        f"aucune file de fond branchée).",
                preuve=f"{reussites}/{len(chemins)}", resultats=resultats)

        travail = lot_module.convertir_lot_en_fond(
            self._convertir_un_fichier, self.travaux, chemins, format_cible)
        return succes(
            "convertir_lot", self.nom,
            message=f"Lot de {len(chemins)} fichier(s) soumis en tâche de fond. "
                    f"Suis avec `etat_lot`, identifiant {travail.identifiant}.",
            preuve=travail.identifiant, job_id=travail.identifiant)

    def _etat_lot(self, job_id: Any) -> ResultatAction:
        job_id = str(job_id or "")
        if not job_id or self.travaux is None:
            return echec("etat_lot", self.nom,
                         "Aucune file de fond branchée, ou identifiant manquant.")
        travail = self.travaux.lire(job_id)
        if travail is None:
            return echec("etat_lot", self.nom, f"Aucun lot connu avec l'identifiant « {job_id} ».")
        return succes(
            "etat_lot", self.nom,
            message=f"Lot {job_id} : {travail.etat.value}"
                    + (f" ({travail.faits}/{travail.total})" if travail.total else ""),
            preuve=job_id, travail=travail.to_dict(), resultat=travail.resultat)
