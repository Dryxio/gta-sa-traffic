# Signals and junction movements

See `examples/signaled-intersection.json` for a complete synthetic four-approach example. Compile it with `sa-traffic compile ... --output output/new-build`.

## Native signals

A `signals` entry uses `id`, exactly one `segment` (generated route segment ID) or `navi` (imported stable navi ID), `toward_node`, `phase_group: 1|2`, optional `approach: {junction, port}`, and `placements`.

```json
{"id":"west-light","segment":"route:approach-west:segment:000000","toward_node":"west:in","phase_group":2,"approach":{"junction":"crossing","port":"west"},"placements":[{"model_id":1315,"position":[45,101,4],"yaw_degrees":90}]}
```

Use the actual IDs in your expanded document/manifest. A signal controls travel **toward** the given endpoint. Zero-lane directions and incompatible assignments on one navi are rejected. A navi can encode only one controlled direction/group. Split approach segments where necessary.

The normal global clock repeats every 32768 ms:

| Group | Green | Yellow | Red |
|---|---|---|---|
| 1 | 0–9999 | 10000–11999 | remainder |
| 2 | 12000–21999 | 22000–23999 | remainder |

No local timers, offset, third group or arbitrary protected-left program. Engine riot/cheat behavior is outside the normal preview.

Placements may be empty for DAT-only output. NODES flags create navigation control; IPL places visible objects. Neither alone creates the other. The compiler exports conjugated world-yaw IPL quaternions and checks visual group consistency: cardinal yaw 0/180 gives group 1, 90/270 group 2. Native recognized IDs: 1262,1283,1284,1315,1350,1351,1352,3516,3855. You must supply intact native model registrations/textures/LIGHT effects in your game; the bundled registry contains only identifiers, no extracted assets or effects. Position, pole height, visibility and curb clearance require visual review.

## Junctions

Each `junctions` entry declares `id`, `enforcement: native_navigation`, distinct `ports` (`id`, `entry_node`, `exit_node`) and `movements` (`from`, `to`, `points`, optional `spacing`). Allowed movements become separate one-way connector paths. No implicit shared node is created where their geometry crosses.

The verifier reconstructs allowed travel from exported DAT bytes and checks first-exit reachability against the requested movement matrix, including unintended external bypasses. This verifies the **normal directed graph**, not every native AI fallback. Some random/pursuit fallback paths ignore lane restrictions. `enforcement: strict` fails with `TURN_RUNTIME_REQUIRED`; no runtime patch or MTA adapter is supplied.

Potential movement conflicts are reported as `same_green_phase`, `uncontrolled_approach`, or `separated_green_phases`. The latter is not clearance-time certification. The diagnostics do not model vehicle envelopes, CarCtrl curved trajectories, merges, priority/yield or every collision. `policies.signal_conflicts` defaults to `report`; `reject` rejects detected uncontrolled/same-green conflicts. Synthetic examples deliberately expose conflicts for review.

Build outputs include `controls.json`, optional `traffic-signals.ipl` and `signal-model-requirements.json`, plus manifest checks. The Blender control preview uses colored diagnostic markers, not actual signal assets or simulated vehicles. Its 12-unit circles are distance references, not the real longitudinal stopping predicate.
