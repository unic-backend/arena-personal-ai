"""Verifie que le bac a sable protege vraiment la machine.

    Lancer avec :  .venv/Scripts/python.exe tests/tools/test_sandbox.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from tools.code.sandbox_interpreter import SandboxInterpreterTool


def main():
    bac = SandboxInterpreterTool()
    isole = bac.docker_available
    repli_autorise = SandboxInterpreterTool._repli_non_isole_autorise()

    print("Test du bac a sable")
    if isole:
        mode = "DOCKER ISOLE"
    elif repli_autorise:
        mode = "FALLBACK LOCAL (non protege, ALLOW_UNSAFE_EXEC actif)"
    else:
        mode = "AUCUN (execution refusee)"
    print("  Mode : %s" % mode)
    print("-" * 62)

    # Sans Docker et sans flag, refuser est le comportement attendu :
    # verifier le refus, pas l execution.
    if not isole and not repli_autorise:
        r = bac.execute_python_code("print('ceci ne doit pas s executer')")
        if r["success"] or r.get("sandbox_mode") != "REFUSED":
            print("  ECHEC  Le code a ete execute alors qu aucun bac a sable n existe")
            sys.exit(1)
        print("  OK     Execution refusee en l absence de bac a sable")
        print("-" * 62)
        print("Le bac a sable n est pas actif : ARENA refuse d executer du code.")
        print("Demarre Docker Desktop puis relance ce test.")
        sys.exit(1)

    echecs = []

    # 1. Le code normal doit fonctionner
    r = bac.execute_python_code("import math; print(round(math.pi, 4))")
    if r["success"] and "3.1416" in r["stdout"]:
        print("  OK     Execution d un calcul simple")
    else:
        print("  ECHEC  Execution d un calcul simple -> %s" % (r["stderr"][:80]))
        echecs.append("calcul simple")

    # 2. Les outils de maths doivent etre disponibles
    r = bac.execute_python_code(
        "import sympy; x = sympy.Symbol('x'); print(sympy.solve(x**2 - 5*x + 6, x))"
    )
    if r["success"] and "[2, 3]" in r["stdout"]:
        print("  OK     Calcul mathematique avec sympy")
    else:
        print("  ECHEC  Calcul mathematique avec sympy -> %s" % (r["stderr"][:80]))
        echecs.append("sympy")

    # 3. et 4. : protections, verifiables uniquement en mode Docker
    if not isole:
        print("  IGNORE Tests de securite (ALLOW_UNSAFE_EXEC : pas de bac a sable)")
        print("-" * 62)
        print("ATTENTION : le code s execute sur la machine, sans isolation.")
        print("Demarre Docker Desktop et retire ALLOW_UNSAFE_EXEC.")
        sys.exit(1)

    r = bac.execute_python_code("import os; print(os.listdir('C:/'))")
    if r["success"]:
        print("  ECHEC  Le code a pu lire le disque de la machine")
        echecs.append("acces disque")
    else:
        print("  OK     Acces au disque bloque")

    r = bac.execute_python_code(
        "import urllib.request; print(urllib.request.urlopen('http://example.com', timeout=5).status)"
    )
    if r["success"]:
        print("  ECHEC  Le code a pu sortir sur Internet")
        echecs.append("acces internet")
    else:
        print("  OK     Acces Internet bloque")

    print("-" * 62)
    if echecs:
        print("%d ECHEC(S) : %s" % (len(echecs), ", ".join(echecs)))
        sys.exit(1)

    print("Bac a sable operationnel : la machine est protegee.")


if __name__ == "__main__":
    main()
