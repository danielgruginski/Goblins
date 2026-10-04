using System;
using UnityEngine;

namespace Goblins
{
    /// <summary>
    /// The shaman's magic: a glow on the staff head (Prop_ShamanStaff in Socket_RightHand) that swells while a spell
    /// is gathered, and the spells themselves at the moment the clip casts them:
    ///   Hex    (Shaman_Hex)    a bolt from the staff head toward the goblin's forward. The attack.
    ///   Chant  (Shaman_Chant)  a ring spreading over the ground from where the staff strikes. The support spell
    ///                          (heal or bolster the goblins inside <see cref="ringRadius"/>).
    /// Timing is in seconds into each clip (the frames of gob_anim.EVENTS at 30 fps). <see cref="Cast"/> fires at
    /// every cast with the spell name, origin and direction; hook damage, healing and sound there.
    /// Reads the clip from the goblin's <see cref="IGoblinAnimSource"/> (GoblinRandomAnimator, or a game's driver), or
    /// from an Animator Controller's layer 0; or call <see cref="Apply"/> yourself.
    /// </summary>
    [DefaultExecutionOrder(200)]        // after the animation and GoblinPosture
    public class GoblinShaman : MonoBehaviour
    {
        [Serializable]
        public class Timing
        {
            public string clip;
            public string spell;
            [Tooltip("Seconds into the clip: the glow starts to gather.")]
            public float charge = -1;
            [Tooltip("Seconds into the clip: the spell goes off.")]
            public float cast = -1;
        }

        public Timing[] timings =
        {
            new Timing { clip = "Shaman_Hex", spell = "Hex", charge = 6 / 30f, cast = 22 / 30f },
            new Timing { clip = "Shaman_Chant", spell = "Chant", charge = 16 / 30f, cast = 52 / 30f },
        };

        [Header("Staff (Socket_RightHand space)")]
        public Vector3 staffOrb = new Vector3(0f, 0.565f, 0f);
        public Vector3 staffFoot = new Vector3(0f, -0.62f, 0f);
        [Tooltip("Additive material with a soft round texture (GoblinSetup makes M_Goblin_Magic).")]
        public Material magicMaterial;
        public Color magic = new Color(0.45f, 1f, 0.28f, 1f);
        public float orbSize = 0.1f;
        public bool orbLight = true;

        [Header("Hex")]
        public float boltSpeed = 9f;
        public float boltRange = 12f;
        public float boltSize = 0.17f;

        [Header("Chant")]
        public float ringRadius = 2.5f;
        public float ringSeconds = 0.9f;

        /// <summary>Fired when a spell goes off: (shaman, spell, origin, direction).</summary>
        public event Action<GoblinShaman, string, Vector3, Vector3> Cast;

        /// <summary>0..1 while a spell is being gathered.</summary>
        public float Charge { get; private set; }

        Transform right, orb;
        MeshRenderer core, halo;
        Light glowLight;
        MaterialPropertyBlock mpb;
        IGoblinAnimSource driver;
        Animator anim;
        string lastClip = "";
        float lastT = -1f, flare, seed;

        void Start()        // after GoblinAppearance merged the goblin in Awake, so the glow stays a separate renderer
        {
            foreach (var t in GetComponentsInChildren<Transform>(true))
                if (t.name == "Socket_RightHand") right = t;
            TryGetComponent(out driver);
            anim = GetComponent<Animator>();
            mpb = new MaterialPropertyBlock();
            seed = UnityEngine.Random.value * 10f;
            if (right == null) return;
            var mat = Material;
            orb = new GameObject("FX_StaffOrb").transform;
            orb.SetParent(right, false);
            orb.localPosition = staffOrb;
            halo = GoblinFx.Quad("FX_Halo", orb, mat);
            core = GoblinFx.Quad("FX_Core", orb, mat);
            if (orbLight)
            {
                glowLight = orb.gameObject.AddComponent<Light>();
                glowLight.type = LightType.Point;
                glowLight.color = magic;
                glowLight.range = 1.2f;
                glowLight.shadows = LightShadows.None;
            }
        }

        Material Material => magicMaterial != null ? magicMaterial : GoblinFx.Fallback;

        void ReadClip(out string clip, out float t)
        {
            clip = "";
            t = 0;
            if (driver == null) TryGetComponent(out driver);
            if (driver != null && (!(driver is Behaviour b) || b.enabled))
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

        void LateUpdate()
        {
            ReadClip(out var clip, out var t);
            Apply(clip, t, Time.deltaTime);
        }

        /// <summary>Glow and spells for <paramref name="clip"/> at <paramref name="t"/> seconds on the current pose.</summary>
        public void Apply(string clip, float t, float dt)
        {
            if (orb == null) return;
            Timing tm = null;
            foreach (var x in timings)
                if (x.clip == clip) tm = x;
            float charge = 0f;
            if (tm != null)
            {
                if (tm.charge >= 0 && t >= tm.charge && t < tm.cast) charge = Mathf.InverseLerp(tm.charge, tm.cast, t);
                if (clip == lastClip && tm.cast >= 0 && lastT < tm.cast && t >= tm.cast) DoCast(tm);
            }
            lastClip = clip;
            lastT = t;
            flare = Mathf.MoveTowards(flare, 0f, dt / 0.5f);
            Charge = charge;

            float pulse = 0.5f + 0.5f * Mathf.Sin(Time.time * 3.1f + seed);
            float glow = 0.5f + 0.15f * pulse + 0.9f * charge + 1.1f * flare;
            core.transform.localScale = Vector3.one * orbSize * (0.8f + 0.3f * glow);
            halo.transform.localScale = Vector3.one * orbSize * (2.2f + 1.4f * glow);
            GoblinFx.Tint(core, mpb, Color.Lerp(magic, Color.white, 0.55f));
            GoblinFx.Tint(halo, mpb, new Color(magic.r, magic.g, magic.b, Mathf.Clamp01(0.35f * glow)));
            GoblinFx.Face(core.transform);
            GoblinFx.Face(halo.transform);
            if (glowLight != null) glowLight.intensity = 0.12f + 0.6f * (charge + flare);      // a hint of green on him and his neighbours
        }

        void DoCast(Timing tm)
        {
            flare = 1f;
            float s = transform.lossyScale.x;
            var origin = orb.position;
            var dir = transform.forward;
            if (tm.spell == "Hex")
                GoblinFxBolt.Fire(Material, magic, origin, dir, boltSpeed, boltRange, boltSize * s);
            else
                GoblinFxRing.Spawn(Material, magic, transform.position, ringRadius, ringSeconds, right.TransformPoint(staffFoot), 0.55f * s);
            Cast?.Invoke(this, tm.spell, origin, dir);
        }
    }
}
