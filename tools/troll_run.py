"""Headless driver for the troll (src/troll_build.py):

    blender.exe -b --factory-startup --python tools/troll_run.py -- build review export anims
    blender.exe -b blender/troll.blend --python tools/troll_run.py -- review
    blender.exe -b blender/troll.blend --python tools/troll_run.py -- anims anim_review

Steps, in the order given: build (body, rig, weights, skin, shape keys, gear, atlas), review (renders/troll_*.png:
views, close-ups, UV layouts, size comparison, game camera, test poses), export (export/Troll/), anims (the troll's own
clips, src/troll_anim.py: Roar and ClubDrag keyed, renders/anim/troll_clips_report.json, export/Troll/Anims/),
anim_review (renders/anim/troll_*: frame strips, close-ups, the game camera). The file is saved as blender/troll.blend
afterwards (unless 'nosave'), with the Troll scene on screen.
"""
import os, sys, time, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import bpy
import troll_build as T
import troll_anim as TA

steps = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
t0 = time.time()
out = {}
for st in steps:
    t = time.time()
    if st == "build":
        T.setup_file()
        out[st] = T.build_all()
    elif st == "review":
        out[st] = T.review()
        out["after_review"] = {k: v for k, v in T.LAST.items() if k == "arms_down"}
    elif st == "export":
        out[st] = T.export()
    elif st == "anims":
        TA.build_all()
        out[st] = TA.report()
        out["anims_export"] = TA.export_clips()
    elif st == "anim_review":
        out[st] = TA.review()
    elif st == "nosave":
        continue
    else:
        raise SystemExit("unknown step " + st)
    print(f"STEP {st} {time.time() - t:.1f}s", flush=True)
if "nosave" not in steps:
    win = bpy.context.window
    if win is not None and T.SCENE in bpy.data.scenes:
        win.scene = bpy.data.scenes[T.SCENE]
    T.save()
print("RESULT " + json.dumps(out, default=str))
print(f"DONE {time.time() - t0:.1f}s")
