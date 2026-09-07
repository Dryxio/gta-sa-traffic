"""Native compact traffic signals: verified two-phase encoding, no local timers."""
import math,struct
from .codec import TrafficError

MODELS={1262:('MTraffic4','mitraffic'),1283:('MTraffic1','mitraffic'),1284:('MTraffic2','mitraffic'),1315:('trafficlight1','dyntraffic'),1350:('CJ_TRAFFIC_LIGHT4','CJ_traffic'),1351:('CJ_TRAFFIC_LIGHT5','CJ_traffic'),1352:('CJ_TRAFFIC_LIGHT3','CJ_traffic'),3516:('vgsstriptlights1','vegtrafic2'),3855:('GAY_TRAFFIC_LIGHT','gay_xref')}

def phase(group,time_ms):
    if type(group)!=int or group not in (1,2) or type(time_ms)!=int:raise TrafficError('SIGNAL_PHASE_ARGUMENT')
    t=((time_ms&0xffffffff)>>1)&0x3fff
    if group==1:return 'green' if t<5000 else 'yellow' if t<6000 else 'red'
    return 'green' if 6000<=t<11000 else 'yellow' if 11000<=t<12000 else 'red'

def pedestrian_phase(time_ms):
    if type(time_ms)!=int:raise TrafficError('SIGNAL_TIME')
    t=((time_ms&0xffffffff)>>1)&0x3fff
    return 'red' if t<12000 else 'green' if t<15384 else 'yellow'

def visual_group(yaw_degrees):
    if type(yaw_degrees) not in (int,float) or not math.isfinite(yaw_degrees):raise TrafficError('SIGNAL_YAW')
    a=(90+yaw_degrees)%360 # model local +Y transformed by Blender/world yaw
    return 1 if 60<a<150 or 240<a<330 else 2

def should_stop(candidates,time_ms,force=False):
    """Restricted PE predicate oracle: caller supplies loaded/eligible autopilot candidates.

    Ordered current,next,previous. Does not simulate vehicle integration or selection.
    """
    for c in candidates:
        if not c.get('valid',True) or not c.get('group',0):continue
        if bool(c['attachment_matches'])!=bool(c['direction_filter']):continue
        if not force and phase(c['group'],time_ms)=='green':return False
        limit=6 if c.get('previous',False) else 12
        f=c['signed_projection']
        if (0<f<limit) if c['direction_sign']==-1 else (-limit<f<0):return True
    return False

