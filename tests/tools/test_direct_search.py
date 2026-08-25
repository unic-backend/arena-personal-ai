import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from tools.search.web_search_tool import WebSearchTool

print("🔍 Recherche Web en direct sur le Sénégal & la Tech...")
tool = WebSearchTool()
res = tool.search("actualites Senegal tech innovation", max_results=3)

print(f"✅ Nombre de résultats trouvés : {len(res)}")
for idx, r in enumerate(res, 1):
    print(f"\n{idx}. {r['title']}")
    print(f"   URL: {r['href']}")
    print(f"   Résumé: {r['body'][:120]}...")