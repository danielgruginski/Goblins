"""Rebuild the goblin from scratch: body -> rig -> skin -> skin texture -> gear -> gear atlas. Run inside Blender."""
import bpy
import gob_body, gob_rig, gob_paint, gob_gear, gob_shapes


def join_into(target, other):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    other.select_set(True)
    target.select_set(True)
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.join()


def work_layer(on):
    """GOB_Work (dense bake sources) must be in the view layer while building; it is excluded afterwards."""
    lc = bpy.context.view_layer.layer_collection.children.get("GOB_Work")
    if lc is not None:
        lc.exclude = not on


def build_base(bake=True, body_tris=3300, tex=1024):
    work_layer(True)
    body, eyes = gob_body.build_body(target_tris=body_tris)
    rig = gob_rig.build_armature()
    gob_rig.skin(body, eyes, rig)
    gob_rig.smooth_weights(body, iterations=4, factor=0.5)
    gob_rig.clean_weights(body)
    eyes_hi = bpy.data.objects["GOB_EyesHi"]
    join_into(body, eyes)
    report = gob_rig.weight_report(body)
    if bake:
        hi = bpy.data.objects["GOB_BodyHi"]
        report.update(gob_paint.paint_sources(hi, eyes_hi))
        gob_paint.unwrap(body)
        report["texture"] = gob_paint.bake(body, [hi, eyes_hi], "T_Goblin_Skin", size=tex)
        report["mouth_texels"] = gob_paint.paint_mouth(body)
        report["warpaint"] = gob_paint.bake_skin_variant(body, hi, eyes_hi, 'warpaint', "T_Goblin_Skin_Warpaint", size=tex)
        report["chiefpaint"] = gob_paint.bake_skin_variant(body, hi, eyes_hi, 'chief', "T_Goblin_Skin_Chief", size=tex)
        report["shamanpaint"] = gob_paint.bake_skin_variant(body, hi, eyes_hi, 'shaman', "T_Goblin_Skin_Shaman", size=tex)
    report["shape_keys"] = gob_shapes.add_body_keys(body)
    eyes_hi.hide_set(True)
    return body, rig, report


def build_all(body_tris=3300, tex=1024, gear_tex=2048):
    body, rig, report = build_base(body_tris=body_tris, tex=tex)
    outfits, props = gob_gear.build_gear()
    gob_shapes.add_outfit_keys(body, outfits)
    report["gear_texture"] = gob_gear.bake_gear(outfits + props, size=gear_tex)
    report["tris"] = {o.name: sum(len(p.vertices) - 2 for p in o.data.polygons) for o in [body] + outfits + props}
    report["tris_total"] = sum(report["tris"].values())
    hide_alternates()
    work_layer(False)
    return report



def hide_alternates():
    """The Blender preview shows the spearman; alternate props on the same socket stay hidden."""
    for n in gob_gear.PREVIEW_HIDDEN:
        ob = bpy.data.objects.get(n)
        if ob is not None:
            ob.hide_set(True)
            ob.hide_render = True
