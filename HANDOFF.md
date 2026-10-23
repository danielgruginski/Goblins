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
- **UVs are never automatic:**
  - a new gear builder must lay out its UVs (use `grid_faces`, `_slab`, `box`, or the `calc_uvs` primitives);
    `gob_gear.uv_report` lists faces left without UVs and `bake_gear` prints them;
  - the body's seams come from skin weights in `gob_paint.mark_body_seams`;
  - after rebuilding textures, look at the PNGs themselves and at a UV layout (`bpy.ops.uv.export_layout`), not
    only at renders. The first unwrap was a smart-UV mess that renders hid (Daniel caught it).
- **Effects** are objects named `FX_*`. `GoblinAppearance` leaves them out of the merged mesh.
- **Unity:**
  - if bones are renamed, delete `Goblin.fbx.meta` before reimporting;
  - the Jaw must be pinned to `Jaw` (`GoblinModelPostprocessor`);
  - Goblin*.fbx and Models/Props/*.fbx import Read/Write (`GoblinModelPostprocessor`): `GoblinAppearance` merges
    the parts at run time and must read their meshes, else a goblin in a game build merges to nothing;
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

- dead goblins (2026-10-02): `Editor/GoblinCorpses.cs`, Tools > Goblins > Bake Dead Goblins: four rolled goblins
  (spearman, archer, swordsman, unarmed) posed at the last frame of Human Animations death clips and baked into
  static props, `Prefabs/Corpses/Goblin_Dead_1..4` (6-8k tris, a low box collider). MedievalSetting's caves place
  them as loot. The animator must be set to always animate for the bake (no camera sees the preview scene).
  `GoblinAppearance` now destroys with DestroyImmediate outside play mode (rolling a look in the editor).

- crossbow clips (2026-10-04, for the RPG's humans): `src/gob_crossbow.py`, scene **Goblin_Crossbow** (the plain
  goblin with a goblin-sized copy of the weapon kit's light crossbow), `Goblin@Crossbow_Ready` / `_Shoot`; checked on
  the human in Unity (aim at the cheek, spanning nose down, a bolt laid) and shooting in play mode. `export_clips` now
  takes the frame range from the scene it runs in (it used the archer scene's, and the ready loop came out 94 frames).
  The rig is left on `Crossbow_Shoot` for viewing: `gob_anim.clear()` before exporting the character.

- warg riders (2026-10-18, Daniel: "goblin warg riders ... complete with animations"; all clips ours): `src/gob_ride.py`,
  scene **Goblin_Warg** (the warg appended from Beasts' `beasts_unsaved_2026-10-12_warg.blend`; `GoblinRider` = a copy
  of GoblinRig parented to the warg's `Socket_Saddle`, dressed with copies of the body and gear). 15 clips
  `Goblin@WargRider_*`: one per warg clip (Idle, IdlePant, Walk, Trot, Run, Bite, Lunge, Threat, Howl, Hit, Death),
  keyed every frame in saddle space: a damped torso lagging the saddle's accelerations, head level, feet on the
  stirrup treads and the left fist on the reins read off the deformed tack each frame, per-clip accents (whoop,
  crouch, levelled spear), and Death throws the goblin off the warg's high side; plus Slash (sword), Thrust (spear),
  Flinch (upper-body overlays) and Fall (played off the seat). `gob_ride.build_all()`, `gob_ride.render_sheet(...)`,
  export with the **Goblin** scene on screen: `gob_ride.export_clips()`. In MedievalSetting: `Beasts.MountedRider`
  + game-side `Assets/Game/Riders` (`RiderSetup.cs`, prefabs WargRider_Spear / WargRider_Sword, `Riders_Test`).
  Gotcha: Blender 4.4 action slots -- an action keyed on GoblinRider binds to GoblinRig only through its slot
  (`gob_anim.use` assigns it now; before, the exports baked the T-pose).
  Same day (Daniel: "the spear swirls wildly in the hand after the thrust"): the thrust is underhand now (the grip
  the fist has on the upright spear; the overhand stab asked for a half turn round the shaft), the hand's roll is the
  least rotation from the resting grip (`_knuckles_for`), and own clips key every frame between the key poses
  (`build_own`: matrices eased, turns slerped, the IK solving each frame).

- troll (2026-10-23, a unit from Daniel's card game: "Trolls would look like goblins, slender with long arms and legs,
  may be hard to animate those though"; "keep moving on the creatures", "don't bother with adding them to the game,
  build the creatures"). The plan he saw: start from the approved goblin body, stretch it to about 2.4–2.6 m with long
  arms and legs, test whether bought Humanoid clips retarget. Built (README > Troll):
  - `src/troll_body.py` (`TrollWarp`: goblin space -> troll space per part, the troll's bone table and IK poles, the
    goblin-space position of every troll vertex), `troll_paint.py` (skin, shape keys), `troll_gear.py` (club, hair,
    loincloth, own atlas), `troll_build.py` (build, review renders, size comparison, game camera, test poses, export),
    `tools/troll_run.py` (headless). Own file `blender/troll.blend` (scenes Troll, Troll_Compare, Troll_Game), so the
    live goblins.blend is never saved over; built headless while another session had the live Blender.
  - The goblin modules only gained optional parameters (`gob_body.build_body` warp / names / eyes / decimation weights,
    `gob_rig.build_armature` name / table / IK rows, `gob_paint` palette, noise and seam positions, bake cage and ray,
    a position attribute for the mouth; `gob_gear` body, rig and gear material names). Checked: a goblin
    `gob_build.build_all()` with the old and the new code (textures redirected to a scratch folder) gives the same body
    geometry, weights, shape keys, dense-mesh paint and rig.
  - Unity: `TrollSetup.cs` (Tools > Goblins > Rebuild Troll, auto once), `GoblinModelPostprocessor` also takes
    `Troll*.fbx` (Humanoid, Jaw pin, Read/Write) and `Goblins/Troll/Models/Props/`, `GoblinAppearance.bodyName`
    (default GoblinBody), `GoblinPosture.Apply()` / `GoblinTwoHandGrip.Apply()` for tools that sample clips themselves.
    The install script's `-Troll` copies the scripts and the troll only. Compiled offline against MedievalSetting's
    editor assemblies (no output in the project) and run in the scratch `unity_verify` project in batch mode:
    `Unity.exe -batchmode -projectPath unity_verify -executeMethod Goblins.EditorTools.TrollSetup.Build -quit`
    (avatar valid, 49 bones, Jaw -> Jaw, 7,384 triangles, 2.49 m; clip numbers in README > Troll). unity_verify now
    holds the current goblin scripts, the troll and ten Kevin clip FBX copied from MedievalSetting (with HumanM_Model and
    the full-body mask, which their import settings need).
  - My calls, not reviewed by Daniel: the stony grey-blue skin with moss (to read apart from the olive goblins at the
    game camera), the branch club, the hair tuft, the hide loincloth, the bulbous nose and level ears, the setup's
    look table (club always, hair 2:1, Skinny 30% / Brawny 25% / Fat 10%, Moss / Dark / Stone tints).
  - Gotchas:
    - **The goblin build is not bit-exact run to run** (seen with the old code too): UV packing, the outfits and props
      projected on the body (FurMantle, ShamanCloak, Harness, Sack, Quiver move up to ~9 mm), their weights, and so the
      textures. Compare builds numerically (geometry, weights, keys, paint), not by file hashes.
    - The fused troll has no part layers (voxel remesh drops attributes): `transfer_gob_co` takes the goblin-space
      position and the part from the nearest point of the warped parts (`TRL_Parts` keeps them as attributes).
    - The goblin's `LM['nose_tip']` is the end of the nose's tip cap: scaling along the nose axis squashed the cap flat
      until the cap was scaled with the width (`nose_end` = the last loft row).
    - The troll needs a deeper bake cage (0.011·S / 0.035·S): the goblin's (0.008 / 0.025, scaled) left black texels.
    - Previewing shape keys: reset the loincloth's keys with the body's; a leftover Skinny on the outfit pulls the belt
      into the body.
    - Kevin clips in a scratch project: their metas copy the avatar of `Models/HumanM_Model.fbx` and use
      `Avatar Masks/Human Body Full Mask.mask`; copy both (with metas) or the clips import without a human avatar.

## Open / next

- **Troll:**
  - installed in MedievalSetting (`-Troll`, Tools > Goblins > Rebuild Troll; checked in cs:82), not in the game, not
    played;
  - two-handed clips: Attack2H02's chop drives the club's tip 0.41 m into the ground, Attack2H04 leaps 1 m and spreads
    the fists 1.27 m; so `TrollAnims` (2026-10-23, README "The troll's animation set") swings one-handed only
    (Attack1H01/03/05_R); a two-handed troll needs a ground clamp or left-hand IK;
  - death clips sink the troll up to 0.42 m into the ground (the goblin 0.26 m): dead trolls as props would need the
    `GoblinCorpses` lift;
  - the hair reads as a flat cap from the front; the eyes are small and the lids subtle; the face shows facets up
    close (5,336-triangle body); 12 black texels left in the skin bake;
  - no troll clips of its own (roar, club drag), no LODs.

- **Still to build:** bard, grenadier (medieval firepots or bombs, with a throw clip from `gob_anim`); a mounted
  archer (warg riders have spear and sword only).
- **Shaman:** the Chant ring has no gameplay effect yet; hook `GoblinShaman.Cast`. The Hex bolt flies along the
  goblin's forward, not at a target.
- **Archer:** two fixed aim heights (level and 35°). The arrow vanishes when an archer switches to walking.
- **Shoulder blades:** faint in shade. The plate offset is in `gob_body.build_torso`.
- **Hands:** 12 tiny faces fold over in the thumb and index crease. There are no LODs.

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
- **Troll:**
  - Blender: `tools/troll_run.py -- build review export`; the build report should show `weights.unweighted 0`,
    `uv_missing {}`, `tris_total` ~7,400; look at `renders/troll_*` (face, hands, UV layouts, `troll_game_22m_x4`,
    the `troll_pose_*_close` joints) at full size;
  - Unity: `Logs/TrollSetup/setup_report.txt` should show `avatar valid=True human=True bones=49 jaw=Jaw`, every clip
    `human=True`, and per-clip numbers like README > Troll's table; look at `troll_lineup*.png` and `troll_clip_*.png`.
