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
