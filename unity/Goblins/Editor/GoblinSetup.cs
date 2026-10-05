using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;

namespace Goblins.EditorTools
{
    /// <summary>
    /// Builds the goblin materials, prop prefabs, goblin prefabs and the showcase scene from the files
    /// exported by Blender (Assets/Goblins/Models, Assets/Goblins/Textures).
    ///
    /// Runs once by itself the first time the goblin files are imported; afterwards use
    /// Tools > Goblins > Rebuild Prefabs and Showcase (e.g. after a new export from Blender).
    ///
    ///   Goblin_Base       plain goblin: body + loincloth, Humanoid Animator, no props
    ///   Goblin_Spearman   variant of Goblin_Base: crude spear used two-handed as a polearm, helmet, pauldron, pouch, knife
    ///   Goblin_Swordsman  variant of Goblin_Base: crude sword and shield, helmet, pauldron, pouch
    ///   Goblin_Chief      variant of Goblin_Base: great axe, bone crown, fur mantle, war banner
    ///   Goblin_Archer     variant of Goblin_Base: short bow, arrow, quiver; GoblinArcher draws the string and
    ///                     lays the arrow, custom clips in Models/Anims (Goblin@Bow_*.fbx, made in Blender)
    ///   Goblin_Shaman     variant of Goblin_Base: forked skull staff, feather headdress, hide cape, shaman paint;
    ///                     GoblinShaman makes the staff glow and casts Hex (bolt) and Chant (ground ring)
    ///   Props/Prop_*      one prefab per prop; drop it under the socket it names and Reset its transform
    /// A report and verification renders go to Logs/GoblinSetup.
    /// </summary>
    [InitializeOnLoad]
    public static class GoblinSetup
    {
        public const string Root = "Assets/Goblins";
        const string Models = Root + "/Models";
        const string PropModels = Models + "/Props";
        public const string Anims = Models + "/Anims";         // Goblin@<clip>.fbx: clips authored on the goblin rig
        const string Textures = Root + "/Textures";
        const string Materials = Root + "/Materials";
        const string Prefabs = Root + "/Prefabs";
        const string PropPrefabs = Prefabs + "/Props";
        const string Scenes = Root + "/Scenes";
        const string ShowcaseScene = Scenes + "/Goblins_Showcase.unity";

        /// <summary>Armed variants of Goblin_Base (all wear the harness and wraps).</summary>
        public static readonly (string prefab, (string prop, string socket)[] props)[] Loadouts =
        {
            ("Goblin_Spearman", new[]
            {
                ("Prop_Spear", "Socket_RightHand"),
                ("Prop_Helmet", "Socket_Helm"),
                ("Prop_Pauldron", "Socket_LeftShoulder"),
                ("Prop_Pouch", "Socket_RightHip"),
                ("Prop_Knife", "Socket_LeftHip"),
            }),
            ("Goblin_Chief", new[]
            {
                ("Prop_GreatAxe", "Socket_RightHand"),
                ("Prop_BoneCrown", "Socket_Helm"),
                ("Prop_SkullPauldron", "Socket_LeftShoulder"),
                ("Prop_ChiefBuckle", "Socket_Belt"),
                ("Prop_Pouch", "Socket_RightHip"),
                ("Prop_WarBanner", "Socket_Back"),
            }),
            ("Goblin_Swordsman", new[]
            {
                ("Prop_Sword", "Socket_RightHand"),
                ("Prop_Shield", "Socket_LeftForearm"),
                ("Prop_Helmet", "Socket_Helm"),
                ("Prop_Pauldron", "Socket_LeftShoulder"),
                ("Prop_Pouch", "Socket_RightHip"),
            }),
            ("Goblin_Archer", new[]
            {
                ("Prop_Shortbow", "Socket_LeftHand"),
                ("Prop_Arrow", "Socket_RightHand"),
                ("Prop_Quiver", "Socket_Back"),
                ("Prop_LeatherCap", "Socket_Helm"),
                ("Prop_Knife", "Socket_LeftHip"),
                ("Prop_Pouch", "Socket_RightHip"),
            }),
            ("Goblin_Shaman", new[]
            {
                ("Prop_ShamanStaff", "Socket_RightHand"),
                ("Prop_ShamanHeaddress", "Socket_Helm"),
                ("Prop_Necklace", "Socket_Chest"),
                ("Prop_Pouch", "Socket_RightHip"),
                ("Prop_SkullTrophy", "Socket_Belt"),
            }),
        };

        /// <summary>Clips with the looping flag; every clip bakes its root into the pose (in place, body turn kept).</summary>
        static readonly HashSet<string> LoopingClips = new HashSet<string> { "Bow_Ready", "Shaman_Idle", "Crossbow_Ready" };

        // ---- variation rolled per goblin by GoblinAppearance ------------------------------------------------
        static GoblinAppearance.Optional[] Outfits(float harness, float wraps) => new[]
        {
            new GoblinAppearance.Optional { part = "Outfit_Harness", chance = harness },
            new GoblinAppearance.Optional { part = "Outfit_Wraps", chance = wraps },
        };

