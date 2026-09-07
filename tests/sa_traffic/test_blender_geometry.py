import os, shutil
import importlib.util,json,subprocess,tempfile,unittest,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BRIDGE=ROOT/'sa_traffic/blender_bridge.py'
BLENDER=Path(os.environ.get('BLENDER_BIN') or shutil.which('blender') or '/nonexistent/blender')
spec=importlib.util.spec_from_file_location('bridge',BRIDGE);bridge=importlib.util.module_from_spec(spec);spec.loader.exec_module(bridge)
class GeometryTests(unittest.TestCase):
    def test_raw_lane_direction_and_proposal_direction(self):
        raw=struct.pack('<hhHHbbBBH',0,0,15,0,100,0,0,2,0)
        d=dict(nodes=[dict(id='a',position=[10,0,0])],navis=[dict(id='n',raw=raw.hex(),attached='a')],routes=[dict(id='r',points=[[0,0,0],[0,10,0]],lanes_forward=0,lanes_backward=1)])
        p=bridge.overlay_primitives(d)
        self.assertEqual(len(p['arrows']),2)
        self.assertEqual(p['arrows'][0]['direction'],[1,0,0])
        self.assertEqual(p['arrows'][0]['lanes'],2)
        self.assertEqual(p['arrows'][1]['direction'],[0,-1,0])
        self.assertEqual(p['attachments'][0][1],[10,0,0])
    def test_estimated_lane_offsets(self):
        d=dict(routes=[dict(id='r',points=[[0,0,0],[10,0,0]],lanes_forward=1,lanes_backward=1,navi_width=0)])
        lines=bridge.estimated_lane_lines(d)
        self.assertAlmostEqual(lines[0]['points'][0][1],-2.7,places=5)
        self.assertAlmostEqual(lines[1]['points'][0][1],2.7,places=5)
        d['routes'][0].update(lanes_forward=2,lanes_backward=0)
        lines=bridge.estimated_lane_lines(d)
        self.assertAlmostEqual(lines[0]['offset'],-2.7,places=5)
        self.assertAlmostEqual(lines[1]['offset'],2.7,places=5)

    @unittest.skipUnless(BLENDER.exists(),'Blender unavailable')
    def test_real_surface_bridge_and_explicit_proposals(self):
        with tempfile.TemporaryDirectory() as t:
            script=Path(t)/'test.py'
            script.write_text(f'''import bpy,importlib.util
spec=importlib.util.spec_from_file_location('bridge',{str(BRIDGE)!r});b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
c=bpy.data.collections.new('Roads');bpy.context.scene.collection.children.link(c)
def mesh(name,verts,edges,faces):
 m=bpy.data.meshes.new(name);m.from_pydata(verts,edges,faces);o=bpy.data.objects.new(name,m);c.objects.link(o);return o
mesh('lower',[(-5,-5,0),(5,-5,0),(5,5,0),(-5,5,0)],[],[(0,1,2,3)])
mesh('bridge',[(-5,-5,10),(5,-5,10),(5,5,10),(-5,5,10)],[],[(0,1,2,3)])
bpy.context.view_layer.update()
d={{'nodes':[{{'id':'ground','position':[0,0,0]}},{{'id':'bridge','position':[0,0,10]}},{{'id':'badheight','position':[0,0,5]}},{{'id':'missing','position':[20,20,0]}}]}}
r=b.surface_diagnostics(d,'Roads',.5)
assert [(x['id'],x['code']) for x in r]==[('badheight','ROAD_HEIGHT_MISMATCH'),('missing','NO_ROAD_SURFACE')],r
assert b.propose_centerlines()['routes']==[]
o=mesh('marked',[(0,0,0),(5,0,0),(10,0,0)],[(0,1),(1,2)],[]);o['traffic_centerline']=True
p=b.propose_centerlines();assert len(p['routes'])==1
assert p['routes'][0]['lanes_forward'] is None
assert p['routes'][0]['points']==[[0,0,0],[5,0,0],[10,0,0]]
assert p['routes'][0]['metadata']['status']=='proposal_requires_lane_configuration'
o['traffic_centerline']=False
curve=bpy.data.curves.new('explicit','CURVE');curve.dimensions='3D';s=curve.splines.new('POLY');s.points.add(1);s.points[0].co=(0,0,0,1);s.points[1].co=(0,5,0,1)
obj=bpy.data.objects.new('curve',curve);c.objects.link(obj);obj['traffic_centerline']=True
assert b.propose_centerlines()['routes'][0]['points']==[[0,0,0],[0,5,0]]
''')
            result=subprocess.run([str(BLENDER),'--background','--factory-startup','--python-exit-code','1','--python',str(script)],capture_output=True,text=True,timeout=120)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
