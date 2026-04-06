# Isaac – Causal Coupling Phase 1

## Ziel

Isaac soll sich vom modularen Nebeneinander zu einer kausal erklärbaren inneren Vernetzung entwickeln.

Nicht nur mehr Module.
Nicht nur mehr Funktionen.
Sondern mehr nachvollziehbare Wechselwirkungen zwischen innerem Zustand, Gedächtnis, Bedeutung, Entscheidungen, Vertrauen und Verhalten.

## Leitgedanke

Isaac braucht nicht nur mehr Funktionen – Isaac braucht mehr kausal begründete innere Wechselwirkungen.

## Zentrale Entwicklungsfrage

Welche Module beeinflussen sich gegenseitig, warum tun sie das, und wie muss diese Wirkung strukturiert werden, damit daraus ein kohärenter persönlicher KI-Kern entsteht?

## Arten von Abhängigkeiten

### 1. Technische Abhängigkeiten
Wer braucht wen zur Ausführung, Datenversorgung oder Laufzeit.

Beispiele:
- Dashboard braucht Monitor Server
- Monitor Server braucht Kernelzustand
- Executor braucht Task- und Statuslogik
- Relay braucht Providerzugriff

### 2. Kausale Abhängigkeiten
Was beeinflusst was und warum.

Beispiele:
- Empathie beeinflusst Rückfrageverhalten, weil erkannter Zustand die Interaktion verändern soll
- Memory beeinflusst Entscheidungsgewichtung, weil frühere Erfahrungen aktuelle Relevanz verschieben
- Values beeinflussen Priorisierung, weil nicht jede mögliche Aktion gleich sinnvoll ist

### 3. Entscheidungs-Abhängigkeiten
Welche Module wirken auf Priorität, Routing, Risiko, Handlung oder Rückfrage.

Beispiele:
- Meaning + Values + Trust + Kontext wirken gemeinsam auf Handlungsfreigaben
- Empathie + Beziehungskontinuität beeinflussen, ob Isaac schweigt, fragt oder aktiv wird
- Datenschutzgewicht beeinflusst Providerwahl

### 4. Zustands-Abhängigkeiten
Welche internen Zustände andere Module oder Prozesse verändern.

Beispiele:
- Überlastung beeinflusst Executor- und Background-Verhalten
- Beziehungszustand beeinflusst Tonfall, Timing und Aktivitätsgrad
- Unsicherheit beeinflusst Rückfragewahrscheinlichkeit

### 5. Zeitliche Abhängigkeiten
Was vorher passieren muss, was später nachwirkt, was zyklisch läuft.

Beispiele:
- Background-Erkenntnisse fließen später in Entscheidungen ein
- Wiederholte Situationen verändern spätere Gewichtungen
- Langzeitgedächtnis wirkt verzögert auf Verhalten

### 6. Gedächtnis-Abhängigkeiten
Welche Erfahrungen oder Muster aus der Vergangenheit aktuelle Prozesse beeinflussen.

Beispiele:
- Wiederholte positive Nutzerreaktionen verstärken bestimmte Verhaltensmuster
- frühere Fehler verändern Risikoabschätzung
- wiederkehrende Themen erhöhen Kontexttiefe

### 7. Werte- und Bedeutungs-Abhängigkeiten
Wo Meaning, Values, Beziehung und Vertrauen Entscheidungen mitformen.

Beispiele:
- Isaac soll nicht nur effizient, sondern sinnvoll handeln
- Benachrichtigungen sollen nicht nur möglich, sondern bedeutsam sein
- Verhalten soll nicht nur funktional, sondern kontextethisch passend sein

### 8. Erziehungs-Abhängigkeiten
Abhängigkeiten, die nicht allein aus Code, sondern aus Lernen, Rückmeldung, Korrektur und gemeinsamer Entwicklung entstehen.

Beispiele:
- Nutzerreaktionen prägen spätere Situationsentscheidungen
- Grenzsetzung verändert Vertrauens- und Aktivitätsmuster
- gemeinsame Geschichte beeinflusst zukünftige Interaktion

## Erste große Kopplungsfelder

### Empathie ↔ Entscheidung
Empathie darf nicht nur den Stil beeinflussen, sondern auch:
- Routing
- Rückfragewahrscheinlichkeit
- Priorisierung
- Benachrichtigung
- Background-Beobachtung

### Memory ↔ Meaning ↔ Values
Gedächtnis soll nicht nur speichern, sondern Bedeutung und Wertung verändern.

### Trust ↔ Privilege ↔ Handlung
Vertrauen, Rechte und tatsächliche Handlungsmöglichkeiten müssen enger verzahnt werden.

### Audit ↔ Reflection ↔ Selbstverbesserung
Logs sollen nicht nur protokollieren, sondern Rückkopplung für spätere Korrektur und Entwicklung liefern.

### Background ↔ offene Fragen ↔ Nutzerkontext
Der Background-Loop soll nicht leer laufen, sondern an echten offenen Spannungen, ungelösten Fragen und Kontextsignalen weiterarbeiten.

### Datenschutz ↔ Decomposer ↔ Providerwahl
Datenschutzarchitektur muss direkt auf Zerlegung, Abstraktion und Wahl externer Instanzen wirken.

## Phase-1-Ziel

Phase 1 definiert noch nicht alle finalen Kopplungen, sondern schafft:

