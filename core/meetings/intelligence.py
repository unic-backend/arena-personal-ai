"""Analyse déterministe d'une réunion à partir d'une transcription.

Ce module reprend uniquement les idées utiles observées dans call.md :
métriques explicites, compte rendu, points clés et actions. Il ne copie aucun
code tiers et ne dépend ni de VideoDB ni d'un service cloud.

La frontière la plus importante est la séparation des locuteurs : Faster-
Whisper produit aujourd'hui des segments temporels, pas une diarisation fiable.
ARENA n'affiche donc un ratio par locuteur QUE si le moteur amont a réellement
fourni un champ `speaker`, `speaker_id` ou `channel`.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any, Iterable

_MOT_REUNION = re.compile(
    r"\b(?:réunion|reunion|meeting|appel|call|enregistrement)\b",
    re.IGNORECASE,
)
_MOT_ANALYSE = re.compile(
    r"\b(?:analyse(?:r)?|résum(?:e|er|é)|resum(?:e|er)|compte[- ]?rendu|"
    r"points?\s+cl[ée]s?|décisions?|decisions?|actions?|action\s+items?|"
    r"prochaines?\s+[ée]tapes?)\b",
    re.IGNORECASE,
)
_REUNION_D_AGENTS = re.compile(
    r"\b(?:réunion|reunion|meeting)\s+(?:de|des|entre)\s+(?:mes\s+)?agents?\b",
    re.IGNORECASE,
)
_APPEL_D_OFFRES = re.compile(
    r"\bappel\s+d['’ ]?offres?\b",
    re.IGNORECASE,
)
_MOT = re.compile(r"[\wÀ-ÿ]+(?:['’\-][\wÀ-ÿ]+)*", re.UNICODE)


def est_demande_analyse_reunion(texte: str) -> bool:
    """Vrai seulement pour une analyse de réunion/appel enregistré.

    Une simple demande de transcription reste de l'AUDIO. Une « réunion des
    agents » reste le travail d'équipe interne d'ARENA, pas l'analyse d'un média.
    """
    valeur = (texte or "").strip()
    if (
        not valeur
        or _REUNION_D_AGENTS.search(valeur)
        or _APPEL_D_OFFRES.search(valeur)
    ):
        return False
    return bool(_MOT_REUNION.search(valeur) and _MOT_ANALYSE.search(valeur))


def _mots(texte: str) -> list[str]:
    return _MOT.findall(texte or "")


def _locuteur(segment: dict[str, Any]) -> str:
    for cle in ("speaker", "speaker_id", "channel"):
        valeur = segment.get(cle)
        if valeur is not None and str(valeur).strip():
            return str(valeur).strip()
    return ""


def mesurer_reunion(
    transcription: str,
    segments: Iterable[dict[str, Any]] | None,
    duree: float | int | None,
) -> dict[str, Any]:
    """Mesure ce qui est réellement observable, sans compléter les absences."""
    texte = transcription or ""
    mots = _mots(texte)
    duree_valide = (
        float(duree)
        if isinstance(duree, (int, float)) and not isinstance(duree, bool) and float(duree) > 0
        else None
    )

    liste_segments = list(segments) if segments is not None else None
    metriques: dict[str, Any] = {
        "word_count": len(mots),
        "question_count": texte.count("?"),
        "duration_seconds": round(duree_valide, 2) if duree_valide is not None else None,
        "words_per_minute": (
            round(len(mots) / (duree_valide / 60.0), 1)
            if duree_valide is not None
            else None
        ),
        "segment_count": len(liste_segments) if liste_segments is not None else None,
        "speaker_separation_available": False,
        "speaker_word_counts": {},
        "speaker_talk_ratio": {},
    }

    if not liste_segments:
        return metriques

    comptes: Counter[str] = Counter()
    for segment in liste_segments:
        if not isinstance(segment, dict):
            continue
        locuteur = _locuteur(segment)
        if not locuteur:
            continue
        comptes[locuteur] += len(_mots(str(segment.get("text") or "")))

    # Un seul label ne prouve aucune séparation. Deux labels distincts sont
    # nécessaires avant de parler de ratio entre locuteurs.
    comptes = Counter({cle: valeur for cle, valeur in comptes.items() if valeur > 0})
    if len(comptes) < 2:
        return metriques

    total = sum(comptes.values())
    metriques["speaker_separation_available"] = True
    metriques["speaker_word_counts"] = dict(sorted(comptes.items()))
    metriques["speaker_talk_ratio"] = {
        cle: round(valeur / total, 4)
        for cle, valeur in sorted(comptes.items())
    }
    return metriques


def formater_metriques_reunion(metriques: dict[str, Any]) -> str:
    """Rend les mesures visibles sans transformer une absence en zéro."""
    duree = metriques.get("duration_seconds")
    debit = metriques.get("words_per_minute")
    lignes = [
        "Métriques mesurées",
        f"- Durée : {duree:.1f} s" if isinstance(duree, (int, float)) else "- Durée : non disponible",
        f"- Mots : {int(metriques.get('word_count') or 0)}",
        f"- Débit : {debit:.1f} mots/min" if isinstance(debit, (int, float)) else "- Débit : non disponible",
        f"- Questions détectées : {int(metriques.get('question_count') or 0)}",
    ]
    if metriques.get("speaker_separation_available"):
        ratios = metriques.get("speaker_talk_ratio") or {}
        details = ", ".join(
            f"{locuteur}: {float(ratio) * 100:.1f}%"
            for locuteur, ratio in ratios.items()
        )
        lignes.append(f"- Répartition des locuteurs : {details or 'non disponible'}")
    else:
        lignes.append("- Répartition des locuteurs : non disponible (pas de diarisation fiable)")
    return "\n".join(lignes)


def construire_prompt_reunion(transcription: str, metriques: dict[str, Any]) -> str:
    """Construit une analyse strictement ancrée dans la transcription."""
    separation = (
        "Des étiquettes de locuteurs existent dans les segments."
        if metriques.get("speaker_separation_available")
        else (
            "Aucune séparation fiable des locuteurs n'est disponible. "
            "N'invente ni nom, ni identité, ni attribution à un locuteur."
        )
    )
    return f"""Tu analyses une réunion UNIQUEMENT à partir de sa transcription.

Règles impératives :
- N'ajoute aucun fait absent de la transcription.
- Distingue clairement ce qui a été décidé de ce qui a seulement été proposé.
- Une action doit être explicitement soutenue par la transcription.
- Pour chaque action, indique responsable et échéance seulement s'ils sont dits ;
  sinon écris « non précisé ».
- N'invente jamais l'identité d'un locuteur. {separation}
- Si une information manque, dis qu'elle manque au lieu de la compléter.

Métriques mesurées par ARENA :
{metriques}

Rends exactement ces sections en français :
1. Résumé
2. Points clés
3. Décisions explicites
4. Actions à faire
5. Questions ouvertes

<TRANSCRIPTION>
{transcription}
</TRANSCRIPTION>"""
