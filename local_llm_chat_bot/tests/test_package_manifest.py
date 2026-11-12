"""Read-only checks for the manually released local-chat-bot ZIP payload."""

from __future__ import annotations

from pathlib import Path
from pathlib import PurePosixPath
import ast
import unittest


APP = Path(__file__).resolve().parents[1]
REPOSITORY = APP.parent
MANIFEST = APP / "PACKAGE_MANIFEST.txt"
WORKFLOW = REPOSITORY / ".github" / "workflows" / "package_local_llm_chat_bot.yml"

REQUIRED = {
    "README_Bosch_Assembly_Assistant.md",
    "chat_workbench.py",
    "model_pricing.json",
    "requirements.txt",
    "Bosch_Assembly_Assistant.bat",
    "workbench_i18n.json",
}
ENTRY_POINT = "chat_workbench.py"


def package_files() -> list[str]:
    """Return the declared release payload without creating an archive."""
    return [
        line.strip()
        for line in MANIFEST.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


class PackageManifest(unittest.TestCase):
    def test_manifest_is_explicit_complete_and_safe(self):
        files = package_files()
        self.assertTrue(files, "The package manifest must name every shipped file.")
        self.assertEqual(files, sorted(files), "Keep the release payload easy to audit.")
        self.assertEqual(len(files), len(set(files)), "The manifest must not duplicate a file.")
        self.assertTrue(REQUIRED <= set(files), REQUIRED - set(files))
        print("Prospective ZIP payload (read-only):")
        for relative in files:
            with self.subTest(relative=relative):
                print(f"  local_llm_chat_bot/{relative}")
                path = APP / relative
                parsed = PurePosixPath(relative)
                self.assertFalse(parsed.is_absolute())
                self.assertNotIn("..", parsed.parts)
                self.assertTrue(path.is_file(), f"Missing packaged file: {relative}")
                self.assertFalse(relative.startswith(("tests/", "AI_Bot_State/", ".bosch_chat/", ".excel_chat_agent/")))
                self.assertNotIn("__pycache__", parsed.parts)
                self.assertNotIn("visual_cache", parsed.parts)
                self.assertFalse(relative.endswith((".env", ".env.local", ".zip")))
                self.assertNotIn(".env/", relative)

    def test_python_files_are_exactly_what_the_workbench_imports(self):
        """Every local module the Workbench imports is shipped, and nothing else."""
        local = {path.stem for path in APP.glob("*.py")}
        needed, todo = set(), [ENTRY_POINT[:-3]]
        while todo:
            module = todo.pop()
            if module in needed:
                continue
            needed.add(module)
            tree = ast.parse((APP / f"{module}.py").read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = ([alias.name for alias in node.names] if isinstance(node, ast.Import)
                         else [node.module] if isinstance(node, ast.ImportFrom) and node.module else [])
                todo.extend(name.split(".")[0] for name in names if name.split(".")[0] in local)
        shipped = {name[:-3] for name in package_files() if name.endswith(".py")}
        self.assertEqual(shipped, needed)

    def test_package_workflow_is_manual_gated_and_uses_the_manifest(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("workflow_dispatch:", workflow)
        self.assertNotIn("push:", workflow)
        self.assertIn("python -m pip install -r local_llm_chat_bot/requirements-dev.txt", workflow)
        self.assertIn("python -m unittest discover -s tests -p 'test_*.py'", workflow)
        self.assertIn("PACKAGE_MANIFEST.txt", workflow)
        self.assertNotIn("zip -qr local_llm_chat_bot.zip local_llm_chat_bot", workflow)


if __name__ == "__main__":
    unittest.main(verbosity=2)
