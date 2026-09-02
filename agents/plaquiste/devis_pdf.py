"""Genere un devis ou une facture a la charte UniC Plaquiste.

Repris du fichier de reference du proprietaire : couleurs, en-tete, bandeaux de
section, tableau materiaux zebre, bandeau TTC jaune, blocs signature. La mise en
page est la sienne ; ce module la rend reproductible.

**Une decision porte tout le reste : le modele choisit les articles et les
quantites, Python calcule l'argent.** Aucun total n'est repris d'un texte
genere. Un modele qui se trompe d'article se voit ; un modele qui se trompe
d'addition passe inapercu jusqu'au client.

Les prix viennent de `config/unic_plaquiste.yaml`. Une ligne dont l'article n'y
figure pas est rendue avec la mention « a confirmer » et un total vide — jamais
un chiffre invente.
"""
import logging
from dataclasses import dataclass, field
from datetime import date as _date
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    Image as RLImage,
)
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

logger = logging.getLogger("usman.agent.plaquiste.pdf")

A_CONFIRMER = "a confirmer"

#: Le bloc destinataire dit toujours « CLIENT » — faux pour un bon de commande,
#: qui s'adresse a un fournisseur. Un type absent d'ici garde « CLIENT » : la
#: liste s'etend sans jamais casser un type_document deja en usage (devis,
#: facture, ou tout autre texte libre que l'appelant aurait choisi).
LIBELLES_DESTINATAIRE = {
    "BON DE COMMANDE": "FOURNISSEUR",
    "BON DE LIVRAISON": "LIVRE A",
}


def libelle_destinataire(type_document: str) -> str:
    return LIBELLES_DESTINATAIRE.get(type_document.upper(), "CLIENT")


#: Largeur reelle du bloc titre (`bloc_doc`, colonne droite de l'entete) :
#: 51 mm, moins une marge pour ne pas coller au bord.
LARGEUR_TITRE_MM = 46
TAILLE_TITRE_MAX = 20
TAILLE_TITRE_MIN = 11


def taille_du_titre(texte: str) -> int:
    """Le plus grand corps qui tient sur UNE ligne — mesure, jamais suppose.

    « DEVIS » et « FACTURE » gardaient toujours 20 pt (mesure : aucun des
    deux ne depasse). « BON DE COMMANDE » et « BON DE LIVRAISON » sont plus
    longs et retournaient a la ligne a 20 pt — un vrai defaut trouve en
    testant le rendu, pas en relisant le code.
    """
    for taille in range(TAILLE_TITRE_MAX, TAILLE_TITRE_MIN - 1, -1):
        if stringWidth(texte, "Helvetica-Bold", taille) <= LARGEUR_TITRE_MM * mm:
            return taille
    return TAILLE_TITRE_MIN


# --- Charte -------------------------------------------------------------------

def _couleurs(metier: Dict[str, Any]) -> Dict[str, Any]:
    """Lit la charte du fichier metier, avec les valeurs du proprietaire en repli."""
    charte = metier.get("charte", {}) if metier else {}
    return {
        "bleu": colors.HexColor(charte.get("bleu", "#1A3FA0")),
        "jaune": colors.HexColor(charte.get("jaune", "#F2C200")),
        "gris_ligne": colors.HexColor("#CCCCCC"),
        "gris_zebre": colors.HexColor("#F4F6FB"),
        "blanc": colors.white,
    }


# --- Lignes du devis ----------------------------------------------------------

@dataclass
class Ligne:
    """Un poste du devis. Le prix vient de la grille, jamais de l'appelant."""

    designation: str
    quantite: float

    def chiffrer(self, grille: Dict[str, int]) -> Tuple[Optional[int], Optional[int]]:
        """Rend (prix unitaire, total). `(None, None)` si l'article est inconnu."""
        prix = grille.get(self.designation)
        if prix is None:
            return None, None
        return prix, int(round(prix * self.quantite))


