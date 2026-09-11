# Arbeitsstand – LLM-Experimente zur Baugruppenklassifikation

**Stand: 11.09.2026**

## Abgeschlossen

### 1. Label-Konfigurationstest

Für die 14 Baugruppen aus dem Prompt Engineering wurden vier Label- und Ausgabekonfigurationen mit Gemini 2.5 Pro, Temperature = 0 und dem unveränderten P3-Original-Codebook getestet.

| Konfiguration | Kurzbeschreibung | Zentrales Ergebnis |
|---|---|---|
| L1 | Nur eine Funktionsklasse ausgeben | **Ausgewählt** |
| L2 | Zusätzlich Mehrdeutigkeit und Alternativlabel ausgeben | Kein erkennbarer Mehrwert; schlechtere E1/E2-Ergebnisse |
| L3 | Wie L2, zusätzlich „nicht entscheidbar“ | Kein zusätzlicher Nutzen gegenüber L1 |
| L4 | Wie L3, aber Gantry und kombinierte Einheit zusammenfassen | Kein Vorteil durch die Zusammenlegung |

**Kompakte Ergebnisübersicht**

| Kennzahl | L1 | L2 | L3 | L4 |
|---|---:|---:|---:|---:|
| Strikte Accuracy gesamt | **78,6 %** | 71,4 % | **78,6 %** | 71,4 % |
| Strikte Accuracy E1/E2 | **90,9 %** | 72,7 % | **90,9 %** | **90,9 %** |
| M Accepted-Set-Accuracy | **100 %** | **100 %** | **100 %** | 66,7 % |
| Joint Decision Accuracy | **71,4 %** | 57,1 % | **71,4 %** | 64,3 % |

**Entscheidung:** Für die folgenden Experimente wird **L1** verwendet. Gantry und kombinierte Einheit bleiben getrennte Klassen.

Kurz zur Interpretation der Kennzahlen:

- *Strikte Accuracy*: Vorhersage stimmt mit dem primären Ground-Truth-Label überein.
- *M Accepted-Set-Accuracy*: Bei mehrdeutigen Fällen werden sowohl das primäre als auch das dokumentierte zulässige Alternativlabel akzeptiert.
- *Joint Decision Accuracy*: Bewertet zusätzlich, ob Eindeutigkeit bzw. Mehrdeutigkeit passend behandelt wurde.

### 2. Prompt Engineering

Die Prompt-Konfigurationen **P1**, **P2** und **P3** wurden iterativ entwickelt und getestet. Anschließend wurde eine optimierte P3-Version erstellt.

### 3. Wiederholbarkeitstest mit Gemini

Der PDF-basierte Wiederholbarkeitstest mit **Gemini 2.5 Pro** und der optimierten P3-Version wurde abgeschlossen:

- 10 vollständige Durchläufe
- jeweils 115 Baugruppen
- identische Randbedingungen pro Durchlauf

Die vorläufigen Accuracy-Werte liegen stabil im Bereich von etwa **80–90 %**.

### 4. PDF-basierter Multi-Model-Test

Der PDF-basierte Vergleich mehrerer Modelle und Konfigurationen wurde durchgeführt:

- 16 vollständige Durchläufe
- jeweils 115 Baugruppen
- gleiche PDF-Datenbasis und festgelegte Label-Konfiguration L1

## Noch offen

- Vollständige automatisierte Auswertung und Zusammenfassung der 10 Wiederholungsdurchläufe.
- Vollständige Auswertung und Vergleich der 16 Multi-Model-Durchläufe.
- Vergleich der Modelle und Prompt-Konfigurationen anhand von Accuracy, klassenweisen Kennzahlen, Confusion Matrices und regime-spezifischen Ergebnissen.
- Ableitung der finalen Empfehlung für Modell und Prompt-Konfiguration.
