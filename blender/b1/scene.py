"""Sky, sun, cameras and render settings."""
import math

import bpy
from mathutils import Vector


def setup_scene(coll, arc=None):
    scene = bpy.context.scene
    world = scene.world or bpy.data.worlds.new('World')
    scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputWorld')
    bg = nt.nodes.new('ShaderNodeBackground')
    coord = nt.nodes.new('ShaderNodeTexCoord')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.5
    ramp.color_ramp.elements[0].color = (0.75, 0.85, 0.95, 1)
    ramp.color_ramp.elements[1].position = 0.75
    ramp.color_ramp.elements[1].color = (0.08, 0.28, 0.80, 1)
    map_range = nt.nodes.new('ShaderNodeMapRange')
    map_range.inputs['From Min'].default_value = -1.0
    map_range.inputs['From Max'].default_value = 1.0
    nt.links.new(coord.outputs['Generated'], sep.inputs['Vector'])
    nt.links.new(sep.outputs['Z'], map_range.inputs['Value'])
    nt.links.new(map_range.outputs['Result'], ramp.inputs['Fac'])
    nt.links.new(ramp.outputs['Color'], bg.inputs['Color'])
    bg.inputs['Strength'].default_value = 1.0
    nt.links.new(bg.outputs['Background'], out.inputs['Surface'])

    sun_data = bpy.data.lights.new('B1_Sun', 'SUN')
    sun_data.energy = 4.0
    sun_data.angle = math.radians(1.0)
    sun = bpy.data.objects.new('B1_Sun', sun_data)
    sun_dir = Vector((0.45, 0.55, 1.6)).normalized()   # high summer sun from the north-east
    sun.rotation_euler = sun_dir.to_track_quat('Z', 'Y').to_euler()
    coll.objects.link(sun)

    def cam(name, loc, target, lens):
        cd = bpy.data.cameras.new(name)
        cd.lens = lens
        cd.clip_end = 2000
        ob = bpy.data.objects.new(name, cd)
        ob.location = loc
        ob.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
        coll.objects.link(ob)
        return ob

    ref_cam = cam('Cam_Ref', (-36.0, 62.0, 1.6), (-4.0, -4.0, 19.0), 20)
    cam('Cam_Aerial', (95.0, 85.0, 75.0), (-5.0, -5.0, 10.0), 35)
    if arc:
        P, N = arc['P'], arc['N']
        cm, nm = P[len(P) // 2], N[len(N) // 2]
        eye = cm + nm * 30.0
        cam('Cam_Lobby', (eye.x, eye.y, 1.7), (cm.x, cm.y, 7.5), 24)
        c0, u, n = arc['entry']
        eye = c0 + n * 9.0 - u * 6.0
        cam('Cam_Porch', (eye.x, eye.y, 1.6), (c0.x + u.x * 1.0, c0.y + u.y * 1.0, 2.6), 20)
    scene.camera = ref_cam
    for eng in ('BLENDER_EEVEE', 'BLENDER_EEVEE_NEXT'):
        try:
            scene.render.engine = eng
            break
        except TypeError:
            pass
    scene.render.resolution_x, scene.render.resolution_y = 1500, 1000
