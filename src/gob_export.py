"""FBX export for Unity.

export/Goblin.fbx            rig + body + outfits (export_all(embed_props=True) also nests the props under their sockets)
export/Props/<Prop>.fbx      each prop alone, in socket space: parent it under the socket named in its
                             custom property "socket" with identity local position/rotation.
export/Textures/*.png        T_Goblin_Skin, T_Goblin_Gear
"""
import bpy, os, shutil
from mathutils import Matrix
from gob_common import ROOT

EXPORT = os.path.join(ROOT, "export")

FBX = dict(apply_scale_options='FBX_SCALE_ALL', axis_forward='-Z', axis_up='Y', use_armature_deform_only=True,
           add_leaf_bones=False, primary_bone_axis='Y', secondary_bone_axis='X', armature_nodetype='NULL',
           bake_anim=False, mesh_smooth_type='FACE', use_mesh_modifiers=True, use_custom_props=True,
           path_mode='STRIP', embed_textures=False)


def _select(objs):
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for o in objs:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]


def export_all(embed_props=False):
    """embed_props=True also puts every prop under its socket in Goblin.fbx (used by the unity_verify check)."""
    os.makedirs(os.path.join(EXPORT, "Props"), exist_ok=True)
    os.makedirs(os.path.join(EXPORT, "Textures"), exist_ok=True)
    rig = bpy.data.objects["GoblinRig"]
    body = bpy.data.objects["GoblinBody"]
    outfits = sorted(bpy.data.collections["GOB_Outfit"].objects, key=lambda o: o.name)
    props = sorted(bpy.data.collections["GOB_Props"].objects, key=lambda o: o.name)
    for pb in rig.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    bpy.context.view_layer.update()
    written = []
    _select([rig, body] + outfits + (props if embed_props else []))
    path = os.path.join(EXPORT, "Goblin.fbx")
    bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={'ARMATURE', 'MESH'}, **FBX)
    written.append(path)
    coll = bpy.context.scene.collection
    for p in props:
        name = p.name
        p.name = name + "__src"
        tmp = bpy.data.objects.new(name, p.data)
        tmp["socket"] = p["socket"]
        coll.objects.link(tmp)
        try:
            _select([tmp])
            path = os.path.join(EXPORT, "Props", name + ".fbx")
            bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={'MESH'}, **FBX)
            written.append(path)
        finally:
            bpy.data.objects.remove(tmp, do_unlink=True)
            p.name = name
    for fn in os.listdir(os.path.join(ROOT, "textures")):
        if fn.startswith("T_Goblin_") and fn.endswith(".png"):
            shutil.copy2(os.path.join(ROOT, "textures", fn), os.path.join(EXPORT, "Textures", fn))
    for o in bpy.context.selected_objects:
        o.select_set(False)
    import gob_build
    gob_build.hide_alternates()
    return written
