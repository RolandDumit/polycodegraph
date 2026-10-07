"""Synthetic accounting and adapter regressions; never AI measurements."""
import copy
import json
import unittest
import tempfile
import hashlib
from pathlib import Path
from efficiency_benchmark import evaluate_post08, validate_manifest
from efficiency_client import Observer, LeanAdapter
from efficiency_usage import requests
from test_efficiency import event


def manifest():
    return dict(protocol_revision='post08-v1',primary_metric='uncached_input_per_accepted_task',
                tasks=[dict(id='t-r1',base_task_id='t',replica=1,order='ABC',oracle_digest='oracle',**{'class':'structural'})],
                limits=dict(attempts_per_cell=2),executor=dict(model='fixed',effort='high',isolation_verifier_sha256='proof'),
                conditions={c:dict(label=c,model_schema_sha256='schema',loaded_graph_instructions_sha256='instructions') for c in 'ABC'})


def record(condition, accepted=True):
    return dict(task_id='t-r1',condition=condition,attempt=1,success=accepted,usage=requests([event()]),
                oracle_sha256='oracle',isolation=dict(verified=True,verifier_sha256='proof',probe_artifact_sha256='probe'),
                client=dict(mcp_calls=0 if condition=='A' else 1,actual_schema_sha256=None if condition=='A' else 'schema',
                            loaded_graph_instructions_sha256=None if condition=='A' else 'instructions',
                            response_representation=['structured'],context_identity_complete=True))


def page(remaining=0, root='root'):
    return dict(format='pcg-lean-1',intent='rename',snapshot=dict(root_id=root,generation='g',health_fingerprint='h'),
                completion=dict(required_inventory=dict(state='incomplete' if remaining else 'complete',remaining_known=remaining)),
                sources=[dict(file='a.ts',source_hash='hash',windows=[dict(start_line=1,end_line=1,text='target();')])],
                next_cursor='cursor' if remaining else None)


def wire(value):
    return dict(content=[dict(type='text',text=json.dumps(value))],structuredContent=value,isError=False)


