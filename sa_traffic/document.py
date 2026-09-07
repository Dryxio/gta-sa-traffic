"""Versioned author graph, imports, transactions and explicit road expansion."""
import base64,copy,hashlib,json,math,struct
from pathlib import Path
from .codec import decode,position,TrafficError

def fingerprint(doc):
    return hashlib.sha256(json.dumps({k:v for k,v in doc.items() if k!='revision'},sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def seal(doc): doc['revision']=fingerprint(doc);return doc
def empty():return seal(dict(schema_version=1,profile='sa_compact',nodes=[],edges=[],routes=[],navis=[],sources={},junctions=[],signals=[]))
def import_files(paths):
    doc=empty();areas={};ids={};navids={}
    for path in sorted(map(Path,paths)):
        try:a=int(path.stem.lower().removeprefix('nodes'))
        except ValueError:raise TrafficError(f'AREA_NAME: {path}')
        if not 0<=a<64 or a in areas:raise TrafficError(f'AREA_ID: {a}')
        b=path.read_bytes();area=decode(b);areas[a]=area
        digest=hashlib.sha256(b).hexdigest();doc['sources'][str(a)]={'path':str(path.resolve()),'sha256':digest,'bytes':base64.b64encode(b).decode()}
        for i,r in enumerate(area.nodes):
            if struct.unpack_from('<H',r,18)[0]!=a:raise TrafficError(f'AREA_ID: node {a}:{i}')
            uid=f'src:{digest[:16]}:{a}:{i}';ids[a,i]=uid
            doc['nodes'].append(dict(id=uid,position=position(r),kind='vehicle' if i<area.counts[1] else 'pedestrian',origin=[a,i],raw=r.hex()))
        for i,r in enumerate(area.navis):
            uid=f'navi:{digest[:16]}:{a}:{i}';navids[a,i]=uid
    for a,area in areas.items():
        for i,r in enumerate(area.navis):
            target=struct.unpack_from('<HH',r,4)
            doc['navis'].append(dict(id=navids[a,i],origin=[a,i],raw=r.hex(),attached=ids.get(target),external_attached=list(target) if target not in ids else None))
        for i,r in enumerate(area.nodes):
            base=struct.unpack_from('<h',r,16)[0]
            for k in range(base,base+(r[24]&15)):
                target=area.links[k];packed=area.navi_links[k]
                doc['edges'].append(dict(id=f'edge:{a}:{i}:{k}',source=ids[a,i],target=ids.get(target),external_target=list(target) if target not in ids else None,navi=navids.get((packed>>10,packed&1023)) if i<area.counts[1] else None,original_navi=packed,distance=area.distances[k],intersection=area.intersections[k]))
    doc['import_graph_hash']=graph_hash(doc)
    return seal(doc)

def graph_hash(doc):
    return hashlib.sha256(json.dumps({k:doc.get(k,[]) for k in ('nodes','edges','navis','routes','junctions','signals')},sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def apply(doc,transaction):
    if transaction.get('base_revision')!=fingerprint(doc):raise TrafficError('REVISION_CONFLICT: transaction base differs')
    result=copy.deepcopy(doc)
    for op in transaction.get('operations',[]):
        action=op.get('op');kind=op.get('collection','nodes')
        if kind not in ('nodes','edges','navis','routes','junctions','signals'):raise TrafficError('COLLECTION: unsupported')
        items=result[kind];uid=op.get('id');index=next((i for i,x in enumerate(items) if x['id']==uid),None)
        if action=='add':
            value=copy.deepcopy(op['value'])
            if any(x['id']==value['id'] for x in items):raise TrafficError('DUPLICATE_ID: '+value['id'])
            items.append(value)
        elif action=='update':
            if index is None:raise TrafficError('MISSING_ID: '+str(uid))
            if 'id' in op['changes']:raise TrafficError('IMMUTABLE_ID')
            items[index].update(copy.deepcopy(op['changes']))
        elif action=='remove':
            if index is None:raise TrafficError('MISSING_ID: '+str(uid))
            if kind=='nodes' and (any(e.get('source')==uid or e.get('target')==uid for e in result['edges']) or any(n.get('attached')==uid for n in result['navis']) or any(r.get('start_node')==uid or r.get('end_node')==uid for r in result['routes']) or any(p.get('entry_node')==uid or p.get('exit_node')==uid for j in result.get('junctions',[]) for p in j.get('ports',[])) or any(s.get('toward_node')==uid for s in result.get('signals',[]))):raise TrafficError('REFERENCED_NODE: disconnect edges, navis and routes first')
            if kind=='navis' and (any(e.get('navi')==uid for e in result['edges']) or any(s.get('navi')==uid for s in result.get('signals',[]))):raise TrafficError('REFERENCED_NAVI: disconnect first')
            if kind=='routes' and any(str(s.get('segment','')).startswith('route:'+uid+':segment:') for s in result.get('signals',[])):raise TrafficError('REFERENCED_ROUTE: remove signal first')
            del items[index]
        else:raise TrafficError('OPERATION: unsupported')
    return seal(result)

def expand_routes(doc):
    """Explicit polylines only. No spatial joining; endpoints require explicit IDs."""
    from .controls import lower_junctions
    result=lower_junctions(doc);known={n['id']:n for n in result['nodes']}
    for route in sorted(result.get('routes',[]),key=lambda r:r['id']):
        allowed={'id','points','spacing','lanes_forward','lanes_backward','start_node','end_node','node_width','navi_width','spawn_probability','behaviour','metadata'}
        unknown=set(route)-allowed
        if unknown:raise TrafficError('ROUTE_FIELDS: unsupported '+','.join(sorted(unknown)))
        rid=route['id'];points=route['points'];step=route.get('spacing',20.)
        if type(step) not in (int,float) or not math.isfinite(step) or step<=0:raise TrafficError('ROUTE_SPACING: '+rid)
        if len(points)<2:raise TrafficError('ROUTE_POINTS: '+rid)
        lf,lb=route.get('lanes_forward'),route.get('lanes_backward')
        if any(type(x)!=int or not 0<=x<=7 for x in (lf,lb)) or lf+lb==0:raise TrafficError('LANES: '+rid)
        if any(not isinstance(p,list) or len(p)!=3 or not all(type(v) in (int,float) and math.isfinite(v) for v in p) for p in points):raise TrafficError('POSITION: '+rid)
        generated=[]
        for j,(a,b) in enumerate(zip(points,points[1:])):
            length=math.dist(a,b)
            if length<.125:raise TrafficError('ZERO_SEGMENT: '+rid)
            count=math.ceil(length/step)
            if count>100000:raise TrafficError('ROUTE_CAPACITY: '+rid)
            for k in range(count):generated.append([a[d]+(b[d]-a[d])*k/count for d in range(3)])
        generated.append(points[-1]);route_nodes=[]
        for j,p in enumerate(generated):
            uid=route.get('start_node') if j==0 else route.get('end_node') if j==len(generated)-1 else None
            uid=uid or f'route:{rid}:node:{j:06d}'
            if uid in known:
                if math.dist(known[uid]['position'],p)>.125:raise TrafficError('ENDPOINT_MISMATCH: '+uid)
            else:
                if uid in (route.get('start_node'),route.get('end_node')):raise TrafficError('MISSING_ENDPOINT: '+uid)
                n=dict(id=uid,position=p,kind='vehicle',width=route.get('node_width',0),spawn_probability=route.get('spawn_probability',15),behaviour=route.get('behaviour',0));known[uid]=n;result['nodes'].append(n)
            route_nodes.append(uid)
        for j,(a,b) in enumerate(zip(route_nodes,route_nodes[1:])):
            common=dict(segment=f'route:{rid}:segment:{j:06d}',lanes_forward=lf,lanes_backward=lb,navi_width=route.get('navi_width',0),route=rid)
            # Both adjacency arcs retained; navi lane counts control permitted travel.
            result['edges'].extend([dict(id=f'{common["segment"]}:forward',source=a,target=b,orientation=1,**common),dict(id=f'{common["segment"]}:backward',source=b,target=a,orientation=-1,**common)])
    result['routes']=[]
    return result
