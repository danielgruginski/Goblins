using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;

namespace Goblins.EditorTools
{
    /// <summary>
    /// Tools > Goblins > Build Animation Test Scene: clip pools from the Kevin Iglesias Human Animations pack plus
    /// the goblin's own clips (Models/Anims, the bow and shaman clips made in Blender) as Assets/Goblins/Animation/GoblinAnims_*.asset,
    /// and Scenes/Goblins_AnimationTest.unity, where chiefs, shamans, spearmen, swordsmen, archers and unarmed goblins play
    /// random clips. Press Play to watch.
    /// </summary>
    public static class GoblinAnimationTestBuilder
    {
        const string ClipRoot = "Assets/Kevin Iglesias/Human Animations/Animations/Male";
        const string SetDir = "Assets/Goblins/Animation";
        const string ScenePath = "Assets/Goblins/Scenes/Goblins_AnimationTest.unity";

        class P
        {
            public string name, next;
            public float w, h0 = 3, h1 = 6, after;
            public string[] clips;
            public bool seq, moves, twoH, upright;
            public P(string name, float w, params string[] clips) { this.name = name; this.w = w; this.clips = clips; }
        }

        static readonly string[] Walk = { "Walk01_Forward [RM]", "Walk01_ForwardLeft [RM]", "Walk01_ForwardRight [RM]" };
        static readonly string[] Run = { "Run01_Forward [RM]", "Run01_ForwardLeft [RM]", "Run01_ForwardRight [RM]" };
        static readonly string[] Deaths = { "CombatDeath01", "CombatDeath02", "CombatDeath03", "CombatDeath04", "Death01", "Death02" };

        static P[] PolearmPools() => new[]
        {
            new P("Guard", 2.5f, "CombatIdlePolearm01") { h0 = 2, h1 = 4, twoH = true },
            new P("Idle", 1.2f, "Idle01", "Idle02", "IdleWounded01") { h0 = 3, h1 = 5 },
            new P("Thrust", 3f, "AttackPolearm01", "AttackPolearm02", "AttackPolearm03", "AttackPolearm04") { next = "Guard", twoH = true },
            new P("Parry", 0.8f, "ParryPolearm01 - Loop", "ParryPolearm01 - Hit") { seq = true, h0 = 1, h1 = 2, next = "Guard", twoH = true },
            new P("Hurt", 0.8f, "CombatDamage01", "CombatDamage02", "Stun01"),
            new P("Walk", 2f, Walk) { moves = true, h0 = 3, h1 = 6 },
            new P("Run", 1.2f, Run) { moves = true, h0 = 2, h1 = 4 },
            new P("Cheer", 0.8f, "Cheer01", "Cheer02", "Angry01", "Angry02"),
            new P("Death", 0.35f, Deaths) { after = 1.5f, next = "GetUp" },
            new P("Knockdown", 0.3f, "Knockdown01 - Fall", "Knockdown01 - Ground", "Knockdown01 - StandUp") { seq = true, h0 = 1, h1 = 2 },
            new P("GetUp", 0f, "Knockdown01 - StandUp"),
        };

        static P[] ChiefPools() => new[]
        {
            new P("Guard", 2f, "CombatIdle2H01") { h0 = 2, h1 = 4, twoH = true },
            new P("Cleave", 2.5f, "Attack2H01", "Attack2H02", "Attack2H03", "Attack2H04") { next = "Guard", twoH = true },
            new P("Parry", 0.6f, "Parry2H01 - Loop", "Parry2H01 - Hit") { seq = true, h0 = 1, h1 = 2, next = "Guard", twoH = true },
            new P("Command", 1.6f, "Talk01", "Talk02", "HandWave01", "Question01", "HeadNod01", "HeadShake01"),
            new P("Roar", 1.3f, "Angry01", "Angry02", "Cheer01", "Cheer02"),
            new P("Idle", 1f, "Idle01", "Idle02") { h0 = 3, h1 = 5 },
            new P("Walk", 1.5f, Walk) { moves = true, h0 = 3, h1 = 6 },
            new P("Run", 0.6f, Run) { moves = true, h0 = 2, h1 = 3 },
            new P("Hurt", 0.4f, "CombatDamage01", "CombatDamage02") { next = "Guard" },
            new P("Death", 0.15f, Deaths) { after = 1.5f, next = "GetUp" },
            new P("GetUp", 0f, "Knockdown01 - StandUp"),
        };

