"""Independent boundary table and serialized-signal remapping regressions."""
import struct
import tempfile
from pathlib import Path
import unittest
from sa_traffic.signals import phase, pedestrian_phase
from sa_traffic.document import empty, import_files
from sa_traffic.compiler import compile_document

class IndependentSignalTests(unittest.TestCase):
    def test_full_native_cycle_against_audited_interval_table(self):
        # Intervals from PE comparisons; notably pedestrian 0x3c18, not reversed 15383.
        intervals=[(0,10000,('green','red','red')),
                   (10000,12000,('yellow','red','red')),
                   (12000,22000,('red','green','red')),
                   (22000,24000,('red','yellow','red')),
                   (24000,30768,('red','red','green')),
                   (30768,32768,('red','red','yellow'))]
        for start,end,want in intervals:
            for ms in range(start,end):
                got=(phase(1,ms),phase(2,ms),pedestrian_phase(ms))
                self.assertEqual(got,want,ms)
            for ms in (start,end-1):
                for offset in (32768,2**32):
                    self.assertEqual((phase(1,ms+offset),phase(2,ms+offset),pedestrian_phase(ms+offset)),want)

    def test_imported_signal_flips_filter_when_attached_address_changes(self):
        doc=empty();doc['routes']=[dict(id='r',points=[[10,10,0],[30,10,0]],lanes_forward=1,lanes_backward=1)]
        files,_=compile_document(doc)
        area,data=next(iter(files.items()));data=bytearray(data)
        count=struct.unpack_from('<I',data)[0];off=20+28*count
        # Add a real-format signal with opaque bits, independent of signal writer.
        data[off+11]|=0xc0
        data[off+12]=0xa5 # group1, bridge bit and opaque high bits.
        data[off+13]=0x9c
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/f'nodes{area}.dat';path.write_bytes(data)
            imported=import_files([path]);imported['nodes'][1]['position']=[-10,10,0]
            output,_=compile_document(imported)
            navis=[]
            for a,b in output.items():
                n,v,p,nv,l=struct.unpack_from('<5I',b)
                navis.extend(b[20+28*n+14*i:20+28*n+14*(i+1)] for i in range(nv))
            self.assertEqual(len(navis),1)
            navi=navis[0]
            self.assertEqual(struct.unpack_from('<HH',navi,4),(35,0))
            self.assertEqual((navi[11]>>6)&1,0)
            self.assertEqual(navi[11]&128,128)
            self.assertEqual(navi[11]&63,9)
            self.assertEqual(navi[12:],bytes([0xa5,0x9c]))

if __name__=='__main__':unittest.main()
