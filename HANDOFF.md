# Handoff

Where the goblins stand and how to pick them up. The README is the reference: rebuild commands, sockets,
budget, Unity layout, one section per goblin type. This file holds the working agreements, the conventions that
have bitten, the open issues and the checks to run.

## Working agreements

- Daniel reviews in Unity (MedievalSetting, `Scenes/Goblins_AnimationTest`) and sends screenshots. He prefers the
  obvious fix over diagnostic measuring.
- Game budget: colony camera ~40 m at 50°, goblins 20–40 px tall, no LODs. A dressed goblin stays under ~9k
  triangles; skins are 1024², all gear shares one 2048² atlas. Report triangle counts when adding gear.
- Keep Blender work visible. Build in scenes he can open (**Goblin**, **Goblin_Archer**, **Goblin_Shaman**,
  **Goblin_Props**) and leave the working scene on screen.
- He asks for commits in batches and says when to push.
- Kevin Iglesias *Human Animations* (Asset Store) covers locomotion, melee, idles and deaths. Anything it lacks
  (bow, spells, throws, instruments) is keyframed in `src/gob_anim.py`.

## Conventions that bite

- **Props are modelled in socket space** (origin = attach point). In `Socket_RightHand` the knuckles face +X, so
  blade edges go on +X (`_edge_to_knuckles`). The left hand's knuckles face -X: left-hand props with a front and
  back (the bow) are built for that.
- **Unity mirrors X on import:** Blender local +X = Unity local -X. Runtime offsets copied from Blender
  (`GoblinArcher.stringTop`, `arrowRest`) flip X.
- **Scene visibility:** `gob_build` and `gob_export.export_all()` hide and unhide objects in the *current* view
  layer, so run them with the **Goblin** scene on screen. A window scene switch only takes effect after the MCP
  call returns, so switch in a separate call. Afterwards, re-apply the archer and shaman scene looks
  (`gob_anim.ARCHER_LOOK` / `SHAMAN_LOOK` with `hide_set(..., view_layer=...)`).
- **Full rebuilds** (`gob_build.build_all`) replace the rig object: put the clips back with `gob_anim.use(name)`.
  `GOB_Work` must be in the view layer while building (`gob_build.work_layer`).
- **Custom clips** are posed through the rig's IK from targets, not hand-set angles:
  - where the hands must be (arrow line, staff grip), where the feet stand (stance tables), and which way things
    point;
  - never straighten a leg fully: the leg IK stretches, and Unity warns "scale animation … discarded". Keep the
    hips dropped at least 0.025;
  - export with `gob_anim.export_clips` (skeleton only). In Unity the clip FBX needs `preserveHierarchy` and
    Goblin.fbx's avatar; `GoblinSetup.ConfigureClips` does both.
- **Effects** are objects named `FX_*`. `GoblinAppearance` leaves them out of the merged mesh.
- **Unity:**
  - if bones are renamed, delete `Goblin.fbx.meta` before reimporting;
  - the Jaw must be pinned to `Jaw` (`GoblinModelPostprocessor`);
  - after swapping renderers, call `Animator.Rebind()`;
  - play mode does not tick while the editor is unfocused: set `Application.runInBackground = true` for the
    session;
  - clip import warnings are in the importer's serialized `m_AnimationImportWarnings`.

## State (2026-09-26)

Done:
- generic goblin with variation and a runtime merge into one mesh;
- spearman, swordsman, chief;
- archer: short bow, 3 clips, string and arrow at runtime;
- shaman: staff, headdress, cape and paint, 3 clips, glow, hex bolt and chant ring;
- animation test scene with 28 goblins.

## Open / next

- **Still to build:** bard, grenadier (medieval firepots or bombs, with a throw clip from `gob_anim`), warg
  raider (the warg needs its own quadruped rig and a saddle socket).
- **Shaman:** the Chant ring has no gameplay effect yet; hook `GoblinShaman.Cast`. The Hex bolt flies along the
  goblin's forward, not at a target.
- **Archer:** two fixed aim heights (level and 35°). The arrow vanishes when an archer switches to walking.
- **Shoulder blades:** faint in shade. The plate offset is in `gob_body.build_torso`.
- **Atlas:** the gear atlas is fragmented (smart UV project). There are no LODs.

## Checks

- **Blender:**
  - `gob_anim.render_sheet(name, frames, cams, scene=..., look=..., skin=...)` renders clip frames to `renders/`;
  - look at new gear at full resolution before reporting.
- **Unity** (after `tools/install_to_unity.ps1` and **Tools > Goblins > Rebuild Prefabs and Showcase**):
  - `Logs/GoblinSetup/setup_report.txt` should show `avatar valid=True`, `jaw=Jaw`, and every clip `human=True`;
  - for exact frames in play mode: disable the goblin's `GoblinRandomAnimator`, play the clip through a
    manual-update `PlayableGraph`, call `GoblinArcher.Apply` / `GoblinShaman.Apply`, and render with
    `RenderPipeline.SubmitRenderRequest` (`Unity_Camera_Capture` fails in play mode).
- **Batch:** `unity/Verify/GoblinVerify.cs` in a scratch project checks the avatar, the sockets, and the
  prop-versus-embedded placement (0.000 mm).
