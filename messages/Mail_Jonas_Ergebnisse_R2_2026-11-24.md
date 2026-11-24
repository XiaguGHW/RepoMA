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

Hinweis zur Interpretation:
Unter R2 liegt die Accuracy auf den mehrdeutigen Baugruppen bei den meisten Modellen höher als auf den eindeutigen (z. B. Gemini Pro 99,7 % ggü. 95,2 %). Gründe aus meiner Sicht:

1. Entstehung von R2: R2 wurde nach dem LLM-Review überarbeitet. Plausible LLM-Vorhersagen wurden dabei als weitere zulässige Labels aufgenommen. Die Modelle werden auf den mehrdeutigen Baugruppen also teilweise an Labels gemessen, die aus ihren eigenen Vorhersagen stammen.
2. Mehrere korrekte Labels: Bei mehrdeutigen Baugruppen gelten mehrere Labels als richtig, ein Treffer ist dadurch leichter.
3. Kleine Teilmenge: Mit 30–31 Baugruppen entspricht eine Baugruppe ca. 3 Prozentpunkten; die Konfidenzintervalle sind entsprechend breit.

Fazit: R1 begünstigt eher die menschliche Annotation, R2 eher die LLMs. Für den Vergleich mit der Human Annotation ist R2 sinnvoll, die hohen Werte der LLMs auf den mehrdeutigen Baugruppen sollte man aber vorsichtig interpretieren.

Viele Grüße
Duanni
