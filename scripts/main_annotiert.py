# main.py 的学习注释版（依据你发送的完整截图整理）。
# 原有执行逻辑与顺序保留；仅新增少量中文 # 注释。

import sys
import os
import logging
from datetime import datetime

import pandas as pd
from dotenv import load_dotenv
from tqdm import tqdm

from llm_connector import LLMConnector


# 从 .env / 系统环境变量中读取 API key，不在源码中保存密钥。
load_dotenv()


# ============================================================================
# CONFIGURATION
# ============================================================================
MODEL_NAME = "claude-opus-4-8"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EXCEL_TEMPLATE_PATH = os.path.join(BASE_DIR, "Exp_template_test.xlsx")
ASSEMBLY_DATA_PATH = os.path.join(BASE_DIR, "DataTest_Lifter")
ASSEMBLY_ID_COLUMN = "Baugruppennummer"

API_KEY = os.getenv("BOSCH_FARM_SUBSCRIPTION_KEY")


# 学习注释：这一段是每次模型调用都共同遵守的技术资料阅读与回答规则。
SYSTEM_PROMPT = """Du bist ein Fachexperte für technische Produktdokumentation und Konstruktion bei Bosch.
Deine Aufgabe ist es, spezifische Fragen zu Baugruppen präzise und auf Basis der zur Verfügung gestellten
Dokumente zu beantworten.

Beachte bei der Analyse der folgenden Quellen deren spezifische Eigenschaften:

*   **Strukturstückliste (PDF):**
    *   Dies ist deine zentrale und primäre Informationsquelle für den Aufbau der Baugruppe.
    *   Sie listet alle Einzelteile und Unterbaugruppen in tabellarischer Form auf.
    *   Die hierarchische Struktur wird durch die Spalte "Ebene" definiert. Anhand des Werts in dieser Spalte
kannst du erkennen, zu welcher Unterbaugruppe ein Bauteil gehört. Nutze diese Spalte, um die
Baugruppenstruktur korrekt zu interpretieren.
*   **Technische Zeichnung (falls vorhanden):**
    *   Enthält maßgebliche geometrische Informationen, Toleranzen, Oberflächenangaben und oft eine
Positionsstückliste, die sich auf die Hauptbaugruppe bezieht.
*   **Herstellerkataloge / Datenblätter (falls vorhanden):**
    *   Enthalten die Spezifikationen von Kaufteilen. Achte besonders auf visuelle Markierungen (z.B. farbige
Kästen, Pfeile, Einkreisungen). Diese heben in der Regel die exakte, in der Baugruppe verbaute Variante
hervor.
*   **Screenshot des CAD-Modells (falls vorhanden):**
    *   Bietet einen visuellen Kontext der gesamten Baugruppe und ihrer Komponenten.
    *   Achte auf die räumliche Anordnung der Bauteile und die allgemeine Konstruktionsweise (z.B. Art der
Achsführung, Art des Greifers).
    *   Kann zur Plausibilitätsprüfung von Informationen aus anderen Quellen oder zur Ableitung von Dimensionen
(z.B. geschätzter Bauraum, falls keine exakten Maße vorliegen) dienen.

Verhalte dich bei deinen Antworten wie folgt:

1.  **Direkte Informationen:** Antworte kurz, prägnant und sachlich in deutscher Sprache. Gib nur die
angefragte Information aus, ohne einleitende Sätze. Füge hinter jede direkte Information in Klammern die
Quelle an (z.B. (Strukturstückliste, Pos. 25), (Zeichnung 123), (Datenblatt XYZ)).

2.  **Interpretierte Informationen:** Wenn eine Information nicht explizit dokumentiert ist, du sie aber aus
den vorhandenen Bauteilen und deren Eigenschaften logisch ableiten kannst, dann stelle diese als
Interpretation dar. Kennzeichne solche abgeleiteten Informationen eindeutig, indem du ihnen den Zusatz
(Interpretation) voranstellst und deine Schlussfolgerung kurz begründest.

3.  **Fehlende Informationen:** Wenn eine Information weder direkt in den Dokumenten enthalten ist, noch
logisch abgeleitet werden kann, antworte ausschließlich mit dem Text: 'Information nicht gefunden.'

4.  **Nicht relevante Fragen:** Einige Fragen enthalten Bedingungen, die sich auf deine vorherigen Antworten
beziehen. Halte dich strikt an diese Bedingungen. Wenn eine Bedingung nicht erfüllt ist oder die Information
nicht gefunden werden kann, antworte ausschließlich mit 'Nicht relevant'.
"""