        static GoblinAppearance.Slot Slot(Dictionary<string, GameObject> props, string name, string[] sockets,
                                          params (string prop, float weight)[] options) => new GoblinAppearance.Slot
        {
            name = name,
            sockets = sockets,
            options = options.Select(o => new GoblinAppearance.Option
            {
                prop = o.prop == null ? null : props[o.prop],
                weight = o.weight,
            }).ToArray(),
        };

        static readonly string[] Hand = { "Socket_RightHand" }, Forearm = { "Socket_LeftForearm" }, Helm = { "Socket_Helm" },
            Shoulders = { "Socket_LeftShoulder", "Socket_RightShoulder" }, Hips = { "Socket_RightHip", "Socket_LeftHip" },
            Back = { "Socket_Back" }, Chest = { "Socket_Chest" }, Belt = { "Socket_Belt" };

        /// <summary>Gear shared by the armed goblins (weapon slots are added per kind).</summary>
        static List<GoblinAppearance.Slot> ArmedSlots(Dictionary<string, GameObject> p) => new List<GoblinAppearance.Slot>
        {
            Slot(p, "Head", Helm, ("Prop_Helmet", 3f), ("Prop_PotHelm", 1.5f), ("Prop_LeatherCap", 2f), ("Prop_Hair", 1.5f), (null, 2f)),
            Slot(p, "Shoulder", Shoulders, ("Prop_Pauldron", 1f), (null, 1f)),
            Slot(p, "HipGear", Hips, ("Prop_Pouch", 2f), ("Prop_Waterskin", 1.5f), (null, 2f)),
            Slot(p, "HipBlade", Hips, ("Prop_Knife", 1.5f), (null, 2.5f)),
            Slot(p, "Back", Back, ("Prop_Sack", 1f), (null, 4f)),
            Slot(p, "Chest", Chest, ("Prop_Necklace", 1f), (null, 3f)),
            Slot(p, "Belt", Belt, ("Prop_SkullTrophy", 0.7f), (null, 4f)),
        };

        static GoblinAppearance.Slot[] SpearmanSlots(Dictionary<string, GameObject> p) =>
            new[] { Slot(p, "Weapon", Hand, ("Prop_Spear", 1.2f), ("Prop_Glaive", 1f)) }.Concat(ArmedSlots(p)).ToArray();

        static GoblinAppearance.Slot[] SwordsmanSlots(Dictionary<string, GameObject> p) => new[]
        {
            Slot(p, "Weapon", Hand, ("Prop_Sword", 1f), ("Prop_Cleaver", 1f), ("Prop_Axe", 1f), ("Prop_Club", 1f)),
            Slot(p, "Shield", Forearm, ("Prop_Shield", 1.4f), ("Prop_ShieldPlank", 1f)),
        }.Concat(ArmedSlots(p)).ToArray();

        static GoblinAppearance.Slot[] UnarmedSlots(Dictionary<string, GameObject> p) => new[]
        {
            Slot(p, "Head", Helm, ("Prop_Hair", 3f), ("Prop_LeatherCap", 1.5f), ("Prop_PotHelm", 0.7f), (null, 4f)),
            Slot(p, "HipGear", Hips, ("Prop_Pouch", 2f), ("Prop_Waterskin", 1.5f), (null, 2f)),
            Slot(p, "HipBlade", Hips, ("Prop_Knife", 1f), (null, 3f)),
            Slot(p, "Back", Back, ("Prop_Sack", 2f), (null, 3f)),
            Slot(p, "Chest", Chest, ("Prop_Necklace", 1f), (null, 3f)),
            Slot(p, "Belt", Belt, ("Prop_SkullTrophy", 0.5f), (null, 4f)),
        };

        static GoblinAppearance.Shape[] Shapes => new[]
        {
            new GoblinAppearance.Shape { name = "Fat", chance = 0.3f, weight = new Vector2(0.5f, 1f), group = "build" },
            new GoblinAppearance.Shape { name = "Skinny", chance = 0.35f, weight = new Vector2(0.5f, 1f), group = "build" },
            new GoblinAppearance.Shape { name = "Brawny", chance = 0.15f, weight = new Vector2(0.5f, 1f), group = "build" },
            new GoblinAppearance.Shape { name = "EarsDroop", chance = 0.25f, weight = new Vector2(0.5f, 1f) },
            new GoblinAppearance.Shape { name = "EarTornL", chance = 0.12f, weight = new Vector2(1f, 1f) },
            new GoblinAppearance.Shape { name = "EarTornR", chance = 0.12f, weight = new Vector2(1f, 1f) },
        };

