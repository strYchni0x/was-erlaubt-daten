"""
Lädt Geofabrik-Extrakte der Bundesländer, baut daraus Offline-Pakete und schreibt index.json.

    python tools/build_all.py <arbeitsverzeichnis> [bundesland ...] [--delete-pbf]

Ohne Angabe werden alle 16 Bundesländer gebaut. Das Ausgabeverzeichnis <arbeitsverzeichnis>/out
enthält danach <id>.wepk und index.json und kann so auf einen Webserver kopiert werden.
Bereits vorhandene, aktuelle Extrakte werden nicht erneut geladen; mit --delete-pbf werden sie
nach dem Bauen gelöscht (spart Platz, z. B. in GitHub Actions).
"""
import json
import os
import sys
import urllib.request
from email.utils import parsedate_to_datetime

sys.path.insert(0, os.path.dirname(__file__))
from build_package import build  # noqa: E402

REGIONS = [
    "baden-wuerttemberg", "bayern", "berlin", "brandenburg", "bremen", "hamburg", "hessen",
    "mecklenburg-vorpommern", "niedersachsen", "nordrhein-westfalen", "rheinland-pfalz",
    "saarland", "sachsen", "sachsen-anhalt", "schleswig-holstein", "thueringen",
]
BASE = "https://download.geofabrik.de/europe/germany/"
UA = {"User-Agent": "WasErlaubt-PackageBuilder/1"}


def fetch(url, path):
    """Lädt nur, wenn die Datei fehlt oder auf dem Server neuer ist."""
    req = urllib.request.Request(url, headers=UA, method="HEAD")
    with urllib.request.urlopen(req) as r:
        remote = parsedate_to_datetime(r.headers["Last-Modified"]).timestamp()
    if os.path.exists(path) and os.path.getmtime(path) >= remote:
        return
    print(f"lade {url}", file=sys.stderr)
    tmp = path + ".part"
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA)) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    os.replace(tmp, path)
    os.utime(path, (remote, remote))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    delete_pbf = "--delete-pbf" in sys.argv
    if not args:
        sys.exit(__doc__)
    work = args[0]
    regions = args[1:] or REGIONS
    pbf_dir = os.path.join(work, "pbf")
    out_dir = os.path.join(work, "out")
    os.makedirs(pbf_dir, exist_ok=True)
    os.makedirs(out_dir, exist_ok=True)

    for region in regions:
        pbf = os.path.join(pbf_dir, f"{region}-latest.osm.pbf")
        poly = os.path.join(pbf_dir, f"{region}.poly")
        fetch(BASE + f"{region}-latest.osm.pbf", pbf)
        fetch(BASE + f"{region}.poly", poly)
        build(pbf, poly, os.path.join(out_dir, f"{region}.wepk"))
        if delete_pbf:
            os.remove(pbf)

    # Katalog aus allen vorhandenen Paketen
    packages = {}
    for region in REGIONS:
        path = os.path.join(out_dir, f"{region}.wepk")
        if os.path.exists(path):
            packages[region] = {"size": os.path.getsize(path), "date": read_date(path)}
    with open(os.path.join(out_dir, "index.json"), "w", encoding="utf-8") as f:
        json.dump({"format": 1, "license": "ODbL, © OpenStreetMap-Mitwirkende", "packages": packages}, f, indent=1)
    print(f"index.json: {len(packages)} Pakete", file=sys.stderr)


def read_date(path):
    """Datenstand aus dem Paketkopf (nach "WEPK" + Version)."""
    with open(path, "rb") as f:
        head = f.read(64)
    length = head[5]
    return head[6:6 + length].decode("utf-8")


if __name__ == "__main__":
    main()