        static P[] SwordShieldPools() => new[]
        {
            new P("Guard", 2.5f, "CombatIdle1H01") { h0 = 2, h1 = 4 },
            new P("Idle", 1.2f, "Idle01", "Idle02", "IdleWounded01") { h0 = 3, h1 = 5 },
            new P("Slash", 3f, "Attack1H01_R", "Attack1H02_R", "Attack1H03_R", "Attack1H04_R", "Attack1H05_R") { next = "Guard" },
            new P("ShieldBash", 1f, "AttackShield01", "AttackShield02") { next = "Guard" },
            new P("Block", 1.2f, "BlockShield01 - Loop", "BlockShield01 - Hit") { seq = true, h0 = 1, h1 = 2.5f, next = "Guard" },
            new P("Parry", 0.7f, "Parry1H01_R - Loop", "Parry1H01_R - Hit") { seq = true, h0 = 1, h1 = 2, next = "Guard" },
            new P("Hurt", 0.8f, "CombatDamage01", "CombatDamage02", "Stun01") { next = "Guard" },
            new P("Walk", 2f, Walk) { moves = true, h0 = 3, h1 = 6 },
            new P("Run", 1.2f, Run) { moves = true, h0 = 2, h1 = 4 },
            new P("Cheer", 0.8f, "Cheer01", "Cheer02", "Angry01", "Angry02"),
            new P("Death", 0.35f, Deaths) { after = 1.5f, next = "GetUp" },
            new P("Knockdown", 0.3f, "Knockdown01 - Fall", "Knockdown01 - Ground", "Knockdown01 - StandUp") { seq = true, h0 = 1, h1 = 2 },
            new P("GetUp", 0f, "Knockdown01 - StandUp"),
        };

        static P[] ArcherPools() => new[]
        {
            new P("Ready", 1.5f, "Bow_Ready") { h0 = 1, h1 = 2.5f, upright = true },
            new P("Shoot", 3f, "Bow_Shoot") { next = "Ready", upright = true },
            new P("Volley", 2f, "Bow_Volley") { next = "Ready", upright = true },
            new P("Salvo", 1f, "Bow_Volley", "Bow_Volley", "Bow_Shoot") { seq = true, next = "Ready", upright = true },
            new P("Idle", 0.7f, "Idle01", "Idle02") { h0 = 3, h1 = 5 },
            new P("Walk", 1.4f, Walk) { moves = true, h0 = 3, h1 = 6 },
            new P("Run", 0.6f, Run) { moves = true, h0 = 2, h1 = 3 },
            new P("Cheer", 0.5f, "Cheer01", "Laugh01", "Angry01"),
            new P("Hurt", 0.5f, "CombatDamage01", "CombatDamage02"),
            new P("Death", 0.25f, Deaths) { after = 1.5f, next = "GetUp" },
            new P("GetUp", 0f, "Knockdown01 - StandUp"),
        };

        static P[] ShamanPools() => new[]
        {
            new P("Idle", 2f, "Shaman_Idle") { h0 = 2, h1 = 4, upright = true },
            new P("Hex", 3f, "Shaman_Hex") { next = "Idle", upright = true },
            new P("Chant", 2f, "Shaman_Chant") { next = "Idle", upright = true },
            new P("Mutter", 0.7f, "Talk01", "Talk02", "Question01", "HeadShake01"),
            new P("Walk", 1f, Walk) { moves = true, h0 = 3, h1 = 5 },
            new P("Hurt", 0.4f, "CombatDamage01", "CombatDamage02"),
            new P("Death", 0.2f, Deaths) { after = 1.5f, next = "GetUp" },
            new P("GetUp", 0f, "Knockdown01 - StandUp"),
        };

