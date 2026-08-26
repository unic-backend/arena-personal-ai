import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from core.permissions.permission_manager import PermissionManager

def test_permissions():
    print("🔒 Test du Gestionnaire de Permissions...")
    pm = PermissionManager()
    
    # 1. Vérification des actions de base
    assert pm.is_allowed("READ_FILES") == True
    assert pm.is_allowed("WRITE_FILES") == True
    print("   ✅ Perms Lecture/Écriture : AUTORISÉES")
    
    # 2. Vérification de la sécurité (PUBLISH & DELETE bloqués)
    assert pm.is_allowed("PUBLISH") == False
    assert pm.is_allowed("DELETE") == False
    assert pm.is_allowed("EXECUTE_COMMANDS") == False
    print("   ✅ Perms Publication/Suppression/Exécution : SÉCURISÉES (BLOQUÉES)")

    # 3. Une permission inconnue est refusée, jamais supposée
    assert pm.is_allowed("PERMISSION_QUI_N_EXISTE_PAS") == False
    print("   ✅ Permission inconnue : REFUSÉE")
    
    print("\n🎉 TEST PERMISSIONS RÉUSSI AVEC SUCCÈS !\n")

if __name__ == "__main__":
    test_permissions()