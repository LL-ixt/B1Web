"""OpenStreetMap loading and lat/lon -> local metres projection."""
import math
import xml.etree.ElementTree as ET

from mathutils import Vector


def load_osm(path):
    root = ET.parse(path).getroot()
    nodes = {n.get('id'): (float(n.get('lat')), float(n.get('lon'))) for n in root.iter('node')}
    ways = {}
    for w in root.iter('way'):
        ways[w.get('id')] = {
            'refs': [nd.get('ref') for nd in w.iter('nd')],
            'tags': {t.get('k'): t.get('v') for t in w.iter('tag')},
        }
    return nodes, ways


def make_projector(nodes, ref_ids):
    lat0 = sum(nodes[r][0] for r in ref_ids) / len(ref_ids)
    lon0 = sum(nodes[r][1] for r in ref_ids) / len(ref_ids)
    kx = 111320.0 * math.cos(math.radians(lat0))
    ky = 110574.0

    def proj(ref):
        lat, lon = nodes[ref]
        return Vector(((lon - lon0) * kx, (lat - lat0) * ky))
    return proj
