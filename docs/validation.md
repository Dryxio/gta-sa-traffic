# Validation and format profile

The `sa_compact` backend was implemented independently of the old editor, using observed PC file layout and executable behavior. Decompilation was a navigation aid; ambiguous behavior was checked against a local compact executable. No decompiled source, assembly listings or executable bytes are distributed. The compiler records the audited executable SHA-256 as a provenance identifier, not as an automatic runtime compatibility check.

Layout: five little-endian uint32 counts; 28-byte path nodes; 14-byte car navigation nodes; links, navigation-link references, distances, intersections and dynamic reserve sections. Region IDs fit six bits; navi indices ten bits. Node positions encode signed int16 / 8; navi direction is signed int8 / 100. Node coordinates must fit [-4096, 4095.875]. Regions use the original 8x8 750-unit scheme centered at (-3000,-3000), with outer-bin clamping. This is not an extended-map profile.

The writer enforces at most 65536 path nodes, 1024 navis and 32768 link entries per region, plus signed link-base bounds, degree/packing constraints and flood labels. These are serialization bounds, not a promise that the game has enough memory/pools for such a map.

Coverage: malformed/truncated buffers, opaque byte roundtrip, determinism, cross-region references, one-way direction/address inversion, geometric crossings and bridges, stable-ID transactions, source integrity, independent binary decoding, junction movement reachability, unsupported strict enforcement, full signal clock boundaries, signal attachment/direction remapping, conflicts, IPL output, output overwrite refusal and package installation. Optional headless tests invoke real Blender rather than mocks.

Optional original-corpus tests use `SA_NODES_CORPUS` pointing to your own extracted 64 `nodes*.dat` files. Four tests depend on a matching original corpus and are skipped by default. Do not commit this corpus or imported documents. A different game version can legitimately fail corpus-specific assertions. Synthetic roundtrip/import regression tests remain enabled without it.

Engine evidence: the maintainer has driven on the Perry custom-map test and observed vehicle traffic. This is a local smoke/integration observation. All runtime paths, dense junction traffic, signal behavior and every custom map are not certified. Headless success is never described as proof of collision-free driving.

## Alpha release checks

Local Python 3.14: 62 tests, 58 passed and four optional original-corpus tests skipped; the four actual Blender integration tests ran with Blender 5.2.1 LTS. Python 3.10: 62 tests, 54 passed and eight optional corpus/Blender tests skipped. Clean wheel build and installation into a new Python 3.13 virtual environment passed from outside the checkout, including control compilation and packaged signal registry. Synthetic overlay PNG was rendered and inspected. CI results are available in the repository Actions tab.

Additional private-corpus check: all 62 tests passed with the maintainer’s local original 64-region corpus and Blender enabled (including byte-identical roundtrip of all 64 files). Only this aggregate result is published; the corpus and derived imported documents remain local.
