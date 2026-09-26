using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;

namespace Goblins
{
    /// <summary>
    /// Per-goblin look, rolled in Awake, then merged into one mesh.
    ///
    /// Slots: each slot picks one weighted option (a prop prefab, or nothing) and puts it on the first free
    /// socket from its list (shuffled), replacing the props the prefab shows in the editor.
    /// Optional: skinned outfit pieces switched on by chance.
    /// Shapes: blend shapes (Fat, Skinny, EarsDroop, EarTornL/R) with a chance and weight range; at most one per
    /// group. Pushes move props on a socket outward/inward with a shape (hip gear on a fat belly).
    /// Skins and scale: a material from the list (list one twice to make it twice as likely) and a size.
    /// Merge: all visible parts become one SkinnedMeshRenderer (one submesh per material) with the chosen blend
    /// shapes baked in; goblins that look the same share one mesh.
    /// </summary>
    [DefaultExecutionOrder(-50)]
    public class GoblinAppearance : MonoBehaviour
    {
        [Serializable]
        public class Option
        {
            public GameObject prop;          // null = nothing in this slot
            [Min(0)] public float weight = 1;
        }

        [Serializable]
        public class Slot
        {
            public string name;
            [Tooltip("Sockets this slot may use; the first free one (random order) is taken.")]
            public string[] sockets = Array.Empty<string>();
            public Option[] options = Array.Empty<Option>();
        }

        [Serializable]
        public struct Optional
        {
            public string part;
            [Range(0, 1)] public float chance;
        }

        [Serializable]
        public class Shape
        {
            public string name;
            [Range(0, 1)] public float chance;
            public Vector2 weight = new Vector2(0.5f, 1f);
            [Tooltip("At most one shape per group (e.g. Fat or Skinny).")]
            public string group;
        }

        [Serializable]
        public struct Push
        {
            public string shape;
            public string socket;
            [Tooltip("Metres along the socket's +Z at full shape weight.")]
            public float metres;
        }

        [Tooltip("0 = a different look every time.")]
        public int seed;
        public Slot[] slots = Array.Empty<Slot>();
        public Optional[] optional = Array.Empty<Optional>();
        public Shape[] shapes = Array.Empty<Shape>();
        public Push[] pushes = Array.Empty<Push>();
        public Material[] skins = Array.Empty<Material>();
        public Vector2 scale = new Vector2(0.92f, 1.08f);
        public bool merge = true;

        public int Seed { get; private set; }
        public bool Merged => combined != null && combined.enabled;
        public string Summary { get; private set; } = "";

        SkinnedMeshRenderer combined;
        readonly List<Renderer> sources = new List<Renderer>();
        static readonly Dictionary<string, Mesh> cache = new Dictionary<string, Mesh>();

        void Awake()
        {
            Randomize(seed);
            if (merge) SetMerged(true);
        }

        /// <summary>Roll a new look now (keeps merging on if it was on).</summary>
        public void Reroll()
        {
            bool wasMerged = Merged || merge;
            if (combined != null)
            {
                combined.gameObject.SetActive(false);
                Destroy(combined.gameObject);
                combined = null;
            }
            foreach (var r in sources) if (r != null) r.enabled = true;
            sources.Clear();
            Randomize(0);
            if (wasMerged) SetMerged(true);
        }

        Transform[] all;
        Transform Find(string n) => Array.Find(all, t => t != null && t.name == n);

