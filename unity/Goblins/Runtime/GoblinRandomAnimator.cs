using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Animations;
using UnityEngine.Playables;

namespace Goblins
{
    /// <summary>
    /// Plays random clips from a <see cref="GoblinAnimationSet"/> through a small playable graph (two-slot
    /// crossfade, foot IK on). Root-motion pools move the goblin; it wanders and steers back toward
    /// <see cref="home"/> when it strays past <see cref="wanderRadius"/>, and keeps apart from other goblins.
    /// For looking at retargeted animation; a game would drive clips from its own state machine.
    /// </summary>
    [RequireComponent(typeof(Animator))]
    public class GoblinRandomAnimator : MonoBehaviour, IGoblinAnimSource
    {
        public GoblinAnimationSet set;
        public float crossfade = 0.25f;
        public Vector3 home;
        public float wanderRadius = 7f;
        public Vector2 speedRange = new Vector2(0.92f, 1.08f);

        public string CurrentClip { get; private set; } = "";
        /// <summary>0..1, follows the crossfade into and out of two-handed pools.</summary>
        public float TwoHandWeight { get; private set; }
        /// <summary>0..1, fades GoblinPosture's hunch out of pools marked upright.</summary>
        public float HunchWeight { get; private set; } = 1f;
        /// <summary>Seconds into the current clip (its own time, playback speed included).</summary>
        public float CurrentTime => cur.IsValid() ? (float)cur.GetTime() : 0f;
        public static readonly List<GoblinRandomAnimator> All = new List<GoblinRandomAnimator>();

        Animator anim;
        PlayableGraph graph;
        AnimationMixerPlayable mixer;
        AnimationClipPlayable cur, prev;
        float fade = 1, stepEnd, speed, seed;
        GoblinAnimationSet.Pool pool;
        int step;

        void OnEnable()
        {
            All.Add(this);
            anim = GetComponent<Animator>();
            anim.applyRootMotion = true;
            graph = PlayableGraph.Create(name + "_Random");
            graph.SetTimeUpdateMode(DirectorUpdateMode.GameTime);
            var output = AnimationPlayableOutput.Create(graph, "Animation", anim);
            mixer = AnimationMixerPlayable.Create(graph, 2);
            output.SetSourcePlayable(mixer);
            graph.Play();
            speed = Random.Range(speedRange.x, speedRange.y);
            seed = Random.value * 100f;
            if (set != null) Restart();
        }

        void OnDisable()
        {
            All.Remove(this);
            if (graph.IsValid()) graph.Destroy();
        }

        public void Restart() => StartPool(set.PickWeighted());

        void StartPool(GoblinAnimationSet.Pool p)
        {
            pool = p;
            step = 0;
            Play(p.sequence ? p.clips[0] : p.clips[Random.Range(0, p.clips.Length)]);
        }

        void Play(AnimationClip clip)
        {
            if (prev.IsValid())
            {
                graph.Disconnect(mixer, 1);
                prev.Destroy();
            }
            if (cur.IsValid())
            {
                graph.Disconnect(mixer, 0);
                graph.Connect(cur, 0, mixer, 1);
                prev = cur;
            }
            cur = AnimationClipPlayable.Create(graph, clip);
            cur.SetApplyFootIK(true);
            cur.SetSpeed(speed);
            graph.Connect(cur, 0, mixer, 0);
            fade = prev.IsValid() ? 0 : 1;
            mixer.SetInputWeight(0, fade);
            mixer.SetInputWeight(1, 1 - fade);
            CurrentClip = clip.name.Replace("HumanM@", "");
            float dur = clip.isLooping ? Random.Range(pool.hold.x, pool.hold.y)
                                       : clip.length / speed - crossfade * 0.5f + pool.holdAfter;
            stepEnd = Time.time + Mathf.Max(0.2f, dur);
        }

        void Update()
        {
            if (set == null || !graph.IsValid()) return;
            float want = pool != null && pool.twoHanded ? 1f : 0f;
            TwoHandWeight = Mathf.MoveTowards(TwoHandWeight, want, Time.deltaTime / Mathf.Max(crossfade, 0.01f));
            HunchWeight = Mathf.MoveTowards(HunchWeight, pool != null && pool.upright ? 0f : 1f, Time.deltaTime / Mathf.Max(crossfade, 0.01f));
            if (fade < 1)
            {
                fade = Mathf.Min(1, fade + Time.deltaTime / crossfade);
                mixer.SetInputWeight(0, fade);
                mixer.SetInputWeight(1, 1 - fade);
            }
            if (Time.time < stepEnd) return;
            if (pool.sequence && step + 1 < pool.clips.Length)
                Play(pool.clips[++step]);
            else
            {
                var next = string.IsNullOrEmpty(pool.next) ? null : set.Get(pool.next);
                StartPool(next != null && next.clips.Length > 0 ? next : set.PickWeighted());
            }
        }

        void OnAnimatorMove()
        {
            var dp = anim.deltaPosition;
            dp.y = 0;
            transform.position += dp;
            transform.rotation *= anim.deltaRotation;
            if (pool == null || !pool.moves) return;
            var toHome = home - transform.position;
            toHome.y = 0;
            float d = toHome.magnitude;
            float turn;
            if (d > wanderRadius * 0.6f)
            {
                var target = Quaternion.LookRotation(toHome.normalized, Vector3.up);
                float urgency = Mathf.InverseLerp(wanderRadius * 0.6f, wanderRadius, d);
                transform.rotation = Quaternion.RotateTowards(transform.rotation, target, (40f + 120f * urgency) * Time.deltaTime);
                return;
            }
            turn = (Mathf.PerlinNoise(Time.time * 0.3f, seed) * 2f - 1f) * 60f;     // lazy meander
            foreach (var o in All)                                                  // step around the others
            {
                if (o == this) continue;
                var away = transform.position - o.transform.position;
                away.y = 0;
                if (away.sqrMagnitude < 1.6f * 1.6f && Vector3.Dot(transform.forward, -away) > 0)
                    turn += Vector3.SignedAngle(transform.forward, away, Vector3.up) > 0 ? 90f : -90f;
            }
            transform.Rotate(0, turn * Time.deltaTime, 0);
        }

        void LateUpdate()
        {
            foreach (var o in All)                      // no standing inside each other
            {
                if (o == this) continue;
                var away = transform.position - o.transform.position;
                away.y = 0;
                float m = away.magnitude;
                if (m < 0.55f && m > 1e-4f) transform.position += away / m * (0.55f - m) * 0.5f;
            }
        }
    }
}
