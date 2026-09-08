"""Generer une interface a partir d'une description — la METHODE d'OpenUI,
pas son moteur.

Demande directe : integrer OpenUI (wandb/openui, Apache-2.0) comme capacite
« decrire une interface en langage naturel -> la voir generee ». Verifie
avant d'ecrire une ligne (clone reel, `wandb/openui` @ `42d7ab4`, 05/09/2026,
contrairement a KrillinAI ce depot n'a pas change de forme) : sa vraie
capacite n'est PAS le serveur FastAPI qu'il fait tourner — celui-ci exige une
connexion GitHub (`request.session["user_id"]`, `backend/openui/server.py`)
et tire `weave`, `boto3`, `peewee`, `fastapi-sso` dans l'arbre de
dependances pour un usage multi-utilisateur/hebergement qu'ARENA n'a pas.
**Ce que fait reellement OpenUI, c'est une technique de prompt** — cote
CLIENT, en TypeScript (`frontend/src/api/openai.ts::systemPrompt`) : fragment
HTML seul (pas de <html>/<head>), classes Tailwind, variables CSS de theme
(clair/sombre), images de substitution — envoyee ensuite a N'IMPORTE QUEL
modele compatible OpenAI (dont Ollama, deja ce qu'ARENA utilise en local).

Ce module reprend cette TECHNIQUE, en code ARENA propre, pas les fichiers
d'OpenUI (aucune ligne de `frontend/src/api/openai.ts` copiee) — meme
discipline que le catalogue de specialistes (`core/specialistes/
catalogue.py`) et Social Media Skills plus tot dans cette session. Le modele
utilise est celui d'ARENA (local d'abord, DEC-0002), jamais un second
service a heberger.

**Deux regles :**

1. **Un document HTML complet et autonome**, pas un fragment a injecter dans
   un apercu live qu'ARENA n'a pas — Tailwind par CDN (le meme domaine que
   ce systeme autorise deja pour ses propres artefacts), aucune dependance
   a une iframe ou un bundler.
2. **Aucun script externe hors d'une liste fermee.** `valider_scripts_externes()`
   refuse tout `<script src="...">` dont le domaine n'est pas explicitement
   autorise — la commande de securite de la mission (« controle des URLs
   externes ») appliquee reellement, pas seulement promise.
"""
from __future__ import annotations

import re
from typing import List, Optional

FRAMEWORKS = frozenset({"html", "react", "svelte", "web-component"})

#: Les seuls domaines qu'un `<script src="...">` genere peut viser. Memes
#: domaines que ceux deja verifies et documentes pour les artefacts de ce
#: systeme — jamais un CDN invente pour l'occasion.
DOMAINES_SCRIPT_AUTORISES = frozenset({
    "cdnjs.cloudflare.com",
    "cdn.jsdelivr.net",
    "cdn.tailwindcss.com",
    "code.jquery.com",
})

MOTIF_SCRIPT_SRC = re.compile(r'<script[^>]+src=["\']([^"\']+)["\']', re.IGNORECASE)


def prompt_systeme(framework: str) -> str:
    """La technique d'OpenUI (fragment/Tailwind/variables de theme), adaptee
    a un document complet — jamais copiee mot pour mot de son prompt."""
    base = (
        "Tu es un generateur d'interface. On te decrit une interface en "
        "langage naturel ; tu rends UNE SEULE page HTML complete et "
        "autonome, prete a etre ouverte directement dans un navigateur.\n\n"
        "Regles :\n"
        "- Un document complet : <!doctype html>, <html>, <head> (avec "
        "<meta charset> et le CDN Tailwind : "
        "<script src=\"https://cdn.tailwindcss.com\"></script>), <body>.\n"
        "- Aucune dependance externe hors du CDN Tailwind ci-dessus.\n"
        "- Utilise des variables CSS de theme (--background, --foreground, "
        "--primary, --border, --muted, --accent...) pour que le clair et le "
        "sombre restent coherents.\n"
        "- Des images de substitution via https://placehold.co, jamais une "
        "URL d'image inventee ailleurs.\n"
        "- Interactivite en JavaScript natif (ES6), inline dans <script>, "
        "jamais un import externe.\n"
        "- Reponds UNIQUEMENT par un bloc de code ```html ... ``` — aucun "
        "texte avant ou apres.\n"
    )
    if framework != "html":
        base += (
            f"\nLe proprietaire a demande du {framework} : rends le meme "
            f"resultat visuel, mais comme composant {framework} dans un "
            f"bloc ```{framework} ... ```, avec les classes Tailwind "
            "toujours presentes sur les elements."
        )
    return base


def prompt_utilisateur(description: str, existant: Optional[str] = None) -> str:
    """La demande du proprietaire, avec le code existant s'il y en a un a
    faire evoluer plutot que d'en produire un nouveau."""
    if existant:
        return (
            f"Voici l'interface actuelle :\n\n{existant}\n\n"
            f"Modifie-la selon cette demande : {description}"
        )
    return description


_MOTIF_BLOC_CODE = re.compile(
    r"```(?:html|react|svelte|web-component|jsx|tsx)?\s*\n(.*?)```", re.DOTALL | re.IGNORECASE)


def extraire_code(reponse_modele: str) -> Optional[str]:
    """Le premier bloc de code du texte du modele — jamais devine, jamais
    le texte entier suppose etre du code s'il n'y a pas de bloc marque.

    Meme discipline que `core/production/plan_video.py::extraire_json` :
    un refus explicite vaut mieux qu'une supposition sur la forme.
    """
    correspondance = _MOTIF_BLOC_CODE.search(reponse_modele or "")
    if not correspondance:
        return None
    code = correspondance.group(1).strip()
    return code or None


def valider_scripts_externes(code: str) -> List[str]:
    """Les domaines de script refuses, chacun nomme — jamais une liste vide
    qui masquerait un domaine non reconnu."""
    problemes: List[str] = []
    for url in MOTIF_SCRIPT_SRC.findall(code or ""):
        domaine = url.split("://", 1)[-1].split("/", 1)[0].lower()
        if domaine not in DOMAINES_SCRIPT_AUTORISES:
            problemes.append(f"script externe refuse : {domaine}")
    return problemes