        static GoblinAppearance.Slot[] ChiefSlots(Dictionary<string, GameObject> p) => new[]
        {
            Slot(p, "Weapon", Hand, ("Prop_GreatAxe", 1f)),
            Slot(p, "Head", Helm, ("Prop_BoneCrown", 1f)),
            Slot(p, "Shoulder", new[] { "Socket_LeftShoulder" }, ("Prop_SkullPauldron", 4f), (null, 1f)),
            Slot(p, "Belt", Belt, ("Prop_ChiefBuckle", 1f)),
            Slot(p, "Back", Back, ("Prop_WarBanner", 3f), (null, 1f)),
            Slot(p, "HipGear", Hips, ("Prop_Pouch", 2f), ("Prop_Waterskin", 1f), (null, 1f)),
            Slot(p, "HipBlade", Hips, ("Prop_Knife", 1f), (null, 1f)),
        };

        /// <summary>The archer always has bow, arrow and quiver; the quiver strap replaces the harness.</summary>
        static GoblinAppearance.Slot[] ArcherSlots(Dictionary<string, GameObject> p) => new[]
        {
            Slot(p, "Bow", new[] { "Socket_LeftHand" }, ("Prop_Shortbow", 1f)),
            Slot(p, "Arrow", Hand, ("Prop_Arrow", 1f)),
            Slot(p, "Quiver", Back, ("Prop_Quiver", 1f)),
            Slot(p, "Head", Helm, ("Prop_LeatherCap", 3f), ("Prop_Hair", 2f), ("Prop_Helmet", 0.7f), (null, 2f)),
            Slot(p, "HipGear", Hips, ("Prop_Pouch", 2f), ("Prop_Waterskin", 1.5f), (null, 1.5f)),
            Slot(p, "HipBlade", Hips, ("Prop_Knife", 2f), (null, 1.5f)),
            Slot(p, "Chest", Chest, ("Prop_Necklace", 1f), (null, 3f)),
            Slot(p, "Belt", Belt, ("Prop_SkullTrophy", 0.5f), (null, 4f)),
        };

        /// <summary>Archers are the scrawny ones.</summary>
        static GoblinAppearance.Shape[] ArcherShapes => new[]
        {
            new GoblinAppearance.Shape { name = "Skinny", chance = 0.5f, weight = new Vector2(0.5f, 1f), group = "build" },
            new GoblinAppearance.Shape { name = "Fat", chance = 0.1f, weight = new Vector2(0.25f, 0.75f), group = "build" },
            new GoblinAppearance.Shape { name = "EarsDroop", chance = 0.25f, weight = new Vector2(0.5f, 1f) },
            new GoblinAppearance.Shape { name = "EarTornL", chance = 0.12f, weight = new Vector2(1f, 1f) },
            new GoblinAppearance.Shape { name = "EarTornR", chance = 0.12f, weight = new Vector2(1f, 1f) },
        };

        /// <summary>The shaman always has the staff; usually the feathers, sometimes just his own hair.</summary>
        static GoblinAppearance.Slot[] ShamanSlots(Dictionary<string, GameObject> p) => new[]
        {
            Slot(p, "Staff", Hand, ("Prop_ShamanStaff", 1f)),
            Slot(p, "Head", Helm, ("Prop_ShamanHeaddress", 4f), ("Prop_Hair", 1f)),
            Slot(p, "Chest", Chest, ("Prop_Necklace", 3f), (null, 1f)),
            Slot(p, "HipGear", Hips, ("Prop_Pouch", 2f), ("Prop_Waterskin", 1f), (null, 1f)),
            Slot(p, "HipBlade", Hips, ("Prop_Knife", 1f), (null, 2f)),
            Slot(p, "Belt", Belt, ("Prop_SkullTrophy", 2f), (null, 1f)),
        };

        /// <summary>Old and bony: droopy ears, often skinny.</summary>
        static GoblinAppearance.Shape[] ShamanShapes => new[]
        {
            new GoblinAppearance.Shape { name = "Skinny", chance = 0.45f, weight = new Vector2(0.5f, 1f), group = "build" },
            new GoblinAppearance.Shape { name = "Fat", chance = 0.15f, weight = new Vector2(0.25f, 0.75f), group = "build" },
            new GoblinAppearance.Shape { name = "EarsDroop", chance = 0.6f, weight = new Vector2(0.5f, 1f) },
            new GoblinAppearance.Shape { name = "EarTornL", chance = 0.15f, weight = new Vector2(1f, 1f) },
            new GoblinAppearance.Shape { name = "EarTornR", chance = 0.15f, weight = new Vector2(1f, 1f) },
        };

        /// <summary>The chief is always brawny, often fat too, and his ears carry the scars of leadership.</summary>
        static GoblinAppearance.Shape[] ChiefShapes => new[]
        {
            new GoblinAppearance.Shape { name = "Brawny", chance = 1f, weight = new Vector2(0.75f, 1f), group = "brawn" },
            new GoblinAppearance.Shape { name = "Fat", chance = 0.6f, weight = new Vector2(0.5f, 1f), group = "build" },
            new GoblinAppearance.Shape { name = "EarTornL", chance = 0.35f, weight = new Vector2(1f, 1f) },
            new GoblinAppearance.Shape { name = "EarTornR", chance = 0.35f, weight = new Vector2(1f, 1f) },
            new GoblinAppearance.Shape { name = "EarsDroop", chance = 0.1f, weight = new Vector2(0.5f, 0.75f) },
        };

