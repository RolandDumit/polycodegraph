"""Native 0.8 feature replay, one explicitly selected structured representation.

Aggregates only. Local estimates/characters and runtime never stand in for AI usage.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
import tempfile
import time
import threading
import statistics
from benchmark import rss_tree
from pathlib import Path
from smoke import Client


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def size(value):
    return len(compact(value))


def pages(client, args):
    found = []
    for _ in range(100):
        value = client.call('inspect_change', **args)
        found.append(value)
        if value['next_cursor'] is None:
            if 'remaining_after_page' in value['evidence']:
                assert value['evidence']['remaining_after_page'] == 0, value
                assert value['evidence']['collection_complete'], value
            return found
        args = dict(args, cursor=value['next_cursor'])
    raise AssertionError('pagination did not terminate')


def run(binary, baseline, config, baseline_config):
    result = dict(model_runs=0, measurement='compact Unicode JSON characters; structured representation explicitly selected by this replay; not model input or quota',
                  candidate_sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                  baseline_sha256=hashlib.sha256(baseline.read_bytes()).hexdigest(), conditions={})
    fixture = Path(__file__).resolve().parent.parent / 'test/fixtures/efficiency08'
    for version, executable, settings in [('B', baseline, baseline_config), ('C', binary, config)]:
        with tempfile.TemporaryDirectory(prefix='pcg efficiency native ') as temp:
            root = Path(temp)
            shutil.copytree(fixture, root, dirs_exist_ok=True)
            (root / 'polycodegraph.json').write_text(json.dumps(dict(settings, watch=True)))
            client = Client(executable.resolve(), root)
            try:
                full = client.request('tools/list', {})
                metrics = dict(full_schema_chars=size(full), tools=len(full['tools']))
                peak = [0, 0, 0]
                stop = threading.Event()
                def sampler():
                    while not stop.wait(.025):
                        tree = rss_tree(client.p.pid)
                        try:
                            server = next(int(line.split()[1])*1024 for line in Path(f'/proc/{client.p.pid}/status').read_text().splitlines() if line.startswith('VmRSS:'))
                        except (OSError,StopIteration):
                            server = 0
                        peak[0] = max(peak[0],server)
                        peak[1] = max(peak[1],max(0,tree-server))
                        peak[2] = max(peak[2],tree)
                thread = threading.Thread(target=sampler,daemon=True);thread.start()
                started = time.monotonic()
                arch = client.call('get_architecture')
                metrics['cold_index_ms'] = (time.monotonic() - started) * 1000
                assert not [d for d in arch['diagnostic_samples'] if d['severity'] == 'error'], arch
                lookup = client.call('search_symbol', query='load', file='typescript/service.ts')
                target = lookup['rows'][0][0]
                durations=[]
                for _ in range(31):
                    started = time.monotonic()
                    client.call('search_symbol',query='load',file='typescript/service.ts')
                    durations.append((time.monotonic()-started)*1000)
                changed = root/'typescript/view.tsx'
                changed.write_text('// matched runtime update\n'+changed.read_text())
                started=time.monotonic();client.call('index_repository')
                metrics['update_ms']=(time.monotonic()-started)*1000
                stop.set();thread.join()
                metrics['warm_queries']=dict(samples=31,p50_ms=statistics.median(durations),p95_ms=sorted(durations)[29],scope='within reconciliation interval; includes revision read; source/render verification depends on operation')
                metrics['rss']=dict(sample_interval_ms=25,server_peak_bytes=peak[0] or None,provider_tree_peak_bytes=peak[1] or None,total_tree_peak_bytes=peak[2] or None,scope='Linux sampled resident peaks during matched cold/index/search/update phases; excludes initialization and unequal feature replays; may miss transients; not allocations')
                args = dict(target=target, intent='change_signature', options={'added_parameters':['locale']})
                legacy = pages(client, args)
                metrics['signature_legacy'] = dict(pages=len(legacy), chars=sum(size(p) for p in legacy), records=sum(len(p['evidence']['rows']) for p in legacy))
                if version == 'C':
                    views = {}
                    for view in ['locations','contracts','edit_context','full_evidence']:
                        gathered = pages(client, dict(args, view=view))
                        assert sum(len(p['evidence']['rows']) for p in gathered) == metrics['signature_legacy']['records']
                        if view == 'locations':
                            assert all(not f['snippets'] for p in gathered for f in p['files'])
                        views[view] = dict(pages=len(gathered), chars=sum(size(p) for p in gathered), records=sum(len(p['evidence']['rows']) for p in gathered))
                    metrics['signature_views'] = views
                    budgets = {}
                    for limit in [512,1024,2048]:
                        raw = client.request('tools/call', dict(name='inspect_change',arguments=dict(args,view='locations',budget={'max_tokens':limit})))
                        value = json.loads(raw['content'][0]['text'])
                        if raw.get('isError'):
                            budgets[str(limit)] = dict(error=value['error'], recovery_explicit='new request' in value['error'])
                        else:
                            gathered = pages(client, dict(args,view='locations',budget={'max_tokens':limit}))
                            assert all(p['token_budget']['estimated_tokens'] <= limit for p in gathered)
                            budgets[str(limit)] = dict(pages=len(gathered), chars=sum(size(p) for p in gathered), records=sum(len(p['evidence']['rows']) for p in gathered))
                    metrics['exploratory_estimate_budgets'] = budgets
                    first = client.call('inspect_change', **dict(args,view='edit_context'))
                    window_ids = [s['window_id'] for f in first['files'] for s in f['snippets']]
                    assert window_ids
                    context = {k:first['context'][k] for k in ['root_id','generation','health_fingerprint','environment_fingerprint']}
                    context.update(epoch='native-1', known_windows=window_ids)
                    delta = client.call('inspect_change', **dict(args,view='edit_context',context=context))
                    assert delta['evidence']['rows'] == first['evidence']['rows']
                    assert all(s.get('acknowledged') for f in delta['files'] for s in f['snippets'])
                    restored = client.call('inspect_change', **dict(args,view='edit_context',context=dict(context,rehydrate=True)))
                    assert [s.get('text') for f in restored['files'] for s in f['snippets']] == [s.get('text') for f in first['files'] for s in f['snippets']]
                    metrics['acknowledgement'] = dict(first_chars=size(first),acknowledged_chars=size(delta),rehydrated_chars=size(restored),windows=len(window_ids))
                    flow_target = client.call('search_symbol',query='entry',file='typescript/flow.ts')['rows'][0][0]
                    destination = client.call('search_symbol',query='destination',file='typescript/flow.ts')['rows'][0][0]
                    flow = client.call('inspect_change',target=flow_target,intent='trace_flow',options={'destination':destination},view='locations',depth=5)
                    assert flow['facts']['destination_found']
                    assert not any('::side#' in r[0] for r in flow['symbols']['rows'])
                    metrics['destination_trace'] = dict(chars=size(flow),records=len(flow['evidence']['rows']))
                    lexical = {}
                    for expand in ['none','dependencies']:
                        value = client.call('search_symbol',query='negative quantities',mode='lexical',expand=expand,limit=5)
                        assert any(r[0] == 'dart/total.dart' for r in value['rows'])
                        lexical[expand] = dict(chars=size(value),candidates=len(value['rows']),relations=len(value['expansion']['relations']),index=value['index'])
                    lexical['current_name_search'] = dict(matches=client.call('search_symbol',query='negative quantities')['total'])
                    anchored = client.call('search_symbol',query='load',mode='lexical',expand='dependencies',file='typescript/service.ts',limit=2)
                    assert anchored['expansion']['relations']
                    lexical['anchored_expansion'] = dict(chars=size(anchored),relations=len(anchored['expansion']['relations']))
                    metrics['lexical'] = lexical
                    metrics['server'] = client.call('status',section='metrics')
                result['conditions'][version] = metrics
            finally:
                if 'stop' in locals():
                    stop.set();thread.join()
                client.close()
    with tempfile.TemporaryDirectory(prefix='pcg selective tools ') as temp:
        root = Path(temp)
        shutil.copytree(fixture/'typescript',root,dirs_exist_ok=True)
        (root/'polycodegraph.json').write_text(json.dumps(dict(config,watch=False)))
        client=Client(binary.resolve(),root,extra_args=('--tool-profile','agent'))
        try:
            schema=client.request('tools/list',{})
            assert len(schema['tools']) == 5
            discovery=client.call('status',section='tools',tool='blast_radius')
            assert discovery['tools'][0]['name'] == 'blast_radius'
            target=client.call('search_symbol',query='load')['rows'][0][0]
            client.call('blast_radius',target=target)
            result['agent_profile']=dict(schema_chars=size(schema),tools=5,discovery_chars=size(discovery),hidden_alias_call_verified=True)
        finally:client.close()
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['binary','baseline','config','baseline-config','output']:
        parser.add_argument('--'+name,type=Path,required=True)
    a=parser.parse_args()
    a.output.write_text(json.dumps(run(a.binary,a.baseline,json.loads(a.config.read_text()),json.loads(a.baseline_config.read_text())),indent=2)+'\n')
