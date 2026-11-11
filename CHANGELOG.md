# Changelog

Alle nennenswerten Änderungen an diesem Projekt. Format angelehnt an
[Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionierung nach [SemVer](https://semver.org/lang/de/).

## [Unreleased]

## [0.8.1] – 2026-11-11

### Behoben
- Der Knopf „Ton an/aus“ öffnete zusätzlich eine leere Links-Seitenleiste
- Einblendungen (Auftrag angenommen, Kollision …) waren durchscheinend, der Auftragsbereich darunter
  schimmerte durch; lange Namen brachen auf zwei Zeilen um. Jetzt deckender Hintergrund, Namen
  werden auf eine Zeile verkleinert

## [0.8.0] – 2026-11-11

### Hinzugefügt
- **Schiffsdatenbank** (`scdash/data/ships.json`, 310 Fahrzeuge, Spielstand 4.10.2) mit Frachtraum und
  Quantum-Tank. Erzeugt von `tools/build_ship_data.py` aus den Spieldateien, abgeglichen mit Wiki-API,
  FleetYards und UEX. Nur Werte mit mindestens zwei übereinstimmenden Quellen; Widersprüche werden
  nicht übernommen; nicht unabhängig bestätigte Werte erscheinen mit „ca.“. Abgleich in
  `docs/ship-data-report.md`.
- **Quantum-Sprung in Prozent des Tanks** („braucht 42 % Tank“), Warnung „reicht nicht!“ bei über
  100 %, Hinweis „Tankstand prüfen“, wenn Bedarf plus Session-Verbrauch 100 % übersteigen; Verbrauch
  der Session in Prozent
- **Frachtraum** am Schiff und Abgleich mit Mengen-Zielen („12 Flüge nötig“ / „passt in einen Flug“)
- **Log-Check** (`--analyze`, optional `--compare`): Bericht über eine Game.log mit unkenntlich
  gemachten persönlichen Daten; wertet auch den Versuch „ausführlichere Log“ (`log_verbosity`) aus

### Geprüft
- Einheit der Treibstoffschätzung in der Log: **Millionstel SCU**. Nachgerechnet an zwei Sprüngen
  einer echten Session mit bekannten Koordinaten (1.995 km bei 1.750 km Luftlinie / 2.131 km
  Oberflächenweg) und am Referenzwert der Wiki; als Test festgehalten.

### Geändert
- Die rohe Treibstoffzahl wird nur noch gezeigt, wenn das Schiff unbekannt ist

## [0.7.0] – 2026-11-10

Schwerpunkt: Mehrwert beim Spielen – beide Modi zeigen mehr von dem, was man wirklich braucht.

### Hinzugefügt
- **Aufträge:** „Nächstes Ziel“ (Ort aus dem ersten offenen Ziel) mit „du bist hier“-Markierung,
  Fortschrittsbalken bei Mengen-Zielen (`8/24 SCU`), Fracht verladen/abgegeben, Ø-Dauer erledigter Aufträge
- **Bilanz statt Einnahmen:** Einkäufe, Strafen und Überweisungen werden automatisch eingerechnet;
  nur der Auftragslohn wird noch von Hand eingetragen
- **Kampf & Überleben:** „Zustand“ mit offenen Verletzungen und nötiger Med-Bed-Stufe (bis zur Behandlung)
- **Crew an Bord** und **Server-Nummer** in beiden Modi
- **Schiff:** Zeit an Bord, Treibstoffbedarf der geplanten Quantum-Route und Summe der geflogenen
  Sprünge (aus `fuel estimate` der echten Log); Schiffsname notfalls aus den Quantum-Zeilen
- **Signaltöne** (abschaltbar, Taste `T`) bei Tod, K.O., Auftragsende, Verbindungsfehler und Timer;
  fertige Timer werden zusätzlich groß eingeblendet
- **Verbindungsfehler** mit Klartext (30000 Zeitüberschreitung, 30013 Serverabsturz …); normale
  Abmeldungen (30010/30016/30028) lösen keinen Alarm aus

### Geändert
- **Schneller:** Long-Polling statt 2-s-Abfrage und Lesetakt 0,5 s – Ereignisse erscheinen nach
  höchstens ~0,5 s statt nach bis zu 3 s; im Leerlauf weniger Anfragen als vorher

## [0.6.0] – 2026-11-10

Gesamtprüfung: jede Erkennungsregel gegen die echte 4.10-Log und die Quellen abgeglichen, Live-Betrieb
mit End-to-End- und Dauertest geprüft.

### Behoben
- **„Spiel läuft“-Anzeige konnte auf deutschem Windows ausfallen:** Die Ausgabe von `tasklist` steht im
  OEM-Zeichensatz („ausgeführt“); das Dekodieren schlug fehl und beendete den Prüf-Thread unbemerkt.
- Raststationen hießen „R&R HUR-LEO“ statt „Everus Harbor“ (geratene Namen durch abgeglichene ersetzt)
- Waffenhersteller: KBAR ist Kroneg, nicht KnightBridge; zwei unbelegte Kürzel entfernt
- Server-Regionen: `apse` ist Australien (Sydney); fehlende Codes `ape`, `sae` ergänzt, geratene entfernt
- Session-Zeit fehlte nach einem Spielneustart bis zum Login – kommt jetzt aus der ersten Log-Zeile
- Ein nie angeflogenes Quantum-Ziel blieb bis zum nächsten Sprung stehen (wird bei Tod/Serverwechsel geräumt)
- Antwort „nichts Neues“ (HTTP 204) enthielt unzulässige Header
- README: Reste der alten Erkennungs-Tabelle entfernt

### Geändert
- Erkennungsregeln ohne Beleg entfernt (z. B. „Contract Expired“, „Entered Armistice Zone“) – jede Regel ist
  jetzt in einer echten Log gesehen oder in einer Quelle belegt; „Exiting Armistice Zone“ ergänzt
- Jurisdiktion nur noch mit dem echten Wortlaut „Entered … Jurisdiction“

### Hinzugefügt
- Installationsordner wird aus der Log des RSI-Launchers gelesen (auch bei eigenen Pfaden), dazu
  `Program Files (x86)` und `SteamLibrary` als Suchorte
- Standort wird bei Quantum-Ankunft an einem bekannten Ort sofort aktualisiert und über
  „Projected Start Location“ korrigiert, wenn man sich ohne Inventar-Abfrage bewegt hat
- Weitere Ortsnamen: Pyro-Stationen (Checkmate, Orbituary …), Außenposten, Sprungtor-Gateways
- Meldung „Quantum blockiert“
- Bei Logs > 8 MB werden Pilot, Shard und Version trotzdem vom Dateianfang gelesen
- Zeitabgleich mit der Uhr des Gaming-PCs (Dashboard auf Tablet/Handy)
- End-to-End-Live-Test (Watcher + Server, Log wird während des Betriebs geschrieben und rotiert) und
  Test der Prozessprüfung auf echtem Windows

## [0.5.0] – 2026-11-10

Recherche in quelloffenen Log-Parsern (sc-log-tracker, csr, all-slain, StarLogs), siehe README → Quellen.

### Geändert
- **Kampf-Modus wird „Kampf & Überleben“:** Star Citizen schreibt seit ~4.4 keine Kills mehr in die
  Log. Statt dauerhaft leerer Kill-Zähler zeigt der Modus jetzt Tode, K.O., Verletzungen, CrimeStat,
  Med-Bed, Kollisionen, längstes Überleben und den letzten Tod. Kills/K/D erscheinen nur noch, wenn
  die Log welche enthält.
- Quantum-Ziele werden eingeordnet statt intern angezeigt: Städte, Raststationen (`CRU-L4`),
  markierte Navpunkte, Partymitglieder, Asteroidenfelder; Auftragsmarker bekommen den Ort aus dem
  aktiven Auftragsziel.
- Tode werden über alle Quellen (`[ActorState] Dead`, `Corpse`, alte `Actor Death`) nur einmal gezählt.

### Hinzugefügt
- Eigener Tod über `[ActorState] Dead` / `Corpse` (aktuelle Versionen), inkl. „Schiff zerstört“ und Ort
- Kampfunfähigkeit, Verletzungen (mit Körperteil und Tier), Med-Bed, tödliche Kollisionen
- CrimeStat, Straftaten, Strafen, Beschlagnahmung, Sperrgebiet, Privatgelände, Ausfall der Überwachung
- Geld erhalten/gesendet, fertige Raffinerie-Aufträge, Belohnungen, Blueprints, Hangar bereit
- Quantum-Ziel als Anzeige unter dem Standort
- Bereinigung von Sprachpaket-Markup in Meldungen (`<EM4>`, `[500 Rep]`, `[BP]`)
- Grenz-Pingpong bei Jurisdiktionen erzeugt keine Meldungsflut mehr
- Demo-Modus mit realistischen Ereignissen aktueller Versionen

## [0.4.0] – 2026-11-10

Abgleich mit einer echten `Game.log` (Star Citizen 4.10).

### Behoben
- Mehrzeilige HUD-Meldungen (z. B. „Objective Complete“, Schiffs-Kanal) wurden übersehen
- Erledigte Aufträge wurden doppelt gezählt (das Spiel meldet das Ende bis zu dreimal)
- „Exited Monitored Space“ wurde nicht erkannt
- „Contract Available“ (Angebot) wird nicht mehr mit angenommenen Aufträgen verwechselt
- „Am Leben“ zählt erst ab dem Betreten des Universums, nicht schon im Hauptmenü

### Hinzugefügt
- Aktuelles Schiff über die Kanal-Meldung beim Ein-/Aussteigen (mit dem echten Schiffsnamen)
- Ziel-Status direkt aus den Server-Meldungen (`ObjectiveUpserted`)
- Quantum-Sprünge (Ziel gesetzt / angekommen) samt Zähler
- Spielversion in der Standort-Zeile
- Lesbare Namen für Notunterkünfte und Verteilzentren
- Regressionstest mit anonymisiertem Auszug einer echten Log-Datei, inklusive Live-Simulation

### Geändert
- Live-Mitlesen robuster: Lesen bis zum echten Dateiende, Öffnen mit voller Freigabe unter Windows,
  Neustart-Erkennung auch über die erste Zeile, fehlerhafte Zeilen kosten nie den Rest
- Schneller: irrelevante Zeilen werden mit einer Prüfung übersprungen
- Dashboard erhält nur noch Daten, wenn sich etwas geändert hat (HTTP 204), Verbindung bleibt offen
- Abhol-Ziele stehen in der Checkliste vor Abliefer-Zielen
- Demo-Modus verwendet die echten Formulierungen und Zeilenformate des Spiels

## [0.3.0] – 2026-11-10

### Hinzugefügt
- Modus-Umschalter **Kampf / Aufträge** (Taste `M`, `?mode=` in der URL, wird gemerkt)
- Auftrags-Modus: aktiver Auftrag mit Ziel-Checkliste, weitere laufende Aufträge, Verlauf mit Dauer,
  Ring „Im Auftrag“, Erfolgsquote, besuchte Orte, manuelle Einnahmen pro Spielsitzung
- Komm-Log mit allen HUD-Meldungen aus der `Game.log`
- Zonen-Status (Armistice, überwachter Raum, Jurisdiktion) und aktuelles Schiff als Anzeige unter dem Standort
- Einblendungen für angenommene, erledigte und gescheiterte Aufträge
- Demo-Modus spielt jetzt auch einen Auftrags-Abend durch

### Geändert
- Getrennte Ereignis-Feeds je Modus, damit Spielmeldungen keine Kampf-Ereignisse verdrängen

## [0.2.0] – 2026-11-10

### Geändert
- Komplett neues Design im Cockpit-HUD-Stil: großer Standortname, Chronometer-Ring, freistehende
  Statistiken, Ereignis-Zeitleiste statt Kästen; warme Amber-Farbpalette
- Notizen und Links wandern in eine ausfahrbare Seitenleiste (Tasten `N` / `L`)
- Layout skaliert mit der Bildschirmgröße (1366×768 bis 4K, auch Hochkant)

### Hinzugefügt
- Kill-/Tod-Einblendung für einige Sekunden
- „Am Leben seit“, aktuelle Kill-Serie und Bestwert, letzter Killer
- Lesbare Orte (System › Planet › Ort), Server-Region aus dem Shard-Namen
- Lesbare Schiffs- und Waffennamen mit Herstellern
- Timer mit Fortschrittsbalken
- Option `--gpu` für Hardwarebeschleunigung des Dashboard-Fensters
- Mitgelieferte Schriften (Rajdhani, Share Tech Mono – OFL)

## [0.1.0] – 2026-11-10

### Hinzugefügt
- Live-Auswertung der `Game.log`: Pilot, Shard, Ort, Session-Dauer
- Kill-/Death-Statistik inkl. NPC-Kills, K/D, zerstörte/verlorene Schiffe
- Ereignis-Feed (letzte 40 Ereignisse)
- RSI-Serverstatus (alle 5 Minuten, abschaltbar mit `--no-status`)
- Timer (z. B. Raffinerie-Jobs) und Notizen, lokal im Browser gespeichert
- Konfigurierbare Link-Liste (`scdash/web/links.json`)
- `--open`: eigenes Fenster per Edge/Chrome im App-Modus mit deaktivierter GPU
- Demo-Modus (`--demo` / `demo.bat`)
- Automatische Suche der `Game.log` (LIVE, PTU, EPTU … auf allen Laufwerken)
