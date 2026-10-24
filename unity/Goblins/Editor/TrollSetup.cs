using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Animations;
using UnityEngine.Playables;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;

namespace Goblins.EditorTools
{
    /// <summary>
    /// The troll (a unit from Daniel's card game: the goblin grown to ~2.5 m in Blender, src/troll_build.py), from the
    /// files in Assets/Goblins/Troll (Models/Troll.fbx, Models/Props/Prop_Troll*.fbx, Textures/T_Troll_*.png):
    ///
    ///   Materials   M_Troll_Skin (+ Moss, Dark, Stone tints), M_Troll_Gear
    ///   Prefabs     Troll: Humanoid Animator, GoblinAppearance (TrollBody, skins, club, hair or none, build shapes),
    ///               GoblinPosture (the goblin hunch), GoblinTwoHandGrip; Props/Prop_TrollClub, Prop_TrollHair
    ///
    /// Then it checks retargeting without touching any open scene: in a preview scene the troll plays Kevin Iglesias
    /// Human Animations clips (idle, walk, run, a two-handed overhead attack, a hit, a death) through a PlayableGraph with
    /// GoblinPosture applied, and Logs/TrollSetup gets a lineup, the game camera (22 m, 50 deg, fov 30), a strip of
    /// frames per clip and setup_report.txt (avatar, sizes, and per clip: feet against the ground, hands against the
    /// legs, the two fists on the club, the club's tip, the head's height; the goblin's numbers beside them when
    /// Goblin_Base is installed). Tools > Goblins > Rebuild Troll; it runs by itself once after the first install.
    ///
    /// The troll's own clips (2026-10-23, src/troll_anim.py): Models/Anims/Troll@Roar.fbx and Troll@ClubDrag.fbx import
    /// Humanoid on Troll.fbx's avatar with the loop, root motion and events of troll_clips.json (the Roar event calls
    /// GoblinEvents.OnGoblinEvent("Roar")). The death clips sink the troll into the ground (a human's fall on longer
    /// limbs), so the set's deaths are grounded copies (Animation/Death02_Grounded.anim ...): the body lifted and
    /// tilted onto its support plane as it falls (GroundDeath), measured before and after.
    /// </summary>
    [InitializeOnLoad]
    public static class TrollSetup
    {
        public const string Root = "Assets/Goblins/Troll";
        const string Models = Root + "/Models";
        const string Anims = Models + "/Anims";
        const string AnimDir = Root + "/Animation";
        public const string EventFunction = "OnGoblinEvent";
        const string PropModels = Models + "/Props";
        const string Textures = Root + "/Textures";
        const string Materials = Root + "/Materials";
        const string Prefabs = Root + "/Prefabs";
        const string PropPrefabs = Prefabs + "/Props";
        public const string Model = Models + "/Troll.fbx";
        public const string PrefabPath = Prefabs + "/Troll.prefab";
        const string ClipRoot = "Assets/Kevin Iglesias/Human Animations/Animations/Male";
        const string GoblinPrefab = "Assets/Goblins/Prefabs/Goblin_Base.prefab";

        /// <summary>The checked clips: label, clip names to try, where in the clip the lineup shows it (0..1), two-handed,
        /// own (looked up among the troll's own clips: Models/Anims/Troll@*.fbx and the grounded deaths in Animation).</summary>
        static readonly (string label, string[] names, float at, bool twoHanded, bool own)[] Checks =
        {
            ("Idle", new[] { "Idle01" }, 0.3f, false, false),
            ("Walk", new[] { "Walk01_Forward [RM]", "Walk01_Forward" }, 0.25f, false, false),
            ("Run", new[] { "Run01_Forward [RM]", "Run01_Forward" }, 0.25f, false, false),
            ("Overhead", new[] { "Attack2H02" }, 0.38f, true, false),        // two-handed chop: fists over the head, then down
            ("Leap", new[] { "Attack2H04" }, 0.23f, true, false),            // the same with a leap (1 m off the ground on the troll)
            ("Swing1H", new[] { "Attack1H01_R" }, 0.3f, false, false),       // one-handed, for comparison with the two-handed grip
            ("Hit", new[] { "CombatDamage01" }, 0.2f, false, false),
            ("Death", new[] { "CombatDeath01", "Death01" }, 1f, false, false),
            // candidates for the troll's own set (2026-10-23: the two-handed chops put the club 0.4 m into the ground)
            ("Swing1H_2", new[] { "Attack1H02_R" }, 0.4f, false, false),
            ("Swing1H_3", new[] { "Attack1H03_R" }, 0.35f, false, false),
            ("Swing1H_4", new[] { "Attack1H04_R" }, 0.4f, false, false),
            ("Swing1H_5", new[] { "Attack1H05_R" }, 0.4f, false, false),
            ("Punch", new[] { "AttackPunch01_R" }, 0.3f, false, false),
            ("Hit2", new[] { "CombatDamage02" }, 0.2f, false, false),
            ("Death2", new[] { "CombatDeath02" }, 1f, false, false),
            ("Death3", new[] { "CombatDeath03" }, 1f, false, false),
            ("Death4", new[] { "CombatDeath04" }, 1f, false, false),
            ("Death5", new[] { "Death01" }, 1f, false, false),
            ("Death6", new[] { "Death02" }, 1f, false, false),
            // the troll's own (2026-10-23, Daniel: "Do the number 4")
            ("Roar", new[] { "Troll@Roar" }, 0.4f, false, true),
            ("ClubDrag", new[] { "Troll@ClubDrag" }, 0.3f, false, true),
            ("Death6G", new[] { "Death02_Grounded" }, 1f, false, true),
            ("Death2G", new[] { "CombatDeath02_Grounded" }, 1f, false, true),
        };

        /// <summary>The checks played upright (the troll's own clips carry its posture; their pools are marked upright).</summary>
        static readonly HashSet<string> Upright = new HashSet<string> { "Roar", "ClubDrag" };

        /// <summary>The set's deaths (labels of Checks) and the grounded copies made from them.</summary>
        static readonly (string src, string grounded)[] Deaths = { ("Death6", "Death6G"), ("Death2", "Death2G") };

        const float ClubReach = 1.12f;          // Prop_TrollClub: grip to the end of the knobbly head, along socket +Y

        static TrollSetup() => EditorApplication.delayCall += () => AutoBuild(20);

        static void AutoBuild(int retries)
        {
            if (!File.Exists(Model) || File.Exists(PrefabPath)) return;
            bool ready = AssetImporter.GetAtPath(Model) is ModelImporter &&
                         AssetDatabase.LoadAssetAtPath<Texture2D>(Textures + "/T_Troll_Gear.png") != null &&
                         !EditorApplication.isCompiling && !EditorApplication.isUpdating && !EditorApplication.isPlayingOrWillChangePlaymode;
            if (ready) Build();
            else if (retries > 0) EditorApplication.delayCall += () => AutoBuild(retries - 1);
        }

        static string OutDir => Path.GetFullPath(Path.Combine(Application.dataPath, "..", "Logs", "TrollSetup"));

