"""Independent checks of serialized driving direction, including address inversions."""
import struct
import unittest
from sa_traffic.document import empty
from sa_traffic.compiler import compile_document


def read_bytes(files):
    nodes, navis, edges = {}, {}, {}
    for area, data in files.items():
        count, vehicles, peds, navi_count, link_count = struct.unpack_from('<5I', data)
        nav_offset = 20 + count * 28
        link_offset = nav_offset + navi_count * 14
        navi_link_offset = link_offset + 4 * link_count + 768
        for i in range(navi_count):
            off = nav_offset + i * 14
            xy = struct.unpack_from('<2h', data, off)
            attached = struct.unpack_from('<2H', data, off + 4)
            direction = struct.unpack_from('<2b', data, off + 8)
            flags = data[off + 11]
            navis[area, i] = (attached, direction, flags & 7, (flags >> 3) & 7, xy)
        for i in range(count):
            off = 20 + i * 28
            nodes[area, i] = tuple(x / 8 for x in struct.unpack_from('<3h', data, off + 8))
            base = struct.unpack_from('<h', data, off + 16)[0]
            degree = data[off + 24] & 15
            for k in range(base, base + degree):
                dest = struct.unpack_from('<2H', data, link_offset + 4 * k)
                packed = struct.unpack_from('<H', data, navi_link_offset + 2 * k)[0]
                edges[(area, i), dest] = (packed >> 10, packed & 1023)
    return nodes, navis, edges


class IndependentDrivingTests(unittest.TestCase):
    def test_physical_lanes_and_tangents_survive_orientation_and_address_changes(self):
        paths = [([0, 0, 0], [20, 0, 0]), ([20, 0, 0], [0, 0, 0]),
                 ([0, 20, 1], [0, 0, 0]), ([-10, 10, 0], [10, 10, 0]),
                 ([10, 10, 0], [-10, 10, 0]), ([10, -10, 0], [10, 10, 0]),
                 ([10, 10, 0], [10, -10, 0]), ([-20, -20, 0], [0, 0, 2])]
        for a, b in paths:
            for names in [('a', 'z'), ('z', 'a')]:
                for forward, backward in [(1, 0), (0, 1), (2, 1), (1, 3)]:
                    with self.subTest(a=a, b=b, names=names, lanes=(forward, backward)):
                        doc = empty()
                        doc['nodes'] = [dict(id=names[0], position=a, kind='vehicle'),
                                        dict(id=names[1], position=b, kind='vehicle')]
                        doc['routes'] = [dict(id='road', points=[a, b], spacing=100,
                                              start_node=names[0], end_node=names[1],
                                              lanes_forward=forward, lanes_backward=backward)]
                        files, manifest = compile_document(doc)
                        nodes, navis, edges = read_bytes(files)
                        source, target = (tuple(manifest['mapping'][name]) for name in names)
                        self.assertEqual(set(edges), {(source, target), (target, source)})
                        self.assertEqual(edges[source, target], edges[target, source])
                        attached, direction, toward, away, midpoint = navis[edges[source, target]]
                        self.assertEqual(attached, min(source, target))
                        self.assertEqual(toward if attached == target else away, forward)
                        self.assertEqual(toward if attached == source else away, backward)
                        other = target if attached == source else source
                        delta = [nodes[attached][j] - nodes[other][j] for j in range(2)]
                        dot = sum(delta[j] * direction[j] for j in range(2))
                        self.assertGreater(dot, 0)
                        self.assertLess(abs(delta[0] * direction[1] - delta[1] * direction[0]), 1)
                        self.assertEqual(midpoint, tuple(round((a[j]+b[j])*4) for j in range(2)))

    def test_new_boundary_placement_uses_encoded_coordinates(self):
        doc=empty()
        doc['routes']=[dict(id='road',points=[[-.01,100,0],[20,100,0]],lanes_forward=1,lanes_backward=1)]
        files,_=compile_document(doc)
        nodes,_,_=read_bytes(files)
        for (area,index),(x,y,z) in nodes.items():
            expected=min(7,max(0,int((x+3000)/750)))+8*min(7,max(0,int((y+3000)/750)))
            self.assertEqual(area,expected)

if __name__=='__main__':unittest.main()
