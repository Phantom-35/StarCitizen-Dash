# SC-Dash

**Ein schlankes Second-Screen-Dashboard für Star Citizen – ohne Grafikkarten-Last.**

[![Tests](https://github.com/phantom-35/starcitizen-dash/actions/workflows/tests.yml/badge.svg)](https://github.com/phantom-35/starcitizen-dash/actions/workflows/tests.yml)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![Abhängigkeiten](https://img.shields.io/badge/abh%C3%A4ngigkeiten-keine-brightgreen)
![Lizenz](https://img.shields.io/badge/lizenz-MIT-lightgrey)

SC-Dash liest die `Game.log` von Star Citizen live mit und zeigt auf dem zweiten Monitor an,
was in deiner Session passiert – Kills, Tode, Ort, Shard, Serverstatus – plus Timer und Notizen.

![Screenshot](docs/screenshot.png)

---

## Warum „ohne GPU-Last“?

Star Citizen braucht jedes Megabyte Grafikspeicher – gerade auf Karten mit 8 GB wie einer RTX 4060.
Ein typisches Overlay oder ein Browser-Tab mit Animationen kann dort schnell 200–500 MB VRAM belegen.
SC-Dash ist darauf ausgelegt, das zu vermeiden:

| Maßnahme | Effekt |
|---|---|
| Dashboard-Fenster startet mit `--disable-gpu` (Software-Rendering) | **Kein VRAM** für das Dashboard, die Grafikkarte gehört dem Spiel |
| Eigenes, schlankes Browser-Profil ohne Erweiterungen | wenig RAM, keine Hintergrund-Tabs |
| Keine Animationen, Bilder, Web-Fonts, Canvas oder WebGL | winzige Neuzeichnungen, nur Text ändert sich |
| Daten werden alle 2 s abgefragt, neu gezeichnet nur bei Änderungen | praktisch keine CPU-Last |
| Polling pausiert, wenn das Fenster minimiert ist | 0 Aufwand, wenn du es nicht siehst |
| Backend: reines Python, keine Abhängigkeiten | ~30 MB RAM, kein Node, kein Electron |

> **Ehrlicher Hinweis:** Ganz ohne GPU geht es unter Windows nie – der Desktop-Compositor (DWM)
> stellt jedes Fenster dar, auch das Dashboard. Das sind aber nur wenige MB und sie fallen auch an,
> wenn z. B. Discord oder der Explorer auf dem zweiten Monitor offen ist.

SC-Dash ist **kein Overlay** und greift nicht ins Spiel ein. Es liest nur eine Textdatei, die das
Spiel ohnehin schreibt. Damit gibt es keinen Konflikt mit Easy Anti-Cheat.

---

## Funktionen

- **Session:** Pilotenname, aktueller Ort, Shard, Spieldauer
- **Kampfstatistik:** Spieler-Kills, NPC-Kills, Tode, K/D, zerstörte und verlorene Schiffe
- **Ereignis-Feed:** die letzten 40 Ereignisse (Kills, Tode, Ortswechsel, Shard-Wechsel …)
- **RSI-Serverstatus:** Platform / Persistent Universe / Arena Commander (alle 5 min)
- **Timer:** z. B. für Raffinerie-Jobs, Schiffsmieten oder Cooldowns – laufen auch nach Neustart weiter
- **Notizen:** Handelsrouten, Koordinaten, Missionsinfos – werden automatisch gespeichert
- **Links:** Schnellzugriff auf Erkul, UEX, SC Trade Tools, Wiki & Co. (anpassbar)
- **Lokal & privat:** Alles läuft auf deinem PC (`127.0.0.1`). Die einzige Internetanfrage ist der
  RSI-Serverstatus – abschaltbar mit `--no-status`.

---

## Installation (Windows)

1. **Python 3.9 oder neuer** installieren: <https://www.python.org/downloads/>
   → beim Installieren den Haken bei **„Add python.exe to PATH“** setzen.
2. Dieses Repository herunterladen: grüner Button **Code → Download ZIP** und entpacken
   (oder `git clone https://github.com/phantom-35/starcitizen-dash.git`).
3. **`start.bat`** doppelklicken.

Das war's. Ein Konsolenfenster zeigt Statusmeldungen, und das Dashboard öffnet sich als eigenes
Fenster (Edge oder Chrome im App-Modus). Zieh es auf den zweiten Monitor und drück ggf. `F11` für
Vollbild. Edge ist auf jedem Windows vorhanden, es muss also nichts weiter installiert werden.

Erst mal ohne Spiel ausprobieren? → **`demo.bat`** starten, das simuliert Ereignisse.

### Wo liegt meine Game.log?

SC-Dash sucht automatisch auf allen Laufwerken in den üblichen Ordnern, z. B.

```
C:\Program Files\Roberts Space Industries\StarCitizen\LIVE\Game.log
D:\Roberts Space Industries\StarCitizen\PTU\Game.log
```

und nimmt die zuletzt geänderte. Wird nichts gefunden (Chip **„KEINE GAME.LOG“** oben im
Dashboard), gib den Ordner einfach an:

```bat
start.bat --log "E:\Spiele\StarCitizen\LIVE"
```

Tipp: Im RSI-Launcher unter *Settings → Games* steht dein Installationspfad.

---

## Optionen

```
python -m scdash [Optionen]

  --log PFAD     Game.log oder Kanal-Ordner (LIVE/PTU/…) – Standard: automatische Suche
  --open         Dashboard-Fenster öffnen (Edge/Chrome, App-Modus, GPU aus)
  --port 8777    Port des lokalen Webservers
  --host ADRESSE Standard 127.0.0.1 (nur dieser PC). Mit 0.0.0.0 z. B. vom Tablet/Handy
                 im WLAN erreichbar – dann auf http://<PC-IP>:8777 öffnen.
  --no-status    RSI-Serverstatus nicht abrufen (keine Internetzugriffe)
  --demo         Demo-Modus mit simulierten Ereignissen
  -v             Ausführliche Ausgabe
```

**Dashboard auf Tablet oder Handy:** Mit `start.bat --host 0.0.0.0` kannst du das Dashboard auf
einem anderen Gerät im Heimnetz öffnen – dann belastet es deinen Gaming-PC grafisch überhaupt nicht.
Windows fragt beim ersten Mal nach einer Firewall-Freigabe (nur „Private Netzwerke“ erlauben).

**Eigener Browser statt `--open`:** Einfach <http://127.0.0.1:8777> öffnen. Damit dein Browser
keinen Grafikspeicher nutzt, in dessen Einstellungen die *Hardwarebeschleunigung* deaktivieren –
oder lieber `--open` verwenden, das macht genau das, ohne deinen normalen Browser zu verändern.

**Links anpassen:** `scdash/web/links.json` bearbeiten.

---

## Was wird erkannt?

| Ereignis | Log-Eintrag |
|---|---|
| Login / Pilotenname | `User Login Success - Handle[…]` |
| Shard-Beitritt | `<Join PU> … shard[…]` |
| Ortswechsel | `<RequestLocationInventory> … Location[…]` |
| Kills & Tode | `<Actor Death> CActor::Kill: …` |
| Schiffszerstörung | `<Vehicle Destruction> …` |
| Spiel beendet | `<SystemQuit>` |

Startet das Spiel neu, legt es eine frische `Game.log` an – SC-Dash merkt das und beginnt eine neue
Session. Ob das Spiel läuft, wird zusätzlich alle 15 s über die Prozessliste geprüft.

> Das Log-Format ist nicht offiziell dokumentiert und ändert sich gelegentlich mit Patches. Wenn
> etwas nicht mehr erkannt wird, bitte ein Issue mit der betreffenden Log-Zeile öffnen.

---

## Entwicklung

```bash
git clone https://github.com/phantom-35/starcitizen-dash.git
cd starcitizen-dash
python -m scdash --demo           # Demo starten → http://127.0.0.1:8777
python -m unittest discover -s tests -t . -v
```

Optional als Befehl installieren: `pip install .` → danach einfach `scdash --open`.

```
scdash/
├── cli.py        Kommandozeile, Start der Threads, Browserfenster
├── parser.py     Erkennung der Log-Zeilen (reine Funktionen, gut testbar)
├── state.py      Thread-sicherer Zustand + Auswertung (Kills/Tode/…)
├── watcher.py    Game.log mitlesen, Spielprozess erkennen
├── status.py     RSI-Serverstatus (cState-JSON)
├── server.py     Mini-HTTP-Server: statische Dateien + /api/state
├── demo.py       Simulierte Game.log für den Demo-Modus
└── web/          index.html, style.css, app.js, links.json
```

Beiträge sind willkommen – siehe [CONTRIBUTING.md](CONTRIBUTING.md). Änderungen stehen im
[CHANGELOG.md](CHANGELOG.md).

### Ideen für später

- Quantum-Travel- und Missions-Ereignisse, sobald stabile Log-Muster bekannt sind
- Session-Historie (Statistik über mehrere Abende)
- Kompakter Terminal-Modus (komplett ohne Browser)

---

## Rechtliches

SC-Dash ist ein inoffizielles Fan-Projekt und steht in keiner Verbindung zu Cloud Imperium Games
oder Roberts Space Industries. *Star Citizen®* ist eine eingetragene Marke von Cloud Imperium Rights LLC.

Lizenz: [MIT](LICENSE)
