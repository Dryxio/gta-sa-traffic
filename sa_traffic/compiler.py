"""Global compiler for explicitly authored roads; no legacy-editor dependencies."""
import base64,hashlib,math,struct,copy
from collections import defaultdict
from .codec import Area,decode,TrafficError,position
from .document import expand_routes,graph_hash
from .controls import junction_contract,verify_junction_reachability,movement_conflicts
from .signals import apply_signals,verify_signal_bytes

PROFILE='sa_compact'
def region(p):return min(7,max(0,int((p[0]+3000)/750)))+8*min(7,max(0,int((p[1]+3000)/750)))
def quant(v,scale,lo,hi,label):
    if type(v) not in (int,float) or not math.isfinite(v):raise TrafficError('NONFINITE: '+label)
    q=round(v*scale)
    if not lo<=q<=hi:raise TrafficError('RANGE: '+label)
    return q

def validate(document):
    diagnostics=[]
    def error(code,uid,message):diagnostics.append(dict(severity='error',code=code,id=uid,message=message))
    if not isinstance(document,dict):error('SCHEMA',None,'Expected JSON object');return diagnostics
    for name in ('nodes','edges','navis','routes'):
        if not isinstance(document.get(name,[]),list) or any(not isinstance(x,dict) for x in document.get(name,[])):error('COLLECTION',name,'Expected array of objects')
    if not isinstance(document.get('sources',{}),dict):error('SOURCES',None,'Expected mapping')
    if diagnostics:return diagnostics
    if document.get('schema_version')!=1:error('SCHEMA',None,'Expected schema_version 1')
    if document.get('profile')!=PROFILE:error('PROFILE',None,'Backend not implemented; document coordinates are not changed')
    policies=document.get('policies',{})
    if not isinstance(policies,dict) or set(policies)-{'merge_flood_components','signal_conflicts'} or ('merge_flood_components' in policies and type(policies['merge_flood_components'])!=bool) or policies.get('signal_conflicts','report') not in ('report','reject'):error('POLICY',None,'Unknown policy or invalid policy value')
    try:d=expand_routes(document)
    except (TrafficError,KeyError,TypeError) as exc:error('ROUTES',None,str(exc));return diagnostics
    nodes={};edges={};navis={}
    for collection,lookup in [('nodes',nodes),('edges',edges),('navis',navis)]:
        for item in d.get(collection,[]):
            uid=item.get('id')
            if not isinstance(uid,str) or not uid:error('ID',None,'Expected nonempty stable string');continue
            if uid in lookup:error('DUPLICATE_ID',uid,collection)
            lookup[uid]=item
    allowed_fields={'nodes':{'id','position','kind','origin','raw','width','spawn_probability','behaviour','metadata'},'edges':{'id','source','target','external_target','navi','original_navi','distance','intersection','segment','orientation','lanes_forward','lanes_backward','navi_width','route','metadata'},'navis':{'id','origin','raw','attached','external_attached','metadata'}}
    for collection,lookup in [('nodes',nodes),('edges',edges),('navis',navis)]:
        for uid,item in lookup.items():
            unknown=set(item)-allowed_fields[collection]
            if unknown:error('UNKNOWN_FIELDS',uid,','.join(sorted(unknown)))
    for uid,n in nodes.items():
        p=n.get('position')
        if not isinstance(p,list) or len(p)!=3 or not all(type(x) in (int,float) and math.isfinite(x) for x in p):error('POSITION',uid,'Expected finite XYZ');continue
        if 'raw' in n:
            try:
                if len(bytes.fromhex(n['raw']))!=28:raise ValueError('length')
            except (ValueError,TypeError):error('RAW_RECORD',uid,'Expected 28 bytes hex')
        if 'origin' in n and (not isinstance(n['origin'],list) or len(n['origin'])!=2 or any(type(x)!=int for x in n['origin']) or not 0<=n['origin'][0]<64 or not 0<=n['origin'][1]<65536):error('ORIGIN',uid,'Invalid source address')
        if n.get('kind') not in ('vehicle','pedestrian'):error('KIND',uid,'Unsupported generated node class')
        try:
            for v in p:quant(v,8,-32768,32767,uid)
        except TrafficError as e:error('CAPACITY',uid,str(e))
        if n.get('movements') or n.get('traffic_lights'):error('UNSUPPORTED_SEMANTICS',uid,'New turn restrictions / traffic lights require verified backend rules')
    degree=defaultdict(int)
    for uid,e in edges.items():
        if any(e.get(side) is not None and not isinstance(e.get(side),str) for side in ('source','target','navi')):error('REFERENCE_TYPE',uid,'Expected stable string reference');continue
        for side in ('source','target'):
            if e.get(side) not in nodes:error('MISSING_REFERENCE',uid,side+' is unresolved; load referenced regions')
        if e.get('source') in nodes and e.get('target') in nodes:
            a,b=nodes[e['source']],nodes[e['target']]
            if a.get('kind')!=b.get('kind'):error('MIXED_CLASS',uid,'Vehicle/pedestrian connection')
            if e['source']==e['target']:error('SELF_LINK',uid,'Self edge')
            degree[e['source']]+=1
        if e.get('navi') and e['navi'] not in navis:error('MISSING_NAVI',uid,'Navi ID unresolved')
        if not e.get('navi') and 'original_navi' not in e and not e.get('segment'):error('SEGMENT_REQUIRED',uid,'New edges require explicit segment and lane metadata')
    for uid,count in degree.items():
        if count>15:error('DEGREE',uid,'Compact supports at most 15 outgoing adjacency links')
    for uid,navi in navis.items():
        try:
            if len(bytes.fromhex(navi['raw']))!=14:raise ValueError('length')
        except (KeyError,ValueError,TypeError):error('RAW_NAVI',uid,'Expected 14 bytes hex')
        if not isinstance(navi.get('origin'),list) or len(navi['origin'])!=2 or any(type(x)!=int for x in navi['origin']) or not 0<=navi['origin'][0]<64:error('NAVI_ORIGIN',uid,'Invalid navi source address')
        if not isinstance(navi.get('attached'),str) or navi.get('attached') not in nodes:error('MISSING_NAVI_TARGET',uid,'Load referenced region or remove orphan navi explicitly')
    return diagnostics