def apply_signals(document,navis_by_area,navi_addresses,addresses,edges):
    requests=document.get('signals',[])
    if not isinstance(requests,list):raise TrafficError('SIGNALS: expected array')
    by_key={};ids=set();result=[]
    for s in requests:
        if not isinstance(s,dict) or set(s)-{'id','segment','navi','toward_node','phase_group','placements','approach','metadata'}:raise TrafficError('SIGNAL_FIELDS: unknown field or unsupported custom timing')
        sid=s.get('id');key=s.get('segment') or s.get('navi');target=s.get('toward_node');group=s.get('phase_group')
        if not isinstance(sid,str) or not sid or sid in ids:raise TrafficError('SIGNAL_ID')
        ids.add(sid)
        if bool(s.get('segment'))==bool(s.get('navi')) or key not in navi_addresses:raise TrafficError('SIGNAL_NAVI: specify exactly one existing segment/navi')
        if target not in addresses:raise TrafficError('SIGNAL_TARGET: unresolved destination node')
        if type(group)!=int or group not in (1,2):raise TrafficError('SIGNAL_GROUP: native supports groups 1 and 2 only')
        matching=[e for e in edges if (e.get('_compiled_navi') or e.get('navi'))==key]
        if not any(e['target']==target for e in matching):raise TrafficError('SIGNAL_TARGET: not a segment endpoint')
        na,ni=navi_addresses[key];raw=bytearray(navis_by_area[na][ni]);attached=struct.unpack_from('<HH',raw,4);bit=int(attached==addresses[target])
        lanes=(raw[11]&7) if bit else ((raw[11]>>3)&7)
        if lanes==0:raise TrafficError('SIGNAL_ZERO_LANES: no normal travel in controlled direction')
        assignment=(group,bit)
        if key in by_key and by_key[key]!=assignment:raise TrafficError('SIGNAL_CONFLICT: one navi can control only one direction/group; split approaches')
        by_key[key]=assignment;raw[11]=(raw[11]&~64)|(bit<<6);raw[12]=(raw[12]&~3)|group;navis_by_area[na][ni]=raw
        xy=[v/8 for v in struct.unpack_from('<hh',raw)];placements=[]
        for p in s.get('placements',[]):
            if not isinstance(p,dict) or set(p)-{'model_id','position','yaw_degrees','metadata'}:raise TrafficError('SIGNAL_PLACEMENT_FIELDS')
            model=p.get('model_id');pos=p.get('position');yaw=p.get('yaw_degrees')
            if type(model)!=int or model not in MODELS:raise TrafficError('SIGNAL_MODEL: not a verified native model ID')
            if not isinstance(pos,list) or len(pos)!=3 or any(type(v) not in (int,float) or not math.isfinite(v) for v in pos):raise TrafficError('SIGNAL_PLACEMENT_POSITION')
            if visual_group(yaw)!=group:raise TrafficError('SIGNAL_VISUAL_GROUP: model orientation and AI phase disagree')
            angle=math.radians(yaw)/2;quaternion=[0.,0.,-math.sin(angle),math.cos(angle)] # IPL conjugates into world matrix
            placements.append(dict(model_id=model,model=MODELS[model][0],txd=MODELS[model][1],position=pos,yaw_degrees=yaw,ipl_quaternion_xyzw=quaternion,group=group,distance_xy_to_navi=math.dist(pos[:2],xy),verification='native recognized model/orientation; placement geometry and visibility require scene inspection'))
        approach=s.get('approach')
        if approach is not None:
            if not isinstance(approach,dict) or set(approach)!={'junction','port'}:raise TrafficError('SIGNAL_APPROACH')
            j=next((j for j in document.get('junctions',[]) if j['id']==approach['junction']),None)
            port=next((p for p in j['ports'] if p['id']==approach['port']),None) if j else None
            if port is None or port['entry_node']!=target:raise TrafficError('SIGNAL_APPROACH_TARGET: must control ingress to the declared entry port')
        result.append(dict(id=sid,navi_key=key,navi_address=[na,ni],toward_node=target,toward_address=list(addresses[target]),phase_group=group,direction_filter=bit,navi_xy=xy,stop_zone_units=12,previous_stop_zone_units=6,placements=placements,visual_status='placement_bundle' if placements else 'unplaced_DAT_only',approach=s.get('approach'),phase_samples={str(t):phase(group,t) for t in (0,9999,10000,11999,12000,21999,22000,23999,24000,30768,32767,32768)}))
    return result

def verify_signal_bytes(signals,files):
    for s in signals:
        a,i=s['navi_address'];b=files[a];n=struct.unpack_from('<I',b)[0];o=20+28*n+14*i
        group=b[o+12]&3;bit=(b[o+11]>>6)&1;attached=struct.unpack_from('<HH',b,o+4)
        if group!=s['phase_group'] or bit!=int(attached==tuple(s['toward_address'])):raise TrafficError('SIGNAL_BYTE_VERIFY: '+s['id'])
    return dict(verified=len(signals),scope='encoded phase and approach filter, not vehicle motion')

def placement_ipl(signals):
    lines=['# SA traffic signal placements; requires matching vanilla model definitions','inst']
    for s in signals:
        for p in s['placements']:
            values=[p['model_id'],p['model'],0,*p['position'],*p['ipl_quaternion_xyzw'],-1]
            lines.append(', '.join(str(x) for x in values))
    lines.extend(['end','']);return '\n'.join(lines)
