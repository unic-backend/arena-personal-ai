"""Un guide de procedure : etapes deja decrites, transformees en document.

Ce qui a motive ce module (04/09/2026) : une demande d'integrer Mimik
(westpoint-io, MIT) — capture en direct des clics/DOM/captures d'ecran d'un
navigateur pendant qu'un proprietaire l'utilise. Cette partie-la a ete
refusee : ARENA n'a ni extension navigateur ni pipeline de capture, et en
construire un pour enregistrer les sessions du proprietaire est une surface
de captation, pas un outil de lecture — aucun besoin reel exprime ne
justifiait ce risque.

Ce qui reste, et que ce module fait reellement : recevoir un **workflow deja
decrit** — des etapes que quelqu'un a ECRITES, pas capturees en silence — et
le transformer en document (PDF, DOCX, HTML, Markdown). Rien ici n'observe
quoi que ce soit en direct ; tout arrive en parametre, explicitement.

Ce module ne fait tourner aucun moteur a lui : le PDF passe par reportlab
(deja une dependance, `agents/plaquiste/devis_pdf.py`), le DOCX par
python-docx (deja une dependance, `tools/documents/reader.py` — qui ne
l'utilisait jusqu'ici qu'en lecture ; ecrire est une capacite de la meme
bibliotheque, pas un second moteur). Aucun rendu video : `SUGGESTION — NON
IMPLEMENTEE`, aucun besoin reel ne l'a justifie et le brancher sur le moteur
de montage existant est un chantier a part.

**Deux regles :**

1. **Le texte fourni est redige AVANT d'etre mis en page**, jamais l'inverse.
   `expurger()` masque ce qui ressemble a un email, un numero de telephone,
   une carte, ou une valeur secrete — avant que quoi que ce soit ne parte
   dans un fichier. Une capture d'ecran fournie (image) n'est PAS analysee :
   masquer des pixels exigerait de la vision, non implemente ici — la
   capture est embarquee telle quelle, et documentee comme telle.
2. **Une capture d'ecran est un chemin vers un fichier DEJA existant**, jamais
   une commande qui va le chercher. Le meme garde que GitIngest
   (`core/connectors/gitingest.py`) refuse un chemin qui vise `.ssh`, `.env`,
   une cle privee — avant meme d'essayer de l'ouvrir.
"""
from __future__ import annotations

import base64
import html
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Sequence

#: Memes segments/noms que core/connectors/gitingest.py — une capture
#: d'ecran ne doit pas plus qu'un depot pouvoir viser un dossier sensible.
SEGMENTS_INTERDITS = frozenset({
    ".ssh", ".aws", ".gnupg", ".git-credentials", ".netrc",
    "id_rsa", "id_ed25519", "id_ecdsa",
})
FICHIERS_INTERDITS = frozenset({".env", "credentials.json", "secrets.json"})

EXTENSIONS_IMAGE_AUTORISEES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp"})

#: Jamais le bloc plein Unicode (█, U+2588) : absent de l'encodage WinAnsi
#: qu'utilise la police Helvetica par defaut de reportlab — un test reel l'a
#: montre rendu comme un tout autre caractere (■) une fois extrait du PDF.
#: Uniquement des caracteres Latin-1, surs dans reportlab/python-docx/HTML.
MASQUE = "[masque]"

MOTIF_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[A-Za-z]{2,}")
#: Prudent par construction : seulement un numero avec indicatif explicite
#: (+221, +33...) ou une suite d'au moins 8 chiffres separee par des
#: espaces/points/tirets — pour ne pas masquer une cote ou une quantite
#: qu'un guide de procedure peut legitimement citer.
MOTIF_TELEPHONE = re.compile(r"(?:\+\d{1,3}[ .-]?)(?:\d[ .-]?){7,12}\d")
MOTIF_CARTE = re.compile(r"\b(?:\d[ -]?){13,19}\b")


def _entropie(valeur: str) -> float:
    """Bits d'information par caractere — meme mesure que scripts/scanner_secrets.py,
    reprise ici en miniature : ce module n'importe pas `scripts/`, reserve aux
    outils autonomes, pas au runtime."""
    if not valeur:
        return 0.0
    frequences = {c: valeur.count(c) for c in set(valeur)}
    n = len(valeur)
    return -sum((f / n) * math.log2(f / n) for f in frequences.values())


