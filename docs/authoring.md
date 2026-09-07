# Authoring and compilation

Commands: `empty`, `inspect`, `roundtrip`, `import`, `apply`, `diff`, `expand`, `validate`, `compile`. Every command requires `--output`; use `sa-traffic COMMAND --help` for arguments. `roundtrip` and `compile` refuse existing destinations. Other JSON commands may replace the specified JSON file.

## Minimal document

```json
{
  "schema_version": 1, "profile": "sa_compact",
  "nodes": [], "edges": [], "navis": [], "sources": {},
  "routes": [{
    "id": "main-road", "points": [[100,100,10],[160,100,10]],
    "lanes_forward": 1, "lanes_backward": 1, "spacing": 20,
    "node_width": 0, "navi_width": 0, "spawn_probability": 15
  }]
}
```

Forward follows point order; lane counts are 0–7, at least one direction nonzero. Spacing is maximum sampling distance; authored corners remain. Node IDs, edge IDs and route IDs must be stable and unique within their collection. Declare a vehicle node with `id`, `position`, `kind: vehicle`, and reference it using route `start_node` / `end_node` to create a junction. End coordinates must coincide with the referenced node. Crossings have no implicit connectivity, which preserves bridges.

World XYZ uses GTA coordinates, Z up, approximately meters; use one Blender unit per game unit. Preserve full world translation, including altitude. Quantization is 1/8 for node and navi positions. The backend uses an 8x8 grid, 750 units per region, centered on the original map; region selection clamps outer bins while signed coordinate storage still limits representable coordinates. See validation.md. Do not silently translate or wrap a large map.

Native lane spacing is approximately 5.4 units. One lane per direction with `navi_width: 0` has centers about ±2.7 from the centerline. `navi_width` is extra central separation, encoded x16, **not** total road width or arbitrary lane width. `node_width` is a separate native field. `spawn_probability` is a raw threshold 0–15; zero does not guarantee no spawning. Advanced `behaviour` values are raw and not comprehensively validated.

## Existing networks

Extract your own files with your own archive tool. Import all relevant regions, preferably the full 64, so cross-region references can be resolved:

```sh
sa-traffic import /path/to/your/nodes0.dat /path/to/your/nodes1.dat --output output/import.json
# Supply the full set for a real map; POSIX shells can expand /path/to/nodes*.dat.
sa-traffic expand output/authored.json --output output/expanded.json
sa-traffic validate output/authored.json --output output/validation.json
sa-traffic compile output/authored.json --output output/build-001
```

Imports embed raw original bytes and their hashes in JSON. Unknown fields in binary records survive a lossless unmodified roundtrip. Import/export with no graph changes produces no replacement files in a compile patch. `roundtrip file.dat --output new.dat` emits the entire lossless file separately.

Compilation may affect neighboring regions because node indices change; install every manifest-listed DAT together. Flood-component merges require explicit `policies: {"merge_flood_components": true}`. Exceptional imported navigation records that cannot be safely reconstructed fail rather than being guessed.

## Transaction edits

`apply INPUT OPERATIONS --output EDITED` accepts `{ "base_revision": "current fingerprint", "operations": [...] }`. Operations use `op: add|update|remove`, `collection` (defaults to nodes), and `id`/`value`/`changes` as appropriate. Example:

```json
{"base_revision":"COPY_INPUT_REVISION","operations":[{"op":"update","collection":"nodes","id":"junction","changes":{"position":[100,100,10]}}]}
```

`sa_traffic.document.seal(document)` computes a revision after an external JSON edit. Moving a node can also require updating matching route endpoints. Unknown route properties are rejected; use `metadata` for notes, not invented traffic semantics. The example `intersection.json` is an overlay/editing fixture; use `roads-from-zero.json` or `controlled-intersection.json` for complete compilation inputs.
