"""La documentation dit-elle encore la vérité sur le code ?

Ces tests existent parce que le défaut le plus durable relevé par les audits du
26/08/2026 n'était pas dans le code : `docs/ROADMAP.md` cochait trois livrables
qui n'existaient pas. Une case cochée à tort empêche quiconque d'y revenir.
"""
import re
from pathlib import Path

import pytest

RACINE = Path(__file__).resolve().parent.parent
DOCS = RACINE / "docs"
WORKLOG = RACINE / "documents" / "USMAN_ENGINEERING_WORKLOG.md"

# Affirmations retirées le 26/08/2026 parce qu'elles étaient fausses.
# Si l'une revient cochée, c'est que le piège a été reposé.
AFFIRMATIONS_RETIREES = [
    "[x] Bac à sable Docker actif",
    "[x] Secrets déplacés vers `.env` et renouvelés",
    "[x] Dépôt Git assaini, dépendances complètes, tests fiables",
]


def fichiers_documentation():
    yield from DOCS.glob("*.md")
    yield WORKLOG
    yield RACINE / "README.md"


def test_le_carnet_de_bord_existe():
    assert WORKLOG.exists(), "documents/USMAN_ENGINEERING_WORKLOG.md est le point d'entrée"


@pytest.mark.parametrize("affirmation", AFFIRMATIONS_RETIREES)
def test_les_affirmations_fausses_ne_reviennent_pas(affirmation):
    roadmap = (DOCS / "ROADMAP.md").read_text(encoding="utf-8")

    assert affirmation not in roadmap, (
        f"'{affirmation}' avait été cochée sans vérification. "
        "Ne la recocher qu'après avoir exécuté la vérification correspondante."
    )


def test_next_steps_ne_decrit_plus_la_phase_0():
    contenu = (DOCS / "NEXT_STEPS.md").read_text(encoding="utf-8")

    assert "Créer README.md" not in contenu
    assert (RACINE / "README.md").exists()


def test_le_rapport_de_travail_n_est_pas_duplique():
    assert not (RACINE / "RAPPORT_TRAVAIL.txt").exists(), (
        "Le rapport ne doit exister qu'une fois, dans docs/."
    )
    assert (DOCS / "RAPPORT_TRAVAIL.txt").exists()


def test_aucun_secret_en_clair_dans_la_documentation():
    """Un document qui décrit une fuite ne doit pas la reproduire.

    La valeur cherchée n'est volontairement pas écrite d'un seul tenant : ce
    fichier deviendrait sinon lui-même une fuite, et ferait échouer le scan de
    secrets à venir (T-03). Cette rechute s'est déjà produite deux fois.
    """
    motif = re.compile("arena-saer" + r"-2026")
    coupables = [
        str(f.relative_to(RACINE))
        for f in fichiers_documentation()
        if f.exists() and motif.search(f.read_text(encoding="utf-8"))
    ]

    assert coupables == [], f"valeur de clé écrite en clair dans : {coupables}"


def test_les_fichiers_cites_par_la_documentation_existent():
    """Un chemin cité entre accents graves doit correspondre à un fichier réel."""
    motif = re.compile(r"`([\w./-]+\.(?:py|yaml|yml|md|txt|toml|html|lock))`")
    ignores = {
        ".env",  # jamais versionné, par construction
        "requirements.lock.txt",
    }
    manquants = []
    for doc in fichiers_documentation():
        if not doc.exists():
            continue
        for chemin in set(motif.findall(doc.read_text(encoding="utf-8"))):
            if chemin in ignores or "/" not in chemin:
                continue
            if not (RACINE / chemin).exists():
                manquants.append(f"{doc.relative_to(RACINE)} → {chemin}")

    assert manquants == [], "chemins cités mais introuvables :\n  " + "\n  ".join(manquants)


# --- La mission en cours dit-elle la vérité sur ce qui dort ? --------------------
#
# Le plan de `docs/CURRENT_TASK.md` ne vaut que s'il reste exact. Un module
# réveillé et oublié dans le plan enverrait le prochain assistant brancher
# quelque chose qui l'est déjà ; un module qui s'endort sans y entrer ne serait
# jamais repris. Ces tests font échouer les deux cas.

MISSION = DOCS / "CURRENT_TASK.md"


def modules_cites_par_la_mission():
    """Les modules du tableau numéroté du plan, en notation pointée.

    Seules les lignes `| 1 | ... |` comptent : le reste du document cite aussi
    des fichiers où brancher (`apps/backend/runtime.py`), qui ne sont pas des
    modules à réveiller.
    """
    ligne_numerotee = re.compile(r"^\|\s*\d+\s*\|")
    chemin = re.compile(r"`((?:core|agents|tools|apps|social)/[\w/]+)\.py`")
    cites = set()
    for ligne in MISSION.read_text(encoding="utf-8").splitlines():
        if ligne_numerotee.match(ligne):
            cites |= set(chemin.findall(ligne))
    return {c.replace("/", ".") for c in cites}


