# Step 8 — remaining static findings (2026-10-25)

This is an itemized snapshot of active findings, not a suppression/baseline file.
Run commands from local_llm_chat_bot with the pinned tools in requirements-dev.txt:

```bash
python -m ruff check --output-format json .
python -m mypy
```

Ruff 0.17.2 reports 260 findings; mypy 1.15.0 reports 44 errors in 6 files while checking 11 application modules for Python 3.10.
The new startup module and new/modified browser and startup tests pass full Ruff. The startup module has no mypy findings.
Both full commands remain nonzero. No ignores, exclusions, expected-failure markers or reduced module lists were added.
The prior step had 264 Ruff findings and 44 mypy errors. Four compact-statement findings disappeared when rewriting setup; the residual counts do not claim a clean release gate.

## Dispositions

| ID | Why retained in this stage; follow-up |
|---|---|
| S1 | Existing compact Python statements. Expand statement/block layout in a separate behavior-preserving cleanup, then rerun regressions. The fatal syntax/name subset passes. |
| S2 | Existing unused imports. Remove individually after checking import side effects. Not introduced by R16. |
| S3 | Existing test import after sys.path setup. Make its portable import boundary explicit without removing the JS/catalog test. |
| T1 | Existing provider callback/body inference. Add explicit callback and heterogeneous request-payload types, preserving transport behavior. |
| T2 | LocalDocumentLibrary.list shadows the builtin annotation name in the class; qualify list annotations and then type OCR/visual containers. Do not rename the public method without checking callers. |
| T3 | A local name is reused for a string identifier and a visual tuple key. Separate those variable names/types, retaining cache identity. |
| T4 | Existing dynamic JSON/state/action containers infer object or overly narrow element types. Add precise boundary/container annotations based on existing validation; do not replace validation with casts or Any everywhere. |
| T5 | split_qualified promises a tuple but returns str.rsplit's list. Make the contract/return representation agree and verify Excel plan callers. Runtime unpacking currently accepts the two-element list. |
| T6 | Excel chat stream-kind and optional tool-name inference. Type the optional stream state and validate/narrow tool names before lookup. |
| T7 | Codebook normalized rules contain strings, integer page lists and optional table structures. Declare the heterogeneous record type explicitly; preserve normalized data and reference validation. |
| T8 | Classification ranking tuples carry floating-point scores where annotations expect int. Correct score annotations and retain ranking/reference regression tests. |

## Ruff — each remaining finding

