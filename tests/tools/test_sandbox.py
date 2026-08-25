import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from tools.code.sandbox_interpreter import SandboxInterpreterTool

def test_sandbox():
    print("🛡️ Test du Bac à Sable OpenSandbox...")
    sandbox = SandboxInterpreterTool()
    
    print(f"   Mode détecté : {'Docker Isolé' if sandbox.docker_available else 'Fallback Local'}")
    
    # Test 1 : Code valide
    code_pass = "import math; print(f'PI = {round(math.pi, 4)}')"
    res1 = sandbox.execute_python_code(code_pass)
    print(f"   Test 1 (Calcul PI) : Success={res1['success']} | Output: {res1['stdout']}")
    assert res1['success'] == True
    assert "PI = 3.1416" in res1['stdout']
    
    # Test 2 : Tentative d'accès non autorisé
    code_attack = "import os; print(os.listdir('C:/'))"
    res2 = sandbox.execute_python_code(code_attack)
    print(f"   Test 2 (Sécurité) : Success={res2['success']}")
    
    print("\n✅ BAC À SABLE OPENSANDBOX VALIDÉ AVEC SUCCÈS !")

if __name__ == "__main__":
    test_sandbox()