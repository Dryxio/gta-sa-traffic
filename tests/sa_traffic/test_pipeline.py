import os
import copy,json,math,struct,sys,tempfile,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from sa_traffic.codec import decode,TrafficError
from sa_traffic.document import empty,import_files,apply,fingerprint,seal,expand_routes
from sa_traffic.compiler import compile_document,validate
ROOT=Path(__file__).resolve().parents[2]
CORPUS=Path(os.environ.get('SA_NODES_CORPUS', '/nonexistent/optional-nodes-corpus'))
def route_doc(points=None,forward=1,backward=1):
 d=empty();d['routes']=[dict(id='test',points=points or [[0,0,0],[40,0,0]],lanes_forward=forward,lanes_backward=backward)];return seal(d)

def oracle(data):
 # Independent offset-based inspection; deliberately no production decode helper.
 n,v,p,nav,l=struct.unpack_from('<5I',data)
 assert n==v+p
 navoff=20+28*n;linkoff=navoff+14*nav;nl=linkoff+4*(l+192)
 ns=[struct.unpack_from('<3h',data,20+i*28+8) for i in range(n)]
 links=[struct.unpack_from('<HH',data,linkoff+4*i) for i in range(l)]
 navis=[]
 for i in range(nav):
  o=navoff+14*i;attached=struct.unpack_from('<HH',data,o+4);lane=data[o+11];navis.append((attached,lane&7,(lane>>3)&7))
 return dict(nodes=ns,links=links,navis=navis,counts=(n,v,p,nav,l))

class CodecTests(unittest.TestCase):
 @unittest.skipUnless(len(list(CORPUS.glob('*.dat')))==64, 'Optional user-supplied 64-region corpus')
 def test_all_corpus_lossless(self):
  files=list(CORPUS.glob('*.dat'));self.assertEqual(len(files),64)
  for p in files:
   with self.subTest(file=p.name):b=p.read_bytes();self.assertEqual(decode(b).encode(),b)
 def test_empty(self):
  b=bytes(20);self.assertEqual(decode(b).encode(),b)
 def test_truncation_every_boundary(self):
  outputs,_=compile_document(route_doc());b=next(iter(outputs.values()));n,v,p,nav,l=struct.unpack_from('<5I',b)
  boundaries=[20,20+28*n,20+28*n+14*nav,20+28*n+14*nav+4*(l+192),len(b)]
  for k in boundaries:
   with self.subTest(k=k),self.assertRaises(TrafficError):decode(b[:k-1])
 def test_huge_count(self):
  with self.assertRaises(TrafficError):decode(struct.pack('<5I',2**32-1,2**32-1,0,0,0))
 def test_unknown_raw_bytes_preserved(self):
  outputs,_=compile_document(route_doc());b=bytearray(next(iter(outputs.values())));b[20:28]=bytes.fromhex('deadbeef01234567');b[47]=0xab;b.extend(b'opaque-tail')
  self.assertEqual(decode(bytes(b)).encode(),bytes(b))

