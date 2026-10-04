using System;
using UnityEngine;

namespace Goblins
{
    /// <summary>
    /// Bow string and arrow for the goblin archer (Prop_Shortbow in Socket_LeftHand, Prop_Arrow in Socket_RightHand).
    ///
    /// The string is a three-point line between the bow tips. While an arrow is nocked, the string's middle rides in
    /// the drawing fingers and the arrow is laid from the fingers through the arrow rest on the bow, so it lines up
    /// whatever the retargeting does to the hands. Timing comes from the clip that is playing: Bow_Shoot and
    /// Bow_Volley loose at <see cref="Timing.release"/>, a fresh arrow is in the hand at <see cref="Timing.arrow"/>
    /// and back on the string at <see cref="Timing.nock"/> (seconds; the frames of gob_anim.EVENTS at 30 fps).
    /// Other clips (walking, idles, hurt) carry the bow with no arrow out.
    ///
    /// Reads the clip from the goblin's <see cref="IGoblinAnimSource"/> (GoblinRandomAnimator, or a game's driver), or
    /// from an Animator Controller's layer 0.
    /// <see cref="Loosed"/> fires at every loose (spawn damage, sound or your own projectile there);
    /// <see cref="projectile"/>, when set, also flies a GoblinArrow.
    /// </summary>
    [DefaultExecutionOrder(200)]        // after the animation and GoblinPosture
    public class GoblinArcher : MonoBehaviour
    {
        [Serializable]
        public class Timing
        {
            public string clip;
            [Tooltip("Seconds into the clip. Negative = the arrow stays nocked for the whole clip (Bow_Ready).")]
            public float release = -1, arrow = -1, nock = -1;
        }

        public Timing[] timings =
        {
            new Timing { clip = "Bow_Ready" },
            new Timing { clip = "Bow_Shoot", release = 33 / 30f, arrow = 62 / 30f, nock = 72 / 30f },
            new Timing { clip = "Bow_Volley", release = 35 / 30f, arrow = 64 / 30f, nock = 74 / 30f },
        };

        [Header("Bow (Socket_LeftHand space)")]
        public Vector3 stringTop = new Vector3(-0.092f, 0.36f, 0f);
        public Vector3 stringBottom = new Vector3(-0.092f, -0.36f, 0f);
        [Tooltip("Where the nocked shaft crosses the bow (gob_gear.ARROW_REST with X mirrored).")]
        public Vector3 arrowRest = new Vector3(0f, 0.04f, 0.021f);
        public float stringWidth = 0.004f;
        public Material stringMaterial;

        [Header("Loose")]
        public GoblinArrow projectile;
        public float arrowSpeed = 18f;

        /// <summary>Fired at the loose: (archer, nock position, velocity).</summary>
        public event Action<GoblinArcher, Vector3, Vector3> Loosed;

        public bool Nocked => nockW > 0.5f;

        Transform left, right, arrow;
        LineRenderer line;
        IGoblinAnimSource driver;
        Animator anim;
        float nockW, lastT = -1;
        string lastClip = "";
        Vector3 lastNock, lastDir = Vector3.forward;

        void Awake()
        {
            foreach (var t in GetComponentsInChildren<Transform>(true))
            {
                if (t.name == "Socket_LeftHand") left = t;
                else if (t.name == "Socket_RightHand") right = t;
            }
            TryGetComponent(out driver);
            anim = GetComponent<Animator>();
            var go = new GameObject("BowString");
            go.transform.SetParent(transform, false);
            line = go.AddComponent<LineRenderer>();
            line.useWorldSpace = true;
            line.positionCount = 3;
            line.numCapVertices = 0;
            line.alignment = LineAlignment.View;
            line.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            line.receiveShadows = false;
            line.sharedMaterial = stringMaterial != null ? stringMaterial : DefaultStringMaterial();
        }

