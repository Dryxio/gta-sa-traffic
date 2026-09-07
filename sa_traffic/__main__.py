"""Run with python -m sa_traffic. No game installation side effects."""
import argparse,base64,hashlib,json,os,sys,tempfile,shutil
from pathlib import Path
from .codec import decode,TrafficError
from .document import empty,import_files,apply,seal,fingerprint,expand_routes
from .compiler import validate,compile_document
from .oracle import check
from .signals import placement_ipl

def read(path):return json.loads(Path(path).read_text())
def write(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='.'+path.name,dir=path.parent)
    try:
        with os.fdopen(fd,'w') as f:json.dump(obj,f,indent=2,allow_nan=False);f.write('\n')
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    for cmd in ('inspect','roundtrip'):
        s=sub.add_parser(cmd);s.add_argument('input');s.add_argument('--output',required=True)
    s=sub.add_parser('empty');s.add_argument('--output',required=True)
    s=sub.add_parser('import');s.add_argument('inputs',nargs='+');s.add_argument('--output',required=True)
    s=sub.add_parser('apply');s.add_argument('input');s.add_argument('operations');s.add_argument('--output',required=True)
    for cmd in ('validate','compile','expand'):
        s=sub.add_parser(cmd);s.add_argument('input');s.add_argument('--output',required=True)
    s=sub.add_parser('diff');s.add_argument('before');s.add_argument('after');s.add_argument('--output',required=True)
    args=p.parse_args(argv)
    try:
        if args.command=='empty':write(args.output,empty())
        elif args.command in ('inspect','roundtrip'):
            b=Path(args.input).read_bytes();a=decode(b)
            if args.command=='inspect':write(args.output,dict(counts=a.counts,bytes=len(b),sha256=hashlib.sha256(b).hexdigest(),trailing_bytes=len(a.trailing)))
            else:
                dest=Path(args.output)
                if dest.exists():raise TrafficError('OUTPUT_EXISTS: roundtrip refuses overwrite')
                dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(a.encode())
        elif args.command=='import':write(args.output,import_files(args.inputs))
        elif args.command=='apply':write(args.output,apply(read(args.input),read(args.operations)))
        elif args.command=='expand':write(args.output,seal(expand_routes(read(args.input))))
        elif args.command=='validate':
            doc=read(args.input);diagnostics=validate(doc)
            if diagnostics:write(args.output,dict(valid=False,diagnostics=diagnostics));return 1
            try:outputs,manifest=compile_document(doc)
            except (ValueError,KeyError,TypeError,OverflowError) as exc:write(args.output,dict(valid=False,diagnostics=[dict(severity='error',code='COMPILE',message=str(exc))]));return 1
            result=check(outputs);result['controls']=manifest.get('controls',{});result['junction_validation']=manifest.get('junction_validation',[]);write(args.output,result);return 0 if result['valid'] else 1
        elif args.command=='compile':
            doc=read(args.input);outputs,manifest=compile_document(doc);verification=check(outputs)
            if not verification['valid']:raise TrafficError('INDEPENDENT_VALIDATION: '+str(verification['errors'][:10]))
            manifest['independent_verification']=verification;dest=Path(args.output)
            if dest.exists():raise TrafficError('OUTPUT_EXISTS: builds use a fresh directory')
            dest.parent.mkdir(parents=True,exist_ok=True);tmp=Path(tempfile.mkdtemp(prefix='.'+dest.name,dir=dest.parent))
            try:
                manifest['document_revision']=fingerprint(doc);manifest['compiler']={'version':'0.1.0','modules':{name:hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest() for name in ('codec.py','document.py','compiler.py','oracle.py','controls.py','signals.py')},'profile_executable_sha256':'72ae59e44c761389e354a50dc6215e964fe771121e2f4b1877273a493ceecc9b'};manifest['files']=[];manifest['sources']={a:{k:s[k] for k in ('path','sha256')} for a,s in doc.get('sources',{}).items()}
                for a in manifest['changed_regions']:
                    b=outputs[a];name=f'nodes{a}.dat';(tmp/name).write_bytes(b);manifest['files'].append(dict(path=name,sha256=hashlib.sha256(b).hexdigest(),bytes=len(b)))
                controls=manifest.get('controls',{})
                if controls.get('signals') or controls.get('junctions'):
                    write(tmp/'controls.json',controls)
                    if any(s['placements'] for s in controls.get('signals',[])):
                        (tmp/'traffic-signals.ipl').write_text(placement_ipl(controls['signals']))
                        registry_path=Path(__file__).parent/'data/signal-model-registry.json';registry=json.loads(registry_path.read_text());wanted={p['model_id'] for s in controls['signals'] for p in s['placements']}
                        write(tmp/'signal-model-requirements.json',{'registry_sha256':hashlib.sha256(registry_path.read_bytes()).hexdigest(),'models':[m for m in registry['models'] if m['id'] in wanted],'scope':'Native compatibility identifiers only; target installation must retain native model registration and compatible LIGHT effects. No assets or extracted effect records are copied.'})
                write(tmp/'manifest.json',manifest);write(tmp/'validation.json',verification)
                os.rename(tmp,dest)
            finally:
                if tmp.exists():shutil.rmtree(tmp)
        elif args.command=='diff':
            a,b=read(args.before),read(args.after);changes={}
            for key in ('nodes','edges','navis','routes'):
                aa={x['id']:x for x in a.get(key,[])};bb={x['id']:x for x in b.get(key,[])}
                changes[key]=dict(added=sorted(bb.keys()-aa.keys()),removed=sorted(aa.keys()-bb.keys()),modified=sorted(k for k in aa.keys()&bb.keys() if aa[k]!=bb[k]))
            write(args.output,changes)
        return 0
    except (TrafficError,ValueError,KeyError,TypeError,OSError,OverflowError) as e:
        print(json.dumps(dict(ok=False,error=type(e).__name__,message=str(e))),file=sys.stderr);return 2
if __name__=='__main__':sys.exit(main())
