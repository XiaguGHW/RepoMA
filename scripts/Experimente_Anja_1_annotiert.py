# main_excel_processor.py

import pandas as pd
import os
import logging
from tqdm import tqdm
import datetime
from dotenv import load_dotenv
from Google_native_connector_multiplefiles_1 import BoschLLMConnector

# 学习注释：从 .env / 系统环境变量读取 API key，不把 key 写进源码。
load_dotenv()

# --- Logging-Konfiguration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("verarbeitung.log", mode='w'),
        logging.StreamHandler()
    ]
)

# ============================================================================
# === KONFIGURATION (mit Ihren bereitgestellten Pfaden) ===
# ============================================================================
EXCEL_VORLAGE_PFAD = r"C:\Users\NUL4FE\OneDrive - Bosch Group\ENG Academy - Training-Baugruppenontologie und Generative KI (MA) - Private\MA_Funktionsmodellierung\Experimente\Handhabung\Experimente_template_V6_ges.xlsx"
BAUGRUPPEN_SPALTE = "Baugruppennummer"
DOKUMENTE_BASIS_PFAD = r"C:\Users\NUL4FE\OneDrive - Bosch Group\ENG Academy - Training-Baugruppenontologie und Generative KI (MA) - Private\MA_Funktionsmodellierung\Experimente\Handhabung\Datenset"

timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
OUTPUT_EXCEL_PFAD = rf"C:\Users\NUL4FE\OneDrive - Bosch Group\ENG Academy - Training-Baugruppenontologie und Generative KI (MA) - Private\MA_Funktionsmodellierung\Experimente\Handhabung\Ergebnis_Auswertung_{timestamp}.xlsx"

# LLM Konfiguration
BOSCH_FARM_API_KEY = os.getenv("BOSCH_FARM_SUBSCRIPTION_KEY")
MODEL_NAME = "gemini-2.5-pro"

# 学习注释：这段是给每次 Gemini 请求共用的全局规则。
# === HIER DEN SYSTEM-PROMPT FÜR DIE GESAMTE AUSWERTUNG DEFINIEREN ===
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
    *   **Beispiel für die Anfrage zu den Positionierungen des Greifers:**
        (Interpretation) Der Greifer kann einstufig (also nur 2 Positionen: offen/geschlossen) annehmen. Dies
wird abgeleitet, da der Greifer über einen einfachen pneumatischen Zylinder ohne
Zwischenpositionierung angetrieben wird.

3.  **Fehlende Informationen:** Wenn eine Information weder direkt in den Dokumenten enthalten ist, noch
logisch abgeleitet werden kann, antworte ausschließlich mit dem Text: 'Information nicht gefunden.'

