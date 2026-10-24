using System;
using UnityEngine;

namespace Goblins
{
    /// <summary>
    /// Receives the animation events of the clips authored in this repo (<c>OnGoblinEvent(name)</c>: the troll's Roar at
    /// the roar's peak) and raises <see cref="EventFired"/>; hook sound and gameplay there. A game's clip player can also
    /// read the event's time from the clip (the event's stringParameter is the name).
    /// </summary>
    public class GoblinEvents : MonoBehaviour
    {
        public event Action<GoblinEvents, string> EventFired;
        public void OnGoblinEvent(string name) => EventFired?.Invoke(this, name);
    }
}
