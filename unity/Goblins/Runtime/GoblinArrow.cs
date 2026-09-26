using System.Collections.Generic;
using UnityEngine;

namespace Goblins
{
    /// <summary>
    /// A loosed arrow: flies ballistically, turns along its velocity, sticks into the first collider its tip meets
    /// (the ground), and goes back to a pool after a while. The model is Prop_Arrow: nock at the origin, shaft
    /// along local -X (Blender +X, mirrored by the FBX import), tip 0.5 m out.
    /// </summary>
    public class GoblinArrow : MonoBehaviour
    {
        public float gravity = 9.81f;
        public float stuckSeconds = 4f;
        public float maxFlightSeconds = 6f;
        const float Length = 0.5f, Bury = 0.09f;

        Vector3 velocity;
        float timer, scale = 1f;
        bool stuck;
        GoblinArrow source;
        static readonly Dictionary<GoblinArrow, Stack<GoblinArrow>> pools = new Dictionary<GoblinArrow, Stack<GoblinArrow>>();

        public static GoblinArrow Fire(GoblinArrow prefab, Vector3 nock, Vector3 velocity, float scale = 1f)
        {
            if (!pools.TryGetValue(prefab, out var pool)) pools[prefab] = pool = new Stack<GoblinArrow>();
            GoblinArrow a = null;
            while (a == null && pool.Count > 0) a = pool.Pop();
            if (a == null) a = Instantiate(prefab);
            a.source = prefab;
            a.velocity = velocity;
            a.scale = scale;
            a.timer = 0;
            a.stuck = false;
            a.transform.localScale = Vector3.one * scale;
            a.transform.SetPositionAndRotation(nock, ShaftRotation(velocity, Vector3.up));
            a.gameObject.SetActive(true);
            return a;
        }

        /// <summary>Rotation that lays the arrow model's shaft (local -X) along dir with its local +Y toward up.</summary>
        public static Quaternion ShaftRotation(Vector3 dir, Vector3 up)
        {
            dir.Normalize();
            var u = Vector3.ProjectOnPlane(up, dir);
            if (u.sqrMagnitude < 1e-6f) u = Vector3.ProjectOnPlane(Vector3.forward, dir);
            u.Normalize();
            return Quaternion.LookRotation(Vector3.Cross(-dir, u), u);
        }

        void Update()
        {
            float dt = Time.deltaTime;
            timer += dt;
            if (stuck)
            {
                if (timer > stuckSeconds) Recycle();
                return;
            }
            if (timer > maxFlightSeconds || transform.position.y < -20f)
            {
                Recycle();
                return;
            }
            velocity += Vector3.down * (gravity * dt);
            var dir = velocity.normalized;
            var step = velocity * dt;
            var tip = transform.position + dir * (Length * scale);
            if (Physics.Raycast(tip, dir, out var hit, step.magnitude, ~0, QueryTriggerInteraction.Ignore))
            {
                transform.position = hit.point - dir * ((Length - Bury) * scale);
                stuck = true;
                timer = 0;
                return;
            }
            transform.SetPositionAndRotation(transform.position + step, ShaftRotation(dir, Vector3.up));
        }

        void Recycle()
        {
            gameObject.SetActive(false);
            if (source != null && pools.TryGetValue(source, out var pool)) pool.Push(this);
            else Destroy(gameObject);
        }
    }
}
