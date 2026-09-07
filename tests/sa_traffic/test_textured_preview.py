import os, shutil
"""A real Blender check for preview material isolation and texture transparency."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

BLENDER=Path(os.environ.get('BLENDER_BIN') or shutil.which('blender') or '/nonexistent/blender')
ROOT=Path(__file__).resolve().parents[2]

@unittest.skipUnless(BLENDER.exists(), 'Blender unavailable')
class TexturedPreviewTests(unittest.TestCase):
    def test_previews_preserve_source_material_and_use_texture_alpha(self):
        with tempfile.TemporaryDirectory() as temp:
            output=Path(temp)/'result.json'
            script=Path(temp)/'probe.py'
            script.write_text('''import sys,json,bpy
sys.path.insert(0,ROOT)
from sa_traffic.textured_preview import prepare
obj=bpy.context.active_object
mat=bpy.data.materials.new('source');mat.use_nodes=True
tex=mat.node_tree.nodes.new('ShaderNodeTexImage');tex.image=bpy.data.images.new('test',2,2,alpha=True)
obj.data.materials.clear();obj.data.materials.append(mat)
count_before=len(mat.node_tree.nodes)
prepare(bpy.context.scene)
new=obj.active_material
links=[(l.from_node.type,l.from_socket.name,l.to_node.type,l.to_socket.name) for l in new.node_tree.links]
result={'distinct':new!=mat,'source_unchanged':len(mat.node_tree.nodes)==count_before,'local':obj.material_slots[0].link=='OBJECT','alpha':any(a=='TEX_IMAGE' and b=='Alpha' and c=='MIX_SHADER' for a,b,c,d in links),'color':any(a=='TEX_IMAGE' and b=='Color' and c=='EMISSION' for a,b,c,d in links),'engine':bpy.context.scene.render.engine}
open(OUTPUT,'w').write(json.dumps(result))
'''.replace('ROOT',repr(str(ROOT))).replace('OUTPUT',repr(str(output))))
            result=subprocess.run([str(BLENDER),'--background','--factory-startup','--python-exit-code','1','--python',str(script)],capture_output=True,text=True,timeout=60)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            data=json.loads(output.read_text())
            for key in ('distinct','source_unchanged','local','alpha','color'):
                self.assertTrue(data[key],key)
            self.assertEqual(data['engine'],'CYCLES')
