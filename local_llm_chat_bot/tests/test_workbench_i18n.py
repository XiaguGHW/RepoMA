"""Offline catalog and embedded JavaScript checks; no app/model imports."""
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from workbench_i18n import load_catalog, validate_catalog, catalog_script_json


class CatalogTests(unittest.TestCase):
    def test_complete_catalog(self):
        validate_catalog(load_catalog())

    def test_missing_language_key_is_rejected(self):
        catalog = load_catalog()
        del catalog['messages']['de']['welcome.title']
        with self.assertRaisesRegex(ValueError, 'keys differ'):
            validate_catalog(catalog)

    def test_wrong_placeholder_is_rejected(self):
        catalog = load_catalog()
        catalog['messages']['en']['reading.file'] = 'Reading {wrong}'
        with self.assertRaisesRegex(ValueError, 'Placeholder mismatch'):
            validate_catalog(catalog)

    def test_empty_or_chinese_foreign_translation_is_rejected(self):
        for value in ('', '正在处理'):
            catalog = load_catalog()
            catalog['messages']['en']['welcome.title'] = value
            with self.assertRaises(ValueError):
                validate_catalog(catalog)

    def test_literal_translation_calls_have_keys(self):
        source = (ROOT / 'chat_workbench.py').read_text(encoding='utf-8')
        source = '\n'.join(line for line in source.splitlines()
                           if not line.lstrip().startswith('//'))
        keys = load_catalog()['messages']['zh']
        for key in re.findall(r"\b(?:t|rt)\('([^']+)'", source):
            self.assertIn(key, keys)

    def test_translation_does_not_observe_or_reclassify_runtime_text(self):
        source = (ROOT / 'chat_workbench.py').read_text(encoding='utf-8')
        self.assertIn('function bindInitialStaticI18n()', source)
        self.assertIn('const initialStaticText=[],initialStaticAttributes=[]', source)
        self.assertNotIn('initLegacyDynamicTranslations', source)
        self.assertNotIn('originalText=', source)
        self.assertNotIn('__legacyTranslationObserver', source)

    def test_language_switch_rebuilds_dynamic_ui_from_data_snapshots(self):
        source = (ROOT / 'chat_workbench.py').read_text(encoding='utf-8')
        self.assertIn('function rerenderLanguageSensitiveUI()', source)
        self.assertIn('rerenderLanguageSensitiveUI();', source)
        self.assertIn('lastStatusSnapshot', source)
        self.assertIn('lastCodebookProfile', source)
        self.assertIn('lastScanReport', source)
        self.assertIn('lastCacheAudit', source)
        self.assertIn('renderScanDrawerForLanguage', source)
        self.assertIn('renderCacheAuditForLanguage', source)
        self.assertIn('renderStatusForLanguage', source)
        self.assertIn('renderUsageDetailForLanguage', source)
        self.assertIn('renderCompareSlotsForLanguage', source)
        self.assertIn('renderSessionRowsForLanguage', source)
        self.assertIn('renderCoverageReportForLanguage', source)

    def test_dynamic_controls_have_explicit_language_refresh(self):
        """Late-created controls cannot rely on the initial DOM text scan."""
        source = (ROOT / 'chat_workbench.py').read_text(encoding='utf-8')
        self.assertIn('function localizeComposerControls()', source)
        self.assertIn("setI18nText($('composermodelnote'),'model.current')", source)
        self.assertIn("setI18nText($('modeltestbutton'),'model.test')", source)
        self.assertIn('function localizeSessionChrome()', source)
        self.assertIn("setI18nText($('newsessionbutton'),'session.new')", source)
        rerender = source.split('function rerenderLanguageSensitiveUI()', 1)[1].split('\n}', 1)[0]
        self.assertIn('localizeComposerControls();', rerender)
        self.assertIn('localizeSessionChrome();', rerender)

    def test_script_serialization(self):
        payload = catalog_script_json()
        self.assertNotIn('<', payload)
        self.assertEqual(json.loads(payload), load_catalog())

    @unittest.skipUnless(shutil.which('node'), 'Node.js required for JavaScript checks')
    def test_javascript_syntax_and_translator(self):
        source = (ROOT / 'chat_workbench.py').read_text(encoding='utf-8')
        script = source.split('<script>', 1)[1].split('</script>', 1)[0]
        script = script.replace('__WORKBENCH_I18N_JSON__', catalog_script_json())
        subprocess.run(['node', '--check'], input=script, text=True, check=True,
                       capture_output=True)
        translator = script.split('function applyLanguage()', 1)[0]
        assertions = r'''
const assert=require('node:assert/strict');
for(const language of ['zh','en','de','zh','en','de']){
  uiLanguage=language;
  assert.equal(t('welcome.title'),CATALOG.messages[language]['welcome.title']);
  assert.equal(tr('你想进行什么分析？'),t('welcome.title'));
  assert.equal(rt('model.processing'),t('model.processing'));
  const name='原始材料_<&>_Roboter.pdf';
  assert(t('reading.file',{index:0,total:2,name}).includes(name));
  assert(t('reading.file',{index:0,total:2,name}).includes('0/2'));
  assert(t('reading.file').includes('{name}'));
}
'''
        subprocess.run(['node'], input=translator+assertions, text=True,
                       check=True, capture_output=True)


if __name__ == '__main__':
    unittest.main()