        void Randomize(int fixedSeed)
        {
            Seed = fixedSeed != 0 ? fixedSeed : UnityEngine.Random.Range(1, int.MaxValue);
            var rng = new System.Random(Seed);
            all = GetComponentsInChildren<Transform>(true);
            var picked = new List<string>();

            foreach (var o in optional)
            {
                var t = Find(o.part);
                if (t == null) continue;
                bool on = rng.NextDouble() < o.chance;
                t.gameObject.SetActive(on);
                if (on) picked.Add(o.part.Replace("Outfit_", ""));
            }

            // slots: clear the editor-time props on every slot socket, then fill
            foreach (var s in slots.SelectMany(s => s.sockets).Distinct())
            {
                var sock = Find(s);
                if (sock == null) continue;
                foreach (Transform c in sock.Cast<Transform>().ToArray())
                    if (c.name.StartsWith("Prop_"))
                    {
                        c.gameObject.SetActive(false);
                        Destroy(c.gameObject);
                    }
            }
            foreach (var slot in slots)
            {
                var opt = Pick(slot.options, rng);
                if (opt == null || opt.prop == null || slot.sockets.Length == 0) continue;
                var order = slot.sockets.OrderBy(_ => rng.Next()).ToArray();
                var sock = order.Select(Find).FirstOrDefault(t => t != null &&
                    !t.Cast<Transform>().Any(c => c.gameObject.activeSelf && c.name.StartsWith("Prop_")));
                if (sock == null) continue;
                var p = Instantiate(opt.prop, sock);
                p.name = opt.prop.name;
                p.transform.SetLocalPositionAndRotation(Vector3.zero, Quaternion.identity);
                p.transform.localScale = Vector3.one;
                picked.Add(p.name.Replace("Prop_", "") + "@" + sock.name.Replace("Socket_", ""));
            }

            // body shapes on every skinned part that has them
            var smrs = GetComponentsInChildren<SkinnedMeshRenderer>(true).Where(s => s.sharedMesh != null && s != combined).ToArray();
            foreach (var smr in smrs)
                for (int i = 0; i < smr.sharedMesh.blendShapeCount; i++) smr.SetBlendShapeWeight(i, 0);
            var weights = new Dictionary<string, float>();
            var groups = new HashSet<string>();
            foreach (var sh in shapes)
            {
                bool roll = rng.NextDouble() < sh.chance;
                float w = Mathf.Round(Mathf.Lerp(sh.weight.x, sh.weight.y, (float)rng.NextDouble()) * 4f) / 4f;
                if (!roll || w <= 0 || (!string.IsNullOrEmpty(sh.group) && groups.Contains(sh.group))) continue;
                if (!string.IsNullOrEmpty(sh.group)) groups.Add(sh.group);
                weights[sh.name] = w;
                foreach (var smr in smrs)
                {
                    int idx = smr.sharedMesh.GetBlendShapeIndex(sh.name);
                    if (idx >= 0) smr.SetBlendShapeWeight(idx, w * 100f);
                }
                picked.Add(sh.name + (w < 1 ? w.ToString("0.##") : ""));
            }
            foreach (var push in pushes)
            {
                if (!weights.TryGetValue(push.shape, out var w)) continue;
                var sock = Find(push.socket);
                if (sock == null) continue;
                foreach (Transform c in sock)
                    if (c.gameObject.activeSelf && c.name.StartsWith("Prop_"))
                        c.localPosition += Vector3.forward * push.metres * w;
            }

            if (skins.Length > 0)
            {
                var body = Find("GoblinBody");
                var smr = body != null ? body.GetComponent<SkinnedMeshRenderer>() : null;
                if (smr != null)
                {
                    var mats = smr.sharedMaterials;
                    mats[0] = skins[rng.Next(skins.Length)];
                    smr.sharedMaterials = mats;
                    picked.Add(mats[0].name.Replace("M_Goblin_", ""));
                }
            }
            transform.localScale = Vector3.one * Mathf.Lerp(scale.x, scale.y, (float)rng.NextDouble());
            Summary = string.Join(" ", picked);
        }

        static Option Pick(Option[] options, System.Random rng)
        {
            float total = options.Sum(o => o.weight);
            if (total <= 0) return null;
            double r = rng.NextDouble() * total;
            foreach (var o in options)
            {
                r -= o.weight;
                if (r <= 0) return o;
            }
            return options[options.Length - 1];
        }

        /// <summary>Switch between the merged mesh and the separate parts (builds the merged mesh on first use).</summary>
        public void SetMerged(bool on)
        {
            if (on && combined == null) Combine();
            if (combined == null) return;
            combined.enabled = on;
            foreach (var r in sources) if (r != null) r.enabled = !on;
            // the Animator culls by the renderers it saw when it bound; let it see the current ones,
            // or it treats the goblin as off-screen and stops animating
            if (TryGetComponent<Animator>(out var anim)) anim.Rebind();
        }

