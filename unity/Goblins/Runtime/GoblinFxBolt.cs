using System.Collections.Generic;
using UnityEngine;

namespace Goblins
{
    /// <summary>
    /// Hex bolt: a glowing ball trailing light, flying straight and wobbling a little. It bursts on the first
    /// collider it meets or when it runs out of range, then goes back to a pool.
    /// </summary>
    public class GoblinFxBolt : MonoBehaviour
    {
        Vector3 dir, side;
        float speed, range, travelled, size, burst = -1f, age;
        Color color;
        MeshRenderer ball;
        TrailRenderer trail;
        MaterialPropertyBlock mpb;
        static readonly Stack<GoblinFxBolt> pool = new Stack<GoblinFxBolt>();

        public static GoblinFxBolt Fire(Material mat, Color color, Vector3 from, Vector3 dir, float speed, float range, float size)
        {
            GoblinFxBolt b = null;
            while (b == null && pool.Count > 0) b = pool.Pop();
            if (b == null)
            {
                b = new GameObject("FX_HexBolt").AddComponent<GoblinFxBolt>();
                b.Build(mat);
            }
            b.dir = dir.normalized;
            b.side = Vector3.Cross(b.dir, Vector3.up).sqrMagnitude > 1e-4f ? Vector3.Cross(b.dir, Vector3.up).normalized : Vector3.right;
            b.speed = speed;
            b.range = range;
            b.size = size;
            b.color = color;
            b.travelled = 0;
            b.age = 0;
            b.burst = -1;
            b.transform.position = from;
            b.gameObject.SetActive(true);
            b.trail.Clear();
            b.trail.emitting = true;
            b.trail.widthMultiplier = size * 0.7f;
            b.trail.startColor = color;
            b.trail.endColor = new Color(color.r, color.g, color.b, 0f);
            return b;
        }

        void Build(Material mat)
        {
            mpb = new MaterialPropertyBlock();
            ball = GoblinFx.Quad("FX_Ball", transform, mat);
            trail = gameObject.AddComponent<TrailRenderer>();
            trail.sharedMaterial = mat;
            trail.time = 0.3f;
            trail.minVertexDistance = 0.04f;
            trail.widthCurve = AnimationCurve.Linear(0, 1, 1, 0);
            trail.alignment = LineAlignment.View;
            trail.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            trail.receiveShadows = false;
        }

        void Update()
        {
            float dt = Time.deltaTime;
            age += dt;
            if (burst >= 0)
            {
                burst += dt / 0.3f;
                ball.transform.localScale = Vector3.one * size * (1f + 3.5f * burst);
                GoblinFx.Tint(ball, mpb, color * Mathf.Clamp01(1f - burst));
                if (burst >= 1f) Recycle();
                return;
            }
            var step = dir * (speed * dt);
            if (Physics.Raycast(transform.position, dir, out var hit, step.magnitude, ~0, QueryTriggerInteraction.Ignore))
            {
                transform.position = hit.point;
                Burst();
                return;
            }
            transform.position += step;
            travelled += step.magnitude;
            ball.transform.localPosition = side * (Mathf.Sin(age * 23f) * 0.025f) + Vector3.up * (Mathf.Cos(age * 17f) * 0.02f);
            ball.transform.localScale = Vector3.one * size * (1f + 0.18f * Mathf.Sin(age * 40f));
            GoblinFx.Tint(ball, mpb, Color.Lerp(color, Color.white, 0.35f));
            if (travelled >= range) Burst();
        }

        void LateUpdate() => GoblinFx.Face(ball.transform);

        void Burst()
        {
            burst = 0;
            trail.emitting = false;
            ball.transform.localPosition = Vector3.zero;
        }

        void Recycle()
        {
            gameObject.SetActive(false);
            pool.Push(this);
        }
    }
}
