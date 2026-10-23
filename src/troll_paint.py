"""Troll skin and shape keys.

The goblin's painter (gob_paint) runs on the troll: its masks (ears, nose, nails, knuckles, belly, the per-texel
mouth) read each vertex's goblin-space position (troll_body.transfer_gob_co), so they land where they do on the goblin.
On top comes the troll's own skin, sampled in troll space: stony grey-blue with darker blotches, moss on the back,
shoulders and crown, warts and fine cracks, a paler belly, dark horn nails, yellow eyes. The colours are my call
(not reviewed by Daniel): the goblins are olive green, and a troll must not read as a big goblin at the game camera.
"""
import bpy, math, os
import numpy as np
from gob_common import smoothstep
import gob_paint as GP
import gob_shapes
import troll_body as TB

hexc = GP.hexc
TPAL = dict(GP.PAL)
TPAL.update({
    'skin': hexc('#5c6a6e'), 'skin_dark': hexc('#3c474c'), 'skin_light': hexc('#7a8686'),
    'belly': hexc('#8c8b7b'), 'red': hexc('#64454a'), 'blush': hexc('#5d4b4d'),
    'nail': hexc('#26211b'), 'hand': hexc('#4a565b'), 'wart': hexc('#4a5651'),
    'iris': hexc('#d4a62c'), 'iris_rim': hexc('#6e480c'), 'sclera': hexc('#b9ae7c'),
})
BLOTCH, MOSS, MOSS_DARK = hexc('#323d43'), hexc('#566436'), hexc('#3a4526')
WART_HI, CRACK = hexc('#7f8a80'), hexc('#2b3438')


def _mix(a, b, t):
    t = np.clip(t, 0, 1)[:, None]
    return a * (1 - t) + b * t


def troll_colors(co, gco, no, e, warp):
    """co: troll-space positions, gco: goblin-space positions of the same vertices."""
    S = warp.p['S']
    col = GP.body_colors(gco, no, e, pal=TPAL, nco=co / S)
    x, y, z = co.T
    face = smoothstep(warp.J[2] + 0.02, warp.J[2] + 0.10, z) * smoothstep(-0.05, -0.15, y - warp.J[1])
    # big dark blotches, broken up
    b1 = GP.vnoise(co, 1.8, 11)
    b2 = GP.vnoise(co, 5.5, 12)
    col = _mix(col, BLOTCH, 0.55 * smoothstep(0.10, 0.45, b1 + 0.4 * b2))
    # moss where rain and dirt sit: shoulders, upper back, crown, outsides of the thighs
    up = np.clip(no[:, 2] * 0.8 + no[:, 1] * 0.5, 0, 1)
    region = smoothstep(warp.hip_z + 0.35, warp.hip_z + 0.6, z) * (1 - 0.7 * face)
    m = GP.vnoise(co, 4.0, 13) + 0.5 * GP.vnoise(co, 12.0, 14)
    moss = region * smoothstep(0.15, 0.55, up) * smoothstep(-0.05, 0.35, m)
    col = _mix(col, MOSS, 0.65 * moss)
    col = _mix(col, MOSS_DARK, 0.4 * moss * smoothstep(0.3, 0.7, GP.vnoise(co, 30.0, 15)))
    # warts: small pale tops with a dark rim below (lit from above)
    w = GP.vnoise(co, 30.0, 5) + 0.25 * GP.vnoise(co, 3.0, 6)
    top = smoothstep(0.50, 0.58, w)
    rim = smoothstep(0.42, 0.50, w) * (1 - top)
    col = _mix(col, CRACK, 0.30 * rim)
    col = _mix(col, WART_HI, 0.40 * top * smoothstep(-0.3, 0.6, no[:, 2] + 0.3))
    # stony grain: fine light and dark speckle
    g = GP.vnoise(co, 55.0, 8)
    col = col * (1 + 0.10 * np.clip(g, -1, 1))[:, None]
    return np.clip(col, 0, 1)


def paint_sources(hi, eyes_hi, warp):
    co, no, e = GP.mesh_arrays(hi.data)
    gco, _ = TB.gob_co(hi)
    S = warp.p['S']
    ao = GP.ray_ao(hi, co, no, dist=0.12 * S)
    ao = GP.smooth_vals(ao, e, len(co), it=2)
    cav = GP.smooth_vals(GP.curvature(co, no, e), e, len(co), it=2) * S     # curvature scales as 1 / size
    col = GP.shade(troll_colors(co, gco, no, e, warp), co, no, ao, cav, e)
    GP.write_color(hi.data, "paint", col)
    eco, eno, ee = GP.mesh_arrays(eyes_hi.data)
    ecol = GP.shade(GP.eye_colors(TB.eye_gob_co(eyes_hi, warp), pal=TPAL), eco, eno, np.ones(len(eco)),
                    np.zeros(len(eco)), ee)
    GP.write_color(eyes_hi.data, "paint", ecol)
    return {"hi_verts": len(co), "ao_mean": float(ao.mean())}


def paint_and_bake(body, hi, eyes_hi, warp, tex=1024):
    """Paint the dense copies, unwrap the game body along the goblin's seams, bake T_Troll_Skin, paint the mouth."""
    S = warp.p['S']
    rep = paint_sources(hi, eyes_hi, warp)
    gco, _ = TB.gob_co(body)
    GP.unwrap(body, pos=gco)
    rep["texture"] = GP.bake(body, [hi, eyes_hi], "T_Troll_Skin", size=tex, material_name="M_Troll_Skin",
                             cage=0.011 * S, ray=0.035 * S)       # the coarser troll needs a deeper cage than the goblin
    rep["mouth_texels"] = GP.paint_mouth(body, "T_Troll_Skin", pos_attr="gob_co")
    return rep


# ---------------------------------------------------------------------------------------------- shape keys
def add_body_keys(body, warp):
    """The goblin's keys, in goblin space, carried into troll space: Fat / Skinny / Brawny push along the normals by
    the goblin's amounts times the troll's growth; the ear keys move goblin-space ears and warp them back."""
    co, no = gob_shapes._arrays(body)
    gco, part = TB.gob_co(body)
    eyes = gob_shapes._eye_mask(body)
    fat, skinny, brawny = gob_shapes.build_amounts(gco)
    k = warp.p['S'] * 0.9
    for a in (fat, skinny, brawny):
        a[eyes] = 0
    head = (part == TB.PART_IDS['head']) & ~eyes

    def ear_key(moved):
        out = co.copy()
        d = warp.head(moved[head]) - warp.head(gco[head])
        out[head] = co[head] + d
        return out
    keys = {
        "Fat": co + no * (fat * k)[:, None],
        "Skinny": co + no * (skinny * k)[:, None],
        "Brawny": co + no * (brawny * k)[:, None],
        "EarsDroop": ear_key(gob_shapes.ear_droop(gco)),
        "EarTornL": ear_key(gob_shapes.ear_torn(gco, 1)),
        "EarTornR": ear_key(gob_shapes.ear_torn(gco, -1)),
    }
    gob_shapes._set_keys(body, keys)
    return {kk: round(float(np.abs(v - co).max()), 4) for kk, v in keys.items()}
