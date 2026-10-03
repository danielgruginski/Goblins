using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using UnityEditor;
using UnityEngine;
using UnityEngine.Animations;
using UnityEngine.Playables;

namespace Goblins.EditorTools
{
    /// <summary>
    /// Dead goblins as static props (bodies to loot in a cave, the aftermath of a fight): a goblin prefab rolled with a
    /// fixed seed, posed at the last frame of one of the Human Animations death clips, its merged mesh baked into one
    /// static mesh lying on the ground, origin under its middle. Tools > Goblins > Bake Dead Goblins writes
    /// Prefabs/Corpses/Goblin_Dead_N (mesh, prefab with a low box collider). Level kits find them by name.
    /// </summary>
    public static class GoblinCorpses
    {
        const string Folder = "Assets/Goblins/Prefabs/Corpses";

        // (goblin prefab, death clip, look seed): a spread of gear and falls
        static readonly (string prefab, string clip, int seed)[] Recipes =
        {
            ("Goblin_Spearman", "HumanM@Death01", 3),
            ("Goblin_Archer", "HumanM@CombatDeath02", 5),
            ("Goblin_Swordsman", "HumanM@Death02", 8),
            ("Goblin_Base", "HumanM@CombatDeath03", 11),
        };

        [MenuItem("Tools/Goblins/Bake Dead Goblins")]
        public static void BakeMenu() => Debug.Log(Bake());

        public static string Bake()
        {
            Directory.CreateDirectory(Folder);
            var log = new StringBuilder();
            for (int i = 0; i < Recipes.Length; i++)
            {
                var (prefab, clip, seed) = Recipes[i];
                log.AppendLine(BakeOne(prefab, clip, seed, $"Goblin_Dead_{i + 1}"));
            }
            AssetDatabase.SaveAssets();
            return log.ToString();
        }

        static T Find<T>(string name, string filter) where T : Object
        {
            var guid = AssetDatabase.FindAssets($"{name} t:{filter}").FirstOrDefault(g => Path.GetFileNameWithoutExtension(AssetDatabase.GUIDToAssetPath(g)) == name);
            return guid != null ? AssetDatabase.LoadAssetAtPath<T>(AssetDatabase.GUIDToAssetPath(guid)) : null;
        }

        static AnimationClip Clip(string fbxName)
        {
            var guid = AssetDatabase.FindAssets(fbxName).FirstOrDefault(g => Path.GetFileNameWithoutExtension(AssetDatabase.GUIDToAssetPath(g)) == fbxName);
            if (guid == null) return null;
            return AssetDatabase.LoadAllAssetsAtPath(AssetDatabase.GUIDToAssetPath(guid)).OfType<AnimationClip>().FirstOrDefault(c => !c.name.StartsWith("__preview__"));
        }

        /// <summary>a mesh's geometry into an existing mesh asset (CopySerialized leaves a runtime mesh's vertices behind)</summary>
        static void Overwrite(Mesh dst, Mesh src)
        {
            dst.Clear();
            dst.indexFormat = src.indexFormat;
            dst.vertices = src.vertices; dst.normals = src.normals; dst.tangents = src.tangents;
            dst.uv = src.uv; dst.colors = src.colors;
            dst.subMeshCount = src.subMeshCount;
            for (int i = 0; i < src.subMeshCount; i++) dst.SetTriangles(src.GetTriangles(i), i);
            dst.RecalculateBounds();
        }