| # | Location | Rule | Diagnostic | Disposition |
|---:|---|---|---|---|
| 1 | `bosch_chat.py:12:8` | F401 | `textwrap` imported but unused | S2 |
| 2 | `bosch_chat.py:42:85` | E702 | Multiple statements on one line (semicolon) | S1 |
| 3 | `bosch_chat.py:47:30` | E701 | Multiple statements on one line (colon) | S1 |
| 4 | `bosch_chat.py:50:81` | E701 | Multiple statements on one line (colon) | S1 |
| 5 | `bosch_chat.py:57:135` | E702 | Multiple statements on one line (semicolon) | S1 |
| 6 | `bosch_chat.py:60:20` | E702 | Multiple statements on one line (semicolon) | S1 |
| 7 | `bosch_chat.py:98:34` | E702 | Multiple statements on one line (semicolon) | S1 |
| 8 | `bosch_chat.py:98:85` | E702 | Multiple statements on one line (semicolon) | S1 |
| 9 | `bosch_chat.py:98:98` | E702 | Multiple statements on one line (semicolon) | S1 |
| 10 | `bosch_chat.py:99:25` | E701 | Multiple statements on one line (colon) | S1 |
| 11 | `bosch_chat.py:104:44` | E701 | Multiple statements on one line (colon) | S1 |
| 12 | `bosch_chat.py:106:25` | E701 | Multiple statements on one line (colon) | S1 |
| 13 | `bosch_chat.py:114:25` | E701 | Multiple statements on one line (colon) | S1 |
| 14 | `bosch_chat.py:139:94` | E702 | Multiple statements on one line (semicolon) | S1 |
| 15 | `bosch_chat.py:144:12` | E701 | Multiple statements on one line (colon) | S1 |
| 16 | `bosch_chat.py:145:45` | E701 | Multiple statements on one line (colon) | S1 |
| 17 | `bosch_chat.py:145:54` | E702 | Multiple statements on one line (semicolon) | S1 |
| 18 | `bosch_chat.py:146:20` | E701 | Multiple statements on one line (colon) | S1 |
| 19 | `bosch_chat.py:147:38` | E701 | Multiple statements on one line (colon) | S1 |
| 20 | `bosch_chat.py:148:27` | E701 | Multiple statements on one line (colon) | S1 |
| 21 | `bosch_chat.py:148:41` | E702 | Multiple statements on one line (semicolon) | S1 |
| 22 | `bosch_chat.py:150:63` | E702 | Multiple statements on one line (semicolon) | S1 |
| 23 | `bosch_chat.py:150:138` | E702 | Multiple statements on one line (semicolon) | S1 |
| 24 | `bosch_chat.py:150:171` | E702 | Multiple statements on one line (semicolon) | S1 |
| 25 | `bosch_chat.py:154:48` | E702 | Multiple statements on one line (semicolon) | S1 |
| 26 | `bosch_chat.py:163:16` | E701 | Multiple statements on one line (colon) | S1 |
| 27 | `bosch_chat.py:164:36` | E701 | Multiple statements on one line (colon) | S1 |
| 28 | `bosch_chat.py:168:16` | E701 | Multiple statements on one line (colon) | S1 |
| 29 | `bosch_chat.py:169:36` | E701 | Multiple statements on one line (colon) | S1 |
| 30 | `bosch_chat.py:172:59` | E701 | Multiple statements on one line (colon) | S1 |
| 31 | `bosch_chat.py:175:61` | E701 | Multiple statements on one line (colon) | S1 |
| 32 | `bosch_chat.py:178:54` | E702 | Multiple statements on one line (semicolon) | S1 |
| 33 | `bosch_chat.py:178:69` | E702 | Multiple statements on one line (semicolon) | S1 |
| 34 | `bosch_chat.py:178:103` | E702 | Multiple statements on one line (semicolon) | S1 |
| 35 | `bosch_chat.py:185:42` | E702 | Multiple statements on one line (semicolon) | S1 |
| 36 | `bosch_chat.py:187:26` | E701 | Multiple statements on one line (colon) | S1 |
| 37 | `chat_workbench.py:161:25` | E702 | Multiple statements on one line (semicolon) | S1 |
| 38 | `chat_workbench.py:163:25` | E702 | Multiple statements on one line (semicolon) | S1 |
| 39 | `chat_workbench.py:169:25` | E702 | Multiple statements on one line (semicolon) | S1 |
| 40 | `chat_workbench.py:499:34` | E701 | Multiple statements on one line (colon) | S1 |
| 41 | `chat_workbench.py:617:39` | E702 | Multiple statements on one line (semicolon) | S1 |
| 42 | `chat_workbench.py:620:37` | E701 | Multiple statements on one line (colon) | S1 |
| 43 | `chat_workbench.py:621:38` | E702 | Multiple statements on one line (semicolon) | S1 |
| 44 | `chat_workbench.py:623:42` | E702 | Multiple statements on one line (semicolon) | S1 |
| 45 | `chat_workbench.py:690:38` | E701 | Multiple statements on one line (colon) | S1 |
| 46 | `chat_workbench.py:977:30` | E702 | Multiple statements on one line (semicolon) | S1 |
| 47 | `chat_workbench.py:1136:35` | E702 | Multiple statements on one line (semicolon) | S1 |
| 48 | `chat_workbench.py:1205:49` | E701 | Multiple statements on one line (colon) | S1 |
| 49 | `chat_workbench.py:1221:49` | E701 | Multiple statements on one line (colon) | S1 |
| 50 | `chat_workbench.py:1227:45` | E702 | Multiple statements on one line (semicolon) | S1 |
| 51 | `chat_workbench.py:1579:31` | E701 | Multiple statements on one line (colon) | S1 |
| 52 | `chat_workbench.py:1580:30` | E701 | Multiple statements on one line (colon) | S1 |
| 53 | `chat_workbench.py:1713:76` | E701 | Multiple statements on one line (colon) | S1 |
| 54 | `chat_workbench.py:1726:41` | E702 | Multiple statements on one line (semicolon) | S1 |
| 55 | `chat_workbench.py:1845:42` | E702 | Multiple statements on one line (semicolon) | S1 |
| 56 | `chat_workbench.py:1847:31` | E702 | Multiple statements on one line (semicolon) | S1 |
| 57 | `chat_workbench.py:2015:34` | E701 | Multiple statements on one line (colon) | S1 |
| 58 | `chat_workbench.py:2091:29` | E702 | Multiple statements on one line (semicolon) | S1 |
| 59 | `chat_workbench.py:2094:49` | E702 | Multiple statements on one line (semicolon) | S1 |
| 60 | `chat_workbench.py:2112:25` | E702 | Multiple statements on one line (semicolon) | S1 |
| 61 | `chat_workbench.py:2133:21` | E702 | Multiple statements on one line (semicolon) | S1 |
| 62 | `chat_workbench.py:2138:56` | E702 | Multiple statements on one line (semicolon) | S1 |
| 63 | `chat_workbench.py:2153:21` | E702 | Multiple statements on one line (semicolon) | S1 |
| 64 | `chat_workbench.py:2226:38` | E701 | Multiple statements on one line (colon) | S1 |
| 65 | `chat_workbench.py:2230:23` | E702 | Multiple statements on one line (semicolon) | S1 |
| 66 | `chat_workbench.py:2230:40` | E702 | Multiple statements on one line (semicolon) | S1 |
| 67 | `chat_workbench.py:2270:21` | E702 | Multiple statements on one line (semicolon) | S1 |
| 68 | `chat_workbench.py:2457:29` | E701 | Multiple statements on one line (colon) | S1 |
| 69 | `chat_workbench.py:2459:38` | E701 | Multiple statements on one line (colon) | S1 |
| 70 | `chat_workbench.py:2467:29` | E702 | Multiple statements on one line (semicolon) | S1 |
| 71 | `chat_workbench.py:2599:21` | E702 | Multiple statements on one line (semicolon) | S1 |
| 72 | `chat_workbench.py:2599:42` | E702 | Multiple statements on one line (semicolon) | S1 |
| 73 | `chat_workbench.py:2601:25` | E702 | Multiple statements on one line (semicolon) | S1 |
| 74 | `chat_workbench.py:2618:36` | E701 | Multiple statements on one line (colon) | S1 |
| 75 | `chat_workbench.py:2844:29` | E701 | Multiple statements on one line (colon) | S1 |
| 76 | `chat_workbench.py:2845:21` | E702 | Multiple statements on one line (semicolon) | S1 |
| 77 | `chat_workbench.py:2865:51` | E702 | Multiple statements on one line (semicolon) | S1 |
| 78 | `chat_workbench.py:2865:101` | E702 | Multiple statements on one line (semicolon) | S1 |
| 79 | `chat_workbench.py:2870:46` | E702 | Multiple statements on one line (semicolon) | S1 |
| 80 | `chat_workbench.py:2870:62` | E702 | Multiple statements on one line (semicolon) | S1 |
| 81 | `chat_workbench.py:2872:35` | E702 | Multiple statements on one line (semicolon) | S1 |
| 82 | `chat_workbench.py:2874:30` | E701 | Multiple statements on one line (colon) | S1 |
| 83 | `chat_workbench.py:2878:27` | E701 | Multiple statements on one line (colon) | S1 |
| 84 | `chat_workbench.py:2881:42` | E702 | Multiple statements on one line (semicolon) | S1 |
| 85 | `chat_workbench.py:2884:30` | E701 | Multiple statements on one line (colon) | S1 |
| 86 | `code_chat_agent.py:16:8` | F401 | `sys` imported but unused | S2 |
| 87 | `code_chat_agent.py:159:50` | E701 | Multiple statements on one line (colon) | S1 |
| 88 | `code_chat_agent.py:205:39` | E701 | Multiple statements on one line (colon) | S1 |
| 89 | `code_chat_agent.py:214:72` | E701 | Multiple statements on one line (colon) | S1 |
| 90 | `code_chat_agent.py:247:90` | E701 | Multiple statements on one line (colon) | S1 |
| 91 | `code_chat_agent.py:250:62` | E701 | Multiple statements on one line (colon) | S1 |
| 92 | `code_chat_agent.py:402:113` | E701 | Multiple statements on one line (colon) | S1 |
| 93 | `excel_agent.py:464:55` | E702 | Multiple statements on one line (semicolon) | S1 |
| 94 | `excel_agent.py:464:105` | E702 | Multiple statements on one line (semicolon) | S1 |
| 95 | `excel_agent.py:466:55` | E702 | Multiple statements on one line (semicolon) | S1 |
| 96 | `excel_agent.py:471:31` | E701 | Multiple statements on one line (colon) | S1 |
| 97 | `excel_agent.py:471:76` | E702 | Multiple statements on one line (semicolon) | S1 |
| 98 | `excel_agent.py:474:33` | E702 | Multiple statements on one line (semicolon) | S1 |
| 99 | `excel_agent.py:474:77` | E702 | Multiple statements on one line (semicolon) | S1 |
| 100 | `excel_agent.py:475:51` | E702 | Multiple statements on one line (semicolon) | S1 |
| 101 | `excel_agent.py:475:105` | E702 | Multiple statements on one line (semicolon) | S1 |
| 102 | `excel_agent.py:475:157` | E702 | Multiple statements on one line (semicolon) | S1 |
| 103 | `excel_agent.py:476:49` | E702 | Multiple statements on one line (semicolon) | S1 |
| 104 | `excel_agent.py:476:105` | E702 | Multiple statements on one line (semicolon) | S1 |
| 105 | `excel_agent.py:476:164` | E702 | Multiple statements on one line (semicolon) | S1 |
| 106 | `excel_agent.py:476:207` | E702 | Multiple statements on one line (semicolon) | S1 |
| 107 | `excel_chat_agent.py:451:20` | E702 | Multiple statements on one line (semicolon) | S1 |
| 108 | `excel_chat_agent.py:472:48` | E702 | Multiple statements on one line (semicolon) | S1 |
| 109 | `excel_chat_agent.py:472:64` | E702 | Multiple statements on one line (semicolon) | S1 |
| 110 | `excel_chat_agent.py:472:108` | E702 | Multiple statements on one line (semicolon) | S1 |
| 111 | `excel_chat_agent.py:516:60` | E701 | Multiple statements on one line (colon) | S1 |
| 112 | `excel_chat_agent.py:517:57` | E701 | Multiple statements on one line (colon) | S1 |
| 113 | `excel_chat_agent.py:518:52` | E701 | Multiple statements on one line (colon) | S1 |
| 114 | `excel_chat_agent.py:519:57` | E701 | Multiple statements on one line (colon) | S1 |
| 115 | `excel_chat_agent.py:520:54` | E701 | Multiple statements on one line (colon) | S1 |
| 116 | `excel_chat_agent.py:521:50` | E701 | Multiple statements on one line (colon) | S1 |
| 117 | `excel_chat_agent.py:522:49` | E701 | Multiple statements on one line (colon) | S1 |
| 118 | `excel_chat_agent.py:523:61` | E701 | Multiple statements on one line (colon) | S1 |
| 119 | `excel_chat_agent.py:524:33` | E701 | Multiple statements on one line (colon) | S1 |
| 120 | `excel_chat_agent.py:547:34` | E702 | Multiple statements on one line (semicolon) | S1 |
| 121 | `llm_connector_with_prompt_caching.py:168:45` | E701 | Multiple statements on one line (colon) | S1 |
| 122 | `llm_connector_with_prompt_caching.py:395:46` | E702 | Multiple statements on one line (semicolon) | S1 |
| 123 | `llm_connector_with_prompt_caching.py:417:42` | E702 | Multiple statements on one line (semicolon) | S1 |
| 124 | `llm_connector_with_prompt_caching.py:417:65` | E702 | Multiple statements on one line (semicolon) | S1 |
| 125 | `llm_connector_with_prompt_caching.py:419:51` | E701 | Multiple statements on one line (colon) | S1 |
| 126 | `llm_connector_with_prompt_caching.py:422:54` | E701 | Multiple statements on one line (colon) | S1 |
| 127 | `llm_connector_with_prompt_caching.py:424:48` | E702 | Multiple statements on one line (semicolon) | S1 |
| 128 | `llm_connector_with_prompt_caching.py:424:61` | E702 | Multiple statements on one line (semicolon) | S1 |
| 129 | `llm_connector_with_prompt_caching.py:426:43` | E702 | Multiple statements on one line (semicolon) | S1 |
| 130 | `llm_connector_with_prompt_caching.py:426:60` | E702 | Multiple statements on one line (semicolon) | S1 |
| 131 | `llm_connector_with_prompt_caching.py:435:39` | E702 | Multiple statements on one line (semicolon) | S1 |
| 132 | `llm_connector_with_prompt_caching.py:435:111` | E702 | Multiple statements on one line (semicolon) | S1 |
| 133 | `llm_connector_with_prompt_caching.py:448:38` | E702 | Multiple statements on one line (semicolon) | S1 |
| 134 | `llm_connector_with_prompt_caching.py:450:30` | E701 | Multiple statements on one line (colon) | S1 |
| 135 | `llm_connector_with_prompt_caching.py:453:28` | E702 | Multiple statements on one line (semicolon) | S1 |
| 136 | `llm_connector_with_prompt_caching.py:455:73` | E702 | Multiple statements on one line (semicolon) | S1 |
| 137 | `llm_connector_with_prompt_caching.py:495:91` | E702 | Multiple statements on one line (semicolon) | S1 |
| 138 | `llm_connector_with_prompt_caching.py:500:39` | E701 | Multiple statements on one line (colon) | S1 |
| 139 | `local_document_library.py:312:57` | E702 | Multiple statements on one line (semicolon) | S1 |
| 140 | `local_document_library.py:360:72` | E702 | Multiple statements on one line (semicolon) | S1 |
| 141 | `local_document_library.py:543:38` | E702 | Multiple statements on one line (semicolon) | S1 |
| 142 | `local_document_library.py:556:42` | E702 | Multiple statements on one line (semicolon) | S1 |
| 143 | `local_document_library.py:623:38` | E702 | Multiple statements on one line (semicolon) | S1 |
| 144 | `local_document_library.py:859:43` | E701 | Multiple statements on one line (colon) | S1 |
| 145 | `local_document_library.py:1003:37` | E702 | Multiple statements on one line (semicolon) | S1 |
| 146 | `local_document_library.py:1003:71` | E702 | Multiple statements on one line (semicolon) | S1 |
| 147 | `local_document_library.py:1016:40` | E702 | Multiple statements on one line (semicolon) | S1 |
| 148 | `release_safety.py:10:52` | E701 | Multiple statements on one line (colon) | S1 |
| 149 | `release_safety.py:11:34` | E701 | Multiple statements on one line (colon) | S1 |
| 150 | `release_safety.py:42:71` | E701 | Multiple statements on one line (colon) | S1 |
| 151 | `release_safety.py:78:18` | E701 | Multiple statements on one line (colon) | S1 |
| 152 | `tests/fixture_support.py:22:38` | E702 | Multiple statements on one line (semicolon) | S1 |
| 153 | `tests/fixture_support.py:22:81` | E702 | Multiple statements on one line (semicolon) | S1 |
| 154 | `tests/fixture_support.py:23:35` | E702 | Multiple statements on one line (semicolon) | S1 |
| 155 | `tests/fixture_support.py:23:53` | E702 | Multiple statements on one line (semicolon) | S1 |
| 156 | `tests/fixture_support.py:23:80` | E702 | Multiple statements on one line (semicolon) | S1 |
| 157 | `tests/fixture_support.py:27:28` | E702 | Multiple statements on one line (semicolon) | S1 |
| 158 | `tests/fixture_support.py:27:108` | E702 | Multiple statements on one line (semicolon) | S1 |
| 159 | `tests/fixture_support.py:27:144` | E702 | Multiple statements on one line (semicolon) | S1 |
| 160 | `tests/fixture_support.py:28:22` | E702 | Multiple statements on one line (semicolon) | S1 |
| 161 | `tests/fixture_support.py:29:37` | E702 | Multiple statements on one line (semicolon) | S1 |
| 162 | `tests/fixture_support.py:37:56` | E701 | Multiple statements on one line (colon) | S1 |
| 163 | `tests/fixture_support.py:38:56` | E701 | Multiple statements on one line (colon) | S1 |
| 164 | `tests/fixture_support.py:40:46` | E701 | Multiple statements on one line (colon) | S1 |
| 165 | `tests/fixture_support.py:41:51` | E701 | Multiple statements on one line (colon) | S1 |
| 166 | `tests/fixture_support.py:61:21` | E701 | Multiple statements on one line (colon) | S1 |
| 167 | `tests/fixture_support.py:66:54` | E702 | Multiple statements on one line (semicolon) | S1 |
| 168 | `tests/fixture_support.py:66:78` | E702 | Multiple statements on one line (semicolon) | S1 |
| 169 | `tests/fixture_support.py:66:130` | E702 | Multiple statements on one line (semicolon) | S1 |
| 170 | `tests/fixture_support.py:66:183` | E702 | Multiple statements on one line (semicolon) | S1 |
| 171 | `tests/fixture_support.py:72:83` | E702 | Multiple statements on one line (semicolon) | S1 |
| 172 | `tests/fixture_support.py:73:32` | E702 | Multiple statements on one line (semicolon) | S1 |
| 173 | `tests/fixture_support.py:73:49` | E702 | Multiple statements on one line (semicolon) | S1 |
| 174 | `tests/fixture_support.py:77:30` | E701 | Multiple statements on one line (colon) | S1 |
| 175 | `tests/fixture_support.py:81:40` | E701 | Multiple statements on one line (colon) | S1 |
| 176 | `tests/fixture_support.py:82:25` | E702 | Multiple statements on one line (semicolon) | S1 |
| 177 | `tests/fixture_support.py:82:51` | E702 | Multiple statements on one line (semicolon) | S1 |
| 178 | `tests/fixture_support.py:83:31` | E702 | Multiple statements on one line (semicolon) | S1 |
| 179 | `tests/fixture_support.py:83:58` | E702 | Multiple statements on one line (semicolon) | S1 |
| 180 | `tests/fixture_support.py:83:86` | E702 | Multiple statements on one line (semicolon) | S1 |
| 181 | `tests/test_release_e2e.py:17:66` | E702 | Multiple statements on one line (semicolon) | S1 |
| 182 | `tests/test_release_e2e.py:24:56` | E702 | Multiple statements on one line (semicolon) | S1 |
| 183 | `tests/test_release_e2e.py:34:40` | E702 | Multiple statements on one line (semicolon) | S1 |
| 184 | `tests/test_release_e2e.py:34:78` | E702 | Multiple statements on one line (semicolon) | S1 |
| 185 | `tests/test_release_e2e.py:38:72` | E702 | Multiple statements on one line (semicolon) | S1 |
| 186 | `tests/test_release_e2e.py:45:47` | E702 | Multiple statements on one line (semicolon) | S1 |
| 187 | `tests/test_release_e2e.py:54:24` | E701 | Multiple statements on one line (colon) | S1 |
| 188 | `tests/test_release_matrix.py:8:8` | F401 | `tempfile` imported but unused | S2 |
| 189 | `tests/test_release_matrix.py:9:8` | F401 | `threading` imported but unused | S2 |
| 190 | `tests/test_release_matrix.py:20:29` | F401 | `code_chat_agent.PricingCatalog` imported but unused | S2 |
| 191 | `tests/test_release_matrix.py:56:37` | E702 | Multiple statements on one line (semicolon) | S1 |
| 192 | `tests/test_release_matrix.py:115:34` | E702 | Multiple statements on one line (semicolon) | S1 |
| 193 | `tests/test_release_matrix.py:116:26` | E702 | Multiple statements on one line (semicolon) | S1 |
| 194 | `tests/test_release_matrix.py:116:79` | E702 | Multiple statements on one line (semicolon) | S1 |
| 195 | `tests/test_release_matrix.py:116:111` | E702 | Multiple statements on one line (semicolon) | S1 |
| 196 | `tests/test_release_matrix.py:117:25` | E702 | Multiple statements on one line (semicolon) | S1 |
| 197 | `tests/test_release_matrix.py:117:60` | E702 | Multiple statements on one line (semicolon) | S1 |
| 198 | `tests/test_release_matrix.py:118:26` | E702 | Multiple statements on one line (semicolon) | S1 |
| 199 | `tests/test_release_matrix.py:118:52` | E702 | Multiple statements on one line (semicolon) | S1 |
| 200 | `tests/test_release_matrix.py:118:78` | E702 | Multiple statements on one line (semicolon) | S1 |
| 201 | `tests/test_release_matrix.py:118:112` | E702 | Multiple statements on one line (semicolon) | S1 |
| 202 | `tests/test_release_matrix.py:118:146` | E702 | Multiple statements on one line (semicolon) | S1 |
| 203 | `tests/test_release_matrix.py:119:47` | E701 | Multiple statements on one line (colon) | S1 |
| 204 | `tests/test_release_matrix.py:120:38` | E701 | Multiple statements on one line (colon) | S1 |
| 205 | `tests/test_release_matrix.py:127:30` | E702 | Multiple statements on one line (semicolon) | S1 |
| 206 | `tests/test_release_matrix.py:131:24` | E702 | Multiple statements on one line (semicolon) | S1 |
| 207 | `tests/test_release_matrix.py:131:56` | E702 | Multiple statements on one line (semicolon) | S1 |
| 208 | `tests/test_release_matrix.py:133:41` | E702 | Multiple statements on one line (semicolon) | S1 |
| 209 | `tests/test_release_matrix.py:135:48` | E701 | Multiple statements on one line (colon) | S1 |
| 210 | `tests/test_release_matrix.py:138:40` | E701 | Multiple statements on one line (colon) | S1 |
| 211 | `tests/test_release_matrix.py:139:57` | E701 | Multiple statements on one line (colon) | S1 |
| 212 | `tests/test_release_matrix.py:142:35` | E702 | Multiple statements on one line (semicolon) | S1 |
| 213 | `tests/test_release_matrix.py:147:33` | E702 | Multiple statements on one line (semicolon) | S1 |
| 214 | `tests/test_release_matrix.py:147:59` | E702 | Multiple statements on one line (semicolon) | S1 |
| 215 | `tests/test_release_matrix.py:147:78` | E702 | Multiple statements on one line (semicolon) | S1 |
| 216 | `tests/test_release_matrix.py:151:48` | E701 | Multiple statements on one line (colon) | S1 |
| 217 | `tests/test_release_matrix.py:155:29` | E701 | Multiple statements on one line (colon) | S1 |
| 218 | `tests/test_release_matrix.py:159:44` | E702 | Multiple statements on one line (semicolon) | S1 |
| 219 | `tests/test_release_matrix.py:161:27` | E702 | Multiple statements on one line (semicolon) | S1 |
| 220 | `tests/test_release_matrix.py:164:39` | E702 | Multiple statements on one line (semicolon) | S1 |
| 221 | `tests/test_release_matrix.py:165:24` | E702 | Multiple statements on one line (semicolon) | S1 |
| 222 | `tests/test_release_matrix.py:165:43` | E702 | Multiple statements on one line (semicolon) | S1 |
| 223 | `tests/test_release_matrix.py:165:63` | E702 | Multiple statements on one line (semicolon) | S1 |
| 224 | `tests/test_release_matrix.py:165:81` | E702 | Multiple statements on one line (semicolon) | S1 |
| 225 | `tests/test_release_matrix.py:165:97` | E702 | Multiple statements on one line (semicolon) | S1 |
| 226 | `tests/test_release_matrix.py:165:120` | E702 | Multiple statements on one line (semicolon) | S1 |
| 227 | `tests/test_release_matrix.py:165:136` | E702 | Multiple statements on one line (semicolon) | S1 |
| 228 | `tests/test_release_matrix.py:165:154` | E702 | Multiple statements on one line (semicolon) | S1 |
| 229 | `tests/test_release_matrix.py:165:181` | E702 | Multiple statements on one line (semicolon) | S1 |
| 230 | `tests/test_release_matrix.py:165:199` | E702 | Multiple statements on one line (semicolon) | S1 |
| 231 | `tests/test_release_matrix.py:170:21` | E702 | Multiple statements on one line (semicolon) | S1 |
| 232 | `tests/test_release_matrix.py:170:49` | E702 | Multiple statements on one line (semicolon) | S1 |
| 233 | `tests/test_release_matrix.py:172:55` | E701 | Multiple statements on one line (colon) | S1 |
| 234 | `tests/test_release_matrix.py:173:69` | E702 | Multiple statements on one line (semicolon) | S1 |
| 235 | `tests/test_release_matrix.py:175:137` | E701 | Multiple statements on one line (colon) | S1 |
| 236 | `tests/test_release_matrix.py:176:42` | E702 | Multiple statements on one line (semicolon) | S1 |
| 237 | `tests/test_release_matrix.py:180:24` | E701 | Multiple statements on one line (colon) | S1 |
| 238 | `tests/test_release_regressions.py:21:43` | E702 | Multiple statements on one line (semicolon) | S1 |
| 239 | `tests/test_release_regressions.py:22:34` | E702 | Multiple statements on one line (semicolon) | S1 |
| 240 | `tests/test_release_regressions.py:22:52` | E702 | Multiple statements on one line (semicolon) | S1 |
| 241 | `tests/test_release_regressions.py:26:30` | E701 | Multiple statements on one line (colon) | S1 |
| 242 | `tests/test_release_regressions.py:30:25` | E702 | Multiple statements on one line (semicolon) | S1 |
| 243 | `tests/test_release_regressions.py:30:52` | E702 | Multiple statements on one line (semicolon) | S1 |
| 244 | `tests/test_release_regressions.py:31:40` | E701 | Multiple statements on one line (colon) | S1 |
| 245 | `tests/test_release_regressions.py:35:48` | E702 | Multiple statements on one line (semicolon) | S1 |
| 246 | `tests/test_release_regressions.py:40:34` | E702 | Multiple statements on one line (semicolon) | S1 |
| 247 | `tests/test_release_regressions.py:42:40` | E702 | Multiple statements on one line (semicolon) | S1 |
| 248 | `tests/test_release_regressions.py:43:12` | E701 | Multiple statements on one line (colon) | S1 |
| 249 | `tests/test_release_regressions.py:44:33` | E701 | Multiple statements on one line (colon) | S1 |
| 250 | `tests/test_release_regressions.py:55:34` | E702 | Multiple statements on one line (semicolon) | S1 |
| 251 | `tests/test_release_regressions.py:102:34` | E702 | Multiple statements on one line (semicolon) | S1 |
| 252 | `tests/test_release_regressions.py:115:40` | E702 | Multiple statements on one line (semicolon) | S1 |
| 253 | `tests/test_release_regressions.py:116:42` | E701 | Multiple statements on one line (colon) | S1 |
| 254 | `tests/test_release_regressions.py:119:44` | E702 | Multiple statements on one line (semicolon) | S1 |
| 255 | `tests/test_release_regressions.py:124:41` | E702 | Multiple statements on one line (semicolon) | S1 |
| 256 | `tests/test_release_regressions.py:124:60` | E702 | Multiple statements on one line (semicolon) | S1 |
| 257 | `tests/test_release_regressions.py:125:24` | E702 | Multiple statements on one line (semicolon) | S1 |
| 258 | `tests/test_release_regressions.py:132:26` | E701 | Multiple statements on one line (colon) | S1 |
| 259 | `tests/test_workbench_i18n.py:12:1` | E402 | Module level import not at top of file | S3 |
| 260 | `tests/test_workbench_reliability.py:5:8` | F401 | `os` imported but unused | S2 |

