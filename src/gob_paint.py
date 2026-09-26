"""Hand-painted skin for the goblin.

Colours, masks and painted shading (ray-traced AO, curvature) are computed per vertex on the dense
GOB_BodyHi mesh, then baked (Cycles EMIT, selected-to-active) into the game mesh's texture.
"""
import bpy, bmesh, math, os
import numpy as np
from mathutils import Vector, Matrix, noise
from mathutils.bvhtree import BVHTree
from gob_common import ROOT, smoothstep
import gob_body

TEX_DIR = os.path.join(ROOT, "textures")


def hexc(h):
    h = h.lstrip('#')
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)])


def srgb_to_lin(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def mesh_arrays(me):
    V = len(me.vertices)
    co = np.empty(V * 3)
    me.vertices.foreach_get('co', co)
    no = np.empty(V * 3)
    me.vertex_normals.foreach_get('vector', no)
    e = np.empty(len(me.edges) * 2, dtype=np.int64)
    me.edges.foreach_get('vertices', e)
    return co.reshape(-1, 3), no.reshape(-1, 3), e.reshape(-1, 2)


def smooth_vals(vals, e, V, it=2, f=0.5):
    deg = np.maximum(np.bincount(e.ravel(), minlength=V), 1).astype(float)
    for _ in range(it):
        acc = np.zeros_like(vals)
        np.add.at(acc, e[:, 0], vals[e[:, 1]])
        np.add.at(acc, e[:, 1], vals[e[:, 0]])
        acc = acc / (deg[:, None] if vals.ndim > 1 else deg)
        vals = (1 - f) * vals + f * acc
    return vals


def ray_ao(ob, co, no, rays=16, dist=0.12):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bvh = BVHTree.FromBMesh(bm)
    bm.free()
    rng = np.random.default_rng(3)
    # cosine-weighted hemisphere around +Z
    u1, u2 = rng.random(rays), rng.random(rays)
    r, phi = np.sqrt(u1), 2 * math.pi * u2
    H = np.stack([r * np.cos(phi), r * np.sin(phi), np.sqrt(1 - u1)], 1)
    ao = np.empty(len(co))
    for i in range(len(co)):
        n = Vector(no[i])
        t = n.orthogonal().normalized()
        b = n.cross(t)
        rot = rng.random() * 2 * math.pi
        c, s = math.cos(rot), math.sin(rot)
        t, b = t * c + b * s, b * c - t * s
        o = Vector(co[i]) + n * 0.0008
        hit = 0
        for h in H:
            d = t * h[0] + b * h[1] + n * h[2]
            if bvh.ray_cast(o, d, dist)[0] is not None:
                hit += 1
        ao[i] = 1.0 - hit / rays
    return ao


def curvature(co, no, e):
    V = len(co)
    d = co[e[:, 1]] - co[e[:, 0]]
    l2 = np.maximum((d * d).sum(1), 1e-12)
    acc = np.zeros(V)
    np.add.at(acc, e[:, 0], (no[e[:, 0]] * d).sum(1) / l2)
    np.add.at(acc, e[:, 1], (no[e[:, 1]] * -d).sum(1) / l2)
    deg = np.maximum(np.bincount(e.ravel(), minlength=V), 1)
    return acc / deg          # >0 concave (cavity), <0 convex


def vnoise(co, scale, seed=0):
    off = Vector((seed * 17.3, seed * 5.1, seed * 9.7))
    return np.array([noise.noise(Vector(p) * scale + off) for p in co])


PAL = {
    'skin': hexc('#66793a'), 'skin_dark': hexc('#45572a'), 'skin_light': hexc('#83924b'),
    'belly': hexc('#939a57'), 'red': hexc('#b8563a'), 'blush': hexc('#a0643e'),
    'nail': hexc('#3a2f22'), 'mouth': hexc('#2b1a15'), 'lip': hexc('#7a5a36'), 'tooth': hexc('#dccfa6'),
    'hand': hexc('#5a6a31'), 'wart': hexc('#50642e'),
    'pupil': hexc('#140c08'), 'iris': hexc('#f0a020'), 'iris_rim': hexc('#8a4a0e'), 'sclera': hexc('#d8cf98'),
}


def _mix(a, b, t):
    t = np.clip(t, 0, 1)[:, None]
    return a * (1 - t) + b * t


def body_colors(co, no, e, variant=None):
    LM = gob_body.LM
    V = len(co)
    x, y, z = co.T
    ax = np.abs(x)
    n1 = vnoise(co, 9.0, 1)
    n2 = vnoise(co, 30.0, 2)
    n3 = vnoise(co, 70.0, 3)
    col = _mix(np.tile(PAL['skin'], (V, 1)), PAL['skin_light'], 0.5 + 0.6 * n1)
    col = _mix(col, PAL['skin_dark'], 0.35 * np.clip(-n2, 0, 1) + 0.25 * smoothstep(0.03, 0.09, y))
    col = _mix(col, PAL['wart'], 0.35 * smoothstep(0.55, 0.68, n3))                         # mottled spots
    col = _mix(col, PAL['skin_dark'], 0.3 * smoothstep(0.32, 0.06, z))                      # darker shins and feet
    belly = smoothstep(-0.03, -0.09, y) * np.exp(-((z - 0.53) / 0.07) ** 2) * smoothstep(0.11, 0.05, ax)
    col = _mix(col, PAL['belly'], 0.45 * belly)
    ext = np.maximum(smoothstep(0.46, 0.52, ax) * (np.abs(z - 0.715) < 0.1), smoothstep(0.08, 0.04, z))
    col = _mix(col, PAL['hand'], 0.45 * ext)

    # ears: red inside the cup, green on the rim and back
    ear = smoothstep(0.092, 0.12, ax) * (z > 0.86) * (z < 1.04)
    inner = smoothstep(0.05, 0.55, -no[:, 1])
    col = _mix(col, PAL['red'], 0.85 * ear * inner * (0.75 + 0.25 * n2))
    col = _mix(col, PAL['blush'], 0.25 * ear * (1 - inner))
    # nose tip, cheeks, knuckles, elbows, knees
    d_nose = np.linalg.norm(co - LM['nose_tip'], axis=1)
    col = _mix(col, PAL['red'], 0.75 * (1 - smoothstep(0.0, 0.055, d_nose)))
    for c, s, k in (((0.058, -0.103, 0.884), 0.020, 0.35), ((0.318, 0.030, 0.715), 0.022, 0.35),
                    ((0.088, -0.044, 0.248), 0.024, 0.35)):
        for sg in (1, -1):
            d2 = ((co - np.array([sg * c[0], c[1], c[2]])) ** 2).sum(1)
            col = _mix(col, PAL['blush'], k * np.exp(-d2 / (2 * s * s)))
    tips = []
    for f, pts in LM['fingers_L'].items():
        p2, p3 = np.array(pts[2]), np.array(pts[3])
        dvec = (p3 - p2) / np.linalg.norm(p3 - p2)
        for sg in (1, -1):          # knuckles
            k = np.exp(-((co - np.array(pts[0]) * [sg, 1, 1] - [0, 0, 0.012]) ** 2).sum(1) / (2 * 0.011 ** 2))
            col = _mix(col, PAL['blush'], 0.3 * k)
        tips.append(p3 + dvec * 0.006)
    for dx, r, ln in ((-0.028, 0.0185, 0.060), (0.001, 0.0155, 0.058), (0.029, 0.0135, 0.050)):
        tips.append(np.array([0.100 + dx + 0.006 * np.sign(dx), -0.090 - ln - r * 0.6, 0.016]))
    nail = np.zeros(V)
    for t in tips:
        for sg in (1, -1):
            d = np.linalg.norm(co - t * np.array([sg, 1, 1]), axis=1)
            nail = np.maximum(nail, 1 - smoothstep(0.006, 0.013, d))
    nail *= smoothstep(-0.1, 0.35, no[:, 2])
    col = _mix(col, PAL['nail'], 0.95 * nail)
    if variant == 'warpaint':
        col = warpaint(col, co)
    elif variant == 'chief':
        col = chiefpaint(col, co)
    elif variant == 'shaman':
        col = shamanpaint(col, co)
    return col


def shamanpaint(col, co):
    """Shaman's paint: bone-white dots under the eyes and down the chin, an ochre third eye on the brow, a white
    spiral on the chest, dotted forearms, ochre-dipped hands."""
    x, y, z = co.T
    ax = np.abs(x)
    white, ochre = hexc('#e2dcc6'), hexc('#c08a26')
    rn = np.linalg.norm((co - gob_body.HC) / gob_body.HR, axis=1)
    face = smoothstep(-0.05, -0.09, y) * smoothstep(1.2, 1.1, rn) * (z > 0.78)
    eye = gob_body.LM['eye_L']
    w = np.zeros(len(co))
    for dx in (-0.013, 0.0, 0.013):                   # three dots under each eye
        for sg in (1, -1):
            d = np.hypot(x - sg * (eye[0] + dx), z - (eye[2] - 0.036))
            w = np.maximum(w, face * smoothstep(0.0062, 0.0042, d))
    for zc in (0.826, 0.808, 0.79):                   # dotted line down the chin
        w = np.maximum(w, face * smoothstep(0.0055, 0.0035, np.hypot(x, z - zc)))
    brow = face * smoothstep(0.1, 0.085, ax)
    d3 = np.hypot(x, z - 0.94)                        # third eye on the brow: ochre ring, white pupil
    o = brow * smoothstep(0.004, 0.0025, np.abs(d3 - 0.011))
    w = np.maximum(w, brow * smoothstep(0.0045, 0.003, d3))
    chest = smoothstep(-0.02, -0.06, y) * (ax < 0.12) * (z > 0.52) * (z < 0.72)
    r = np.hypot(x, z - 0.625)                        # spiral, three turns out from the breastbone
    th = (np.arctan2(z - 0.625, x) / (2 * np.pi)) % 1.0
    turn = (r - 0.006) / 0.0135 - th
    spiral = smoothstep(0.2, 0.08, np.abs(turn - np.round(turn))) * (turn > -0.5) * (turn < 2.6) * (r < 0.05)
    w = np.maximum(w, chest * spiral)
    arm = (np.abs(z - 0.72) < 0.045) * (ax > 0.3) * (ax < 0.46)
    for k in range(6):                                # dots along the top of each forearm
        w = np.maximum(w, arm * smoothstep(0.0065, 0.0045, np.hypot(ax - (0.315 + 0.026 * k), z - 0.735)))
    hands = smoothstep(0.5, 0.53, ax) * (np.abs(z - 0.715) < 0.1)
    col = _mix(col, ochre, 0.65 * hands + 0.9 * o)
    return _mix(col, white, 0.9 * w)


def chiefpaint(col, co):
    """Chief's bone-ash paint: pale skull mask with dark eye rings, jaw stripes, chest bands, arm rings."""
    x, y, z = co.T
    ax = np.abs(x)
    pale, dark = hexc('#d6cfb6'), hexc('#241a14')
    rn = np.linalg.norm((co - gob_body.HC) / gob_body.HR, axis=1)
    face = smoothstep(-0.05, -0.09, y) * smoothstep(1.2, 1.1, rn) * (z > 0.78)
    mask = face * smoothstep(0.885, 0.9, z) * smoothstep(0.985, 0.97, z) * smoothstep(0.1, 0.085, ax)
    eyes = np.zeros(len(co))
    for sg in (1, -1):
        d = np.linalg.norm(co - gob_body.LM['eye_L'] * np.array([sg, 1, 1]), axis=1)
        eyes = np.maximum(eyes, smoothstep(0.03, 0.022, d))
    for sx in (-0.03, -0.012, 0.012, 0.03):
        mask = np.maximum(mask, face * smoothstep(0.0055, 0.0035, np.abs(x - sx)) * (z > 0.79) * (z < 0.852))
    chest = smoothstep(-0.02, -0.06, y) * (ax < 0.115)
    for zc in (0.60, 0.645):
        mask = np.maximum(mask, chest * smoothstep(0.009, 0.006, np.abs(z - zc)))
    mask = np.maximum(mask, chest * smoothstep(0.007, 0.004, ax) * (z > 0.52) * (z < 0.7))
    arm = np.abs(z - 0.715) < 0.07
    for ring in (0.18, 0.21, 0.24):
        mask = np.maximum(mask, arm * smoothstep(0.0075, 0.0045, np.abs(ax - ring)))
    col = _mix(col, pale, 0.85 * mask)
    return _mix(col, dark, 0.9 * eyes)


def warpaint(col, co):
    """Red-ochre war paint: a band across the eyes, chin stripes, claw marks on the chest, upper-arm rings."""
    x, y, z = co.T
    ax = np.abs(x)
    ochre = hexc('#9a2e1b')
    front_head = smoothstep(-0.06, -0.10, y) * (z > 0.78) * smoothstep(0.1, 0.085, ax)
    mask = front_head * smoothstep(0.019, 0.013, np.abs(z - 0.918)) * smoothstep(1.2, 1.1, np.linalg.norm((co - gob_body.HC) / gob_body.HR, axis=1))
    for sx in (-0.014, 0.0, 0.014):
        mask = np.maximum(mask, front_head * smoothstep(0.005, 0.003, np.abs(x - sx)) * (z > 0.795) * (z < 0.845))
    chest = smoothstep(-0.02, -0.06, y) * (z > 0.55) * (z < 0.72) * (ax < 0.12)
    d = x * 0.6 + (z - 0.64) * 0.8
    for off in (-0.04, 0.0, 0.04):
        mask = np.maximum(mask, chest * smoothstep(0.009, 0.005, np.abs(d - off)))
    arm = np.abs(z - 0.715) < 0.07
    for ring in (0.20, 0.235):
        mask = np.maximum(mask, arm * smoothstep(0.008, 0.005, np.abs(ax - ring)))
    return _mix(col, ochre, 0.85 * mask)


def bake_skin_variant(body, hi, eyes_hi, variant, image_name, size=1024):
    """Bake a painted variant of the skin into its own texture; the body keeps M_Goblin_Skin."""
    paint_sources(hi, eyes_hi, variant=variant)
    old = list(body.data.materials)
    path = bake(body, [hi, eyes_hi], image_name, size=size, material_name="M_Goblin_Skin_" + variant.title())
    paint_mouth(body, image_name)
    body.data.materials.clear()
    for m in old:
        body.data.materials.append(m)
    return path


def eye_colors(co):
    LM = gob_body.LM
    V = len(co)
    c = np.where(co[:, :1] > 0, LM['eye_L'], LM['eye_L'] * np.array([-1, 1, 1]))
    d = co - c
    d /= np.linalg.norm(d, axis=1)[:, None]
    ang = np.degrees(np.arccos(np.clip(-d[:, 1], -1, 1)))
    col = np.tile(PAL['sclera'], (V, 1))
    col = _mix(col, PAL['sclera'] * 0.6, smoothstep(60, 110, ang))
    iris = _mix(np.tile(PAL['iris'], (V, 1)), PAL['iris_rim'], smoothstep(22, 33, ang))
    col = _mix(col, iris, smoothstep(37, 33, ang))
    col = _mix(col, PAL['pupil'], smoothstep(15, 12, ang))
    hl = np.array([-0.35, -0.85, 0.40]) / np.linalg.norm([-0.35, -0.85, 0.40])
    col = _mix(col, np.ones(3), smoothstep(0.985, 0.992, d @ hl))
    return col


def shade(col, co, no, ao, cav, e):
    light = 0.80 + 0.30 * (no[:, 2] * 0.5 + 0.5)
    aot = 0.42 + 0.58 * ao
    col = col * (light * aot)[:, None] + ((1 - aot) * 0.12)[:, None] * np.array([0.25, 0.2, 0.4])
    c = np.clip(cav / 90.0, -1, 1)
    col = col * (1 - 0.45 * np.clip(c, 0, 1))[:, None]
    col = col + (0.10 * np.clip(-c, 0, 1))[:, None] * np.array([1.0, 1.0, 0.75])
    return np.clip(col, 0, 1)


def write_color(me, name, col_srgb):
    if name in me.color_attributes:
        me.color_attributes.remove(me.color_attributes[name])
    att = me.color_attributes.new(name, 'FLOAT_COLOR', 'POINT')
    lin = srgb_to_lin(col_srgb)
    rgba = np.hstack([lin, np.ones((len(lin), 1))]).ravel()
    att.data.foreach_set('color', rgba)


def paint_sources(hi, eyes_hi, variant=None):
    co, no, e = mesh_arrays(hi.data)
    ao = ray_ao(hi, co, no)
    ao = smooth_vals(ao, e, len(co), it=2)
    cav = smooth_vals(curvature(co, no, e), e, len(co), it=2)
    col = shade(body_colors(co, no, e, variant), co, no, ao, cav, e)
    write_color(hi.data, "paint", col)
    eco, eno, ee = mesh_arrays(eyes_hi.data)
    ecol = shade(eye_colors(eco), eco, eno, np.ones(len(eco)), np.zeros(len(eco)), ee)
    write_color(eyes_hi.data, "paint", ecol)
    return {"hi_verts": len(co), "ao_mean": float(ao.mean())}


def bake_material():
    m = bpy.data.materials.get("M_Bake_Paint") or bpy.data.materials.new("M_Bake_Paint")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    em = nt.nodes.new('ShaderNodeEmission')
    att = nt.nodes.new('ShaderNodeAttribute')
    att.attribute_name = "paint"
    tc = nt.nodes.new('ShaderNodeTexCoord')
    nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = 90.0
    nz.inputs['Detail'].default_value = 3.0
    mr = nt.nodes.new('ShaderNodeMapRange')
    mr.inputs['To Min'].default_value = 0.92
    mr.inputs['To Max'].default_value = 1.08
    mul = nt.nodes.new('ShaderNodeMix')
    mul.data_type = 'RGBA'
    mul.blend_type = 'MULTIPLY'
    mul.inputs['Factor'].default_value = 1.0
    nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
    nt.links.new(nz.outputs['Fac'], mr.inputs['Value'])
    nt.links.new(att.outputs['Color'], mul.inputs['A'])
    nt.links.new(mr.outputs['Result'], mul.inputs['B'])
    nt.links.new(mul.outputs['Result'], em.inputs['Color'])
    nt.links.new(em.outputs['Emission'], out.inputs['Surface'])
    return m


def game_material(name, image):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.inputs['Roughness'].default_value = 0.85
    tex = nt.nodes.new('ShaderNodeTexImage')
    tex.image = image
    nt.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    nt.nodes.active = tex
    return m


def unwrap(ob, head_scale=1.7, margin=0.004):
    vl = bpy.context.view_layer
    for o in bpy.context.selected_objects:
        o.select_set(False)
    vl.objects.active = ob
    ob.select_set(True)
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=margin, area_weight=0.0,
                             correct_aspect=True, scale_to_bounds=False)
    bm = bmesh.from_edit_mesh(ob.data)
    uv = bm.loops.layers.uv.active
    for f in bm.faces:           # more texels for the face, ears and eyes
        c = f.calc_center_median()
        if c.z > 0.80 and abs(c.x) < 0.32:
            for l in f.loops:
                l[uv].uv *= head_scale
    bmesh.update_edit_mesh(ob.data)
    bpy.ops.uv.select_all(action='SELECT')
    bpy.ops.uv.pack_islands(margin=margin, rotate=True)
    bpy.ops.object.mode_set(mode='OBJECT')