        static string BakeOne(string prefabName, string clipName, int seed, string outName)
        {
            var pf = Find<GameObject>(prefabName, "Prefab");
            var clip = Clip(clipName);
            if (pf == null || clip == null) return $"{outName}: missing {(pf == null ? prefabName : clipName)}";
            var scene = UnityEditor.SceneManagement.EditorSceneManager.NewPreviewScene();     // off every open scene
            var go = Object.Instantiate(pf);                                                    // unlinked: the roll may remove parts
            UnityEngine.SceneManagement.SceneManager.MoveGameObjectToScene(go, scene);
            PlayableGraph graph = default;
            try
            {
                if (go.TryGetComponent<GoblinAppearance>(out var look))
                {
                    Random.InitState(seed);
                    look.Reroll();                       // the same goblin every bake
                }
                var anim = go.GetComponentInChildren<Animator>();
                anim.cullingMode = AnimatorCullingMode.AlwaysAnimate;     // no camera sees it here: it would not pose
                graph = PlayableGraph.Create("corpse");
                graph.SetTimeUpdateMode(DirectorUpdateMode.Manual);
                var output = AnimationPlayableOutput.Create(graph, "pose", anim);
                var cp = AnimationClipPlayable.Create(graph, clip);
                cp.SetApplyFootIK(false);
                cp.SetTime(clip.length - 0.01f);                          // the last frame (not wrapped round)
                output.SetSourcePlayable(cp);
                graph.Evaluate(0f);

                // every visible part (the merged goblin, else its pieces) into one mesh in the goblin's space, by material
                var parts = new List<(Mesh mesh, int sub, Matrix4x4 m, Material mat)>();
                var root = Matrix4x4.TRS(go.transform.position, go.transform.rotation, Vector3.one).inverse;   // keeps the rolled size
                foreach (var r in go.GetComponentsInChildren<Renderer>(false).Where(r => r.enabled && !r.name.StartsWith("FX_")))
                {
                    Mesh m;
                    if (r is SkinnedMeshRenderer smr)
                    {
                        if (smr.sharedMesh == null) continue;
                        m = new Mesh();
                        smr.BakeMesh(m, true);
                    }
                    else if (r is MeshRenderer && r.TryGetComponent<MeshFilter>(out var mf) && mf.sharedMesh != null) m = mf.sharedMesh;
                    else continue;
                    var mats = r.sharedMaterials;
                    var mm = root * (r is SkinnedMeshRenderer ? Matrix4x4.TRS(r.transform.position, r.transform.rotation, Vector3.one) : r.transform.localToWorldMatrix);
                    for (int s = 0; s < m.subMeshCount && s < mats.Length; s++) parts.Add((m, s, mm, mats[s]));
                }
                if (parts.Count == 0) return $"{outName}: nothing to bake";
                var byMat = parts.GroupBy(p => p.mat).ToList();
                var subs = new List<CombineInstance>();
                foreach (var g in byMat)
                {
                    var one = new Mesh { indexFormat = UnityEngine.Rendering.IndexFormat.UInt32 };
                    one.CombineMeshes(g.Select(p => new CombineInstance { mesh = p.mesh, subMeshIndex = p.sub, transform = p.m }).ToArray(), true, true);
                    subs.Add(new CombineInstance { mesh = one, transform = Matrix4x4.identity });
                }
                var body = new Mesh { name = outName, indexFormat = UnityEngine.Rendering.IndexFormat.UInt32 };
                body.CombineMeshes(subs.ToArray(), false, false);
                // lying on the ground, origin under its middle
                var b = body.bounds;
                var shift = new Vector3(-b.center.x, -b.min.y - 0.02f, -b.center.z);
                body.vertices = body.vertices.Select(v => v + shift).ToArray();
                body.RecalculateBounds();
                body.Optimize();

                string meshPath = $"{Folder}/{outName}.asset", prefabPath = $"{Folder}/{outName}.prefab";
                var old = AssetDatabase.LoadAssetAtPath<Mesh>(meshPath);
                if (old != null) { Overwrite(old, body); body = old; EditorUtility.SetDirty(old); }    // keep the asset (and its GUID)
                else AssetDatabase.CreateAsset(body, meshPath);
                var holder = new GameObject(outName);
                holder.AddComponent<MeshFilter>().sharedMesh = body;
                holder.AddComponent<MeshRenderer>().sharedMaterials = byMat.Select(g => g.Key).ToArray();
                var box = holder.AddComponent<BoxCollider>();                                  // something to click and step round
                box.center = body.bounds.center; box.size = Vector3.Scale(body.bounds.size, new Vector3(1f, 0.6f, 1f));
                PrefabUtility.SaveAsPrefabAsset(holder, prefabPath);
                Object.DestroyImmediate(holder);
                return $"{outName}: {prefabName} ({look?.Summary}) on {clipName}, {body.triangles.Length / 3} tris, {body.bounds.size.x:0.00} x {body.bounds.size.z:0.00} x {body.bounds.size.y:0.00} m";
            }
            finally
            {
                if (graph.IsValid()) graph.Destroy();
                Object.DestroyImmediate(go);
                UnityEditor.SceneManagement.EditorSceneManager.ClosePreviewScene(scene);
            }
        }
    }
}
