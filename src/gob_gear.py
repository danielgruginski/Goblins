"""Generic goblin gear.

Outfits (skinned, share the goblin armature): Outfit_Loincloth, Outfit_Harness, Outfit_Wraps.
Props (rigid, parented to socket bones, modelled in socket space):
    Prop_Spear -> Socket_RightHand, Prop_Shield -> Socket_LeftForearm, Prop_Helmet -> Socket_Helm,
    Prop_Pauldron -> Socket_LeftShoulder, Prop_Pouch -> Socket_RightHip, Prop_Knife -> Socket_LeftHip.
All gear shares one baked atlas (T_Goblin_Gear) and one material (M_Goblin_Gear).
"""
import bpy, bmesh, math, os
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
from gob_common import (ROOT, loft, ellipsoid, cone, get_coll, remove_obj, spline, smoothstep, uv_layer, set_uvs,
                        grid_faces, fill_gutters)
import gob_body

TEX_DIR = os.path.join(ROOT, "textures")

# Game budget (colony camera ~40 m, no LODs): segment counts are scaled down here in one place.
SEG_SCALE = 0.6


def S(n):
    return max(5, int(round(n * SEG_SCALE)))


def SR(n):
    return max(4, int(round(n * SEG_SCALE)))


def PS(n):
    return max(1, n // 2)
RIG = "GoblinRig"


# ----------------------------------------------------------------------------------------- materials
def _hex(h, a=1.0):
    h = h.lstrip('#')
    c = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return (*c, a)


def paint_group():
    g = bpy.data.node_groups.get("GOB_PaintLight")
    if g is not None:
        return g
    g = bpy.data.node_groups.new("GOB_PaintLight", 'ShaderNodeTree')
    g.interface.new_socket("Color", in_out='INPUT', socket_type='NodeSocketColor')
    g.interface.new_socket("Edge", in_out='INPUT', socket_type='NodeSocketFloat')
    g.interface.new_socket("Color", in_out='OUTPUT', socket_type='NodeSocketColor')
    N, L = g.nodes, g.links
    gi, go = N.new('NodeGroupInput'), N.new('NodeGroupOutput')
    ao = N.new('ShaderNodeAmbientOcclusion')
    ao.samples = 12
    ao.inputs['Distance'].default_value = 0.05
    bev = N.new('ShaderNodeBevel')
    bev.samples = 8
    bev.inputs['Radius'].default_value = 0.0035
    geo = N.new('ShaderNodeNewGeometry')
    dot = N.new('ShaderNodeVectorMath')
    dot.operation = 'DOT_PRODUCT'
    L.new(bev.outputs['Normal'], dot.inputs[0])
    L.new(geo.outputs['Normal'], dot.inputs[1])
    edge = N.new('ShaderNodeMapRange')
    edge.inputs['From Min'].default_value = 0.999
    edge.inputs['From Max'].default_value = 0.93
    L.new(dot.outputs['Value'], edge.inputs['Value'])
    sep = N.new('ShaderNodeSeparateXYZ')
    L.new(geo.outputs['Normal'], sep.inputs[0])
    top = N.new('ShaderNodeMapRange')
    top.inputs['From Min'].default_value = -1
    top.inputs['To Min'].default_value = 0.80
    top.inputs['To Max'].default_value = 1.10
    L.new(sep.outputs['Z'], top.inputs['Value'])
    aot = N.new('ShaderNodeMapRange')
    aot.inputs['To Min'].default_value = 0.45
    L.new(ao.outputs['AO'], aot.inputs['Value'])
    m1 = N.new('ShaderNodeMix')
    m1.data_type, m1.blend_type = 'RGBA', 'MULTIPLY'
    m1.inputs['Factor'].default_value = 1
    L.new(gi.outputs['Color'], m1.inputs['A'])
    L.new(aot.outputs['Result'], m1.inputs['B'])
    m2 = N.new('ShaderNodeMix')
    m2.data_type, m2.blend_type = 'RGBA', 'MULTIPLY'
    m2.inputs['Factor'].default_value = 1
    L.new(m1.outputs['Result'], m2.inputs['A'])
    L.new(top.outputs['Result'], m2.inputs['B'])
    ef = N.new('ShaderNodeMath')
    ef.operation = 'MULTIPLY'
    L.new(edge.outputs['Result'], ef.inputs[0])
    L.new(gi.outputs['Edge'], ef.inputs[1])
    m3 = N.new('ShaderNodeMix')
    m3.data_type, m3.blend_type = 'RGBA', 'ADD'
    m3.inputs['B'].default_value = (0.30, 0.28, 0.22, 1)
    L.new(ef.outputs['Value'], m3.inputs['Factor'])
    L.new(m2.outputs['Result'], m3.inputs['A'])
    L.new(m3.outputs['Result'], go.inputs['Color'])
    return g


def _src_material(name, c_dark, c_light, scale=(30, 30, 30), detail=4, stain=None, edge=0.5, stripes=None):
    """Painted source material: two-tone noise (stretched by `scale`), optional stains/stripes, AO + edges."""
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    N, L = nt.nodes, nt.links
    out = N.new('ShaderNodeOutputMaterial')
    em = N.new('ShaderNodeEmission')
    tc = N.new('ShaderNodeTexCoord')
    mp = N.new('ShaderNodeMapping')
    mp.inputs['Scale'].default_value = scale
    L.new(tc.outputs['Object'], mp.inputs['Vector'])
    nz = N.new('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = 1.0
    nz.inputs['Detail'].default_value = detail
    nz.inputs['Roughness'].default_value = 0.6
    L.new(mp.outputs['Vector'], nz.inputs['Vector'])
    ramp = N.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = _hex(c_dark)
    ramp.color_ramp.elements[1].position = 0.65
    ramp.color_ramp.elements[1].color = _hex(c_light)
    L.new(nz.outputs['Fac'], ramp.inputs['Fac'])
    col = ramp.outputs['Color']
    if stripes is not None:           # rope twist / weave bands along object axis
        wv = N.new('ShaderNodeTexWave')
        wv.wave_type = 'BANDS'
        wv.bands_direction = stripes[0]
        wv.inputs['Scale'].default_value = stripes[1]
        wv.inputs['Distortion'].default_value = 1.5
        L.new(tc.outputs['Object'], wv.inputs['Vector'])
        mr = N.new('ShaderNodeMapRange')
        mr.inputs['To Min'].default_value = 0.78
        L.new(wv.outputs['Fac'], mr.inputs['Value'])
        mx = N.new('ShaderNodeMix')
        mx.data_type, mx.blend_type = 'RGBA', 'MULTIPLY'
        mx.inputs['Factor'].default_value = 1
        L.new(col, mx.inputs['A'])
        L.new(mr.outputs['Result'], mx.inputs['B'])
        col = mx.outputs['Result']
    if stain is not None:             # rust / dirt patches
        sn = N.new('ShaderNodeTexNoise')
        sn.inputs['Scale'].default_value = stain[1]
        sn.inputs['Detail'].default_value = 6
        L.new(tc.outputs['Object'], sn.inputs['Vector'])
        sr = N.new('ShaderNodeMapRange')
        sr.inputs['From Min'].default_value = stain[2]
        sr.inputs['From Max'].default_value = stain[2] + 0.08
        L.new(sn.outputs['Fac'], sr.inputs['Value'])
        mx = N.new('ShaderNodeMix')
        mx.data_type = 'RGBA'
        mx.inputs['B'].default_value = _hex(stain[0])
        L.new(sr.outputs['Result'], mx.inputs['Factor'])
        L.new(col, mx.inputs['A'])
        col = mx.outputs['Result']
    grp = N.new('ShaderNodeGroup')
    grp.node_tree = paint_group()
    grp.inputs['Edge'].default_value = edge
    L.new(col, grp.inputs['Color'])
    L.new(grp.outputs['Color'], em.inputs['Color'])
    L.new(em.outputs['Emission'], out.inputs['Surface'])
    return m


def build_materials():
    return {
        'wood': _src_material("GS_Wood", '#553823', '#8a6238', scale=(45, 3, 45), stain=('#3e2918', 6, 0.62), edge=0.6),
        'wood_plank': _src_material("GS_WoodPlank", '#5e4128', '#93693c', scale=(40, 2.5, 40), stain=('#3b2616', 5, 0.6), edge=0.8),
        'iron': _src_material("GS_Iron", '#3d3f44', '#5d6066', scale=(25, 25, 25), stain=('#7b4326', 12, 0.56), edge=1.4),
        'leather': _src_material("GS_Leather", '#4d301b', '#7a5132', scale=(35, 35, 35), stain=('#35200f', 9, 0.6), edge=0.7),
        'leather_dark': _src_material("GS_LeatherDark", '#2f1f14', '#4d3322', scale=(35, 35, 35), edge=0.6),
        'cloth': _src_material("GS_Cloth", '#5c4c30', '#8a7650', scale=(60, 60, 60), stain=('#3e3220', 7, 0.6), edge=0.3,
                               stripes=('X', 260)),
        'linen': _src_material("GS_Linen", '#7d7053', '#ab9d7a', scale=(50, 50, 50), stain=('#5e5238', 8, 0.58), edge=0.3,
                               stripes=('Z', 220)),
        'rope': _src_material("GS_Rope", '#6e5a36', '#a38a5a', scale=(30, 30, 30), edge=0.4, stripes=('DIAGONAL', 180)),
        'bone': _src_material("GS_Bone", '#a59572', '#e0d4b0', scale=(20, 20, 20), stain=('#7d6a48', 7, 0.6), edge=0.5),
        'hair': _src_material("GS_Hair", '#1b1410', '#3d2e22', scale=(8, 8, 80), edge=0.3),
        'fur': _src_material("GS_Fur", '#2e241b', '#6e5c45', scale=(90, 90, 7), stain=('#241a12', 6, 0.62), edge=0.25,
                             stripes=('Z', 140)),
        'banner': _src_material("GS_Banner", '#5e1a12', '#9a3324', scale=(40, 40, 40), stain=('#3a120c', 8, 0.6), edge=0.3,
                                stripes=('Z', 200)),
        'brass': _src_material("GS_Brass", '#6b4e1c', '#b8913e', scale=(25, 25, 25), stain=('#3f4a2a', 10, 0.64), edge=1.2),
        'pot': _src_material("GS_Pot", '#2a2b2e', '#46484c', scale=(20, 20, 20), stain=('#5a3a24', 10, 0.6), edge=1.2),
    }


# ----------------------------------------------------------------------------------------- geometry helpers
class Builder:
    def __init__(self):
        self.bm = bmesh.new()
        self.mats = []

    def part(self, mat, fn, *a, **k):
        n0 = len(self.bm.faces)
        fn(self.bm, *a, **k)
        self.bm.faces.ensure_lookup_table()
        if mat not in self.mats:
            self.mats.append(mat)
        mi = self.mats.index(mat)
        for f in self.bm.faces[n0:]:
            f.material_index = mi


def _slab(bm, outline, frame, z0, z1):
    """Closed slab from a 2D outline between z0 and z1 in `frame` (a 4x4 taking outline (x, y, z) to object
    space). UVs: the two flat faces as drawn, the rim as one strip."""
    uvl = uv_layer(bm)
    top = [bm.verts.new(frame @ Vector((x, y, z1))) for x, y in outline]
    bot = [bm.verts.new(frame @ Vector((x, y, z0))) for x, y in outline]
    set_uvs(bm.faces.new(top), uvl, [(x, y) for x, y in outline])
    set_uvs(bm.faces.new(bot[::-1]), uvl, [(-x, y) for x, y in outline[::-1]])
    grid_faces(bm, [top, bot], close_j=True)


def prism(bm, pts, z0, z1):
    """Closed slab from a 2D outline (x, y) between z0 and z1 (flat blades, planks)."""
    _slab(bm, pts, Matrix.Identity(4), z0, z1)


def box(bm, center, size, rot=None):
    """Box with each face unwrapped flat at its true size (six islands)."""
    uvl = uv_layer(bm)
    R = rot.to_4x4() if rot is not None else Matrix.Identity(4)
    M = Matrix.Translation(Vector(center)) @ R
    V = {}
    for ix in (0, 1):
        for iy in (0, 1):
            for iz in (0, 1):
                V[ix, iy, iz] = bm.verts.new(M @ Vector(((ix - 0.5) * size[0], (iy - 0.5) * size[1], (iz - 0.5) * size[2])))
    for k in range(3):
        a, b = [x for x in range(3) if x != k]
        for s in (0, 1):
            quad, uvs = [], []
            for ca, cb in ((0, 0), (1, 0), (1, 1), (0, 1)):
                idx = [0, 0, 0]
                idx[k], idx[a], idx[b] = s, ca, cb
                quad.append(V[tuple(idx)])
                uvs.append((ca * size[a], cb * size[b]))
            set_uvs(bm.faces.new(quad), uvl, uvs)


def band(bm, P, N, W, width, thick):
    """Closed strap: centreline P, outward normals N, across-strap vectors W (all n x 3). One strip island."""
    n = len(P)
    secs = []
    for i in range(n):
        p, nn, w = Vector(P[i]), Vector(N[i]).normalized(), Vector(W[i]).normalized()
        c = [p - w * width / 2, p + w * width / 2, p + w * width / 2 + nn * thick, p - w * width / 2 + nn * thick]
        secs.append([bm.verts.new(v) for v in c])
    grid_faces(bm, secs, close_j=True, close_i=True)


def torus(bm, center, normal, R, r, seg=S(16), rseg=SR(6)):
    nrm = Vector(normal).normalized()
    t = nrm.orthogonal().normalized()
    b = nrm.cross(t)
    rings = []
    for i in range(seg):
        a = 2 * math.pi * i / seg
        d = t * math.cos(a) + b * math.sin(a)
        c = Vector(center) + d * R
        rings.append([bm.verts.new(c + d * r * math.cos(2 * math.pi * j / rseg) + nrm * r * math.sin(2 * math.pi * j / rseg))
                      for j in range(rseg)])
    grid_faces(bm, rings, close_j=True, close_i=True)


def closed_spline(pts, per_seg=PS(8)):
    c = np.asarray(pts, float)
    n = len(c)
    out = []
    for i in range(n):
        p0, p1, p2, p3 = c[(i - 1) % n], c[i], c[(i + 1) % n], c[(i + 2) % n]
        for k in range(per_seg):
            t = k / per_seg
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    return np.array(out)


class BodySurface:
    """Rest-pose body surface for projection and weight transfer."""

    def __init__(self):
        self.ob = bpy.data.objects["GoblinBody"]
        self.bm = bmesh.new()
        self.bm.from_mesh(self.ob.data)
        self.bm.faces.ensure_lookup_table()
        self.bm.verts.ensure_lookup_table()
        self.bvh = BVHTree.FromBMesh(self.bm)
        self.dl = self.bm.verts.layers.deform.active
        self.names = [g.name for g in self.ob.vertex_groups]

    def ray(self, o, d):
        hit = self.bvh.ray_cast(Vector(o), Vector(d).normalized(), 1.0)
        return None if hit[0] is None else (hit[0] - Vector(o)).length

    def nearest(self, p):
        loc, nrm, idx, dist = self.bvh.find_nearest(Vector(p))
        return loc, nrm, idx

    def weights_at(self, p):
        loc, nrm, idx = self.nearest(p)
        f = self.bm.faces[idx]
        ws = {}
        ds = [max((v.co - loc).length, 1e-6) for v in f.verts]
        inv = [1 / d for d in ds]
        s = sum(inv)
        for v, k in zip(f.verts, inv):
            for gi, w in v[self.dl].items():
                n = self.names[gi]
                ws[n] = ws.get(n, 0) + w * k / s
        return ws

    def free(self):
        self.bm.free()


def skin_to_rig(ob, surf, hips_blend=None, limit=4):
    rig = bpy.data.objects[RIG]
    ob.vertex_groups.clear()
    groups = {}
    for v in ob.data.vertices:
        ws = surf.weights_at(v.co)
        if hips_blend is not None:
            a = hips_blend(v.co)
            ws = {k: w * (1 - a) for k, w in ws.items()}
            ws["Hips"] = ws.get("Hips", 0) + a
        top = sorted(ws.items(), key=lambda kv: -kv[1])[:limit]
        tot = sum(w for _, w in top) or 1.0
        for n, w in top:
            if n not in groups:
                groups[n] = ob.vertex_groups.new(name=n)
            groups[n].add([v.index], w / tot, 'REPLACE')
    for m in [m for m in ob.modifiers if m.type == 'ARMATURE']:
        ob.modifiers.remove(m)
    mod = ob.modifiers.new("Armature", 'ARMATURE')
    mod.object = rig
    ob.parent = rig
    ob.matrix_parent_inverse = rig.matrix_world.inverted()


def _finish(name, b, coll, mats, solidify=0.0):
    remove_obj(name)
    me = bpy.data.meshes.new(name)
    ngons = [f for f in b.bm.faces if len(f.verts) > 4]      # concave outlines (notched blades): triangulate here
    if ngons:
        bmesh.ops.triangulate(b.bm, faces=ngons, quad_method='BEAUTY', ngon_method='BEAUTY')
    bmesh.ops.recalc_face_normals(b.bm, faces=b.bm.faces[:])
    b.bm.to_mesh(me)
    b.bm.free()
    ob = bpy.data.objects.new(name, me)
    coll.objects.link(ob)
    for mn in b.mats:
        me.materials.append(mats[mn])
    if solidify:
        mod = ob.modifiers.new("solid", 'SOLIDIFY')
        mod.thickness = solidify
        mod.offset = 0.0
        dg = bpy.context.evaluated_depsgraph_get()
        new = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
        ob.modifiers.remove(mod)
        ob.data = new
        bpy.data.meshes.remove(me)
        ob.data.name = name
    for p in ob.data.polygons:
        p.use_smooth = True
    return ob


# ----------------------------------------------------------------------------------------- outfits
def build_loincloth(surf, mats, coll, seed=4):
    rng = np.random.default_rng(seed)
    remove_obj("Outfit_Loincloth")
    J, R = 24, 3
    th = np.linspace(0, 2 * math.pi, J, endpoint=False)
    D = np.stack([np.sin(th), -np.cos(th), np.zeros(J)], 1)       # theta = 0 faces front (-Y)

    def body_r(z):
        return np.array([surf.ray((0, 0.0, z), d) or 0.12 for d in D])

    r_ref = body_r(0.405)
    ang = np.abs(np.angle(np.exp(1j * th)))                       # 0 front .. pi back
    front = smoothstep(0.55, 0.35, ang)
    back = smoothstep(math.pi - 0.6, math.pi - 0.4, ang)
    hem = 0.378 - 0.075 * front - 0.060 * back
    hem = hem + np.where(np.arange(J) % 2 == 1, 0.022, 0.0) + rng.uniform(0, 0.014, J)   # tatters
    z_top = 0.478
    b = Builder()
    zs = np.array([[z_top + (hem[j] - z_top) * (i / R) for j in range(J)] for i in range(R + 1)])
    # radii: ray-cast where the torso exists, below that reuse the lowest ring and flare out
    grid = []
    for i in range(R + 1):
        ring = []
        for j in range(J):
            z = zs[i, j]
            if z >= 0.405:
                r = surf.ray((0, 0, z), D[j]) or r_ref[j]
            else:
                r = r_ref[j]
            r = r + 0.008 + max(0.0, 0.43 - z) * 0.32
            ring.append(b.bm.verts.new(Vector((D[j][0] * r, D[j][1] * r, z))))
        grid.append(ring)
    if 'cloth' not in b.mats:
        b.mats.append('cloth')
    for f in grid_faces(b.bm, grid, close_j=True)[0]:
        f.material_index = 0
    skirt = _finish("Outfit_Loincloth_Skirt", b, coll, mats, solidify=0.004)

    # belt under the gut + iron buckle
    b = Builder()
    zb = 0.482
    rb = body_r(zb)
    P = D * (rb + 0.004)[:, None] + np.array([0, 0, zb])
    Nn = D
    W = np.tile([0, 0, 1.0], (J, 1))
    b.part('leather_dark', band, P, Nn, W, 0.034, 0.008)
    yb = -(rb[0] + 0.012)
    for c, s in (((0, yb, zb + 0.019), (0.05, 0.008, 0.008)), ((0, yb, zb - 0.019), (0.05, 0.008, 0.008)),
                 ((0.021, yb, zb), (0.008, 0.008, 0.046)), ((-0.021, yb, zb), (0.008, 0.008, 0.046)),
                 ((0.0, yb - 0.002, zb), (0.006, 0.006, 0.036))):
        b.part('iron', box, c, s)
    belt = _finish("Outfit_Loincloth_Belt", b, coll, mats)
    # one object for the outfit piece
    skirt_me, belt_me = skirt.data, belt.data
    for o in bpy.context.selected_objects:
        o.select_set(False)
    belt.select_set(True)
    skirt.select_set(True)
    bpy.context.view_layer.objects.active = skirt
    bpy.ops.object.join()
    skirt.name = skirt.data.name = "Outfit_Loincloth"
    remove_obj("Outfit_Loincloth_Belt")

    def hips(co):
        centre = smoothstep(0.07, 0.02, abs(co.x))
        low = smoothstep(0.43, 0.33, co.z)
        return max(0.35 * low, 0.75 * centre * low)
    skin_to_rig(skirt, surf, hips_blend=hips)
    return skirt


def build_harness(surf, mats, coll):
    ctrl = [(0.080, -0.045, 0.748), (0.030, -0.080, 0.680), (0.0, -0.090, 0.620), (-0.060, -0.100, 0.555),
            (-0.112, -0.050, 0.505), (-0.130, 0.020, 0.500), (-0.095, 0.078, 0.520), (-0.040, 0.088, 0.575),
            (0.0, 0.092, 0.620), (0.045, 0.090, 0.680), (0.080, 0.060, 0.740), (0.092, 0.005, 0.768)]
    b = Builder()
    for side, lift in ((1, 0.006), (-1, 0.010)):
        pts = closed_spline([(side * x, y, z) for x, y, z in ctrl], per_seg=PS(8))
        for _ in range(2):                 # project, relax, project
            proj = []
            for p in pts:
                loc, nrm, _ = surf.nearest(p)
                proj.append(np.array(loc))
            pts = np.array(proj)
            pts = 0.5 * pts + 0.25 * (np.roll(pts, 1, 0) + np.roll(pts, -1, 0))
        P, N = [], []
        for p in pts:
            loc, nrm, _ = surf.nearest(p)
            P.append(np.array(loc) + np.array(nrm) * lift)
            N.append(np.array(nrm))
        P, N = np.array(P), np.array(N)
        T = np.roll(P, -1, 0) - np.roll(P, 1, 0)
        W = np.cross(T, N)
        b.part('leather', band, P, N, W, 0.022, 0.005)
    for y in (-1, 1):                      # iron rings where the straps cross
        loc, nrm, _ = surf.nearest((0, y * 0.09, 0.62))
        b.part('iron', torus, Vector(loc) + nrm * 0.016, nrm, 0.016, 0.0045)
    ob = _finish("Outfit_Harness", b, coll, mats)
    skin_to_rig(ob, surf)
    return ob


def build_wraps(surf, mats, coll):
    b = Builder()
    limbs = [((0.335, 0.009, 0.715), (0.475, 0.003, 0.715), 3), ((0.090, -0.008, 0.212), (0.095, 0.0, 0.092), 3)]
    for side in (1, -1):
        for a, c, nb in limbs:
            a = np.array(a) * [side, 1, 1]
            c = np.array(c) * [side, 1, 1]
            ax = (c - a) / np.linalg.norm(c - a)
            t0 = Vector(ax).orthogonal().normalized()
            t1 = Vector(ax).cross(t0)
            for k in range(nb):
                ctr = a + (c - a) * (0.08 + 0.84 * k / (nb - 1))
                tilt = Matrix.Rotation(math.radians(13 if k % 2 else -9), 3, t0)
                n = 10
                P, N, W = [], [], []
                for i in range(n):
                    ang = 2 * math.pi * i / n
                    d = (t0 * math.cos(ang) + t1 * math.sin(ang))
                    d = tilt @ d
                    r = surf.ray(ctr, d) or 0.03
                    P.append(np.array(ctr) + np.array(d) * (r + 0.0025))
                    N.append(np.array(d))
                    W.append(np.array(tilt @ Vector(ax)))
                b.part('linen', band, np.array(P), np.array(N), np.array(W), 0.030, 0.0035)
    ob = _finish("Outfit_Wraps", b, coll, mats)
    skin_to_rig(ob, surf)
    return ob


# ----------------------------------------------------------------------------------------- props
def prop_spear():
    b = Builder()
    rng = np.random.default_rng(7)
    ys = np.linspace(-0.40, 0.62, 6)
    rows = [(0.0025 * math.sin(y * 9) + rng.uniform(-0.001, 0.001), y, 0.002 * math.cos(y * 7),
             0.0125 + rng.uniform(-0.0008, 0.0008), 0.0125, 0.0125) for y in ys]
    b.part('wood', loft, rows, up=(0, 0, 1), seg=S(10), per_seg=PS(2), cap0=0.3, cap1=0.3)
    b.part('leather', loft, [(0, y, 0, 0.0152, 0.0152, 0.0152) for y in (-0.09, 0.0, 0.11)], up=(0, 0, 1), seg=S(10),
           per_seg=PS(2), cap0=0.2, cap1=0.2)
    for y in (-0.06, 0.06):
        b.part('leather_dark', loft, [(0, y - 0.006, 0, 0.0166, 0.0166, 0.0166), (0, y + 0.006, 0, 0.0166, 0.0166, 0.0166)],
               up=(0, 0, 1), seg=S(10), per_seg=PS(1), cap0=0.2, cap1=0.2)
    b.part('rope', loft, [(0, y, 0, 0.0165, 0.0165, 0.0165) for y in (0.575, 0.60, 0.625)], up=(0, 0, 1), seg=S(10),
           per_seg=PS(2), cap0=0.3, cap1=0.3)
    blade = [(0, 0.60, 0, 0.012, 0.011, 0.011), (0, 0.635, 0, 0.015, 0.010, 0.010), (0, 0.665, 0, 0.032, 0.007, 0.007),
             (0, 0.715, 0, 0.043, 0.006, 0.006), (0, 0.775, 0, 0.030, 0.005, 0.005), (0, 0.845, 0, 0.008, 0.0035, 0.0035)]
    b.part('iron', loft, blade, up=(0, 0, 1), seg=S(12), per_seg=PS(3), cap0=0.3, cap1=1.4)
    b.part('iron', cone, (0, -0.395, 0), (0, -0.44, 0), 0.0145, 0.004, seg=S(10))
    b.part('cloth', box, (0.0, 0.56, -0.045), (0.004, 0.022, 0.08), Matrix.Rotation(0.25, 3, 'Y'))   # rag
    return b, 'socket'


def prop_shield():
    b = Builder()
    R, T = 0.19, 0.018
    rng = np.random.default_rng(11)
    xs = np.linspace(-R, R, 6)
    for k in range(5):
        x0, x1 = xs[k] + 0.0015, xs[k + 1] - 0.0015
        zoff = 0.022 + rng.uniform(-0.0015, 0.0015)
        cut = 0.03 if k == 3 else 0.0            # one chipped plank
        pts = []
        for x in np.linspace(x0, x1, 3):
            pts.append((x, -math.sqrt(max(R * R - x * x, 0)) * 0.985))
        for x in np.linspace(x1, x0, 3):
            y = math.sqrt(max(R * R - x * x, 0)) * 0.985
            pts.append((x, y - cut * smoothstep(x0, x1, x)))
        b.part('wood_plank', prism, pts, zoff - T / 2, zoff + T / 2)
    b.part('iron', torus, (0, 0, 0.022), (0, 0, 1), R - 0.002, 0.009, seg=S(36), rseg=SR(6))
    b.part('iron', ellipsoid, Vector((0, 0, 0.033)), (0.052, 0.052, 0.034), None, 12, 6)
    b.part('iron', torus, (0, 0, 0.034), (0, 0, 1), 0.052, 0.006, seg=S(24), rseg=SR(5))
    for a in range(6):
        ang = 2 * math.pi * a / 6 + 0.2
        b.part('iron', ellipsoid, Vector((math.cos(ang) * (R - 0.022), math.sin(ang) * (R - 0.022), 0.032)),
               (0.0065, 0.0065, 0.004), None, 6, 3)
    for y in (-0.05, 0.05):                       # arm straps on the back
        b.part('leather', box, (0, y, 0.006), (0.12, 0.022, 0.006))
    return b, 'socket'


def head_pt(theta, phi, off):
    """Point on the sculpted head (polar angle from the crown, azimuth), pushed out by `off` metres."""
    n = np.array([math.sin(theta) * math.cos(phi), math.sin(theta) * math.sin(phi), math.cos(theta)])
    return gob_body.head_sculpt(n)[0] + n * off


def head_shell(b, mat, zrim, off_in, off_out, U=16, K=4):
    """Closed cap following the skull between off_in and off_out, cut where it meets zrim(y). World space.
    Returns the outer rim ring (U x 3) and the crown point."""
    rows_o, rows_i = [], []
    for kk in range(K + 1):
        ro, ri = [], []
        for u in range(U):
            phi = 2 * math.pi * u / U
            lo, hi = 0.0, math.pi * 0.75
            for _ in range(30):                 # polar angle where the outer surface meets the rim
                mid = (lo + hi) / 2
                q = head_pt(mid, phi, off_out)
                if q[2] > zrim(q[1]):
                    lo = mid
                else:
                    hi = mid
            th = lo * (kk / K) ** 0.9
            ro.append(head_pt(th, phi, off_out))
            ri.append(head_pt(th, phi, off_in))
        rows_o.append(ro)
        rows_i.append(ri)
    bm = b.bm
    uvl = uv_layer(bm)
    n0 = len(bm.faces)
    VO = [[bm.verts.new(Vector(p)) for p in r] for r in rows_o[1:]]
    VI = [[bm.verts.new(Vector(p)) for p in r] for r in rows_i[1:]]
    po = bm.verts.new(Vector(rows_o[0][0]))
    pi = bm.verts.new(Vector(rows_i[0][0]))
    for V, pole in ((VO, po), (VI, pi)):              # outside and inside: crown fan + rows down to the rim
        _, Uc, vv = grid_faces(bm, V, close_j=True)
        top = vv[0] - (V[0][0].co - pole.co).length
        for u in range(U):
            f = bm.faces.new((pole, V[0][u], V[0][(u + 1) % U]))
            set_uvs(f, uvl, ((0.0, top), (Uc[0][u], vv[0]), (Uc[0][u + 1], vv[0])))
    grid_faces(bm, [VO[-1], VI[-1]], close_j=True)    # the rim
    bm.faces.ensure_lookup_table()
    if mat not in b.mats:
        b.mats.append(mat)
    for f in bm.faces[n0:]:
        f.material_index = b.mats.index(mat)
    return np.array(rows_o[-1]), rows_o[0][0]


def prop_helmet():
    """Iron kettle cap offset from the head surface, rim band, top spike and two bone horns (world space)."""
    b = Builder()
    rim, top = head_shell(b, 'iron', lambda y: 0.952 - 0.62 * max(0.0, y), 0.007, 0.017)
    ctr = rim.mean(0)
    Nn = rim - ctr
    Nn[:, 2] = 0
    Nn /= np.linalg.norm(Nn, axis=1)[:, None]
    T = np.roll(rim, -1, 0) - np.roll(rim, 1, 0)
    W = np.cross(Nn, T)
    b.part('iron', band, rim + [0, 0, 0.008] - Nn * 0.002, Nn, W, 0.02, 0.006)
    for u in range(0, len(rim), 4):
        b.part('iron', ellipsoid, Vector(rim[u] + [0, 0, 0.008]) + Vector(Nn[u]) * 0.006, (0.005, 0.005, 0.005), None, 6, 3)
    b.part('iron', cone, Vector(top) - Vector((0, 0, 0.01)), Vector(top) + Vector((0, 0.005, 0.07)), 0.018, 0.0, seg=S(10))
    for sg in (1, -1):
        horn = [(sg * 0.090, -0.012, 0.972, 0.016, 0.016, 0.016), (sg * 0.135, -0.022, 0.992, 0.0125, 0.0125, 0.0125),
                (sg * 0.168, -0.040, 1.025, 0.009, 0.009, 0.009), (sg * 0.180, -0.062, 1.068, 0.0045, 0.0045, 0.0045)]
        b.part('bone', loft, horn, up=(0, -1, 0), seg=S(10), per_seg=PS(3), cap0=0.3, cap1=1.2)
        b.part('iron', torus, (sg * 0.100, -0.014, 0.976), (sg * 0.9, -0.2, 0.4), 0.017, 0.004, seg=S(14), rseg=SR(5))
    return b, 'world'


def prop_pauldron(spikes=True):
    b = Builder()
    c = np.array([0.135, 0.006, 0.713])            # shoulder joint
    for layer, (x0, x1, r, mat) in enumerate(((0.095, 0.205, 0.074, 'leather'), (0.105, 0.185, 0.083, 'iron'))):
        A, X = 6, 3
        grid = []
        for i in range(X + 1):
            x = x0 + (x1 - x0) * i / X
            dome = 1.0 - 0.28 * ((i / X) - 0.45) ** 2 * 4
            row = []
            for a in range(A + 1):
                ang = math.radians(-70 + 140 * a / A)          # around the arm axis, 0 = up
                rr = r * dome
                o = Vector((x, c[1] + math.sin(ang) * rr, c[2] + math.cos(ang) * rr))
                ins = Vector((x, c[1] + math.sin(ang) * (rr - 0.007), c[2] + math.cos(ang) * (rr - 0.007)))
                row.append((o, ins))
            grid.append(row)
        bm = b.bm
        n0 = len(bm.faces)
        VO = [[bm.verts.new(p[0]) for p in row] for row in grid]
        VI = [[bm.verts.new(p[1]) for p in row] for row in grid]
        grid_faces(bm, VO)                            # outer and inner plate
        grid_faces(bm, VI)
        for a in (0, A):                              # the four edges, each a thin strip
            grid_faces(bm, [[VO[i][a] for i in range(X + 1)], [VI[i][a] for i in range(X + 1)]])
        for i in (0, X):
            grid_faces(bm, [VO[i], VI[i]])
        bm.faces.ensure_lookup_table()
        if mat not in b.mats:
            b.mats.append(mat)
        for f in bm.faces[n0:]:
            f.material_index = b.mats.index(mat)
    for x, tilt in ((0.128, -0.15), (0.162, 0.0)) if spikes else ():
        base = Vector((x, c[1], c[2] + 0.083))
        b.part('iron', cone, base - Vector((0, 0, 0.004)), base + Vector((0.012 + tilt * 0.02, 0, 0.042)), 0.013, 0.0, seg=S(10))
    return b, 'world'


def _edge_to_knuckles(b):
    """Blades are drawn with the edge on -X; in the right-hand grip the knuckles face +X, so mirror."""
    bmesh.ops.scale(b.bm, vec=(-1, 1, 1), verts=b.bm.verts[:])


def _tilt(b, deg=-22):
    bmesh.ops.rotate(b.bm, verts=b.bm.verts[:], cent=(0, 0, 0), matrix=Matrix.Rotation(math.radians(deg), 3, 'X'))


def prop_pouch():
    b = Builder()
    body = [(0, -0.070, 0.020, 0.030, 0.019, 0.016), (0, -0.045, 0.024, 0.034, 0.023, 0.018),
            (0, -0.012, 0.022, 0.033, 0.021, 0.017), (0, 0.004, 0.019, 0.029, 0.017, 0.015)]
    b.part('leather', loft, body, up=(0, 0, 1), seg=S(14), per_seg=PS(3), cap0=0.5, cap1=0.3)
    flap = [(0, 0.012, 0.022, 0.035, 0.022, 0.006), (0, -0.012, 0.043, 0.034, 0.006, 0.004),
            (0, -0.032, 0.046, 0.030, 0.004, 0.003)]
    b.part('leather_dark', loft, flap, up=(0, 0, 1), seg=S(12), per_seg=PS(3), cap0=0.2, cap1=0.3)
    b.part('iron', ellipsoid, Vector((0, -0.030, 0.047)), (0.006, 0.006, 0.004), None, 6, 3)
    b.part('leather_dark', box, (0, 0.012, 0.006), (0.018, 0.035, 0.004))          # belt loop
    _tilt(b)
    return b, 'socket'


def prop_knife():
    b = Builder()
    rot = Matrix.Rotation(math.radians(18), 3, 'Z')
    def R(p):
        return tuple(rot @ Vector(p))
    sheath = [(0, 0.020, 0.012, 0.016, 0.009, 0.009), (0, -0.05, 0.012, 0.015, 0.008, 0.008),
              (0, -0.11, 0.012, 0.010, 0.006, 0.006), (0, -0.14, 0.012, 0.004, 0.004, 0.004)]
    b.part('leather', loft, [R(r[:3]) + r[3:] for r in sheath], up=(0, 0, 1), seg=S(10), per_seg=PS(2), cap0=0.4, cap1=0.8)
    b.part('iron', loft, [R((0, 0.018, 0.012)) + (0.019, 0.006, 0.006), R((0, 0.028, 0.012)) + (0.019, 0.006, 0.006)],
           up=(0, 0, 1), seg=S(8), per_seg=PS(1), cap0=0.2, cap1=0.2)
    b.part('wood', loft, [R((0, 0.028, 0.012)) + (0.0075, 0.0075, 0.0075), R((0, 0.085, 0.012)) + (0.0085, 0.0085, 0.0085)],
           up=(0, 0, 1), seg=S(8), per_seg=PS(2), cap0=0.2, cap1=0.2)
    b.part('rope', loft, [R((0, 0.04, 0.012)) + (0.0092,) * 3, R((0, 0.07, 0.012)) + (0.0092,) * 3], up=(0, 0, 1), seg=S(8),
           per_seg=PS(2), cap0=0.2, cap1=0.2)
    b.part('iron', ellipsoid, Vector(R((0, 0.09, 0.012))), (0.0105, 0.0105, 0.0105), None, 6, 4)
    b.part('leather_dark', box, (0, 0.012, 0.003), (0.02, 0.03, 0.004))
    _tilt(b)
    return b, 'socket'


def prop_sword():
    """Crude goblin falchion: straight spine, bellied chipped edge, clipped tip, bent bar guard (socket space)."""
    b = Builder()
    spine = 0.022                                   # the back edge stays straight; the cutting edge bellies out
    rows = []
    for y, w in ((0.062, 0.019), (0.09, 0.022), (0.20, 0.025), (0.30, 0.028), (0.355, 0.023), (0.375, 0.029),
                 (0.44, 0.031), (0.49, 0.029), (0.525, 0.017), (0.548, 0.004)):
        rows.append((spine - w, y, 0.0, w, 0.0038, 0.0038))
    b.part('iron', loft, rows, up=(0, 0, 1), seg=S(12), per_seg=PS(2), cap0=0.2, cap1=0.6)
    b.part('iron', box, (0.0, 0.058, 0.0), (0.105, 0.013, 0.022), Matrix.Rotation(math.radians(4), 3, 'Z'))
    b.part('leather_dark', loft, [(0, y, 0, 0.0145, 0.0145, 0.0145) for y in (-0.048, 0.0, 0.05)], up=(0, 0, 1),
           seg=S(10), per_seg=PS(2), cap0=0.2, cap1=0.2)
    for y in (-0.03, 0.03):
        b.part('rope', loft, [(0, y - 0.006, 0, 0.0158, 0.0158, 0.0158), (0, y + 0.006, 0, 0.0158, 0.0158, 0.0158)],
               up=(0, 0, 1), seg=S(10), per_seg=1, cap0=0.2, cap1=0.2)
    b.part('iron', ellipsoid, Vector((0, -0.062, 0)), (0.019, 0.016, 0.017), None, 8, 5)
    _edge_to_knuckles(b)
    return b, 'socket'


# ----------------------------------------------------------------------------------------- more props
def _rings(b, mat, ys, r, seg=10):
    for y in ys:
        b.part(mat, loft, [(0, y - 0.007, 0, r, r, r), (0, y + 0.007, 0, r, r, r)], up=(0, 0, 1), seg=S(seg), per_seg=1,
               cap0=0.2, cap1=0.2)


def prop_cleaver():
    """Butcher's chopper: flat iron slab, notched edge, riveted to a short wooden handle (socket space)."""
    b = Builder()
    b.part('wood', loft, [(0, y, 0, 0.0135, 0.0135, 0.0135) for y in (-0.07, 0.0, 0.065)], up=(0, 0, 1), seg=S(10),
           per_seg=PS(2), cap0=0.4, cap1=0.2)
    _rings(b, 'rope', (-0.045, 0.015), 0.0152)
    blade = [(0.028, 0.055), (0.030, 0.33), (0.0, 0.352), (-0.06, 0.345), (-0.082, 0.31), (-0.084, 0.22), (-0.072, 0.21),
             (-0.084, 0.198), (-0.083, 0.10), (-0.06, 0.07), (-0.02, 0.055)]
    b.part('iron', prism, blade, -0.0045, 0.0045)
    for x in (0.008, -0.022):
        b.part('iron', ellipsoid, Vector((x, 0.075, 0)), (0.006, 0.006, 0.0065), None, 6, 3)
    _edge_to_knuckles(b)
    return b, 'socket'


def prop_club():
    """Knobbly wooden club studded with iron nails (socket space)."""
    b = Builder()
    rng = np.random.default_rng(21)
    prof = [(-0.085, 0.0135), (0.02, 0.0155), (0.12, 0.022), (0.20, 0.032), (0.26, 0.038), (0.31, 0.036), (0.345, 0.024)]
    rows = [(0.002 * math.sin(y * 30), y, 0, r * rng.uniform(0.95, 1.05), r, r) for y, r in prof]
    b.part('wood', loft, rows, up=(0, 0, 1), seg=S(12), per_seg=PS(3), cap0=0.4, cap1=0.9)
    b.part('leather_dark', loft, [(0, y, 0, 0.0158, 0.0158, 0.0158) for y in (-0.075, -0.02, 0.03)], up=(0, 0, 1),
           seg=S(10), per_seg=PS(2), cap0=0.2, cap1=0.2)
    for i in range(10):
        y = rng.uniform(0.17, 0.33)
        r = float(np.interp(y, [p[0] for p in prof], [p[1] for p in prof]))
        a = rng.uniform(0, 2 * math.pi)
        d = Vector((math.cos(a), rng.uniform(-0.2, 0.3), math.sin(a))).normalized()
        base = Vector((0, y, 0)) + Vector((math.cos(a), 0, math.sin(a))) * (r - 0.004)
        b.part('iron', cone, base, base + d * rng.uniform(0.022, 0.032), 0.0055, 0.0, seg=5)
    return b, 'socket'


def prop_axe():
    """Crude hand axe: wedge head lashed to a bent stick (socket space)."""
    b = Builder()
    rows = [(0.006 * math.sin((y + 0.1) * 6), y, 0, 0.013, 0.013, 0.013) for y in (-0.10, 0.0, 0.12, 0.24, 0.335)]
    b.part('wood', loft, rows, up=(0, 0, 1), seg=S(10), per_seg=PS(2), cap0=0.4, cap1=0.5)
    head = [(0.014, 0.24), (0.015, 0.315), (-0.02, 0.322), (-0.06, 0.345), (-0.09, 0.352), (-0.098, 0.28), (-0.088, 0.203),
            (-0.055, 0.215), (-0.02, 0.235)]
    b.part('iron', prism, head, -0.0075, 0.0075)
    b.part('iron', box, (0.024, 0.278, 0.0), (0.02, 0.034, 0.018))
    for y in (0.232, 0.326):
        b.part('rope', torus, (0.004, y, 0), (0, 1, 0), 0.016, 0.0045, seg=S(12), rseg=SR(5))
    _rings(b, 'leather_dark', (-0.07, -0.02), 0.0148)
    _edge_to_knuckles(b)
    return b, 'socket'


def prop_glaive():
    """Goblin glaive: long bent pole with a cleaver blade lashed to the top and a back hook (socket space)."""
    b = Builder()
    rng = np.random.default_rng(9)
    ys = np.linspace(-0.44, 0.70, 6)
    rows = [(0.003 * math.sin(y * 8) + rng.uniform(-0.001, 0.001), y, 0.002 * math.cos(y * 6), 0.0125, 0.0125, 0.0125) for y in ys]
    b.part('wood', loft, rows, up=(0, 0, 1), seg=S(10), per_seg=PS(2), cap0=0.3, cap1=0.3)
    _rings(b, 'leather_dark', (-0.06, 0.06), 0.0152)
    blade = [(0.012, 0.60), (0.014, 0.86), (-0.005, 0.95), (-0.04, 0.885), (-0.064, 0.79), (-0.061, 0.70), (-0.04, 0.64),
             (-0.012, 0.60)]
    b.part('iron', prism, blade, -0.0045, 0.0045)
    b.part('iron', cone, (0.012, 0.80, 0), (0.046, 0.835, 0), 0.007, 0.0, seg=5)
    for y in (0.615, 0.648, 0.681):
        b.part('rope', torus, (0.002, y, 0), (0, 1, 0), 0.0175, 0.0045, seg=S(12), rseg=SR(5))
    b.part('iron', cone, (0, -0.435, 0), (0, -0.48, 0), 0.0145, 0.004, seg=S(10))
    _edge_to_knuckles(b)
    return b, 'socket'


def prop_shield_plank():
    """Three rough planks, two iron bands with nails, arm straps behind (forearm socket space, face +Z)."""
    b = Builder()
    rng = np.random.default_rng(13)
    for x in (-0.074, 0.0, 0.074):
        x0, x1 = x - 0.035, x + 0.035
        y0a, y0b = -0.19 + rng.uniform(-0.015, 0.01), -0.19 + rng.uniform(-0.015, 0.01)
        y1a, y1b = 0.19 + rng.uniform(-0.01, 0.015), 0.19 + rng.uniform(-0.01, 0.015)
        z = 0.022 + rng.uniform(-0.002, 0.002)
        b.part('wood_plank', prism, [(x0, y0a), (x1, y0b), (x1, y1b), (x + rng.uniform(-0.01, 0.01), max(y1a, y1b) + 0.012),
                                     (x0, y1a)], z - 0.009, z + 0.009)
    for y in (-0.11, 0.11):
        b.part('iron', box, (0, y, 0.0325), (0.232, 0.022, 0.005))
        for x in (-0.09, 0.0, 0.09):
            b.part('iron', ellipsoid, Vector((x, y, 0.036)), (0.0055, 0.0055, 0.004), None, 6, 3)
    for y in (-0.05, 0.05):
        b.part('leather', box, (0, y, 0.006), (0.12, 0.022, 0.006))
    return b, 'socket'


def prop_pot_helm():
    """An upturned iron cooking pot worn at a jaunty tilt, with its handle (world space)."""
    b = Builder()
    tilt = Matrix.Rotation(math.radians(-7), 3, 'X') @ Matrix.Rotation(math.radians(3), 3, 'Y')
    c = Vector((0, -0.026, 0.957))
    b.part('pot', cone, c, c + tilt @ Vector((0, 0, 0.095)), 0.114, 0.105, seg=S(22))
    b.part('pot', torus, c, tilt @ Vector((0, 0, 1)), 0.115, 0.006, seg=S(22), rseg=SR(5))
    b.part('pot', torus, c + tilt @ Vector((0.128, 0, 0.055)), tilt @ Vector((0, 1, 0)), 0.02, 0.005, seg=S(12), rseg=SR(5))
    for dz in (0.035, 0.075):
        b.part('pot', ellipsoid, c + tilt @ Vector((0.108, 0, dz)), (0.006, 0.006, 0.006), None, 6, 3)
    return b, 'world'


def prop_leather_cap():
    """Stitched leather skullcap with a rim band and a knotted top (world space)."""
    b = Builder()
    rim, top = head_shell(b, 'leather_dark', lambda y: 0.958 - 0.5 * max(0.0, y), 0.004, 0.011)
    ctr = rim.mean(0)
    Nn = rim - ctr
    Nn[:, 2] = 0
    Nn /= np.linalg.norm(Nn, axis=1)[:, None]
    T = np.roll(rim, -1, 0) - np.roll(rim, 1, 0)
    b.part('leather', band, rim + [0, 0, 0.006] - Nn * 0.001, Nn, np.cross(Nn, T), 0.014, 0.004)
    for phi, th in ((0.6, 0.55), (2.4, 0.5)):                 # two sewn-on patches
        p = head_pt(th, phi, 0.012)
        n = Vector(p - gob_body.HC).normalized()
        b.part('leather', box, tuple(p), (0.03, 0.028, 0.004), n.to_track_quat('Z', 'Y').to_matrix())
    t = Vector(top)
    b.part('leather_dark', loft, [tuple(t - Vector((0, 0, 0.01))) + (0.012, 0.012, 0.012),
                                  tuple(t + Vector((0, 0.012, 0.018))) + (0.009, 0.009, 0.009),
                                  tuple(t + Vector((0, 0.03, 0.028))) + (0.005, 0.005, 0.005)], up=(0, -1, 0), seg=S(8),
           per_seg=PS(2), cap0=0.3, cap1=0.8)
    return b, 'world'


def prop_hair():
    """Scraggly dark tufts sprouting from the crown and back of the skull (world space)."""
    b = Builder()
    rng = np.random.default_rng(5)
    for i in range(16):
        th = rng.uniform(0.0, 0.85)
        phi = rng.uniform(0.15 * math.pi, 0.85 * math.pi) if i > 3 else rng.uniform(0, 2 * math.pi)
        base = Vector(head_pt(th, phi, -0.003))
        n = (base - Vector(gob_body.HC)).normalized()
        d = (n + Vector((rng.uniform(-0.3, 0.3), 0.55, 0.35))).normalized()
        b.part('hair', cone, base, base + d * rng.uniform(0.045, 0.095), rng.uniform(0.007, 0.011), 0.0012, seg=5)
    return b, 'world'


def _surface_loop(surf, ctrl, lift, per_seg=4, keep_off=None):
    """Closed path through ctrl points, projected onto the body (points listed in keep_off stay where they are)."""
    pts = closed_spline(ctrl, per_seg=per_seg)
    P, N = [], []
    for i, p in enumerate(pts):
        loc, nrm, _ = surf.nearest(p)
        if keep_off is not None and keep_off(i // per_seg, p):
            P.append(np.array(p))
            N.append(np.array(nrm))
        else:
            P.append(np.array(loc) + np.array(nrm) * lift)
            N.append(np.array(nrm))
    P, N = np.array(P), np.array(N)
    T = np.roll(P, -1, 0) - np.roll(P, 1, 0)
    return P, N, np.cross(T, N)


def prop_sack():
    """Lumpy loot sack on the back with two shoulder straps (world space)."""
    b = Builder()
    rows = [(0, 0.165, 0.55, 0.05, 0.035, 0.03), (0, 0.168, 0.60, 0.085, 0.06, 0.045), (0, 0.170, 0.675, 0.092, 0.066, 0.046),
            (0, 0.166, 0.735, 0.07, 0.05, 0.036), (0, 0.160, 0.772, 0.03, 0.022, 0.02), (0, 0.158, 0.80, 0.042, 0.03, 0.03)]
    b.part('cloth', loft, rows, up=(0, 1, 0), seg=S(14), per_seg=PS(3), cap0=0.7, cap1=0.6)
    b.part('rope', torus, (0, 0.16, 0.775), (0, 0, 1), 0.024, 0.005, seg=S(12), rseg=SR(5))
    surf = BodySurface()
    try:
        for s in (1, -1):
            ctrl = [(s * 0.05, 0.13, 0.745), (s * 0.075, 0.03, 0.772), (s * 0.075, -0.06, 0.70), (s * 0.108, -0.01, 0.635),
                    (s * 0.07, 0.125, 0.575)]
            P, N, W = _surface_loop(surf, ctrl, 0.016, keep_off=lambda seg, p: p[1] > 0.1)
            b.part('leather', band, P, N, W, 0.02, 0.005)
    finally:
        surf.free()
    return b, 'world'


def prop_necklace():
    """Cord of teeth and finger bones around the neck (world space, rides on the upper chest)."""
    b = Builder()
    surf = BodySurface()
    try:
        ctrl = [(0.0, -0.058, 0.728), (0.055, -0.042, 0.748), (0.078, 0.0, 0.768), (0.05, 0.05, 0.782), (0.0, 0.062, 0.786),
                (-0.05, 0.05, 0.782), (-0.078, 0.0, 0.768), (-0.055, -0.042, 0.748)]
        P, N, W = _surface_loop(surf, ctrl, 0.006, per_seg=4)
        b.part('leather_dark', band, P, N, W, 0.007, 0.005)
        front = [i for i in range(len(P)) if P[i][1] < -0.03]
        rng = np.random.default_rng(3)
        for k, i in enumerate(front[::max(1, len(front) // 7)][:7]):
            p, n = Vector(P[i]), Vector(N[i])
            length = 0.034 if k == 3 else rng.uniform(0.018, 0.026)
            tip = p + (n * 0.35 + Vector((0, 0, -1))).normalized() * length
            b.part('bone', cone, p + n * 0.003, tip, 0.0055 if k == 3 else 0.0042, 0.0008, seg=5)
    finally:
        surf.free()
    return b, 'world'


def prop_waterskin():
    """Leather waterskin with a wooden stopper, hanging from the belt (hip socket space)."""
    b = Builder()
    rows = [(0, -0.13, 0.03, 0.03, 0.028, 0.02), (0, -0.09, 0.035, 0.045, 0.04, 0.028), (0, -0.045, 0.033, 0.04, 0.035, 0.025),
            (0, -0.012, 0.028, 0.02, 0.018, 0.015), (0, 0.008, 0.028, 0.012, 0.012, 0.012)]
    b.part('leather', loft, rows, up=(0, 0, 1), seg=S(12), per_seg=PS(3), cap0=0.8, cap1=0.2)
    b.part('wood', loft, [(0, 0.004, 0.028, 0.0095, 0.0095, 0.0095), (0, 0.026, 0.028, 0.0085, 0.0085, 0.0085)], up=(0, 0, 1),
           seg=S(8), per_seg=1, cap0=0.2, cap1=0.5)
    b.part('rope', torus, (0, -0.008, 0.028), (0, 1, 0), 0.02, 0.004, seg=S(10), rseg=SR(4))
    b.part('leather_dark', box, (0, 0.012, 0.004), (0.016, 0.035, 0.004))
    _tilt(b, -18)
    return b, 'socket'


def prop_skull_trophy():
    """Small horned animal skull hanging from the belt front (belt socket space: +Y up, +Z forward)."""
    b = Builder()
    b.part('leather_dark', box, (0, -0.018, 0.006), (0.006, 0.036, 0.004))
    b.part('bone', ellipsoid, Vector((0, -0.062, 0.03)), (0.026, 0.028, 0.024), None, 10, 6)
    b.part('bone', ellipsoid, Vector((0, -0.08, 0.052)), (0.016, 0.014, 0.02), None, 8, 5)
    for s in (1, -1):
        b.part('leather_dark', ellipsoid, Vector((s * 0.011, -0.056, 0.049)), (0.0075, 0.0075, 0.006), None, 6, 4)
        b.part('bone', cone, (s * 0.018, -0.044, 0.028), (s * 0.04, -0.028, 0.018), 0.006, 0.0, seg=5)
    return b, 'socket'


# ----------------------------------------------------------------------------------------- chief
_MANTLE_HEM = [(0, (0.0, -0.092, 0.625)), (45, (0.105, -0.076, 0.655)), (90, (0.200, 0.0, 0.748)),
               (135, (0.120, 0.098, 0.56)), (180, (0.0, 0.108, 0.47))]


def _mantle_hem(deg):
    """Hem point of the fur mantle at azimuth deg (0 = front); the right side mirrors the left."""
    side = 1 if deg <= 180 else -1
    a = deg if deg <= 180 else 360 - deg
    angs = [h[0] for h in _MANTLE_HEM]
    pts = np.array([h[1] for h in _MANTLE_HEM])
    p = np.array([np.interp(a, angs, pts[:, k]) for k in range(3)])
    p[0] *= side
    return p


def build_fur_mantle(surf, mats, coll, J=36, R=5):
    """Chief's fur mantle: a thick pelt over shoulders and upper back with a short cape and a brass clasp."""
    remove_obj("Outfit_FurMantle")
    b = Builder()
    rng = np.random.default_rng(17)
    grid = []
    for j in range(J):
        deg = 360.0 * j / J
        th = math.radians(deg)
        front = math.cos(th) > 0
        S0 = np.array([0.062 * math.sin(th), -(0.048 if front else 0.064) * math.cos(th), 0.772])
        E = _mantle_hem(deg)
        E = E + (E - S0) / np.linalg.norm(E - S0) * (0.022 if j % 2 else 0.0) + rng.uniform(-0.006, 0.006, 3) * [1, 1, 1]
        col = []
        for i in range(R + 1):
            t = i / R
            p = S0 + (E - S0) * t + np.array([0, 0, 0.03 * math.sin(math.pi * t)])
            loc, nrm, _ = surf.nearest(p)
            col.append(b.bm.verts.new(Vector(loc) + nrm * (0.013 + 0.004 * math.sin(math.pi * t))))
        grid.append(col)
    b.mats.append('fur')
    for f in grid_faces(b.bm, [[grid[j][i] for j in range(J)] for i in range(R + 1)], close_j=True)[0]:
        f.material_index = 0
    ob = _finish("Outfit_FurMantle", b, coll, mats, solidify=0.012)
    clasp = Builder()                              # brass clasp at the throat, part of the mantle
    loc, nrm, _ = surf.nearest((0, -0.06, 0.745))
    clasp.part('brass', ellipsoid, Vector(loc) + nrm * 0.024, (0.016, 0.008, 0.016), None, 10, 6)
    clasp.part('brass', torus, Vector(loc) + nrm * 0.028, nrm, 0.018, 0.004, seg=S(12), rseg=SR(5))
    cl = _finish("Outfit_FurMantle_Clasp", clasp, coll, mats)
    for o in bpy.context.selected_objects:
        o.select_set(False)
    cl.select_set(True)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.join()
    ob.name = ob.data.name = "Outfit_FurMantle"
    skin_to_rig(ob, surf)
    return ob


def head_ring(zrim, off, U=24):
    """Ring around the skull where it crosses zrim(y), pushed out by off (world space)."""
    pts = []
    for u in range(U):
        phi = 2 * math.pi * u / U
        lo, hi = 0.0, math.pi * 0.75
        for _ in range(30):
            mid = (lo + hi) / 2
            q = head_pt(mid, phi, off)
            if q[2] > zrim(q[1]):
                lo = mid
            else:
                hi = mid
        pts.append(head_pt(lo, phi, off))
    return np.array(pts)


def prop_bone_crown():
    """Chief's crown: leather headband with brass studs, a fan of bone spikes in front, two great horns."""
    b = Builder()
    ring = head_ring(lambda y: 0.968 - 0.35 * max(0.0, y), 0.011)
    ctr = ring.mean(0)
    N = ring - ctr
    N[:, 2] = 0
    N /= np.linalg.norm(N, axis=1)[:, None]
    T = np.roll(ring, -1, 0) - np.roll(ring, 1, 0)
    W = np.cross(N, T)
    b.part('leather_dark', band, ring, N, W, 0.024, 0.006)
    b.part('brass', band, ring + [0, 0, 0.012] + N * 0.001, N, W, 0.006, 0.008)
    for i, p in enumerate(ring):
        n = Vector(N[i])
        front = -n.y                                   # 1 at the front of the head
        if front > 0.25:
            h = 0.035 + 0.065 * front ** 2
            base = Vector(p) + n * 0.004 + Vector((0, 0, 0.006))
            b.part('bone', cone, base, base + Vector((0, 0, h)) + n * 0.012, 0.0085, 0.0, seg=5)
        if i % 3 == 0:
            b.part('brass', ellipsoid, Vector(p) + n * 0.007, (0.0055, 0.0055, 0.0055), None, 6, 3)
    for sg in (1, -1):
        horn = [(sg * 0.092, -0.004, 0.972, 0.021, 0.021, 0.021), (sg * 0.150, 0.008, 1.005, 0.017, 0.017, 0.017),
                (sg * 0.192, 0.004, 1.062, 0.012, 0.012, 0.012), (sg * 0.200, -0.028, 1.122, 0.007, 0.007, 0.007),
                (sg * 0.188, -0.062, 1.150, 0.0025, 0.0025, 0.0025)]
        b.part('bone', loft, horn, up=(0, -1, 0), seg=S(10), per_seg=PS(3), cap0=0.3, cap1=1.2)
        b.part('brass', torus, (sg * 0.100, -0.004, 0.975), (sg * 0.9, 0.0, 0.45), 0.022, 0.005, seg=S(14), rseg=SR(5))
    return b, 'world'


def prop_great_axe():
    """Chief's two-handed great axe: long haft, big bearded crescent blade, back spike, top spike (socket space)."""
    b = Builder()
    rows = [(0.003 * math.sin(y * 7), y, 0, 0.0165, 0.0165, 0.0165) for y in (-0.30, -0.1, 0.1, 0.3, 0.5, 0.64)]
    b.part('wood', loft, rows, up=(0, 0, 1), seg=S(10), per_seg=PS(2), cap0=0.4, cap1=0.3)
    _rings(b, 'leather_dark', (-0.22, -0.16, 0.0, 0.06), 0.019)
    blade = [(0.016, 0.42), (0.016, 0.66), (-0.04, 0.705), (-0.11, 0.725), (-0.165, 0.665), (-0.178, 0.57),
             (-0.168, 0.47), (-0.13, 0.43), (-0.12, 0.40), (-0.10, 0.415), (-0.05, 0.425)]
    b.part('iron', prism, blade, -0.0085, 0.0085)
    b.part('iron', cone, (0.016, 0.54, 0), (0.10, 0.555, 0), 0.014, 0.0, seg=6)
    b.part('iron', cone, (0, 0.62, 0), (0, 0.74, 0), 0.013, 0.0, seg=6)
    for y in (0.43, 0.65):
        b.part('rope', torus, (0.004, y, 0), (0, 1, 0), 0.021, 0.005, seg=S(12), rseg=SR(5))
    b.part('bone', torus, (0.004, 0.395, 0), (0, 1, 0), 0.02, 0.004, seg=S(10), rseg=SR(4))
    for k in range(4):                               # teeth dangling under the head
        a = k * math.pi / 2 + 0.4
        base = Vector((0.004 + math.cos(a) * 0.022, 0.39, math.sin(a) * 0.022))
        b.part('bone', cone, base, base + Vector((0, -0.028, 0)), 0.005, 0.0008, seg=5)
    b.part('iron', cone, (0, -0.30, 0), (0, -0.345, 0), 0.018, 0.005, seg=S(10))
    _edge_to_knuckles(b)
    return b, 'socket'


def _skull(b, c, s=1.0, facing=(0, -1, 0), horns=True):
    """Stylised horned skull at c, snout toward `facing` (world or socket space)."""
    f = Vector(facing).normalized()
    c = Vector(c)
    b.part('bone', ellipsoid, c, (0.032 * s, 0.032 * s, 0.03 * s), None, 10, 6)
    b.part('bone', ellipsoid, c + f * 0.03 * s - Vector((0, 0, 0.008 * s)), (0.02 * s, 0.02 * s, 0.017 * s), None, 8, 5)
    side = f.cross(Vector((0, 0, 1))).normalized()
    for sg in (1, -1):
        b.part('leather_dark', ellipsoid, c + f * 0.022 * s + side * sg * 0.013 * s + Vector((0, 0, 0.006 * s)),
               (0.0085 * s, 0.0085 * s, 0.0075 * s), None, 6, 4)
        if horns:
            base = c + side * sg * 0.022 * s + Vector((0, 0, 0.014 * s))
            b.part('bone', cone, base, base + side * sg * 0.035 * s + Vector((0, 0, 0.035 * s)) - f * 0.01 * s,
                   0.008 * s, 0.0, seg=5)


def prop_skull_pauldron():
    """Iron-and-leather shoulder plate crowned with a horned skull (left shoulder, world space)."""
    b, _ = prop_pauldron(spikes=False)
    _skull(b, (0.152, -0.004, 0.823), s=1.05, facing=(0, -1, 0))
    for x in (0.115, 0.19):
        base = Vector((x, 0.006, 0.785))
        b.part('iron', cone, base, base + Vector((0.0, 0.0, 0.03)), 0.009, 0.0, seg=5)
    return b, 'world'


def prop_chief_buckle():
    """Big iron belt plate with a brass rim and a horned skull (belt socket space: +Y up, +Z forward)."""
    b = Builder()
    b.part('iron', cone, (0, 0, 0.001), (0, 0, 0.011), 0.048, 0.046, seg=S(16))
    b.part('brass', torus, (0, 0, 0.011), (0, 0, 1), 0.047, 0.005, seg=S(16), rseg=SR(4))
    _skull(b, (0, 0.004, 0.028), s=0.8, facing=(0, -0.35, 1))
    return b, 'socket'


def prop_war_banner():
    """Chief's war banner strapped to the back: tall pole, crossbar, tattered red flag, horned skull on top.
    Back socket space: +Y up, +Z away from the back. Rises well above the head so the chief reads from afar."""
    b = Builder()
    ys = np.linspace(-0.06, 1.08, 5)
    b.part('wood', loft, [(0.004 * math.sin(y * 5), y, 0.03, 0.012, 0.012, 0.012) for y in ys], up=(0, 0, 1), seg=S(8),
           per_seg=PS(2), cap0=0.3, cap1=0.3)
    b.part('wood', loft, [(x, 0.95, 0.03, 0.0085, 0.0085, 0.0085) for x in (-0.15, 0.0, 0.15)], up=(0, 1, 0), seg=S(8),
           per_seg=PS(2), cap0=0.4, cap1=0.4)
    b.part('rope', torus, (0, 0.95, 0.03), (0, 0, 1), 0.016, 0.004, seg=S(10), rseg=SR(4))
    flag = [(-0.135, 0.935), (0.135, 0.935), (0.135, 0.62), (0.095, 0.565), (0.055, 0.635), (0.01, 0.55), (-0.04, 0.625),
            (-0.085, 0.56), (-0.135, 0.605)]
    b.part('banner', prism, flag, 0.038, 0.045)
    _skull(b, (0, 1.12, 0.03), s=1.1, facing=(0, 0, -1))
    for x in (-0.15, 0.15):                          # bones dangling from the crossbar ends
        b.part('bone', cone, (x, 0.94, 0.03), (x, 0.88, 0.03), 0.006, 0.002, seg=5)
    for y in (0.05, 0.25):                           # straps to the back
        b.part('leather_dark', box, (0, y, 0.012), (0.05, 0.02, 0.01))
    return b, 'socket'


# ----------------------------------------------------------------------------------------- archer
BOW_HALF, BOW_BEND = 0.36, 0.092   # half length and brace depth of the short bow (string ends at (BOW_BEND, +-BOW_HALF))
ARROW_REST = (0.0, 0.040, 0.021)   # where the nocked shaft crosses the bow, Socket_LeftHand space (GoblinArcher uses it)


def _bow_x(u):
    return BOW_BEND * abs(u) ** 1.8


def prop_shortbow():
    """Goblin short bow for the LEFT hand. Left-hand knuckles (and the bow's back) face -X, so the stave bows
    toward +X (the archer) and the string, drawn at runtime by GoblinArcher, runs between the tips at x = BOW_BEND."""
    b = Builder()
    rows = []
    for y in np.linspace(-BOW_HALF, BOW_HALF, 11):
        u = abs(y) / BOW_HALF
        r = 0.0125 - 0.0065 * u
        rows.append((_bow_x(u), y, 0.0, r * 1.2, r * 0.75, r * 0.75))
    b.part('wood', loft, rows, up=(1, 0, 0), seg=S(8), per_seg=PS(2), cap0=0.3, cap1=0.3)
    b.part('leather_dark', loft, [(0.0, y, 0.0, 0.0165, 0.0165, 0.0165) for y in (-0.055, 0.0, 0.055)], up=(1, 0, 0),
           seg=S(10), per_seg=PS(2), cap0=0.2, cap1=0.2)
    b.part('rope', loft, [(0.0, y, 0.0, 0.0172, 0.0172, 0.0172) for y in (0.05, 0.062)], up=(1, 0, 0), seg=S(10),
           per_seg=1, cap0=0.2, cap1=0.2)
    for sg in (1, -1):                               # horn nocks where the string ties on
        base = Vector((_bow_x(0.93), sg * BOW_HALF * 0.93, 0))
        tip = Vector((BOW_BEND, sg * BOW_HALF, 0))
        b.part('bone', cone, base, tip + (tip - base).normalized() * 0.012, 0.0075, 0.0022, seg=5)
    return b, 'socket'


def prop_arrow():
    """Arrow for the RIGHT hand: nock at the grip centre (where the string runs through the fingers), shaft along
    +X (the knuckle side), red fletching. GoblinArcher lines it up with the bow while it is nocked."""
    b = Builder()
    b.part('wood', loft, [(x, 0, 0, 0.0045, 0.0045, 0.0045) for x in (-0.012, 0.22, 0.455)], up=(0, 0, 1), seg=5,
           per_seg=1, cap0=0.2, cap1=0.2)
    b.part('iron', cone, (0.448, 0, 0), (0.505, 0, 0), 0.0105, 0.0, seg=5)
    for k in range(3):
        rot = Matrix.Rotation(k * 2 * math.pi / 3, 3, 'X')
        b.part('banner', box, tuple(Vector((0.05, 0, 0)) + rot @ Vector((0.0, 0.0, 0.0105))), (0.065, 0.0016, 0.013), rot)
    b.part('leather_dark', loft, [(x, 0, 0, 0.0058, 0.0058, 0.0058) for x in (-0.014, -0.002)], up=(0, 0, 1), seg=5,
           per_seg=1, cap0=0.3, cap1=0.3)
    return b, 'socket'


QUIVER_MOUTH = ((-0.07, 0.158, 0.83), (0.055, 0.158, 0.50))   # world rest: mouth centre, bottom centre


def prop_quiver():
    """Leather quiver slung across the back, mouth over the right shoulder, fletched arrows showing, strap across
    the chest (world space)."""
    b = Builder()
    c, a = np.array(QUIVER_MOUTH[0]), np.array(QUIVER_MOUTH[1])
    rows = [tuple(a + (c - a) * t) + (0.034, 0.03, 0.03) for t in (0.0, 0.5, 1.0)]
    b.part('leather', loft, rows, up=(0, 1, 0), seg=S(12), per_seg=PS(2), cap0=0.6, cap1=0.15)
    d = (c - a) / np.linalg.norm(c - a)
    for t in (0.97, 0.3):
        b.part('leather_dark', torus, tuple(a + (c - a) * t), tuple(d), 0.035, 0.005, seg=S(12), rseg=SR(4))
    rng = np.random.default_rng(12)
    for k in range(6):
        off = np.array([rng.uniform(-0.02, 0.02), rng.uniform(-0.014, 0.014), rng.uniform(-0.014, 0.014)])
        base = c + off - d * 0.03
        tip = base + (d + rng.uniform(-0.12, 0.12, 3)) * rng.uniform(0.09, 0.12)
        b.part('wood', cone, tuple(base), tuple(tip), 0.0045, 0.004, seg=5)
        tv, dv = Vector(tip), (Vector(tip) - Vector(base)).normalized()
        rot = dv.to_track_quat('Z', 'Y').to_matrix() @ Matrix.Rotation(rng.uniform(0, math.pi), 3, 'Z')
        b.part('banner', box, tuple(tv - dv * 0.028), (0.018, 0.0016, 0.045), rot)
    surf = BodySurface()
    try:
        ctrl = [(-0.06, 0.13, 0.80), (-0.085, 0.01, 0.772), (-0.03, -0.08, 0.66), (0.08, -0.085, 0.53), (0.125, 0.02, 0.50),
                (0.07, 0.125, 0.53)]
        P, N, W = _surface_loop(surf, ctrl, 0.014, keep_off=lambda seg, p: p[1] > 0.11)
        b.part('leather_dark', band, P, N, W, 0.018, 0.005)
    finally:
        surf.free()
    return b, 'world'


# ----------------------------------------------------------------------------------------- shaman
STAFF_FOOT = -0.62          # staff length below the grip (Socket_RightHand +Y runs up the staff)
STAFF_ORB = (0.0, 0.565, 0.0)   # the glow between the fork tips, Socket_RightHand space (GoblinShaman uses it)


def prop_shaman_staff():
    """Gnarled forked staff taller than its goblin: a horned skull wedged in the fork, facing the knuckle side
    (+X, forward when the staff is held upright), feathers and a bone dangling below it (socket space)."""
    b = Builder()
    # the skull first, built upright (Z up, facing -Y) and turned into staff space (Y up, facing +X)
    _skull(b, (0, 0, 0), s=0.85, facing=(0, -1, 0))
    R = Matrix(((0, -1, 0), (0, 0, 1), (-1, 0, 0))).to_4x4()          # x->-z, y->-x, z->y
    bmesh.ops.transform(b.bm, matrix=Matrix.Translation((0.012, 0.47, 0.0)) @ R, verts=b.bm.verts[:])
    ys = np.linspace(STAFF_FOOT, 0.42, 9)
    rows = [(0.006 * math.sin(y * 9), y, 0.005 * math.cos(y * 7),
             r, r, r) for y, r in zip(ys, np.linspace(0.011, 0.0145, 9))]
    for k in (2, 6):                                                    # knots
        rows[k] = rows[k][:3] + tuple(v * 1.28 for v in rows[k][3:])
    b.part('wood', loft, rows, up=(0, 0, 1), seg=S(9), per_seg=PS(2), cap0=0.5, cap1=0.3)
    for sg in (1, -1):                                                  # the fork
        fork = [(0.0, 0.40, 0.0, 0.012, 0.012, 0.012), (0.004, 0.46, sg * 0.036, 0.0105, 0.0105, 0.0105),
                (0.006, 0.54, sg * 0.047, 0.008, 0.008, 0.008), (0.0, 0.605, sg * 0.03, 0.0035, 0.0035, 0.0035)]
        b.part('wood', loft, fork, up=(1, 0, 0), seg=S(8), per_seg=PS(3), cap0=0.3, cap1=1.0)
    for y in (0.395, 0.425):
        b.part('rope', torus, (0.0, y, 0.0), (0, 1, 0), 0.016, 0.004, seg=S(10), rseg=SR(4))
    b.part('leather_dark', loft, [(0, y, 0, 0.0158, 0.0158, 0.0158) for y in (-0.06, 0.0, 0.06)], up=(0, 0, 1),
           seg=S(9), per_seg=PS(2), cap0=0.2, cap1=0.2)
    for k, (z, mat, ln) in enumerate(((0.03, 'banner', 0.075), (-0.028, 'linen', 0.09), (0.0, 'hair', 0.065))):
        top = Vector((0.004, 0.39, z))                                  # cords hanging from the fork
        end = top + Vector((0.0, -ln, 0.0))
        b.part('rope', box, tuple((top + end) / 2), (0.003, ln, 0.003))
        b.part(mat, box, tuple(end + Vector((0, -0.028, 0))), (0.0025, 0.055, 0.016))   # feather
    b.part('bone', cone, (0.004, 0.37, 0.0), (0.004, 0.30, 0.0), 0.006, 0.002, seg=5)  # a finger bone
    b.part('wood', cone, (0.0, STAFF_FOOT + 0.005, 0.0), (0.0, STAFF_FOOT - 0.03, 0.0), 0.011, 0.003, seg=S(9))
    return b, 'socket'


def _feather(bm, base, rot, ln, w=0.012):
    """Flat feather: quill end at base, vane widening then tapering to a point along rot's +Y, face along +Z."""
    prof = [(0.0, 0.0), (0.3, 0.07), (0.85, 0.28), (1.0, 0.55), (0.7, 0.83), (0.0, 1.0)]
    outline = [(w * a, ln * t) for a, t in prof] + [(-w * a, ln * t) for a, t in reversed(prof[1:-1])]
    _slab(bm, outline, Matrix.Translation(base) @ rot.to_4x4(), -0.0012, 0.0012)


def prop_shaman_headdress():
    """Leather band with a fan of feathers swept back, strings of beads hanging by the ears (world space)."""
    b = Builder()
    ring = head_ring(lambda y: 0.962 - 0.3 * max(0.0, y), 0.011)
    ctr = ring.mean(0)
    N = ring - ctr
    N[:, 2] = 0
    N /= np.linalg.norm(N, axis=1)[:, None]
    T = np.roll(ring, -1, 0) - np.roll(ring, 1, 0)
    W = np.cross(N, T)
    b.part('leather_dark', band, ring, N, W, 0.02, 0.006)
    mats = ('banner', 'linen', 'hair', 'linen', 'banner', 'hair', 'linen')
    rng = np.random.default_rng(5)
    for k, u in enumerate(np.linspace(-1.0, 1.0, 7)):                   # fan across the back half of the head
        phi = math.pi / 2 + u                                           # azimuth; pi/2 = straight back (+Y)
        p = Vector(ring[int(round(phi / (2 * math.pi) * len(ring))) % len(ring)])
        n = Vector((math.cos(phi), math.sin(phi), 0))
        ln = 0.14 - 0.035 * abs(u) + rng.uniform(-0.012, 0.012)
        d = (Vector((0, 0, 1)) + n * (0.75 + 0.2 * abs(u))).normalized()   # swept back, outer ones lower
        zt = (n - n.project(d)).normalized()                            # broad face turned outward: a fan
        rot = Matrix((d.cross(zt), d, zt)).transposed()
        rot = rot @ Matrix.Rotation(rng.uniform(-0.12, 0.12), 3, 'Y')   # not all perfectly flat to the fan
        b.part(mats[k], _feather, p + n * 0.006 + d * 0.012, rot, ln)
        b.part('bone', cone, p + n * 0.004, p + n * 0.004 + d * 0.03, 0.0042, 0.0025, seg=5)  # quill
    for sg in (1, -1):                                                  # bead strings at the temples
        top = Vector((sg * 0.088, -0.03, 0.935))
        for j in range(4):
            mat = 'bone' if j % 2 == 0 else 'banner'
            b.part(mat, ellipsoid, top + Vector((sg * 0.006, 0, -0.018 * j - 0.01)), (0.0065, 0.0065, 0.0075), None, 6, 4)
        b.part('bone', cone, top + Vector((sg * 0.006, 0, -0.08)), top + Vector((sg * 0.006, 0, -0.11)), 0.006, 0.0, seg=5)
    return b, 'world'


def _cloak_hem(deg):
    """Hem of the shaman's hide cape at azimuth deg (0 = front, 180 = back): short at the open front, down to the
    hips behind (world space, right side mirrors the left)."""
    a = deg if deg <= 180 else 360 - deg
    side = 1 if deg <= 180 else -1
    pts = [(40, (0.095, -0.07, 0.66)), (90, (0.19, 0.0, 0.60)), (135, (0.13, 0.11, 0.49)), (180, (0.0, 0.13, 0.43))]
    angs = [p[0] for p in pts]
    arr = np.array([p[1] for p in pts])
    p = np.array([np.interp(a, angs, arr[:, k]) for k in range(3)])
    p[0] *= side
    return p


def build_shaman_cloak(surf, mats, coll, J=36, R=6):
    """Shaman's ragged hide cape: over the shoulders, open at the chest, long behind, tied with a cord."""
    remove_obj("Outfit_ShamanCloak")
    b = Builder()
    rng = np.random.default_rng(23)
    b.mats.append('leather')
    grid = {}
    for j in range(J):
        deg = 360.0 * j / J
        a = deg if deg <= 180 else 360 - deg
        if a < 40:                                   # open front
            continue
        th = math.radians(deg)
        S0 = np.array([0.064 * math.sin(th), -0.05 * math.cos(th), 0.772])
        E = _cloak_hem(deg)
        tear = (0.03 if j % 3 == 0 else 0.0) + rng.uniform(-0.01, 0.012)   # ragged hem
        E = E + (E - S0) / np.linalg.norm(E - S0) * tear
        col = []
        for i in range(R + 1):
            t = i / R
            p = S0 + (E - S0) * t + np.array([0, 0, 0.025 * math.sin(math.pi * t)])
            loc, nrm, _ = surf.nearest(p)
            col.append(b.bm.verts.new(Vector(loc) + nrm * (0.011 + 0.006 * math.sin(math.pi * t) + 0.004 * t)))
        grid[j] = col
    js = sorted(grid)                                # one run of columns from one front edge round the back
    for f in grid_faces(b.bm, [[grid[j][i] for j in js] for i in range(R + 1)])[0]:
        f.material_index = 0
    ob = _finish("Outfit_ShamanCloak", b, coll, mats, solidify=0.008)
    tie = Builder()                                  # cord across the collarbones with a bone toggle
    ctrl = [(0.095, -0.07, 0.72), (0.05, -0.085, 0.705), (0.0, -0.09, 0.70), (-0.05, -0.085, 0.705), (-0.095, -0.07, 0.72)]
    pts = spline(ctrl, 4)[:, :3]
    for p0, p1 in zip(pts[:-1], pts[1:]):
        l0, n0, _ = surf.nearest(p0)
        l1, n1, _ = surf.nearest(p1)
        tie.part('rope', cone, Vector(l0) + n0 * 0.012, Vector(l1) + n1 * 0.012, 0.0035, 0.0035, seg=5)
    loc, nrm, _ = surf.nearest((0.0, -0.09, 0.70))
    tie.part('bone', cone, Vector(loc) + nrm * 0.016 + Vector((-0.02, 0, 0)), Vector(loc) + nrm * 0.016 + Vector((0.02, 0, 0)),
             0.006, 0.006, seg=5)
    tl = _finish("Outfit_ShamanCloak_Tie", tie, coll, mats)
    for o in bpy.context.selected_objects:
        o.select_set(False)
    tl.select_set(True)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.join()
    ob.name = ob.data.name = "Outfit_ShamanCloak"
    skin_to_rig(ob, surf)
    return ob


# props that share a socket with the default loadout are built and exported but hidden in the Blender preview
PREVIEW_HIDDEN = {"Prop_Sword", "Prop_Cleaver", "Prop_Club", "Prop_Axe", "Prop_Glaive", "Prop_ShieldPlank", "Prop_PotHelm",
                  "Prop_LeatherCap", "Prop_Hair", "Prop_Sack", "Prop_Necklace", "Prop_Waterskin", "Prop_SkullTrophy",
                  "Prop_GreatAxe", "Prop_BoneCrown", "Prop_SkullPauldron", "Prop_ChiefBuckle", "Prop_WarBanner", "Outfit_FurMantle",
                  "Prop_Shortbow", "Prop_Arrow", "Prop_Quiver", "Prop_ShamanStaff", "Prop_ShamanHeaddress",
                  "Outfit_ShamanCloak"}

PROPS = [
    ("Prop_Spear", prop_spear, "Socket_RightHand"),
    ("Prop_Sword", prop_sword, "Socket_RightHand"),
    ("Prop_Shield", prop_shield, "Socket_LeftForearm"),
    ("Prop_Helmet", prop_helmet, "Socket_Helm"),
    ("Prop_Pauldron", prop_pauldron, "Socket_LeftShoulder"),
    ("Prop_Pouch", prop_pouch, "Socket_RightHip"),
    ("Prop_Knife", prop_knife, "Socket_LeftHip"),
    ("Prop_Cleaver", prop_cleaver, "Socket_RightHand"),
    ("Prop_Club", prop_club, "Socket_RightHand"),
    ("Prop_Axe", prop_axe, "Socket_RightHand"),
    ("Prop_Glaive", prop_glaive, "Socket_RightHand"),
    ("Prop_ShieldPlank", prop_shield_plank, "Socket_LeftForearm"),
    ("Prop_PotHelm", prop_pot_helm, "Socket_Helm"),
    ("Prop_LeatherCap", prop_leather_cap, "Socket_Helm"),
    ("Prop_Hair", prop_hair, "Socket_Helm"),
    ("Prop_Sack", prop_sack, "Socket_Back"),
    ("Prop_Necklace", prop_necklace, "Socket_Chest"),
    ("Prop_Waterskin", prop_waterskin, "Socket_RightHip"),
    ("Prop_SkullTrophy", prop_skull_trophy, "Socket_Belt"),
    ("Prop_GreatAxe", prop_great_axe, "Socket_RightHand"),
    ("Prop_BoneCrown", prop_bone_crown, "Socket_Helm"),
    ("Prop_SkullPauldron", prop_skull_pauldron, "Socket_LeftShoulder"),
    ("Prop_ChiefBuckle", prop_chief_buckle, "Socket_Belt"),
    ("Prop_WarBanner", prop_war_banner, "Socket_Back"),
    ("Prop_Shortbow", prop_shortbow, "Socket_LeftHand"),
    ("Prop_Arrow", prop_arrow, "Socket_RightHand"),
    ("Prop_Quiver", prop_quiver, "Socket_Back"),
    ("Prop_ShamanStaff", prop_shaman_staff, "Socket_RightHand"),
    ("Prop_ShamanHeaddress", prop_shaman_headdress, "Socket_Helm"),
]


def attach(ob, socket):
    rig = bpy.data.objects[RIG]
    bone = rig.data.bones[socket]
    ob.parent = rig
    ob.parent_type = 'BONE'
    ob.parent_bone = socket
    ob.matrix_parent_inverse = Matrix.Identity(4)
    ob.matrix_basis = Matrix.Translation((0, -bone.length, 0))


def build_prop(name, fn, socket, mats, coll):
    rig = bpy.data.objects[RIG]
    b, space = fn()
    if space == 'world':
        M = rig.matrix_world @ rig.data.bones[socket].matrix_local
        bmesh.ops.transform(b.bm, matrix=M.inverted(), verts=b.bm.verts[:])
    ob = _finish(name, b, coll, mats)
    attach(ob, socket)
    ob["socket"] = socket
    return ob


def build_gear():
    import gob_common
    gob_common.CAPK = 2
    mats = build_materials()
    oc = get_coll("GOB_Outfit")
    pc = get_coll("GOB_Props")
    surf = BodySurface()
    try:
        outfits = [build_loincloth(surf, mats, oc), build_harness(surf, mats, oc), build_wraps(surf, mats, oc),
                   build_fur_mantle(surf, mats, oc), build_shaman_cloak(surf, mats, oc)]
    finally:
        surf.free()
    props = [build_prop(n, f, s, mats, pc) for n, f, s in PROPS]
    gob_common.CAPK = 4
    return outfits, props


# ----------------------------------------------------------------------------------------- atlas bake
def uv_report(objs):
    """Islands per object and faces left without UVs (all loops at 0,0), which should be none."""
    out = {}
    for o in objs:
        me = o.data
        uv = me.uv_layers.active
        if uv is None:
            out[o.name] = "NO UV LAYER"
            continue
        co = np.empty(len(me.loops) * 2, dtype=np.float32)
        uv.data.foreach_get("uv", co)
        co = co.reshape(-1, 2)
        bad = sum(1 for p in me.polygons if not np.any(co[p.loop_start:p.loop_start + p.loop_total]))
        out[o.name] = bad
    return {k: v for k, v in out.items() if v}


def bake_gear(objs, size=1024, name="T_Goblin_Gear", samples=24, margin=0.0035):
    """Pack the construction UVs of all gear into one atlas (even texel density) and bake the painted materials."""
    os.makedirs(TEX_DIR, exist_ok=True)
    img = bpy.data.images.get(name)
    if img is not None:
        bpy.data.images.remove(img)
    img = bpy.data.images.new(name, size, size, alpha=True)     # alpha marks the islands for fill_gutters
    missing = uv_report(objs)
    if missing:
        print("gear faces without UVs:", missing)
    vl = bpy.context.view_layer
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for o in objs:
        o.select_set(True)
    vl.objects.active = objs[0]
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.select_all(action='SELECT')
    bpy.ops.uv.average_islands_scale()
    bpy.ops.uv.pack_islands(margin=margin, rotate=True)
    bpy.ops.object.mode_set(mode='OBJECT')
    mats = {m for o in objs for m in o.data.materials if m is not None}
    for m in mats:
        nt = m.node_tree
        node = nt.nodes.get("BAKE_TARGET") or nt.nodes.new('ShaderNodeTexImage')
        node.name = "BAKE_TARGET"
        node.image = img
        nt.nodes.active = node
    scn = bpy.context.scene
    prev = scn.render.engine
    scn.render.engine = 'CYCLES'
    scn.cycles.samples = samples
    # rest pose for the bake
    rig = bpy.data.objects[RIG]
    prev_pose = rig.data.pose_position
    rig.data.pose_position = 'REST'
    bpy.ops.object.bake(type='EMIT', margin=4, use_clear=True)
    rig.data.pose_position = prev_pose
    scn.render.engine = prev
    fill_gutters(img)
    img.filepath_raw = os.path.join(TEX_DIR, name + ".png")
    img.file_format = 'PNG'
    img.save()
    # swap the painted source materials for the single game material
    gm = bpy.data.materials.get("M_Goblin_Gear") or bpy.data.materials.new("M_Goblin_Gear")
    gm.use_nodes = True
    nt = gm.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.inputs['Roughness'].default_value = 0.8
    tex = nt.nodes.new('ShaderNodeTexImage')
    tex.image = img
    nt.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])
    for o in objs:
        o.data.materials.clear()
        o.data.materials.append(gm)
        for p in o.data.polygons:
            p.material_index = 0
    return img.filepath_raw
