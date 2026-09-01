import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger("usman.tools.swe_aci")

class SWEACITool:
    """Agent-Computer Interface (ACI) basée sur le papier de recherche SWE-agent (Princeton NLP)."""

    def __init__(self, root_dir: Optional[str] = None):
        self.root_dir = Path(root_dir).resolve() if root_dir else Path.cwd().resolve()

    def view(self, file_path: str, start_line: int = 1, end_line: int = 100) -> str:
        """Affiche les lignes exactes d'un fichier avec numérotation de lignes (Commande ACI)."""
        full_path = (self.root_dir / file_path).resolve()
        try:
            full_path.relative_to(self.root_dir)
            if not full_path.exists():
                return f"❌ Fichier introuvable: {file_path}"

            lines = full_path.read_text(encoding="utf-8", errors="ignore").splitlines()
            total_lines = len(lines)

            start = max(1, start_line)
            end = min(total_lines, end_line)

            output_lines = [f"--- {file_path} (Lignes {start} à {end} sur {total_lines}) ---"]
            for idx in range(start - 1, end):
                output_lines.append(f"{idx + 1:4d} | {lines[idx]}")

            return "\n".join(output_lines)
        except Exception as e:
            return f"❌ Erreur de lecture ACI: {e}"

    def search_dir(self, term: str, max_matches: int = 10) -> str:
        """Cherche un terme/fonction dans tout le projet (Commande ACI).

        Un fichier illisible est COMPTE, jamais avale : sans ce compte, une
        recherche qui n'avait rien pu ouvrir repondait « Aucun resultat », et
        l'agent qui la lisait en concluait que le terme n'existe pas. Une
        absence de resultat et une absence de lecture ne sont pas la meme
        reponse.
        """
        matches = []
        illisibles = []
        ignore_dirs = {".git", ".venv", "__pycache__", "node_modules"}

        for root, dirs, files in os.walk(self.root_dir):
            dirs[:] = [d for d in dirs if d not in ignore_dirs]
            for file in files:
                if file.endswith(('.py', '.md', '.html', '.json', '.yaml')):
                    file_path = Path(root) / file
                    try:
                        lines = file_path.read_text(encoding="utf-8", errors="ignore").splitlines()
                        for idx, line in enumerate(lines, start=1):
                            if term.lower() in line.lower():
                                rel_p = file_path.relative_to(self.root_dir)
                                matches.append(f"{rel_p}:{idx} | {line.strip()}")
                                if len(matches) >= max_matches:
                                    break
                    except OSError as erreur:
                        illisibles.append(f"{file_path.name} ({erreur.strerror or erreur})")
                if len(matches) >= max_matches:
                    break

        reserve = ""
        if illisibles:
            apercu = ", ".join(illisibles[:3])
            suite = f" (+{len(illisibles) - 3})" if len(illisibles) > 3 else ""
            reserve = (f"\n⚠️ {len(illisibles)} fichier(s) n'ont pas pu être lus, "
                       f"la recherche est incomplète : {apercu}{suite}")

        if not matches:
            return f"🔍 Aucun résultat pour '{term}'.{reserve}"
        return (f"🔍 Résultats pour '{term}' ({len(matches)} occurrences) :\n"
                + "\n".join(matches) + reserve)

    def edit(self, file_path: str, start_line: int, end_line: int, new_code: str) -> str:
        """Remplacement chirurgical de lignes de code (Commande ACI)."""
        full_path = (self.root_dir / file_path).resolve()
        try:
            full_path.relative_to(self.root_dir)
            if not full_path.exists():
                return f"❌ Fichier introuvable: {file_path}"

            lines = full_path.read_text(encoding="utf-8", errors="ignore").splitlines()

            # Remplacement des lignes de start_line à end_line
            new_code_lines = new_code.splitlines()
            updated_lines = lines[:start_line - 1] + new_code_lines + lines[end_line:]

            full_path.write_text("\n".join(updated_lines), encoding="utf-8")
            logger.info(f"Édition chirurgicale ACI appliquée sur {file_path} (lignes {start_line}-{end_line}).")
            return f"✅ Modification ACI appliquée avec succès sur {file_path} (lignes {start_line} à {end_line})."
        except Exception as e:
            return f"❌ Erreur d'édition ACI: {e}"

if __name__ == "__main__":
    aci = SWEACITool()
    print("🖥️ Outil SWEACITool prêt. Test view :")
    print(aci.view("README.md", 1, 10))