4.  **Nicht relevante Fragen:** Einige Fragen enthalten Bedingungen, die sich auf deine vorherigen Antworten
beziehen (z.B. "wenn das Ergebnis des Kriteriums mit der ID K1 genau 3 ist"). Halte dich strikt an diese
Bedingungen.
Wenn eine Bedingung nicht erfüllt ist oder die Information nicht gefunden werden kann, antworte
ausschließlich mit 'Nicht relevant'
"""

# ============================================================================
# Dokumentation: https://cloud.google.com/vertex-ai/docs/generative-ai/model-reference/gemini
GENERATION_CONFIG = {
    # Steuert die Zufälligkeit der Antwort. Werte zwischen 0.0 und 1.0.
    # Für Faktenextraktion sind niedrige Werte (z.B. 0.1 - 0.3) am besten. --> Default 1.0
    "temperature": 0.1,

    # Wählt aus den Tokens, deren kumulative Wahrscheinlichkeit über diesem Wert liegt.
    # Ein hoher Wert (z.B. 0.95) erlaubt mehr Vielfalt. --> Default 0.95
    "topP": 0.95,

    # Wie viele alternative Antworten sollen generiert werden? (Fast immer 1) --> Default= 1
    "candidateCount": 1,

    # Maximale Anzahl an Tokens in der generierten Antwort. Wichtig zur Kostenkontrolle.
    "maxOutputTokens": 1000000,

    # Eine Liste von Zeichenketten. Wenn das Modell eine dieser Sequenzen generiert, stoppt es.
    # Beispiel: "stopSequences": ["\n\n", "###"]
    "stopSequences": []
}

# 学习注释：根据 BG 编号，在数据集目录中递归收集可发送给 Gemini 的文件。
def finde_dateien_fuer_baugruppe(baugruppennummer: str, basis_pfad: str) -> list:
    # ... (Diese Funktion bleibt unverändert) ...
    baugruppen_ordner_pfad = os.path.join(basis_pfad, str(baugruppennummer))
    if not os.path.isdir(baugruppen_ordner_pfad):
        logging.warning(f"Ordner für '{baugruppennummer}' nicht gefunden: {baugruppen_ordner_pfad}")
        return []
    gefundene_dateien = []
    supported_extensions = ('.pdf', '.png', '.jpg', '.jpeg')
    for verzeichnis_pfad, _, dateinamen in os.walk(baugruppen_ordner_pfad):
        for datei in dateinamen:
            if datei.lower().endswith(supported_extensions):
                gefundene_dateien.append(os.path.join(verzeichnis_pfad, datei))
    logging.info(f"{len(gefundene_dateien)} unterstützte Dateien für '{baugruppennummer}' gefunden.")
    return gefundene_dateien

# 学习注释：主流程——按 Excel 的每一行 BG 和每一个问题列循环调用 Gemini。
def verarbeite_excel_vorlage(llm: BoschLLMConnector):
    # ... (Der Anfang dieser Funktion bis zur Schleife bleibt unverändert) ...
    try:
        df = pd.read_excel(EXCEL_VORLAGE_PFAD)
        logging.info(f"Excel-Vorlage '{os.path.basename(EXCEL_VORLAGE_PFAD)}' geladen. {len(df)} Zeilen zu verarbeiten.")
    except FileNotFoundError:
        logging.error(f"FEHLER: Excel-Vorlage nicht gefunden: {EXCEL_VORLAGE_PFAD}")
        return
    except KeyError as e:
        logging.error(f"FEHLER: Spalte '{e}' wurde in der Excel-Datei nicht gefunden. Bitte prüfen Sie die Variable 'BAUGRUPPEN_SPALTE'.")
        return
    except Exception as e:
        logging.error(f"FEHLER beim Lesen der Excel-Datei: {e}")
        return

    frage_spalten = [col for col in df.columns if col != BAUGRUPPEN_SPALTE]
    logging.info(f"Fragespalten: {', '.join(frage_spalten)}")

    for index, zeile in tqdm(df.iterrows(), total=df.shape[0], desc="Verarbeite Baugruppen"):
        baugruppennummer = zeile[BAUGRUPPEN_SPALTE]
        if pd.isna(baugruppennummer):
            logging.warning(f"Zeile {index+2} übersprungen, da keine Baugruppennummer vorhanden ist.")
            continue

        logging.info(f"\n--- Starte Baugruppe: {baugruppennummer} ---")
        dateipfade = finde_dateien_fuer_baugruppe(baugruppennummer, DOKUMENTE_BASIS_PFAD)

        if not dateipfade:
            for frage in frage_spalten:
                df.loc[index, frage] = "FEHLER: Keine Dokumente gefunden."
            continue

        for frage_text in frage_spalten:
            if pd.notna(zeile[frage_text]) and str(zeile[frage_text]).strip() != "":
                logging.info(f"Spalte '{frage_text}' enthält bereits Daten, wird übersprungen.")
                continue

            logging.info(f"Stelle Frage aus Überschrift: '{frage_text}'")

            # === HIER WIRD DER SYSTEM-PROMPT AN DEN CONNECTOR ÜBERGEBEN ===
            antwort = llm.ask_about_files(
                file_paths=dateipfade,
                question=frage_text,
                system_prompt=SYSTEM_PROMPT  # Übergabe des globalen Prompts
            )
            df.loc[index, frage_text] = antwort

    # ... (Speichern am Ende bleibt unverändert) ...
    try:
        logging.info(f"Speichere Ergebnisse in neuer Datei: {OUTPUT_EXCEL_PFAD}")
        df.to_excel(OUTPUT_EXCEL_PFAD, index=False, engine='openpyxl')
        logging.info("\nVerarbeitung abgeschlossen. Ergebnisdatei wurde erfolgreich erstellt.")
    except Exception as e:
        logging.error(f"FEHLER beim Speichern der Ergebnisdatei: {e}")

if __name__ == "__main__":
    llm = BoschLLMConnector(model_name=MODEL_NAME, api_key=BOSCH_FARM_API_KEY)
    verarbeite_excel_vorlage(llm)
