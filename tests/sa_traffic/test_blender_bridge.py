import os, shutil
"""Run with python -m unittest discover -s tests/sa_traffic -p test_blender_bridge.py.
The integration test invokes the actual installed Blender; no bpy mocks.
"""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
BRIDGE = ROOT / 'sa_traffic/blender_bridge.py'
BLENDER = Path(os.environ.get('BLENDER_BIN') or shutil.which('blender') or '/nonexistent/blender')
spec = importlib.util.spec_from_file_location('bridge', BRIDGE)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

class BridgeValidation(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT/'examples/intersection.json').read_text())

    def test_bad_positions_and_unknown_references(self):
        for bad in ([0, 1], [0, True, 2], [0, float('nan'), 2]):
            data = copy.deepcopy(self.data)
            data['nodes'][0]['position'] = bad
            with self.assertRaises(ValueError):
                bridge.validate(data)
        self.data['edges'][0]['source'] = 'missing'
        with self.assertRaises(ValueError):
            bridge.validate(self.data)

    def test_duplicate_ids(self):
        self.data['nodes'][1]['id'] = self.data['nodes'][0]['id']
        with self.assertRaises(ValueError):
            bridge.validate(self.data)

    @unittest.skipUnless(BLENDER.exists(), 'Blender installation unavailable')
    def test_real_blender_roundtrip_edit_and_topology_rejection(self):
        with tempfile.TemporaryDirectory(prefix='traffic-bridge-') as tmp:
            tmp = Path(tmp)
            output, rendered, exported = tmp/'scene.blend', tmp/'scene.png', tmp/'graph.json'
            subprocess.run([str(BLENDER), '--background', '--factory-startup', '--python-exit-code', '1', '--python', str(BRIDGE), '--', '--input', str(ROOT/'examples/intersection.json'), '--output', str(output), '--render', str(rendered), '--export-json', str(exported)], check=True, capture_output=True, text=True, timeout=120)
            self.assertEqual(json.loads(exported.read_text()), self.data)
            self.assertGreater(rendered.stat().st_size, 1000)
            self.assertGreater(output.stat().st_size, 1000)
            # Verify persistence and edits on a new Blender process; preserve unknown metadata.
            script = tmp/'edit.py'
            edited = tmp/'edited.json'
            script.write_text(f'''import bpy, importlib.util, json
spec=importlib.util.spec_from_file_location("bridge", {str(BRIDGE)!r})
b=importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
col=bpy.data.collections[b.COLLECTION]
assert len([o for o in col.objects if o.type in {{'MESH','CURVE'}}]) == 10
assert bpy.data.objects.get('Cube') is not None, 'Existing scene was deleted'
g=next(o for o in col.objects if o.get('traffic_role')=='graph')
g.data.vertices[0].co.x = -21
routes=next(o for o in col.objects if o.get('traffic_role')=='routes')
routes.data.splines[0].points[0].co.x = -22
out=b.export_scene()
assert out['nodes'][0]['flags']==123
assert out['nodes'][0]['position'][0]==-21
assert out['routes'][0]['points'][0][0]==-22
open({str(edited)!r},'w').write(json.dumps(out))
g.data.clear_geometry()
try: b.export_scene()
except ValueError: pass
else: raise AssertionError('Topology edit silently accepted')
''')
            subprocess.run([str(BLENDER), '--background', str(output), '--python-exit-code', '1', '--python', str(script)], check=True, capture_output=True, text=True, timeout=120)
            self.assertEqual(json.loads(edited.read_text())['nodes'][0]['position'][0], -21)

if __name__ == '__main__':
    unittest.main()