        [MenuItem("Tools/Goblins/Rebuild Troll")]
        public static void Build()
        {
            Directory.CreateDirectory(OutDir);
            var log = new StringBuilder();
            Application.LogCallback onLog = (c, s, t) =>
            {
                // GroundDeath reads Animator.bodyPosition outside OnAnimatorIK on purpose (the sampled pose's body centre)
                if (t != LogType.Log && !c.StartsWith("Setting and getting Body Position")) log.AppendLine($"[{t}] {c}");
            };
            Application.logMessageReceived += onLog;
            try
            {
                if (!File.Exists(Model)) { log.AppendLine($"MISSING {Model}: run tools/install_to_unity.ps1 first"); return; }
                foreach (var d in new[] { Materials, Prefabs, PropPrefabs }) EnsureFolder(d);
                foreach (var guid in AssetDatabase.FindAssets("t:Texture2D", new[] { Textures }))
                {
                    var ti = (TextureImporter)AssetImporter.GetAtPath(AssetDatabase.GUIDToAssetPath(guid));
                    ti.maxTextureSize = 1024;
                    ti.sRGBTexture = true;
                    ti.mipmapEnabled = true;
                    ti.textureCompression = TextureImporterCompression.CompressedHQ;
                    ti.SaveAndReimport();
                }
                var skin = MakeMaterial("M_Troll_Skin", Textures + "/T_Troll_Skin.png");
                var gear = MakeMaterial("M_Troll_Gear", Textures + "/T_Troll_Gear.png");
                var skins = new[]                           // a material listed twice is twice as likely
                {
                    skin, skin,
                    MakeTint("M_Troll_Skin_Moss", skin, new Color(0.84f, 0.95f, 0.78f)),
                    MakeTint("M_Troll_Skin_Dark", skin, new Color(0.74f, 0.77f, 0.80f)),
                    MakeTint("M_Troll_Skin_Stone", skin, new Color(0.93f, 0.91f, 0.88f)),
                };

                ConfigureModel(Model, skin, gear, humanoid: true);
                var mi = (ModelImporter)AssetImporter.GetAtPath(Model);
                if (!mi.humanDescription.human.Any(h => h.humanName == "Jaw" && h.boneName == "Jaw"))
                    mi.SaveAndReimport();                  // GoblinModelPostprocessor pins the Jaw on this pass
                var avatar = AssetDatabase.LoadAllAssetsAtPath(Model).OfType<Avatar>().FirstOrDefault();
                var hd = ((ModelImporter)AssetImporter.GetAtPath(Model)).humanDescription;
                log.AppendLine($"avatar valid={avatar?.isValid} human={avatar?.isHuman} bones={hd.human.Length} " +
                               $"jaw={hd.human.FirstOrDefault(h => h.humanName == "Jaw").boneName}");

                var props = new Dictionary<string, GameObject>();
                foreach (var guid in AssetDatabase.FindAssets("t:GameObject", new[] { PropModels }))
                {
                    var path = AssetDatabase.GUIDToAssetPath(guid);
                    if (!path.EndsWith(".fbx", System.StringComparison.OrdinalIgnoreCase)) continue;
                    ConfigureModel(path, skin, gear, humanoid: false);
                    var model = AssetDatabase.LoadAssetAtPath<GameObject>(path);
                    var wrapper = new GameObject(model.name);
                    var inst = (GameObject)PrefabUtility.InstantiatePrefab(model, wrapper.transform);
                    inst.name = model.name + "_Mesh";
                    inst.transform.SetLocalPositionAndRotation(Vector3.zero, Quaternion.identity);    // modelled in socket space
                    inst.transform.localScale = Vector3.one;
                    props[model.name] = PrefabUtility.SaveAsPrefabAsset(wrapper, $"{PropPrefabs}/{model.name}.prefab");
                    Object.DestroyImmediate(wrapper);
                }
                log.AppendLine("prop prefabs: " + string.Join(", ", props.Keys.OrderBy(k => k)));

                var go = (GameObject)PrefabUtility.InstantiatePrefab(AssetDatabase.LoadAssetAtPath<GameObject>(Model));
                go.name = "Troll";
                var anim = go.GetComponent<Animator>() ?? go.AddComponent<Animator>();
                anim.avatar = avatar;
                anim.applyRootMotion = false;
                anim.cullingMode = AnimatorCullingMode.CullUpdateTransforms;
                var look = go.GetComponent<GoblinAppearance>() ?? go.AddComponent<GoblinAppearance>();
                look.bodyName = "TrollBody";
                look.skins = skins;
                look.optional = new GoblinAppearance.Optional[0];
                look.slots = new[]
                {
                    Slot(props, "Weapon", new[] { "Socket_RightHand" }, ("Prop_TrollClub", 1f)),
                    Slot(props, "Hair", new[] { "Socket_Helm" }, ("Prop_TrollHair", 2f), (null, 1f)),
                };
                look.shapes = new[]
                {
                    new GoblinAppearance.Shape { name = "Skinny", chance = 0.3f, weight = new Vector2(0.5f, 1f), group = "build" },
                    new GoblinAppearance.Shape { name = "Brawny", chance = 0.25f, weight = new Vector2(0.5f, 1f), group = "build" },
                    new GoblinAppearance.Shape { name = "Fat", chance = 0.1f, weight = new Vector2(0.25f, 0.75f), group = "build" },
                    new GoblinAppearance.Shape { name = "EarsDroop", chance = 0.35f, weight = new Vector2(0.5f, 1f) },
                    new GoblinAppearance.Shape { name = "EarTornL", chance = 0.12f, weight = new Vector2(1f, 1f) },
                    new GoblinAppearance.Shape { name = "EarTornR", chance = 0.12f, weight = new Vector2(1f, 1f) },
                };
                look.pushes = new GoblinAppearance.Push[0];
                look.scale = new Vector2(0.95f, 1.06f);
                if (go.GetComponent<GoblinPosture>() == null) go.AddComponent<GoblinPosture>();
                if (go.GetComponent<GoblinTwoHandGrip>() == null) go.AddComponent<GoblinTwoHandGrip>();    // weight 0: a game's driver sets it
                if (go.GetComponent<GoblinEvents>() == null) go.AddComponent<GoblinEvents>();              // the Roar's event
                foreach (var (prop, socket) in new[] { ("Prop_TrollClub", "Socket_RightHand"), ("Prop_TrollHair", "Socket_Helm") })
                {
                    var s = Find(go.transform, socket);
                    if (s == null || !props.ContainsKey(prop)) { log.AppendLine($"MISSING {prop} -> {socket}"); continue; }
                    var p = (GameObject)PrefabUtility.InstantiatePrefab(props[prop], s);
                    p.transform.SetLocalPositionAndRotation(Vector3.zero, Quaternion.identity);
                    p.transform.localScale = Vector3.one;
                }
                var prefab = PrefabUtility.SaveAsPrefabAsset(go, PrefabPath);
                Object.DestroyImmediate(go);
                log.AppendLine($"prefab: {PrefabPath}");
                Sizes(prefab, log);

                ConfigureClips(avatar, log);
                GroundDeaths(prefab, log);
                Verify(prefab, log);
                MakeAnims(log);
                AssetDatabase.SaveAssets();
                log.AppendLine("OK");
            }
            catch (System.Exception e)
            {
                log.AppendLine("EXCEPTION " + e);
            }
            finally
            {
                Application.logMessageReceived -= onLog;
                File.WriteAllText(Path.Combine(OutDir, "setup_report.txt"), log.ToString());
                Debug.Log("Troll setup finished: " + Path.Combine(OutDir, "setup_report.txt"));
            }
        }

        static GoblinAppearance.Slot Slot(Dictionary<string, GameObject> props, string name, string[] sockets,
                                          params (string prop, float weight)[] options) => new GoblinAppearance.Slot
        {
            name = name,
            sockets = sockets,
            options = options.Select(o => new GoblinAppearance.Option
            {
                prop = o.prop == null || !props.ContainsKey(o.prop) ? null : props[o.prop],
                weight = o.weight,
            }).ToArray(),
        };

        static void Sizes(GameObject prefab, StringBuilder log)
        {
            int tris = 0;
            var size = Vector3.zero;
            foreach (var r in prefab.GetComponentsInChildren<Renderer>(true))
            {
                var mf = r.GetComponent<MeshFilter>();
                Mesh m = r is SkinnedMeshRenderer s ? s.sharedMesh : (mf != null ? mf.sharedMesh : null);
                if (m == null) continue;
                tris += m.triangles.Length / 3;
                if (r.name == "TrollBody")                 // the bind pose in the prefab's space, metres
                {
                    var bb = new Bounds(r.transform.TransformPoint(m.bounds.min), Vector3.zero);
                    for (int i = 0; i < 8; i++)
                        bb.Encapsulate(r.transform.TransformPoint(m.bounds.center + Vector3.Scale(m.bounds.extents,
                            new Vector3((i & 1) == 0 ? -1 : 1, (i & 2) == 0 ? -1 : 1, (i & 4) == 0 ? -1 : 1))));
                    size = bb.size;
                }
            }
            log.AppendLine($"triangles (body, loincloth, club, hair): {tris}; body in its bind pose: {size.y:0.00} m tall, " +
                           $"{size.x:0.00} m across the arms (GoblinAppearance scales each troll 0.95..1.06)");
        }

        // ------------------------------------------------------------------------------------------- verification
        class Probe
        {
            public GameObject go;
            public PlayableGraph graph;
            public AnimationClipPlayable play;
            public Animator anim;
            public Transform hips, head, lHand, rHand, lMid, rMid, lUp, rUp, lLow, rLow, lFoot, rFoot, rSock, lSock;
            public GoblinPosture posture;
            public GoblinTwoHandGrip grip;
            public SkinnedMeshRenderer body;
            public float height;
        }

