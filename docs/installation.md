# Installing generated files in a test game

This compiler writes files, not a game conversion or runtime traffic system. Keep your original installation and use a separate backed-up test copy.

1. Compile the full authoring document to a new build directory. Read `manifest.json`, `validation.json`, changed regions and diagnostics.
2. For an existing map, apply **all** changed `nodesN.dat` files as a consistent set using your own IMG/Modloader setup; original SA stores NODES in its archives. Keep unchanged regions from the same source snapshot. Do not mix files from different builds or rename region numbers.
3. For a replacement map with zero prior nodes, the compiler emits occupied/affected regions only. Your test setup must provide all 64 `nodes0.dat`–`nodes63.dat`: use generated files for occupied regions and valid empty files for the remainder only if the entire original network is intentionally replaced. A valid empty file for this layout is 20 zero bytes. Do not do this when adding a chunk to the existing SA map.
4. Install optional signal IPL placements with matching native model definitions/assets, using your existing map loader. DAT flags and visible signal objects are separate. Avoid installing duplicate poles when the map already contains the intended lights.
5. Verify collision/map registration/streaming first, then test spawning, both lane directions, junctions, bridges, signals, route boundaries and longer driving. Keep crash logs local.

Original map limits and pools, unused IPLs, missing COL, model registrations and streaming configuration are integration responsibilities. Successful compile cannot fix a broken game conversion. Perry's local setup required such fixes separately; they are not bundled as generic patches.

MTA does not acquire an ambient traffic system merely by receiving these DAT files. This project does not supply a server resource, synced AI or runtime enforcement. Extended-map/FLA backends require a separate supported profile and are not currently implemented.
