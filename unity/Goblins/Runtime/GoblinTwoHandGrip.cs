using UnityEngine;

namespace Goblins
{
    /// <summary>
    /// Two-handed polearm grip: the prop in Socket_RightHand is swung about the right fist so its shaft passes
    /// through the left fist (Socket_LeftHand), as polearm clips expect. <see cref="weight"/> blends it in; the
    /// GoblinRandomAnimator drives it from pools marked two-handed, a game state machine can set it directly.
    /// </summary>
    [DefaultExecutionOrder(200)]       // after the animation and GoblinPosture
    public class GoblinTwoHandGrip : MonoBehaviour
    {
        [Range(0, 1)] public float weight;

        Transform right, left, prop;
        GoblinRandomAnimator driver;

        void Awake()
        {
            foreach (var t in GetComponentsInChildren<Transform>(true))
            {
                if (t.name == "Socket_RightHand") right = t;
                else if (t.name == "Socket_LeftHand") left = t;
            }
            driver = GetComponent<GoblinRandomAnimator>();
        }

        void LateUpdate()
        {
            if (right == null || left == null) return;
            if (prop == null || prop.parent != right)
                prop = right.childCount > 0 ? right.GetChild(right.childCount - 1) : null;
            if (prop == null) return;
            prop.localRotation = Quaternion.identity;
            if (driver != null) weight = driver.TwoHandWeight;
            var axis = right.up;                                   // the prop's shaft (+Y, toward the tip)
            var toLeft = left.position - right.position;
            float w = weight * Mathf.Clamp01((toLeft.magnitude - 0.08f) / 0.07f);   // hands too close: no reliable line
            if (w <= 0) return;
            var target = Vector3.Dot(toLeft, axis) >= 0 ? toLeft.normalized : -toLeft.normalized;
            var swing = Quaternion.FromToRotation(axis, target);
            prop.rotation = Quaternion.Slerp(Quaternion.identity, swing, w) * prop.rotation;
        }
    }
}