        static P[] UnarmedPools() => new[]
        {
            new P("Idle", 2f, "Idle01", "Idle02", "Idle01-Idle02", "Idle02-Idle01") { h0 = 3, h1 = 5 },
            new P("Talk", 2f, "Talk01", "Talk02", "Talk03", "Question01", "Question02", "HeadNod01", "HeadShake01", "HeadShake02", "HandWave01", "HandWave02"),
            new P("Emote", 1.2f, "Cheer01", "Cheer02", "Laugh01", "Angry01", "Angry02", "Fear01", "HandClap01"),
            new P("Loot", 1f, "Loot01 - Begin", "Loot01 - Loop", "Loot01 - Stop") { seq = true, h0 = 2, h1 = 4 },
            new P("Sit", 0.6f, "SitGround01 - Begin", "SitGround01 - Loop", "SitGround01 - Stop") { seq = true, h0 = 3, h1 = 6 },
            new P("Eat", 0.4f, "Eat01_R - Loop") { h0 = 2, h1 = 4 },
            new P("Beg", 0.4f, "Beg01 - Loop") { h0 = 2, h1 = 4 },
            new P("Brawl", 1f, "AttackPunch01_R", "AttackPunch02_R", "AttackPunch03_L", "AttackKick01_R", "AttackKick02_L"),
            new P("Walk", 2f, Walk) { moves = true, h0 = 3, h1 = 6 },
            new P("Run", 1f, Run) { moves = true, h0 = 2, h1 = 4 },
            new P("Sprint", 0.4f, "Sprint01_Forward [RM]") { moves = true, h0 = 1.5f, h1 = 3 },
            new P("Hurt", 0.5f, "CombatDamage01", "CombatDamage02"),
            new P("Death", 0.25f, Deaths) { after = 1.5f, next = "GetUp" },
            new P("GetUp", 0f, "Knockdown01 - StandUp"),
        };

        [MenuItem("Tools/Goblins/Build Animation Test Scene")]
        public static void BuildMenu()
        {
            if (Enumerable.Range(0, SceneManager.sceneCount).Any(i => SceneManager.GetSceneAt(i).isDirty) &&
                !EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo())
                return;
            Debug.Log(Build());
        }