def bake(low, sources, image_name, size=1024, material_name="M_Goblin_Skin"):
    os.makedirs(TEX_DIR, exist_ok=True)
    img = bpy.data.images.get(image_name)
    if img is None or img.size[0] != size:
        if img is not None:
            bpy.data.images.remove(img)
        img = bpy.data.images.new(image_name, size, size, alpha=False)
    img.colorspace_settings.name = 'sRGB'
    gm = game_material(material_name, img)
    low.data.materials.clear()
    low.data.materials.append(gm)
    bm_mat = bake_material()
    for s in sources:
        s.data.materials.clear()
        s.data.materials.append(bm_mat)
    scn = bpy.context.scene
    prev = scn.render.engine
    scn.render.engine = 'CYCLES'
    scn.cycles.samples = 4
    scn.cycles.device = 'CPU'
    hidden = {}
    for s in sources:
        hidden[s.name] = (s.hide_get(), s.hide_viewport, s.hide_render)
        s.hide_viewport = False
        s.hide_set(False)
        s.hide_render = False
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for s in sources:
        s.select_set(True)
    low.select_set(True)
    bpy.context.view_layer.objects.active = low
    bpy.ops.object.bake(type='EMIT', use_selected_to_active=True, cage_extrusion=0.008,
                        max_ray_distance=0.025, margin=8, use_clear=True)
    for s in sources:
        h, hv, hr = hidden[s.name]
        s.select_set(False)
        s.hide_set(h)
        s.hide_viewport = hv
        s.hide_render = hr
    scn.render.engine = prev
    path = os.path.join(TEX_DIR, image_name + ".png")
    img.filepath_raw = path
    img.file_format = 'PNG'
    img.save()
    return path


