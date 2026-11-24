# Mail an Jonas – Ergebnisse unter R2 (2026-11-24)

**Betreff:** Ergebnisse unter R2

**Anhänge:** Wiederhollaeufe_R2.xlsx, Ergebnisse_unter_R2.xlsx, Diagramme_Wiederholung_R2.xlsx, R2.md

---

Hallo Jonas,

anbei wie besprochen dieselben Ergebnisse auf Basis von R2:

1. Wiederhollaeufe_R2.xlsx – Wiederholungsläufe (115 und 185 BG, je 10 Läufe)
2. Ergebnisse_unter_R2.xlsx – Ergebnistabelle (P1–P4 / pdf, Bild, text / eindeutig, mehrdeutig, gesamt)
3. Diagramme_Wiederholung_R2.xlsx – Mittelwert und Streuung über die 10 Läufe
4. R2.md – die verwendete Ground Truth

Das Vorgehen ist identisch zu R1, nur die Ground Truth ist ausgetauscht. Unter R2 sind von den 185 ausgewerteten Baugruppen 154 eindeutig und 31 mehrdeutig (115 BG: 85 / 30).

Ein Hinweis zur Interpretation: Unter R2 liegt die Accuracy auf den mehrdeutigen Baugruppen bei den meisten Modellen höher als auf den eindeutigen (z. B. Gemini Pro 99,7 % ggü. 95,2 %). Das ist meiner Einschätzung nach zum Teil durch die Entstehung von R2 bedingt: R2 wurde nach dem LLM-Review überarbeitet, und plausible LLM-Vorhersagen wurden dabei als weitere zulässige Labels aufgenommen. Die Modelle werden auf den mehrdeutigen Baugruppen also teilweise an Labels gemessen, die aus ihren eigenen Vorhersagen stammen. Hinzu kommt, dass bei mehrdeutigen Baugruppen mehrere Labels als korrekt gelten und die Teilmenge mit 30–31 Baugruppen klein ist (eine Baugruppe entspricht ca. 3 Prozentpunkten, entsprechend breit sind die Konfidenzintervalle).

Das ist quasi das Gegenstück zu deinem Punkt zu R1: R1 begünstigt eher die menschliche Annotation, R2 eher die LLMs. Für den Vergleich mit der Human Annotation ist R2 daher sinnvoll, die hohen Werte der LLMs auf den mehrdeutigen Baugruppen sollte man aber vorsichtig interpretieren.

Viele Grüße
Duanni
