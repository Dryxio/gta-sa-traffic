"""Blender diagnostic signal overlay. No game simulation or native model replacement.

blender -b [context.blend] --python-exit-code 1 --python control_preview.py --
  --report manifest.json --time-ms 12000 --output preview.blend --render preview.png
"""
import argparse,json,math,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from sa_traffic.signals import phase

COLORS={'red':(1,.035,.025,1),'yellow':(1,.7,.02,1),'green':(.05,1,.2,1)}

def scene_plan(report,time_ms):
    """Pure manifest validation, preserving explicit distinctions in the visual legend."""
    if type(time_ms)!=int:raise ValueError('TIME_INTEGER_REQUIRED')
    signals=report.get('controls',{}).get('signals',[])
    if not isinstance(signals,list) or not signals:raise ValueError('SIGNALS_REQUIRED')
    result=[];ids=set()
    def vec(v,n):
        if not isinstance(v,(list,tuple)) or len(v)!=n or any(type(x) not in (int,float) or not math.isfinite(x) for x in v):raise ValueError('FINITE_POSITION_REQUIRED')
        return list(v)
    for s in signals:
        sid=s['id']
        if not isinstance(sid,str) or not sid or sid in ids:raise ValueError('UNIQUE_SIGNAL_ID_REQUIRED')
        ids.add(sid);xy=vec(s['navi_xy'],2);group=s['phase_group'];color=phase(group,time_ms)
        if type(s['direction_filter'])!=int or s['direction_filter'] not in (0,1):raise ValueError('DIRECTION_FILTER_REQUIRED')
        placements=[]
        for p in s.get('placements',[]):
            if p.get('group')!=group:raise ValueError('PLACEMENT_GROUP_MISMATCH')
            placements.append(dict(model_id=p['model_id'],position=vec(p['position'],3),yaw_degrees=vec([p['yaw_degrees']],1)[0]))
        # Navi carries no Z in DAT; use supplied diagnostic height or nearby placement.
        height=s.get('preview_z', min((p['position'][2] for p in placements),default=0.))
        height=vec([height],1)[0]
        result.append(dict(id=sid,xy=xy,z=height,color=color,group=group,filter=s['direction_filter'],toward=s.get('toward_node',s.get('toward_address')),placements=placements))
    return dict(signals=result,time_ms=time_ms,conflicts=report.get('controls',{}).get('movement_conflicts',report.get('controls',{}).get('conflicts',[])),legend='DIAGNOSTIC ONLY | phase clock, not simulated vehicles | circle = 12m distance reference, NOT stop footprint | navi height estimated')

