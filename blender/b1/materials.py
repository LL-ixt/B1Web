"""Material library; MAT maps names to bpy materials for MB.build."""
import bpy

MAT = {}

GLASS_POOL = ['B1_Glass'] * 12 + ['B1_GlassCurtain'] * 4 + ['B1_GlassBlind'] * 2 + ['B1_GlassDark'] * 2


def principled(name, color, rough=0.5, metal=0.0, coat=0.0, emission=None):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get('Principled BSDF')
    vals = {'Base Color': (*color, 1.0), 'Roughness': rough, 'Metallic': metal, 'Coat Weight': coat}
    if emission is not None:
        vals.update({'Emission Color': (*emission[0], 1.0), 'Emission Strength': emission[1]})
    for k, v in vals.items():
        if k in bsdf.inputs:
            bsdf.inputs[k].default_value = v
    m.diffuse_color = (*color, 1.0)
    MAT[name] = m
    return m


def add_grime(mat_name, scale, dark):
    """Multiply the base colour by a soft object-space noise so big flat surfaces read as weathered."""
    m = MAT[mat_name]
    nt = m.node_tree
    bsdf = nt.nodes['Principled BSDF']
    ramp = next((n for n in nt.nodes if n.bl_idname == 'ShaderNodeValToRGB'), None)
    if ramp is None:
        base = tuple(bsdf.inputs['Base Color'].default_value)
        coord = nt.nodes.new('ShaderNodeTexCoord')
        noise = nt.nodes.new('ShaderNodeTexNoise')
        noise.inputs['Scale'].default_value = scale
        noise.inputs['Detail'].default_value = 6.0
        ramp = nt.nodes.new('ShaderNodeValToRGB')
        ramp.color_ramp.elements[0].position = 0.35
        ramp.color_ramp.elements[1].position = 0.65
        nt.links.new(coord.outputs['Object'], noise.inputs['Vector'])
        nt.links.new(noise.outputs['Fac'], ramp.inputs['Fac'])
        nt.links.new(ramp.outputs['Color'], bsdf.inputs['Base Color'])
    else:
        base = tuple(m.diffuse_color)
    ramp.color_ramp.elements[0].color = tuple(c * (1 - dark) for c in base[:3]) + (1,)
    ramp.color_ramp.elements[1].color = base[:3] + (1,)


def make_materials():
    principled('B1_Wall', (0.80, 0.80, 0.77), 0.8)
    add_grime('B1_Wall', 0.6, 0.08)
    principled('B1_WallCream', (0.78, 0.60, 0.33), 0.75)        # ground floor of the main lobby
    add_grime('B1_WallCream', 0.8, 0.06)
    principled('B1_Frame', (0.62, 0.65, 0.66), 0.35, 0.6)
    principled('B1_FrameDark', (0.12, 0.13, 0.14), 0.4, 0.5)
    principled('B1_Glass', (0.035, 0.05, 0.065), 0.05, 0.0)
    principled('B1_GlassCurtain', (0.50, 0.46, 0.38), 0.6, 0.0, coat=1.0)
    principled('B1_GlassBlind', (0.40, 0.42, 0.43), 0.6, 0.0, coat=1.0)
    principled('B1_GlassDark', (0.008, 0.009, 0.01), 0.1)
    principled('B1_GlassCluster', (0.07, 0.10, 0.13), 0.05, 0.0)  # one glass for all clustered windows
    principled('B1_GlassLobby', (0.05, 0.065, 0.075), 0.03, 0.0)  # clear storefront glass, slightly lighter
    principled('B1_Roof', (0.38, 0.37, 0.35), 0.9)
    add_grime('B1_Roof', 0.3, 0.3)
    principled('B1_Canopy', (0.06, 0.065, 0.07), 0.5, 0.2)        # porte-cochere fascia + soffit
    principled('B1_CanopySoffit', (0.25, 0.26, 0.27), 0.5, 0.1)   # recessed ceiling panel
    principled('B1_Downlight', (1.0, 0.97, 0.9), 0.3, emission=((1.0, 0.95, 0.85), 6.0))
    principled('B1_Stone', (0.05, 0.05, 0.055), 0.3)              # dark granite steps
    principled('B1_SignBlue', (0.03, 0.20, 0.62), 0.3)
    principled('B1_Metal', (0.55, 0.56, 0.58), 0.35, 1.0)
    principled('B1_Steel', (0.62, 0.63, 0.65), 0.22, 1.0)
    principled('Ctx_Asphalt', (0.07, 0.07, 0.075), 0.9)
    add_grime('Ctx_Asphalt', 0.4, 0.3)
    principled('Ctx_Paving', (0.36, 0.34, 0.31), 0.9)
    add_grime('Ctx_Paving', 0.15, 0.25)
    principled('Ctx_Footway', (0.45, 0.38, 0.33), 0.9)
    principled('Ctx_Rust', (0.33, 0.17, 0.08), 0.7, 0.3)
    principled('Ctx_Wall', (0.70, 0.66, 0.58), 0.85)
    add_grime('Ctx_Wall', 0.5, 0.12)
    principled('Ctx_Roof', (0.30, 0.29, 0.28), 0.9)
    principled('Ctx_Leaf', (0.07, 0.22, 0.035), 0.8)
    principled('Ctx_Trunk', (0.13, 0.09, 0.06), 0.9)
    principled('Ctx_Tyre', (0.02, 0.02, 0.02), 0.8)
    for name, col in [('Car_White', (0.8, 0.8, 0.8)), ('Car_Silver', (0.45, 0.46, 0.48)),
                      ('Car_Black', (0.02, 0.02, 0.025)), ('Car_Red', (0.55, 0.03, 0.03)),
                      ('Car_Grey', (0.18, 0.19, 0.2))]:
        principled(name, col, 0.25, 0.4, coat=1.0)
