# Schiffsdaten – Abgleich der Quellen

Erzeugt am 2026-11-11 mit `tools/build_ship_data.py`. Spielversion laut Wiki-API: **4.10.2-LIVE.12881860**.

SC-Dash zeigt Frachtraum und Quantum-Tank nur für Schiffe, bei denen **mindestens zwei Quellen
übereinstimmen** und kein ungeklärter Widerspruch besteht. Die offizielle RSI-Schiffsliste dient nur zum Vergleich: Sie enthält
Marketing-Angaben, die oft von den Werten im Spiel abweichen.

| | Anzahl |
|---|---:|
| Fahrzeuge in den Spieldateien | 331 |
| davon in der Wiki-API | 310 |
| davon bei FleetYards | 220 |
| übernommen (mind. ein bestätigter Wert) | 310 |
| mit bestätigtem Quantum-Tank | 249 |
| mit bestätigtem Frachtraum | 307 |
| Quantum-Tank unabhängig bestätigt | 171 |
| Frachtraum unabhängig bestätigt | 226 |

„Unabhängig bestätigt“ heißt: FleetYards oder UEX nennt denselben Wert wie die Spieldateien.
Werte, die nur die Spieldateien und die darauf aufbauende Wiki-API nennen, zeigt SC-Dash als
ungefähr („ca.“) an.

## Widersprüche beim Quantum-Tank

Mehrheit gewinnt; abweichende Quelle in Klammern.

- **Argo RAFT**: 7.2 SCU (scunpacked, wiki, fleetyards) – abweichend: {'uex': 1.8}
- **Mirai Guardian QI**: 4.6 SCU (scunpacked, wiki, fleetyards) – abweichend: {'uex': 1.79}

## Widersprüche beim Frachtraum


- **Aegis Javelin**: 0.0 SCU (scunpacked, wiki) – abweichend: {'fleetyards': 5400.0} → **nicht übernommen**
- **Aegis Retaliator**: 0.0 SCU (scunpacked, wiki, fleetyards) – abweichend: {'uex': 74.0} → **nicht übernommen**
- **Esperia Prowler**: 0.0 SCU (scunpacked, wiki, fleetyards) – abweichend: {'uex': 32.0} → **nicht übernommen**
- **Tumbril Cyclone**: 1.0 SCU (scunpacked, wiki, uex) – abweichend: {'fleetyards': 0.0}

## Nur eine Quelle (nicht übernommen)

- Aegis Gladius Dunlevy: cargo = {'scunpacked': 0.0}
- Aegis Gladius Dunlevy: qt_fuel = {'scunpacked': 0.6}
- Aegis Reclaimer Teach's Special: cargo = {'scunpacked': 420.0}
- Aegis Reclaimer Teach's Special: qt_fuel = {'scunpacked': 21.8}
- Argo MOLE Teach's Special: cargo = {'scunpacked': 32.0}
- Argo MOLE Teach's Special: qt_fuel = {'scunpacked': 6.4}
- C.O. Nomad Teach's Special: cargo = {'scunpacked': 0.0}
- C.O. Nomad Teach's Special: qt_fuel = {'scunpacked': 1.0}
- Drake Caterpillar: cargo = {'scunpacked': 576.0}
- Drake Caterpillar: qt_fuel = {'scunpacked': 18.8}
- Drake Command Module: cargo = {'scunpacked': 0.0}
- Drake Command Module: qt_fuel = {'scunpacked': 1.0}
- Drake Golem Teach's Special: cargo = {'scunpacked': 0.0}
- Drake Golem Teach's Special: qt_fuel = {'scunpacked': 1.0}
- Drake Vulture Teach's Special: cargo = {'scunpacked': 12.0}
- Drake Vulture Teach's Special: qt_fuel = {'scunpacked': 0.9}
- Grey's Shiv: cargo = {'scunpacked': 32.0}
- Grey's Shiv: qt_fuel = {'scunpacked': 4.1}
- Grey's Shiv: cargo = {'scunpacked': 32.0}
- Grey's Shiv: qt_fuel = {'scunpacked': 4.1}
- Grey's Shiv: cargo = {'scunpacked': 32.0}
- Grey's Shiv: qt_fuel = {'scunpacked': 4.1}
- MISC Fortune Teach's Special: cargo = {'scunpacked': 16.0}
- MISC Fortune Teach's Special: qt_fuel = {'scunpacked': 0.9}
- MISC Starfarer Teach's Special: cargo = {'scunpacked': 291.0}
- MISC Starfarer Teach's Special: qt_fuel = {'scunpacked': 19.0}
- Power Suit: cargo = {'scunpacked': 0.0}
- RSI Apollo Medivac: cargo = {'scunpacked': 32.0}
- RSI Apollo Medivac: qt_fuel = {'scunpacked': 9.4}
- RSI Apollo Medivac: cargo = {'scunpacked': 32.0}
- RSI Apollo Medivac: qt_fuel = {'scunpacked': 9.4}
- RSI Apollo Medivac: cargo = {'scunpacked': 32.0}
- RSI Apollo Medivac: qt_fuel = {'scunpacked': 9.4}
- RSI Apollo Triage: cargo = {'scunpacked': 32.0}
- RSI Apollo Triage: qt_fuel = {'scunpacked': 9.4}
- RSI Apollo Triage: cargo = {'scunpacked': 32.0}
- RSI Apollo Triage: qt_fuel = {'scunpacked': 9.4}
- RSI Apollo Triage: cargo = {'scunpacked': 32.0}
- RSI Apollo Triage: qt_fuel = {'scunpacked': 9.4}
- RSI Meteor: cargo = {'scunpacked': 0.0}
- RSI Meteor: qt_fuel = {'scunpacked': 0.9}

## RSI-Schiffsliste weicht ab (13 Schiffe)

| Schiff | Im Spiel (SCU) | RSI-Liste (SCU) |
|---|---:|---:|
| Aegis Hammerhead | 40 | 64 |
| Anvil F7C Hornet Mk I | 0 | 2 |
| Anvil F7C Hornet Mk II | 2 | 0 |
| Argo MOTH | 224 | 320 |
| Argo RAFT | 192 | 224 |
| Drake Golem | 0 | 32 |
| Greycat MTC | 0 | 0.06 |
| Greycat ROC | 0 | 1.2 |
| Greycat ROC-DS | 0 | 3.4 |
| Origin 135c | 6 | 4 |
| RSI Aurora Mk II | 2 | 5 |
| RSI Polaris | 576 | 620 |
| RSI Polaris | 576 | 620 |
