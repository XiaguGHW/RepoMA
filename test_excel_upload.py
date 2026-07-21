from pathlib import Path

from openpyxl import Workbook

from Google_native_connector_multiplefiles_1 import BoschLLMConnector


# === KONFIGURATION ===
INPUT_ORDNER = Path("input")
TEST_DATEI = INPUT_ORDNER / "excel_upload_test.xlsx"
TESTWERT = "EXCEL_TEST_7F3K9"

BOSCH_FARM_API_KEY = "HIER_API_KEY_EINTRAGEN"
MODEL_NAME = "gemini-2.5-pro"

GENERATION_CONFIG = {
    "temperature": 0.1,
    "topP": 0.95,
    "candidateCount": 1,
    "maxOutputTokens": 100,
    "stopSequences": []
}


def erstelle_testdatei():
    INPUT_ORDNER.mkdir(exist_ok=True)

    workbook = Workbook()
    worksheet = workbook.active
    worksheet["A1"] = TESTWERT
    workbook.save(TEST_DATEI)


if __name__ == "__main__":
    erstelle_testdatei()
    print("Testdatei erstellt:", TEST_DATEI)

    llm = BoschLLMConnector(
        model_name=MODEL_NAME,
        api_key=BOSCH_FARM_API_KEY
    )

    try:
        antwort = llm.ask_about_files(
            file_paths=[str(TEST_DATEI.resolve())],
            question=(
                "Lies die hochgeladene Excel-Datei. "
                "Antworte ausschliesslich mit dem Inhalt der Zelle A1."
            ),
            generation_config=GENERATION_CONFIG
        )

        antwort = str(antwort).strip()
        print("Gemini-Antwort:", antwort)

        if antwort == TESTWERT:
            print("TEST ERFOLGREICH: Gemini kann den Inhalt der Excel-Datei lesen.")
        else:
            print("TEST NICHT ERFOLGREICH: Der Inhalt aus A1 wurde nicht korrekt erkannt.")

    except Exception as e:
        print("TEST FEHLGESCHLAGEN:", e)
