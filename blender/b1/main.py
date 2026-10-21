"""Assemble B1 from its modules into the B1_OSM collection tree."""
import bpy

from . import config
from .config import B1_WAY
from .context import build_context, build_ground
from .lobby import build_lobby
from .materials import make_materials
from .meshkit import collection
from .osm import load_osm, make_projector
from .rooftop import build_rooftop
from .scene import setup_scene
from .tower import build_tower
from .wings import build_wings, load_parts


def reset_root(name='B1_OSM'):
    old = bpy.data.collections.get(name)
    if old:
        for ob in list(old.all_objects):
            bpy.data.objects.remove(ob, do_unlink=True)
        for ch in list(old.children_recursive):
            bpy.data.collections.remove(ch)
        bpy.data.collections.remove(old)
    for block in (bpy.data.meshes, bpy.data.curves, bpy.data.cameras, bpy.data.lights):
        for d in list(block):
            if d.users == 0 and d.name.startswith(('B1_', 'Ctx_', 'Cam_', 'Lobby_', 'Tower_', 'Roof_')):
                block.remove(d)
    root = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(root)
    return root


def run(osm_path):
    osm = load_osm(osm_path)
    nodes, ways = osm
    proj = make_projector(nodes, ways[B1_WAY]['refs'][:-1])

    root = reset_root()
    c_b1 = collection(root, 'B1_Building')
    c_ctx = collection(root, 'B1_Context')
    c_rig = collection(root, 'B1_CamerasLights')

    ob = bpy.data.objects.get('Cube')  # default startup cube sits inside the footprint
    if ob:
        ob.hide_set(True)
        ob.hide_render = True

    make_materials()
    info = load_parts(osm, proj)
    build_wings(info, collection(c_b1, 'B1_Wings'))
    arc = build_lobby(osm, proj, c_b1)
    build_tower(arc, info, c_b1)
    build_rooftop(info, c_b1)

    build_ground(c_ctx)
    if config.BUILD_CONTEXT:
        b1_outline = [proj(r) for r in ways[B1_WAY]['refs'][:-1]]
        build_context(osm, proj, c_ctx, b1_outline)
    setup_scene(c_rig, arc)

    def tree(c, depth=0):
        mesh = [o for o in c.objects if o.type in ('MESH', 'FONT')]
        faces = sum(len(o.data.polygons) for o in mesh if o.type == 'MESH')
        print('  ' * depth + f'{c.name}: {len(c.objects)} objects, {faces} faces')
        for o in c.objects:
            if depth >= 1 and c.name != 'B1_Context':
                print('  ' * (depth + 1) + '- ' + o.name)
        for ch in c.children:
            tree(ch, depth + 1)
    tree(root)
