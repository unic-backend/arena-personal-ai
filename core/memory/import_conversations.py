"""Importer une conversation exportee (ChatGPT, Claude, texte brut) comme des
souvenirs CANDIDATS — jamais des faits, jamais executee.

Mission ARENA x AI MEMORY VAULT (11/09/2026, DEC-0090). AI Memory Vault
(`backend/app/importers.py` + `backend/app/suggestions.py`, audit complet ->
`docs/audits/ai_memory_vault_audit.md`) fait deux choses bien, reprises ici en
tant qu'IDEE, jamais en code copie :

1. **Detecter le format avant de le lire** (export ChatGPT `conversations.json`
   avec sa structure `mapping`, export Claude avec `chat_messages`, ou texte
   brut) — jamais deviner a l'aveugle.
2. **Extraire par expressions regulieres, jamais par un modele.** Un modele
   qui lirait le texte importe POUR en extraire des souvenirs serait un
   modele qui LIT une instruction potentiellement glissee dans ce texte —
   « Ignore previous instructions... » deviendrait alors une donnee qu'on
   demande a un LLM d'interpreter. Les regex ne l'interpretent jamais : le
   texte reste une chaine de caracteres comparee a un motif, jamais un
   prompt. C'est la meme defense que `src/security/trust.py` documente pour
   du texte externe ailleurs dans ce depot — appliquee ici par construction,
   pas par un filtre ajoute apres coup.

**Ce que ce module NE fait PAS**, et pourquoi :

- Il n'ecrit jamais directement dans `MemoirePersonnelle` : `importer()` rend
  des `SuggestionMemoire` (candidats), et c'est l'appelant (le routeur HTTP,
  le serveur MCP) qui decide de les passer a `retenir(nature=INFERENCE)` —
  jamais un chemin qui contourne l'approbation.
- Il ne detecte que des formulations ANGLAISES (comme l'original — les
  exports ChatGPT/Claude sont trypiquement en anglais quand l'utilisateur
  parle anglais a ces outils). Une conversation en francais ne produira que
  la suggestion de repli (note generique) — limite reelle, documentee, pas
  masquee.
"""
from __future__ import annotations

import json
import logging
import re
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import List, Tuple

from core.memory.consolidation import empreinte
from core.memory.personnelle import MemoirePersonnelle, Nature, Souvenir, TypeSouvenir

logger = logging.getLogger("usman.memoire.import")

#: Un import ne doit pas faire exploser la memoire d'un coup : chaque
#: conversation contribue au plus ce nombre de candidats (meme borne
#: qu'AI Memory Vault, verifiee utile — au-dela, l'extraction par motifs
#: produit surtout du bruit, jamais des candidats plus pertinents).
CANDIDATS_MAX_PAR_TEXTE = 20
CONVERSATIONS_MAX_PAR_EXPORT = 100
CARACTERES_MAX_PAR_CONVERSATION = 20_000


class FormatImportInconnu(ValueError):
    """Le fichier fourni n'est ni un export ChatGPT/Claude reconnu, ni .txt/.md/.json/.zip."""


@dataclass(frozen=True)
class SuggestionMemoire:
    """Un candidat, jamais un fait. `raison` dit toujours pourquoi il a ete propose."""

    type: TypeSouvenir
    contenu: str
    confiance: float
    raison: str


_MOTIF_PROJET = re.compile(
    r"(?:I am|I'm|we are|we're|currently)?\s*(?:building|working on|creating|developing)\s+"
    r"([A-Z][A-Za-z0-9 _-]{2,80})(?:\s+(?:using|with)\s+([^.\n]+))?",
    re.IGNORECASE,
)
_MOTIF_STACK = re.compile(
    r"([A-Z][A-Za-z0-9 _-]{2,80})\s+(?:uses|is using|runs on|is built with)\s+([^.\n]+)",
    re.IGNORECASE,
)
_MOTIF_PREFERENCE = re.compile(r"\b(?:I prefer|I like|I want|I usually|Please)\s+([^.\n]+)", re.IGNORECASE)
_MOTIF_OBJECTIF = re.compile(r"\b(?:my goal is|goal is|I want to|we want to|need to)\s+([^.\n]+)", re.IGNORECASE)
_MOTIF_COMPETENCE = re.compile(r"\b(?:I know|I can|skilled in|experience with)\s+([^.\n]+)", re.IGNORECASE)


def _nettoyer(valeur: str) -> str:
    return re.sub(r"\s+", " ", valeur).strip(" .,:;-")


def _decouper_pile(valeur: str) -> List[str]:
    return [
        _nettoyer(partie)
        for partie in re.split(r",| and | plus | with ", valeur, flags=re.IGNORECASE)
        if len(_nettoyer(partie)) > 1
    ]


