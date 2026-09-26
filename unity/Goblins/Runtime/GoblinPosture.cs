using UnityEngine;

namespace Goblins
{
    /// <summary>
    /// Goblin hunch layered on top of any Humanoid clip: bends the spine forward and counter-rotates neck and
    /// head so the gaze stays level. Human mocap reads upright; this makes it read goblin. Skipped while the
    /// goblin is lying down (hips far from upright).
    /// </summary>
    [RequireComponent(typeof(Animator))]
    [DefaultExecutionOrder(100)]
    public class GoblinPosture : MonoBehaviour
    {
        public static bool GlobalEnabled = true;
        [Range(0, 2)] public float amount = 1f;
        public float spine = 8f, chest = 7f, upperChest = 8f, neck = -9f, head = -12f;

        Transform hips, tSpine, tChest, tUpper, tNeck, tHead;
        GoblinRandomAnimator driver;

        void Awake()
        {
            driver = GetComponent<GoblinRandomAnimator>();
            var a = GetComponent<Animator>();
            hips = a.GetBoneTransform(HumanBodyBones.Hips);
            tSpine = a.GetBoneTransform(HumanBodyBones.Spine);
            tChest = a.GetBoneTransform(HumanBodyBones.Chest);
            tUpper = a.GetBoneTransform(HumanBodyBones.UpperChest);
            tNeck = a.GetBoneTransform(HumanBodyBones.Neck);
            tHead = a.GetBoneTransform(HumanBodyBones.Head);
        }

        void LateUpdate()
        {
            if (!GlobalEnabled || amount <= 0 || hips == null) return;
            float upright = Mathf.InverseLerp(0.5f, 0.85f, Vector3.Dot(hips.up, Vector3.up));
            if (upright <= 0) return;
            var axis = transform.right;
            float k = amount * upright * (driver != null ? driver.HunchWeight : 1f);   // bow clips carry their own hunch
            if (k <= 0) return;
            Bend(tSpine, spine * k, axis);
            Bend(tChest, chest * k, axis);
            Bend(tUpper, upperChest * k, axis);
            Bend(tNeck, neck * k, axis);
            Bend(tHead, head * k, axis);
        }

        static void Bend(Transform t, float deg, Vector3 axis)
        {
            if (t != null) t.rotation = Quaternion.AngleAxis(deg, axis) * t.rotation;
        }
    }
}
