"""Générer un croquis IFC minimal d'une cloison — jamais un second moteur BIM.

Demande directe du propriétaire (reprise de la mission BIM, section « BIM as
Code » / BuildingPy, 06/09/2026) : les deux dépôts évalués (benjaminwfriedman/
bimascode, OpenAEC-Foundation/building-py) apportent un SECOND moteur
géométrique (`build123d`/OCCT pour BIM as Code ; visée Blender/Revit/Speckle
pour BuildingPy) — exactement ce que la mission interdit (§11, « pas de
moteurs BIM redondants »). Vérifié directement dans le code d'IfcOpenShell
(déjà une dépendance, DEC-0053) : son API haut niveau
(`ifcopenshell.api.geometry.create_2pt_wall`) suffit à créer un mur simple et
l'exporter en IFC valide — sans dépendance supplémentaire, sans second
moteur. `core/connectors/ifc.py` reste dédié à la LECTURE ; ce module est
l'écriture, séparé, jamais mélangé au premier (son en-tête dit « lecture
seule », ça reste vrai).

**Portée volontairement étroite** : UNE cloison rectiligne, sans porte ni
fenêtre dans cette phase — positionner un linteau suppose une mesure que
rien ici ne fait encore. `SUGGESTION — NON IMPLÉMENTÉE`.

**La quantité écrite est calculée EXACTEMENT comme `agents/plaquiste/
calcul_materiaux.py` la lit** : `NetSideArea` = longueur x hauteur, une
face — jamais un second calcul qui pourrait diverger du devis. Un fichier
généré ici, relu par `core/production/ifc_lecture.py`, rend donc la MÊME
surface que celle utilisée pour le chiffrer.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Tuple

if TYPE_CHECKING:
    import ifcopenshell

logger = logging.getLogger("usman.production.ifc_generation")

#: Montant 70 mm, la référence du chantier UC-2026-0804-FG2 (`config/metier.yaml`).
EPAISSEUR_DEFAUT_M = 0.07


def nouveau_projet(nom: str) -> Tuple["ifcopenshell.file", "ifcopenshell.entity_instance", "ifcopenshell.entity_instance"]:
    """Le squelette minimal (projet/site/bâtiment/niveau) autour duquel une
    cloison peut être créée. Rend `(fichier, niveau, contexte_corps)`.
    """
    import ifcopenshell  # local : NON_CONFIGURE si absent, jamais un demarrage casse
    import ifcopenshell.api

    fichier = ifcopenshell.file(schema="IFC4")
    projet = ifcopenshell.api.run("root.create_entity", fichier, ifc_class="IfcProject", name=nom)
    ifcopenshell.api.run("unit.assign_unit", fichier, length={"is_metric": True, "raw": "METERS"})
    contexte = ifcopenshell.api.run("context.add_context", fichier, context_type="Model")
    contexte_corps = ifcopenshell.api.run(
        "context.add_context", fichier, context_type="Model",
        context_identifier="Body", target_view="MODEL_VIEW", parent=contexte)

    site = ifcopenshell.api.run("root.create_entity", fichier, ifc_class="IfcSite")
    batiment = ifcopenshell.api.run("root.create_entity", fichier, ifc_class="IfcBuilding")
    niveau = ifcopenshell.api.run(
        "root.create_entity", fichier, ifc_class="IfcBuildingStorey", name="Niveau 1")
    ifcopenshell.api.run("aggregate.assign_object", fichier, relating_object=projet, products=[site])
    ifcopenshell.api.run("aggregate.assign_object", fichier, relating_object=site, products=[batiment])
    ifcopenshell.api.run(
        "aggregate.assign_object", fichier, relating_object=batiment, products=[niveau])
    return fichier, niveau, contexte_corps


def ajouter_cloison(
    fichier: "ifcopenshell.file", niveau: "ifcopenshell.entity_instance",
    contexte: "ifcopenshell.entity_instance", longueur_m: float, hauteur_m: float,
    epaisseur_m: float = EPAISSEUR_DEFAUT_M, nom: str = "Cloison proposée",
) -> "ifcopenshell.entity_instance":
    """Ajoute UN mur rectiligne, de (0,0) à (longueur_m, 0) — sa quantité de
    surface est écrite dans le même geste, jamais recalculée à la relecture.
    """
    import ifcopenshell.api

    mur = ifcopenshell.api.run("root.create_entity", fichier, ifc_class="IfcWall", name=nom)
    ifcopenshell.api.run(
        "spatial.assign_container", fichier, relating_structure=niveau, products=[mur])
    ifcopenshell.api.run(
        "geometry.create_2pt_wall", fichier, element=mur, context=contexte,
        p1=(0.0, 0.0), p2=(float(longueur_m), 0.0), elevation=0.0,
        height=float(hauteur_m), thickness=float(epaisseur_m))

    qto = ifcopenshell.api.run(
        "pset.add_qto", fichier, product=mur, name="Qto_WallBaseQuantities")
    ifcopenshell.api.run("pset.edit_qto", fichier, qto=qto, properties={
        "Length": float(longueur_m),
        "Height": float(hauteur_m),
        "Width": float(epaisseur_m),
        "NetSideArea": round(float(longueur_m) * float(hauteur_m), 4),
    })
    return mur


def generer_croquis_cloison(
    longueur_m: float, hauteur_m: float, epaisseur_m: float = EPAISSEUR_DEFAUT_M,
    nom: str = "Cloison proposée",
) -> "ifcopenshell.file":
    """Un fichier IFC minimal complet — projet + une cloison — prêt à écrire."""
    fichier, niveau, contexte = nouveau_projet(nom)
    ajouter_cloison(fichier, niveau, contexte, longueur_m, hauteur_m, epaisseur_m, nom)
    return fichier
