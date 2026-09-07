"""Game-free full-region import and package-output regression coverage."""
import copy, json, struct, tempfile, unittest
from pathlib import Path
from sa_traffic.compiler import compile_document
from sa_traffic.document import empty, import_files
from sa_traffic.codec import decode, TrafficError
from sa_traffic.__main__ import main

class SyntheticImportTests(unittest.TestCase):
    def test_64_regions_roundtrip_and_append_patch(self):
        doc=empty();doc['nodes']=[{'id':'anchor','position':[-10,10,0],'kind':'vehicle'}]
        doc['routes']=[{'id':'cross-region','points':[[-10,10,0],[40,10,0]],'start_node':'anchor','lanes_forward':1,'lanes_backward':1}]
        generated,_=compile_document(doc)
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);original={a:generated.get(a,bytes(20)) for a in range(64)}
            for a,b in original.items():
                (root/f'nodes{a}.dat').write_bytes(b)
                self.assertEqual(decode(b).encode(),b)
            imported=import_files(root.glob('nodes*.dat'))
            output,manifest=compile_document(imported)
            self.assertEqual(output,original);self.assertEqual(manifest['changed_regions'],[])
            anchor=next(n for n in imported['nodes'] if n['position']==[-10,10,0])
            imported['routes']=[{'id':'extension','points':[[-10,10,0],[-10,50,0]],'start_node':anchor['id'],'lanes_forward':1,'lanes_backward':0}]
            edited,manifest=compile_document(imported)
            self.assertTrue(manifest['changed_regions'])
            for a in set(original)-set(manifest['changed_regions']):self.assertEqual(edited[a],original[a])
            bad=copy.deepcopy(imported);bad['sources']['0']['sha256']='wrong'
            with self.assertRaises(TrafficError):compile_document(bad)

    def test_control_bundle_contains_only_identifier_registry(self):
        root=Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'build'
            self.assertEqual(main(['compile',str(root/'examples/signaled-intersection.json'),'--output',str(out)]),0)
            required=json.loads((out/'signal-model-requirements.json').read_text())
            self.assertTrue(required['models'])
            for model in required['models']:self.assertEqual(set(model),{'id','name','txd'})
            self.assertTrue(json.loads((out/'validation.json').read_text())['valid'])
