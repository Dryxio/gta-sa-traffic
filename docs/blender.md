# Blender CLI

The scripts run with Blender's bundled Python; the compiler uses ordinary Python. There is no GUI add-on installation requirement. Run from this repository checkout. Tested locally with the installed Blender; release test results are in validation.md. `BLENDER_BIN` selects an executable for tests; CLI examples use `blender` on PATH.

```sh
blender --background --factory-startup --python-exit-code 1 --python sa_traffic/blender_bridge.py -- --input examples/roads-from-zero.json --output output/roads.blend --render output/roads.png --export-json output/roads-editable.json
```

For a map, replace `--factory-startup` with your `context.blend` path. The bridge owns only its `SA Traffic` collection. It stores the original JSON in `SA_TRAFFIC_SOURCE.json`. Editable graph vertices and POLY route control points preserve stable order and metadata; moving points and object transforms is supported. Adding/deleting/reordering vertices, edges or splines is unsupported: edit explicit JSON and reimport. Same-count identity swaps cannot always be detected. Leave edit mode before export. Display helpers are static: export and reimport after editing.

```sh
blender --background output/roads.blend --python-exit-code 1 --python sa_traffic/blender_bridge.py -- --export-json output/edited.json
```

The overlay batches geometry rather than creating an object per node. Cyan nodes, orange links, green proposals, purple navi centers and estimated lanes are diagnostics. Green does not mean validated. `--focus 100,100,10 --span 140 --display-lift 3` changes the view/display only.

## Map textures / DragonFF

Map import is a separate step; this tool does not contain a general IMG/IPL/DFF loader or a game asset extractor. Install [DragonFF](https://github.com/Parik27/DragonFF) separately (GPL-3.0; not bundled). Use its API for your installed version, explicitly enabling **`read_mat_split=True`** during DFF import. Without material splits, some meshes can assign wrong textures to faces (checkerboards or stripes). If your version lacks this option, use a compatible version rather than silently dropping it. Resolve each DFF's TXD/textures from your own game and verify several buildings and road surfaces before authoring routes. Import placements/world transforms as well as meshes; isolated DFF local coordinates are insufficient.

To inspect an already textured scene with overlay and camera:

```sh
blender --background output/context-with-traffic.blend --python-exit-code 1 --python sa_traffic/textured_preview.py -- --output output/textured.blend --render output/textured.png
blender --background output/context-with-traffic.blend --python-exit-code 1 --python sa_traffic/control_preview.py -- --report output/signals-build-001/manifest.json --time-ms 12000 --output output/signals.blend --render output/signals.png
```

These previews copy materials and use the first image's diffuse color/alpha; they do not reproduce GTA day/night prelighting or arbitrary multilayer/PBR materials. Never use them to claim engine visual parity.

## Centerline proposals and surface checks

Tag POLY curves or nonbranching mesh-edge chains `traffic_centerline = True`:

```sh
blender --background context.blend --python-exit-code 1 --python sa_traffic/blender_bridge.py -- --propose-centerlines output/proposals.json
```

Lane counts are deliberately unset. Inspect and complete proposals before compiling. Branching chains must be explicitly split. No generic road mesh extraction is performed.

`--input graph.json --road-collection Roads --diagnostics-json output/surface.json` raycasts only your named road collection. Samples include nodes, route points and estimated lane offsets at at most 5-unit spacing, in a ±50 vertical window. Layered surfaces are enumerated. Default height tolerance is 1 unit. This does not certify width, vehicle clearance, collisions or turning radii. Without a road collection the scene records `unchecked_no_road_collection`.

Preview-only `diagnostics` are metadata for the bridge, not compiler graph properties; keep the authoring document and preview artifact distinct when necessary.
