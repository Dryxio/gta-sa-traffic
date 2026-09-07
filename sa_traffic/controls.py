"""Explicit junction authoring contracts; never invents native turn-table flags."""
import copy,math,hashlib,json
from .codec import TrafficError


def lower_junctions(document):
    """Encode approach memory as separate entry/exit ports and one-way connectors.

    This is navigation topology, not a guarantee against native wandering fallback.
    Strict restrictions require an approach-aware runtime, and are refused here.
    """
    doc=copy.deepcopy(document);junctions=doc.get('junctions',[])
    if not isinstance(junctions,list):raise TrafficError('JUNCTIONS: expected array')
    digest=hashlib.sha256(json.dumps(junctions,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    if doc.get('junctions_lowered_sha256'):
        if doc['junctions_lowered_sha256']!=digest:raise TrafficError('JUNCTIONS_CHANGED_AFTER_LOWER: edit the author document and expand again')
        return doc
    nodes={n['id']:n for n in doc.get('nodes',[])};seen=set()
    for j in junctions:
        if not isinstance(j,dict) or set(j)-{'id','ports','movements','enforcement','metadata'}:raise TrafficError('JUNCTION_FIELDS')
        jid=j.get('id')
        if not isinstance(jid,str) or not jid or jid in seen:raise TrafficError('JUNCTION_ID')
        seen.add(jid)
        if j.get('enforcement')!='native_navigation':
            raise TrafficError('TURN_RUNTIME_REQUIRED: strict approach-dependent restrictions cannot be guaranteed by compact NODES; select native_navigation explicitly or an implemented runtime adapter')
        ports={};port_nodes=set()
        for p in j.get('ports',[]):
            if not isinstance(p,dict) or set(p)-{'id','entry_node','exit_node','metadata'}:raise TrafficError('PORT_FIELDS: '+jid)
            pid=p.get('id');entry,exit_=p.get('entry_node'),p.get('exit_node')
            if not isinstance(pid,str) or not pid or pid in ports:raise TrafficError('PORT_ID: '+jid)
            if entry not in nodes or exit_ not in nodes or entry==exit_:raise TrafficError('PORT_NODES: distinct existing entry/exit required')
            if entry in port_nodes or exit_ in port_nodes:raise TrafficError('PORT_ALIAS: ports must retain separate identities')
            if nodes[entry].get('kind')!='vehicle' or nodes[exit_].get('kind')!='vehicle':raise TrafficError('PORT_CLASS')
            ports[pid]=p;port_nodes.update((entry,exit_))
        if len(ports)<2:raise TrafficError('PORT_COUNT: at least two approaches')
        pairs=set();outgoing=set()
        for m in j.get('movements',[]):
            if not isinstance(m,dict) or set(m)-{'from','to','points','spacing','metadata'}:raise TrafficError('MOVEMENT_FIELDS: '+jid)
            src,dst=m.get('from'),m.get('to')
            if src not in ports or dst not in ports or (src,dst) in pairs:raise TrafficError('MOVEMENT_REFERENCE: '+jid)
            pairs.add((src,dst));outgoing.add(src)
            points=m.get('points')
            if not isinstance(points,list) or len(points)<2:raise TrafficError('MOVEMENT_POINTS: explicitly author connector geometry')
            a,b=ports[src]['entry_node'],ports[dst]['exit_node']
            for point,uid in ((points[0],a),(points[-1],b)):
                if not isinstance(point,list) or len(point)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) for v in point):raise TrafficError('MOVEMENT_POSITION')
                if math.dist(point,nodes[uid]['position'])>.125:raise TrafficError('MOVEMENT_ENDPOINT: '+uid)
            doc.setdefault('routes',[]).append(dict(id=f'junction:{jid}:{src}->{dst}',points=points,start_node=a,end_node=b,lanes_forward=1,lanes_backward=0,spacing=m.get('spacing',10),navi_width=0,node_width=0,metadata={'junction':jid,'movement':[src,dst],'semantics':'native_navigation; wandering fallback may reverse'}))
        if outgoing!=set(ports):raise TrafficError('MOVEMENT_DEAD_APPROACH: every entry requires an exit; dead ends invite native fallback')
    if junctions:doc['junctions_lowered_sha256']=digest
    return doc


def junction_contract(document):
    return {'version':1,'native_semantics':'directed connector reachability only; native wandering fallback can reverse',
            'junctions':[{'id':j['id'],'enforcement':j['enforcement'],'ports':j['ports'],'allowed_movements':[[m['from'],m['to']] for m in j['movements']]} for j in document.get('junctions',[])],
            'strict_runtime_required':False,'engine_validation':'pending'}