        static GoblinAppearance.Push[] Pushes
        {
            get
            {
                var list = new List<GoblinAppearance.Push>();
                foreach (var (socket, fat, skinny) in new[] { ("Socket_RightHip", 0.016f, -0.009f), ("Socket_LeftHip", 0.016f, -0.009f),
                             ("Socket_Belt", 0.028f, -0.014f), ("Socket_Chest", 0.008f, -0.005f), ("Socket_Back", 0.01f, -0.006f) })
                {
                    list.Add(new GoblinAppearance.Push { shape = "Fat", socket = socket, metres = fat });
                    list.Add(new GoblinAppearance.Push { shape = "Skinny", socket = socket, metres = skinny });
                }
                // brawny: bigger deltoids, forearms and chest lift the gear sitting on them
                foreach (var (socket, m) in new[] { ("Socket_LeftShoulder", 0.016f), ("Socket_RightShoulder", 0.016f),
                             ("Socket_LeftForearm", 0.011f), ("Socket_RightForearm", 0.011f), ("Socket_Chest", 0.012f),
                             ("Socket_Back", 0.01f), ("Socket_RightHip", 0.006f), ("Socket_LeftHip", 0.006f), ("Socket_Belt", 0.004f) })
                    list.Add(new GoblinAppearance.Push { shape = "Brawny", socket = socket, metres = m });
                return list.ToArray();
            }
        }

        static GoblinSetup() => EditorApplication.delayCall += () => AutoBuild(20);

        static void AutoBuild(int retries)
        {
            if (!File.Exists(Models + "/Goblin.fbx") || File.Exists(Prefabs + "/Goblin_Spearman.prefab") ||
                File.Exists(Prefabs + "/Goblin_Grunt.prefab")) return;
            bool ready = AssetImporter.GetAtPath(Models + "/Goblin.fbx") is ModelImporter &&
                         AssetDatabase.LoadAssetAtPath<Texture2D>(Textures + "/T_Goblin_Gear.png") != null &&
                         !EditorApplication.isCompiling && !EditorApplication.isUpdating;
            if (ready) Build();
            else if (retries > 0) EditorApplication.delayCall += () => AutoBuild(retries - 1);
        }

        static string OutDir => Path.GetFullPath(Path.Combine(Application.dataPath, "..", "Logs", "GoblinSetup"));