def compile_document(document):
    errors=validate(document)
    if errors:raise TrafficError('; '.join(f'{x["code"]}:{x["id"]}: {x["message"]}' for x in errors))
    d=expand_routes(document);nodes={n['id']:n for n in d['nodes']};groups=defaultdict(list);sources={}
    for n in nodes.values():
        n['position']=[quant(v,8,-32768,32767,n['id'])/8 for v in n['position']]
        n['_position_changed']=bool(n.get('raw') and n['position']!=position(bytes.fromhex(n['raw'])))
    for a,s in d.get('sources',{}).items():
        b=base64.b64decode(s['bytes'],validate=True)
        if hashlib.sha256(b).hexdigest()!=s['sha256']:raise TrafficError('SOURCE_HASH: '+a)
        sources[int(a)]=decode(b)
    for n in nodes.values():
        if 'raw' in n:
            a,i=n.get('origin',[-1,-1]);source=sources.get(a)
            if source is None or not 0<=i<len(source.nodes) or bytes.fromhex(n['raw'])!=source.nodes[i]:raise TrafficError('RAW_PROVENANCE: node '+n['id'])
        elif 'origin' in n:raise TrafficError('RAW_PROVENANCE: origin without source node')
        a=n['origin'][0] if n.get('raw') and not n['_position_changed'] else region([quant(v,8,-32768,32767,n['id'])/8 for v in n['position']])
        groups[a].append(n)
    def order(n):return (n['kind']!='vehicle',0 if 'origin'in n else 1,n.get('origin',[0,0]),n['id'])
    addresses={}
    for a,ns in groups.items():
        ns.sort(key=order)
        if len(ns)>65536:raise TrafficError('CAPACITY: nodes per region')
        for i,n in enumerate(ns):addresses[n['id']]=(a,i)
    edges=defaultdict(list)
    for e in d['edges']:edges[e['source']].append(e)
    # Keep source order; new edges sorted by stable ID for deterministic output.
    for uid in edges:edges[uid].sort(key=lambda e:(0 if 'original_navi'in e else 1,e['id'] if 'original_navi'not in e else int(e['id'].rsplit(':',1)[1])))
    navis_by_area=defaultdict(list);navi_addresses={};navi_records={}
    for navi in sorted(d.get('navis',[]),key=lambda x:x['origin']):
        raw=bytearray.fromhex(navi['raw']);attached=navi['attached'];a,i=navi['origin'];source=sources.get(a)
        if source is None or not 0<=i<len(source.navis) or bytes(raw)!=source.navis[i]:raise TrafficError('RAW_PROVENANCE: navi '+navi['id'])
        struct.pack_into('<HH',raw,4,*addresses[attached])
        navi_addresses[navi['id']]=(a,len(navis_by_area[a]));navis_by_area[a].append(raw);navi_records[navi['id']]=navi
    segment_edges=defaultdict(list)
    imported_navi_edges=defaultdict(list)
    for e in d['edges']:
        if e.get('segment'):segment_edges[e['segment']].append(e)
        elif e.get('navi'):
            imported_navi_edges[e['navi']].append(e)
    for key,es in imported_navi_edges.items():
        endpoints={u for e in es for u in (e['source'],e['target'])}
        moved=any(nodes[u].get('raw') and nodes[u]['position']!=position(bytes.fromhex(nodes[u]['raw'])) for u in endpoints)
        attached=navi_records[key]['attached']
        canonical=min(endpoints,key=lambda uid:addresses[uid])
        flip=len(endpoints)==2 and attached in endpoints and canonical!=attached
        if flip:
            na,ni=navi_addresses[key];raw=navis_by_area[na][ni];lanes=raw[11];raw[11]=((lanes&192)^(64 if raw[12]&3 else 0))|((lanes&7)<<3)|((lanes>>3)&7)
            dx,dy=struct.unpack_from('<bb',raw,8);struct.pack_into('<bb',raw,8,-dx,-dy);struct.pack_into('<HH',raw,4,*addresses[canonical]);attached=canonical
        if not moved:continue
        if len(endpoints)!=2 or attached not in endpoints:raise TrafficError('REAUTHOR_SEGMENT: exceptional imported navi '+key)
        other=next(u for u in endpoints if u!=attached);pa,pb=nodes[other]['position'],nodes[attached]['position']
        dx,dy=pb[0]-pa[0],pb[1]-pa[1];length=math.hypot(dx,dy)
        if length<.125:raise TrafficError('VERTICAL_OR_ZERO_ROAD: '+key)
        na,ni=navi_addresses[key];raw=navis_by_area[na][ni]
        struct.pack_into('<hh',raw,0,quant((pa[0]+pb[0])/2,8,-32768,32767,'navi x'),quant((pa[1]+pb[1])/2,8,-32768,32767,'navi y'))
        struct.pack_into('<bb',raw,8,quant(dx/length,100,-127,127,'dir x'),quant(dy/length,100,-127,127,'dir y'))
        for e in es:e.pop('distance',None)
    for segment,es in sorted(segment_edges.items()):
        if len(es)!=2 or es[0]['source']!=es[1]['target'] or es[1]['source']!=es[0]['target']:raise TrafficError('SEGMENT_PAIR: '+segment)
        forward=next((e for e in es if e.get('orientation')==1),None)
        if forward is None:raise TrafficError('SEGMENT_ORIENTATION: '+segment)
        backward=next((e for e in es if e.get('orientation')==-1),None)
        if backward is None or any(forward.get(k)!=backward.get(k) for k in ('lanes_forward','lanes_backward','navi_width')):raise TrafficError('SEGMENT_METADATA: inconsistent reciprocal edges '+segment)
        u,v=forward['source'],forward['target'];pa,pb=nodes[u]['position'],nodes[v]['position'];dx,dy=pb[0]-pa[0],pb[1]-pa[1];length=math.hypot(dx,dy)
        if length<.125:raise TrafficError('VERTICAL_OR_ZERO_ROAD: '+segment)
        lf,lb=forward['lanes_forward'],forward['lanes_backward']
        if any(type(x)!=int or not 0<=x<=7 for x in (lf,lb)) or lf+lb==0:raise TrafficError('LANES: '+segment)
        # Canonical attached endpoint; bits low=toward attached, high=away.
        attached=min((u,v),key=lambda uid:addresses[uid]);toward=lf if attached==v else lb;away=lb if attached==v else lf
        if attached==u:dx,dy=-dx,-dy
        area=addresses[attached][0];idx=len(navis_by_area[area]);navi_addresses[segment]=(area,idx)
        width=quant(forward.get('navi_width',0),16,0,255,'navi width')
        raw=struct.pack('<hhHHbbBBH',quant((pa[0]+pb[0])/2,8,-32768,32767,'navi x'),quant((pa[1]+pb[1])/2,8,-32768,32767,'navi y'),*addresses[attached],quant(dx/length,100,-127,127,'dir x'),quant(dy/length,100,-127,127,'dir y'),width,toward|(away<<3),0)
        navis_by_area[area].append(raw)
        for e in es:e['_compiled_navi']=segment
    for a,navs in navis_by_area.items():
        if len(navs)>1024:raise TrafficError('CAPACITY: navi nodes >1024 in region '+str(a))
    signal_report=apply_signals(document,navis_by_area,navi_addresses,addresses,d['edges'])
    # Flood labels are derived on the complete vehicle topology, avoiding arbitrary
    # unrelated labels. Imported labels anchor components; conflicting anchors fail.
    neighbors=defaultdict(set)
    for e in d['edges']:neighbors[e['source']].add(e['target']);neighbors[e['target']].add(e['source'])
    unseen=set(nodes);flood={};used={bytes.fromhex(n['raw'])[23] for n in nodes.values() if n.get('raw')}
    while unseen:
        seed=min(unseen);stack=[seed];component=set()
        while stack:
            u=stack.pop()
            if u in component:continue
            component.add(u);unseen.discard(u);stack.extend(neighbors[u]-component)
        anchors={bytes.fromhex(nodes[u]['raw'])[23] for u in component if nodes[u].get('raw')}
        new=[u for u in component if not nodes[u].get('raw')]
        if len(anchors)>1:
            if not d.get('policies',{}).get('merge_flood_components',False):raise TrafficError('FLOOD_CONFLICT: enable explicit merge_flood_components policy')
            label=min(anchors)
            for u in component:nodes[u]['_flood_override']=label
            anchors={label}
        if not new:continue
        if anchors:label=next(iter(anchors))
        else:
            label=next((i for i in range(1,256) if i not in used),None)
            if label is None:raise TrafficError('CAPACITY: flood labels')
            used.add(label)
        for u in new:flood[u]=label
    outputs={};changed=[]
    for a in sorted(set(groups)|set(sources)|set(navis_by_area)):
        ns=groups[a];records=[];links=[];nl=[];dist=[];inter=[]
        for i,n in enumerate(ns):
            es=edges[n['id']];raw=bytearray.fromhex(n['raw']) if n.get('raw') else bytearray(28)
            if not n.get('raw'):
                if n['kind']!='vehicle':raise TrafficError('GENERATION_CLASS: only road vehicles implemented')
                spawn=n.get('spawn_probability',15);behaviour=n.get('behaviour',0)
                if type(spawn)!=int or not 0<=spawn<=15 or type(behaviour)!=int or not 0<=behaviour<=15:raise TrafficError('FLAGS_RANGE')
                struct.pack_into('<h',raw,14,32766);raw[22]=quant(n.get('width',0),16,0,255,'path width');raw[23]=flood[n['id']]
                struct.pack_into('<I',raw,24,(spawn<<16)|(behaviour<<20)|0x1000)
            if '_flood_override' in n:raw[23]=n['_flood_override']
            if 'width' in n:raw[22]=quant(n['width'],16,0,255,'path width')
            if 'spawn_probability' in n or 'behaviour' in n:
                spawn=n.get('spawn_probability',raw[26]&15);behaviour=n.get('behaviour',raw[26]>>4)
                if type(spawn)!=int or not 0<=spawn<=15 or type(behaviour)!=int or not 0<=behaviour<=15:raise TrafficError('FLAGS_RANGE')
                raw[26]=spawn|(behaviour<<4)
            struct.pack_into('<3h',raw,8,*(quant(x,8,-32768,32767,n['id']) for x in n['position']))
            if len(links)>32767:raise TrafficError('CAPACITY: signed base link index')
            struct.pack_into('<hHH',raw,16,len(links),a,i);raw[24]=(raw[24]&240)|len(es);records.append(bytes(raw))
            for e in es:
                links.append(addresses[e['target']]);key=e.get('_compiled_navi') or e.get('navi')
                if key:
                    na,ni=navi_addresses[key];nl.append((na<<10)|ni)
                else:nl.append(e.get('original_navi',0))
                distance=e.get('distance')
                if distance is None:
                    length=math.dist(n['position'],nodes[e['target']]['position'])
                    if length<.125:raise TrafficError('QUANTIZED_ZERO_SEGMENT: '+e['id'])
                    distance=max(1,math.floor(length))
                if type(distance)!=int or not 0<=distance<=255:raise TrafficError('DISTANCE_RANGE: subdivide '+e['id'])
                dist.append(distance);inter.append(e.get('intersection',0))
        old=sources.get(a);l=len(links)
        if l>32768:raise TrafficError('CAPACITY: link array')
        area=Area((len(ns),sum(n['kind']=='vehicle' for n in ns),sum(n['kind']=='pedestrian' for n in ns),len(navis_by_area[a]),l),records,[bytes(x) for x in navis_by_area[a]],links,nl,bytes(dist),bytes(inter),old.reserved_links if old and old.counts[4] and l else bytes(768) if l else b'',old.reserved_distances if old and old.counts[4] and l else bytes(192) if l else b'',old.reserved_intersections if old and old.counts[4] and l else bytes(192) if l else b'',old.trailing if old else b'')
        b=area.encode();decode(b);outputs[a]=b
        if old is None or b!=old.encode():changed.append(a)
    junction_checks=verify_junction_reachability(document,outputs,addresses)
    control_report=junction_contract(document);control_report['signals']=signal_report;control_report['signal_verification']=verify_signal_bytes(signal_report,outputs);control_report['movement_conflicts']=movement_conflicts(document,signal_report)
    return outputs,dict(navi_mapping={k:list(v) for k,v in navi_addresses.items()},controls=control_report,junction_validation=junction_checks,profile=PROFILE,changed_regions=changed,mapping={k:list(v) for k,v in addresses.items()},diagnostics=[],engine_validation='pending',geometry_validation='unchecked_by_compiler; use Blender surface report',generation_policy='explicit roads/connectors; midpoint navis; floor 3D costs; native two-group signals')
