"""Quels modules le chemin de reponse atteint-il vraiment ?

    python scripts/orphelins.py

Parcourt les imports depuis les points d entree reels — le serveur, la
passerelle PWA, le cablage et l orchestrateur — et nomme ce que personne
n atteint. Un module orphelin n est pas forcement a supprimer : c est une
question a poser, pas un verdict.

Ecrit le 2026-08-28, apres avoir decouvert que le calculateur de materiaux
n etait appele par personne depuis sa creation.
"""
import ast
import pathlib
from collections import deque

RACINE = pathlib.Path('.')
PAQUETS = ('core', 'agents', 'tools', 'apps', 'social')

def module_de(chemin: pathlib.Path) -> str:
    return str(chemin.with_suffix('')).replace('/', '.')

fichiers = {module_de(p): p for p in RACINE.rglob('*.py')
            if p.parts[0] in PAQUETS and '__pycache__' not in p.parts}

def imports(p: pathlib.Path):
    try:
        arbre = ast.parse(p.read_text(encoding='utf-8'))
    except Exception:
        return set()
    noms = set()
    for n in ast.walk(arbre):
        if isinstance(n, ast.Import):
            noms |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            noms.add(n.module)
            noms |= {f"{n.module}.{a.name}" for a in n.names}
    return noms

DEPART = ['apps.backend.main', 'apps.backend.routers.pwa_gateway',
          'apps.backend.runtime', 'agents.orchestrator.orchestrator_agent']
vus, file = set(), deque(m for m in DEPART if m in fichiers)
vus |= set(file)
while file:
    m = file.popleft()
    for cible in imports(fichiers[m]):
        for candidat in (cible, cible.rsplit('.', 1)[0] if '.' in cible else cible):
            if candidat in fichiers and candidat not in vus:
                vus.add(candidat)
                file.append(candidat)

orphelins = sorted(set(fichiers) - vus)
print(f"Modules totaux : {len(fichiers)}  |  atteints : {len(vus)}  |  orphelins : {len(orphelins)}\n")
for o in orphelins:
    if o.endswith('__init__') or o.startswith('apps.pwa.server'):
        continue
    print(' ', o)
