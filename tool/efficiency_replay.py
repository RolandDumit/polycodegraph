"""Reproduce core review scaling with a synthetic provider (no semantic coverage claim)."""
import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from smoke import Client

PROVIDER = r'''
import json,sys,pathlib
r=json.load(sys.stdin); out=[]
for f in r['files']:
    if f['file'] not in r['options']['emit_files']: continue
    text=(pathlib.Path(r['root'])/f['file']).read_text(); name=f['file']; lines=text.splitlines()
    nodes=[dict(id=name+'::file',name=name,q=name,kind='file',file=name,line=1,end=len(lines),offset=0,length=len(text))]
    offset=0
    for i,line in enumerate(lines):
        fn='f'+str(i)
        nodes.append(dict(id=name+'::'+fn+'#function',name=fn,q=fn,kind='function',file=name,line=i+1,end=i+1,offset=offset,length=len(line)))
        offset+=len(line)+1
    out.append(dict(file=name,hash=f['hash'],nodes=nodes,edges=[],dependencies=[],diagnostics=[],unresolved_calls=0))
json.dump(out,sys.stdout)
'''


def replay(binary):
    cases=[]
    with tempfile.TemporaryDirectory(prefix='pcg review replay ') as temp:
        base=Path(temp); assets=base/'provider'; (assets/'typescript').mkdir(parents=True)
        (assets/'typescript/index.cjs').write_text(PROVIDER)
        for count in [1,40,100,140]:
            root=base/str(count); root.mkdir()
            text=''.join(f'function f{i}() {{ return 0; }}\n' for i in range(count))
            (root/'sample.ts').write_text(text)
            (root/'polycodegraph.json').write_text(json.dumps(dict(providers_path=str(assets),node_path=sys.executable,watch=False)))
            client=Client(binary.resolve(),root)
            try:
                schema=client.request('tools/list',{})
                before=client.call('inspect_change',target='sample.ts',intent='review_change',options={'capture_baseline':True},budget={'max_chars':100000})
                handle=before['facts']['baseline']['handle']
                (root/'sample.ts').write_text(text.replace('return 0','return 1',1))
                args=dict(target='sample.ts',intent='review_change',options={'baseline':handle})
                raw=client.request('tools/call',dict(name='inspect_change',arguments=args))
                failed=bool(raw.get('isError')); page=json.loads(raw['content'][0]['text'])
                error=page.get('error') if failed else None
                pages=[page] if not failed else []
                diagnostic=client.call('inspect_change',**dict(args,budget={'max_chars':100000})) if failed else page
                while not failed and pages[-1]['next_cursor']:
                    args['cursor']=pages[-1]['next_cursor']; pages.append(client.call('inspect_change',**args))
                limits=diagnostic['limits']
                cases.append(dict(functions=count,default_error=error,limits=len(limits),distinct_limits=len(set(limits)),limits_chars=len(json.dumps(limits,ensure_ascii=False)),pages=len(pages),result_chars=sum(len(json.dumps(p,ensure_ascii=False)) for p in pages),evidence=sum(len(p['evidence']['rows']) for p in pages),schema_chars=len(json.dumps(schema,ensure_ascii=False))))
            finally: client.close()
    return dict(binary_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),model_runs=0,measurement='one JSON representation with Python default spaces; characters are not model tokens',cases=cases)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--binary',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.write_text(json.dumps(replay(a.binary),indent=2)+'\n')
