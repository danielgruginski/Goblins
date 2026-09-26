using System;
using System.Collections.Generic;
using UnityEngine;

namespace Goblins
{
    /// <summary>
    /// Attaches modular prop prefabs to a goblin's Socket_* transforms.
    ///
    /// Every prop FBX in Goblins/Props is modelled in its socket's space, so it only has to be
    /// parented under the socket with an identity local pose. The same prop fits any goblin that
    /// shares the skeleton (same Socket_ names).
    ///
    /// Sockets: Socket_RightHand, Socket_LeftHand (grip; +Y along the handle toward the business end, +Z up in the T-pose),
    /// Socket_LeftForearm / Socket_RightForearm (shields), Socket_LeftShoulder / Socket_RightShoulder,
    /// Socket_LeftHip / Socket_RightHip, Socket_Belt, Socket_Chest, Socket_Back, Socket_Helm.
    /// </summary>
    public class GoblinLoadout : MonoBehaviour
    {
        [Serializable]
        public struct Attachment
        {
            public string socket;
            public GameObject prefab;
        }

        public List<Attachment> attachments = new List<Attachment>();
        [Tooltip("Hide the props that ship inside Goblin.fbx so only this loadout shows.")]
        public bool hideEmbeddedProps = true;

        readonly List<GameObject> spawned = new List<GameObject>();

        void Awake() => Apply();

        public void Apply()
        {
            Clear();
            if (hideEmbeddedProps)
                foreach (var t in GetComponentsInChildren<Transform>(true))
                    if (t.name.StartsWith("Prop_") && t.parent != null && t.parent.name.StartsWith("Socket_"))
                        t.gameObject.SetActive(false);
            foreach (var a in attachments)
            {
                var socket = FindSocket(a.socket);
                if (socket == null || a.prefab == null)
                {
                    Debug.LogWarning($"GoblinLoadout: missing socket '{a.socket}' or prefab on {name}", this);
                    continue;
                }
                var go = Instantiate(a.prefab, socket);
                go.transform.SetLocalPositionAndRotation(Vector3.zero, Quaternion.identity);
                go.transform.localScale = Vector3.one;
                spawned.Add(go);
            }
        }

        public void Clear()
        {
            foreach (var go in spawned)
                if (go != null)
                {
                    if (Application.isPlaying) Destroy(go);
                    else DestroyImmediate(go);
                }
            spawned.Clear();
        }

        public Transform FindSocket(string socketName)
        {
            foreach (var t in GetComponentsInChildren<Transform>(true))
                if (t.name == socketName)
                    return t;
            return null;
        }
    }
}