MOTIF_AFFECTATION_SECRETE = re.compile(
    r"""(?ix) \b (?:api[_-]?key|secret|token|password|passwd) \b \s* [:=] \s* ['"]?([^\s'"]{8,})['"]?""")


def expurger(texte: str) -> str:
    """Masque ce qui ressemble a un email, un telephone, une carte, un
    secret — avant que ce texte n'entre dans un document produit."""
    if not texte:
        return texte
    texte = MOTIF_EMAIL.sub(MASQUE, texte)
    texte = MOTIF_CARTE.sub(MASQUE, texte)
    texte = MOTIF_TELEPHONE.sub(MASQUE, texte)

    def _masquer_secret(correspondance: "re.Match[str]") -> str:
        valeur = correspondance.group(1)
        if _entropie(valeur) >= 3.0:
            return correspondance.group(0).replace(valeur, MASQUE)
        return correspondance.group(0)

    return MOTIF_AFFECTATION_SECRETE.sub(_masquer_secret, texte)


def chemin_capture_est_sur(chemin: str) -> Optional[str]:
    """None si la capture d'ecran peut etre lue ; sinon la raison du refus.

    Meme garde que `core/connectors/gitingest.py::_chemin_local_est_sur` —
    un nom de segment/fichier sensible refuse, avant meme d'ouvrir le fichier.
    """
    p = Path(chemin).expanduser()
    try:
        resolu = p.resolve()
    except OSError as erreur:
        return f"chemin illisible : {erreur}"

    segments_bas = {s.lower() for s in resolu.parts}
    trouve = SEGMENTS_INTERDITS & segments_bas
    if trouve:
        return f"chemin sensible refuse (« {sorted(trouve)[0]} »)"
    if resolu.name.lower() in FICHIERS_INTERDITS:
        return f"fichier sensible refuse ({resolu.name})"
    if not resolu.exists():
        return f"capture introuvable : {resolu}"
    if resolu.suffix.lower() not in EXTENSIONS_IMAGE_AUTORISEES:
        return f"extension non prise en charge : {resolu.suffix or '(aucune)'}"
    return None


@dataclass(frozen=True)
class Etape:
    """Une etape ECRITE par quelqu'un — jamais capturee en silence.

    `capture_ecran` est un chemin vers un fichier image DEJA existant, fourni
    explicitement. Rien ici ne prend une capture d'ecran toute seule.
    """

    action: str
    description: str = ""
    contexte: str = ""
    capture_ecran: Optional[str] = None
    avertissement: str = ""


@dataclass(frozen=True)
class Workflow:
    """Un guide de procedure a produire — jamais un enregistrement de session."""

    titre: str
    introduction: str = ""
    etapes: Sequence[Etape] = field(default_factory=tuple)
    prerequis: Sequence[str] = field(default_factory=tuple)
    conclusion: str = ""


@dataclass(frozen=True)
class ProblemeCapture:
    """Une capture d'ecran fournie que le rendu n'a pas pu inclure, et pourquoi."""

    etape_index: int
    chemin: str
    raison: str


def valider_captures(workflow: Workflow) -> List[ProblemeCapture]:
    """Les captures fournies qui ne peuvent pas etre incluses, et pourquoi.

    Ne leve jamais : un rendu doit pouvoir continuer sans une capture
    refusee, en le disant, plutot que d'echouer entierement pour un
    fichier annexe.
    """
    problemes = []
    for i, etape in enumerate(workflow.etapes):
        if not etape.capture_ecran:
            continue
        raison = chemin_capture_est_sur(etape.capture_ecran)
        if raison:
            problemes.append(ProblemeCapture(i, etape.capture_ecran, raison))
    return problemes


def _etapes_expurgees(workflow: Workflow) -> List[Etape]:
    return [
        Etape(
            action=expurger(e.action),
            description=expurger(e.description),
            contexte=expurger(e.contexte),
            capture_ecran=e.capture_ecran,
            avertissement=expurger(e.avertissement),
        )
        for e in workflow.etapes
    ]


