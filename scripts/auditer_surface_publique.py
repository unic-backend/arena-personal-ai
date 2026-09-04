"""Ce qu'un visiteur d'Internet peut atteindre sans la clé — mesuré, pas lu.

    python scripts/auditer_surface_publique.py

VOLET « ARENA en ligne », phase 4.1. Aujourd'hui ARENA écoute sur sa machine,
derrière un tunnel Cloudflare dont l'adresse est longue et change à chaque
redémarrage (`docs/REPRISE.md`). Sur le serveur (DEC-0021), l'adresse sera
fixe et permanente : ce que ce script trouve ouvert aujourd'hui, tout Internet
pourra le trouver aussi.

**Trois règles :**

1. **On interroge l'application réelle, jamais son code source.** Une route
   décorée `dependencies=[Depends(verify_api_key)]` peut exister sans que la
   dépendance s'applique vraiment — c'est exactement le genre d'écart qu'une
   lecture ne voit pas et qu'un vrai appel révèle. Ce script utilise
   `TestClient` sur `apps.backend.main.app`, sans jamais démarrer de serveur
   réseau.

2. **Une route publique n'est pas un défaut si elle est sur la liste — et un
   défaut si elle n'y est pas.** `/`, `/health`, les fichiers de l'interface :
   personne n'a de raison de les protéger. Le reste, oui.

3. **On appelle la VRAIE méthode de chaque route, jamais un `GET` par
   défaut.** Trouvé par sabotage le 04/09/2026 (DEC-0045) : la version
   précédente de ce script n'envoyait que des `GET`. Une route déclarée en
   `POST` répondait alors `405 Method Not Allowed` — un code >= 400, compté
   comme « protégée » — sans que la dépendance d'authentification n'ait
   jamais été évaluée. Une protection retirée d'une route `POST` passait
   inaperçue. Pire : les routes paramétrées (`/connectors/{fournisseur}/...`,
   `/api/actions/{id}/...`) n'étaient JAMAIS appelées, sautées d'un
   `if "{" in chemin: continue`. Ce script appelle maintenant la vraie
   méthode de chaque route, avec un paramètre de substitution neutre pour
   les chemins qui en attendent un, et un corps minimal mais VALIDE pour les
   quatre routes qui exigent un fichier — sans quoi une route non protégée
   échouerait sur sa propre validation (422) avant même d'avoir eu la
   moindre chance de répondre 200, masquant le défaut au lieu de le révéler.
"""
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

#: Une cle de test, jamais lue ni ecrite ailleurs — voir `_avec_une_cle_de_test`.
CLE_DE_TEST = "audit-cle-de-test-non-secrete"

#: Ce qui n'a jamais eu besoin de la clé, et n'en aura jamais besoin : l'interface
#: elle-même, pas ce qu'elle sert. Toute route absente de cette liste ET
#: joignable sans clé est un défaut, pas un choix.
ROUTES_DELIBEREMENT_PUBLIQUES = frozenset({
    "/", "/offline.html", "/manifest.webmanifest", "/sw.js",
    "/icons/{nom}", "/ui/classique", "/health",
    # Google appelle cette route directement, jamais avec la clé d'ARENA — le
    # `state` CSRF à usage unique est sa propre protection (connectors.py).
    "/connectors/{fournisseur}/callback",
})

#: Une valeur neutre pour un segment `{xxx}` d'un chemin, quand aucune valeur
#: réelle n'existe (`/icons/{nom}`, `/api/actions/{identifiant}`) — la route
#: répond alors 404 sur SA PROPRE logique (fichier/identifiant introuvable)
#: que la clé soit bonne ou non, ce qui ne prouve rien sur l'authentification
#: pour ces chemins-là. Documenté, pas contourné : il faudrait un vrai
#: fichier ou une vraie action en attente pour lever le doute, ce que
#: `tests/test_surface_api.py` couvre déjà autrement (lecture statique de
#: `dependencies=[...]`, fiable ici — voir DEC-0045).
PARAMETRE_DE_SONDE = "sonde-audit"