        [MenuItem("Tools/Goblins/Rebuild Prefabs and Showcase")]
        public static void Build()
        {
            Directory.CreateDirectory(OutDir);
            var log = new StringBuilder();
            Application.LogCallback onLog = (c, s, t) => { if (t != LogType.Log) log.AppendLine($"[{t}] {c}"); };
            Application.logMessageReceived += onLog;
            try
            {
                foreach (var d in new[] { Materials, Prefabs, PropPrefabs, Scenes }) EnsureFolder(d);

                foreach (var guid in AssetDatabase.FindAssets("t:Texture2D", new[] { Textures }))
                {
                    if (AssetDatabase.GUIDToAssetPath(guid).Contains("Glow")) continue;     // MakeMagicMaterial sets it up
                    var ti = (TextureImporter)AssetImporter.GetAtPath(AssetDatabase.GUIDToAssetPath(guid));
                    ti.maxTextureSize = AssetDatabase.GUIDToAssetPath(guid).Contains("Gear") ? 2048 : 1024;   // gear atlas holds every prop
                    ti.sRGBTexture = true;
                    ti.mipmapEnabled = true;
                    ti.textureCompression = TextureImporterCompression.CompressedHQ;
                    ti.SaveAndReimport();
                }
                var skin = MakeMaterial("M_Goblin_Skin", Textures + "/T_Goblin_Skin.png");
                var gear = MakeMaterial("M_Goblin_Gear", Textures + "/T_Goblin_Gear.png");
                var warpaint = MakeMaterial("M_Goblin_Skin_Warpaint", Textures + "/T_Goblin_Skin_Warpaint.png");
                var chiefSkin = MakeMaterial("M_Goblin_Skin_Chief", Textures + "/T_Goblin_Skin_Chief.png");
                var shamanSkin = MakeMaterial("M_Goblin_Skin_Shaman", Textures + "/T_Goblin_Skin_Shaman.png");
                var magicMat = MakeMagicMaterial();
                var skins = new[]                           // a material listed twice is twice as likely
                {
                    skin, skin,
                    MakeTint("M_Goblin_Skin_Dark", skin, new Color(0.78f, 0.82f, 0.74f)),
                    MakeTint("M_Goblin_Skin_Olive", skin, new Color(0.95f, 0.9f, 0.72f)),
                    MakeTint("M_Goblin_Skin_Grey", skin, new Color(0.82f, 0.86f, 0.86f)),
                    warpaint,
                    MakeTint("M_Goblin_Skin_WarpaintDark", warpaint, new Color(0.78f, 0.82f, 0.74f)),
                };

                var modelPath = Models + "/Goblin.fbx";
                ConfigureModel(modelPath, skin, gear, humanoid: true);
                var mi = (ModelImporter)AssetImporter.GetAtPath(modelPath);
                if (!mi.humanDescription.human.Any(h => h.humanName == "Jaw" && h.boneName == "Jaw"))
                    mi.SaveAndReimport();                  // GoblinModelPostprocessor pins the Jaw on this pass
                var avatar = AssetDatabase.LoadAllAssetsAtPath(modelPath).OfType<Avatar>().FirstOrDefault();
                var hd = ((ModelImporter)AssetImporter.GetAtPath(modelPath)).humanDescription;
                log.AppendLine($"avatar valid={avatar?.isValid} human={avatar?.isHuman} bones={hd.human.Length} " +
                               $"jaw={hd.human.FirstOrDefault(h => h.humanName == "Jaw").boneName}");

                var props = new Dictionary<string, GameObject>();
                foreach (var guid in AssetDatabase.FindAssets("t:GameObject", new[] { PropModels }))
                {
                    var path = AssetDatabase.GUIDToAssetPath(guid);
                    ConfigureModel(path, skin, gear, humanoid: false);
                    var model = AssetDatabase.LoadAssetAtPath<GameObject>(path);
                    var wrapper = new GameObject(model.name);
                    var inst = (GameObject)PrefabUtility.InstantiatePrefab(model, wrapper.transform);
                    inst.name = model.name + "_Mesh";
                    // the mesh is modelled in socket space: identity under the wrapper, wrapper identity under the socket
                    inst.transform.SetLocalPositionAndRotation(Vector3.zero, Quaternion.identity);
                    inst.transform.localScale = Vector3.one;
                    props[model.name] = PrefabUtility.SaveAsPrefabAsset(wrapper, $"{PropPrefabs}/{model.name}.prefab");
                    Object.DestroyImmediate(wrapper);
                }
                log.AppendLine("prop prefabs: " + string.Join(", ", props.Keys.OrderBy(k => k)));
                ConfigureClips(avatar, log);

                // archer extras: the flying arrow and the bow string's material
                GoblinArrow projectile = null;
                if (props.TryGetValue("Prop_Arrow", out var arrowProp))
                {
                    var pgo = (GameObject)PrefabUtility.InstantiatePrefab(arrowProp);
                    pgo.name = "Arrow_Projectile";
                    pgo.AddComponent<GoblinArrow>();
                    projectile = PrefabUtility.SaveAsPrefabAsset(pgo, Prefabs + "/Arrow_Projectile.prefab").GetComponent<GoblinArrow>();
                    Object.DestroyImmediate(pgo);
                }
                var stringMat = AssetDatabase.LoadAssetAtPath<Material>(Materials + "/M_Goblin_BowString.mat");
                if (stringMat == null)
                {
                    stringMat = new Material(Shader.Find("Universal Render Pipeline/Unlit") ?? Shader.Find("Unlit/Color"));
                    AssetDatabase.CreateAsset(stringMat, Materials + "/M_Goblin_BowString.mat");
                }
                stringMat.color = new Color(0.78f, 0.72f, 0.58f);
                if (stringMat.HasProperty("_BaseColor")) stringMat.SetColor("_BaseColor", new Color(0.78f, 0.72f, 0.58f));
                EditorUtility.SetDirty(stringMat);

                var baseGo = (GameObject)PrefabUtility.InstantiatePrefab(AssetDatabase.LoadAssetAtPath<GameObject>(modelPath));
                baseGo.name = "Goblin_Base";
                SetActive(baseGo, "Outfit_Harness", false);
                SetActive(baseGo, "Outfit_Wraps", false);
                SetActive(baseGo, "Outfit_FurMantle", false);
                SetActive(baseGo, "Outfit_ShamanCloak", false);
                var anim = baseGo.GetComponent<Animator>() ?? baseGo.AddComponent<Animator>();
                anim.avatar = avatar;
                anim.applyRootMotion = false;
                anim.cullingMode = AnimatorCullingMode.CullUpdateTransforms;
                var look = baseGo.GetComponent<GoblinAppearance>() ?? baseGo.AddComponent<GoblinAppearance>();
                look.skins = skins;
                look.optional = Outfits(0.25f, 0.35f);
                look.slots = UnarmedSlots(props);
                look.shapes = Shapes;
                look.pushes = Pushes;
                var basePrefab = PrefabUtility.SaveAsPrefabAsset(baseGo, Prefabs + "/Goblin_Base.prefab");
                Object.DestroyImmediate(baseGo);

                // the first armed prefab was called Goblin_Grunt: rename it so scene references survive
                if (File.Exists(Prefabs + "/Goblin_Grunt.prefab") && !File.Exists(Prefabs + "/Goblin_Spearman.prefab"))
                    AssetDatabase.MoveAsset(Prefabs + "/Goblin_Grunt.prefab", Prefabs + "/Goblin_Spearman.prefab");
                var variants = new List<GameObject>();
                foreach (var (prefabName, loadout) in Loadouts)
                {
                    var go = (GameObject)PrefabUtility.InstantiatePrefab(basePrefab);
                    go.name = prefabName;
                    SetActive(go, "Outfit_Harness", true);
                    SetActive(go, "Outfit_Wraps", true);
                    var vlook = go.GetComponent<GoblinAppearance>();
                    vlook.optional = Outfits(0.75f, 0.6f);
                    vlook.slots = prefabName == "Goblin_Spearman" ? SpearmanSlots(props) : SwordsmanSlots(props);
                    if (prefabName == "Goblin_Chief")
                    {
                        SetActive(go, "Outfit_Harness", false);
                        SetActive(go, "Outfit_FurMantle", true);
                        vlook.slots = ChiefSlots(props);
                        vlook.optional = new[]
                        {
                            new GoblinAppearance.Optional { part = "Outfit_FurMantle", chance = 1f },
                            new GoblinAppearance.Optional { part = "Outfit_Harness", chance = 0f },
                            new GoblinAppearance.Optional { part = "Outfit_Wraps", chance = 0.5f },
                        };
                        vlook.shapes = ChiefShapes;
                        vlook.skins = new[] { chiefSkin, chiefSkin, MakeTint("M_Goblin_Skin_ChiefDark", chiefSkin, new Color(0.8f, 0.84f, 0.76f)) };
                        vlook.scale = new Vector2(1.25f, 1.3f);
                    }
                    if (prefabName == "Goblin_Archer")
                    {
                        SetActive(go, "Outfit_Harness", false);          // the quiver strap crosses the chest instead
                        vlook.slots = ArcherSlots(props);
                        vlook.optional = Outfits(0f, 0.6f);
                        vlook.shapes = ArcherShapes;
                        vlook.scale = new Vector2(0.88f, 1.0f);
                        var archer = go.GetComponent<GoblinArcher>() ?? go.AddComponent<GoblinArcher>();
                        archer.stringMaterial = stringMat;
                        archer.projectile = projectile;
                    }
                    if (prefabName == "Goblin_Shaman")
                    {
                        SetActive(go, "Outfit_Harness", false);
                        SetActive(go, "Outfit_ShamanCloak", true);
                        vlook.slots = ShamanSlots(props);
                        vlook.optional = new[]
                        {
                            new GoblinAppearance.Optional { part = "Outfit_ShamanCloak", chance = 1f },
                            new GoblinAppearance.Optional { part = "Outfit_Harness", chance = 0f },
                            new GoblinAppearance.Optional { part = "Outfit_Wraps", chance = 0.5f },
                        };
                        vlook.shapes = ShamanShapes;
                        vlook.skins = new[] { shamanSkin, shamanSkin, MakeTint("M_Goblin_Skin_ShamanDark", shamanSkin, new Color(0.8f, 0.84f, 0.76f)) };
                        vlook.scale = new Vector2(0.9f, 1.0f);
                        var shaman = go.GetComponent<GoblinShaman>() ?? go.AddComponent<GoblinShaman>();
                        shaman.magicMaterial = magicMat;
                    }
                    foreach (var (prop, socket) in loadout)
                    {
                        var s = Find(go.transform, socket);
                        if (s == null || !props.ContainsKey(prop)) { log.AppendLine($"MISSING {prop} -> {socket}"); continue; }
                        var p = (GameObject)PrefabUtility.InstantiatePrefab(props[prop], s);
                        p.transform.SetLocalPositionAndRotation(Vector3.zero, Quaternion.identity);
                        p.transform.localScale = Vector3.one;
                    }
                    variants.Add(PrefabUtility.SaveAsPrefabAsset(go, $"{Prefabs}/{prefabName}.prefab"));
                    Object.DestroyImmediate(go);
                }
                log.AppendLine("prefabs: Goblin_Base, " + string.Join(", ", Loadouts.Select(l => l.prefab)) + " (variants of Goblin_Base)");

                BuildShowcase(basePrefab, variants, log);
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
                Debug.Log("Goblin setup finished: " + Path.Combine(OutDir, "setup_report.txt"));
            }
        }

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
            imp.importBlendShapes = humanoid;          // body variation (Fat, Skinny, ears) lives in blend shapes
            imp.isReadable = false;
            imp.materialImportMode = ModelImporterMaterialImportMode.ImportViaMaterialDescription;
            imp.AddRemap(new AssetImporter.SourceAssetIdentifier(typeof(Material), "M_Goblin_Skin"), skin);
            imp.AddRemap(new AssetImporter.SourceAssetIdentifier(typeof(Material), "M_Goblin_Gear"), gear);
            if (humanoid)
            {
                imp.animationType = ModelImporterAnimationType.Human;
                imp.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
                imp.optimizeGameObjects = false;          // the Socket_ transforms must stay in the hierarchy
            }
            else
            {
                imp.animationType = ModelImporterAnimationType.None;
            }
            imp.SaveAndReimport();
        }

