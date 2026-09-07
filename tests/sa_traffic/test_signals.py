import copy,json,struct,unittest
from pathlib import Path
from sa_traffic.codec import TrafficError,decode
from sa_traffic.document import empty,expand_routes
from sa_traffic.compiler import compile_document
from sa_traffic.signals import phase,pedestrian_phase,visual_group,should_stop,placement_ipl
from sa_traffic.controls import movement_conflicts

def signal_doc():
 d=empty();d['nodes']=[dict(id='A',position=[10,10,0],kind='vehicle'),dict(id='B',position=[30,10,0],kind='vehicle')];d['routes']=[dict(id='r',points=[[10,10,0],[30,10,0]],start_node='A',end_node='B',lanes_forward=1,lanes_backward=1)];d['signals']=[dict(id='s',segment='route:r:segment:000000',toward_node='B',phase_group=2,placements=[dict(model_id=1315,position=[20,15,3],yaw_degrees=90)])];return d

class SignalTests(unittest.TestCase):
 def test_actual_encoded_filter_and_ipl(self):
  files,m=compile_document(signal_doc());s=m['controls']['signals'][0];a,i=s['navi_address'];b=files[a];n=struct.unpack_from('<I',b)[0];o=20+n*28+i*14
  self.assertEqual(b[o+12]&3,2);self.assertEqual((b[o+11]>>6)&1,0);self.assertEqual(b[o+11]&63,9)
  line=placement_ipl([s]).splitlines()[2].split(', ');self.assertEqual(len(line),11);self.assertEqual(line[:2],['1315','trafficlight1']);self.assertAlmostEqual(float(line[8]),-2**-.5)
 def test_opposite_direction(self):
  d=signal_doc();d['signals'][0]['toward_node']='A';f,m=compile_document(d);self.assertEqual(m['controls']['signals'][0]['direction_filter'],1)
 def test_zero_lane_refused(self):
  d=signal_doc();d['routes'][0]['lanes_backward']=0;d['signals'][0]['toward_node']='A'
  with self.assertRaisesRegex(TrafficError,'ZERO_LANES'):compile_document(d)
 def test_conflicting_navi_assignments(self):
  d=signal_doc();s=copy.deepcopy(d['signals'][0]);s['id']='other';s['toward_node']='A';d['signals'].append(s)
  with self.assertRaisesRegex(TrafficError,'SIGNAL_CONFLICT'):compile_document(d)
 def test_visual_group_mismatch(self):
  d=signal_doc();d['signals'][0]['placements'][0]['yaw_degrees']=0
  with self.assertRaisesRegex(TrafficError,'VISUAL_GROUP'):compile_document(d)
 def test_custom_group_timing_model_rejected(self):
  for mutate in (lambda s:s.update(phase_group=3),lambda s:s.update(offset_ms=100),lambda s:s['placements'][0].update(model_id=99999)):
   d=signal_doc();mutate(d['signals'][0])
   with self.assertRaises(TrafficError):compile_document(d)
 def test_phase_boundaries(self):
  self.assertEqual([phase(1,t) for t in (9999,10000,11999,12000,32768)],['green','yellow','yellow','red','green'])
  self.assertEqual([phase(2,t) for t in (11999,12000,21999,22000,23999,24000)],['red','green','green','yellow','yellow','red'])
  self.assertEqual(pedestrian_phase(30767),'green');self.assertEqual(pedestrian_phase(30768),'yellow')
 def test_visual_open_boundaries(self):
  for yaw in (-30,60,150,240):self.assertEqual(visual_group(yaw),2)
  self.assertEqual(visual_group(-29.99),1);self.assertEqual(visual_group(59.99),1)
 def test_pe_green_short_circuit(self):
  a=dict(group=1,attachment_matches=True,direction_filter=1,direction_sign=-1,signed_projection=4);b={**a,'group':2}
  self.assertFalse(should_stop([a,b],0));self.assertTrue(should_stop([b,a],0))
  self.assertTrue(should_stop([a,b],0,force=True))
 def test_stop_open_intervals(self):
  c=dict(group=2,attachment_matches=True,direction_filter=1,direction_sign=-1)
  self.assertFalse(should_stop([{**c,'signed_projection':0}],0));self.assertFalse(should_stop([{**c,'signed_projection':12}],0));self.assertTrue(should_stop([{**c,'signed_projection':11.999}],0));self.assertFalse(should_stop([{**c,'signed_projection':7,'previous':True}],0))
 def test_expand_preserves_control_contract(self):
  d=json.loads((Path(__file__).parents[2]/'examples/controlled-intersection.json').read_text());expanded=expand_routes(d)
  self.assertTrue(expanded['junctions']);a,ma=compile_document(d);b,mb=compile_document(expanded);self.assertEqual(a,b);self.assertEqual(ma['junction_validation'],mb['junction_validation'])
 def test_geometry_conflict_z_and_policy(self):
  j={'id':'j','movements':[{'from':'w','to':'e','points':[[-10,0,0],[10,0,0]]},{'from':'s','to':'n','points':[[0,-10,0],[0,10,0]]}]};d={'junctions':[j]};signals=[{'approach':{'junction':'j','port':p},'phase_group':1} for p in ('w','s')]
  self.assertEqual(movement_conflicts(d,signals)[0]['status'],'same_green_phase');d['policies']={'signal_conflicts':'reject'}
  with self.assertRaises(TrafficError):movement_conflicts(d,signals)
  j['movements'][1]['points']=[[0,-10,10],[0,10,10]];self.assertEqual(movement_conflicts(d,signals),[])
if __name__=='__main__':unittest.main()
