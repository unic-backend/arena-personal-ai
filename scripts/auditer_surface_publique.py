"""Ce qu'un visiteur d'Internet peut atteindre sans la clé — mesuré, pas lu.

    python scripts/auditer_surface_publique.py

VOLET « ARENA en ligne », phase 4.1. Aujourd'hui ARENA écoute sur sa machine,
derrière un tunnel Cloudflare dont l'adresse est longue et change à chaque
redémarrage (`docs/REPRISE.md`). Sur le serveur (DEC-0021), l'adresse sera
fixe et permanente : ce que ce script trouve ouvert aujourd'hui, tout Internet
pourra le trouver aussi.

**Deux règles :**

1. **On interroge l'application réelle, jamais son code source.** Une route
   décorée `dependencies=[Depends(verify_api_key)]` peut exister sans que la
   dépendance s'applique vraiment — c'est exactement le genre d'écart qu'une
   lecture ne voit pas et qu'un vrai appel révèle. Ce script utilise
   `TestClient` sur `apps.backend.main.app`, sans jamais démarrer de serveur
   réseau.

2. **Une route publique n'est pas un défaut si elle est sur la liste — et un
   défaut si elle n'y est pas.** `/`, `/health`, les fichiers de l'interface :
   personne n'a de raison de les protéger. Le reste, oui.
"""
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

# Sans cle configuree (poste de developpement, ce bac a sable), la passerelle
# refuse tout par defaut de securite — mais avec un code 500, pas le 401 d'un
# serveur deploye normalement. Ce script mesure la surface publique, pas la
# configuration locale : une cle de test, jamais lue ni ecrite ailleurs, sert
# uniquement a voir les vrais codes 401/429 qu'un visiteur obtiendrait. Elle
# n'ecrase jamais une vraie cle deja presente dans l'environnement.
os.environ.setdefault("USMAN_API_KEY", "audit-cle-de-test-non-secrete")

#: Ce qui n'a jamais eu besoin de la clé, et n'en aura jamais besoin : l'interface
#: elle-même, pas ce qu'elle sert. Toute route absente de cette liste ET
#: joignable sans clé est un défaut, pas un choix.
ROUTES_DELIBEREMENT_PUBLIQUES = frozenset({
    "/", "/offline.html", "/manifest.webmanifest", "/sw.js",
    "/icons/{nom}", "/ui/classique", "/health",
})


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


def _routes_api_declarees() -> List[str]:
    """Les chemins `@router.*` du projet — pas les mounts statiques, traités à part."""
    from fastapi.routing import APIRoute

    from apps.backend.main import app

    def parcourir(routes):
        for route in routes:
            if isinstance(route, APIRoute):
                yield route.path
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


def auditer() -> List[Constat]:
    """Appelle chaque route déclarée et les mounts connus, sans aucune clé."""
    from fastapi.testclient import TestClient

    from apps.backend.main import app

    client = TestClient(app)
    constats = []

    for chemin in _routes_api_declarees():
        if "{" in chemin:
            continue  # parametree : /icons/{nom} est deja sur la liste publique
        reponse = client.get(chemin)
        constats.append(Constat(chemin, reponse.status_code,
                                attendu_public=chemin in ROUTES_DELIBEREMENT_PUBLIQUES))

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