#: Par nom de paramètre, une valeur qui traverse la logique métier de la
#: route SANS la masquer — pour que le seul obstacle qui reste soit
#: l'authentification, et que la réponse dise vraiment quelque chose sur
#: elle. `gmail` est le seul fournisseur OAuth câblé (`connectors.py`,
#: `FOURNISSEURS_OAUTH`) : une valeur inventée y échouerait sur sa propre
#: validation (« fournisseur inconnu ») avant même d'atteindre la clé.
VALEURS_DE_SONDE_PAR_PARAMETRE: Dict[str, str] = {
    "fournisseur": "gmail",
}

#: Les quatre routes qui exigent un fichier (`File(...)`) ou un champ de
#: formulaire (`Form(...)`) obligatoire. Un corps vide y échoue sur SA PROPRE
#: validation (422) que la route soit protégée ou non — ce qui masquerait un
#: défaut réel. Chaque valeur construit les arguments `requests`/`TestClient`
#: d'un appel qui, sur une route non protégée, réussirait vraiment (200).
CORPS_MINIMAL: Dict[str, Dict[str, Any]] = {
    "/api/upload": {"files": {"file": ("sonde.mp4", b"sonde", "video/mp4")}},
    "/files": {"files": {"file": ("sonde.txt", b"sonde", "text/plain")}},
    "/api/speech/transcribe": {"files": {"file": ("sonde.wav", b"sonde", "audio/wav")}},
    "/api/process-video": {"data": {"video_path": "/tmp/sonde-inexistant.mp4"}},
}


@dataclass
class Constat:
    """Une route mesurée : ce qu'elle a réellement répondu, sans clé."""

    chemin: str
    code: int
    attendu_public: bool

    @property
    def est_un_defaut(self) -> bool:
        """Répond sans exiger de clé, alors que rien ne l'y autorisait."""
        return self.code < 400 and not self.attendu_public


def _chemin_concret(gabarit: str) -> str:
    """Remplace chaque `{xxx}` par une valeur de sonde — la valeur dédiée du
    paramètre si elle existe, sinon la valeur neutre par défaut."""
    if "{" not in gabarit:
        return gabarit
    import re

    def substituer(correspondance: "re.Match[str]") -> str:
        nom = correspondance.group(1)
        return VALEURS_DE_SONDE_PAR_PARAMETRE.get(nom, PARAMETRE_DE_SONDE)

    return re.sub(r"\{([^}]+)\}", substituer, gabarit)


def _routes_api_declarees() -> List[Tuple[str, Tuple[str, ...]]]:
    """Les chemins `@router.*` du projet et leurs vraies méthodes — pas les
    mounts statiques, traités à part."""
    from fastapi.routing import APIRoute

    from apps.backend.main import app

    def parcourir(routes):
        for route in routes:
            if isinstance(route, APIRoute):
                yield route.path, tuple(sorted(route.methods - {"HEAD", "OPTIONS"}))
            elif hasattr(route, "original_router"):
                yield from parcourir(route.original_router.routes)
            elif hasattr(route, "routes"):
                yield from parcourir(route.routes)

    return sorted(set(parcourir(app.routes)))


def _auditer_mount_media(client) -> Constat:
    """Sonde `/media/rendered` avec un vrai fichier, pas un chemin vide.

    Le mount ne repond rien d'utile sur un dossier vide : sonder `/media/rendered/`
    tel quel donne un 404 qui ne prouve rien. Le defaut reel est qu'un fichier
    depose la` (par `/api/upload`, avec un nom derive de celui envoye) est
    ensuite servi sans cle a quiconque en devine — ou en connait deja — le
    nom. On le reproduit donc pour de vrai : un fichier temporaire, la meme
    requete qu'un visiteur ferait, puis nettoyage immediat.
    """
    from apps.backend.config import RENDERED_DIR

    nom_fichier = "_audit_temp_devis_vertical_9_16.mp4"
    chemin_disque = RENDERED_DIR / nom_fichier
    RENDERED_DIR.mkdir(parents=True, exist_ok=True)
    chemin_disque.write_bytes(b"contenu-fictif-audit")
    try:
        reponse = client.get(f"/media/rendered/{nom_fichier}")
    finally:
        chemin_disque.unlink(missing_ok=True)

    return Constat(f"/media/rendered/{nom_fichier}", reponse.status_code, attendu_public=False)