def verify_junction_reachability(document,files,mapping):
    """Byte oracle: decode permitted arcs independently, stop at first exit port."""
    import struct
    graph={};nodes={};navis={};records={}
    for area,b in files.items():
        n,v,p,nv,l=struct.unpack_from('<5I',b);off=20+28*n;lo=off+14*nv;nlo=lo+4*(l+192)
        for i in range(nv):
            r=off+14*i;navis[area,i]=(struct.unpack_from('<HH',b,r+4),b[r+11]&7,(b[r+11]>>3)&7)
        for i in range(n):
            base=struct.unpack_from('<h',b,20+i*28+16)[0];degree=b[20+i*28+24]&15;adj=[]
            for k in range(base,base+degree):
                target=struct.unpack_from('<HH',b,lo+4*k);packed=struct.unpack_from('<H',b,nlo+2*k)[0];adj.append((target,(packed>>10,packed&1023)))
            records[area,i]=adj
    for source,adj in records.items():
        graph[source]=[]
        for target,key in adj:
            attached,toward,away=navis.get(key,(None,0,0))
            if (toward if target==attached else away)>0:graph[source].append(target)
    reports=[]
    for j in document.get('junctions',[]):
        ports={p['id']:p for p in j['ports']};exits={tuple(mapping[p['exit_node']]):pid for pid,p in ports.items()}
        allowed={(m['from'],m['to']) for m in j['movements']};internal={tuple(addr) for uid,addr in mapping.items() if uid.startswith(f'route:junction:{j["id"]}:')}
        internal.update(tuple(mapping[p[side]]) for p in ports.values() for side in ('entry_node','exit_node'))
        # A bypass through an old shared junction must not disappear from the oracle.
        entries={tuple(mapping[p['entry_node']]) for p in ports.values()}
        for source,targets in graph.items():
            for target in targets:
                if source in internal and target not in internal and source not in exits:raise TrafficError('JUNCTION_LEAK_OUT: '+j['id'])
                if source not in internal and target in internal and target not in entries:raise TrafficError('JUNCTION_LEAK_IN: '+j['id'])
        actual=set()
        for pid,p in ports.items():
            start=tuple(mapping[p['entry_node']]);todo=[start];visited=set()
            while todo:
                at=todo.pop()
                if at in visited:continue
                visited.add(at)
                if at in exits:actual.add((pid,exits[at]));continue
                todo.extend(x for x in graph.get(at,[]) if x in internal and x not in visited)
        missing=sorted(allowed-actual);unwanted=sorted(actual-allowed)
        if missing or unwanted:raise TrafficError(f'JUNCTION_REACHABILITY: {j["id"]}: missing={missing}, unwanted={unwanted}')
        reports.append(dict(id=j['id'],allowed=sorted(allowed),actual=sorted(actual),scope='first exit reachability inside connector topology; not all native AI strategies'))
    return reports


def movement_conflicts(document,signals):
    """Detect potential geometric crossing, including Z; not a vehicle simulator."""
    groups={}
    for signal in signals:
        a=signal.get('approach')
        if a:
            key=(a['junction'],a['port']);value=signal['phase_group']
            if key in groups and groups[key]!=value:raise TrafficError('APPROACH_PHASE_CONFLICT')
            groups[key]=value
    reports=[]
    def crossing(a,b,c,d):
        ux,uy=b[0]-a[0],b[1]-a[1];vx,vy=d[0]-c[0],d[1]-c[1];den=ux*vy-uy*vx
        if abs(den)<1e-9:
            # Collinear overlap: sample an interior overlap point instead of ignoring it.
            if abs((c[0]-a[0])*uy-(c[1]-a[1])*ux)>1e-7:return None
            uu=ux*ux+uy*uy;vv=vx*vx+vy*vy
            if uu<1e-9 or vv<1e-9:return None
            ts=[((p[0]-a[0])*ux+(p[1]-a[1])*uy)/uu for p in (c,d)]
            lo,hi=max(0,min(ts)),min(1,max(ts))
            if hi-lo<1e-6:return None
            t=(lo+hi)/2;x,y=a[0]+t*ux,a[1]+t*uy;s=((x-c[0])*vx+(y-c[1])*vy)/vv
        else:
            t=((c[0]-a[0])*vy-(c[1]-a[1])*vx)/den;s=((c[0]-a[0])*uy-(c[1]-a[1])*ux)/den
            if not (-1e-7<=t<=1+1e-7 and -1e-7<=s<=1+1e-7):return None
            x,y=a[0]+t*ux,a[1]+t*uy
        za=a[2]+t*(b[2]-a[2]);zb=c[2]+s*(d[2]-c[2])
        if abs(za-zb)>2.:return None # explicit diagnostic clearance, not a native rule
        return [x,y,(za+zb)/2]
    for j in document.get('junctions',[]):
        moves=j['movements'];seen=set()
        for i,a in enumerate(moves):
            for b in moves[i+1:]:
                if a['from']==b['from'] or a['to']==b['to']:continue # shared entry/exit following or merge, separate warning below
                for p,q in zip(a['points'],a['points'][1:]):
                    for r,s in zip(b['points'],b['points'][1:]):
                        pos=crossing(p,q,r,s)
                        if pos is None:continue
                        pair=((a['from'],a['to']),(b['from'],b['to']))
                        if pair in seen:continue
                        seen.add(pair);ga=groups.get((j['id'],a['from']));gb=groups.get((j['id'],b['from']))
                        risk='same_green_phase' if ga is not None and ga==gb else 'uncontrolled_approach' if ga is None or gb is None else 'separated_green_phases'
                        reports.append(dict(junction=j['id'],movements=pair,position=pos,phase_groups=[ga,gb],status=risk,severity='warning' if risk!='separated_green_phases' else 'info',scope='polyline crossing within 2m vertical separation; no vehicle envelope, native yielding or clearance simulation'))
    if document.get('policies',{}).get('signal_conflicts','report')=='reject' and any(r['status']!='separated_green_phases' for r in reports):raise TrafficError('SIGNAL_MOVEMENT_CONFLICT: simultaneous or uncontrolled geometric crossing')
    return reports
