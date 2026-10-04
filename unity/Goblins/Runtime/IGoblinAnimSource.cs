namespace Goblins
{
    /// <summary>
    /// What plays a goblin's clips, for the parts that follow them (GoblinArcher's string and arrow, GoblinShaman's
    /// glow and spells, GoblinTwoHandGrip, GoblinPosture): <see cref="GoblinRandomAnimator"/> in the test scenes, a
    /// game's own driver in a game. Looked for on the goblin's GameObject (the Animator's) until one is there, so a
    /// game may add its driver after the goblin woke.
    /// </summary>
    public interface IGoblinAnimSource
    {
        /// <summary>the clip playing, named without the "HumanM@" prefix (Bow_Shoot, Shaman_Hex...)</summary>
        string CurrentClip { get; }
        /// <summary>seconds into that clip (its own time, playback speed included)</summary>
        float CurrentTime { get; }
        /// <summary>0..1: a two-handed pool is playing (GoblinTwoHandGrip puts the shaft through both fists)</summary>
        float TwoHandWeight { get; }
        /// <summary>0..1: GoblinPosture's hunch (0 for clips that carry their own, the bow and staff clips)</summary>
        float HunchWeight { get; }
    }
}