## Mypy — each remaining error

| # | Location | Code | Diagnostic | Disposition |
|---:|---|---|---|---|
| 1 | `llm_connector_with_prompt_caching.py:96` | operator | Cannot call function of unknown type | T1 |
| 2 | `llm_connector_with_prompt_caching.py:158` | assignment | Incompatible types in assignment (expression has type "dict[str, list[dict[str, Any]]]", target has type "list[dict[str, Sequence[Collection[Any]]]]") | T1 |
| 3 | `local_document_library.py:278` | valid-type | Function "local_document_library.LocalDocumentLibrary.list" is not valid as a type | T2 |
| 4 | `local_document_library.py:293` | valid-type | Function "local_document_library.LocalDocumentLibrary.list" is not valid as a type | T2 |
| 5 | `local_document_library.py:303` | attr-defined | "list?[builtins.dict[Any, Any]]" has no attribute "__iter__" (not iterable) | T2 |
| 6 | `local_document_library.py:322` | attr-defined | "list?[builtins.dict[Any, Any]]" has no attribute "__iter__" (not iterable) | T2 |
| 7 | `local_document_library.py:331` | attr-defined | "list?[builtins.dict[Any, Any]]" has no attribute "__iter__" (not iterable) | T2 |
| 8 | `local_document_library.py:343` | var-annotated | Need type annotation for "record" | T2 |
| 9 | `local_document_library.py:371` | valid-type | Function "local_document_library.LocalDocumentLibrary.list" is not valid as a type | T2 |
| 10 | `local_document_library.py:469` | valid-type | Function "local_document_library.LocalDocumentLibrary.list" is not valid as a type | T2 |
| 11 | `local_document_library.py:472` | attr-defined | "list?[builtins.dict[Any, Any]]" has no attribute "__iter__" (not iterable) | T2 |
| 12 | `local_document_library.py:480` | valid-type | Function "local_document_library.LocalDocumentLibrary.list" is not valid as a type | T2 |
| 13 | `local_document_library.py:486` | attr-defined | "list?[builtins.dict[Any, Any]]" has no attribute "__iter__" (not iterable) | T2 |
| 14 | `local_document_library.py:497` | var-annotated | Need type annotation for "segment" | T2 |
| 15 | `local_document_library.py:595` | var-annotated | Need type annotation for "paths" (hint: "paths: list[<type>] = ...") | T2 |
| 16 | `local_document_library.py:676` | var-annotated | Need type annotation for "groups" (hint: "groups: dict[<type>, <type>] = ...") | T2 |
| 17 | `local_document_library.py:691` | attr-defined | "list?[pathlib.Path]" has no attribute "__iter__" (not iterable) | T2 |
| 18 | `local_document_library.py:707` | assignment | Incompatible types in assignment (expression has type "tuple[Any \| None, str, Any \| None, Any \| None, Any \| None]", variable has type "str") | T3 |
| 19 | `local_document_library.py:733` | valid-type | Function "local_document_library.LocalDocumentLibrary.list" is not valid as a type | T2 |
| 20 | `local_document_library.py:815` | valid-type | Function "local_document_library.LocalDocumentLibrary.list" is not valid as a type | T2 |
| 21 | `local_document_library.py:819` | var-annotated | Need type annotation for "item" | T2 |
| 22 | `local_document_library.py:822` | valid-type | Function "local_document_library.LocalDocumentLibrary.list" is not valid as a type | T2 |
| 23 | `local_document_library.py:824` | attr-defined | "list?[pathlib.Path]" has no attribute "__iter__" (not iterable) | T2 |
| 24 | `local_document_library.py:834` | var-annotated | Need type annotation for "source" | T2 |
| 25 | `local_document_library.py:870` | var-annotated | Need type annotation for "chunks" (hint: "chunks: list[<type>] = ...") | T2 |
| 26 | `excel_agent.py:371` | return-value | Incompatible return value type (got "list[str]", expected "tuple[str, str]") | T5 |
| 27 | `excel_chat_agent.py:108` | assignment | Incompatible types in assignment (expression has type "str", variable has type "None") | T6 |
| 28 | `excel_chat_agent.py:515` | arg-type | Argument 1 to "get" of "dict" has incompatible type "Any \| None"; expected "str" | T6 |
| 29 | `code_chat_agent.py:152` | var-annotated | Need type annotation for "entries" (hint: "entries: list[<type>] = ...") | T4 |
| 30 | `code_chat_agent.py:251` | attr-defined | "object" has no attribute "items" | T4 |
| 31 | `code_chat_agent.py:544` | attr-defined | "object" has no attribute "append" | T4 |
| 32 | `code_chat_agent.py:562` | operator | Unsupported operand types for > ("int" and "object") | T4 |
| 33 | `code_chat_agent.py:563` | index | Invalid index type "object" for "str"; expected type "SupportsIndex \| slice[Any, Any, Any]" | T4 |
| 34 | `code_chat_agent.py:564` | operator | Unsupported operand types for + ("object" and "int") | T4 |
| 35 | `code_chat_agent.py:566` | operator | Unsupported left operand type for + ("object") | T4 |
| 36 | `code_chat_agent.py:567` | arg-type | Argument 1 to "len" has incompatible type "object"; expected "Sized" | T4 |
| 37 | `code_chat_agent.py:569` | call-overload | No overload variant of "int" matches argument types "object", "int" | T4 |
| 38 | `code_chat_agent.py:571` | operator | Unsupported operand types for + ("str" and "object") | T4 |
| 39 | `code_chat_agent.py:780` | var-annotated | Need type annotation for "pending" (hint: "pending: list[<type>] = ...") | T4 |
| 40 | `chat_workbench.py:672` | misc | List comprehension has incompatible type List[int]; expected List[str] | T7 |
| 41 | `chat_workbench.py:693` | misc | List comprehension has incompatible type List[int]; expected List[str] | T7 |
| 42 | `chat_workbench.py:694` | dict-item | Dict entry 3 has incompatible type "str": "Any \| None"; expected "str": "Sequence[str]" | T7 |
| 43 | `chat_workbench.py:1367` | arg-type | Argument 1 to "append" of "list" has incompatible type "tuple[int, float, list[int], str, str]"; expected "tuple[int, int, list[int], str, str]" | T8 |
| 44 | `chat_workbench.py:1378` | arg-type | Argument 1 to "append" of "list" has incompatible type "tuple[int, float, list[int], str, str]"; expected "tuple[int, int, list[int], str, str]" | T8 |

This snapshot is diagnostic documentation only. Keep both commands active for step 9 and future changes.
