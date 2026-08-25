import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from tools.code.code_interpreter_tool import CodeInterpreterTool

def test_interpreter():
    print("🧪 Test du CodeInterpreterTool...")
    tool = CodeInterpreterTool()
    
    # Test 1 : Calcul mathématique & logique
    code_1 = """
def fibonacci(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a

print(f'Fibonacci(10) = {fibonacci(10)}')
"""
    res1 = tool.execute_python_code(code_1)
    print(f"   Test 1 (Calcul) : Success={res1['success']} | Output: {res1['stdout']}")
    assert res1['success'] == True
    assert "Fibonacci(10) = 55" in res1['stdout']
    
    # Test 2 : Capture d'erreur auto
    code_2 = "print(10 / 0)"
    res2 = tool.execute_python_code(code_2)
    print(f"   Test 2 (Détection d'erreur 0) : Success={res2['success']} | Error: {res2['stderr']}")
    assert res2['success'] == False
    assert "ZeroDivisionError" in res2['stderr']
    
    print("\n✅ CODE INTERPRETER LOCAL VALIDÉ AVEC SUCCÈS !")

if __name__ == "__main__":
    test_interpreter()