"""
Baut ein Offline-Paket (.wepk) für "was erlaubt" aus einem Geofabrik-Extrakt.

    python tools/build_package.py niedersachsen-latest.osm.pbf niedersachsen.poly out/niedersachsen.wepk

Enthalten sind nur befahrbare Straßen (wie in der Overpass-Abfrage der App) mit den Tags,
die für das Tempolimit gebraucht werden. Format siehe PackageReader.kt in der App.
"""
import math
import struct
import sys
from datetime import datetime, timezone

import osmium
from shapely.geometry import Polygon, MultiPolygon, box
from shapely.prepared import prep

HIGHWAYS = {
    "motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link",
    "secondary", "secondary_link", "tertiary", "tertiary_link", "unclassified",
    "residential", "living_street", "road",
}
KEEP_KEYS = {"highway", "name", "ref", "oneway", "junction", "motorroad", "lanes", "zone:maxspeed", "zone:traffic"}
KEEP_PREFIXES = ("maxspeed", "source:maxspeed")

TILE_LAT = 0.02  # muss zu TileRepository passen
TILE_LON = 0.03
SAMPLE_M = 400.0  # Abtastabstand, um alle berührten Kacheln eines langen Segments zu finden
VERSION = 1


def keep_tag(k):
    return k in KEEP_KEYS or k.startswith(KEEP_PREFIXES)


def tile_of(lat, lon):
    return math.floor(lat / TILE_LAT), math.floor(lon / TILE_LON)


class Collector(osmium.SimpleHandler):
    def __init__(self):
        super().__init__()
        self.ways = []  # (id, [(k, v)], [(latE6, lonE6)])

    def way(self, w):
        if w.tags.get("highway") not in HIGHWAYS:
            return
        if w.tags.get("area") == "yes":
            return
        pts = []
        for n in w.nodes:
            if n.location.valid():
                pts.append((round(n.location.lat * 1e6), round(n.location.lon * 1e6)))
        if len(pts) < 2:
            return
        tags = sorted((t.k, t.v) for t in w.tags if keep_tag(t.k))
        self.ways.append((w.id, tags, pts))


def touched_tiles(pts):
    tiles = set()
    for (a_lat, a_lon), (b_lat, b_lon) in zip(pts, pts[1:]):
        a = (a_lat / 1e6, a_lon / 1e6)
        b = (b_lat / 1e6, b_lon / 1e6)
        dy = (b[0] - a[0]) * 110_540
        dx = (b[1] - a[1]) * 111_320 * math.cos(math.radians(a[0]))
        steps = max(1, int(math.hypot(dx, dy) / SAMPLE_M))
        for i in range(steps + 1):
            t = i / steps
            tiles.add(tile_of(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return tiles


def read_poly(path):
    """Geofabrik-.poly-Datei → shapely-Geometrie (Löcher mit '!' werden abgezogen)."""
    outers, holes = [], []
    with open(path, encoding="utf-8") as f:
        lines = [l.strip() for l in f]
    i = 1  # erste Zeile = Name
    while i < len(lines) and lines[i] != "END":
        name = lines[i]
        i += 1
        ring = []
        while lines[i] != "END":
            lon, lat = map(float, lines[i].split())
            ring.append((lon, lat))
            i += 1
        i += 1
        (holes if name.startswith("!") else outers).append(Polygon(ring))
    geom = MultiPolygon(outers).buffer(0)
    for h in holes:
        geom = geom.difference(h)
    return geom


def varint(n, out):
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return


def zigzag(n):
    return (n << 1) ^ (n >> 63)


def put_string(s, out):
    data = s.encode("utf-8")
    varint(len(data), out)
    out.extend(data)


def data_date(pbf):
    header = osmium.io.Reader(pbf, osmium.osm.osm_entity_bits.NOTHING).header()
    ts = header.get("osmosis_replication_timestamp")
    if ts:
        return ts[:10]
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def build(pbf, poly, out_path):
    c = Collector()
    c.apply_file(pbf, locations=True, idx="flex_mem")
    print(f"{len(c.ways)} Straßen gelesen", file=sys.stderr)

    strings = {}

    def sid(s):
        if s not in strings:
            strings[s] = len(strings)
        return strings[s]

    ways_buf = bytearray()
    tile_ways = {}
    for wid, tags, pts in c.ways:
        offset = len(ways_buf)
        varint(wid, ways_buf)
        varint(len(tags), ways_buf)
        for k, v in tags:
            varint(sid(k), ways_buf)
            varint(sid(v), ways_buf)
        varint(len(pts), ways_buf)
        plat, plon = 0, 0
        for lat, lon in pts:
            varint(zigzag(lat - plat), ways_buf)
            varint(zigzag(lon - plon), ways_buf)
            plat, plon = lat, lon
        for t in touched_tiles(pts):
            tile_ways.setdefault(t, []).append(offset)

    area = prep(read_poly(poly))
    lists_buf = bytearray()
    index = []
    complete_count = 0
    for (y, x) in sorted(tile_ways):
        offsets = sorted(tile_ways[(y, x)])
        cell = box(x * TILE_LON, y * TILE_LAT, (x + 1) * TILE_LON, (y + 1) * TILE_LAT)
        complete = area.contains(cell)
        complete_count += complete
        index.append(struct.pack(">iiii", y, x, len(lists_buf), (len(offsets) << 1) | int(complete)))
        prev = 0
        for o in offsets:
            varint(o - prev, lists_buf)
            prev = o

    head = bytearray(b"WEPK")
    head.append(VERSION)
    put_string(data_date(pbf), head)
    varint(round(TILE_LAT * 1e6), head)
    varint(round(TILE_LON * 1e6), head)
    varint(len(strings), head)
    for s in strings:  # dict behält die Einfügereihenfolge = ID
        put_string(s, head)
    head += struct.pack(">ii", len(index), len(lists_buf))

    with open(out_path, "wb") as f:
        f.write(head)
        for e in index:
            f.write(e)
        f.write(lists_buf)
        f.write(ways_buf)
    print(f"{out_path}: {len(index)} Kacheln ({complete_count} vollständig), "
          f"{len(strings)} Texte, {(len(head) + 16 * len(index) + len(lists_buf) + len(ways_buf)) / 1e6:.1f} MB",
          file=sys.stderr)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    build(*sys.argv[1:])