# ----------------------------------------------------------------------------------------- mouth (per texel)
def bake_positions(low, size):
    """Object-space position of every texel of the low mesh (float image, +1 offset so all values are > 0)."""
    img = bpy.data.images.get("_GOB_Pos")
    if img is not None:
        bpy.data.images.remove(img)
    img = bpy.data.images.new("_GOB_Pos", size, size, alpha=True, float_buffer=True)
    img.colorspace_settings.name = 'Non-Color'
    m = bpy.data.materials.get("_GOB_PosMat") or bpy.data.materials.new("_GOB_PosMat")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    em = nt.nodes.new('ShaderNodeEmission')
    tc = nt.nodes.new('ShaderNodeTexCoord')
    add = nt.nodes.new('ShaderNodeVectorMath')
    add.operation = 'ADD'
    add.inputs[1].default_value = (1, 1, 1)
    nt.links.new(tc.outputs['Object'], add.inputs[0])
    nt.links.new(add.outputs['Vector'], em.inputs['Color'])
    nt.links.new(em.outputs['Emission'], out.inputs['Surface'])
    tex = nt.nodes.new('ShaderNodeTexImage')
    tex.image = img
    nt.nodes.active = tex
    old = list(low.data.materials)
    low.data.materials.clear()
    low.data.materials.append(m)
    scn = bpy.context.scene
    prev = scn.render.engine
    scn.render.engine = 'CYCLES'
    scn.cycles.samples = 1
    for o in bpy.context.selected_objects:
        o.select_set(False)
    low.select_set(True)
    bpy.context.view_layer.objects.active = low
    bpy.ops.object.bake(type='EMIT', margin=8, use_clear=True)
    scn.render.engine = prev
    low.data.materials.clear()
    for mm in old:
        low.data.materials.append(mm)
    buf = np.empty(size * size * 4, dtype=np.float32)
    img.pixels.foreach_get(buf)
    buf = buf.reshape(size, size, 4)[..., :3].astype(float)
    valid = buf.sum(-1) > 0.5
    return buf - 1.0, valid