        static Probe Spawn(GameObject prefab, Scene scene, Vector3 pos, float yaw, int seed, AnimationClip clip)
        {
            var go = Object.Instantiate(prefab);       // unlinked: the roll removes and adds parts
            SceneManager.MoveGameObjectToScene(go, scene);
            go.transform.SetPositionAndRotation(pos, Quaternion.Euler(0, yaw, 0));
            if (go.GetComponent<GoblinPosture>() == null) go.AddComponent<GoblinPosture>();    // Goblin_Base gets it in the test scene
            if (go.TryGetComponent<GoblinAppearance>(out var look))
            {
                Random.InitState(seed);
                look.Reroll();                         // the merged mesh, as a game shows it; the same look every run
            }
            var p = new Probe { go = go, anim = go.GetComponent<Animator>() };
            p.anim.cullingMode = AnimatorCullingMode.AlwaysAnimate;   // no camera sees a preview scene while posing
            foreach (var smr in go.GetComponentsInChildren<SkinnedMeshRenderer>(true)) smr.forceMatrixRecalculationPerRender = true;
            Transform B(HumanBodyBones b) => p.anim.GetBoneTransform(b);
            p.hips = B(HumanBodyBones.Hips); p.head = B(HumanBodyBones.Head);
            p.lHand = B(HumanBodyBones.LeftHand); p.rHand = B(HumanBodyBones.RightHand);
            p.lMid = B(HumanBodyBones.LeftMiddleProximal); p.rMid = B(HumanBodyBones.RightMiddleProximal);
            p.lUp = B(HumanBodyBones.LeftUpperLeg); p.rUp = B(HumanBodyBones.RightUpperLeg);
            p.lLow = B(HumanBodyBones.LeftLowerLeg); p.rLow = B(HumanBodyBones.RightLowerLeg);
            p.lFoot = B(HumanBodyBones.LeftFoot); p.rFoot = B(HumanBodyBones.RightFoot);
            p.rSock = Find(go.transform, "Socket_RightHand"); p.lSock = Find(go.transform, "Socket_LeftHand");
            p.posture = go.GetComponent<GoblinPosture>();
            p.grip = go.GetComponent<GoblinTwoHandGrip>();
            var bodyName = look != null ? look.bodyName : "GoblinBody";
            p.body = go.GetComponentsInChildren<SkinnedMeshRenderer>(true).FirstOrDefault(r => r.name == bodyName);
            p.height = p.head != null ? p.head.position.y - pos.y : 1f;
            if (clip != null)
            {
                p.graph = PlayableGraph.Create("troll_check");
                p.graph.SetTimeUpdateMode(DirectorUpdateMode.Manual);
                var output = AnimationPlayableOutput.Create(p.graph, "pose", p.anim);
                p.play = AnimationClipPlayable.Create(p.graph, clip);
                p.play.SetApplyFootIK(true);           // as GoblinRandomAnimator plays them
                output.SetSourcePlayable(p.play);
            }
            return p;
        }

        static void Pose(Probe p, float seconds, bool twoHanded, bool upright = false)
        {
            if (!p.graph.IsValid()) return;
            p.play.SetTime(seconds);
            p.play.SetTime(seconds);                   // twice: SetTime keeps the previous time for root motion deltas
            p.graph.Evaluate(0f);
            if (p.posture != null && !upright) p.posture.Apply();     // own clips carry their posture (pools marked upright)
            if (p.grip != null)
            {
                p.grip.weight = twoHanded ? 1f : 0f;
                p.grip.Apply();
            }
        }

        static float SegDist(Vector3 p, Vector3 a, Vector3 b)
        {
            var ab = b - a;
            float t = Mathf.Clamp01(Vector3.Dot(p - a, ab) / Mathf.Max(ab.sqrMagnitude, 1e-6f));
            return Vector3.Distance(p, a + ab * t);
        }

        /// <summary>Retargeting numbers for one clip on one character, sampled 30 times. Radii are the troll's (thigh 0.11,
        /// shin 0.08, hand 0.06 m) scaled by height, so the goblin's numbers compare.</summary>
        static string Measure(GameObject prefab, Scene scene, AnimationClip clip, bool twoHanded, float refHeight, bool upright = false)
        {
            var p = Spawn(prefab, scene, new Vector3(0, 0, 60), 180f, 11, clip);
            try
            {
                float k = p.height / refHeight;
                float rThigh = 0.11f * k, rShin = 0.08f * k, rHand = 0.06f * k;
                float lowest = float.MaxValue, highest = float.MinValue, headMax = float.MinValue, headMin = float.MaxValue;
                float clear = float.MaxValue, fistMin = float.MaxValue, fistMax = 0f, tipMin = float.MaxValue;
                int into = 0, n = 30;
                var baked = new Mesh();
                var verts = new List<Vector3>();
                for (int i = 0; i < n; i++)
                {
                    float t = clip.length * i / (n - 1);
                    Pose(p, t, twoHanded, upright);
                    float low = float.MaxValue;
                    if (p.body != null)                    // the body alone (the club may rest on the ground)
                    {
                        p.body.BakeMesh(baked, true);
                        baked.GetVertices(verts);
                        var m = Matrix4x4.TRS(p.body.transform.position, p.body.transform.rotation, Vector3.one);
                        foreach (var v in verts) low = Mathf.Min(low, m.MultiplyPoint3x4(v).y);
                    }
                    lowest = Mathf.Min(lowest, low);
                    highest = Mathf.Max(highest, low);
                    if (p.head != null) { headMax = Mathf.Max(headMax, p.head.position.y); headMin = Mathf.Min(headMin, p.head.position.y); }
                    bool hit = false;
                    foreach (var (hand, mid) in new[] { (p.lHand, p.lMid), (p.rHand, p.rMid) })
                    {
                        if (hand == null) continue;
                        var palm = mid != null ? (hand.position + mid.position) * 0.5f : hand.position;
                        foreach (var (up, lowLeg, foot) in new[] { (p.lUp, p.lLow, p.lFoot), (p.rUp, p.rLow, p.rFoot) })
                        {
                            if (up == null || lowLeg == null || foot == null) continue;
                            float c = Mathf.Min(SegDist(palm, up.position, lowLeg.position) - rThigh,
                                                SegDist(palm, lowLeg.position, foot.position) - rShin) - rHand;
                            clear = Mathf.Min(clear, c);
                            if (c < 0) hit = true;
                        }
                    }
                    if (hit) into++;
                    if (twoHanded && p.rSock != null && p.lSock != null)
                    {
                        float d = Vector3.Distance(p.rSock.position, p.lSock.position);
                        fistMin = Mathf.Min(fistMin, d);
                        fistMax = Mathf.Max(fistMax, d);
                    }
                    var prop = p.rSock != null && p.rSock.childCount > 0 ? p.rSock.GetChild(p.rSock.childCount - 1) : null;
                    if (prop != null && prop.name.Contains("Club")) tipMin = Mathf.Min(tipMin, prop.TransformPoint(0, ClubReach, 0).y);
                }
                Object.DestroyImmediate(baked);
                var sb = new StringBuilder();
                sb.Append($"lowest point {lowest:+0.000;-0.000} m (highest of the per-frame lowest {highest:+0.000;-0.000}), " +
                          $"head {headMin:0.00}..{headMax:0.00} m, hands vs legs: closest {clear:+0.000;-0.000} m, into a leg in {into}/{n} frames");
                if (twoHanded) sb.Append($"; fists {fistMin:0.00}..{fistMax:0.00} m apart");
                if (tipMin < float.MaxValue) sb.Append($"; club tip lowest {tipMin:+0.00;-0.00} m");
                return sb.ToString();
            }
            finally
            {
                if (p.graph.IsValid()) p.graph.Destroy();
                Object.DestroyImmediate(p.go);
            }
        }

        /// <summary>The body's parts by the bone that weighs most on each vertex.</summary>
        static string Region(string bone)
        {
            if (bone.Contains("Ear")) return "ears";
            if (bone == "Head" || bone == "Jaw" || bone.Contains("Eye") || bone == "Neck") return "head";
            if (bone.Contains("Thumb") || bone.Contains("Index") || bone.Contains("Middle") || bone.Contains("Ring") ||
                bone.EndsWith("Hand")) return "hands";
            if (bone.Contains("Arm") || bone.EndsWith("Shoulder")) return "arms";
            if (bone.EndsWith("Foot") || bone.EndsWith("Toes")) return "feet";
            if (bone.Contains("Leg")) return "legs";
            return "torso";
        }

        static readonly string[] Regions = { "torso", "head", "ears", "arms", "hands", "legs", "feet" };

