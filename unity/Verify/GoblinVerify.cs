using System.IO;
using System.Linq;
using System.Text;
using Goblins;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

/// <summary>
/// Batch-mode check of the Blender goblin export.
///   Unity.exe -batchmode -projectPath unity_verify -executeMethod GoblinVerify.Run -quit
/// Imports Goblin.fbx as Humanoid, reports the avatar and the bone mapping, checks every socket,
/// checks that each standalone prop FBX attached through GoblinLoadout lands exactly on the prop
/// embedded in Goblin.fbx, then drives both goblins through HumanPoseHandler (retargeting path)
/// and renders them.
/// </summary>
public static class GoblinVerify
{
    const string Dir = "Assets/GoblinVerify/Model";

    public static void Run()
    {
        var outDir = Path.GetFullPath(Path.Combine(Application.dataPath, "..", "VerifyOutput"));
        Directory.CreateDirectory(outDir);
        var log = new StringBuilder();
        Application.logMessageReceived += (c, s, t) => { if (t != LogType.Log) log.AppendLine($"[{t}] {c}"); };
        try
        {
            AssetDatabase.Refresh();
            var model = Dir + "/Goblin.fbx";
            var imp = (ModelImporter)AssetImporter.GetAtPath(model);
            imp.animationType = ModelImporterAnimationType.Human;
            imp.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
            imp.materialSearch = ModelImporterMaterialSearch.Everywhere;
            imp.SaveAndReimport();
            foreach (var p in Directory.GetFiles(Dir + "/Props", "*.fbx"))
            {
                var pi = (ModelImporter)AssetImporter.GetAtPath(p.Replace('\\', '/'));
                pi.materialSearch = ModelImporterMaterialSearch.Everywhere;
                pi.SaveAndReimport();
            }

            var avatar = AssetDatabase.LoadAllAssetsAtPath(model).OfType<Avatar>().FirstOrDefault();
            log.AppendLine($"avatar={(avatar ? avatar.name : "NONE")} valid={avatar?.isValid} human={avatar?.isHuman}");
            if (avatar != null)
            {
                var mapped = avatar.humanDescription.human.ToDictionary(h => h.humanName, h => h.boneName);
                var required = Enumerable.Range(0, HumanTrait.BoneCount).Where(HumanTrait.RequiredBone)
                    .Select(i => HumanTrait.BoneName[i]).ToArray();
                log.AppendLine($"mapped {mapped.Count} human bones; required missing: " +
                               string.Join(",", required.Where(r => !mapped.ContainsKey(r))));
                foreach (var kv in mapped.OrderBy(k => k.Key)) log.AppendLine($"  {kv.Key} -> {kv.Value}");
            }

            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(model);
            var a = (GameObject)PrefabUtility.InstantiatePrefab(prefab);
            a.name = "Goblin_Embedded";
            a.transform.position = new Vector3(-0.55f, 0, 0);
            var b = (GameObject)PrefabUtility.InstantiatePrefab(prefab);
            b.name = "Goblin_Loadout";
            b.transform.position = new Vector3(0.55f, 0, 0);

            var ta = a.GetComponentsInChildren<Transform>(true);
            log.AppendLine($"root rot={a.transform.GetChild(0).localEulerAngles} scale={a.transform.GetChild(0).localScale}");
            foreach (var t in ta.Where(t => t.name.StartsWith("Socket_")))
                log.AppendLine($"socket {t.name} parent={t.parent.name} children=[{string.Join(",", t.Cast<Transform>().Select(c => c.name))}]" +
                               $" fwd(Z)={t.forward:F2} up(Y)={t.up:F2}");
            foreach (var r in a.GetComponentsInChildren<Renderer>(true))
                log.AppendLine($"renderer {r.name} {r.GetType().Name} mats=[{string.Join(",", r.sharedMaterials.Select(m => m ? $"{m.name}:{(m.mainTexture ? m.mainTexture.name : "NO TEXTURE")}" : "null"))}]" +
                               (r is SkinnedMeshRenderer s ? $" bones={s.bones.Length} verts={s.sharedMesh.vertexCount}" : ""));

            // standalone props through the loadout component
            var lo = b.AddComponent<GoblinLoadout>();
            foreach (var p in Directory.GetFiles(Dir + "/Props", "*.fbx"))
            {
                var pf = AssetDatabase.LoadAssetAtPath<GameObject>(p.Replace('\\', '/'));
                var emb = ta.First(t => t.name == pf.name);
                lo.attachments.Add(new GoblinLoadout.Attachment { socket = emb.parent.name, prefab = pf });
                log.AppendLine($"prop {pf.name}: root rot={pf.transform.localEulerAngles} scale={pf.transform.localScale}");
            }
            lo.Apply();
            var tb = b.GetComponentsInChildren<Transform>(true);
            foreach (var at in lo.attachments)
            {
                var emb = ta.First(t => t.name == at.prefab.name);
                var sockB = tb.First(t => t.name == at.socket);
                var inst = sockB.GetChild(sockB.childCount - 1);
                var mA = emb.GetComponentInChildren<MeshFilter>(true);
                var mB = inst.GetComponentInChildren<MeshFilter>(true);
                var off = b.transform.position - a.transform.position;
                float worst = 0;
                var vA = mA.sharedMesh.vertices;
                var vB = mB.sharedMesh.vertices;
                for (int i = 0; i < Mathf.Min(vA.Length, vB.Length); i += 7)
                    worst = Mathf.Max(worst, Vector3.Distance(mA.transform.TransformPoint(vA[i]) + off, mB.transform.TransformPoint(vB[i])));
                log.AppendLine($"loadout {at.prefab.name} on {at.socket}: max vertex offset vs embedded = {worst * 1000f:F3} mm");
            }

            // humanoid retargeting path: drive both through muscles
            foreach (var go in new[] { a, b })
            {
                var anim = go.GetComponent<Animator>() ?? go.AddComponent<Animator>();
                anim.avatar = avatar;
                var h = new HumanPoseHandler(avatar, go.transform);
                var pose = new HumanPose();
                h.GetHumanPose(ref pose);
                for (int i = 0; i < pose.muscles.Length; i++)
                {
                    var n = HumanTrait.MuscleName[i];
                    if (n.Contains("Stretched")) pose.muscles[i] = -0.7f;          // fists
                    else if (n.Contains("Arm Down-Up")) pose.muscles[i] = -0.35f;
                    else if (n.Contains("Arm Front-Back")) pose.muscles[i] = 0.3f;
                    else if (n.Contains("Forearm Stretch")) pose.muscles[i] = -0.2f;
                    else if (n.Contains("Upper Leg Front-Back")) pose.muscles[i] = 0.25f;
                    else if (n.Contains("Lower Leg Stretch")) pose.muscles[i] = -0.3f;
                    else if (n == "Spine Front-Back") pose.muscles[i] = 0.4f;
                    else if (n == "Head Turn Left-Right") pose.muscles[i] = 0.3f;
                    else pose.muscles[i] = 0f;
                }
                pose.bodyPosition = new Vector3(pose.bodyPosition.x, pose.bodyPosition.y - 0.02f, pose.bodyPosition.z);
                h.SetHumanPose(ref pose);
                go.transform.position = go == a ? new Vector3(-0.55f, 0, 0) : new Vector3(0.55f, 0, 0);
            }

            var light = new GameObject("Sun").AddComponent<Light>();
            light.type = LightType.Directional;
            light.intensity = 1.1f;
            light.transform.rotation = Quaternion.Euler(45, 150, 0);
            RenderSettings.ambientLight = new Color(0.55f, 0.55f, 0.6f);
            Render(outDir, "goblin_unity_front.png", new Vector3(0, 0.6f, 2.6f), new Vector3(0, 0.5f, 0));
            Render(outDir, "goblin_unity_34.png", new Vector3(1.9f, 1.2f, 1.9f), new Vector3(0, 0.5f, 0));
            log.AppendLine("OK");
        }
        catch (System.Exception e)
        {
            log.AppendLine("EXCEPTION " + e);
        }
        File.WriteAllText(Path.Combine(outDir, "goblin_report.txt"), log.ToString());
    }

    static void Render(string outDir, string file, Vector3 pos, Vector3 target)
    {
        var cam = new GameObject("Cam").AddComponent<Camera>();
        cam.transform.position = pos;
        cam.transform.LookAt(target);
        cam.fieldOfView = 34;
        cam.clearFlags = CameraClearFlags.SolidColor;
        cam.backgroundColor = new Color(0.45f, 0.47f, 0.52f);
        var rt = new RenderTexture(1400, 900, 24);
        cam.targetTexture = rt;
        cam.Render();
        RenderTexture.active = rt;
        var tex = new Texture2D(1400, 900, TextureFormat.RGB24, false);
        tex.ReadPixels(new Rect(0, 0, 1400, 900), 0, 0);
        tex.Apply();
        File.WriteAllBytes(Path.Combine(outDir, file), tex.EncodeToPNG());
        RenderTexture.active = null;
        Object.DestroyImmediate(cam.gameObject);
    }
}
