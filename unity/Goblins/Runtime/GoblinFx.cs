using UnityEngine;
using UnityEngine.Rendering;

namespace Goblins
{
    /// <summary>
    /// Shared pieces for the goblins' spell effects: a soft round glow texture, an additive material, camera-facing
    /// quads and a flat ring mesh. Effect objects are named FX_* so GoblinAppearance leaves them out of the merged mesh.
    /// </summary>
    public static class GoblinFx
    {
        /// <summary>Camera the glow quads turn to; null = Camera.main.</summary>
        public static Camera FaceCamera;

        static Texture2D glow;
        static Material fallback;
        static Mesh quad, ring;

        /// <summary>White, alpha falling off from the centre: a bright core inside a soft halo.</summary>
        public static Texture2D GlowTexture(int size = 64)
        {
            if (glow != null) return glow;
            glow = new Texture2D(size, size, TextureFormat.RGBA32, true) { name = "GoblinGlow", wrapMode = TextureWrapMode.Clamp };
            var px = new Color32[size * size];
            for (int y = 0; y < size; y++)
                for (int x = 0; x < size; x++)
                {
                    float dx = (x + 0.5f) / size * 2f - 1f, dy = (y + 0.5f) / size * 2f - 1f;
                    float d = Mathf.Sqrt(dx * dx + dy * dy);
                    float a = Mathf.Pow(Mathf.Clamp01(1f - d), 2.2f) + 0.6f * Mathf.Pow(Mathf.Clamp01(1f - d * 2.4f), 2f);
                    px[y * size + x] = new Color32(255, 255, 255, (byte)(Mathf.Clamp01(a) * 255));
                }
            glow.SetPixels32(px);
            glow.Apply(true);
            return glow;
        }

        /// <summary>URP Particles/Unlit, additive, two-sided, no depth write; tint through _BaseColor or vertex colour.</summary>
        public static Material AdditiveMaterial(Texture tex)
        {
            var sh = Shader.Find("Universal Render Pipeline/Particles/Unlit") ?? Shader.Find("Sprites/Default");
            var m = new Material(sh) { name = "GoblinMagic" };
            m.SetFloat("_Surface", 1f);
            m.SetFloat("_Blend", 2f);                                   // additive
            m.SetFloat("_SrcBlend", (float)BlendMode.SrcAlpha);
            m.SetFloat("_DstBlend", (float)BlendMode.One);
            m.SetFloat("_SrcBlendAlpha", (float)BlendMode.One);
            m.SetFloat("_DstBlendAlpha", (float)BlendMode.One);
            m.SetFloat("_ZWrite", 0f);
            m.SetFloat("_Cull", 0f);
            m.SetOverrideTag("RenderType", "Transparent");
            m.EnableKeyword("_SURFACE_TYPE_TRANSPARENT");
            m.renderQueue = (int)RenderQueue.Transparent;
            m.SetTexture("_BaseMap", tex);
            m.mainTexture = tex;
            m.SetColor("_BaseColor", Color.white);
            return m;
        }

        public static Material Fallback => fallback != null ? fallback : fallback = AdditiveMaterial(GlowTexture());

        public static void Face(Transform t)
        {
            var cam = FaceCamera != null ? FaceCamera : Camera.main;
            if (cam != null && t != null) t.rotation = cam.transform.rotation;
        }

        public static MeshRenderer Quad(string name, Transform parent, Material mat)
        {
            var go = new GameObject(name);
            go.transform.SetParent(parent, false);
            go.AddComponent<MeshFilter>().sharedMesh = QuadMesh();
            var mr = go.AddComponent<MeshRenderer>();
            mr.sharedMaterial = mat;
            mr.shadowCastingMode = ShadowCastingMode.Off;
            mr.receiveShadows = false;
            mr.lightProbeUsage = LightProbeUsage.Off;
            return mr;
        }

        public static void Tint(Renderer r, MaterialPropertyBlock mpb, Color c)
        {
            mpb.SetColor("_BaseColor", c);
            r.SetPropertyBlock(mpb);
        }

        public static Mesh QuadMesh()
        {
            if (quad != null) return quad;
            quad = new Mesh { name = "FX_Quad" };
            quad.vertices = new[] { new Vector3(-0.5f, -0.5f, 0), new Vector3(0.5f, -0.5f, 0), new Vector3(0.5f, 0.5f, 0), new Vector3(-0.5f, 0.5f, 0) };
            quad.uv = new[] { new Vector2(0, 0), new Vector2(1, 0), new Vector2(1, 1), new Vector2(0, 1) };
            quad.triangles = new[] { 0, 2, 1, 0, 3, 2 };
            quad.RecalculateNormals();
            quad.RecalculateBounds();
            return quad;
        }

        /// <summary>Flat ring of radius 1 in the XZ plane; v runs across the band so the glow texture makes it soft.</summary>
        public static Mesh RingMesh(int seg = 48, float inner = 0.8f)
        {
            if (ring != null) return ring;
            ring = new Mesh { name = "FX_Ring" };
            var v = new Vector3[seg * 2];
            var uv = new Vector2[seg * 2];
            var tri = new int[seg * 6];
            for (int i = 0; i < seg; i++)
            {
                float a = i * Mathf.PI * 2f / seg;
                var d = new Vector3(Mathf.Cos(a), 0, Mathf.Sin(a));
                v[i * 2] = d * inner;
                v[i * 2 + 1] = d;
                uv[i * 2] = new Vector2(0.5f, 0f);
                uv[i * 2 + 1] = new Vector2(0.5f, 1f);
                int j = (i + 1) % seg;
                int t = i * 6;
                tri[t] = i * 2; tri[t + 1] = j * 2; tri[t + 2] = i * 2 + 1;
                tri[t + 3] = i * 2 + 1; tri[t + 4] = j * 2; tri[t + 5] = j * 2 + 1;
            }
            ring.vertices = v;
            ring.uv = uv;
            ring.triangles = tri;
            ring.RecalculateNormals();
            ring.RecalculateBounds();
            return ring;
        }
    }
}
