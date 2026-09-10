"""Quels modules le chemin de reponse atteint-il vraiment ?

    python scripts/orphelins.py

Parcourt les imports depuis les points d entree reels — le serveur, la
passerelle PWA, le cablage et l orchestrateur — et nomme ce que personne
n atteint. Un module orphelin n est pas forcement a supprimer : c est une
question a poser, pas un verdict.

Ecrit le 2026-08-28, apres avoir decouvert que le calculateur de materiaux
n etait appele par personne depuis sa creation. C est la mesure qui suit la
mission de `docs/CURRENT_TASK.md`, et `tests/test_documentation.py` s en sert
pour verifier que le plan ne ment pas sur ce qui dort encore.
"""
import ast
import pathlib
from collections import deque
from typing import Dict, List, Set, Tuple

RACINE = pathlib.Path(__file__).resolve().parent.parent
PAQUETS = ('core', 'agents', 'tools', 'apps', 'social')

#: Les points d entree reels. Un module atteint depuis un script ne compte pas.
DEPART = ['apps.backend.main', 'apps.backend.routers.pwa_gateway',
          'apps.backend.runtime', 'agents.orchestrator.orchestrator_agent']

#: Les moteurs externes, installes SOUS `tools/` mais qui ne sont pas notre
#: code : ils ne sont pas versionnes (`.gitignore`), on ne les corrige pas, et
#: les compter comme orphelins ferait remonter des milliers de modules d'un
#: `.venv` (mesure du 03/09/2026 : le SDK Faceplugin en apporte plus de 3000).
MOTEURS_EXTERNES = ('tools/vision/faceplugin', 'tools/design/ui_ux_pro_max')

#: Des modules lances en SOUS-PROCESSUS, jamais importes.
#:
#: Un pont vers un moteur externe tourne avec l'interpreteur DE CE MOTEUR : il
#: ne peut pas etre importe par ARENA, sinon il chargerait torch dans notre
#: environnement. Il est pourtant bel et bien atteint — le declarer dormant
#: serait faux, et le citer dans le plan des modules qui dorment le serait
#: aussi. Chaque entree nomme qui le lance, pour qu'on puisse le verifier.
LANCES_EN_SOUS_PROCESSUS = {
    'core.connectors.ponts.faceplugin_pont': 'core/connectors/faceplugin.py',
}

#: Le service CSM (`tools/audio/csm_service/`, mission Sesame CSM, DEC-0080) :
#: du code ARENA, versionne, jamais importe par ARENA elle-meme — ni
#: directement, ni par un pont en sous-processus comme ci-dessus. C'est le
#: PROPRIETAIRE qui le lance (`python server.py`), dans son propre
#: environnement isole (`torch`/`transformers`, absents de l'environnement
#: principal — le meler l'importerait dans ARENA). `core/connectors/csm.py`
#: ne lui parle QUE par HTTP, jamais par import. Contrairement a
#: `LANCES_EN_SOUS_PROCESSUS`, aucun code d'ARENA ne le demarre : c'est donc
#: une categorie a part, pas le meme mecanisme deguise. Detail complet ->
#: `docs/audits/sesame_csm_audit.md`, section « Isolation des dependances ».
SERVICE_LANCE_PAR_LE_PROPRIETAIRE = frozenset({
    'tools.audio.csm_service.server',
    'tools.audio.csm_service.watermark',
    'tools.audio.csm_service.test_server',
})


def _module_de(chemin: pathlib.Path) -> str:
    """`core/memory/semantique.py` -> `core.memory.semantique`, partout.

    `as_posix()` n est pas un detail de style. Sous Windows, `str(chemin)` rend
    `core\\memory\\semantique` : aucun nom ne correspondait plus aux imports,
    le parcours ne trouvait meme pas ses points d entree, et TOUT le depot
    ressortait orphelin. Mesure le 2026-08-30 sur la machine du proprietaire —
    la CI, sous Linux, ne pouvait pas le voir.
    """
    return chemin.relative_to(RACINE).with_suffix('').as_posix().replace('/', '.')


def fichiers_du_projet() -> Dict[str, pathlib.Path]:
    """Tous les modules des paquets du projet, par nom pointe."""
    fichiers = {}
    for p in RACINE.rglob('*.py'):
        relatif = p.relative_to(RACINE)
        if relatif.parts[0] not in PAQUETS or '__pycache__' in p.parts:
            continue
        if any(relatif.as_posix().startswith(m) for m in MOTEURS_EXTERNES):
            continue
        fichiers[_module_de(p)] = p
    return fichiers


def _imports(chemin: pathlib.Path) -> Set[str]:
    """Ce qu un fichier importe. Un fichier illisible n importe rien, sans lever."""
    try:
        arbre = ast.parse(chemin.read_text(encoding='utf-8'))
    except Exception:
        return set()
    noms: Set[str] = set()
    for n in ast.walk(arbre):
        if isinstance(n, ast.Import):
            noms |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            noms.add(n.module)
            noms |= {f"{n.module}.{a.name}" for a in n.names}
    return noms


def parcourir() -> Tuple[Dict[str, pathlib.Path], Set[str], List[str]]:
    """Rend (tous les modules, ceux atteints, les orphelins tries)."""
    fichiers = fichiers_du_projet()
    vus: Set[str] = set()
    file = deque(m for m in DEPART if m in fichiers)
    vus |= set(file)
    while file:
        for cible in _imports(fichiers[file.popleft()]):
            paquet = cible.rsplit('.', 1)[0] if '.' in cible else cible
            for candidat in (cible, paquet):
                if candidat in fichiers and candidat not in vus:
                    vus.add(candidat)
                    file.append(candidat)
    return fichiers, vus, sorted(set(fichiers) - vus)


def est_reveillable(module: str) -> bool:
    """Un orphelin sur lequel il y a du travail a faire.

    Un `__init__.py` vide est un marqueur de paquet : il n y a rien a brancher.

    Une exemption pour `apps.pwa.server.*` vivait ici, avec pour raison « une
    question posee au proprietaire ». Elle a ete tranchee le 29/08/2026 —
    supprime — et l exemption est restee. Verifie le 01/09/2026 : elle ne
    masquait plus rien, mais elle aurait masque en silence tout module futur
    portant ce nom. Une exemption survit toujours a sa raison ; c est pour ca
    qu elle doit partir avec elle.
    """
    if module in LANCES_EN_SOUS_PROCESSUS or module in SERVICE_LANCE_PAR_LE_PROPRIETAIRE:
        return False
    return not module.endswith('__init__')


def orphelins_reels() -> List[str]:
    """Les modules qui existent, sont testes, et que personne n atteint."""
    return [o for o in parcourir()[2] if est_reveillable(o)]


if __name__ == '__main__':
    fichiers, vus, orphelins = parcourir()
    print(f"Modules totaux : {len(fichiers)}  |  atteints : {len(vus)}  "
          f"|  orphelins : {len(orphelins)}\n")
    for o in orphelins:
        if est_reveillable(o):
            print(' ', o)