        /// <summary>Additive glow for the shaman's spells: T_Goblin_Glow (a soft round dot) on URP Particles/Unlit.</summary>
        static Material MakeMagicMaterial()
        {
            var texPath = Textures + "/T_Goblin_Glow.png";
            if (!File.Exists(texPath))
            {
                File.WriteAllBytes(texPath, GoblinFx.GlowTexture().EncodeToPNG());
                AssetDatabase.ImportAsset(texPath, ImportAssetOptions.ForceSynchronousImport);
            }
            var ti = (TextureImporter)AssetImporter.GetAtPath(texPath);
            ti.alphaIsTransparency = true;
            ti.wrapMode = TextureWrapMode.Clamp;
            ti.textureCompression = TextureImporterCompression.Uncompressed;
            ti.SaveAndReimport();
            var tex = AssetDatabase.LoadAssetAtPath<Texture2D>(texPath);
            var path = Materials + "/M_Goblin_Magic.mat";
            var mat = AssetDatabase.LoadAssetAtPath<Material>(path);
            var fresh = GoblinFx.AdditiveMaterial(tex);
            if (mat == null)
            {
                mat = fresh;
                mat.name = "M_Goblin_Magic";
                AssetDatabase.CreateAsset(mat, path);
            }
            else
            {
                mat.shader = fresh.shader;
                mat.CopyPropertiesFromMaterial(fresh);
                mat.shaderKeywords = fresh.shaderKeywords;
                mat.renderQueue = fresh.renderQueue;
                mat.SetOverrideTag("RenderType", "Transparent");
                Object.DestroyImmediate(fresh);
            }
            EditorUtility.SetDirty(mat);
            return mat;
        }

