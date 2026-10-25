"""R14 final verification: the native picker receives the current UI title."""
from pathlib import Path
import sys
from types import ModuleType
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient  # noqa: E402 - sibling app import
import chat_workbench as w  # noqa: E402
from workbench_i18n import UIMessage  # noqa: E402


class NativePickerLanguage(unittest.TestCase):
    def test_native_picker_uses_language_header_for_both_dialogs(self):
        tk = ModuleType('tkinter')
        root = Mock()
        tk.Tk = Mock(return_value=root)
        dialogs = ModuleType('tkinter.filedialog')
        path = 'C:/Fixture 中文 ü/材料 {count}.pdf'
        dialogs.askopenfilename = Mock(return_value=path)
        dialogs.askdirectory = Mock(return_value=path)
        tk.filedialog = dialogs
        old = dict(w.ACTIVE)
        self.addCleanup(w.ACTIVE.update, old)
        self.addCleanup(w.ACTIVE.clear)
        w.ACTIVE.clear()
        w.ACTIVE['language'] = 'zh'  # Header wins even before language-save finishes.
        with patch.dict(sys.modules, {'tkinter': tk, 'tkinter.filedialog': dialogs}), TestClient(w.app) as client:
            for language in ['zh', 'en', 'de']:
                for kind in ['file', 'folder']:
                    with self.subTest(language=language, kind=kind):
                        response = client.get('/api/pick/' + kind, headers={'X-Workbench-Language': language})
                        self.assertEqual(response.status_code, 200, response.text)
                        self.assertEqual(response.json()['path'], path)
                        dialog = dialogs.askopenfilename if kind == 'file' else dialogs.askdirectory
                        key = 'picker.file_title' if kind == 'file' else 'picker.folder_title'
                        self.assertEqual(dialog.call_args.kwargs['title'], str(UIMessage(key, language)))
            cancelled = dialogs.askopenfilename
            cancelled.return_value = ''
            self.assertEqual(client.get('/api/pick/file').json()['path'], '')
            before = tk.Tk.call_count
            self.assertEqual(client.get('/api/pick/unsupported').status_code, 400)
            self.assertEqual(tk.Tk.call_count, before)
        self.assertEqual(root.destroy.call_count, 7)


if __name__ == '__main__':
    unittest.main()