        /// <summary>The lowest point of each part of the body in the current pose (metres, + above the ground), the lowest
        /// of all and where it is.</summary>
        static (float all, string where, Dictionary<string, float> low) Lows(Probe p)
        {
            var low = Regions.ToDictionary(r => r, r => float.MaxValue);
            var baked = new Mesh();
            p.body.BakeMesh(baked, true);
            var verts = baked.vertices;
            var bw = p.body.sharedMesh.boneWeights;
            var names = p.body.bones.Select(b => b != null ? b.name : "").ToArray();
            var m = Matrix4x4.TRS(p.body.transform.position, p.body.transform.rotation, Vector3.one);
            float all = float.MaxValue;
            string where = "";
            for (int i = 0; i < verts.Length; i++)
            {
                float y = m.MultiplyPoint3x4(verts[i]).y;
                var r = Region(names[bw[i].boneIndex0]);
                if (y < low[r]) low[r] = y;
                if (y < all) { all = y; where = r; }
            }
            Object.DestroyImmediate(baked);
            return (all, where, low);
        }

        /// <summary>The pose lying at the end of a death clip: the lowest point of each part of the body (metres, + above the
        /// ground), and the club's lowest point (its mesh).</summary>
        static string EndPose(Probe p, AnimationClip clip, float at = -1f)
        {
            Pose(p, at >= 0 ? at : clip.length, false);
            var (all, where, low) = Lows(p);
            var sb = new StringBuilder($"lowest {all:+0.000;-0.000} m ({where}); ");
            sb.Append(string.Join(", ", Regions.Where(r => low[r] < float.MaxValue).Select(r => $"{r} {low[r]:+0.00;-0.00}")));
            float club = ClubLowest(p);
            if (club < float.MaxValue) sb.Append($"; club {club:+0.00;-0.00}");
            if (p.hips != null) sb.Append($"; hips {p.hips.position.y:0.00}");
            return sb.ToString();
        }

        /// <summary>The body's lowest point at each tenth of a clip.</summary>
        static string Tenths(Probe p, AnimationClip clip)
        {
            var lows = new List<string>();
            for (int i = 0; i <= 10; i++)
            {
                Pose(p, clip.length * i / 10f, false);
                lows.Add(Lows(p).all.ToString("+0.00;-0.00"));
            }
            return string.Join(" ", lows);
        }

        /// <summary>The club's lowest point in the current pose: its mesh (rigid on its prop transform), not just the tip.</summary>
        static float ClubLowest(Probe p)
        {
            var prop = p.rSock != null && p.rSock.childCount > 0 ? p.rSock.GetChild(p.rSock.childCount - 1) : null;
            if (prop == null || !prop.name.Contains("Club")) return float.MaxValue;
            float low = float.MaxValue;
            foreach (var mf in prop.GetComponentsInChildren<MeshFilter>(true))
            {
                if (mf.sharedMesh == null) continue;
                var mm = mf.transform.localToWorldMatrix;
                foreach (var v in mf.sharedMesh.vertices) low = Mathf.Min(low, mm.MultiplyPoint3x4(v).y);
            }
            return low;
        }

        /// <summary>Tools > Goblins > Troll Death Poses: how deep each death clip's end pose lies (Logs/TrollSetup/deaths.txt).</summary>
        [MenuItem("Tools/Goblins/Troll Death Poses")]
        public static void MeasureDeaths()
        {
            Directory.CreateDirectory(OutDir);
            var log = new StringBuilder();
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(PrefabPath);
            var clips = FindClips(log);
            var scene = EditorSceneManager.NewPreviewScene();
            try
            {
                foreach (var c in Checks.Where(c => c.label.StartsWith("Death")))
                {
                    if (!clips.TryGetValue(c.label, out var clip)) continue;
                    var p = Spawn(prefab, scene, new Vector3(0, 0, 60), 180f, 11, clip);
                    try
                    {
                        log.AppendLine($"{c.label,-7} {clip.name.Replace("HumanM@", "")} {clip.length:0.00}s end: " + EndPose(p, clip));
                        log.AppendLine("        lowest per tenth: " + Tenths(p, clip));
                    }
                    finally
                    {
                        if (p.graph.IsValid()) p.graph.Destroy();
                        Object.DestroyImmediate(p.go);
                    }
                }
            }
            finally
            {
                EditorSceneManager.ClosePreviewScene(scene);
                File.WriteAllText(Path.Combine(OutDir, "deaths.txt"), log.ToString());
            }
        }

        // ------------------------------------------------------------------------------------------- grounded deaths
        /// <summary>
        /// The set's death clips sink the troll into the ground (Death02 0.07 m, CombatDeath02 up to 0.15 m: a human's fall
        /// on the troll's longer limbs and bigger ears), so the set plays grounded copies. On the troll (the probe's look,
        /// foot IK on, GoblinPosture as a game plays deaths) each source clip is sampled at 60 Hz; the end pose is laid on
        /// its support plane (the plane under the body that is highest below the body's centre: the lying body rolls onto
        /// it, tilted at most 8 deg), and that tilt and lift come in as the hips fall; any frame still under the ground on
        /// the way down is lifted out of it. The correction is a rigid move of the whole body, written into the clip's body
        /// curves (RootT, RootQ); the muscle and IK goal curves are copied as they are (the goals follow the body: moving
        /// them too put the feet 3 cm under with foot IK on). Saved as
        /// Animation/&lt;clip&gt;_Grounded.anim and measured again.
        /// </summary>
        static void GroundDeaths(GameObject prefab, StringBuilder log)
        {
            var clips = FindClips(new StringBuilder());
            EnsureFolder(AnimDir);
            var scene = EditorSceneManager.NewPreviewScene();
            try
            {
                foreach (var (srcLabel, gLabel) in Deaths)
                {
                    if (!clips.TryGetValue(srcLabel, out var src)) { log.AppendLine($"grounded death: {srcLabel} missing"); continue; }
                    var name = src.name.Replace("HumanM@", "") + "_Grounded";
                    var clip = GroundDeath(prefab, scene, src, name, log);
                    if (clip == null) continue;
                    foreach (var (tag, c) in new[] { ("before", src), ("after", clip) })
                    {
                        var p = Spawn(prefab, scene, new Vector3(0, 0, 60), 180f, 11, c);
                        try
                        {
                            log.AppendLine($"  {tag,-6} {c.name.Replace("HumanM@", ""),-24} end: " + EndPose(p, c));
                            log.AppendLine($"         lowest per tenth: " + Tenths(p, c));
                        }
                        finally
                        {
                            if (p.graph.IsValid()) p.graph.Destroy();
                            Object.DestroyImmediate(p.go);
                        }
                    }
                }
                AssetDatabase.SaveAssets();
            }
            finally
            {
                EditorSceneManager.ClosePreviewScene(scene);
            }
        }

