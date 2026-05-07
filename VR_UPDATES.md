# VR Client Protocol Updates

Reference document for aligning the Python HRV backend with the current Unity client build.
Covers all behavioural and protocol changes made since the original ball-pacer version.

---

## 1. Breathing Pacer — UI Ring (replaces 3D ball)

The breathing pacer is now a **Screen Space UI ring** (scale animation) and a **heartbeat dot** (pulse animation).

- `move_breathing_ball` — **no-op**. The command is received but ignored; the UI ring has no spatial movement. Do not send this command expecting any visible effect.
- The pacer ring animates at `targetAnimationBPM` (starts 6 BPM, descends toward 5 BPM as patient stabilises). The server does not control this directly — it is driven by the client's own breathing rate estimation loop.
- The heartbeat dot pulses at the live HR received from `hr_data` messages.

---

## 2. New Command — `restart_therapy`

Resets the entire client to its initial state without dropping the WebSocket connection.

```json
{ "type": "command", "action": "restart_therapy" }
```

**Client effect:**
- Hides pacer ring, heartbeat dot, fireflies, birds
- Resets birds to start positions
- Clears all HR / HRV / breathing-rate history buffers
- Resets `isTherapy` to false — firefly timer stops
- Re-enables the debug skip shortcut

**Server should send this** when starting a new session with the same headset connection, or when the therapist triggers a full reset from the control panel.

After sending `restart_therapy`, the server can immediately re-issue the normal therapy flow commands (`play_calibration_tutorial`, `start_hrv_calibration`, `start_therapy`, etc.).

---

## 3. Fireflies — Autonomous Timer (server signals ignored)

Firefly display is now **fully client-driven**. The server no longer controls it.

- `show_fireflies` — **ignored**
- `hide_fireflies` — **ignored**

**Client behaviour:**
- During therapy phase (`isTherapy = true`), fireflies appear automatically every **180 seconds** for **30 seconds**.
- Each appearance randomly selects one of: left group only, right group only, or both groups.
- Timer resets on `restart_therapy` and on therapy start.

**Action required:** Remove `show_fireflies` / `hide_fireflies` from the server's therapy script. They have no effect and can be dropped without replacement.

---

## 4. HRV Color Ring — requires `rr_intervals` in `hr_data`

The pacer ring color shifts based on **RMSSD trend** (short-term HRV):
- HRV decreasing → ring shifts toward **green**
- HRV stable → ring stays **neutral blue**
- HRV increasing → ring shifts toward **red**

This requires the server to include RR intervals in every `hr_data` message:

```json
{
  "type": "hr_data",
  "heartrate": 72,
  "rr_intervals": [832.0, 845.0, 819.0, 858.0]
}
```

- `rr_intervals`: array of floats, successive RR intervals in **milliseconds**, from the most recent sensor batch.
- If `rr_intervals` is absent or has fewer than 2 values, the color ring stays at neutral and no error is thrown.
- The client computes RMSSD internally; the server does not need to send HRV metrics directly.
- A **3 ms RMSSD delta** (recent 20 s vs prior 20 s) is required to register a trend.
- A trend must be **sustained for 8 seconds** before the color begins shifting (anti-flicker).

---

## 5. Unchanged Commands (still active)

| Command | Behaviour |
|---|---|
| `play_calibration_tutorial` | Logged; no visual change |
| `start_hr_baseline` | Logged; no visual change |
| `play_hrv_tutorial` | Shows pacer ring + heartbeat dot |
| `start_hrv_calibration` | Shows pacer ring + heartbeat dot |
| `start_therapy` | Sets therapy active, starts firefly timer |
| `start_birds_flyover` | Triggers bird flyover animation |
| `skip_tutorial` | Logged; no visual change |

---

## 6. Client → Server Status Messages (unchanged)

```json
{ "type": "status", "action": "headset_ready" }
{ "type": "status", "action": "debug_skip_to_therapy" }
```

No new outbound messages were added.
