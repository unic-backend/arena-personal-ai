"""Backend d'ARENA.

Ce fichier prépare le chemin du projet **avant** tout autre import du paquet.
Python garantit qu'il s'exécute en premier ; l'ordre des imports à l'intérieur
des modules, lui, dépend du tri de l'outil de lint — une garantie qui tient à un
nom de fichier n'en est pas une.
"""
import sys
from pathlib import Path

# Racine du dépôt : ce fichier est dans apps/backend/.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
