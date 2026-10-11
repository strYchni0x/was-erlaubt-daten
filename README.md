# was erlaubt – Offline-Straßendaten

Offline-Pakete für die Android-App [„was erlaubt“](https://github.com/strYchni0x/was-erlaubt-app), die das erlaubte Tempolimit passend zur
Fahrtrichtung anzeigt. Je Bundesland ein Paket (`<bundesland>.wepk`) plus `index.json`.

Die Pakete werden monatlich per GitHub Action aus den
[Geofabrik-Extrakten](https://download.geofabrik.de/europe/germany.html) gebaut und als
Release veröffentlicht. Die App lädt sie von
`https://github.com/strYchni0x/was-erlaubt-daten/releases/latest/download/`.
Aktueller Stand: [STAND.md](STAND.md).

## Inhalt

Nur für Autos befahrbare Straßen (`highway=motorway … residential, living_street, road`) mit
den Tags für das Tempolimit (`maxspeed*`, `source:maxspeed*`, `zone:*`, `oneway`, `motorroad`,
`lanes`, `name`, `ref`) in Kacheln von 0,02° × 0,03°.

## Selbst bauen

```
pip install -r tools/requirements.txt
python tools/build_all.py work            # alle 16 Bundesländer
python tools/build_all.py work bremen     # einzelne
```

## Lizenz

Skripte: Copyright © 2026 Florian Willnat, [GNU GPL v3 oder später](LICENSE).

Daten © OpenStreetMap-Mitwirkende, verfügbar unter der
[Open Database License (ODbL) 1.0](https://opendatacommons.org/licenses/odbl/1-0/).
Die Pakete sind eine abgeleitete Datenbank und stehen ebenfalls unter der ODbL.