# --- Rendus ---------------------------------------------------------------

def vers_markdown(workflow: Workflow) -> str:
    w = Workflow(titre=expurger(workflow.titre), introduction=expurger(workflow.introduction),
                etapes=_etapes_expurgees(workflow),
                prerequis=[expurger(p) for p in workflow.prerequis],
                conclusion=expurger(workflow.conclusion))
    lignes = [f"# {w.titre}", ""]
    if w.introduction:
        lignes += [w.introduction, ""]
    if w.prerequis:
        lignes += ["## Prerequis", ""]
        lignes += [f"- {p}" for p in w.prerequis]
        lignes.append("")
    lignes.append("## Etapes")
    lignes.append("")
    for i, e in enumerate(w.etapes, 1):
        lignes.append(f"{i}. **{e.action}**")
        if e.description:
            lignes.append(f"   {e.description}")
        if e.capture_ecran and chemin_capture_est_sur(e.capture_ecran) is None:
            lignes.append(f"   \n   ![Etape {i}]({e.capture_ecran})")
        if e.avertissement:
            lignes.append(f"   \n   > ⚠️ {e.avertissement}")
        lignes.append("")
    if w.conclusion:
        lignes += ["## Conclusion", "", w.conclusion]
    return "\n".join(lignes).strip() + "\n"


def vers_html(workflow: Workflow) -> str:
    """Un HTML autonome : images encodees en base64, aucune ressource externe."""
    w_titre = html.escape(expurger(workflow.titre))
    w_intro = html.escape(expurger(workflow.introduction))
    etapes = _etapes_expurgees(workflow)

    parties = [
        "<!doctype html><html lang=\"fr\"><head><meta charset=\"utf-8\">",
        f"<title>{w_titre}</title>",
        "<style>body{font-family:sans-serif;max-width:760px;margin:2rem auto;"
        "padding:0 1rem;color:#1a1a1a}h1{color:#1d4ed8}li{margin-bottom:1.2rem}"
        "img{max-width:100%;border:1px solid #ddd;border-radius:4px}"
        "blockquote{color:#92400e;background:#fffbeb;padding:.5rem 1rem;"
        "border-left:3px solid #f59e0b}</style></head><body>",
        f"<h1>{w_titre}</h1>",
    ]
    if w_intro:
        parties.append(f"<p>{w_intro}</p>")
    if workflow.prerequis:
        parties.append("<h2>Prerequis</h2><ul>")
        parties += [f"<li>{html.escape(expurger(p))}</li>" for p in workflow.prerequis]
        parties.append("</ul>")
    parties.append("<h2>Etapes</h2><ol>")
    for e in etapes:
        parties.append(f"<li><strong>{html.escape(e.action)}</strong>")
        if e.description:
            parties.append(f"<p>{html.escape(e.description)}</p>")
        if e.capture_ecran and chemin_capture_est_sur(e.capture_ecran) is None:
            chemin = Path(e.capture_ecran)
            donnees = base64.b64encode(chemin.read_bytes()).decode("ascii")
            type_mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                        "gif": "image/gif", "webp": "image/webp"}[chemin.suffix.lower().lstrip(".")]
            parties.append(f"<img src=\"data:{type_mime};base64,{donnees}\" alt=\"\">")
        if e.avertissement:
            parties.append(f"<blockquote>⚠️ {html.escape(e.avertissement)}</blockquote>")
        parties.append("</li>")
    parties.append("</ol>")
    if workflow.conclusion:
        parties.append(f"<h2>Conclusion</h2><p>{html.escape(expurger(workflow.conclusion))}</p>")
    parties.append("</body></html>")
    return "\n".join(parties)


