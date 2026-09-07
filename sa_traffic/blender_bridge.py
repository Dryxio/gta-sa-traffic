"""Explicit traffic graph visualization and editing bridge for Blender CLI.

No traffic inference is performed. Original metadata is preserved verbatim in a
Text datablock. Node vertex order and route spline order are stable identities;
changing topology requires reimporting an explicitly edited JSON graph.
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import sys

TEXT = 'SA_TRAFFIC_SOURCE.json'
COLLECTION = 'SA Traffic'


def validate(data):
    if data.get('schema_version') != 1 or data.get('profile') != 'sa_compact':
        raise ValueError('Expected schema_version 1 and profile sa_compact')
    def point(p):
        if not isinstance(p, list) or len(p) != 3 or any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) for v in p):
            raise ValueError('Position must contain three finite numbers')
    ids = {}
    for group in ('nodes', 'edges', 'routes'):
        values = data.get(group, [])
        if not isinstance(values, list):
            raise ValueError(f'{group} must be a list')
        ids[group] = set()
        for item in values:
            ident = item.get('id')
            if not isinstance(ident, str) or not ident or ident in ids[group]:
                raise ValueError(f'Missing or duplicate {group} id')
            ids[group].add(ident)
    for n in data.get('nodes', []):
        point(n.get('position'))
    for e in data.get('edges', []):
        if e.get('source') not in ids['nodes'] or e.get('target') not in ids['nodes']:
            raise ValueError('Edge references an unknown node')
    for r in data.get('routes', []):
        if not isinstance(r.get('points'), list) or len(r['points']) < 2:
            raise ValueError('Route needs at least two points')
        for p in r['points']:
            point(p)
    return data


def estimated_lane_lines(data):
    """Straight lane estimates using audited compact constants, not CarCtrl curves."""
    import struct
    nodes={n['id']:n for n in data.get('nodes',[])}
    lines=[]
    edge_by_navi={}
    for edge in data.get("edges",[]):
        edge_by_navi.setdefault(edge.get("navi"),[]).append(edge)
    def emit(ident,center,dx,dy,length,forward,backward,width_raw,kind):
        if forward is None or backward is None:return
        offset=.5-.5*max(forward,backward) if min(forward,backward)==0 else .5+width_raw*.011574073694646358
        for sign,count in ((1,forward),(-1,backward)):
            for i in range(count):
                lateral=5.400000095367432*(offset+i)
                x=center[0]+dy*sign*lateral;y=center[1]-dx*sign*lateral;z=center[2]+.15
                a=[x-dx*sign*length/2,y-dy*sign*length/2,z];b=[x+dx*sign*length/2,y+dy*sign*length/2,z]
                lines.append(dict(id=ident,points=[a,b],lane_index=i,travel_sign=sign,offset=lateral,kind=kind))
    for n in data.get('navis',[]):
        raw=bytes.fromhex(n['raw']);attached=nodes.get(n.get('attached'))
        if attached is None:continue
        neighbors={e['source'] if e['target']==n['attached'] else e['target'] for e in edge_by_navi.get(n['id'],[]) if n['attached'] in (e['source'],e['target'])}
        neighbors.discard(n['attached'])
        if len(neighbors)!=1:continue
        other=nodes.get(next(iter(neighbors)))
        if other is None:continue
        x,y=struct.unpack_from('<hh',raw);dx,dy=struct.unpack_from('<bb',raw,8)
        length=math.dist(attached['position'][:2],other['position'][:2]);z=(attached['position'][2]+other['position'][2])/2
        emit(n['id'],[x/8,y/8,z],dx/100,dy/100,length,raw[11]&7,(raw[11]>>3)&7,raw[10],'navi_straight_estimate')
    for r in data.get('routes',[]):
        for a,b in zip(r['points'],r['points'][1:]):
            dx,dy=b[0]-a[0],b[1]-a[1];length=math.hypot(dx,dy)
            if length:
                emit(r['id'],[(a[i]+b[i])/2 for i in range(3)],dx/length,dy/length,length,r.get('lanes_forward'),r.get('lanes_backward'),(r.get('navi_width') or 0)*16,'proposal_straight_estimate')
    return lines


def overlay_primitives(data):
    """Diagnostic-only primitives; lane convention comes from the audited codec.

    Low lane bits travel toward the attached endpoint, high bits away. Arrows
    show the stored navi direction; they do not assert valid edge connectivity.
    """
    import struct
    nodes = {n['id']: n for n in data.get('nodes', [])}
    arrows, navis, attachments, regions, diagnostics = [], [], [], [], []
    for n in data.get('navis', []):
        raw = bytes.fromhex(n['raw'])
        if len(raw) != 14:
            raise ValueError('Navi raw record must contain 14 bytes')
        attached = nodes.get(n.get('attached'))
        z = attached['position'][2] if attached else 0
        x, y = struct.unpack_from('<hh', raw)
        dx, dy = struct.unpack_from('<bb', raw, 8)
        p = [x/8, y/8, z+.3]
        navis.append(p)
        if attached:
            attachments.append([p, attached['position']])
        length = math.hypot(dx, dy)
        if length:
            for sign, lanes in ((1, raw[11]&7), (-1, (raw[11]>>3)&7)):
                if lanes:
                    # Side offset keeps opposing arrows separately visible.
                    center = [p[0]-dy/length*.6*sign, p[1]+dx/length*.6*sign, p[2]+.2]
                    arrows.append({'position': center, 'direction': [dx/length*sign, dy/length*sign, 0], 'lanes': lanes, 'source': n['id'], 'kind': 'navi'})
    for r in data.get('routes', []):
        for a, b in zip(r['points'], r['points'][1:]):
            dx, dy = b[0]-a[0], b[1]-a[1]
            length = math.hypot(dx, dy)
            if not length:
                continue
            for sign, lanes in ((1, r.get('lanes_forward', 0)), (-1, r.get('lanes_backward', 0))):
                if lanes is not None and lanes > 0:
                    arrows.append({'position': [(a[0]+b[0])/2-dy/length*.6*sign, (a[1]+b[1])/2+dx/length*.6*sign, (a[2]+b[2])/2+.6], 'direction': [dx/length*sign, dy/length*sign, 0], 'lanes': lanes, 'source': r['id'], 'kind': 'proposal'})
    occupied = set()
    for n in nodes.values():
        x, y, z = n['position']
        if -3000 <= x < 3000 and -3000 <= y < 3000:
            occupied.add((int((x+3000)//750), int((y+3000)//750)))
    z = min((n['position'][2] for n in nodes.values()), default=0)-.3
    for x, y in sorted(occupied):
        a, b = x*750-3000, y*750-3000
        regions.append({'id': y*8+x, 'points': [[a,b,z],[a+750,b,z],[a+750,b+750,z],[a,b+750,z],[a,b,z]]})
    for diag in data.get('diagnostics', []):
        p = diag.get('position')
        if p is None and diag.get('id') in nodes:
            p = nodes[diag['id']]['position']
        if p is not None:
            diagnostics.append({'position': p, 'message': diag.get('message', ''), 'code': diag.get('code', ''), 'severity': diag.get('severity', 'error')})
    return dict(arrows=arrows, navis=navis, attachments=attachments, regions=regions, diagnostics=diagnostics)


def build_overlays(data, col, mesh, curves, material):
    import bpy
    primitives = overlay_primitives(data)
    lane_lines=estimated_lane_lines(data)
    primitives['estimated_lane_lines']=lane_lines
    gold = material('Traffic permitted direction', (1, .85, .03))
    curves('Traffic estimated lanes', [l['points'] for l in lane_lines], .065, gold, 'display_only')
    purple = material('Traffic navi attachment', (.7, .15, 1))
    red = material('Traffic diagnostic marker', (1, .03, .08))
    gray = material('Traffic region boundary', (.3, .4, .6))
    verts, faces = [], []
    for arrow in primitives['arrows']:
        x, y, z = arrow['position']; dx, dy, _ = arrow['direction']
        i = len(verts)
        verts.extend([(x+dx*1.5,y+dy*1.5,z),(x-dx*.8-dy*.6,y-dy*.8+dx*.6,z),(x-dx*.8+dy*.6,y-dy*.8-dx*.6,z)])
        faces.append((i,i+1,i+2))
    obj = mesh('Traffic permitted direction arrows', verts, [], faces, gold)
    obj['traffic_role'] = 'display_only'
    obj['arrow_metadata'] = json.dumps(primitives['arrows'])
    curves('Traffic navi attachments', primitives['attachments'], .045, purple, 'display_only')
    for name, points, radius, mat in [('Traffic navi centers',primitives['navis'],.24,purple),('Traffic diagnostics',[d['position'] for d in primitives['diagnostics']],1.2,red)]:
        vertices, triangles = [], []
        for x,y,z in points:
            i=len(vertices)
            vertices.extend([(x-radius,y,z+.3),(x+radius,y,z+.3),(x,y-radius,z+.3),(x,y+radius,z+.3),(x,y,z+radius+.3)])
            triangles.extend((i+a,i+b,i+c) for a,b,c in [(0,2,4),(2,1,4),(1,3,4),(3,0,4)])
        o=mesh(name,vertices,[],triangles,mat);o['traffic_role']='display_only'
    curves('Traffic region boundaries', [r['points'] for r in primitives['regions']], .1, gray, 'display_only')
    summary = bpy.data.texts.get('SA_TRAFFIC_DIAGNOSTICS.json') or bpy.data.texts.new('SA_TRAFFIC_DIAGNOSTICS.json')
    summary.clear();summary.write(json.dumps(primitives, indent=2))
    # Region and diagnostics metadata remain readable even when their markers are
    # outside the camera crop. No diagnostics are silently used as validation.
    col['traffic_regions'] = json.dumps([r['id'] for r in primitives['regions']])


def build_scene(data):
    import bpy
    validate(data)
    # Own only our collection; existing map geometry is retained.
    old = bpy.data.collections.get(COLLECTION)
    if old:
        for obj in list(old.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(old)
    col = bpy.data.collections.new(COLLECTION)
    bpy.context.scene.collection.children.link(col)
    txt = bpy.data.texts.get(TEXT) or bpy.data.texts.new(TEXT)
    txt.clear()
    txt.write(json.dumps(data, ensure_ascii=False, indent=2))
    def material(name, color):
        mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        mat.diffuse_color = (*color, 1)
        return mat
    cyan = material('Traffic nodes cyan', (.03, .75, 1))
    orange = material('Traffic links orange', (1, .4, .04))
    green = material('Traffic route proposals green', (.1, .85, .25))
    def mesh(name, vertices, edges, faces, mat=None):
        m = bpy.data.meshes.new(name)
        m.from_pydata(vertices, edges, faces)
        m.update()
        obj = bpy.data.objects.new(name, m)
        col.objects.link(obj)
        if mat:
            m.materials.append(mat)
        return obj
    nodes = data.get('nodes', [])
    positions = [n['position'] for n in nodes]
    index = {n['id']: i for i, n in enumerate(nodes)}
    links = [(index[e['source']], index[e['target']]) for e in data.get('edges', [])]
    graph = mesh('Traffic editable graph', positions, links, [])
    graph['traffic_role'] = 'graph'
    graph['node_ids'] = json.dumps([n['id'] for n in nodes])
    graph['edge_ids'] = json.dumps([e['id'] for e in data.get('edges', [])])
    graph.hide_render = True
    graph.show_in_front = True
    # Octahedra are a render helper; vertex graph above is the editable authority.
    verts, faces = [], []
    for x, y, z in positions:
        off = len(verts)
        s = .38
        verts.extend([(x+s,y,z),(x-s,y,z),(x,y+s,z),(x,y-s,z),(x,y,z+s),(x,y,z-s)])
        faces.extend(tuple(off+i for i in f) for f in ((0,2,4),(2,1,4),(1,3,4),(3,0,4),(2,0,5),(1,2,5),(3,1,5),(0,3,5)))
    helper = mesh('Traffic node display', verts, [], faces, cyan)
    helper['traffic_role'] = 'display_only'
    def curves(name, lines, radius, mat, role):
        curve = bpy.data.curves.new(name, 'CURVE')
        curve.dimensions = '3D'
        curve.bevel_depth = radius
        curve.bevel_resolution = 0
        for points in lines:
            spline = curve.splines.new('POLY')
            spline.points.add(len(points)-1)
            for bp, p in zip(spline.points, points):
                bp.co = (*p, 1)
        curve.materials.append(mat)
        obj = bpy.data.objects.new(name, curve)
        col.objects.link(obj)
        obj['traffic_role'] = role
        return obj
    curves('Traffic link display', [[positions[a], positions[b]] for a,b in links], .09, orange, 'display_only')
    routes = curves('Traffic editable routes', [r['points'] for r in data.get('routes', [])], .16, green, 'routes')
    routes['route_ids'] = json.dumps([r['id'] for r in data.get('routes', [])])
    build_overlays(data, col, mesh, curves, material)
    bpy.context.scene['traffic_bridge_note'] = 'Edit graph vertex positions and route polyline points; export JSON then reimport to refresh display. Green routes are explicit proposals, not compiled traffic.'
    return col


def export_scene():
    import bpy
    data = json.loads(bpy.data.texts[TEXT].as_string())
    col = bpy.data.collections[COLLECTION]
    graph = next(o for o in col.objects if o.get('traffic_role') == 'graph')
    routes = next(o for o in col.objects if o.get('traffic_role') == 'routes')
    if graph.mode != 'OBJECT' or routes.mode != 'OBJECT':
        raise ValueError('Leave edit mode before exporting')
    if len(graph.data.vertices) != len(data.get('nodes', [])) or len(graph.data.edges) != len(data.get('edges', [])):
        raise ValueError('Graph topology changed; edit JSON and reimport instead')
    expected = {n['id']: i for i,n in enumerate(data.get('nodes', []))}
    # Mesh edges are undirected display links; source/target direction stays in JSON.
    from collections import Counter
    wanted = Counter(tuple(sorted((expected[e['source']], expected[e['target']]))) for e in data.get('edges', []))
    actual = Counter(tuple(sorted(e.vertices)) for e in graph.data.edges)
    if wanted != actual:
        raise ValueError('Graph connectivity changed; edit JSON and reimport instead')
    for n, v in zip(data.get('nodes', []), graph.data.vertices):
        n['position'] = list(graph.matrix_world @ v.co)
    if len(routes.data.splines) != len(data.get('routes', [])):
        raise ValueError('Route topology changed')
    for r, spline in zip(data.get('routes', []), routes.data.splines):
        if spline.type != 'POLY' or len(spline.points) != len(r['points']):
            raise ValueError('Route topology changed')
        r['points'] = [list(routes.matrix_world @ p.co.xyz) for p in spline.points]
    return validate(data)


def render_scene(path, focus=None, span_override=None):
    import bpy
    from mathutils import Vector
    scene = bpy.context.scene
    pts = [Vector(n['position']) for n in export_scene().get('nodes', [])]
    pts += [Vector(p) for r in export_scene().get('routes', []) for p in r['points']]
    if not pts:
        raise ValueError('Cannot frame an empty graph')
    low = Vector(tuple(min(p[i] for p in pts) for i in range(3)))
    high = Vector(tuple(max(p[i] for p in pts) for i in range(3)))
    center = (low+high)/2
    span = max((high-low).length, 10)
    if focus is not None:
        center=Vector(focus)
    if span_override is not None:
        span=span_override
    cam_data = bpy.data.cameras.new('Traffic preview camera')
    cam = bpy.data.objects.new('Traffic preview camera', cam_data)
    bpy.data.collections[COLLECTION].objects.link(cam)
    cam.location = center + Vector((.15, -.65, 1.1))*span
    cam.rotation_euler = (center-cam.location).to_track_quat('-Z','Y').to_euler()
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = span*1.2
    cam_data.clip_end = max(1000, span*5)
    scene.camera = cam
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.display.shading.light = 'STUDIO'
    scene.display.shading.color_type = 'MATERIAL'
    scene.display.shading.background_type = 'WORLD'
    if scene.world is None:
        scene.world = bpy.data.worlds.new('Traffic preview world')
    scene.world.color = (.025,.025,.025)
    scene.render.resolution_x = 1200
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.filepath = str(Path(path).resolve())
    bpy.ops.render.render(write_still=True)


def propose_centerlines():
    """Read only explicitly tagged centerlines; never infer lanes or road meshes."""
    import bpy
    routes = []
    for obj in bpy.context.scene.objects:
        if not obj.get('traffic_centerline'):
            continue
        chains = []
        if obj.type == 'CURVE':
            for spline in obj.data.splines:
                if spline.type != 'POLY':
                    raise ValueError('Centerline curves must be explicit POLY splines: '+obj.name)
                points = [list(obj.matrix_world @ p.co.xyz) for p in spline.points]
                if spline.use_cyclic_u:
                    points.append(points[0])
                chains.append(points)
        elif obj.type == 'MESH':
            neighbors = {}
            for e in obj.data.edges:
                a,b=e.vertices
                neighbors.setdefault(a,set()).add(b);neighbors.setdefault(b,set()).add(a)
            if any(len(v)>2 for v in neighbors.values()):
                raise ValueError('Branching centerline mesh needs explicit route splitting: '+obj.name)
            unused={tuple(sorted(e.vertices)) for e in obj.data.edges}
            while unused:
                available={v for edge in unused for v in edge}
                start=next((v for v in sorted(available) if len(neighbors[v])==1),min(available))
                chain=[start];current=start
                while True:
                    targets=[v for v in sorted(neighbors[current]) if tuple(sorted((current,v))) in unused]
                    if not targets:break
                    target=targets[0];unused.remove(tuple(sorted((current,target))));chain.append(target);current=target
                chains.append([list(obj.matrix_world @ obj.data.vertices[v].co) for v in chain])
        else:
            raise ValueError('Tagged centerline must be a CURVE or mesh-edge object: '+obj.name)
        for i,points in enumerate(chains):
            if len(points)<2:continue
            routes.append(dict(id=f'proposal:{obj.name}:{i}',points=points,lanes_forward=None,lanes_backward=None,metadata=dict(status='proposal_requires_lane_configuration',source_object=obj.name,reason='Explicit centerline only; lane counts and permitted directions deliberately unspecified')))
    return dict(schema_version=1,profile='sa_compact',nodes=[],edges=[],navis=[],routes=routes)


def surface_diagnostics(data, collection_name, tolerance=1.0, ray_height=50.0):
    """Raycast only the explicitly named road collection, never traffic helpers."""
    import bpy
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    if collection_name == COLLECTION:
        raise ValueError('Traffic helper collection cannot be the road surface')
    collection = bpy.data.collections.get(collection_name)
    if collection is None:
        raise ValueError('Road surface collection not found: '+collection_name)
    trees=[];depsgraph=bpy.context.evaluated_depsgraph_get()
    for obj in collection.all_objects:
        if obj.type!='MESH' or obj.get('traffic_role'):continue
        evaluated=obj.evaluated_get(depsgraph);m=evaluated.to_mesh()
        try:
            if m.polygons:
                trees.append(BVHTree.FromPolygons([evaluated.matrix_world @ v.co for v in m.vertices],[list(p.vertices) for p in m.polygons],all_triangles=False))
        finally:evaluated.to_mesh_clear()
    samples=[(n['id'],n['position']) for n in data.get('nodes',[])]
    for r in list(data.get('routes',[]))+estimated_lane_lines(data):
        for a,b in zip(r['points'],r['points'][1:]):
            distance=math.dist(a,b);count=max(1,math.ceil(distance/5))
            samples.extend((r['id'],[a[i]+(b[i]-a[i])*j/count for i in range(3)]) for j in range(count+1))
    result=[]
    for ident,p in samples:
        hits=[]
        for tree in trees:
            origin=Vector((p[0],p[1],p[2]+ray_height));remaining=2*ray_height
            # Enumerate stacked surfaces; choose the closest height, preserving bridges.
            for _ in range(128):
                loc,normal,index,distance=tree.ray_cast(origin,Vector((0,0,-1)),remaining)
                if loc is None:break
                hits.append(loc.z);advance=distance+.001;remaining-=advance
                if remaining<=0:break
                origin=loc-Vector((0,0,.001))
        if not hits:
            result.append(dict(severity='error',code='NO_ROAD_SURFACE',id=ident,position=p,message='No surface in named road collection within ray window'))
        else:
            height=min(hits,key=lambda z:abs(z-p[2]));delta=p[2]-height
            if abs(delta)>tolerance:
                result.append(dict(severity='error',code='ROAD_HEIGHT_MISMATCH',id=ident,position=p,message=f'Node/route is {delta:.3f} m from nearest road height',surface_z=height,delta_z=delta))
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--propose-centerlines', help='Export explicitly traffic_centerline-tagged geometry as unconfigured route proposals')
    p.add_argument('--road-collection', help='Explicit road mesh collection for geometric preflight')
    p.add_argument('--surface-tolerance', type=float, default=1.0)
    p.add_argument('--diagnostics-json', help='Write geometric preflight diagnostics')
    p.add_argument('--input', help='Explicit graph JSON; omit to export the currently loaded blend')
    p.add_argument('--output', help='Save .blend project')
    p.add_argument('--focus', help='Preview center x,y,z')
    p.add_argument('--span', type=float, help='Preview framing span in metres')
    p.add_argument('--display-lift', type=float, default=0, help='Display-only helper elevation; author positions unchanged')
    p.add_argument('--render', help='Save preview PNG')
    p.add_argument('--export-json', help='Export editable positions, preserving metadata')
    args = p.parse_args(argv)
    import bpy
    if args.propose_centerlines:
        Path(args.propose_centerlines).write_text(json.dumps(propose_centerlines(), indent=2)+'\n')
    if args.input:
        data=json.loads(Path(args.input).read_text())
        if args.road_collection:
            findings=surface_diagnostics(data,args.road_collection,args.surface_tolerance)
            data['diagnostics']=data.get('diagnostics',[])+findings
            if args.diagnostics_json:
                Path(args.diagnostics_json).write_text(json.dumps(dict(scope='Geometry only, not engine validation',diagnostics=findings),indent=2)+'\n')
        build_scene(data)
        bpy.context.scene['traffic_geometry_preflight']='checked_named_collection' if args.road_collection else 'unchecked_no_road_collection'
    if args.display_lift:
        for obj in bpy.data.collections[COLLECTION].objects:
            if obj.get('traffic_role')=='display_only':obj.location.z+=args.display_lift
    if args.export_json:
        Path(args.export_json).write_text(json.dumps(export_scene(), ensure_ascii=False, indent=2)+'\n')
    if args.render:
        render_scene(args.render, [float(v) for v in args.focus.split(',')] if args.focus else None, args.span)
    if args.output:
        bpy.ops.wm.save_as_mainfile(filepath=str(Path(args.output).resolve()))

if __name__ == '__main__':
    main(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
