"""Sauvegarder la base SQLite d'ARENA, et prouver que la copie se restaure.

    python scripts/sauvegarder_donnees.py

VOLET « ARENA en ligne », phase 3.2. `data/database/memory.db` porte **tout** :
la mémoire du chat, le journal des actions, les tâches en attente, la mémoire
personnelle, les entités et relations, et la file du gardien
(`core/guardian/`) — onze tables mesurées le 30/08/2026, un seul fichier.

Le paquet déployable (phase 3.1) monte `data/` en volume : le conteneur peut
être reconstruit sans effacer ce fichier. **Ce n'est pas une sauvegarde.** Un
volume protège d'un rebuild, pas d'un fichier corrompu, d'une écriture
interrompue, ni d'un `rm -rf data` — et ce dépôt a déjà vécu un `rm -rf`
malheureux (voir `docs/REPRISE.md`).

**Quatre règles :**

1. **La copie passe par l'API de sauvegarde de SQLite, jamais un `cp` brut.**
   Un fichier copié pendant une écriture peut saisir une page à moitié écrite ;
   l'API de SQLite prend un verrou le temps de la copie et rend un fichier
   cohérent, même si la base sert des requêtes au même moment.

2. **Une sauvegarde qui ne se restaure pas n'est pas une sauvegarde.**
   `PRAGMA integrity_check` tourne sur la copie elle-même, pas sur la source —
   sinon on prouverait que la base originale va bien, ce qu'on savait déjà.

3. **Le nombre de sauvegardes gardées est fini, et c'est écrit.** Sans purge,
   un répertoire de sauvegardes grossit pour toujours sur un serveur au disque
   modeste — exactement le genre de serveur que ce VOLET vise.

4. **Une sauvegarde ratée se rapporte, elle ne lève pas.** Ce script tourne
   depuis une tâche planifiée (cron) : une exception non attrapée y meurt en
   silence, alors qu'un rapport imprimé finit dans les journaux du système.
"""
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

RACINE = Path(__file__).resolve().parent.parent
if str(RACINE) not in sys.path:
    sys.path.insert(0, str(RACINE))

#: Le format du nom de fichier porte l'horodatage : trié alphabétiquement,
#: l'ordre des fichiers EST l'ordre chronologique — aucun tri par date de
#: modification n'est nécessaire pour retrouver la plus récente.
FORMAT_HORODATAGE = "%Y%m%d-%H%M%S"

#: Combien de sauvegardes garder par défaut. Une par jour, deux semaines :
#: assez pour revenir en arrière sans laisser le dossier grossir sans fin.
GARDER_PAR_DEFAUT = 14


@dataclass
class RapportSauvegarde:
    """Ce qui s'est réellement passé. `ok` sans `chemin` ne se construit pas."""

    ok: bool
    message: str
    chemin: Optional[Path] = None
    octets: Optional[int] = None
    supprimees: List[Path] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.ok and self.chemin is None:
            raise ValueError("un succès sans chemin ne prouve rien")


def _verifier_integrite(chemin: Path) -> Optional[str]:
    """Rend `None` si la copie s'ouvre et se lit sans erreur, sinon la raison.

    C'est la seule preuve qui compte : un fichier de la bonne taille peut
    quand même être une copie tronquée.
    """
    try:
        connexion = sqlite3.connect(str(chemin))
        try:
            resultat = connexion.execute("PRAGMA integrity_check").fetchone()
        finally:
            connexion.close()
    except sqlite3.Error as erreur:
        return f"{type(erreur).__name__}: {erreur}"
    if resultat is None or resultat[0] != "ok":
        return str(resultat[0]) if resultat else "aucune reponse"
    return None


def _purger(dossier: Path, motif: str, garder: int, proteger: Path) -> List[Path]:
    """Supprime les plus anciennes sauvegardes au-delà de `garder`. Rend celles retirées.

    `proteger` — la copie qui vient d'être écrite et vérifiée — ne fait jamais
    partie des candidates à la suppression, même avec `garder=0` : rapporter
    un succès puis effacer la preuve de ce succès dans la même fonction serait
    absurde. `garder` compte le total voulu, `proteger` inclus.
    """
    existantes = sorted(p for p in dossier.glob(motif) if p != proteger)
    limite = max(garder - 1, 0)  # une place du quota est deja prise par `proteger`
    excedent = existantes[:-limite] if limite > 0 else existantes
    for fichier in excedent:
        fichier.unlink()
    return excedent


def _copier_via_sqlite(source: Path, cible: Path) -> None:
    """La vraie copie : l'API de sauvegarde de SQLite, verrou pris le temps de la copie.

    Isolée dans sa propre fonction pour que les tests puissent la remplacer :
    `sqlite3.Connection` est un type C immuable, il ne se monkeypatch pas.
    """
    source_connexion = sqlite3.connect(str(source))
    cible_connexion = sqlite3.connect(str(cible))
    try:
        source_connexion.backup(cible_connexion)
    finally:
        cible_connexion.close()
        source_connexion.close()


def sauvegarder(source: Path, dossier: Path, garder: int = GARDER_PAR_DEFAUT,
                copier=_copier_via_sqlite) -> RapportSauvegarde:
    """Copie `source` dans `dossier`, vérifie la copie, purge les anciennes.

    Args:
        source: le fichier SQLite à sauvegarder.
        dossier: où écrire les copies horodatées.
        garder: combien de sauvegardes garder au total, celle-ci incluse.
        copier: la fonction de copie — remplaçable par les tests.

    Returns:
        Le rapport. Un échec à n'importe quelle étape efface la copie
        partielle plutôt que de laisser un fichier qui a l'air d'une
        sauvegarde et n'en est pas une.
    """
    if not source.exists():
        return RapportSauvegarde(
            ok=False, message=f"rien à sauvegarder : {source} n'existe pas")

    dossier.mkdir(parents=True, exist_ok=True)
    horodatage = datetime.now(timezone.utc).strftime(FORMAT_HORODATAGE)
    cible = dossier / f"{source.stem}-{horodatage}.db"

    try:
        copier(source, cible)
    except sqlite3.Error as erreur:
        cible.unlink(missing_ok=True)
        return RapportSauvegarde(
            ok=False, message=f"la copie a échoué : {type(erreur).__name__}: {erreur}")

    raison_invalide = _verifier_integrite(cible)
    if raison_invalide is not None:
        cible.unlink(missing_ok=True)
        return RapportSauvegarde(
            ok=False, message=f"copie écrite mais illisible, retirée : {raison_invalide}")

    supprimees = _purger(dossier, f"{source.stem}-*.db", garder, proteger=cible)

    return RapportSauvegarde(
        ok=True, message=f"sauvegarde ecrite et verifiee : {cible.name}",
        chemin=cible, octets=cible.stat().st_size, supprimees=supprimees)


def main() -> int:
    from apps.backend.config import DB_PATH

    dossier = RACINE / "data" / "sauvegardes"
    rapport = sauvegarder(DB_PATH, dossier)

    print("=" * 62)
    print("  ARENA — sauvegarde de la base. Copiee, puis relue pour verifier.")
    print("=" * 62)
    if rapport.ok:
        print(f"[OK]   {rapport.message}")
        print(f"       {rapport.octets} octets -> {rapport.chemin}")
    else:
        print(f"[ECHEC] {rapport.message}")
    if rapport.supprimees:
        print(f"       {len(rapport.supprimees)} ancienne(s) sauvegarde(s) retiree(s) "
              f"(retention {GARDER_PAR_DEFAUT})")
    print("=" * 62)
    return 0 if rapport.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