@dataclass
class Devis:
    """Tout ce qu'il faut pour rendre un document. Rien de calcule ici.

    `date` et `numero` valent le jour reel s'ils ne sont pas donnes. C'est la
    correction du 2026-08-27 : ces deux champs etaient des chaines libres, donc
    un modele pouvait y ecrire n'importe quelle date. Un devis mal date est un
    devis juridiquement fragile.
    """

    client: str
    lieu: str
    objet: str
    numero: str = ""
    date: str = ""
    lignes: List[Ligne] = field(default_factory=list)
    type_document: str = "DEVIS"
    validite_jours: int = 15
    main_oeuvre_m2: Optional[float] = None
    exclusions: List[str] = field(default_factory=list)
    suffixe_client: str = "XXX"
    # Un devis signe d'avance est un devis qu'on peut envoyer tel quel. Il
    # reste faux par defaut : signer automatiquement un document qu'on n'a
    # pas relu est une mauvaise habitude a prendre.
    signe: bool = False

    def __post_init__(self) -> None:
        """Comble la date et le numero avec le jour reel, jamais avec autre chose."""
        from agents.plaquiste.plaquiste_agent import (
            date_du_jour,
            date_en_toutes_lettres,
            numero_du_jour,
        )

        jour: _date = date_du_jour()
        if not self.date:
            self.date = date_en_toutes_lettres(jour)
        if not self.numero:
            self.numero = numero_du_jour(jour, self.suffixe_client)


def _format_montant(valeur: Optional[int]) -> str:
    if valeur is None:
        return A_CONFIRMER
    return f"{valeur:,}".replace(",", " ")


def chiffrer(devis: Devis, metier: Dict[str, Any]) -> Dict[str, Any]:
    """Calcule le devis. **C'est Python qui additionne, pas le modele.**

    Rend les lignes chiffrees, le total des articles connus, et la liste des
    articles sans prix. Le total ignore les articles inconnus : additionner une
    valeur inventee serait pire que rendre un total incomplet, et la liste dit
    lesquels manquent.
    """
    grille = dict(metier.get("prix_materiaux") or {})
    grille.update(metier.get("prix_portes") or {})

    detail, inconnus, total = [], [], 0
    for ligne in devis.lignes:
        prix, montant = ligne.chiffrer(grille)
        if prix is None:
            inconnus.append(ligne.designation)
        else:
            total += montant
        detail.append({
            "designation": ligne.designation,
            "quantite": ligne.quantite,
            "prix_unitaire": prix,
            "total": montant,
        })

    total_mo = 0
    if devis.main_oeuvre_m2:
        tarif = (metier.get("main_oeuvre") or {}).get("tarif_m2")
        if tarif:
            total_mo = int(round(tarif * devis.main_oeuvre_m2))
            total += total_mo

    return {
        "lignes": detail,
        "total_materiaux": total - total_mo,
        "total_main_oeuvre": total_mo,
        "total": total,
        "articles_sans_prix": inconnus,
    }


# --- Rendu --------------------------------------------------------------------

#: Les fichiers de la marque, deposes par le proprietaire. Ils etaient la
#: depuis le 27/08/2026 et **personne ne les passait** : `construire()` avait
#: `logo=None` par defaut, et son unique appelant
#: (`core/connectors/devis.py`) ne le renseignait pas. Tous les devis sortaient
#: donc sans le logo — mesure du 02/09/2026, 0 image dans le PDF produit.
#:
#: Le defaut vit ici plutot que chez l'appelant : un devis sans logo est un
#: defaut, pas un choix, et chaque nouvel appelant le reproduirait.
DOSSIER_MARQUE = Path(__file__).resolve().parents[2] / "documents" / "unic_plaquiste"
LOGO_PAR_DEFAUT = DOSSIER_MARQUE / "logo_unic_plaquiste.png"
SIGNATURE_PAR_DEFAUT = DOSSIER_MARQUE / "signature_uthman.png"


