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
    /// </summary>
    [InitializeOnLoad]
    public static class TrollSetup
    {
        public const string Root = "Assets/Goblins/Troll";
        const string Models = Root + "/Models";
        const string PropModels = Models + "/Props";
        const string Textures = Root + "/Textures";
        const string Materials = Root + "/Materials";
        const string Prefabs = Root + "/Prefabs";
        const string PropPrefabs = Prefabs + "/Props";
        public const string Model = Models + "/Troll.fbx";
        public const string PrefabPath = Prefabs + "/Troll.prefab";
        const string ClipRoot = "Assets/Kevin Iglesias/Human Animations/Animations/Male";
        const string GoblinPrefab = "Assets/Goblins/Prefabs/Goblin_Base.prefab";

        /// <summary>The checked clips: label, clip names to try, where in the clip the lineup shows it (0..1), two-handed.</summary>
        static readonly (string label, string[] names, float at, bool twoHanded)[] Checks =
        {
            ("Idle", new[] { "Idle01" }, 0.3f, false),
            ("Walk", new[] { "Walk01_Forward [RM]", "Walk01_Forward" }, 0.25f, false),
            ("Run", new[] { "Run01_Forward [RM]", "Run01_Forward" }, 0.25f, false),
            ("Overhead", new[] { "Attack2H02" }, 0.38f, true),        // two-handed chop: fists over the head, then down
            ("Leap", new[] { "Attack2H04" }, 0.23f, true),            // the same with a leap (1 m off the ground on the troll)
            ("Swing1H", new[] { "Attack1H01_R" }, 0.3f, false),       // one-handed, for comparison with the two-handed grip
            ("Hit", new[] { "CombatDamage01" }, 0.2f, false),
            ("Death", new[] { "CombatDeath01", "Death01" }, 1f, false),
        };

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
            Application.LogCallback onLog = (c, s, t) => { if (t != LogType.Log) log.AppendLine($"[{t}] {c}"); };
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

                Verify(prefab, log);
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

        static void Pose(Probe p, float seconds, bool twoHanded)
        {
            if (!p.graph.IsValid()) return;
            p.play.SetTime(seconds);
            p.play.SetTime(seconds);                   // twice: SetTime keeps the previous time for root motion deltas
            p.graph.Evaluate(0f);
            if (p.posture != null) p.posture.Apply();
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
        static string Measure(GameObject prefab, Scene scene, AnimationClip clip, bool twoHanded, float refHeight)
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
                    Pose(p, t, twoHanded);
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

        static Dictionary<string, AnimationClip> FindClips(StringBuilder log)
        {
            var found = new Dictionary<string, AnimationClip>();
            if (!AssetDatabase.IsValidFolder(ClipRoot))
            {
                log.AppendLine($"no Kevin Iglesias Human Animations at {ClipRoot}: retargeting not checked");
                return found;
            }
            foreach (var (label, names, _, _) in Checks)
                foreach (var n in names)
                {
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
                foreach (var (label, _, _, twoH) in Checks)
                {
                    if (!clips.TryGetValue(label, out var clip)) continue;
                    log.AppendLine($"{label,-9} troll : " + Measure(prefab, scene, clip, twoH, trollH));
                    if (goblin != null) log.AppendLine($"{label,-9} goblin: " + Measure(goblin, scene, clip, twoH, trollH));
                }

                // the lineup: one troll per clip at its telling moment, a goblin for scale
                float spacing = 2.6f;
                int count = Checks.Length;
                float x0 = -(count - 1) * 0.5f * spacing;
                for (int i = 0; i < count; i++)
                {
                    clips.TryGetValue(Checks[i].label, out var clip);
                    var p = Spawn(prefab, scene, new Vector3(x0 + i * spacing, 0, 0), 180f, 3 + i, clip);
                    Pose(p, clip != null ? clip.length * Checks[i].at : 0f, Checks[i].twoHanded);
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
                foreach (var p in probes)
                {
                    if (p.graph.IsValid()) p.graph.Destroy();
                    Object.DestroyImmediate(p.go);
                }
                probes.Clear();

                // a strip per clip: six moments, start to end
                foreach (var (label, _, _, twoH) in Checks)
                {
                    if (!clips.TryGetValue(label, out var clip)) continue;
                    for (int i = 0; i < 6; i++)
                    {
                        var p = Spawn(prefab, scene, new Vector3((i - 2.5f) * 2.4f, 0, 0), 160f, 21, clip);
                        Pose(p, clip.length * i / 5f, twoH);
                        probes.Add(p);
                    }
                    Shoot(scene, "CAM_Strip", new Vector3(2f, 2.4f, -9f), new Vector3(0, 1.1f, 0), 34,
                          $"troll_clip_{label.ToLowerInvariant()}.png", 2000, 700);
                    foreach (var p in probes)
                    {
                        if (p.graph.IsValid()) p.graph.Destroy();
                        Object.DestroyImmediate(p.go);
                    }
                    probes.Clear();
                }
                log.AppendLine("renders: " + OutDir);
            }
            finally
            {
                foreach (var p in probes)
                {
                    if (p.graph.IsValid()) p.graph.Destroy();
                    if (p.go != null) Object.DestroyImmediate(p.go);
                }
                ShaderUtil.allowAsyncCompilation = async;
                EditorSceneManager.ClosePreviewScene(scene);
            }
        }

        static void Shoot(Scene scene, string name, Vector3 pos, Vector3 at, float fov, string file, int w, int h)
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
            Render(cam, file, w, h);                   // the first render of fresh skinned meshes can come out empty
            Render(cam, file, w, h);
            Object.DestroyImmediate(cam.gameObject);
        }

        static void Render(Camera cam, string file, int w, int h)
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