GENERATION_CONFIG = {
    "temperature": 0.0,
    "topP": 0.95,
    "candidateCount": 1,
    "maxOutputTokens": 65536,
    "stopSequences": [],
}


# 学习注释：按 BG 编号找到同名文件夹，并递归收集可发送的 PDF/图片。
def find_files_for_assembly(assembly_id: str, base_path: str) -> list:
    assembly_folder = os.path.join(base_path, str(assembly_id))

    if not os.path.isdir(assembly_folder):
        logging.warning("Assembly folder not found: %s", assembly_folder)
        return []

    files = []
    supported_extensions = (".pdf", ".png", ".jpg", ".jpeg")

    for root, _, filenames in os.walk(assembly_folder):
        for filename in filenames:
            if filename.lower().endswith(supported_extensions):
                files.append(os.path.join(root, filename))

    logging.info("Found %d supported file(s) for assembly '%s'.", len(files), assembly_id)
    return files


# 学习注释：主循环——每一行是一个 BG；除编号列以外，每个列标题都是要问模型的问题。
def run_pipeline(llm: LLMConnector, output_path: str):
    try:
        df = pd.read_excel(EXCEL_TEMPLATE_PATH)
        logging.info("Excel template loaded: %s", EXCEL_TEMPLATE_PATH)
    except FileNotFoundError:
        logging.error("Excel template not found: %s", EXCEL_TEMPLATE_PATH)
        return
    except Exception as error:
        logging.error("Could not read Excel template: %s", error)
        return

    if ASSEMBLY_ID_COLUMN not in df.columns:
        logging.error("Required column '%s' is missing.", ASSEMBLY_ID_COLUMN)
        return

    prompt_columns = [column for column in df.columns if column != ASSEMBLY_ID_COLUMN]
    logging.info("Prompt columns: %s", ", ".join(prompt_columns))

    for index, row in tqdm(df.iterrows(), total=df.shape[0], desc="Processing assemblies"):
        assembly_id = row[ASSEMBLY_ID_COLUMN]

        if pd.isna(assembly_id):
            logging.warning("Skipping row %d because no assembly ID is available.", index + 2)
            continue

        logging.info("Processing assembly: %s", assembly_id)
        files = find_files_for_assembly(assembly_id, ASSEMBLY_DATA_PATH)

        if not files:
            for prompt_column in prompt_columns:
                df.loc[index, prompt_column] = "ERROR: No documents found."
            continue

        for prompt_column in prompt_columns:
            if pd.notna(row[prompt_column]) and str(row[prompt_column]).strip() != "":
                logging.info("Skipping '%s' because it already contains data.", prompt_column)
                continue

            prompt = prompt_column
            logging.info("Asking question: %s", prompt)

            try:
                response = llm.ask_about_files(
                    file_paths=files,
                    question=prompt,
                    system_prompt=SYSTEM_PROMPT,
                    generation_config=GENERATION_CONFIG,
                )
                df.loc[index, prompt_column] = response
            except Exception as error:
                logging.error("Error while processing '%s': %s", assembly_id, error)
                df.loc[index, prompt_column] = f"ERROR: {error}"

    try:
        df.to_excel(output_path, index=False, engine="openpyxl")
        logging.info("Pipeline finished. Results saved to: %s", output_path)
    except Exception as error:
        logging.error("Could not save the result file: %s", error)


if __name__ == "__main__":
    active_model = sys.argv[1] if len(sys.argv) > 1 else MODEL_NAME
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    active_output = os.path.join(BASE_DIR, f"Ergebnis_{active_model}_{timestamp}.xlsx")
    log_file = os.path.join(BASE_DIR, f"pipeline_{active_model}_{timestamp}.log")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        handlers=[logging.FileHandler(log_file), logging.StreamHandler()],
        force=True,
    )

    if not API_KEY:
        logging.error("BOSCH_FARM_SUBSCRIPTION_KEY is not set.")
        sys.exit(1)

    if not os.path.isfile(EXCEL_TEMPLATE_PATH):
        logging.error("Excel template not found: %s", EXCEL_TEMPLATE_PATH)
        sys.exit(1)

    llm = LLMConnector(model_name=active_model, api_key=API_KEY)
    run_pipeline(llm, active_output)

