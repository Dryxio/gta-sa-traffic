"""Independent exported-byte verifier. Does not use the production codec."""
import struct

def check(files):
    errors=[];warnings=[];areas={}
    for area,data in files.items():
        if len(data)<20:errors.append(f'{area}:short header');continue
        n,v,p,nv,l=struct.unpack_from('<5I',data)
        end=20+n*28+nv*14+(l*8+1152 if l else 0)
        if end>len(data) or n!=v+p:errors.append(f'{area}:size/counts');continue
        nodes=[]
        for i in range(n):
            r=20+28*i;xyz=struct.unpack_from('<3h',data,r+8);base,a,j=struct.unpack_from('<hHH',data,r+16);degree=data[r+24]&15
            if a!=area or j!=i:errors.append(f'{area}:{i}:identity')
            if base<0 or base+degree>l:errors.append(f'{area}:{i}:link range')
            nodes.append(dict(xyz=xyz,base=base,degree=degree,flood=data[r+23],vehicle=i<v))
        no=20+n*28;navs=[]
        for i in range(nv):
            r=no+14*i;target=struct.unpack_from('<HH',data,r+4);lanes=data[r+11];navs.append((target,lanes&7,(lanes>>3)&7))
        lo=no+nv*14;nlo=lo+4*(l+192);dl=nlo+2*l
        links=[struct.unpack_from('<HH',data,lo+4*i) for i in range(l)]
        nl=[struct.unpack_from('<H',data,nlo+2*i)[0] for i in range(l)]
        distances=data[dl:dl+l] if l else b''
        areas[area]=(nodes,navs,links,nl,distances)
    for a,(nodes,navs,links,nl,distances) in areas.items():
        for i,node in enumerate(nodes):
            for k in range(node['base'],node['base']+node['degree']):
                if not 0<=k<len(links):continue
                ta,ti=links[k]
                if ta not in areas or ti>=len(areas[ta][0]):errors.append(f'{a}:{i}:unresolved target {ta}:{ti}');continue
                other=areas[ta][0][ti]
                if node['vehicle']!=other['vehicle']:errors.append(f'{a}:{i}:mixed class')
                if node['vehicle']:
                    na,ni=nl[k]>>10,nl[k]&1023
                    if na not in areas or ni>=len(areas[na][1]):errors.append(f'{a}:{i}:unresolved navi');continue
                    target,low,high=areas[na][1][ni]
                    if target not in [(a,i),(ta,ti)]:warnings.append(f'{a}:{i}:exceptional attached navi')
                    if node['flood']!=other['flood']:errors.append(f'{a}:{i}:flood mismatch')
                    if distances[k]==0:warnings.append(f'{a}:{i}:zero distance')
        for i,(target,low,high) in enumerate(navs):
            ta,ti=target
            if ta not in areas or ti>=len(areas[ta][0]):errors.append(f'{a}:navi{i}:unresolved attached')
    return dict(valid=not errors,errors=errors,warnings=warnings,areas=len(areas),scope='independent byte topology; no engine or collision simulation')