def paint_mouth(low, image_name="T_Goblin_Skin"):
    """Wide grin painted per texel: dark mouth band, upper teeth, two underbite fangs over the upper lip."""
    img = bpy.data.images[image_name]
    size = img.size[0]
    P, valid = bake_positions(low, size)
    HC, HR = gob_body.HC, gob_body.HR
    q = (P - HC) / HR
    rn = np.linalg.norm(q, axis=-1) + 1e-9
    nz0 = q[..., 2] / rn
    q[..., 0] /= (1 - 0.24 * smoothstep(-0.1, -0.9, nz0))
    rn = np.linalg.norm(q, axis=-1) + 1e-9
    nq = q / rn[..., None]
    s, d = nq[..., 0], nq[..., 2] - gob_body.mouth_line(nq[..., 0])
    W = gob_body.MOUTH_W
    face = valid & (nq[..., 1] < -0.4) & (rn > 0.8) & (rn < 1.12) & (np.abs(s) < W + 0.12)
    e = 0.004
    h = 0.030 * np.sqrt(np.clip(1 - (s / W) ** 2, 0, 1))
    ad = np.abs(d)

    buf = np.empty(size * size * 4, dtype=np.float32)
    img.pixels.foreach_get(buf)
    col = buf.reshape(size, size, 4)[..., :3].astype(float)
    base = col.copy()

    def mix(c, target, t):
        t = np.clip(t, 0, 1) * face
        return c * (1 - t[..., None]) + np.asarray(target) * t[..., None]

    # lips: darker upper lip shadow, lighter lower lip, crease continuing past the corners
    col = mix(col, base * 0.62, 0.8 * smoothstep(h + 0.045, h + 0.004, d) * (d > 0) * (np.abs(s) < W))
    col = mix(col, np.minimum(base * 1.18, 1), 0.6 * smoothstep(-h - 0.05, -h - 0.012, d) * smoothstep(-h - 0.004, -h - 0.02, d))
    crease = smoothstep(0.010, 0.003, ad) * smoothstep(W + 0.10, W + 0.02, np.abs(s)) * (np.abs(s) > W - 0.05)
    col = mix(col, hexc('#2a1510'), 0.8 * crease)
    # mouth opening with a dark rim
    col = mix(col, hexc('#1c0908'), smoothstep(h + e + 0.006, h + 0.004, ad) * (h > 0.002))
    col = mix(col, hexc('#3a1210'), smoothstep(h + e, h - e, ad) * (h > 0.004))
    # upper teeth hang from the top edge of the opening
    p = 0.085
    t = np.mod(s / p + 0.5, 1.0)
    tri = 1 - np.abs(2 * t - 1)
    tooth = smoothstep(h - 1.45 * h * tri - e, h - 1.45 * h * tri + e, d) * smoothstep(h + e, h - e, ad) * (np.abs(s) < 0.40)
    col = mix(col, hexc('#e2d4a8') * (0.8 + 0.2 * tri[..., None]), tooth)
    # two lower fangs poking up over the upper lip
    for s0 in (-0.25, 0.25):
        tip = 0.030 + 0.042
        span = np.clip((tip - d) / (tip + 0.030), 0, 1)
        half = 0.034 * span
        fang = smoothstep(half + 0.006, half - 0.002, np.abs(s - s0)) * (d > -0.030) * (d < tip)
        edge = smoothstep(half + 0.012, half + 0.004, np.abs(s - s0)) * (d > -0.030) * (d < tip + 0.006) * (1 - fang)
        col = mix(col, hexc('#241008'), 0.9 * edge)
        col = mix(col, hexc('#ece0b8') * (0.82 + 0.18 * (1 - span[..., None])), fang)
    out = buf.reshape(size, size, 4).copy()
    out[..., :3] = col
    img.pixels.foreach_set(out.ravel().astype(np.float32))
    img.save()
    return int(face.sum())
