"""Headless driver for the troll (src/troll_build.py):

    blender.exe -b --factory-startup --python tools/troll_run.py -- build review export
    blender.exe -b blender/troll.blend --python tools/troll_run.py -- review

Steps, in the order given: build (body, rig, weights, skin, shape keys, gear, atlas), review (renders/troll_*.png:
views, close-ups, UV layouts, size comparison, game camera, test poses), export (export/Troll/). The file is saved as
blender/troll.blend afterwards (unless 'nosave'), with the Troll scene on screen.
"""
import os, sys, time, json
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
import bpy
import troll_build as T

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
    elif st == "nosave":
        continue
    else:
        raise SystemExit("unknown step " + st)
    print(f"STEP {st} {time.time() - t:.1f}s", flush=True)
if "nosave" not in steps:
    T.save()
print("RESULT " + json.dumps(out, default=str))
print(f"DONE {time.time() - t0:.1f}s")