def build(plan):
    import bpy
    from mathutils import Vector
    label_z=max((o.matrix_world @ Vector(c)).z for o in bpy.context.scene.objects if o.type=='MESH' for c in o.bound_box)+5 if any(o.type=='MESH' for o in bpy.context.scene.objects) else 20
    collection=bpy.data.collections.new('TRAFFIC SIGNAL DIAGNOSTIC');bpy.context.scene.collection.children.link(collection)
    def own(obj):
        for c in list(obj.users_collection):c.objects.unlink(obj)
        collection.objects.link(obj);obj['traffic_diagnostic']=True;return obj
    def material(name,rgba):
        m=bpy.data.materials.new(name);m.diffuse_color=rgba;m.use_nodes=True;tree=m.node_tree;tree.nodes.clear();a=tree.nodes.new('ShaderNodeEmission');a.inputs[0].default_value=rgba;b=tree.nodes.new('ShaderNodeOutputMaterial');tree.links.new(a.outputs[0],b.inputs[0]);return m
    mats={k:material('diagnostic '+k,v) for k,v in COLORS.items()};white=material('diagnostic labels',(.82,.9,1,1));blue=material('diagnostic reference',(.12,.55,1,1))
    def line(name,points,mat,width=.06):
        curve=bpy.data.curves.new(name,'CURVE');curve.dimensions='3D';curve.bevel_depth=width;curve.bevel_resolution=1;s=curve.splines.new('POLY');s.points.add(len(points)-1)
        for p,xyz in zip(s.points,points):p.co=(*xyz,1)
        obj=bpy.data.objects.new(name,curve);collection.objects.link(obj);obj.data.materials.append(mat);obj['traffic_diagnostic']=True;return obj
    def label(body,pos,size=1.):
        data=bpy.data.curves.new(body,'FONT');data.body=body;data.size=size;data.align_x='LEFT';obj=bpy.data.objects.new(body,data);collection.objects.link(obj);obj.location=(pos[0],pos[1],max(pos[2],label_z));obj.data.materials.append(white);return obj
    coords=[]
    for s in plan['signals']:
        x,y=s['xy'];z=s['z']+1;coords.append((x,y,z));mat=mats[s['color']]
        bpy.ops.mesh.primitive_uv_sphere_add(segments=12,ring_count=6,radius=.9,location=(x,y,z));obj=own(bpy.context.object);obj.name='DIAG phase '+s['id'];obj.data.materials.append(mat);obj['phase']=s['color'];obj['group']=s['group']
        circle=[(x+12*math.cos(t*math.tau/64),y+12*math.sin(t*math.tau/64),z-.65) for t in range(65)];line('12m reference '+s['id'],circle,blue)
        label(f"{s['id']} | G{s['group']} {s['color'].upper()} | filter {s['filter']}\nto {s['toward']} | 12m REFERENCE",(x+2,y+2,z+1),.9)
        for i,p in enumerate(s['placements']):
            px,py,pz=p['position'];coords.append((px,py,pz));bpy.ops.mesh.primitive_cube_add(size=1.3,location=(px,py,pz+1));ob=own(bpy.context.object);ob.name=f"DIAG placement {s['id']} model {p['model_id']}";ob.data.materials.append(mat)
            angle=math.radians(p['yaw_degrees']);dx,dy=-math.sin(angle),math.cos(angle)
            line('placement forward',[(px,py,pz+1),(px+4*dx,py+4*dy,pz+1)],mat,.15)
            line('association (author metadata)',[(x,y,z),(px,py,pz+1)],blue,.045)
            ob['model_id']=p['model_id']
    xs=[p[0] for p in coords];ys=[p[1] for p in coords];zs=[p[2] for p in coords];cx=(min(xs)+max(xs))/2;cy=(min(ys)+max(ys))/2;z=max(max(zs)+2,label_z+1);span=max(max(xs)-min(xs),max(ys)-min(ys),35)+32
    label(f"SIGNAL DIAGNOSTIC | t={plan['time_ms']}ms\nSpheres = phase | cubes = placement markers (not native models)\nBlue circles = 12m distance reference, NOT actual stop footprint\nNative clock only, no vehicle simulation | Navi height estimated",(cx-span*.70,cy+span*.44,z),span/72)
    if plan['conflicts']:label('MOVEMENT CONFLICTS (report): '+json.dumps(plan['conflicts'],ensure_ascii=False)[:500],(cx-span*.47,cy-span*.40,z),span/120)
    bpy.ops.object.camera_add(location=(cx,cy,z+span));camera=own(bpy.context.object);camera.rotation_euler=(0,0,0);camera.data.type='ORTHO';camera.data.ortho_scale=span*1.6;bpy.context.scene.camera=camera
    # Blender cameras look along local -Z; overhead view keeps world XY labels legible.
    return dict(collection=collection.name,signals=len(plan['signals']),markers=sum(len(s['placements']) for s in plan['signals']),legend=plan['legend'])

def main(argv=None):
    import bpy
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--report',required=True);p.add_argument('--time-ms',type=int,default=0);p.add_argument('--output',required=True);p.add_argument('--render',required=True);a=p.parse_args(argv)
    paths=[Path(a.output).resolve(),Path(a.render).resolve()];report=Path(a.report).resolve()
    if len(set(paths+[report]))!=3:raise ValueError('OUTPUT_COLLISION')
    if any(x.exists() for x in paths):raise ValueError('OUTPUT_EXISTS')
    plan=scene_plan(json.loads(report.read_text()),a.time_ms)
    from sa_traffic.textured_preview import prepare
    prepare(bpy.context.scene);stats=build(plan);scene=bpy.context.scene;scene.render.resolution_x=1500;scene.render.resolution_y=1050;scene.render.resolution_percentage=100;scene.world.color=(.03,.03,.03);scene.render.filepath=str(paths[1]);scene['traffic_control_preview']=json.dumps(stats)
    for x in paths:x.parent.mkdir(parents=True,exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(paths[0]));bpy.ops.render.render(write_still=True)

if __name__=='__main__':main(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