        static AnimationClip GroundDeath(GameObject prefab, Scene scene, AnimationClip src, string name, StringBuilder log)
        {
            var p = Spawn(prefab, scene, new Vector3(0, 0, 60), 180f, 11, src);
            try
            {
                var bindings = AnimationUtility.GetCurveBindings(src);
                var byName = new Dictionary<string, EditorCurveBinding>();
                foreach (var b in bindings) if (b.type == typeof(Animator) && b.path == "") byName[b.propertyName] = b;
                if (!byName.ContainsKey("RootT.y")) { log.AppendLine($"grounded death: {src.name} has no RootT curves"); return null; }
                AnimationCurve C(string prop) => byName.TryGetValue(prop, out var b) ? AnimationUtility.GetEditorCurve(src, b) : null;
                Vector3 V(string n, float t) => new Vector3(C(n + ".x").Evaluate(t), C(n + ".y").Evaluate(t), C(n + ".z").Evaluate(t));
                Quaternion Q(string n, float t) => new Quaternion(C(n + ".x").Evaluate(t), C(n + ".y").Evaluate(t),
                                                                  C(n + ".z").Evaluate(t), C(n + ".w").Evaluate(t)).normalized;
                var root = p.go.transform;
                Vector3 r0 = root.position;
                Quaternion q0 = root.rotation;

                // metres per clip unit, from the standing first frame (the body's height over RootT.y)
                Pose(p, 0f, false);
                Vector3 body0 = p.anim.bodyPosition;
                float k = (body0.y - r0.y) / Mathf.Max(1e-4f, V("RootT", 0f).y);
                Vector3 check = r0 + q0 * (V("RootT", 0f) * k);

                // samples: world body vertices and hips height
                float fps = 60f;
                int n = Mathf.CeilToInt(src.length * fps) + 1;
                var times = Enumerable.Range(0, n).Select(i => Mathf.Min(src.length, i / fps)).ToArray();
                var verts = new List<Vector3[]>();
                var hips = new float[n];
                var baked = new Mesh();
                for (int i = 0; i < n; i++)
                {
                    Pose(p, times[i], false);
                    p.body.BakeMesh(baked, true);
                    var m = Matrix4x4.TRS(p.body.transform.position, p.body.transform.rotation, Vector3.one);
                    verts.Add(baked.vertices.Select(v => m.MultiplyPoint3x4(v)).ToArray());
                    hips[i] = p.hips.position.y;
                }
                Pose(p, src.length, false);
                Vector3 com = p.anim.bodyPosition;
                Object.DestroyImmediate(baked);

                // the end pose's support plane: y = h + a (x - cx) + b (z - cz), highest at the body's centre
                var end = verts[n - 1];
                float bestH = float.MinValue, bestA = 0, bestB = 0, lim = Mathf.Tan(8f * Mathf.Deg2Rad);
                float PlaneH(float a, float b)
                {
                    float h = float.MaxValue;
                    foreach (var v in end) h = Mathf.Min(h, v.y - a * (v.x - com.x) - b * (v.z - com.z));
                    return h;
                }
                for (float step = 0.01f; step >= 0.0005f; step *= 0.25f)
                {
                    float a0 = bestA, b0 = bestB;
                    for (int ia = -8; ia <= 8; ia++)
                        for (int ib = -8; ib <= 8; ib++)
                        {
                            float a = Mathf.Clamp(a0 + ia * step, -lim, lim), b = Mathf.Clamp(b0 + ib * step, -lim, lim);
                            float h = PlaneH(a, b);
                            if (h > bestH + 1e-6f) { bestH = h; bestA = a; bestB = b; }
                        }
                }
                float flatH = PlaneH(0, 0);
                var normal = new Vector3(-bestA, 1f, -bestB).normalized;
                Quaternion tilt = Quaternion.FromToRotation(normal, Vector3.up);
                var pivot = new Vector3(com.x, bestH, com.z);
                float lift = -bestH;

                // in as the hips fall (0 standing .. 1 lying), plus whatever still sinks on the way down
                float h0 = hips[0], h1 = hips[n - 1];
                var s = hips.Select(h => Mathf.SmoothStep(0f, 1f, Mathf.Clamp01((h0 - h) / Mathf.Max(1e-3f, h0 - h1)))).ToArray();
                var extra = new float[n];
                for (int i = 0; i < n; i++)
                {
                    var R = Quaternion.Slerp(Quaternion.identity, tilt, s[i]);
                    float low = float.MaxValue;
                    foreach (var v in verts[i]) low = Mathf.Min(low, (pivot + R * (v - pivot)).y + lift * s[i]);
                    extra[i] = Mathf.Max(0f, -low);
                }
                var held = new float[n];                 // each lift held a frame either side, then blurred: no jitter
                for (int i = 0; i < n; i++)
                    for (int j = Mathf.Max(0, i - 1); j <= Mathf.Min(n - 1, i + 1); j++) held[i] = Mathf.Max(held[i], extra[j]);
                var dz = new float[n];
                for (int i = 0; i < n; i++)
                {
                    float sum = 0; int cnt = 0;
                    for (int j = Mathf.Max(0, i - 1); j <= Mathf.Min(n - 1, i + 1); j++) { sum += held[j]; cnt++; }
                    dz[i] = lift * s[i] + Mathf.Max(extra[i], sum / cnt);
                }

                // the move in the clip's own space: the root's frame, clip units
                Quaternion qi = Quaternion.Inverse(q0);
                Vector3 pivotL = qi * (pivot - r0) / k;
                var curves = new Dictionary<string, Keyframe[]>();
                void Key(string prop, int i, float v)
                {
                    if (!curves.TryGetValue(prop, out var ks)) curves[prop] = ks = new Keyframe[n];
                    ks[i] = new Keyframe(times[i], v);
                }
                var prevQ = new Dictionary<string, Quaternion>();
                for (int i = 0; i < n; i++)
                {
                    var Rl = qi * Quaternion.Slerp(Quaternion.identity, tilt, s[i]) * q0;
                    Vector3 up = Vector3.up * (dz[i] / k);
                    foreach (var g in new[] { "Root" })        // the body; the IK goals stay (moving them as well put the feet under)
                    {
                        var t = pivotL + Rl * (V(g + "T", times[i]) - pivotL) + up;
                        var q = Rl * Q(g + "Q", times[i]);
                        if (prevQ.TryGetValue(g, out var pq) && Quaternion.Dot(pq, q) < 0) q = new Quaternion(-q.x, -q.y, -q.z, -q.w);
                        prevQ[g] = q;
                        Key(g + "T.x", i, t.x); Key(g + "T.y", i, t.y); Key(g + "T.z", i, t.z);
                        Key(g + "Q.x", i, q.x); Key(g + "Q.y", i, q.y); Key(g + "Q.z", i, q.z); Key(g + "Q.w", i, q.w);
                    }
                }
                var outB = new List<EditorCurveBinding>();
                var outC = new List<AnimationCurve>();
                foreach (var b in bindings)
                {
                    AnimationCurve c;
                    if (b.type == typeof(Animator) && b.path == "" && curves.TryGetValue(b.propertyName, out var ks))
                    {
                        c = new AnimationCurve(ks);
                        for (int i = 0; i < c.length; i++)
                        {
                            AnimationUtility.SetKeyLeftTangentMode(c, i, AnimationUtility.TangentMode.Linear);
                            AnimationUtility.SetKeyRightTangentMode(c, i, AnimationUtility.TangentMode.Linear);
                        }
                    }
                    else c = AnimationUtility.GetEditorCurve(src, b);
                    if (c == null) continue;
                    outB.Add(b);
                    outC.Add(c);
                }
                var clip = new AnimationClip { name = name, frameRate = src.frameRate };
                AnimationUtility.SetEditorCurves(clip, outB.ToArray(), outC.ToArray());
                AnimationUtility.SetAnimationClipSettings(clip, AnimationUtility.GetAnimationClipSettings(src));

                var path = $"{AnimDir}/{name}.anim";
                var old = AssetDatabase.LoadAssetAtPath<AnimationClip>(path);
                if (old != null)
                {
                    EditorUtility.CopySerialized(clip, old);     // keep the asset (and its GUID: the set and prefabs point at it)
                    old.name = name;
                    EditorUtility.SetDirty(old);
                    Object.DestroyImmediate(clip);
                    clip = old;
                }
                else AssetDatabase.CreateAsset(clip, path);
                log.AppendLine($"grounded death: {path} from {src.name.Replace("HumanM@", "")} ({clip.length:0.00}s, human={clip.humanMotion}, " +
                               $"{outB.Count} curves): end pose {flatH:+0.000;-0.000} m flat, support plane tilted " +
                               $"{Vector3.Angle(normal, Vector3.up):0.0} deg, lift {lift:0.000} m; most extra lift on the way down " +
                               $"{extra.Max():0.000} m; clip unit {k:0.000} m (body at frame 0 off by {(check - body0).magnitude:0.000} m)");
                return clip;
            }
            finally
            {
                if (p.graph.IsValid()) p.graph.Destroy();
                Object.DestroyImmediate(p.go);
            }
        }

        // ------------------------------------------------------------------------------------------- the troll's own clips
        [System.Serializable] class ClipEvent { public string name; public float time; }
        [System.Serializable] class ClipInfo { public string name; public int frames; public int fps; public bool loop; public bool rootMotion; public ClipEvent[] events; }
        [System.Serializable] class ClipList { public ClipInfo[] clips; }

