import os, shutil
import copy,json,math,subprocess,tempfile,unittest
from pathlib import Path
from sa_traffic.control_preview import scene_plan
ROOT=Path(__file__).resolve().parents[2]
BLENDER=Path(os.environ.get('BLENDER_BIN') or shutil.which('blender') or '/nonexistent/blender')
def fixture():return {'controls':{'signals':[dict(id='approach A',navi_xy=[0,0],toward_node='B',phase_group=1,direction_filter=1,placements=[dict(model_id=1315,position=[4,0,0],yaw_degrees=0,group=1)])]}}
class PlanTests(unittest.TestCase):
 def test_clock_boundaries(self):
  r=fixture();self.assertEqual(scene_plan(r,9999)['signals'][0]['color'],'green');self.assertEqual(scene_plan(r,10000)['signals'][0]['color'],'yellow');self.assertEqual(scene_plan(r,12000)['signals'][0]['color'],'red');self.assertEqual(scene_plan(r,32768)['signals'][0]['color'],'green')
 def test_invalid_manifest(self):
  for mutate in [lambda r:r['controls']['signals'][0].update(navi_xy=[float('nan'),0]),lambda r:r['controls']['signals'][0]['placements'][0].update(group=2),lambda r:r['controls']['signals'].append(copy.deepcopy(r['controls']['signals'][0]))]:
   r=fixture();mutate(r)
   with self.assertRaises(ValueError):scene_plan(r,0)
 def test_diagnostic_distinction(self):self.assertIn('NOT stop footprint',scene_plan(fixture(),0)['legend'])
 @unittest.skipUnless(BLENDER.exists(),'Blender unavailable')
 def test_real_blender_build(self):
  with tempfile.TemporaryDirectory() as td:
   td=Path(td);probe=td/'probe.py';result=td/'result.json'
   probe.write_text('import sys,json,bpy\nsys.path.insert(0,'+repr(str(ROOT))+')\nfrom sa_traffic.control_preview import build,scene_plan\nr=build(scene_plan('+repr(fixture())+',12000))\nmarkers=[o for o in bpy.data.objects if o.name.startswith("DIAG phase")]\nassert len(markers)==1 and markers[0]["phase"]=="red"\nassert bpy.context.scene.camera.data.type=="ORTHO"\nassert any(o.name.startswith("12m reference") for o in bpy.data.objects)\nopen('+repr(str(result))+',"w").write(json.dumps(r))\n')
   run=subprocess.run([str(BLENDER),'--background','--factory-startup','--python-exit-code','1','--python',str(probe)],capture_output=True,text=True,timeout=60)
   self.assertEqual(run.returncode,0,run.stdout+run.stderr);self.assertEqual(json.loads(result.read_text())['markers'],1)
if __name__=='__main__':unittest.main()