        static Material defaultMat;
        static Material DefaultStringMaterial()
        {
            if (defaultMat == null)
            {
                var sh = Shader.Find("Universal Render Pipeline/Unlit") ?? Shader.Find("Unlit/Color") ?? Shader.Find("Sprites/Default");
                defaultMat = new Material(sh) { name = "BowString (runtime)", color = new Color(0.78f, 0.72f, 0.58f) };
            }
            return defaultMat;
        }

        Transform FindArrow()
        {
            if (arrow != null && arrow.parent == right && arrow.gameObject.activeSelf) return arrow;
            arrow = null;
            if (right == null) return null;
            foreach (Transform c in right)
                if (c.gameObject.activeSelf && c.name.StartsWith("Prop_Arrow")) arrow = c;
            return arrow;
        }

        void ReadClip(out string clip, out float t)
        {
            clip = "";
            t = 0;
            if (driver == null) TryGetComponent(out driver);
            if (driver != null)
            {
                clip = driver.CurrentClip;
                t = driver.CurrentTime;
                return;
            }
            if (anim == null || anim.runtimeAnimatorController == null) return;
            var infos = anim.GetCurrentAnimatorClipInfo(0);
            if (infos.Length == 0) return;
            var c = infos[0].clip;
            float n = anim.GetCurrentAnimatorStateInfo(0).normalizedTime;
            clip = c.name;
            t = (c.isLooping ? Mathf.Repeat(n, 1f) : n) * c.length;
        }

        Timing Find(string clip)
        {
            foreach (var tm in timings)
                if (tm.clip == clip) return tm;
            return null;
        }

        void LateUpdate()
        {
            ReadClip(out var clip, out var t);
            Apply(clip, t, Time.deltaTime);
        }

        /// <summary>
        /// String and arrow for <paramref name="clip"/> at <paramref name="t"/> seconds, on the current skeleton pose.
        /// LateUpdate calls it with the playing clip; call it yourself after sampling a pose (dt = infinity snaps).
        /// </summary>
        public void Apply(string clip, float t, float dt)
        {
            if (left == null || right == null) return;
            var tm = Find(clip);
            bool nockedPhase = false, inHand = false;
            if (tm != null)
            {
                if (tm.release < 0 || t < tm.release || (tm.nock >= 0 && t >= tm.nock)) nockedPhase = true;
                else if (tm.arrow >= 0 && t >= tm.arrow) inHand = true;
                if (clip == lastClip && tm.release >= 0 && lastT < tm.release && t >= tm.release && nockW > 0.5f)
                    Loose();
            }
            lastClip = clip;
            lastT = t;
            nockW = nockedPhase ? Mathf.MoveTowards(nockW, 1f, dt / 0.15f) : 0f;

            var top = left.TransformPoint(stringTop);
            var bottom = left.TransformPoint(stringBottom);
            var mid = Vector3.Lerp((top + bottom) * 0.5f, right.position, nockW);
            line.SetPosition(0, top);
            line.SetPosition(1, mid);
            line.SetPosition(2, bottom);
            line.widthMultiplier = stringWidth * transform.lossyScale.x;

            var a = FindArrow();
            if (a == null) return;
            bool show = nockedPhase || inHand;
            a.localScale = show ? Vector3.one : Vector3.zero;       // scaled away, so it also vanishes from a merged mesh
            a.SetLocalPositionAndRotation(Vector3.zero, Quaternion.identity);
            if (!show || nockW <= 0) return;
            var dir = left.TransformPoint(arrowRest) - right.position;
            if (dir.sqrMagnitude < 1e-6f) return;
            dir.Normalize();
            a.rotation = Quaternion.Slerp(right.rotation, GoblinArrow.ShaftRotation(dir, left.up), nockW);
            lastNock = right.position;
            lastDir = dir;
        }

        void Loose()
        {
            var v = lastDir * arrowSpeed;
            if (projectile != null) GoblinArrow.Fire(projectile, lastNock, v, transform.lossyScale.x);
            Loosed?.Invoke(this, lastNock, v);
        }
    }
}