class Post08(unittest.TestCase):
    def test_zero_authorization_blocks_launch_and_primary_is_frozen(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);snapshot=root/'fixture';snapshot.mkdir();(snapshot/'source.txt').write_text('source')
            m=manifest();m['tasks'][0].update(snapshot='fixture',source_hashes={'source.txt':hashlib.sha256(b'source').hexdigest()},prompt='task',correctness_criteria=['unchanged quality'])
            m['limits'].update(authorized_runs=0,authorized_model_requests=0,authorized_uncached_input_tokens=0,timeout_seconds=1200)
            m['conditions']['A']['graph_enabled']=False
            self.assertTrue(any('not authorized' in item for item in validate_manifest(m,root)))
            with self.assertRaisesRegex(ValueError,'launch blocked'):
                validate_manifest(m,root,launch=True)
            m['primary_metric']='money_per_accepted_task'
            with self.assertRaisesRegex(ValueError,'freezes uncached input'):
                validate_manifest(m,root)

    def test_failed_attempts_and_unknown_timeout_are_included(self):
        m=manifest(); runs=[record('A',False),record('A'),record('B'),record('C')];runs[1]['attempt']=2
        result=evaluate_post08(m,runs)
        self.assertEqual(result['aggregates']['A']['primary_per_accepted_task'],30)
        self.assertEqual(result['aggregates']['A']['consumption_per_assigned_task']['uncached_input_tokens'],30)
        runs[0]['usage']={}
        result=evaluate_post08(m,runs)
        self.assertIsNone(result['aggregates']['A']['primary_per_accepted_task'])
        self.assertEqual(result['decision'],'inconclusive')
        self.assertFalse(result['consumption_evidence']['comparable'])

    def test_consumption_is_separate_from_attribution_and_no_runs_are_null(self):
        m=manifest(); runs=[record(c) for c in 'ABC'];runs[2]['client']['context_identity_complete']=False
        result=evaluate_post08(m,runs)
        self.assertTrue(result['consumption_evidence']['comparable'])
        self.assertFalse(result['attribution_evidence']['complete'])
        result=evaluate_post08(m,[])
        self.assertEqual(result['status'],'not_run')
        self.assertIsNone(result['comparisons']['C/A'])
        self.assertIsNone(result['aggregates']['C']['components']['input_tokens'])
        self.assertIsNone(result['aggregates']['C']['primary_per_accepted_task'])

    def test_one_lean_representation_is_inserted_with_exact_source_identity(self):
        observer=Observer(); seen=[]
        def call(name, arguments):
            seen.append((name, arguments));return wire(page(1 if len(seen)==1 else 0))
        adapter=LeanAdapter(call,observer)
        result=adapter.collect(dict(intent='rename',target='target'))
        self.assertTrue(result['complete'])
        self.assertEqual(seen[1][1]['cursor'],'cursor')
        self.assertEqual(observer.summary()['mcp_calls'],2)
        self.assertEqual(observer.summary()['pages'],2)
        self.assertEqual(observer.summary()['injected_chars'],len(result['text']))
        self.assertTrue(observer.summary()['context_identity_complete'])
        self.assertNotIn('structuredContent',result['text'])
        self.assertEqual(observer.source_ledger[0]['file'],'a.ts')
        self.assertEqual(observer.source_ledger[1]['state'],'repeated')
        observer.ledger.compaction();adapter.collect(dict(intent='rename',target='target'))
        self.assertEqual(observer.source_ledger[-1]['state'],'rehydrated')

    def test_changed_snapshot_discards_all_prior_source_and_budgets_are_bounded(self):
        observer=Observer(); count=[0]
        def call(name, arguments):
            count[0]+=1;return wire(page(1,root='root' if count[0]==1 else 'other'))
        result=LeanAdapter(call,observer).collect(dict(intent='rename',target='target'))
        self.assertFalse(result['complete'])
        self.assertEqual(json.loads(result['text'])['pages'],[])
        self.assertEqual(observer.summary()['new_context_chars'],0)
        result=LeanAdapter(lambda n,a:wire(page(1)),Observer(),max_pages=1).collect(dict(intent='rename',target='target'))
        self.assertEqual(result['reason'],'collector_page_budget')
        self.assertFalse(result['complete'])
        huge=page();huge['sources'][0]['windows'][0]['text']='x'*4000
        result=LeanAdapter(lambda n,a:wire(huge),Observer(),max_chars=3000).collect(dict(intent='rename',target='target'))
        self.assertEqual(result['reason'],'collector_context_budget')
        with self.assertRaises(ValueError):LeanAdapter(call,Observer(),max_pages=65)

    def test_errors_are_returned_once_and_root_changes_never_suppress_text(self):
        observer=Observer()
        result=LeanAdapter(lambda n,a:dict(content=[dict(type='text',text='{"error":"wrong scope"}')],isError=True),observer).collect(dict(intent='review_change',target='bad.ts'))
        self.assertEqual(result['reason'],'tool_error')
        self.assertEqual(observer.summary()['errors'],1)
        observer=Observer()
        for root in ['root','other']:
            result=LeanAdapter(lambda n,a:wire(page(root=root)),observer).collect(dict(intent='rename',target='target'))
            self.assertIn('target();',result['text'])
        self.assertEqual(observer.summary()['new_context_chars'],len('target();')*2)

    def test_cancel_and_wire_limits_never_certify_a_partial_inventory(self):
        result=LeanAdapter(lambda n,a:self.fail('cancelled collector called server'),Observer(),cancelled=lambda:True).collect(dict(intent='rename',target='target'))
        self.assertEqual(result['reason'],'cancelled')
        self.assertFalse(result['complete'])
        huge=page();huge['sources'][0]['windows'][0]['text']='x'*2000
        observer=Observer()
        result=LeanAdapter(lambda n,a:wire(huge),observer,max_wire_bytes=1024).collect(dict(intent='rename',target='target'))
        self.assertEqual(result['reason'],'collector_wire_budget')
        self.assertFalse(result['complete'])
        self.assertEqual(observer.summary()['mcp_calls'],1)
        self.assertEqual(json.loads(result['text'])['pages'],[])


if __name__=='__main__':unittest.main()
