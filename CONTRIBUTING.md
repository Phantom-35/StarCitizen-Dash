# Mitmachen

Danke für dein Interesse! Ein paar Grundregeln, damit SC-Dash schlank bleibt:

1. **Kaum GPU-Last.** Das Dashboard läuft standardmäßig mit Software-Rendering. Effekte (Glow,
   Verläufe) nur statisch; Animationen nur kurz und auf kleinen Flächen (z. B. Kill-Einblendung).
   Kein Canvas/WebGL, keine Videos, kein `backdrop-filter`, keine Dauer-Animationen über große Flächen.
2. **Keine Abhängigkeiten.** Backend nur Python-Standardbibliothek, Frontend nur Vanilla-JS.
3. **Belege statt Vermutungen.** Jedes neue Log-Muster braucht entweder eine echte (anonymisierte)
   Zeile aus einer `Game.log` oder eine Quelle (quelloffenes Projekt, das mit echten Logs arbeitet).
   Bitte im README unter „Was wird erkannt?“ eintragen und mit einem Test absichern. Echte Zeilen
   gehören nach `tests/fixtures/` – Spielernamen, Konto-IDs und IP-Adressen vorher ersetzen.

```bash
python -m unittest discover -s tests -t . -v   # Tests
python -m scdash --demo                        # ausprobieren ohne Spiel
```

## Neue Log-Ereignisse melden

Star Citizen ändert das Log-Format gelegentlich. Wenn etwas nicht mehr erkannt wird, öffne ein Issue
mit der betreffenden Zeile aus der `Game.log` – Spielernamen gerne vorher unkenntlich machen.

## Layout prüfen (vor jedem Design-Änderung)

Ein Prüfskript lädt das Dashboard mit absichtlich schwierigen Inhalten (sehr lange Namen, viele Ziele,
alle Statusanzeigen gleichzeitig, sechs Timer) und misst in 9 Bildschirmgrößen × 2 Modi × 3 Zuständen
(normal, Timer-Eingabe offen, Seitenleiste offen, Verlauf offen; mit eingeblendetem Update-Hinweis) plus einer laufenden Einblendung, ob irgendein
sichtbares Element in einen anderen Bereich ragt, abgeschnitten wird, über den Rand läuft oder sich mit
etwas anderem überlappt. Braucht Node.js und Playwright (nicht Teil der normalen Tests):

```bash
python tools/make_stress_log.py stress.log
python -m scdash --log stress.log --no-status --port 8777      # in einem zweiten Fenster
# (mit SCDASH_DATA_DIR=<leerer Ordner> landen Verlauf und Fensterposition nicht in deinen echten Daten)
node tools/ui_audit.js ui-audit stress.log                     # Screenshots + Bericht, Exit-Code 1 bei Funden
```