        /// <summary>
        /// Models/Anims/Troll@&lt;clip&gt;.fbx (src/troll_anim.py exports them with troll_clips.json beside them): Humanoid
        /// with Troll.fbx's avatar, one clip named after the file, loop, root motion and events from the JSON (the events
        /// call GoblinEvents.OnGoblinEvent with the event's name). Clips without root motion play in place.
        /// </summary>
        static void ConfigureClips(Avatar avatar, StringBuilder log)
        {
            if (!AssetDatabase.IsValidFolder(Anims) || avatar == null) { log.AppendLine($"own clips: no {Anims}"); return; }
            var json = Path.Combine(Anims, "troll_clips.json");
            var info = File.Exists(json) ? JsonUtility.FromJson<ClipList>(File.ReadAllText(json)) : new ClipList();
            var byName = (info.clips ?? new ClipInfo[0]).ToDictionary(c => c.name);
            var lines = new List<string>();
            foreach (var guid in AssetDatabase.FindAssets("t:Model", new[] { Anims }))
            {
                var path = AssetDatabase.GUIDToAssetPath(guid);
                var file = Path.GetFileNameWithoutExtension(path);
                if (!file.StartsWith("Troll@")) continue;
                var clipName = file.Substring(file.IndexOf('@') + 1);
                byName.TryGetValue(clipName, out var ci);
                var imp = (ModelImporter)AssetImporter.GetAtPath(path);
                imp.importCameras = false;
                imp.importLights = false;
                imp.materialImportMode = ModelImporterMaterialImportMode.None;
                imp.preserveHierarchy = true;           // the armature is the file's only root: keep it, as in Troll.fbx
                imp.animationType = ModelImporterAnimationType.Human;
                imp.avatarSetup = ModelImporterAvatarSetup.CopyFromOther;
                imp.sourceAvatar = avatar;
                imp.importAnimation = true;
                imp.animationCompression = ModelImporterAnimationCompression.KeyframeReduction;
                imp.SaveAndReimport();                    // take info exists only after an import that succeeded
                var take = imp.importedTakeInfos.FirstOrDefault();
                if (string.IsNullOrEmpty(take.name)) { lines.Add($"{clipName}: no take"); continue; }
                bool loop = ci != null && ci.loop, moves = ci != null && ci.rootMotion;
                float length = ci != null && ci.fps > 0 ? ci.frames / (float)ci.fps : take.stopTime - take.startTime;
                imp.clipAnimations = new[]
                {
                    new ModelImporterClipAnimation
                    {
                        name = clipName,
                        takeName = take.name,
                        firstFrame = Mathf.Round(take.startTime * take.sampleRate),
                        lastFrame = Mathf.Round(take.stopTime * take.sampleRate),
                        loopTime = loop,
                        loopPose = false,                 // the loop's ends already match (the drag's last frame is its first, a stride on)
                        lockRootRotation = true, keepOriginalOrientation = true,
                        lockRootHeightY = true, keepOriginalPositionY = true,
                        lockRootPositionXZ = !moves, keepOriginalPositionXZ = true,
                        events = (ci?.events ?? new ClipEvent[0]).Select(e => new AnimationEvent
                        {
                            time = Mathf.Clamp01(e.time / Mathf.Max(length, 1e-3f)),     // importer events are normalised
                            functionName = EventFunction,
                            stringParameter = e.name,
                        }).ToArray(),
                    },
                };
                imp.SaveAndReimport();
                var clip = AssetDatabase.LoadAllAssetsAtPath(path).OfType<AnimationClip>().FirstOrDefault(c => c.name == clipName);
                if (clip == null) { lines.Add(clipName + " (missing)"); continue; }
                var ev = AnimationUtility.GetAnimationEvents(clip);
                lines.Add($"{clipName} {clip.length:0.00}s{(clip.isLooping ? " loop" : "")} human={clip.humanMotion}" +
                          (moves ? " root motion" : "") +
                          (ev.Length > 0 ? " events " + string.Join("/", ev.Select(e => $"{e.stringParameter}@{e.time:0.00}s")) : ""));
            }
            log.AppendLine("own clips: " + string.Join("; ", lines));
        }

        public const string AnimsPath = AnimDir + "/TrollAnims.asset";

        /// <summary>The troll's clip set (GoblinAnimationSet, for a game's CreatureAnim / GoblinRandomAnimator), from the
        /// checks' numbers (2026-10-23, Logs/TrollSetup): one-handed swings that keep the 1.3 m club out of the ground
        /// (Attack1H01/03/05_R: tip -0.03 / +0.24 / +0.24 m; 02 put a hand through a leg, 04 the club 0.11 m into the
        /// ground, the two-handed chops 0.41-0.57 m), both hit reactions, the deaths that sink least (Death02, CombatDeath02;
        /// the others 0.28-0.42 m) as grounded copies; the troll's own Roar (a threat pool, like the goblin chief's) and
        /// ClubDrag (its own pool: a slow walk with root motion, not a variant of Walk, whose speed it does not match).
        /// Own pools are upright: the clips carry the troll's posture, GoblinPosture's hunch stays out.</summary>
        static void MakeAnims(StringBuilder log)
        {
            var clips = FindClips(new StringBuilder());
            EnsureFolder(AnimDir);
            var set = AssetDatabase.LoadAssetAtPath<GoblinAnimationSet>(AnimsPath);
            if (set == null)
            {
                set = ScriptableObject.CreateInstance<GoblinAnimationSet>();
                AssetDatabase.CreateAsset(set, AnimsPath);
            }
            GoblinAnimationSet.Pool P(string name, float w, string[] labels, bool moves = false, float after = 0f,
                                      bool upright = false, Vector2? hold = null) =>
                new GoblinAnimationSet.Pool
                {
                    name = name, weight = w, moves = moves, holdAfter = after, hold = hold ?? new Vector2(3, 6), upright = upright,
                    clips = labels.Where(clips.ContainsKey).Select(l => clips[l]).ToArray(),
                };
            set.pools = new[]
            {
                P("Idle", 3, new[] { "Idle" }),
                P("Walk", 2, new[] { "Walk" }, moves: true),
                P("Run", 1, new[] { "Run" }, moves: true),
                P("Swing", 2, new[] { "Swing1H", "Swing1H_3", "Swing1H_5" }),
                P("Roar", 1, new[] { "Roar" }, upright: true),
                P("ClubDrag", 1.5f, new[] { "ClubDrag" }, moves: true, upright: true, hold: new Vector2(4, 8)),
                P("Hurt", 0, new[] { "Hit", "Hit2" }),
                P("Death", 0, Deaths.Select(d => clips.ContainsKey(d.grounded) ? d.grounded : d.src).ToArray(), after: 1.5f),
            };
            EditorUtility.SetDirty(set);
            log.AppendLine($"animation set: {AnimsPath} (" + string.Join(", ", set.pools.Select(p =>
                $"{p.name} {p.clips.Length}" + (p.clips.Length > 0 ? " [" + string.Join("/", p.clips.Select(c => c.name.Replace("HumanM@", ""))) + "]" : ""))) + ")");
        }

        static Dictionary<string, AnimationClip> FindClips(StringBuilder log)
        {
            var found = new Dictionary<string, AnimationClip>();
            bool kevin = AssetDatabase.IsValidFolder(ClipRoot);
            if (!kevin) log.AppendLine($"no Kevin Iglesias Human Animations at {ClipRoot}: retargeting not checked");
            foreach (var (label, names, _, _, own) in Checks)
                foreach (var n in names)
                {
                    if (own)
                    {
                        // Models/Anims/Troll@<clip>.fbx, or a grounded death made here (Animation/<clip>.anim)
                        var clipName = n.Contains("@") ? n.Substring(n.IndexOf('@') + 1) : n;
                        var c = AssetDatabase.LoadAllAssetsAtPath($"{Anims}/{n}.fbx").OfType<AnimationClip>()
                                    .FirstOrDefault(x => x.name == clipName)
                                ?? AssetDatabase.LoadAssetAtPath<AnimationClip>($"{AnimDir}/{n}.anim");
                        if (c != null && !found.ContainsKey(label)) found[label] = c;
                        if (found.ContainsKey(label)) break;
                        continue;
                    }
                    if (!kevin) continue;
                    var file = "HumanM@" + n.Replace(" [RM]", "");
                    foreach (var guid in AssetDatabase.FindAssets(file, new[] { ClipRoot }))
                    {
                        var path = AssetDatabase.GUIDToAssetPath(guid);
                        if (Path.GetFileNameWithoutExtension(path) != file) continue;
                        var c = AssetDatabase.LoadAllAssetsAtPath(path).OfType<AnimationClip>()
                            .FirstOrDefault(x => !x.name.StartsWith("__preview") && x.name.Replace("HumanM@", "") == n);
                        if (c != null && !found.ContainsKey(label)) found[label] = c;
                    }
                    if (found.ContainsKey(label)) break;
                }
            log.AppendLine("clips: " + string.Join(", ", Checks.Select(c => found.TryGetValue(c.label, out var a)
                ? $"{c.label}={a.name.Replace("HumanM@", "")} {a.length:0.00}s human={a.humanMotion}" : $"{c.label}=MISSING")));
            return found;
        }

