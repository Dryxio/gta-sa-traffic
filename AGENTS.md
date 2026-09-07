# Agent workflow

Read README.md and docs/authoring.md, docs/blender.md, docs/controls.md before editing a network.

1. Discover user-provided map paths and Blender executable. Work in a fresh ignored output directory. Never assume the maintainer's machine or SSH access exists.
2. Run the synthetic quick start and CLI help. Use profile `sa_compact`; do not claim a different engine is supported.
3. Import map geometry/textures locally using a compatible DragonFF, with `read_mat_split=True`. Confirm roads, textures, world XYZ, scale and height visually. Preserve map coordinates.
4. Author explicit centerlines or tag POLY curves/nonbranching edge chains with `traffic_centerline = True`. Extraction produces proposals with unset lane counts; it is not automatic road detection.
5. Configure forward/backward lanes, separate bridges, explicit junction ports/movements and supported signal groups. Inspect width and turn geometry. Never infer a connection solely from an XY crossing.
6. Run validate, compile into a fresh directory, then reimport the emitted files together with unchanged source regions to inspect the actual encoded graph. Do not inspect an incomplete patch as if it were the whole map.
7. Use the named road collection for surface diagnostics. Unknown/unchecked geometry must remain explicit. Screenshots are not proof of in-game traffic, collisions or AI behavior.
8. Return NODES, manifest, diagnostics and installation notes. Installing to a separate game copy is a distinct integration step. A partial chunk is not a complete map conversion.

Do not promise strict turns, custom signal timings, MTA ambient traffic, extended engine pools or automatic collision generation. Source-import JSON can embed proprietary bytes; never publish it or game files. Tests and examples committed here must remain synthetic.
