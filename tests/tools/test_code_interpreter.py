"""Interpréteur local : exécution réelle d'un script Python dans un sous-processus.

Ce test ne dépend d'aucun service externe — il lance l'interpréteur de la machine.
"""
from tools.code.code_interpreter_tool import CodeInterpreterTool

FIBONACCI = """
def fibonacci(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a

print(f'Fibonacci(10) = {fibonacci(10)}')
"""


def test_un_code_valide_s_execute_et_renvoie_sa_sortie():
    res = CodeInterpreterTool().execute_python_code(FIBONACCI)

    assert res["success"] is True
    assert res["exit_code"] == 0
    assert "Fibonacci(10) = 55" in res["stdout"]


def test_une_erreur_est_remontee_et_pas_avalee():
    res = CodeInterpreterTool().execute_python_code("print(10 / 0)")

    assert res["success"] is False
    assert "ZeroDivisionError" in res["stderr"]


def test_les_balises_markdown_sont_retirees_avant_execution():
    res = CodeInterpreterTool().execute_python_code("```python\nprint('bonjour')\n```")

    assert res["success"] is True
    assert res["stdout"] == "bonjour"
    assert "```" not in res["executed_code"]


def test_un_code_trop_long_est_interrompu():
    res = CodeInterpreterTool(timeout_seconds=1).execute_python_code("import time; time.sleep(10)")

    assert res["success"] is False
    assert res["exit_code"] == -1
    assert "Temps d'exécution dépassé" in res["stderr"]