        void Combine()
        {
            sources.Clear();
            foreach (var r in GetComponentsInChildren<Renderer>(false))
            {
                if (IsFx(r.transform)) continue;                 // spell glows and the like stay separate
                if (r is SkinnedMeshRenderer s && s.sharedMesh != null) sources.Add(s);
                else if (r is MeshRenderer && r.TryGetComponent<MeshFilter>(out var mf) && mf.sharedMesh != null) sources.Add(r);
            }
            if (sources.Count == 0) return;

            var go = new GameObject("GoblinMerged");
            go.transform.SetParent(transform, false);
            combined = go.AddComponent<SkinnedMeshRenderer>();
            var C = go.transform;

            // bones: every skinned bone, plus each prop's own transform (rigid)
            var bones = new List<Transform>();
            var bind = new List<Matrix4x4>();
            var index = new Dictionary<Transform, int>();
            int Bone(Transform t, Matrix4x4 bp)
            {
                if (!index.TryGetValue(t, out var i))
                {
                    i = bones.Count;
                    bones.Add(t);
                    bind.Add(bp);
                    index[t] = i;
                }
                return i;
            }
            var remaps = new List<int[]>();
            foreach (var r in sources)
            {
                if (r is SkinnedMeshRenderer s)
                {
                    var Minv = (C.worldToLocalMatrix * s.transform.localToWorldMatrix).inverse;
                    var bps = s.sharedMesh.bindposes;
                    var map = new int[s.bones.Length];
                    for (int i = 0; i < map.Length; i++) map[i] = Bone(s.bones[i], bps[i] * Minv);
                    remaps.Add(map);
                }
                else
                    remaps.Add(new[] { Bone(r.transform, r.transform.worldToLocalMatrix * C.localToWorldMatrix) });
            }

            var materials = new List<Material>();
            foreach (var r in sources)
                foreach (var m in r.sharedMaterials)
                    if (!materials.Contains(m)) materials.Add(m);

            string key = string.Join("|", sources.Select(r =>
            {
                var p = r.transform.parent;
                var shapes = r is SkinnedMeshRenderer s && s.sharedMesh.blendShapeCount > 0
                    ? string.Join(",", Enumerable.Range(0, s.sharedMesh.blendShapeCount).Select(i => s.GetBlendShapeWeight(i).ToString("0")))
                    : "";
                var lp = r.transform.parent != null ? r.transform.parent.localPosition : Vector3.zero;
                return $"{r.name}@{(p ? p.name : "")}@{(p && p.parent ? p.parent.name : "")}[{shapes}]{lp.z:0.000}:" +
                       string.Join(",", r.sharedMaterials.Select(m => m ? m.name : "-"));
            }));
            if (!cache.TryGetValue(key, out var mesh) || mesh == null)
            {
                mesh = Build(C, bind, remaps, materials);
                mesh.name = name + "_Merged";
                cache[key] = mesh;
            }

            var body = sources.OfType<SkinnedMeshRenderer>().FirstOrDefault(s => s.name == "GoblinBody") ?? sources.OfType<SkinnedMeshRenderer>().FirstOrDefault();
            combined.bones = bones.ToArray();
            combined.rootBone = body != null ? body.rootBone : transform;
            combined.sharedMesh = mesh;
            combined.sharedMaterials = materials.ToArray();
            combined.quality = SkinQuality.Bone4;
            if (body != null) combined.shadowCastingMode = body.shadowCastingMode;
            // culling bounds live in the root bone's space; pad them for limbs and weapons in motion
            var toRoot = combined.rootBone.worldToLocalMatrix * C.localToWorldMatrix;
            var mb = mesh.bounds;
            var lb = new Bounds(toRoot.MultiplyPoint3x4(mb.center), Vector3.zero);
            for (int i = 0; i < 8; i++)
                lb.Encapsulate(toRoot.MultiplyPoint3x4(mb.center + Vector3.Scale(mb.extents,
                    new Vector3((i & 1) == 0 ? -1 : 1, (i & 2) == 0 ? -1 : 1, (i & 4) == 0 ? -1 : 1))));
            lb.Expand(0.8f);
            combined.localBounds = lb;
        }

