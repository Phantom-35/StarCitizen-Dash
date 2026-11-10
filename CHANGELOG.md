# Changelog

Alle nennenswerten Änderungen an diesem Projekt. Format angelehnt an
[Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionierung nach [SemVer](https://semver.org/lang/de/).

## [Unreleased]

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
