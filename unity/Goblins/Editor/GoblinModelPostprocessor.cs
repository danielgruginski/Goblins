using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;

namespace Goblins.EditorTools
{
    /// <summary>
    /// Imports Goblin*.fbx as Humanoid and pins the optional Jaw to the "Jaw" bone. The goblin and its props import with
    /// Read/Write on: GoblinAppearance merges a goblin's parts into one mesh at run time, and reads theirs to do it
    /// (without it a goblin in a game is merged empty: invisible).
    ///
    /// Unity's auto-mapper otherwise hands the Jaw slot to another child of Head (the helmet
    /// socket) or leaves it empty; a clip that animates the jaw would then wobble the helmet or do nothing. The first import
    /// auto-maps; this postprocessor then reimports once with the corrected mapping.
    /// </summary>
    class GoblinModelPostprocessor : AssetPostprocessor
    {
        // Goblin@<clip>.fbx animation files copy Goblin.fbx's avatar instead (GoblinSetup.ConfigureClips)
        static bool IsGoblin(string path) =>
            Path.GetFileName(path).StartsWith("Goblin", StringComparison.OrdinalIgnoreCase) &&
            !Path.GetFileName(path).Contains("@") &&
            path.EndsWith(".fbx", StringComparison.OrdinalIgnoreCase);

        static bool JawIsWrong(ModelImporter imp)
        {
            var hd = imp.humanDescription;
            var human = hd.human;
            if (human == null || human.Length == 0) return false;
            if (hd.skeleton == null || !hd.skeleton.Any(s => s.name == "Jaw")) return false;   // no Jaw bone: nothing to pin
            var jaw = human.FirstOrDefault(h => h.humanName == "Jaw");
            return jaw.humanName == null || jaw.boneName != "Jaw";      // missing or pointing at another bone
        }

        static bool IsProp(string path) =>
            path.Replace('\\', '/').IndexOf("Goblins/Models/Props/", StringComparison.OrdinalIgnoreCase) >= 0 &&
            path.EndsWith(".fbx", StringComparison.OrdinalIgnoreCase);

        void OnPreprocessModel()
        {
            if (IsProp(assetPath)) ((ModelImporter)assetImporter).isReadable = true;     // merged at run time
            if (!IsGoblin(assetPath)) return;
            var imp = (ModelImporter)assetImporter;
            imp.isReadable = true;                                                      // merged at run time
            if (imp.animationType != ModelImporterAnimationType.Human)
            {
                imp.animationType = ModelImporterAnimationType.Human;
                imp.avatarSetup = ModelImporterAvatarSetup.CreateFromThisModel;
            }
            if (!JawIsWrong(imp)) return;
            var hd = imp.humanDescription;
            var human = hd.human.ToList();
            var jaw = new HumanBone { humanName = "Jaw", boneName = "Jaw", limit = new HumanLimit { useDefaultValues = true } };
            var i = human.FindIndex(h => h.humanName == "Jaw");
            if (i >= 0) human[i] = jaw;
            else human.Add(jaw);
            hd.human = human.ToArray();
            imp.humanDescription = hd;
        }

        static void OnPostprocessAllAssets(string[] imported, string[] deleted, string[] moved, string[] movedFrom)
        {
            foreach (var path in imported.Where(IsGoblin))
            {
                if (AssetImporter.GetAtPath(path) is ModelImporter imp && JawIsWrong(imp))
                    EditorApplication.delayCall += () => AssetDatabase.ImportAsset(path, ImportAssetOptions.ForceUpdate);
            }
        }
    }
}