        bool IsFx(Transform t)
        {
            for (; t != null && t != transform; t = t.parent)
                if (t.name.StartsWith("FX_")) return true;
            return false;
        }

        Mesh Build(Transform C, List<Matrix4x4> bind, List<int[]> remaps, List<Material> materials)
        {
            var verts = new List<Vector3>();
            var norms = new List<Vector3>();
            var uvs = new List<Vector2>();
            var weights = new List<BoneWeight>();
            var tris = materials.Select(_ => new List<int>()).ToArray();
            for (int si = 0; si < sources.Count; si++)
            {
                var r = sources[si];
                var map = remaps[si];
                var smr = r as SkinnedMeshRenderer;
                Mesh m = smr != null ? smr.sharedMesh : r.GetComponent<MeshFilter>().sharedMesh;
                var M = C.worldToLocalMatrix * r.transform.localToWorldMatrix;
                int baseV = verts.Count;
                var mv = m.vertices;
                var mn = m.normals;
                var mu = m.uv;
                if (smr != null && m.blendShapeCount > 0)        // bake the chosen body shape
                {
                    var dv = new Vector3[m.vertexCount];
                    var dn = new Vector3[m.vertexCount];
                    var dt = new Vector3[m.vertexCount];
                    for (int b = 0; b < m.blendShapeCount; b++)
                    {
                        float w = smr.GetBlendShapeWeight(b);
                        if (w <= 0) continue;
                        int f = m.GetBlendShapeFrameCount(b) - 1;
                        float k = w / Mathf.Max(m.GetBlendShapeFrameWeight(b, f), 1e-4f);
                        m.GetBlendShapeFrameVertices(b, f, dv, dn, dt);
                        for (int i = 0; i < mv.Length; i++)
                        {
                            mv[i] += dv[i] * k;
                            if (mn.Length > 0) mn[i] += dn[i] * k;
                        }
                    }
                }
                for (int i = 0; i < mv.Length; i++)
                {
                    verts.Add(M.MultiplyPoint3x4(mv[i]));
                    norms.Add(mn.Length > 0 ? M.MultiplyVector(mn[i]).normalized : Vector3.up);
                    uvs.Add(mu.Length > 0 ? mu[i] : Vector2.zero);
                }
                if (smr != null)
                {
                    foreach (var w in m.boneWeights)
                        weights.Add(new BoneWeight
                        {
                            boneIndex0 = map[w.boneIndex0], weight0 = w.weight0,
                            boneIndex1 = map[w.boneIndex1], weight1 = w.weight1,
                            boneIndex2 = map[w.boneIndex2], weight2 = w.weight2,
                            boneIndex3 = map[w.boneIndex3], weight3 = w.weight3,
                        });
                }
                else
                    for (int i = 0; i < mv.Length; i++) weights.Add(new BoneWeight { boneIndex0 = map[0], weight0 = 1f });
                var mats = r.sharedMaterials;
                for (int sub = 0; sub < m.subMeshCount; sub++)
                {
                    var mat = mats[Mathf.Min(sub, mats.Length - 1)];
                    var list = tris[materials.IndexOf(mat)];
                    foreach (var t in m.GetTriangles(sub)) list.Add(baseV + t);
                }
            }
            var mesh = new Mesh();
            if (verts.Count > 65535) mesh.indexFormat = UnityEngine.Rendering.IndexFormat.UInt32;
            mesh.SetVertices(verts);
            mesh.SetNormals(norms);
            mesh.SetUVs(0, uvs);
            mesh.boneWeights = weights.ToArray();
            mesh.bindposes = bind.ToArray();
            mesh.subMeshCount = materials.Count;
            for (int i = 0; i < materials.Count; i++) mesh.SetTriangles(tris[i], i);
            mesh.RecalculateBounds();
            return mesh;
        }
    }
}