class GraphTests(unittest.TestCase):
 def test_empty_to_double(self):
  o,m=compile_document(route_doc());a=oracle(next(iter(o.values())));self.assertEqual(a['counts'],(3,3,0,2,4));self.assertTrue(all(x[1:]==(1,1) for x in a['navis']))
 def test_one_way_orientation(self):
  o,m=compile_document(route_doc(forward=1,backward=0));a=oracle(next(iter(o.values())))
  # Attached minimum node; forward is away from it, therefore high lanes=1.
  self.assertTrue(all(x[1:]==(0,1) for x in a['navis']))
 def test_reverse_one_way(self):
  o,_=compile_document(route_doc(forward=0,backward=1));self.assertTrue(all(x[1:]==(1,0) for x in oracle(next(iter(o.values())))['navis']))
 def test_region_boundary(self):
  o,m=compile_document(route_doc([[-10,10,0],[10,10,0]]));self.assertEqual(len(o),2)
  refs=[x for b in o.values() for x in oracle(b)['links']];self.assertTrue(any(a!=min(o) for a,i in refs))
 def test_parallel_bridge_no_autoconnect(self):
  d=route_doc([[-20,0,0],[20,0,0]]);d['routes'].append(dict(id='bridge',points=[[0,-20,10],[0,20,10]],lanes_forward=1,lanes_backward=1));x=expand_routes(d)
  self.assertFalse(any(e['source'].split(':')[1]!=e['target'].split(':')[1] for e in x['edges']));compile_document(d)
 def test_junction_explicit(self):
  d=empty();d['nodes']=[dict(id='junction',position=[0,0,0],kind='vehicle')]
  for i,p in enumerate(([40,0,0],[0,40,0],[-40,0,0])):d['routes'].append(dict(id=str(i),points=[[0,0,0],p],start_node='junction',lanes_forward=1,lanes_backward=1))
  o,m=compile_document(d);self.assertEqual(len([e for e in expand_routes(d)['edges'] if e['source']=='junction']),3)
 def test_deterministic_and_permutation(self):
  d=route_doc();o,_=compile_document(d);self.assertEqual(o,compile_document(d)[0]);x=expand_routes(d);x['nodes'].reverse();x['edges'].reverse();self.assertEqual(o,compile_document(x)[0])
 def test_quantized_region_assignment(self):
  o,m=compile_document(route_doc([[-.01,100,0],[20,100,0]]));self.assertEqual(set(o),{36})
 def test_too_dense_route_rejected(self):
  d=route_doc([[0,0,0],[1,0,0]]);d['routes'][0]['spacing']=.01
  with self.assertRaises(TrafficError):compile_document(d)
 def test_out_of_profile_no_wrap(self):
  with self.assertRaises(TrafficError):compile_document(route_doc([[5000,0,0],[5010,0,0]]))
 def test_pair_metadata(self):
  d=expand_routes(route_doc());d['edges'][1]['lanes_forward']=7
  with self.assertRaises(TrafficError):compile_document(d)
 def test_unsupported_route_fields(self):
  for k in ('traffic_lights','movements','lanse_forward'):
   d=route_doc();d['routes'][0][k]=True
   with self.assertRaises(TrafficError):compile_document(d)
 def test_transaction_conflict_and_reference(self):
  d=empty();d['nodes']=[dict(id='a',position=[0,0,0],kind='vehicle')];d['routes']=[dict(id='r',points=[[0,0,0],[10,0,0]],start_node='a',lanes_forward=1,lanes_backward=1)]
  with self.assertRaises(TrafficError):apply(d,dict(base_revision='wrong',operations=[]))
  with self.assertRaises(TrafficError):apply(d,dict(base_revision=fingerprint(d),operations=[dict(op='remove',id='a')]))
 def test_move_restore(self):
  d=empty();d['nodes']=[dict(id='a',position=[0,0,0],kind='vehicle')];original=copy.deepcopy(d)
  d=apply(d,dict(base_revision=fingerprint(d),operations=[dict(op='update',id='a',changes=dict(position=[1,0,0]))]));d=apply(d,dict(base_revision=fingerprint(d),operations=[dict(op='update',id='a',changes=dict(position=[0,0,0]))]));self.assertEqual(fingerprint(d),fingerprint(original))

@unittest.skipUnless(len(list(CORPUS.glob('*.dat')))==64, 'Optional user-supplied 64-region corpus')
class CorpusGraphTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.doc=import_files(CORPUS.glob('*.dat'))
 def test_full_import_roundtrip(self):
  o,m=compile_document(self.doc);self.assertEqual(m['changed_regions'],[]);self.assertEqual(len(o),64)
 def test_local_append_only_dependency_regions(self):
  d=copy.deepcopy(self.doc);anchor=next(n for n in d['nodes'] if n.get('origin')==[15,11]);p=anchor['position'];d['routes']=[dict(id='grove-service',points=[p,[p[0]+10,p[1],p[2]]],start_node=anchor['id'],lanes_forward=1,lanes_backward=1)]
  o,m=compile_document(d);self.assertIn(15,m['changed_regions']);self.assertEqual(m['changed_regions'],[7,14,15,23])
  for a in set(range(64))-set(m['changed_regions']):self.assertEqual(o[a],(CORPUS/f'nodes{a}.dat').read_bytes())
 def test_source_corruption(self):
  d=copy.deepcopy(self.doc);d['sources']['0']['sha256']='wrong'
  with self.assertRaises(TrafficError):compile_document(d)
if __name__=='__main__':unittest.main()
