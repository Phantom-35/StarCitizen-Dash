# Mitmachen

Danke für dein Interesse! Ein paar Grundregeln, damit SC-Dash schlank bleibt:

1. **Kaum GPU-Last.** Das Dashboard läuft standardmäßig mit Software-Rendering. Effekte (Glow,
   Verläufe) nur statisch; Animationen nur kurz und auf kleinen Flächen (z. B. Kill-Einblendung).
   Kein Canvas/WebGL, keine Videos, kein `backdrop-filter`, keine Dauer-Animationen über große Flächen.
2. **Keine Abhängigkeiten.** Backend nur Python-Standardbibliothek, Frontend nur Vanilla-JS.
3. **Tests.** Neue Log-Muster bitte mit einer echten (anonymisierten) Beispielzeile in
   `tests/test_parser.py` absichern.

```bash
python -m unittest discover -s tests -t . -v   # Tests
python -m scdash --demo                        # ausprobieren ohne Spiel
```

## Neue Log-Ereignisse melden

Star Citizen ändert das Log-Format gelegentlich. Wenn etwas nicht mehr erkannt wird, öffne ein Issue
mit der betreffenden Zeile aus der `Game.log` – Spielernamen gerne vorher unkenntlich machen.