        /// <summary>
        /// Goblin@<clip>.fbx (skeleton + one take, exported by gob_anim.export_clips): Humanoid with Goblin.fbx's avatar,
        /// one clip named after the file, root baked into the pose so the clip plays in place and keeps its body turn.
        /// </summary>
        static void ConfigureClips(Avatar avatar, StringBuilder log)
        {
            if (!AssetDatabase.IsValidFolder(Anims) || avatar == null) return;
            var names = new List<string>();
            foreach (var guid in AssetDatabase.FindAssets("t:Model", new[] { Anims }))
            {
                var path = AssetDatabase.GUIDToAssetPath(guid);
                var file = Path.GetFileNameWithoutExtension(path);
                if (!file.Contains("@")) continue;
                var clipName = file.Substring(file.IndexOf('@') + 1);
                var imp = (ModelImporter)AssetImporter.GetAtPath(path);
                imp.importCameras = false;
                imp.importLights = false;
                imp.materialImportMode = ModelImporterMaterialImportMode.None;
                imp.preserveHierarchy = true;       // the armature is the file's only root: keep it, as in Goblin.fbx
                imp.animationType = ModelImporterAnimationType.Human;
                imp.avatarSetup = ModelImporterAvatarSetup.CopyFromOther;
                imp.sourceAvatar = avatar;
                imp.importAnimation = true;
                imp.animationCompression = ModelImporterAnimationCompression.KeyframeReduction;
                imp.SaveAndReimport();                // take info exists only after an import that succeeded
                var take = imp.importedTakeInfos.FirstOrDefault();
                if (string.IsNullOrEmpty(take.name))
                {
                    log.AppendLine($"clip {file}: no take found");
                    continue;
                }
                bool loop = LoopingClips.Contains(clipName);
                imp.clipAnimations = new[]
                {
                    new ModelImporterClipAnimation
                    {
                        name = clipName,
                        takeName = take.name,
                        firstFrame = Mathf.Round(take.startTime * take.sampleRate),
                        lastFrame = Mathf.Round(take.stopTime * take.sampleRate),
                        loopTime = loop,
                        loopPose = loop,
                        lockRootRotation = true, keepOriginalOrientation = true,
                        lockRootHeightY = true, keepOriginalPositionY = true,
                        lockRootPositionXZ = true, keepOriginalPositionXZ = true,
                    },
                };
                imp.SaveAndReimport();
                var clip = AssetDatabase.LoadAllAssetsAtPath(path).OfType<AnimationClip>().FirstOrDefault(c => c.name == clipName);
                names.Add(clip != null ? $"{clipName} {clip.length:0.00}s{(clip.isLooping ? " loop" : "")} human={clip.humanMotion}" : clipName + " (missing)");
            }
            log.AppendLine("clips: " + string.Join(", ", names));
        }

        static void BuildShowcase(GameObject basePrefab, List<GameObject> variants, StringBuilder log)
        {
            // never discard unsaved work: replace the open scene only when it is clean, otherwise add alongside it
            var previous = SceneManager.GetActiveScene();
            var previousPath = previous.path;
            bool untitled = string.IsNullOrEmpty(previousPath);
            bool dirty = Enumerable.Range(0, SceneManager.sceneCount).Any(i => SceneManager.GetSceneAt(i).isDirty);
            if (untitled && dirty)
            {
                log.AppendLine("showcase skipped: the open scene is untitled and has unsaved changes (save it, then Tools > Goblins > Rebuild)");
                return;
            }
            bool single = !dirty;
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, single ? NewSceneMode.Single : NewSceneMode.Additive);
            SceneManager.SetActiveScene(scene);

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
            ground.transform.localScale = new Vector3(3, 1, 3);
            var groundMat = AssetDatabase.LoadAssetAtPath<Material>(Scenes + "/M_ShowcaseGround.mat");
            if (groundMat == null)
            {
                groundMat = new Material(GraphicsSettings.currentRenderPipeline != null
                    ? GraphicsSettings.currentRenderPipeline.defaultShader : Shader.Find("Standard"));
                AssetDatabase.CreateAsset(groundMat, Scenes + "/M_ShowcaseGround.mat");
            }
            groundMat.color = new Color(0.36f, 0.42f, 0.24f);
            if (groundMat.HasProperty("_Smoothness")) groundMat.SetFloat("_Smoothness", 0f);
            ground.GetComponent<Renderer>().sharedMaterial = groundMat;

