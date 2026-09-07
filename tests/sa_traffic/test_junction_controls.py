"""Serialized junction contracts and explicit limits of compact fallback semantics."""
import copy
import json
import struct
import unittest
from pathlib import Path
from sa_traffic.compiler import compile_document
from sa_traffic.codec import TrafficError

EXAMPLE=Path(__file__).resolve().parents[2]/'examples/controlled-intersection.json'

def graph_from_bytes(files):
    navis={};records=[];graph={}
    for area,data in files.items():
        n,v,p,nv,l=struct.unpack_from('<5I',data)
        no=20+28*n;lo=no+14*nv;nlo=lo+4*l+768
        for i in range(nv):
            o=no+14*i;lanes=data[o+11]
            navis[area,i]=(struct.unpack_from('<HH',data,o+4),lanes&7,(lanes>>3)&7)
        for i in range(v):
            o=20+28*i;src=(area,i);graph[src]=[]
            base=struct.unpack_from('<h',data,o+16)[0]
            for k in range(base,base+(data[o+24]&15)):
                dst=struct.unpack_from('<HH',data,lo+4*k)
                packed=struct.unpack_from('<H',data,nlo+2*k)[0]
                records.append((src,dst,(packed>>10,packed&1023)))
    for src,dst,nav in records:
        attached,toward,away=navis[nav]
        if (toward if dst==attached else away)>0:graph[src].append(dst)
    return graph,records

def first_exits(graph,start,exits):
    todo=[start];seen=set();found=set()
    while todo:
        at=todo.pop()
        if at in seen:continue
        seen.add(at)
        if at in exits:found.add(exits[at]);continue
        todo.extend(graph.get(at,[]))
    return found

class JunctionControlsTests(unittest.TestCase):
    def setUp(self):self.doc=json.loads(EXAMPLE.read_text())

    def test_serialized_graph_exactly_eleven_movements_and_reverse_arcs_forbidden(self):
        files,manifest=compile_document(self.doc)
        graph,records=graph_from_bytes(files)
        j=self.doc['junctions'][0];mapping=manifest['mapping']
        exits={tuple(mapping[p['exit_node']]):p['id'] for p in j['ports']}
        actual={(p['id'],end) for p in j['ports'] for end in first_exits(graph,tuple(mapping[p['entry_node']]),exits)}
        expected={(a,b) for a in ('west','east','north','south') for b in ('west','east','north','south') if a!=b}-{('west','north')}
        self.assertEqual(actual,expected);self.assertEqual(len(actual),11)
        self.assertEqual({tuple(x) for x in manifest['junction_validation'][0]['actual']},expected)
        for source,target,_ in records:
            self.assertNotEqual(target in graph[source],source in graph[target])
        self.assertEqual(manifest['controls']['engine_validation'],'pending')

    def test_ordering_does_not_change_serialized_navigation(self):
        a,_=compile_document(self.doc)
        d=copy.deepcopy(self.doc);d['nodes'].reverse();d['junctions'][0]['ports'].reverse();d['junctions'][0]['movements'].reverse()
        b,_=compile_document(d);self.assertEqual(a,b)

    def test_strict_contract_refused(self):
        self.doc['junctions'][0]['enforcement']='strict'
        with self.assertRaisesRegex(TrafficError,'TURN_RUNTIME_REQUIRED'):compile_document(self.doc)

    def test_shared_port_identity_refused(self):
        self.doc['junctions'][0]['ports'][1]['entry_node']='west:in'
        with self.assertRaisesRegex(TrafficError,'PORT_ALIAS'):compile_document(self.doc)

    def test_entry_and_exit_must_be_distinct(self):
        self.doc['junctions'][0]['ports'][0]['exit_node']='west:in'
        with self.assertRaisesRegex(TrafficError,'PORT_NODES'):compile_document(self.doc)

    def test_connector_endpoint_must_match_port(self):
        self.doc['junctions'][0]['movements'][0]['points'][0][0]+=2
        with self.assertRaisesRegex(TrafficError,'MOVEMENT_ENDPOINT'):compile_document(self.doc)

    def test_dead_approach_refused(self):
        j=self.doc['junctions'][0];j['movements']=[m for m in j['movements'] if m['from']!='west']
        with self.assertRaisesRegex(TrafficError,'MOVEMENT_DEAD_APPROACH'):compile_document(self.doc)

    def test_external_bypass_into_forbidden_exit_is_not_hidden_by_internal_filter(self):
        self.doc['nodes'].append(dict(id='outside-bypass',position=[75,130,1],kind='vehicle'))
        self.doc['routes'].extend([
            dict(id='bypass-a',start_node='west:in',end_node='outside-bypass',points=[[60,97,1],[75,130,1]],lanes_forward=1,lanes_backward=0),
            dict(id='bypass-b',start_node='outside-bypass',end_node='north:out',points=[[75,130,1],[97,140,1]],lanes_forward=1,lanes_backward=0)])
        with self.assertRaisesRegex(TrafficError,'JUNCTION_'):compile_document(self.doc)

    def test_abstract_last_fallback_can_select_zero_lane_predecessor(self):
        # Focused counterexample to any guarantee inferred only from lane counts.
        # Models assignments at compact 0x42E44D, not full vehicle execution.
        previous='approach';loaded_outgoing=[];backward_lanes=0
        chosen=loaded_outgoing[0] if loaded_outgoing else previous
        self.assertEqual(backward_lanes,0);self.assertEqual(chosen,previous)
        # Chase fallback 0x4271F0..0x42734C ranks adjacency angle without navi lanes.
        candidates=[dict(node='reverse_connector',angle=.1,lanes=0),dict(node='legal',angle=.5,lanes=1)]
        best=min(candidates,key=lambda item:item['angle'])
        self.assertEqual(best['node'],'reverse_connector');self.assertEqual(best['lanes'],0)

if __name__=='__main__':unittest.main()