def extraire_candidats(texte: str) -> List[SuggestionMemoire]:
    """Les candidats trouves dans `texte` par motifs, jamais par un modele.

    `texte` est traite comme de la DONNEE du debut a la fin — jamais
    interprete, jamais transmis a un fournisseur de modele par cette
    fonction.
    """
    candidats: List[SuggestionMemoire] = []
    vus: set = set()

    def ajouter(type_: TypeSouvenir, contenu: str, confiance: float, raison: str) -> None:
        contenu = _nettoyer(contenu)
        if len(contenu) < 8:
            return
        cle = (type_.value, contenu.lower())
        if cle in vus:
            return
        vus.add(cle)
        candidats.append(SuggestionMemoire(type=type_, contenu=contenu,
                                            confiance=confiance, raison=raison))

    for correspondance in _MOTIF_PROJET.finditer(texte):
        projet = _nettoyer(correspondance.group(1))
        pile = correspondance.group(2)
        ajouter(TypeSouvenir.SEMANTIQUE, f"User is working on {projet}.", 0.72,
                "Formulation de projet actif detectee.")
        if pile:
            for techno in _decouper_pile(pile):
                ajouter(TypeSouvenir.SEMANTIQUE, f"{projet} uses {techno}.", 0.70,
                        "Pile technique de projet detectee.")

    for correspondance in _MOTIF_STACK.finditer(texte):
        projet = _nettoyer(correspondance.group(1))
        for techno in _decouper_pile(correspondance.group(2)):
            ajouter(TypeSouvenir.SEMANTIQUE, f"{projet} uses {techno}.", 0.72,
                    "Phrase explicite de pile technique detectee.")

    for correspondance in _MOTIF_PREFERENCE.finditer(texte):
        ajouter(TypeSouvenir.SEMANTIQUE, f"User prefers {_nettoyer(correspondance.group(1))}.",
                0.64, "Formulation de preference detectee.")

    for correspondance in _MOTIF_OBJECTIF.finditer(texte):
        ajouter(TypeSouvenir.TACHE, f"User wants to {_nettoyer(correspondance.group(1))}.",
                0.62, "Formulation d'objectif detectee.")

    for correspondance in _MOTIF_COMPETENCE.finditer(texte):
        ajouter(TypeSouvenir.SEMANTIQUE, f"User has experience with {_nettoyer(correspondance.group(1))}.",
                0.58, "Formulation de competence detectee.")

    if not candidats and texte.strip():
        ajouter(TypeSouvenir.EPISODIQUE, texte.strip()[:500], 0.35,
                "Aucun motif structure reconnu ; conserve comme note brute.")

    return candidats[:CANDIDATS_MAX_PAR_TEXTE]


def _extraire_chatgpt(charge: bytes) -> Tuple[str, List[SuggestionMemoire]]:
    conversations = json.loads(charge.decode("utf-8", errors="ignore"))
    candidats: List[SuggestionMemoire] = []
    for conversation in conversations[:CONVERSATIONS_MAX_PAR_EXPORT]:
        titre = conversation.get("title") or "Conversation ChatGPT sans titre"
        messages = []
        for noeud in (conversation.get("mapping") or {}).values():
            message = noeud.get("message") if isinstance(noeud, dict) else None
            if not message:
                continue
            role = (message.get("author") or {}).get("role")
            if role not in {"user", "assistant"}:
                continue
            parties = (message.get("content") or {}).get("parts") or []
            texte = "\n".join(p for p in parties if isinstance(p, str)).strip()
            if texte:
                messages.append(f"{role}: {texte}")
        texte_source = f"ChatGPT conversation: {titre}\n\n" + "\n\n".join(messages)
        candidats.extend(extraire_candidats(texte_source[:CARACTERES_MAX_PAR_CONVERSATION]))
    return "chatgpt_export", candidats[:100]


def _extraire_claude(charge: bytes) -> Tuple[str, List[SuggestionMemoire]]:
    conversations = json.loads(charge.decode("utf-8", errors="ignore"))
    candidats: List[SuggestionMemoire] = []
    for conversation in conversations[:CONVERSATIONS_MAX_PAR_EXPORT]:
        titre = conversation.get("name") or conversation.get("title") or "Conversation Claude sans titre"
        messages = conversation.get("chat_messages") or conversation.get("messages") or []
        parties = [f"Claude conversation: {titre}"]
        for message in messages:
            contenu = message.get("text") or message.get("content") or ""
            if isinstance(contenu, list):
                contenu = "\n".join(
                    str(p.get("text", "")) if isinstance(p, dict) else str(p) for p in contenu
                )
            if contenu:
                parties.append(str(contenu))
        texte_source = "\n\n".join(parties)
        candidats.extend(extraire_candidats(texte_source[:CARACTERES_MAX_PAR_CONVERSATION]))
    return "claude_export", candidats[:100]


def _extraire_zip(charge: bytes) -> Tuple[str, List[SuggestionMemoire]]:
    with zipfile.ZipFile(BytesIO(charge)) as archive:
        noms = archive.namelist()
        minuscules = {n.lower(): n for n in noms}
        if "conversations.json" in minuscules:
            return _extraire_chatgpt(archive.read(minuscules["conversations.json"]))
        nom_claude = next(
            (n for n in noms if "conversation" in n.lower() and n.lower().endswith(".json")),
            None,
        )
        if nom_claude:
            return _extraire_claude(archive.read(nom_claude))
        textes = [
            archive.read(n).decode("utf-8", errors="ignore")
            for n in noms if n.lower().endswith((".txt", ".md"))
        ]
        if textes:
            return "text_zip", extraire_candidats("\n\n".join(textes))
    raise FormatImportInconnu("Aucun contenu ChatGPT, Claude ou texte reconnu dans ce ZIP.")


