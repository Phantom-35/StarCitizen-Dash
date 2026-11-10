# Changelog

Alle nennenswerten Änderungen an diesem Projekt. Format angelehnt an
[Keep a Changelog](https://keepachangelog.com/de/1.1.0/), Versionierung nach [SemVer](https://semver.org/lang/de/).

## [Unreleased]

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