@contextmanager
def _avec_une_cle_de_test() -> Iterator[None]:
    """Force `security.USMAN_API_KEY` le temps de l'audit, puis la restitue.

    Sans cle reelle configuree (ce bac a sable, un poste de developpement),
    `verify_api_key`/`verify_media_access` refusent tout avec un 500 — le
    defaut de securite, pas le 401 qu'un visiteur obtiendrait vraiment sur un
    serveur deploye. Passer par `os.environ` ne suffit pas : `apps.backend.config`
    lit la variable une seule fois, a son tout premier import — souvent deja
    fait par un autre module (la suite de tests, par exemple) avant que ce
    script ne s'execute. Patcher directement l'attribut du module, comme le
    font deja les tests du depot (`monkeypatch.setattr(securite, ...)`),
    fonctionne quel que soit l'ordre d'import — et la restitution en `finally`
    ne laisse rien pour l'appelant suivant.
    """
    from apps.backend import security

    originale = security.USMAN_API_KEY
    security.USMAN_API_KEY = CLE_DE_TEST
    try:
        yield
    finally:
        security.USMAN_API_KEY = originale


def auditer() -> List[Constat]:
    """Appelle chaque route déclarée — sa vraie méthode, un paramètre de
    sonde si elle en attend un, un corps minimal si sa propre validation
    l'exige — et les mounts connus, sans aucune clé."""
    from fastapi.testclient import TestClient

    from apps.backend.main import app

    with _avec_une_cle_de_test():
        client = TestClient(app)
        constats = []

        for gabarit, methodes in _routes_api_declarees():
            if gabarit == "/media/rendered/{nom}":
                continue  # sonde dediee, avec un vrai fichier : _auditer_mount_media
            chemin = _chemin_concret(gabarit)
            corps = CORPS_MINIMAL.get(gabarit, {})
            for methode in methodes:
                reponse = client.request(methode, chemin, **corps)
                constats.append(Constat(gabarit, reponse.status_code,
                                        attendu_public=gabarit in ROUTES_DELIBEREMENT_PUBLIQUES))

        constats.append(_auditer_mount_media(client))

        # La documentation auto-generee de FastAPI ne figure pas dans `app.routes`
        # comme une `APIRoute` : sondes directes.
        for chemin in ("/openapi.json", "/docs", "/redoc"):
            reponse = client.get(chemin)
            constats.append(Constat(chemin, reponse.status_code, attendu_public=False))

    return constats


def main() -> int:
    constats = auditer()
    print("=" * 70)
    print("  ARENA — surface publique. Chaque ligne est un appel reel, sans cle.")
    print("=" * 70)
    for c in constats:
        marque = "[DEFAUT]" if c.est_un_defaut else "[ok]    "
        etiquette = "public assume" if c.attendu_public else "protege attendu"
        print(f"{marque} {c.chemin:<32} HTTP {c.code}  ({etiquette})")

    defauts = [c for c in constats if c.est_un_defaut]
    print("=" * 70)
    if defauts:
        print(f"{len(defauts)} route(s) joignable(s) sans cle, sans etre sur la liste publique :")
        for c in defauts:
            print(f"  - {c.chemin}")
    else:
        print("Aucun defaut : tout ce qui repond sans cle est deliberement public.")
    print("=" * 70)
    return 1 if defauts else 0


if __name__ == "__main__":
    raise SystemExit(main())
