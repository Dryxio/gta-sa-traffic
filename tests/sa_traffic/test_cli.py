import json,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
class CLITests(unittest.TestCase):
 def test_pipeline_and_no_overwrite(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)
   def run(*args):return subprocess.run([sys.executable,'-m','sa_traffic',*map(str,args)],cwd=ROOT,capture_output=True,text=True)
   self.assertEqual(run('empty','--output',p/'empty.json').returncode,0)
   d=json.loads((p/'empty.json').read_text());op={'base_revision':d['revision'],'operations':[{'op':'add','collection':'routes','value':{'id':'r','points':[[10,10,0],[30,10,0]],'lanes_forward':1,'lanes_backward':0}}]};(p/'op.json').write_text(json.dumps(op))
   self.assertEqual(run('apply',p/'empty.json',p/'op.json','--output',p/'road.json').returncode,0)
   self.assertEqual(run('validate',p/'road.json','--output',p/'check.json').returncode,0)
   self.assertTrue(json.loads((p/'check.json').read_text())['valid'])
   self.assertEqual(run('compile',p/'road.json','--output',p/'build').returncode,0)
   before=(p/'build/manifest.json').read_bytes();self.assertNotEqual(run('compile',p/'road.json','--output',p/'build').returncode,0);self.assertEqual(before,(p/'build/manifest.json').read_bytes())
 def test_validate_catches_compile_semantics(self):
  with tempfile.TemporaryDirectory() as td:
   p=Path(td);doc={'schema_version':1,'profile':'sa_compact','nodes':[],'edges':[],'routes':[{'id':'r','points':[[0,0,0],[10,0,0]],'lanes_forward':1,'lanes_backward':1,'traffic_lights':True}]};(p/'d.json').write_text(json.dumps(doc))
   r=subprocess.run([sys.executable,'-m','sa_traffic','validate',str(p/'d.json'),'--output',str(p/'result.json')],cwd=ROOT,capture_output=True,text=True);self.assertEqual(r.returncode,1);self.assertFalse(json.loads((p/'result.json').read_text())['valid'])
if __name__=='__main__':unittest.main()