            var lineup = new List<(GameObject go, float x)>();
            var all = new[] { basePrefab }.Concat(variants).ToList();
            for (int i = 0; i < all.Count; i++)
            {
                var go = (GameObject)PrefabUtility.InstantiatePrefab(all[i], scene);
                float x = (i - (all.Count - 1) * 0.5f) * 1.3f;
                go.transform.position = new Vector3(x, 0, 0);
                lineup.Add((go, x));
            }

            // goblins face +Z; cameras look back at them
            var close = MakeCamera("CAM_Close", new Vector3(0, 1.25f, 1.1f * all.Count + 0.6f), new Vector3(0, 0.55f, 0), 38);   // fits the lineup
            var colony = MakeCamera("CAM_Colony", new Vector3(0, 40 * Mathf.Sin(50 * Mathf.Deg2Rad), 40 * Mathf.Cos(50 * Mathf.Deg2Rad)),
                                    new Vector3(0, 0.5f, 0), 30);
            close.tag = "MainCamera";

            Render(close, "showcase_close.png", 1600, 900);
            Render(colony, "showcase_colony_40m.png", 1600, 900);
            // Humanoid muscle pose (the retargeting path), rendered and then reverted
            foreach (var (go, x) in lineup)
            {
                RelaxedPose(go);
                go.transform.position = new Vector3(x, 0, 0);
            }
            Render(close, "showcase_posed.png", 1600, 900);
            foreach (var (go, x) in lineup)
            {
                PrefabUtility.RevertPrefabInstance(go, InteractionMode.AutomatedAction);
                go.transform.position = new Vector3(x, 0, 0);
            }

            EditorSceneManager.SaveScene(scene, ShowcaseScene);
            log.AppendLine($"showcase scene: {ShowcaseScene} (built {(single ? "as the only open scene, then reopened " + (untitled ? "a new empty scene" : previousPath) : "alongside your unsaved scene, then closed")})");
            if (single && !untitled)
                EditorSceneManager.OpenScene(previousPath, OpenSceneMode.Single);
            else if (single)
                EditorSceneManager.NewScene(NewSceneSetup.DefaultGameObjects, NewSceneMode.Single);
            else
            {
                SceneManager.SetActiveScene(previous);
                EditorSceneManager.CloseScene(scene, true);
            }
        }

        static void RelaxedPose(GameObject go)
        {
            var anim = go.GetComponent<Animator>();
            go.transform.position = Vector3.zero;            // HumanPose body position is world-space: pose at the origin
            var h = new HumanPoseHandler(anim.avatar, go.transform);
            var pose = new HumanPose();
            h.GetHumanPose(ref pose);
            for (int i = 0; i < pose.muscles.Length; i++)
            {
                var n = HumanTrait.MuscleName[i];
                pose.muscles[i] =
                    n.Contains("Stretched") ? -0.65f :
                    n.Contains("Arm Down-Up") ? -0.55f :
                    n.Contains("Arm Front-Back") ? 0.15f :
                    n.Contains("Forearm Stretch") ? 0.1f :
                    n.Contains("Upper Leg In-Out") ? 0.1f :
                    n == "Spine Front-Back" || n == "Chest Front-Back" ? 0.25f :
                    n == "Neck Nod Down-Up" ? -0.2f : 0f;
            }
            h.SetHumanPose(ref pose);
            h.Dispose();
        }

        static Camera MakeCamera(string name, Vector3 pos, Vector3 target, float fov)
        {
            var cam = new GameObject(name).AddComponent<Camera>();
            cam.transform.position = pos;
            cam.transform.LookAt(target);
            cam.fieldOfView = fov;
            cam.nearClipPlane = 0.05f;
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = new Color(0.47f, 0.52f, 0.58f);
            return cam;
        }

        static void Render(Camera cam, string file, int w, int h)
        {
            var rt = new RenderTexture(w, h, 24, RenderTextureFormat.ARGB32, RenderTextureReadWrite.sRGB);
            foreach (var smr in Object.FindObjectsByType<SkinnedMeshRenderer>(FindObjectsSortMode.None))
                smr.forceMatrixRecalculationPerRender = true;
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
        }

        static void SetActive(GameObject root, string child, bool on)
        {
            var t = Find(root.transform, child);
            if (t != null) t.gameObject.SetActive(on);
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
