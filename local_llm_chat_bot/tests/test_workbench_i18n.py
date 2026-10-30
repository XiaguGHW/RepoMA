"""Offline catalog and embedded JavaScript checks; no app/model imports."""
import importlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
workbench_i18n = importlib.import_module("workbench_i18n")
load_catalog = workbench_i18n.load_catalog
validate_catalog = workbench_i18n.validate_catalog
catalog_script_json = workbench_i18n.catalog_script_json


class CatalogTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node.js required for UI handler checks')
    def test_material_confirmation_preserves_current_selection(self):
        source = (ROOT / 'chat_workbench.py').read_text(encoding='utf-8')
        handler = source.split('function contextSyncTarget(){', 1)[1].split('\nfunction ', 1)[0]
        handler = 'function contextSyncTarget(){' + handler
        # Confirming in the materials drawer syncs the drawer's path before analysing.
        self.assertIn("async function analyzeTarget(){if(!await allowRuleDraftTransition())return;if($('contexttargetpath'))contextSyncTarget();", source)
        assertions = r'''
const assert=require('node:assert/strict');
const fields={contexttargetpath:{value:' C:\\BG A '},targetpath:{value:'C:\\BG A'}};
const $=id=>fields[id];
let materialDraftDirty=false,selected=['C:\\BG A\\facts.txt'],submitted=null,clears=0;
function clearTargetTree(){selected=[];clears++}
function refreshContextPanel(){}
function analyzeTarget(){submitted=[...selected]}
contextSyncTarget();analyzeTarget();
assert.deepEqual(submitted,['C:\\BG A\\facts.txt'],'Confirm must submit the checked files');
assert.equal(clears,0,'An unchanged target must retain its file tree');
assert.equal(materialDraftDirty,false,'Confirming an unchanged target must not mark it changed');
selected=[];materialDraftDirty=true;
contextSyncTarget();analyzeTarget();
assert.deepEqual(submitted,[],'An empty selection must not restore previously selected files');
assert.equal(materialDraftDirty,true);
fields.contexttargetpath.value='C:\\BG B';selected=['C:\\BG A\\facts.txt'];
contextSyncTarget();
assert.deepEqual(selected,[],'A new target must clear the old file selection');
assert.equal(clears,1);
assert.equal(fields.targetpath.value,'C:\\BG B');
assert.equal(materialDraftDirty,true);
'''
        result = subprocess.run(['node'], input=handler + '\n' + assertions,
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

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

