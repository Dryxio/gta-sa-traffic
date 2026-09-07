"""Strict lossless codec for the audited SA compact NODES layout."""
from dataclasses import dataclass
import struct

class TrafficError(ValueError):
    pass

@dataclass
class Area:
    counts: tuple
    nodes: list
    navis: list
    links: list
    navi_links: list
    distances: bytes
    intersections: bytes
    reserved_links: bytes = b''
    reserved_distances: bytes = b''
    reserved_intersections: bytes = b''
    trailing: bytes = b''

    def encode(self):
        n,v,p,nv,l = self.counts
        if n != v+p or len(self.nodes)!=n or len(self.navis)!=nv or len(self.links)!=l:
            raise TrafficError('COUNTS: inconsistent arrays')
        if any(len(x)!=28 for x in self.nodes) or any(len(x)!=14 for x in self.navis):
            raise TrafficError('RECORD_SIZE: node/navi')
        out=bytearray(struct.pack('<5I',*self.counts))
        out.extend(b''.join(self.nodes));out.extend(b''.join(self.navis))
        if l:
            if len(self.navi_links)!=l or len(self.distances)!=l or len(self.intersections)!=l:
                raise TrafficError('COUNTS: inconsistent link arrays')
            if (len(self.reserved_links),len(self.reserved_distances),len(self.reserved_intersections))!=(768,192,192):
                raise TrafficError('RESERVE: incorrect dynamic reserve sizes')
            for a,i in self.links: out.extend(struct.pack('<HH',a,i))
            out.extend(self.reserved_links)
            for x in self.navi_links: out.extend(struct.pack('<H',x))
            out.extend(self.distances);out.extend(self.reserved_distances)
            out.extend(self.intersections);out.extend(self.reserved_intersections)
        elif any((self.navi_links,self.distances,self.intersections,self.reserved_links,self.reserved_distances,self.reserved_intersections)):
            raise TrafficError('EMPTY: link arrays with zero count')
        out.extend(self.trailing)
        return bytes(out)

def decode(data):
    if len(data)<20: raise TrafficError('TRUNCATED: header')
    counts=struct.unpack_from('<5I',data);n,v,p,nv,l=counts
    if n!=v+p: raise TrafficError('COUNTS: total differs from vehicles + pedestrians')
    size=20+28*n+14*nv+(8*l+1152 if l else 0)
    if size>len(data):raise TrafficError(f'TRUNCATED: needs {size}, got {len(data)}')
    # Length check precedes allocation and bounds. Counts cannot induce huge allocations.
    if nv>1024 or n>65536 or l>32768:raise TrafficError('CAPACITY: compact record/index bounds')
    pos=20;nodes=[data[pos+28*i:pos+28*(i+1)] for i in range(n)];pos+=28*n
    navis=[data[pos+14*i:pos+14*(i+1)] for i in range(nv)];pos+=14*nv
    links=[];nl=[];d=b'';inter=b'';rl=rd=ri=b''
    if l:
        links=[struct.unpack_from('<HH',data,pos+4*i) for i in range(l)];pos+=4*l
        rl=data[pos:pos+768];pos+=768
        nl=list(struct.unpack_from(f'<{l}H',data,pos));pos+=2*l
        d=data[pos:pos+l];pos+=l;rd=data[pos:pos+192];pos+=192
        inter=data[pos:pos+l];pos+=l;ri=data[pos:pos+192];pos+=192
    for i,r in enumerate(nodes):
        base=struct.unpack_from('<h',r,16)[0];degree=r[24]&15
        if base<0 or base+degree>l:raise TrafficError(f'LINK_RANGE: node {i}')
        if struct.unpack_from('<H',r,20)[0]!=i:raise TrafficError(f'NODE_ID: record {i}')
    return Area(counts,nodes,navis,links,nl,d,inter,rl,rd,ri,data[pos:])

def position(raw): return [v/8 for v in struct.unpack_from('<3h',raw,8)]