        static void Verify(GameObject prefab, StringBuilder log)
        {
            var clips = FindClips(log);
            var goblin = AssetDatabase.LoadAssetAtPath<GameObject>(GoblinPrefab);
            var scene = EditorSceneManager.NewPreviewScene();      // never the open scenes (other tools and sessions use them)
            bool async = ShaderUtil.allowAsyncCompilation;
            ShaderUtil.allowAsyncCompilation = false;
            var probes = new List<Probe>();
            void Clear()
            {
                foreach (var p in probes)
                {
                    if (p.graph.IsValid()) p.graph.Destroy();
                    if (p.go != null) Object.DestroyImmediate(p.go);
                }
                probes.Clear();
            }
            try
            {
                void Add(GameObject g) => SceneManager.MoveGameObjectToScene(g, scene);
                var ground = GameObject.CreatePrimitive(PrimitiveType.Plane);
                Add(ground);
                ground.transform.localScale = new Vector3(8, 1, 8);
                var gm = AssetDatabase.LoadAssetAtPath<Material>("Assets/Goblins/Scenes/M_ShowcaseGround.mat");
                if (gm != null) ground.GetComponent<Renderer>().sharedMaterial = gm;
                var sun = new GameObject("Sun").AddComponent<Light>();
                Add(sun.gameObject);
                sun.type = LightType.Directional;
                sun.intensity = 1.6f;
                sun.shadows = LightShadows.Soft;
                sun.transform.rotation = Quaternion.Euler(50, 200, 0);

                // measures first, one character at a time, away from the renders
                var refProbe = Spawn(prefab, scene, new Vector3(0, 0, 80), 180f, 1, null);
                float trollH = refProbe.height;
                Object.DestroyImmediate(refProbe.go);
                float gobH = 0f;
                if (goblin != null)
                {
                    var g = Spawn(goblin, scene, new Vector3(0, 0, 80), 180f, 1, null);
                    gobH = g.height;
                    Object.DestroyImmediate(g.go);
                }
                log.AppendLine($"head bone in the bind pose: troll {trollH:0.00} m" + (goblin != null ? $", goblin {gobH:0.00} m" : ""));
                foreach (var (label, _, _, twoH, own) in Checks)
                {
                    if (!clips.TryGetValue(label, out var clip)) continue;
                    bool up = Upright.Contains(label);
                    log.AppendLine($"{label,-9} troll : " + Measure(prefab, scene, clip, twoH, trollH, up));
                    if (goblin != null && !own) log.AppendLine($"{label,-9} goblin: " + Measure(goblin, scene, clip, twoH, trollH));
                }
                if (clips.TryGetValue("ClubDrag", out var drag)) log.AppendLine(PerFrame(prefab, scene, drag));
                if (clips.TryGetValue("Roar", out var roar)) log.AppendLine(PerFrame(prefab, scene, roar));

                // the lineup: one troll per clip at its telling moment, a goblin for scale
                float spacing = 2.6f;
                int count = Checks.Length;
                float x0 = -(count - 1) * 0.5f * spacing;
                for (int i = 0; i < count; i++)
                {
                    clips.TryGetValue(Checks[i].label, out var clip);
                    var p = Spawn(prefab, scene, new Vector3(x0 + i * spacing, 0, 0), 180f, 3 + i, clip);
                    Pose(p, clip != null ? clip.length * Checks[i].at : 0f, Checks[i].twoHanded, Upright.Contains(Checks[i].label));
                    probes.Add(p);
                }
                if (goblin != null)
                {
                    var g = Spawn(goblin, scene, new Vector3(x0 - spacing * 0.8f, 0, 0.6f), 180f, 5, clips.TryGetValue("Idle", out var gi) ? gi : null);
                    Pose(g, gi != null ? gi.length * 0.3f : 0f, false);
                    probes.Add(g);
                }
                float w = (count + 1.5f) * spacing, cx = -0.4f * spacing;
                Shoot(scene, "CAM_Lineup", new Vector3(cx + 1.5f, 3.4f, -w * 0.6f), new Vector3(cx, 1.1f, 0), 40, "troll_lineup.png", 2200, 900);
                Shoot(scene, "CAM_Game", new Vector3(cx, 22f * Mathf.Sin(50 * Mathf.Deg2Rad), -22f * Mathf.Cos(50 * Mathf.Deg2Rad)),
                      new Vector3(cx, 1f, 0), 30, "troll_lineup_game_22m.png", 1920, 1080);
                Clear();

                // a strip per clip: six moments, start to end (eight for the troll's own)
                foreach (var (label, _, _, twoH, own) in Checks)
                {
                    if (!clips.TryGetValue(label, out var clip)) continue;
                    int tiles = own ? 8 : 6;
                    float step = own ? 2.0f : 2.4f;
                    for (int i = 0; i < tiles; i++)
                    {
                        var p = Spawn(prefab, scene, new Vector3((i - (tiles - 1) * 0.5f) * step, 0, 0), 160f, 21, clip);
                        Pose(p, clip.length * i / (tiles - 1), twoH, Upright.Contains(label));
                        probes.Add(p);
                    }
                    Shoot(scene, "CAM_Strip", own ? new Vector3(2f, 2.4f, -11.5f) : new Vector3(2f, 2.4f, -9f), new Vector3(0, 1.1f, 0), 34,
                          $"troll_clip_{label.ToLowerInvariant()}.png", own ? 2400 : 2000, 700);
                    Clear();
                }

                // the deaths' end poses, before and after grounding: from above, and from the ground's level with the ground
                // hidden and its line drawn red (whatever is under the line is under the ground)
                foreach (var (src, g) in Deaths)
                {
                    if (!clips.TryGetValue(src, out var a) || !clips.TryGetValue(g, out var b)) continue;
                    int k = 0;
                    foreach (var c in new[] { a, b })
                    {
                        var p = Spawn(prefab, scene, Vector3.zero, 90f, 11, c);
                        Pose(p, c.length, false);
                        // the body's middle on its spot: left the clip as it was, right the grounded copy
                        var baked = new Mesh();
                        p.body.BakeMesh(baked, true);
                        var m = Matrix4x4.TRS(p.body.transform.position, p.body.transform.rotation, Vector3.one);
                        var wv = baked.vertices.Select(v => m.MultiplyPoint3x4(v)).ToArray();
                        Object.DestroyImmediate(baked);
                        var mid = new Vector3((wv.Min(v => v.x) + wv.Max(v => v.x)) / 2, 0, (wv.Min(v => v.z) + wv.Max(v => v.z)) / 2);
                        p.go.transform.position += new Vector3(k++ == 0 ? -1.45f : 1.45f, 0, 0) - mid;
                        Pose(p, c.length, false);
                        probes.Add(p);
                    }
                    var tag = a.name.Replace("HumanM@", "").ToLowerInvariant();
                    Shoot(scene, "CAM_Dead", new Vector3(0.4f, 3.2f, -5.2f), new Vector3(0, 0.1f, 0.2f), 34, $"troll_death_{tag}_before_after.png", 1800, 900);
                    ground.SetActive(false);
                    Shoot(scene, "CAM_DeadLevel", new Vector3(0f, 0f, -7.5f), new Vector3(0f, 0f, 0f), 18, $"troll_death_{tag}_ground_line.png", 2000, 700, line: true);
                    ground.SetActive(true);
                    Clear();
                }

                // the new clips from the game camera (22 m, 50 deg, fov 30): the roar's peak, the drag, a grounded death,
                // a goblin for scale
                var shots = new (string label, float at)[] { ("Roar", 0.4f), ("ClubDrag", 0.3f), ("Death6G", 1f), ("Idle", 0.3f) };
                for (int i = 0; i < shots.Length; i++)
                {
                    if (!clips.TryGetValue(shots[i].label, out var c)) continue;
                    var p = Spawn(prefab, scene, new Vector3((i - 1.5f) * 2.3f, 0, 0), 180f, 7 + i, c);
                    Pose(p, c.length * shots[i].at, false, Upright.Contains(shots[i].label));
                    probes.Add(p);
                }
                if (goblin != null)
                {
                    var g = Spawn(goblin, scene, new Vector3(-5.0f, 0, 0.4f), 180f, 5, clips.TryGetValue("Idle", out var gi2) ? gi2 : null);
                    Pose(g, gi2 != null ? gi2.length * 0.3f : 0f, false);
                    probes.Add(g);
                }
                var gameCam = new Vector3(-0.6f, 22f * Mathf.Sin(50 * Mathf.Deg2Rad), -22f * Mathf.Cos(50 * Mathf.Deg2Rad));
                Shoot(scene, "CAM_GameNew", gameCam, new Vector3(-0.6f, 1f, 0), 30, "troll_new_clips_game_22m.png", 1920, 1080);
                Shoot(scene, "CAM_GameNew", gameCam, new Vector3(-0.6f, 1f, 0), 30, "troll_new_clips_game_22m_x2.png", 1920, 1080, crop: 2);
                Clear();
                log.AppendLine("renders: " + OutDir);
            }
            finally
            {
                Clear();
                ShaderUtil.allowAsyncCompilation = async;
                EditorSceneManager.ClosePreviewScene(scene);
            }
        }

