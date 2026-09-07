# Edit an existing San Andreas network

The README's Grove before/after screenshots were rendered from real imported NODES. The following workflow reproduces the operation on a user's own extracted files; no game assets or original NODES are supplied here.

1. Extract all 64 original `nodes0.dat`–`nodes63.dat` into a local directory. Keep the game installation unchanged.
2. Import the complete set, select a stable node, and apply an explicit position change. Use a new output directory.

```python
from pathlib import Path
from sa_traffic.document import import_files, apply, fingerprint
from sa_traffic.compiler import compile_document
from sa_traffic.oracle import check

source = Path("/path/to/your/extracted-nodes")
out = Path("output/my-edited-network")
out.mkdir(parents=True, exist_ok=False)
doc = import_files(source.glob("nodes*.dat"))
original, unchanged = compile_document(doc)
assert unchanged["changed_regions"] == []

# Example demonstrated in the gallery: original PC Grove loop node 15:6.
# On other datasets, inspect the map and select your own existing node.
node = next(n for n in doc["nodes"] if n["origin"] == [15, 6])
position = list(node["position"])
position[0] -= 2
edited = apply(doc, {
    "base_revision": fingerprint(doc),
    "operations": [{"op": "update", "collection": "nodes",
                    "id": node["id"], "changes": {"position": position}}]
})
files, manifest = compile_document(edited)
assert check(files)["valid"]
for region, blob in files.items():
    (out / f"nodes{region}.dat").write_bytes(blob)
for region in set(original) - set(manifest["changed_regions"]):
    assert original[region] == files[region]
rebuilt = import_files(out.glob("nodes*.dat"))
assert next(n for n in rebuilt["nodes"] if n["origin"] == [15, 6])["position"] == position
print("Changed regions:", manifest["changed_regions"])
```

3. Visualize a local **vehicle-only subset** from both original and reimported documents in the same textured Blender map chunk. Keep nodes in the chosen bounds, only edges whose endpoints both survive, and navis referenced by those edges. A clipped visualization is not a complete compiler input.
4. Compare using the same camera. In this example the node is highlighted pink solely for readability. The after view uses the reimported DAT, including reconstructed navigation records, rather than a manually dragged display object.

Local result used for the gallery: original node 15:6 moved from `[2502, -1669.75, 13]` to `[2500, -1669.75, 13]`; region 15 changed; 63 other regions remained byte-identical. Independent binary validation succeeded with four pre-existing exceptional-navi warnings preserved. The installed game was untouched, and this specific edit was not driven in game.

For practical edits, inspect road width, surface height, turning radius and collisions. The example demonstrates the data roundtrip; it does not assert that every two-unit displacement is a good road design. Native source files and their imported JSON contain proprietary data and must stay local.
