"""F-13: no dead backend code and no runtime-overridden legacy UI functions."""

import inspect
from pathlib import Path
import re
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import chat_workbench as w

SOURCE = (Path(__file__).resolve().parents[1] / "chat_workbench.py").read_text(encoding="utf-8")
# The page template before the i18n catalog is embedded: script code only.
TEMPLATE = SOURCE[SOURCE.index("HTML = r'''"):SOURCE.index("'''", SOURCE.index("HTML = r'''") + 11)]

PUBLIC_RENDERERS = ["renderCoverageReport", "renderScanDrawer", "renderCacheAudit", "renderStatus",
                    "renderUsageDetail", "renderEvidenceSources", "renderCompareSlots", "renderSessionRows",
                    "openSessionMenu", "updateMaterialFlowButtons", "setScanReportAvailable", "clearTargetTree",
                    "updateTreeStatus", "makeTreeNode", "loadTargetTree", "ensureMaterialFlow"]
# Hard-coded copy that only existed in the overridden legacy implementations.
LEGACY_COPY = ["视觉证据已附带", "未知来源", "分类/Codebook 问题会自动准备证据", "选择模型…",
               "'files':'文件'", "'items':'个'", "取消置顶", "BG 综合档案：",
               "材料选择或模型已更新"]


class FrontendCleanup(unittest.TestCase):
    def test_each_public_renderer_is_declared_once_and_never_reassigned(self):
        for name in PUBLIC_RENDERERS:
            with self.subTest(name=name):
                declarations = re.findall(r"(?m)^(?:async\s+)?function\s+" + name + r"\s*\(", TEMPLATE)
                self.assertEqual(len(declarations), 1, name)
                self.assertEqual(re.findall(r"(?m)^" + name + r"\s*=", TEMPLATE), [], name)
        self.assertNotIn("baseRenderCoverageReport", TEMPLATE)
        self.assertNotIn("baseEnsureMaterialFlow", TEMPLATE)

    def test_public_renderers_delegate_to_the_language_aware_implementation(self):
        for name in PUBLIC_RENDERERS:
            if name == "ensureMaterialFlow":
                continue
            with self.subTest(name=name):
                line = re.search(r"(?m)^(?:async\s+)?function\s+" + name + r"\s*\(.*$", TEMPLATE).group(0)
                self.assertIn(name + "ForLanguage(", line)

    def test_legacy_hard_coded_copy_is_gone(self):
        for text in LEGACY_COPY:
            with self.subTest(text=text):
                self.assertNotIn(text, TEMPLATE)

    def test_status_lines_are_key_based_so_a_language_switch_redraws_them(self):
        one_shot = re.findall(r"""innerHTML='<span class="(?:ok|error|muted)">'\+(?:esc\()?(?:t|rt)\(""", TEMPLATE)
        self.assertEqual(one_shot, [])

    def test_backend_dead_code_is_removed(self):
        self.assertFalse(hasattr(w, "needs_bg_preparation"))
        source = inspect.getsource(w.activate_bg)
        body = source.split('"""')[-1]
        self.assertEqual(body.count("return"), 1)
        self.assertTrue(body.strip().splitlines()[-1].strip().startswith("return analyze_target("))
        self.assertIn("ignored", w.activate_bg.__doc__)


if __name__ == "__main__":
    unittest.main(verbosity=2)