def construire(devis: Devis, metier: Dict[str, Any], sortie: Path,
               logo: Optional[Path] = None,
               signature: Optional[Path] = None) -> Dict[str, Any]:
    """Ecrit le PDF et rend le chiffrage. Le fichier existe, ou la fonction leve.

    `logo` et `signature` retombent sur les fichiers de la marque quand
    l'appelant ne dit rien. Un chemin explicite l'emporte toujours — c'est ce
    qui permet aux tests de passer un fichier absent et de verifier qu'un
    devis sort quand meme.
    """
    logo = logo if logo is not None else LOGO_PAR_DEFAUT
    signature = signature if signature is not None else SIGNATURE_PAR_DEFAUT
    c = _couleurs(metier)
    e = metier.get("entreprise", {})
    calcul = chiffrer(devis, metier)

    st = {
        "nom": ParagraphStyle("nom", fontName="Helvetica-Bold", fontSize=17,
                              textColor=c["bleu"], leading=20, spaceAfter=1),
        "sous": ParagraphStyle("sous", fontName="Helvetica-Bold", fontSize=10,
                               textColor=c["jaune"], leading=12, spaceAfter=3),
        "info": ParagraphStyle("info", fontName="Helvetica-Bold", fontSize=8.5,
                               textColor=colors.black, leading=10.5),
        "titre": ParagraphStyle(
            "titre", fontName="Helvetica-Bold", fontSize=taille_du_titre(devis.type_document),
            textColor=c["bleu"], alignment=TA_RIGHT, leading=taille_du_titre(devis.type_document) + 2),
        "num": ParagraphStyle("num", fontName="Helvetica-Bold", fontSize=10,
                              textColor=colors.black, alignment=TA_RIGHT, leading=14),
        "secblanc": ParagraphStyle("secblanc", fontName="Helvetica-Bold", fontSize=11,
                                   textColor=c["blanc"], leading=13),
        "txt": ParagraphStyle("txt", fontName="Helvetica-Bold", fontSize=9,
                              textColor=colors.black, leading=12),
        "just": ParagraphStyle("just", fontName="Helvetica-Bold", fontSize=9,
                               textColor=colors.black, leading=12.5, alignment=TA_JUSTIFY),
        "clienttitre": ParagraphStyle("ct", fontName="Helvetica-Bold", fontSize=10,
                                      textColor=c["bleu"], leading=13),
    }

    def barre(titre: str) -> Table:
        t = Table([[Paragraph(titre, st["secblanc"])]], colWidths=[180 * mm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), c["bleu"]),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        return t

    infos = (
        f"{e.get('specialite', '')}<br/>{e.get('gerant', '')} - Gerant<br/>"
        f"Tel : {e.get('telephone', '')}<br/>{e.get('adresse', '')}<br/>"
        f"{e.get('site', '')}<br/>NINEA : {e.get('ninea', '')} | RCCM : {e.get('rccm', '')}"
    )
    bloc_nom = [
        Paragraph(e.get("nom", "UniC Plaquiste"), st["nom"]),
        Paragraph(e.get("accroche", ""), st["sous"]),
        Paragraph(infos, st["info"]),
    ]
    bloc_doc = [Paragraph(devis.type_document, st["titre"]),
                Paragraph(f"N° {devis.numero}", st["num"])]

    # Le logo est optionnel : son absence ne doit pas empecher un devis.
    if logo and Path(logo).exists():
        colonnes = [RLImage(str(logo), width=30 * mm, height=30 * mm), bloc_nom, bloc_doc]
        largeurs = [32 * mm, 97 * mm, 51 * mm]
    else:
        colonnes = [bloc_nom, bloc_doc]
        largeurs = [129 * mm, 51 * mm]

    entete = Table([colonnes], colWidths=largeurs)
    entete.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")] + [
        (p, (0, 0), (-1, -1), 0) for p in
        ("LEFTPADDING", "RIGHTPADDING", "TOPPADDING", "BOTTOMPADDING")
    ]))

    ligne_jaune = Table([[""]], colWidths=[180 * mm], rowHeights=[2])
    ligne_jaune.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), c["jaune"])]))

    story: List[Any] = [entete, Spacer(1, 2), ligne_jaune, Spacer(1, 4)]

    gauche = [Paragraph(libelle_destinataire(devis.type_document), st["clienttitre"]),
              Paragraph(devis.client, st["txt"]),
              Paragraph(f"Lieu du chantier : {devis.lieu}", st["txt"])]
    droite = [Paragraph(f"Date : {devis.date}", st["txt"]),
              Paragraph(f"N° {devis.type_document.title()} : {devis.numero}", st["txt"]),
              Paragraph(f"Validite : {devis.validite_jours} jours", st["txt"])]
    bloc_client = Table([[gauche, droite]], colWidths=[90 * mm, 90 * mm])
    bloc_client.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                     ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story += [bloc_client, Spacer(1, 5)]

    story += [barre(f"Objet du {devis.type_document.lower()}"), Spacer(1, 3),
              Paragraph(devis.objet, st["just"]), Spacer(1, 8)]

    devise = e.get("devise", "FCFA")
    rows = [["Designation", "Prix Unitaire", "Quantite", "Prix Total"]]
    for detail in calcul["lignes"]:
        quantite = detail["quantite"]
        rows.append([
            detail["designation"],
            _format_montant(detail["prix_unitaire"]),
            f"{quantite:g}",
            f"{_format_montant(detail['total'])} {devise}"
            if detail["total"] is not None else A_CONFIRMER,
        ])
    rows.append(["Total Materiaux", "", "",
                 f"{_format_montant(calcul['total_materiaux'])} {devise}"])

    tableau = Table(rows, colWidths=[78 * mm, 34 * mm, 28 * mm, 40 * mm])
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), c["bleu"]), ("TEXTCOLOR", (0, 0), (-1, 0), c["blanc"]),
        ("BACKGROUND", (0, -1), (-1, -1), c["bleu"]), ("TEXTCOLOR", (0, -1), (-1, -1), c["blanc"]),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"), ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, c["gris_ligne"]),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for r in range(1, len(rows) - 1):
        if r % 2 == 0:
            style.append(("BACKGROUND", (0, r), (-1, r), c["gris_zebre"]))
    tableau.setStyle(TableStyle(style))
    story += [barre("Tableau 1 - Materiaux"), Spacer(1, 3), tableau, Spacer(1, 10)]

    if calcul["total_main_oeuvre"]:
        mo = metier.get("main_oeuvre", {})
        rows_mo = [
            ["Designation", "Prix Unitaire", "Quantite", "Prix Total"],
            [mo.get("libelle", "Main-d'oeuvre"),
             f"{_format_montant(mo.get('tarif_m2'))} {devise}/m2",
             f"{devis.main_oeuvre_m2:g} m2",
             f"{_format_montant(calcul['total_main_oeuvre'])} {devise}"],
        ]
        t_mo = Table(rows_mo, colWidths=[78 * mm, 34 * mm, 28 * mm, 40 * mm])
        t_mo.setStyle(TableStyle(style[:9]))
        story += [barre("Tableau 2 - Main-d'oeuvre"), Spacer(1, 3), t_mo, Spacer(1, 10)]

    ttc = Table([[
        Paragraph("MONTANT TOTAL TTC", ParagraphStyle(
            "ttc", fontName="Helvetica-Bold", fontSize=12, textColor=c["bleu"])),
        Paragraph(f"{_format_montant(calcul['total'])} {devise}", ParagraphStyle(
            "ttc2", fontName="Helvetica-Bold", fontSize=12,
            textColor=c["bleu"], alignment=TA_RIGHT)),
    ]], colWidths=[130 * mm, 50 * mm])
    ttc.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), c["jaune"]),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story += [ttc, Spacer(1, 12)]

    exclusions = devis.exclusions or metier.get("exclusions_habituelles", [])
    if exclusions:
        story += [barre("Ne sont pas inclus"), Spacer(1, 3)]
        story += [Paragraph(f"• {x}", st["txt"]) for x in exclusions]
        story.append(Spacer(1, 12))

    if calcul["articles_sans_prix"]:
        story += [
            Paragraph(
                "Articles sans prix de reference, a confirmer avant envoi : "
                + ", ".join(calcul["articles_sans_prix"]),
                st["txt"],
            ),
            Spacer(1, 10),
        ]

    # La signature du gerant, si elle existe et si le document est signe.
    signature_gerant: Any = Paragraph("Signature : ______________________", st["txt"])
    if devis.signe and signature and Path(signature).exists():
        signature_gerant = RLImage(str(signature), width=42 * mm, height=17 * mm)
    elif devis.signe:
        logger.warning("Document marque signe mais aucune signature trouvee : ligne vide.")

    signatures = Table([
        [Paragraph(e.get("nom", "UniC Plaquiste"), st["txt"]),
         Paragraph(f"{libelle_destinataire(devis.type_document).title()} ({devis.client})",
                   st["txt"])],
        [signature_gerant,
         Paragraph("Signature : ______________________", st["txt"])],
        [Paragraph(f"{e.get('gerant', '')} — Gerant" if devis.signe else "Date : ____________",
                   st["txt"]),
         Paragraph("Date : ____________", st["txt"])],
    ], colWidths=[90 * mm, 90 * mm])
    signatures.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 6),
                                    ("LEFTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(KeepTogether(signatures))

    sortie = Path(sortie)
    sortie.parent.mkdir(parents=True, exist_ok=True)
    SimpleDocTemplate(
        str(sortie), pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=9 * mm, bottomMargin=10 * mm,
    ).build(story)

    logger.info("Document ecrit : %s (%d octets)", sortie.name, sortie.stat().st_size)
    return {**calcul, "fichier": str(sortie), "octets": sortie.stat().st_size}
