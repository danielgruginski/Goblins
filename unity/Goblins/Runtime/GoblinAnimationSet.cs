using System;
using UnityEngine;

namespace Goblins
{
    /// <summary>
    /// Weighted pools of Humanoid clips for GoblinRandomAnimator. A pool plays one random clip, or all of its
    /// clips in order when <see cref="Pool.sequence"/> is set (Begin, Loop, Stop). Looping clips are held for a
    /// random time inside <see cref="Pool.hold"/>.
    /// </summary>
    [CreateAssetMenu(menuName = "Goblins/Animation Set")]
    public class GoblinAnimationSet : ScriptableObject
    {
        [Serializable]
        public class Pool
        {
            public string name;
            [Min(0)] public float weight = 1;
            public AnimationClip[] clips;
            [Tooltip("Play the clips in order instead of picking one.")]
            public bool sequence;
            [Tooltip("Root-motion locomotion: the goblin steers while this plays.")]
            public bool moves;
            [Tooltip("Seconds a looping clip is held.")]
            public Vector2 hold = new Vector2(3, 6);
            [Tooltip("Seconds to hold the last frame of a one-shot clip (e.g. lying dead).")]
            public float holdAfter;
            [Tooltip("Two-handed weapon clips (polearm): GoblinTwoHandGrip puts the shaft through both fists.")]
            public bool twoHanded;
            [Tooltip("Clips authored on the goblin (bow clips) already carry the hunch: GoblinPosture stays out.")]
            public bool upright;
            [Tooltip("Pool to play next; empty = pick a random pool.")]
            public string next;
        }

        public Pool[] pools = Array.Empty<Pool>();

        public Pool Get(string poolName) => Array.Find(pools, p => p.name == poolName);

        public Pool PickWeighted()
        {
            float total = 0;
            foreach (var p in pools) if (p.clips != null && p.clips.Length > 0) total += p.weight;
            float r = UnityEngine.Random.value * total;
            foreach (var p in pools)
            {
                if (p.clips == null || p.clips.Length == 0) continue;
                r -= p.weight;
                if (r <= 0 && p.weight > 0) return p;
            }
            return pools[0];
        }
    }
}