        /// <summary>A clip frame by frame on the troll (upright, as its pool plays it): the club's lowest point (its mesh) and
        /// the body's, metres above the ground.</summary>
        static string PerFrame(GameObject prefab, Scene scene, AnimationClip clip)
        {
            var p = Spawn(prefab, scene, new Vector3(0, 0, 60), 180f, 11, clip);
            try
            {
                int n = Mathf.RoundToInt(clip.length * clip.frameRate);
                var club = new List<float>();
                var body = new List<float>();
                for (int f = 0; f <= n; f++)
                {
                    Pose(p, Mathf.Min(clip.length, f / clip.frameRate), false, true);
                    club.Add(ClubLowest(p));
                    body.Add(Lows(p).all);
                }
                string travel = "";
                if (clip.isLooping && !AnimationUtility.GetAnimationClipSettings(clip).loopBlendPositionXZ)
                {
                    // the root motion of one loop, played through with the Animator applying it to the troll
                    p.anim.applyRootMotion = true;
                    Pose(p, 0f, false, true);
                    var t0 = p.go.transform;
                    Vector3 start = t0.position, fwd = t0.forward, side = t0.right;
                    float lateral = 0f;
                    for (int f = 0; f < n; f++)
                    {
                        p.graph.Evaluate(1f / clip.frameRate);
                        lateral = Mathf.Max(lateral, Mathf.Abs(Vector3.Dot(t0.position - start, side)));
                    }
                    var d = t0.position - start;
                    travel = $"; root motion over one loop {Vector3.Dot(d, fwd):0.000} m forward ({Vector3.Dot(d, fwd) / clip.length:0.00} m/s), " +
                             $"{Vector3.Dot(d, side):+0.000;-0.000} m sideways at the end (at most {lateral:0.000}), troll scale {t0.lossyScale.x:0.00}";
                    p.anim.applyRootMotion = false;
                }
                return $"{clip.name} per frame ({n + 1} frames at {clip.frameRate:0} fps): club lowest {club.Min():+0.000;-0.000}..{club.Max():+0.000;-0.000} m, " +
                       $"body lowest {body.Min():+0.000;-0.000}..{body.Max():+0.000;-0.000} m{travel}\n  club: " +
                       string.Join(" ", club.Select(v => v.ToString("+0.000;-0.000"))) +
                       "\n  body: " + string.Join(" ", body.Select(v => v.ToString("+0.000;-0.000")));
            }
            finally
            {
                if (p.graph.IsValid()) p.graph.Destroy();
                Object.DestroyImmediate(p.go);
            }
        }

        static void Shoot(Scene scene, string name, Vector3 pos, Vector3 at, float fov, string file, int w, int h, bool line = false,
                          int crop = 1)
        {
            var cam = new GameObject(name).AddComponent<Camera>();
            SceneManager.MoveGameObjectToScene(cam.gameObject, scene);
            cam.scene = scene;
            cam.transform.position = pos;
            cam.transform.LookAt(at);
            cam.fieldOfView = fov;
            cam.nearClipPlane = 0.05f;
            cam.farClipPlane = 200f;
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = new Color(0.47f, 0.52f, 0.58f);
            Render(cam, file, w, h, line, crop);       // the first render of fresh skinned meshes can come out empty
            Render(cam, file, w, h, line, crop);
            Object.DestroyImmediate(cam.gameObject);
        }

        /// <summary>line: a red row where the ground's plane meets the picture (the camera looks level from y = 0: the
        /// middle row); crop: the middle of the picture blown up crop times (nearest), as the game camera's pixels.</summary>
        static void Render(Camera cam, string file, int w, int h, bool line = false, int crop = 1)
        {
            var rt = new RenderTexture(w, h, 24, RenderTextureFormat.ARGB32, RenderTextureReadWrite.sRGB);
            var req = new RenderPipeline.StandardRequest { destination = rt };
            if (GraphicsSettings.currentRenderPipeline != null && RenderPipeline.SupportsRenderRequest(cam, req))
                RenderPipeline.SubmitRenderRequest(cam, req);
            else
            {
                cam.targetTexture = rt;
                cam.Render();
                cam.targetTexture = null;
            }
            var prev = RenderTexture.active;
            RenderTexture.active = rt;
            var tex = new Texture2D(w, h, TextureFormat.RGB24, false);
            tex.ReadPixels(new Rect(0, 0, w, h), 0, 0);
            tex.Apply();
            RenderTexture.active = prev;
            if (line)
            {
                var px = tex.GetPixels32();
                for (int y = h / 2 - 1; y <= h / 2; y++)
                    for (int x = 0; x < w; x++) px[y * w + x] = new Color32(230, 30, 30, 255);
                tex.SetPixels32(px);
                tex.Apply();
            }
            if (crop > 1)
            {
                var src = tex.GetPixels32();
                var dst = new Color32[w * h];
                int cw = w / crop, ch = h / crop, x0 = (w - cw) / 2, y0 = (h - ch) / 2;
                for (int y = 0; y < h; y++)
                    for (int x = 0; x < w; x++) dst[y * w + x] = src[(y0 + y / crop) * w + x0 + x / crop];
                tex.SetPixels32(dst);
                tex.Apply();
            }
            File.WriteAllBytes(Path.Combine(OutDir, file), tex.EncodeToPNG());
            Object.DestroyImmediate(tex);
            rt.Release();
            Object.DestroyImmediate(rt);
        }

        // ------------------------------------------------------------------------------------------- assets
        static Material MakeMaterial(string name, string texPath)
        {
            var path = $"{Materials}/{name}.mat";
            var mat = AssetDatabase.LoadAssetAtPath<Material>(path);
            var shader = GraphicsSettings.currentRenderPipeline != null
                ? GraphicsSettings.currentRenderPipeline.defaultShader
                : Shader.Find("Standard");
            if (mat == null)
            {
                mat = new Material(shader) { name = name };
                AssetDatabase.CreateAsset(mat, path);
            }
            mat.shader = shader;
            var tex = AssetDatabase.LoadAssetAtPath<Texture2D>(texPath);
            mat.mainTexture = tex;
            if (mat.HasProperty("_BaseMap")) mat.SetTexture("_BaseMap", tex);
            if (mat.HasProperty("_BaseColor")) mat.SetColor("_BaseColor", Color.white);
            if (mat.HasProperty("_Smoothness")) mat.SetFloat("_Smoothness", 0.08f);   // painted, matte
            if (mat.HasProperty("_Glossiness")) mat.SetFloat("_Glossiness", 0.08f);
            if (mat.HasProperty("_EnvironmentReflections")) { mat.SetFloat("_EnvironmentReflections", 0f); mat.EnableKeyword("_ENVIRONMENTREFLECTIONS_OFF"); }
            EditorUtility.SetDirty(mat);
            return mat;
        }

        static Material MakeTint(string name, Material src, Color tint)
        {
            var path = $"{Materials}/{name}.mat";
            var m = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (m == null)
            {
                m = new Material(src) { name = name };
                AssetDatabase.CreateAsset(m, path);
            }
            else m.CopyPropertiesFromMaterial(src);
            if (m.HasProperty("_BaseColor")) m.SetColor("_BaseColor", tint);
            else m.color = tint;
            EditorUtility.SetDirty(m);
            return m;
        }

        static void ConfigureModel(string path, Material skin, Material gear, bool humanoid)
        {
            var imp = (ModelImporter)AssetImporter.GetAtPath(path);
            imp.importCameras = false;
            imp.importLights = false;
            imp.importAnimation = false;
            imp.importBlendShapes = humanoid;          // Skinny, Brawny, Fat, the ear shapes
            imp.materialImportMode = ModelImporterMaterialImportMode.ImportViaMaterialDescription;
            imp.AddRemap(new AssetImporter.SourceAssetIdentifier(typeof(Material), "M_Troll_Skin"), skin);
            imp.AddRemap(new AssetImporter.SourceAssetIdentifier(typeof(Material), "M_Troll_Gear"), gear);
            if (humanoid)
            {
                imp.animationType = ModelImporterAnimationType.Human;
                imp.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
                imp.optimizeGameObjects = false;          // the Socket_ transforms must stay in the hierarchy
            }
            else imp.animationType = ModelImporterAnimationType.None;
            imp.SaveAndReimport();                     // GoblinModelPostprocessor keeps them Read/Write (the merge reads them)
        }

        static Transform Find(Transform root, string name)
        {
            foreach (var t in root.GetComponentsInChildren<Transform>(true))
                if (t.name == name) return t;
            return null;
        }

        static void EnsureFolder(string path)
        {
            if (AssetDatabase.IsValidFolder(path)) return;
            var parent = Path.GetDirectoryName(path).Replace('\\', '/');
            EnsureFolder(parent);
            AssetDatabase.CreateFolder(parent, Path.GetFileName(path));
        }
    }
}
