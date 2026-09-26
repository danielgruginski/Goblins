using System.Collections.Generic;
using UnityEngine;

namespace Goblins
{
    /// <summary>
    /// Chant pulse: a glowing ring spreading over the ground and fading, with a flash where the staff struck.
    /// Pooled.
    /// </summary>
    public class GoblinFxRing : MonoBehaviour
    {
        float t, seconds, radius, flashSize;
        Color color;
        MeshRenderer ring, flash;
        MaterialPropertyBlock mpb;
        static readonly Stack<GoblinFxRing> pool = new Stack<GoblinFxRing>();

        public static GoblinFxRing Spawn(Material mat, Color color, Vector3 ground, float radius, float seconds, Vector3 strike,
                                         float flashSize = 0.5f)
        {
            GoblinFxRing r = null;
            while (r == null && pool.Count > 0) r = pool.Pop();
            if (r == null)
            {
                r = new GameObject("FX_ChantRing").AddComponent<GoblinFxRing>();
                r.Build(mat);
            }
            r.transform.position = ground + Vector3.up * 0.03f;
            r.flash.transform.position = strike + Vector3.up * 0.05f;
            r.color = color;
            r.radius = radius;
            r.seconds = seconds;
            r.flashSize = flashSize;
            r.t = 0;
            r.gameObject.SetActive(true);
            r.Update();
            return r;
        }

        void Build(Material mat)
        {
            mpb = new MaterialPropertyBlock();
            var go = new GameObject("FX_Ring");
            go.transform.SetParent(transform, false);
            go.AddComponent<MeshFilter>().sharedMesh = GoblinFx.RingMesh();
            ring = go.AddComponent<MeshRenderer>();
            ring.sharedMaterial = mat;
            ring.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            ring.receiveShadows = false;
            flash = GoblinFx.Quad("FX_Flash", transform, mat);
        }

        void Update()
        {
            t += Time.deltaTime / Mathf.Max(seconds, 0.01f);
            if (t >= 1f)
            {
                gameObject.SetActive(false);
                pool.Push(this);
                return;
            }
            float k = 1f - (1f - t) * (1f - t);                          // fast out, slowing down
            ring.transform.localScale = Vector3.one * Mathf.Lerp(0.25f, radius, k);
            GoblinFx.Tint(ring, mpb, color * Mathf.Pow(1f - t, 1.5f));
            flash.transform.localScale = Vector3.one * flashSize * (1f + 2f * t);
            GoblinFx.Tint(flash, mpb, Color.Lerp(color, Color.white, 0.4f) * Mathf.Clamp01(1f - t * 2.2f));
        }

        void LateUpdate() => GoblinFx.Face(flash.transform);
    }
}