def vers_docx(workflow: Workflow, sortie: Path) -> Path:
    """Ecrit un vrai .docx (python-docx — deja une dependance ; ecrire est une
    capacite de la meme bibliotheque, pas un second moteur DOCX)."""
    from docx import Document

    w = Workflow(titre=expurger(workflow.titre), introduction=expurger(workflow.introduction),
                etapes=_etapes_expurgees(workflow),
                prerequis=[expurger(p) for p in workflow.prerequis],
                conclusion=expurger(workflow.conclusion))

    document = Document()
    document.add_heading(w.titre, level=1)
    if w.introduction:
        document.add_paragraph(w.introduction)
    if w.prerequis:
        document.add_heading("Prerequis", level=2)
        for p in w.prerequis:
            document.add_paragraph(p, style="List Bullet")
    document.add_heading("Etapes", level=2)
    for i, e in enumerate(w.etapes, 1):
        document.add_paragraph(f"{i}. {e.action}", style="List Number")
        if e.description:
            document.add_paragraph(e.description)
        if e.capture_ecran and chemin_capture_est_sur(e.capture_ecran) is None:
            document.add_picture(e.capture_ecran, width=None)
        if e.avertissement:
            document.add_paragraph(f"⚠️ {e.avertissement}")
    if w.conclusion:
        document.add_heading("Conclusion", level=2)
        document.add_paragraph(w.conclusion)

    sortie.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(sortie))
    return sortie


def vers_pdf(workflow: Workflow, sortie: Path) -> Path:
    """Ecrit un vrai .pdf (reportlab — deja une dependance,
    `agents/plaquiste/devis_pdf.py` l'utilise pour le devis ; meme moteur,
    document different)."""
    from PIL import Image as ImagePIL
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer

    def _image_proportionnelle(chemin: str, largeur: float) -> Image:
        """`Image(kind="proportional")` (reportlab) exige largeur ET hauteur
        pour calculer le ratio — lui donner `height=None` leve un
        TypeError des la mise en page. Le vrai ratio est lu sur le fichier."""
        with ImagePIL.open(chemin) as img:
            largeur_px, hauteur_px = img.size
        hauteur = largeur * (hauteur_px / largeur_px) if largeur_px else largeur
        return Image(chemin, width=largeur, height=hauteur)

    w = Workflow(titre=expurger(workflow.titre), introduction=expurger(workflow.introduction),
                etapes=_etapes_expurgees(workflow),
                prerequis=[expurger(p) for p in workflow.prerequis],
                conclusion=expurger(workflow.conclusion))

    st_titre = ParagraphStyle("titre", fontName="Helvetica-Bold", fontSize=17, spaceAfter=10)
    st_h2 = ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=12, spaceBefore=10, spaceAfter=6)
    st_texte = ParagraphStyle("texte", fontName="Helvetica", fontSize=10, leading=13.5)
    st_avert = ParagraphStyle("avert", fontName="Helvetica-Oblique", fontSize=9,
                             textColor="#92400e", leading=12)

    flux = [Paragraph(w.titre, st_titre)]
    if w.introduction:
        flux += [Paragraph(w.introduction, st_texte), Spacer(1, 8)]
    if w.prerequis:
        flux.append(Paragraph("Prerequis", st_h2))
        flux.append(ListFlowable(
            [ListItem(Paragraph(p, st_texte)) for p in w.prerequis], bulletType="bullet"))
    flux.append(Paragraph("Etapes", st_h2))
    for i, e in enumerate(w.etapes, 1):
        flux.append(Paragraph(f"{i}. {e.action}", st_texte))
        if e.description:
            flux.append(Paragraph(e.description, st_texte))
        if e.capture_ecran and chemin_capture_est_sur(e.capture_ecran) is None:
            flux.append(Spacer(1, 4))
            flux.append(_image_proportionnelle(e.capture_ecran, 140 * mm))
        if e.avertissement:
            flux.append(Paragraph(f"⚠️ {e.avertissement}", st_avert))
        flux.append(Spacer(1, 8))
    if w.conclusion:
        flux.append(Paragraph("Conclusion", st_h2))
        flux.append(Paragraph(w.conclusion, st_texte))

    sortie.parent.mkdir(parents=True, exist_ok=True)
    SimpleDocTemplate(str(sortie), pagesize=A4,
                      leftMargin=20 * mm, rightMargin=20 * mm,
                      topMargin=18 * mm, bottomMargin=18 * mm).build(flux)
    return sortie
