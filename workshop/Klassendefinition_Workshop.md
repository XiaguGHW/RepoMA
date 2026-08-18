# Workshop: Klassendefinition der sechs Funktionsklassen

## Ziel des Workshops

Ziel dieses Workshops ist es, die Verständlichkeit und Trennschärfe des vorgeschlagenen Klassenschemas für Baugruppen zu überprüfen. Dafür sollen ausgewählte Baugruppen anhand ihrer dominierenden Hauptfunktion einer von sechs Funktionsklassen zugeordnet werden.

Bitte bewerten Sie die übergeordnete Funktion der gesamten Baugruppe und nicht jedes enthaltene Einzelmodul separat. Falls eine eindeutige Zuordnung schwierig ist, kann dies im Kommentarfeld vermerkt werden.

---

## 1. Lineareinheit

### Beschreibung
Eine Lineareinheit ist eine Baugruppe, deren Hauptfunktion eine lineare Bewegung in einer Richtung ist. Meist handelt es sich um eine einzelne Linearachse oder einen linearen Aktor.

### Zweck / Hauptfunktion
Lineares Transportieren, Verfahren oder Positionieren eines Bauteils, Werkzeugs oder einer weiteren Baugruppe.

### Typische Merkmale
- eine lineare Bewegungsrichtung
- Linearführung oder Schlitten
- Hubachse
- Pneumatikzylinder
- Spindel- oder Zahnriemenantrieb
- linearer Aktor

### Abgrenzung
Wenn die Baugruppe hauptsächlich in einer Richtung linear bewegt, wird sie als Lineareinheit klassifiziert. Wenn zwei oder drei orthogonale Linearachsen zu einem übergeordneten System kombiniert sind, handelt es sich eher um ein Gantry.

---

## 2. Gantry

### Beschreibung
Ein Gantry ist ein kartesisches Achssystem, das Bewegungen in zwei oder drei zueinander orthogonalen Richtungen ermöglicht. Es besteht typischerweise aus mehreren kombinierten Linearachsen.

### Zweck / Hauptfunktion
Positionieren, Transportieren oder Handhaben von Bauteilen, Werkzeugen oder Greifern in einem zwei- oder dreidimensionalen Arbeitsbereich.

### Typische Merkmale
- X-/Y- oder X-/Y-/Z-Bewegung
- zwei bis drei orthogonale Bewegungsrichtungen
- Portal- oder Achssystem
- mehrere kombinierte Linearachsen
- kartesischer Arbeitsraum

### Abgrenzung
Eine einzelne lineare Bewegungsrichtung spricht für eine Lineareinheit. Zwei oder drei orthogonale lineare Bewegungsrichtungen sprechen für ein Gantry. Im Unterschied zu einem Roboter erfolgt die Bewegung überwiegend kartesisch über Linearachsen.

---

## 3. Greifer

### Beschreibung
Ein Greifer ist eine Baugruppe, deren Hauptfunktion das Aufnehmen, Halten, Klemmen oder Ablegen eines Werkstücks ist. Der Greifer hat meist direkten Kontakt zum Werkstück.

### Zweck / Hauptfunktion
Werkstücke greifen, halten, fixieren, aufnehmen oder ablegen.

### Typische Merkmale
- Greifbacken oder Greiffinger
- Spann- oder Klemmmechanismus
- Sauger oder Vakuumsystem
- direkter Werkstückkontakt
- Endeffektor

### Abgrenzung
Wenn das reine Greifen, Halten oder Spannen im Vordergrund steht, wird die Baugruppe als Greifer klassifiziert. Wenn zusätzlich mehrere Bewegungs-, Übergabe- oder Ausrichtfunktionen in einer Baugruppe kombiniert sind, handelt es sich eher um eine Handhabungsbaugruppe.

---

## 4. Handhabungsbaugruppe / kombinierte Einheit

### Beschreibung
Eine Handhabungsbaugruppe ist eine kombinierte Einheit, die mehrere Teilfunktionen zur Handhabung eines Werkstücks integriert. Sie besteht häufig aus mehreren Modulen, zum Beispiel aus Greifer, Linearachse, Dreh- oder Schwenkeinheit und Sensorik.

### Zweck / Hauptfunktion
Werkstücke innerhalb eines Prozesses aufnehmen, bewegen, ausrichten, übergeben oder positionieren.

### Typische Merkmale
- Kombination mehrerer Funktionsmodule
- Greifen und Bewegen
- Ausrichten oder Übergeben
- integrierte Linear-, Dreh- oder Schwenkbewegung
- auf eine konkrete Handling-Aufgabe zugeschnitten

### Abgrenzung
Im Unterschied zum Greifer steht nicht nur der direkte Werkstückkontakt im Vordergrund, sondern eine vollständige kombinierte Handhabungsaufgabe. Wenn eine einzelne Bewegungsart eindeutig dominiert, kann die Baugruppe eher als Lineareinheit oder Rotationseinheit eingeordnet werden.

---

## 5. Roboter

### Beschreibung
Ein Roboter ist ein frei programmierbares, mehrachsiges System zur flexiblen Bewegung von Werkzeugen, Greifern oder Werkstücken innerhalb eines Arbeitsraums.

### Zweck / Hauptfunktion
Flexible Handhabung, Positionierung oder Bearbeitung durch programmierbare Bewegungen.

### Typische Merkmale
- Industrieroboter oder Roboterarm
- mehrere Achsen
- programmierbare Bahnbewegung
- definierter Arbeitsraum
- Werkzeug oder Greifer am Roboterflansch

### Abgrenzung
Ein Roboter ist flexibel programmierbar und besitzt typischerweise mehrere rotatorische Achsen. Ein Gantry bewegt sich dagegen überwiegend kartesisch über lineare Achsen. Eine Handhabungsbaugruppe ist meistens auf eine konkrete Aufgabe zugeschnitten und nicht so flexibel programmierbar wie ein Roboter.

---

## 6. Rotationseinheit

### Beschreibung
Eine Rotationseinheit ist eine Baugruppe, deren Hauptfunktion eine rotatorische Bewegung ist. Sie dreht, schwenkt, wendet oder richtet ein Bauteil, Werkzeug oder einen Werkstückträger um eine Achse aus.

### Zweck / Hauptfunktion
Drehen, Schwenken, Wenden, Indexieren oder Ausrichten.

### Typische Merkmale
- Dreheinheit
- Schwenkeinheit
- Rundtisch oder Drehteller
- Rotationsachse
- Wendeeinheit
- Winkelverstellung

### Abgrenzung
Wenn die rotatorische Bewegung die zentrale Funktion der Baugruppe ist, wird sie als Rotationseinheit klassifiziert. Wenn die Rotation nur Teil einer größeren kombinierten Handhabungsaufgabe ist, kann die Baugruppe eher als Handhabungsbaugruppe eingeordnet werden.

---

## Kurze Entscheidungshilfe

- hauptsächlich lineare Bewegung in einer Richtung → **Lineareinheit**
- zwei bis drei orthogonale lineare Bewegungsrichtungen → **Gantry**
- hauptsächlich greifen, halten, klemmen oder spannen → **Greifer**
- mehrere Handling-Funktionen kombiniert → **Handhabungsbaugruppe / kombinierte Einheit**
- frei programmierbares mehrachsiges System → **Roboter**
- hauptsächlich drehen, schwenken oder wenden → **Rotationseinheit**
