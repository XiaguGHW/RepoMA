# zero_shot_classification.py
import pandas as pd
import os
import logging
from tqdm import tqdm
import datetime
from Google_native_connector_multiplefiles_1 import BoschLLMConnector


# --- Logging-Konfiguration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("verarbeitung.log", mode='w'),
        logging.StreamHandler()
    ]
)

# === KONFIGURATION ===
# ================================================================================

ASSEMBLY_LABEL_PFAD = "Assembly_label.xlsx"
FUNCTIONAL_CLASSES_PFAD = "Functional_classes.xlsx"
OUTPUT_EXCEL_PFAD = "Classification_result.xlsx"

BAUGRUPPENNAME_SPALTE = "Baugruppenname"
TRUE_LABEL_SPALTE = "Label_Full"
FUNKTIONSKLASSE_SPALTE = "Funktionsklasse"

BOSCH_FARM_API_KEY = "HIER_API_KEY_EINTRAGEN"
MODEL_NAME = "gemini-2.5-pro"

GENERATION_CONFIG = {
    "temperature": 0.1,
    "topP": 0.95,
    "candidateCount": 1,
    "maxOutputTokens": 1000,
    "stopSequences": []
}


def lade_daten():
    assembly_df = pd.read_excel(ASSEMBLY_LABEL_PFAD)
    classes_df = pd.read_excel(FUNCTIONAL_CLASSES_PFAD)

    logging.info(f"Assembly-Datei geladen: {len(assembly_df)} Zeilen")
    logging.info(f"Functional-Classes-Datei geladen: {len(classes_df)} Zeilen")

    logging.info(f"Spalten in Assembly-Datei: {list(assembly_df.columns)}")
    logging.info(f"Spalten in Functional-Classes-Datei: {list(classes_df.columns)}")

    klassen_liste = (
        classes_df[FUNKTIONSKLASSE_SPALTE]
        .dropna()
        .astype(str)
        .str.strip()
        .tolist()
    )

    logging.info(f"{len(klassen_liste)} Funktionsklassen geladen")
    return assembly_df, klassen_liste


def baue_prompt(baugruppenname, klassen_liste):
    klassen_text = "\n".join(f"- {klasse}" for klasse in klassen_liste)

    prompt = f"""
Du bist ein technischer Experte für Baugruppenklassifikation im Maschinen- und Anlagenbau.

Klassifiziere den folgenden Baugruppennamen in genau eine der vorgegebenen Funktionsklassen.

Baugruppenname:
{baugruppenname}

Zulässige Funktionsklassen:
{klassen_text}

Regeln:
- Wähle genau eine Funktionsklasse aus der Liste.
- Antworte ausschließlich mit dem exakten Namen der Funktionsklasse, nie mit einer Abkürzung.
- Keine Erklärung, keine zusätzlichen Wörter.
- Wenn keine Klasse eindeutig passt, wähle "Nicht klassifizierbar".

Antwort:
"""
    return prompt


if __name__ == "__main__":
    baugruppen_tabelle, funktionsklassen = lade_daten()

    llm = BoschLLMConnector(
        model_name=MODEL_NAME,
        api_key=BOSCH_FARM_API_KEY
    )

    vorhersagen = []

    for index, zeile in baugruppen_tabelle.iterrows():
        baugruppenname = zeile[BAUGRUPPENNAME_SPALTE]

        if pd.isna(baugruppenname) or str(baugruppenname).strip() == "":
            antwort = "FEHLER: Kein Baugruppenname"
            vorhersagen.append(antwort)
            continue

        prompt = baue_prompt(baugruppenname, funktionsklassen)

        try:
            antwort = llm.ask_about_files(
                file_paths=[],
                question=prompt,
                generation_config=GENERATION_CONFIG
            )

            antwort = str(antwort).strip()

        except Exception as e:
            antwort = f"FEHLER: {e}"

        print(f"{index + 1}/{len(baugruppen_tabelle)}")
        print("Baugruppenname:", baugruppenname)
        print("LLM-Antwort:", antwort)
        print("True Label:", zeile[TRUE_LABEL_SPALTE])
        print("-" * 40)

        vorhersagen.append(antwort)

    baugruppen_tabelle["LLM_Label"] = vorhersagen

    baugruppen_tabelle["Korrekt"] = (
        baugruppen_tabelle["LLM_Label"] == baugruppen_tabelle[TRUE_LABEL_SPALTE]
    )

    confusion_matrix = pd.crosstab(
        baugruppen_tabelle[TRUE_LABEL_SPALTE],
        baugruppen_tabelle["LLM_Label"],
        rownames=["True Label"],
        colnames=["LLM Prediction"],
        dropna=False
    )

    accuracy = baugruppen_tabelle["Korrekt"].mean()
    print(f"Accuracy: {accuracy:.2%}")

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    output_pfad = f"Baugruppenlabel_Ergebnis_{timestamp}.xlsx"

    with pd.ExcelWriter(output_pfad, engine="openpyxl") as writer:
        baugruppen_tabelle.to_excel(writer, sheet_name="Ergebnisse", index=False)
        confusion_matrix.to_excel(writer, sheet_name="Confusion_Matrix")

    print("Fertig. Ergebnis gespeichert in:", output_pfad)