- eine gemeinsame Sprache für Abhängigkeiten
- ein erstes klares Modell der Koppelungstypen
- die wichtigsten Kopplungsfelder für Isaac
- die Basis für spätere Implementierung und Diagramme

## Leitsatz

Isaac soll nicht nur vernetzt sein, sondern kausal verstehbar vernetzt sein.

## Koppelungsmatrix – Phase 1

| Modul / Bereich | Technische Abhängigkeiten | Entscheidungs-Abhängigkeiten | Zustands-Abhängigkeiten | Gedächtnis-/Lern-Abhängigkeiten | Werte-/Bedeutungs-Abhängigkeiten | Erziehungs-Abhängigkeiten |
|---|---|---|---|---|---|---|
| Empathie | Kontext, Nutzerinput, Monitorzustand | Rückfrageverhalten, Priorisierung, Tonwahl | Stress, Offenheit, Erschöpfung, soziale Spannung | merkt Reaktionsmuster des Nutzers | beeinflusst Bedeutung von Interventionen | lernt, wann Nähe hilfreich oder störend ist |
| Memory | DB, Working Memory, Fakten, Gesprächsverlauf | Relevanzgewichtung, Wiederaufnahme von Themen | Beziehungszustand, Langzeitkontext | zentrale Basis für Musterbildung | verstärkt Bedeutung wiederkehrender Themen | speichert, was sich in Interaktion bewährt |
| Meaning | Kontext, Memory, Wertequellen | bestimmt, was bedeutsam genug für Aktion ist | beeinflusst Aktivitätsgrad | nutzt Verlauf zur Bedeutungsverdichtung | zentral | wächst durch Rückmeldung und gemeinsame Geschichte |
| Values | Regelwerk, Meaning, Trust | Priorisierung, Grenzziehung, Handlungswahl | beeinflusst Verhalten in Konflikten | lernt aus Korrektur und Folgen | zentral | wird durch Erziehungsphase geschärft |
| Trust / Privilege | Rechte- und Direktivenlogik | Freigaben, Hemmung, Eskalation | Unsicherheit, Vertrauensgrad | merkt Grenzüberschreitungen und Bestätigungen | wirkt auf Verantwortung | Vertrauen wächst oder sinkt durch Erfahrung |
| Background Loop | offene Aufgaben, Monitor, Zeitlogik | was weitergedacht oder verschoben wird | Überlastung, Ruhephasen, offene Spannungen | greift frühere offene Fragen wieder auf | arbeitet an bedeutsamen Restspannungen | lernt, wann Eigenaktivität wertvoll ist |
| Audit / Reflection | Logs, Events, Taskverlauf | spätere Korrektur und Selbstprüfung | Fehlerzustände, Instabilität | speichert Fehlmuster und Erfolge | kann Bedeutung von Fehlern erhöhen | Grundlage für reflektiertes Umlernen |
| Decomposer / Datenschutz | Input, Relay, Providerlogik | entscheidet Grad der Zerlegung | hohe Sensitivität verändert Verarbeitung | merkt riskante Muster | Datenschutz als Wert beeinflusst Verhalten | lernt, wann mehr Abschirmung nötig ist |
| Relay / Providerwahl | Provider, APIs, lokale Modelle | Routing, Fallback, Risikoabwägung | Belastung, Verfügbarkeit, Sensitivität | merkt Zuverlässigkeit von Providern | Datenschutz und Bedeutung wirken auf Auswahl | kann durch Erfahrung vorsichtiger oder selektiver werden |
| Executor / Tasks | Tasksystem, Statuslogik, Watchdog | Abbruch, Neustart, Reihenfolge | Überlastung, Hänger, Prioritätswechsel | merkt problematische Tasktypen | bedeutsame Tasks können Vorrang erhalten | lernt aus erfolgreichen und gescheiterten Abläufen |
| Dashboard / Monitor | Monitor Server, State, WS | indirekt: Sichtbarkeit beeinflusst Kontrolle | zeigt Zustände, Spannungen, Fehler | gibt Verlauf für menschliche Rückkopplung | macht Bedeutung sichtbar | unterstützt Erziehungs- und Korrekturphase |

## Erste Prioritäten für reale Umsetzung

### Priorität 1
Empathie ↔ Entscheidung ↔ Rückfrageverhalten

Frage:
- Wann schweigt Isaac?
- Wann fragt Isaac?
- Wann handelt Isaac aktiv?

### Priorität 2
Memory ↔ Meaning ↔ Values

Frage:
- Was bleibt nicht nur gespeichert, sondern wird handlungsrelevant?

### Priorität 3
Trust ↔ Privilege ↔ Handlung

Frage:
- Wann darf Isaac nur denken, wann vorschlagen, wann handeln?

### Priorität 4
Datenschutz ↔ Decomposer ↔ Providerwahl

Frage:
- Wie wird Datenschutz nicht nur Prinzip, sondern Routing-Faktor?

### Priorität 5
Audit ↔ Reflection ↔ spätere Selbstverbesserung

Frage:
- Wie wird aus Protokoll ein Lern- und Korrekturraum?

## Nächster Ausbau der Matrix

In der nächsten Phase soll aus dieser Matrix folgen:

- welche Kopplungen bereits technisch existieren
- welche nur konzeptionell bestehen
- welche bewusst erzogen werden müssen
- welche später in Zustandsmaschinen oder Gewichtungslogik übersetzt werden
- welche für Isaac Device und Situationslernen relevant werden