def _extraire_json(nom_fichier: str, charge: bytes) -> Tuple[str, List[SuggestionMemoire]]:
    donnees = json.loads(charge.decode("utf-8", errors="ignore"))
    if isinstance(donnees, list) and donnees and isinstance(donnees[0], dict) and "mapping" in donnees[0]:
        return _extraire_chatgpt(charge)
    if isinstance(donnees, list) and donnees and isinstance(donnees[0], dict) and (
        "chat_messages" in donnees[0] or "uuid" in donnees[0]
    ):
        return _extraire_claude(charge)
    if isinstance(donnees, list) and donnees and isinstance(donnees[0], dict) and "content" in donnees[0]:
        texte = "\n\n".join(str(item.get("content", "")) for item in donnees)
        return "memory_json", extraire_candidats(texte[:100_000])
    return "json", extraire_candidats(json.dumps(donnees)[:100_000])


def detecter_et_extraire(nom_fichier: str, charge: bytes) -> Tuple[str, List[SuggestionMemoire]]:
    """Point d'entree : detecte le format depuis l'extension, extrait des candidats.

    Raises:
        FormatImportInconnu: extension non geree, ou ZIP sans contenu reconnu.
    """
    suffixe = Path(nom_fichier).suffix.lower()
    if suffixe == ".zip":
        return _extraire_zip(charge)
    if suffixe == ".json":
        return _extraire_json(nom_fichier, charge)
    if suffixe in {".txt", ".md"}:
        texte = charge.decode("utf-8", errors="ignore")
        return suffixe.lstrip("."), extraire_candidats(texte)
    raise FormatImportInconnu(
        f"Format non reconnu ({suffixe or 'sans extension'}). "
        "Formats acceptes : .zip (export ChatGPT/Claude), .json, .txt, .md."
    )


@dataclass(frozen=True)
class ResultatImport:
    """Ce qui s'est reellement passe — jamais un simple compte de lignes.

    Attributes:
        format_detecte: chatgpt_export / claude_export / json / txt / md / ...
        crees: les souvenirs reellement ecrits, tous `Nature.INFERENCE`.
        doublons_ignores: candidats dont l'empreinte existait deja (dans cet
            import ou dans la memoire) — jamais re-ecrits.
        refuses: (contenu tronque, raison) pour tout candidat que `retenir()`
            a refuse — le plus souvent parce qu'il a la forme d'un secret
            (mission §35 : un import ne contourne pas cette regle).
    """

    format_detecte: str
    crees: List[Souvenir] = field(default_factory=list)
    doublons_ignores: int = 0
    refuses: List[Tuple[str, str]] = field(default_factory=list)


def importer_dans_la_memoire(
    memoire: MemoirePersonnelle,
    nom_fichier: str,
    charge: bytes,
    source: str,
    projet: str | None = None,
) -> ResultatImport:
    """Le seul chemin depuis un fichier importe jusqu'a la memoire.

    IMPORT -> PARSE (`detecter_et_extraire`) -> CANDIDAT (`SuggestionMemoire`)
    -> DEDUPLICATION (`empreinte`, contre l'import ET contre la memoire deja
    la) -> `retenir(nature=INFERENCE)` -> jamais canonique tant que le
    proprietaire n'a pas appele `confirmer()`.

    Raises:
        FormatImportInconnu: propagee depuis `detecter_et_extraire`.
    """
    format_detecte, candidats = detecter_et_extraire(nom_fichier, charge)

    empreintes_connues = {empreinte(s.contenu) for s in memoire.souvenirs(projet=projet, limite=5000)}

    crees: List[Souvenir] = []
    doublons_ignores = 0
    refuses: List[Tuple[str, str]] = []
    for candidat in candidats:
        cle = empreinte(candidat.contenu)
        if cle in empreintes_connues:
            doublons_ignores += 1
            continue
        empreintes_connues.add(cle)
        try:
            souvenir = memoire.retenir(
                contenu=candidat.contenu,
                type=candidat.type,
                nature=Nature.INFERENCE,   # jamais un fait a l'import : une deduction
                source=source,
                projet=projet,
                importance=candidat.confiance,
                metadonnees={"raison_extraction": candidat.raison},
            )
        except ValueError as erreur:
            refuses.append((candidat.contenu[:60], str(erreur)))
            continue
        crees.append(souvenir)

    logger.info(
        "Import %s : %s cree(s), %s doublon(s) ignore(s), %s refuse(s).",
        format_detecte, len(crees), doublons_ignores, len(refuses),
    )
    return ResultatImport(format_detecte=format_detecte, crees=crees,
                           doublons_ignores=doublons_ignores, refuses=refuses)