        /// <summary>Builds the pools and the scene. The caller makes sure no open scene has unsaved changes.</summary>
        public static string Build()
        {
            var clips = new Dictionary<string, AnimationClip>();
            foreach (var guid in AssetDatabase.FindAssets("t:Model", new[] { ClipRoot }))
                foreach (var c in AssetDatabase.LoadAllAssetsAtPath(AssetDatabase.GUIDToAssetPath(guid)).OfType<AnimationClip>())
                    if (!c.name.StartsWith("__preview")) clips[c.name.Replace("HumanM@", "")] = c;
            if (AssetDatabase.IsValidFolder(GoblinSetup.Anims))
                foreach (var guid in AssetDatabase.FindAssets("t:Model", new[] { GoblinSetup.Anims }))
                    foreach (var c in AssetDatabase.LoadAllAssetsAtPath(AssetDatabase.GUIDToAssetPath(guid)).OfType<AnimationClip>())
                        if (!c.name.StartsWith("__preview")) clips[c.name] = c;
            var missing = new List<string>();
            AssetDatabase.DeleteAsset(SetDir + "/GoblinAnims_Armed.asset");        // replaced by the two sets below
            var polearm = MakeSet("GoblinAnims_Polearm", PolearmPools(), clips, missing);
            var swordShield = MakeSet("GoblinAnims_SwordShield", SwordShieldPools(), clips, missing);
            var unarmed = MakeSet("GoblinAnims_Unarmed", UnarmedPools(), clips, missing);
            var chief = MakeSet("GoblinAnims_Chief", ChiefPools(), clips, missing);
            var archer = MakeSet("GoblinAnims_Archer", ArcherPools(), clips, missing);
            var shaman = MakeSet("GoblinAnims_Shaman", ShamanPools(), clips, missing);

            var kinds = new[]
            {
                (prefab: AssetDatabase.LoadAssetAtPath<GameObject>("Assets/Goblins/Prefabs/Goblin_Chief.prefab"), set: chief, label: "Chief", count: 2),
                (prefab: AssetDatabase.LoadAssetAtPath<GameObject>("Assets/Goblins/Prefabs/Goblin_Shaman.prefab"), set: shaman, label: "Shaman", count: 2),
                (prefab: AssetDatabase.LoadAssetAtPath<GameObject>("Assets/Goblins/Prefabs/Goblin_Archer.prefab"), set: archer, label: "Archer", count: 6),
                (prefab: AssetDatabase.LoadAssetAtPath<GameObject>("Assets/Goblins/Prefabs/Goblin_Spearman.prefab"), set: polearm, label: "Spearman", count: 6),
                (prefab: AssetDatabase.LoadAssetAtPath<GameObject>("Assets/Goblins/Prefabs/Goblin_Swordsman.prefab"), set: swordShield, label: "Swordsman", count: 6),
                (prefab: AssetDatabase.LoadAssetAtPath<GameObject>("Assets/Goblins/Prefabs/Goblin_Base.prefab"), set: unarmed, label: "Goblin", count: 6),
            };

            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            var sun = new GameObject("Sun").AddComponent<Light>();
            sun.type = LightType.Directional;
            sun.intensity = 1.6f;
            sun.shadows = LightShadows.Soft;
            sun.transform.rotation = Quaternion.Euler(50, 200, 0);
            RenderSettings.ambientMode = AmbientMode.Trilight;
            RenderSettings.ambientSkyColor = new Color(0.62f, 0.66f, 0.72f);
            RenderSettings.ambientEquatorColor = new Color(0.45f, 0.46f, 0.42f);
            RenderSettings.ambientGroundColor = new Color(0.25f, 0.23f, 0.2f);
            var ground = GameObject.CreatePrimitive(PrimitiveType.Plane);
            ground.name = "Ground";
            ground.transform.localScale = new Vector3(4, 1, 4);
            var gm = AssetDatabase.LoadAssetAtPath<Material>("Assets/Goblins/Scenes/M_ShowcaseGround.mat");
            if (gm != null) ground.GetComponent<Renderer>().sharedMaterial = gm;

            var rng = new System.Random(7);
            var spots = new List<Vector3>();
            int total = kinds.Sum(k => k.count);
            while (spots.Count < total)
            {
                var p = new Vector3((float)(rng.NextDouble() * 2 - 1) * 6.5f, 0, (float)(rng.NextDouble() * 2 - 1) * 6.5f);
                if (p.magnitude <= 6.5f && spots.All(s => (s - p).magnitude > 1.4f)) spots.Add(p);
            }
            var root = new GameObject("Goblins").transform;
            int i = 0;
            foreach (var k in kinds)
                for (int n = 0; n < k.count; n++, i++)
                {
                    var go = (GameObject)PrefabUtility.InstantiatePrefab(k.prefab, scene);
                    go.name = k.label + "_" + n.ToString("00");
                    go.transform.SetParent(root, false);
                    go.transform.SetPositionAndRotation(spots[i], Quaternion.Euler(0, (float)rng.NextDouble() * 360f, 0));
                    var ra = go.AddComponent<GoblinRandomAnimator>();
                    ra.set = k.set;
                    ra.home = Vector3.zero;
                    ra.wanderRadius = 8.5f;
                    go.AddComponent<GoblinPosture>();
                    if (k.set == polearm || k.set == chief) go.AddComponent<GoblinTwoHandGrip>();
                }

            var cam = new GameObject("Camera").AddComponent<Camera>();
            cam.tag = "MainCamera";
            cam.fieldOfView = 35f;
            cam.farClipPlane = 300f;
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = new Color(0.47f, 0.52f, 0.58f);
            var ui = cam.gameObject.AddComponent<GoblinAnimationTestUI>();
            ui.distance = 15f;
            ui.pitch = 40f;
            EditorSceneManager.SaveScene(scene, ScenePath);
            return $"Built {ScenePath}: " + string.Join(", ", kinds.Select(k => $"{k.count} {k.label}")) + "; " +
                   (missing.Count == 0 ? "all clips found" : "MISSING clips: " + string.Join(", ", missing.Distinct()));
        }

        static GoblinAnimationSet MakeSet(string name, P[] pools, Dictionary<string, AnimationClip> clips, List<string> missing)
        {
            if (!AssetDatabase.IsValidFolder(SetDir)) AssetDatabase.CreateFolder("Assets/Goblins", "Animation");
            var path = $"{SetDir}/{name}.asset";
            var set = AssetDatabase.LoadAssetAtPath<GoblinAnimationSet>(path);
            if (set == null)
            {
                set = ScriptableObject.CreateInstance<GoblinAnimationSet>();
                AssetDatabase.CreateAsset(set, path);
            }
            set.pools = pools.Select(p => new GoblinAnimationSet.Pool
            {
                name = p.name,
                weight = p.w,
                clips = p.clips.Select(n =>
                {
                    if (clips.TryGetValue(n, out var c)) return c;
                    missing.Add(n);
                    return null;
                }).Where(c => c != null).ToArray(),
                sequence = p.seq,
                moves = p.moves,
                hold = new Vector2(p.h0, p.h1),
                holdAfter = p.after,
                next = p.next,
                twoHanded = p.twoH,
                upright = p.upright,
            }).ToArray();
            EditorUtility.SetDirty(set);
            AssetDatabase.SaveAssets();
            return set;
        }
    }
}
