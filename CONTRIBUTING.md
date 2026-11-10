# Mitmachen

Danke für dein Interesse! Ein paar Grundregeln, damit SC-Dash schlank bleibt:

1. **Keine GPU-Last.** Keine Animationen, Transitions, Canvas/WebGL, Videos, `backdrop-filter`,
   große Schatten oder Hintergrundbilder. Das Dashboard soll neben dem Spiel quasi unsichtbar sein.
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
