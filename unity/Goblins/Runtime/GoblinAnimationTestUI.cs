using UnityEngine;

namespace Goblins
{
    /// <summary>
    /// Viewer for the goblin animation test scene: orbit camera with colony / mid / close presets
    /// (right-drag orbits, scroll zooms), hunch toggle, time scale, reshuffle, and clip names over heads.
    /// Uses IMGUI events only, so it works with either input system.
    /// </summary>
    [RequireComponent(typeof(Camera))]
    public class GoblinAnimationTestUI : MonoBehaviour
    {
        public Vector3 focus = new Vector3(0, 0.5f, 0);
        public float distance = 15f, pitch = 40f, yaw = 200f;
        public bool orbit = true;
        public bool labels = true;

        Camera cam;
        float timeScale = 1f;
        bool merged = true, looksLabels;
        int renderers, draws;
        float countAt;

        void Awake() => cam = GetComponent<Camera>();

        void LateUpdate()
        {
            if (orbit) yaw += 5f * Time.unscaledDeltaTime;
            var rot = Quaternion.Euler(pitch, yaw, 0);
            transform.SetPositionAndRotation(focus + rot * new Vector3(0, 0, -distance), rot);
        }

        void Preset(float d, float p, float fov)
        {
            distance = d;
            pitch = p;
            cam.fieldOfView = fov;
        }

        void OnGUI()
        {
            var e = Event.current;
            if (e.type == EventType.MouseDrag && e.button == 1)
            {
                yaw += e.delta.x * 0.3f;
                pitch = Mathf.Clamp(pitch + e.delta.y * 0.2f, 5f, 85f);
            }
            if (e.type == EventType.ScrollWheel)
                distance = Mathf.Clamp(distance * (1f + e.delta.y * 0.05f), 2f, 80f);

            GUILayout.BeginArea(new Rect(10, 10, 260, 450), GUI.skin.box);
            GUILayout.Label($"Goblins: {GoblinRandomAnimator.All.Count}   (right-drag orbit, scroll zoom)");
            GUILayout.BeginHorizontal();
            if (GUILayout.Button("Colony 40m")) Preset(40f, 50f, 30f);
            if (GUILayout.Button("Mid 15m")) Preset(15f, 40f, 35f);
            if (GUILayout.Button("Close 5m")) Preset(5f, 18f, 40f);
            GUILayout.EndHorizontal();
            orbit = GUILayout.Toggle(orbit, "Slow orbit");
            GoblinPosture.GlobalEnabled = GUILayout.Toggle(GoblinPosture.GlobalEnabled, "Goblin hunch (on top of the clips)");
            labels = GUILayout.Toggle(labels, "Show labels");
            if (labels) looksLabels = GUILayout.Toggle(looksLabels, "   labels show looks (not clips)");
            if (GUILayout.Button("Re-roll looks"))
                foreach (var g in GoblinRandomAnimator.All)
                    if (g.TryGetComponent<GoblinAppearance>(out var look)) look.Reroll();
            GUILayout.Label($"Time scale {timeScale:F2}");
            timeScale = GUILayout.HorizontalSlider(timeScale, 0.1f, 2f);
            Time.timeScale = timeScale;
            if (GUILayout.Button("Reshuffle animations"))
                foreach (var g in GoblinRandomAnimator.All) g.Restart();
            bool m = GUILayout.Toggle(merged, "Merge each goblin into one mesh");
            if (m != merged)
            {
                merged = m;
                foreach (var g in GoblinRandomAnimator.All)
                    if (g.TryGetComponent<GoblinAppearance>(out var look)) look.SetMerged(merged);
                countAt = 0;
            }
            if (Time.unscaledTime >= countAt)
            {
                renderers = draws = 0;
                foreach (var g in GoblinRandomAnimator.All)
                    foreach (var r in g.GetComponentsInChildren<Renderer>())
                        if (r.enabled)
                        {
                            renderers++;
                            draws += r.sharedMaterials.Length;
                        }
                countAt = Time.unscaledTime + 0.5f;
            }
            GUILayout.Label($"Goblin renderers: {renderers}, draws: {draws} (+ as many shadow draws)");
            GUILayout.EndArea();

            if (!labels) return;
            var style = new GUIStyle(GUI.skin.label) { alignment = TextAnchor.MiddleCenter, fontSize = 11 };
            foreach (var g in GoblinRandomAnimator.All)
            {
                var sp = cam.WorldToScreenPoint(g.transform.position + Vector3.up * 1.25f);
                if (sp.z < 0) continue;
                string text = g.CurrentClip;
                if (looksLabels && g.TryGetComponent<GoblinAppearance>(out var look)) text = look.Summary;
                var r = new Rect(sp.x - 150, Screen.height - sp.y - 20, 300, 40);
                style.wordWrap = true;
                GUI.color = Color.black;
                GUI.Label(new Rect(r.x + 1, r.y + 1, r.width, r.height), text, style);
                GUI.color = Color.white;
                GUI.Label(r, text, style);
            }
        }
    }
}