def test_le_plan_nomme_exactement_les_modules_qui_dorment():
    """Ni un module réveillé oublié dans le plan, ni un dormant absent."""
    import sys

    sys.path.insert(0, str(RACINE / "scripts"))
    from orphelins import orphelins_reels

    dorment = set(orphelins_reels())
    cites = modules_cites_par_la_mission()

    assert dorment - cites == set(), (
        "des modules dorment sans figurer dans docs/CURRENT_TASK.md : "
        f"{sorted(dorment - cites)}")
    assert cites - dorment == set(), (
        "docs/CURRENT_TASK.md demande de brancher des modules déjà atteints : "
        f"{sorted(cites - dorment)}. Les retirer du plan et le dire dans "
        "« Ce qui est déjà fait ».")


def test_les_points_d_entree_dirigent_vers_la_mission():
    """Un assistant qui arrive sans contexte doit tomber dessus, pas la chercher."""
    manquants = [
        nom for nom, fichier in (
            ("CLAUDE.md", RACINE / "CLAUDE.md"),
            ("docs/START_HERE.md", DOCS / "START_HERE.md"),
            ("docs/REPRISE.md", DOCS / "REPRISE.md"),
        )
        if "CURRENT_TASK.md" not in fichier.read_text(encoding="utf-8")
    ]

    assert manquants == [], (
        f"ces points d'entrée ne mènent pas à la mission en cours : {manquants}")


def test_les_noms_de_modules_sont_pointes_sur_les_deux_systemes():
    """`scripts/orphelins.py` doit rendre `a.b.c`, jamais `a\\b\\c`.

    Mesuré le 30/08/2026 sur la machine du propriétaire (Windows) :
    `str(chemin).replace('/', '.')` laissait les antislashs intacts. Aucun nom
    ne correspondait plus aux imports, le parcours ne retrouvait même pas ses
    points d'entrée, et **tout le dépôt ressortait orphelin** — le plan de
    `docs/CURRENT_TASK.md` échouait en réclamant des modules déjà branchés.

    Ce test est structurel, et il l'est pour la même raison que celui du
    transport MCP : sous Linux les chemins utilisent `/`, donc le défaut est
    invisible ici. Seule l'absence de la construction fragile se vérifie des
    deux côtés.
    """
    source = (RACINE / "scripts" / "orphelins.py").read_text(encoding="utf-8")
    # La ligne qui construit le nom, pas la prose qui l'explique.
    retours = [ligne.strip() for ligne in source.splitlines()
               if ligne.strip().startswith("return chemin.relative_to")]

    assert retours, "la construction du nom de module a disparu ou changé de forme"
    assert all("as_posix()" in ligne for ligne in retours), (
        "les noms de modules ne sont plus construits en POSIX : sous Windows "
        f"ils sortiront avec des antislashs et le parcours ne trouvera rien — {retours}")


class TestLeDetecteurNeGardePasUneExemptionMorte:
    """Une exemption survit toujours à sa raison. Elle doit partir avec elle.

    `est_reveillable` exemptait `apps.pwa.server.*` parce que son sort était
    « une question posée au propriétaire ». La question a été tranchée le
    29/08/2026 — le dossier supprimé — et l'exemption est restée. Vérifié le
    01/09/2026 : elle ne masquait plus rien, mais elle aurait masqué en silence
    tout module futur portant ce nom.
    """

    def test_seuls_les_marqueurs_de_paquet_sont_exemptes(self):
        from scripts.orphelins import est_reveillable

        assert est_reveillable("apps.pwa.server.main") is True
        assert est_reveillable("core.memory.__init__") is False
        assert est_reveillable("core.memory.semantique") is True

    def test_aucune_exemption_ne_nomme_un_chemin_disparu(self):
        """Une exemption qui nomme un chemin absent du dépôt est morte."""
        import inspect
        from pathlib import Path

        from scripts import orphelins

        racine = Path(orphelins.__file__).resolve().parent.parent
        source = inspect.getsource(orphelins.est_reveillable)
        corps = source.split('"""')[-1]  # la docstring raconte l'histoire, pas la règle

        for fragment in ("apps.pwa", "apps/pwa"):
            assert fragment not in corps, (
                f"{fragment} est encore exempté alors que "
                f"{'existe' if (racine / 'apps' / 'pwa').exists() else 'le dossier a disparu'}"
            )
