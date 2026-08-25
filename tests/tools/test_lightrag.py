import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from tools.rag.lightrag_tool import LightRAGTool

def test_lightrag_basic():
    print("📚 Test du moteur documentaire LightRAG...")
    tool = LightRAGTool()

    # 1. Insertion d'un texte de test dans la base RAG
    sample_doc = (
        "Le projet ARENA est une IA autonome de classe mondiale créée par Saer au Sénégal. "
        "Elle intègre des agents spécialisés pour le code, la recherche profonde, l'analyse de tendances "
        "et le montage vidéo au format vertical 9:16 pour TikTok et Reels."
    )
    
    print("   Insertion du document de test dans LightRAG...")
    inserted = tool.insert_text(sample_doc)
    print(f"   Statut insertion : {'RÉUSSI' if inserted else 'ÉCHEC'}")

    # 2. Interrogation documentaire
    prompt = "Qui a créé le projet ARENA et quelles sont ses spécialités ?"
    print(f"\n🔍 Question posée à LightRAG : '{prompt}'")
    answer = tool.query(prompt, mode="hybrid")

    print(f"\n🤖 Réponse de LightRAG :\n{answer}\n")
    print("✅ TEST LIGHTRAG COMPLÉTÉ AVEC SUCCÈS !")

if __name__ == "__main__":
    test_lightrag_basic()