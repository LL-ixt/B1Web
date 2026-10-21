"""Build the exterior of HUST building B1 in Blender from an OpenStreetMap export.

Footprint and per-part heights come from OSM (way 184021007 + its building:part ways);
facade articulation follows the reference photos in the project root. The model is
assembled from the modules in ./b1 (wings, lobby, tower, rooftop, context, scene),
each piece landing in its own object/collection under "B1_OSM".

Run inside a live Blender (e.g. via the BlenderMCP socket) or headless:
    blender -b B1.blend -P build_b1.py -- "path/to/map.osm"
Re-running rebuilds only the "B1_OSM" collection and reloads the b1 package.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(globals().get('__file__', 'D:/Project III/B1Web/blender/build_b1.py')))
OSM_PATH = globals().get('OSM_PATH') or os.path.join(HERE, '..', 'map (3).osm')
if '--' in sys.argv and len(sys.argv) > sys.argv.index('--') + 1:
    OSM_PATH = sys.argv[sys.argv.index('--') + 1]

if HERE not in sys.path:
    sys.path.insert(0, HERE)
for name in [m for m in sys.modules if m == 'b1' or m.startswith('b1.')]:
    del sys.modules[name]

from b1.main import run  # noqa: E402

run(OSM_PATH)
