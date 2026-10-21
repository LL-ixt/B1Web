"""Rebuild B1 and render the named cameras into ./renders.

    blender -b B1.blend -P render_views.py -- "path/to/map.osm" Cam_Ref Cam_Lobby Cam_Porch Cam_Aerial
"""
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'build_b1.py')
exec(compile(open(SRC, encoding='utf-8').read(), SRC, 'exec'), {'__file__': SRC, '__name__': '__main__'})

cams = sys.argv[sys.argv.index('--') + 2:] if '--' in sys.argv else ['Cam_Ref']
scene = bpy.context.scene
for name in cams:
    scene.camera = bpy.data.objects[name]
    scene.render.filepath = os.path.join(HERE, 'renders', name + '.png')
    bpy.ops.render.render(write_still=True)
scene.camera = bpy.data.objects['Cam_Ref']
