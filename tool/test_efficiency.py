"""Deterministic accounting/boundary/evaluator tests, never model experiments."""
import copy
import unittest
from efficiency_usage import normalize, requests, verify, codex_metadata
from efficiency_benchmark import evaluate, ORDERS, check_snapshot
from efficiency_client import Observer


def event(identity='r1', provider='anthropic'):
    return dict(request_id=identity,provider=provider,model='fixed',effort='high',usage=dict(input_tokens=10,cache_read_input_tokens=20,cache_creation_input_tokens=5,output_tokens=3))


class Accounting(unittest.TestCase):
    def test_anthropic_all_input_and_unknown_reasoning(self):
        usage=normalize('anthropic',event()['usage'])
        self.assertEqual(usage['input_tokens'],35)
        self.assertEqual(usage['uncached_input_tokens'],15)
        self.assertEqual(usage['total_tokens'],38)
        self.assertIsNone(usage['reasoning_output_tokens'])
        self.assertEqual(usage['raw_usage'],event()['usage'])

    def test_subsets_and_conflicting_duplicates(self):
        self.assertEqual(requests([event(),event()])['model_requests'],1)
        wrong=event();wrong['usage']['input_tokens']=11
        with self.assertRaises(ValueError):requests([event(),wrong])
        with self.assertRaises(ValueError):normalize('openai',dict(input_tokens=10,cached_input_tokens=11,output_tokens=2))
        with self.assertRaises(ValueError):normalize('openai',dict(input_tokens=10,output_tokens=2,reasoning_output_tokens=3))

    def test_raw_usage_recomputed_and_symlinks_rejected(self):
        measured = requests([event()])
        measured['totals']['uncached_input_tokens'] = 0
        with self.assertRaises(ValueError):
            verify(measured)
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base = root / 'snapshot'
            base.mkdir()
            (base / 'file').symlink_to(root / 'elsewhere')
            with self.assertRaises(ValueError):
                check_snapshot(base, {}, root)

    def test_codex_cumulative_metadata_remains_verifiable_without_messages(self):
        from test_token_usage import event as cumulative_event
        raw = [dict(type='turn_context',payload=dict(model='fixed',effort='high',source='do not retain')),cumulative_event(1),cumulative_event(1),cumulative_event(2,1),cumulative_event(1)]
        measured = codex_metadata(raw)
        self.assertEqual(measured['counter_resets'],1)
        self.assertEqual(measured['model_requests'],3)
        self.assertEqual(verify(measured)['totals']['uncached_input_tokens'],150)
        self.assertNotIn('source',str(measured))
        measured['totals']['input_tokens'] = 0
        with self.assertRaises(ValueError):verify(measured)

    def test_wire_and_actual_prompt_are_distinct(self):
        observer=Observer();value=dict(intent='rename',files=[dict(file='a.ts',snippets=[dict(window_id='key',text='abc')])])
        import json
        wire=dict(content=[dict(type='text',text=json.dumps(value))],structuredContent=value,isError=False)
        observer.observe_wire(wire);observer.inject(wire,'structured')
        observer.observe_wire(wire);observer.inject(wire,'text')
        observer.ledger.compaction();observer.inject(wire,'structured')
        result=observer.summary()
        self.assertEqual(result['mcp_calls'],2)
        self.assertEqual(result['wire_duplicate_objects'],2)
        self.assertEqual(result['new_context_chars'],3)
        self.assertEqual(result['repeated_context_chars'],3)
        self.assertEqual(result['rehydrated_context_chars'],3)
        observer.inject(wire,'transformed','{}')
        self.assertEqual(observer.summary()['rehydrated_context_chars'],3)
        self.assertFalse(observer.summary()['context_identity_complete'])

    def test_actual_text_and_both_representations_count_the_inserted_windows(self):
        import json
        value=dict(intent='rename',files=[dict(file='a.ts',snippets=[dict(window_id='key',text='abc')])])
        wire=dict(content=[dict(type='text',text=json.dumps(value))],structuredContent=value)
        observer=Observer();observer.inject(wire,'both')
        self.assertEqual(observer.summary()['new_context_chars'],3)
        self.assertEqual(observer.summary()['repeated_context_chars'],3)
        self.assertEqual(observer.summary()['pages'],1)
        observer=Observer()
        # The structured object on the wire was not inserted by this text-only client.
        wire['structuredContent']=dict(intent='rename',files=[])
        observer.inject(wire,'text')
        self.assertEqual(observer.summary()['new_context_chars'],3)

    def test_primitive_source_and_explicit_transformed_inventory(self):
        import json
        observer=Observer(source_identity=lambda file: ('root','hash'))
        source=dict(file='a.ts',start_line=1,end_line=1,text='abc',truncated=False)
        wire=dict(content=[dict(type='text',text=json.dumps(dict(snippet=source)))])
        observer.inject(wire,'text')
        observer.ledger.external('root','hash',1,1,'abc')
        self.assertEqual(observer.summary()['new_context_chars'],3)
        self.assertEqual(observer.summary()['repeated_context_chars'],3)
        observer.inject({},'transformed','abc',prompt_windows=[source])
        self.assertEqual(observer.summary()['repeated_context_chars'],6)
        self.assertTrue(observer.summary()['context_identity_complete'])
        observer.inject({},'transformed','no source',prompt_windows=[])
        self.assertTrue(observer.summary()['context_identity_complete'])

    def test_failed_attempts_stay_in_primary_and_zero_success_is_undefined(self):
        manifest=dict(primary_metric='uncached_input_per_accepted_task',tasks=[dict(id=str(i),order=o,**{'class':'local' if i==0 else 'structural'}) for i,o in enumerate(ORDERS)],limits=dict(attempts_per_cell=2),executor=dict(model='fixed',effort='high',isolation_verifier_sha256='proof'),conditions={c:dict(schema_sha256='schema',harness_sha256='harness',model_schema_sha256='schema',loaded_graph_instructions_sha256='harness') for c in 'BC'})
        runs=[]
        for task in manifest['tasks']:
            for c in task['order']:
                client=dict(actual_schema_sha256=None if c=='A' else 'schema',loaded_graph_instructions_sha256=None if c=='A' else 'harness',response_representation=['structured'],model_requests=1,mcp_calls=0 if c=='A' else 1,external_reads=0,new_context_chars=0,repeated_context_chars=0,rehydrated_context_chars=0,pages=0,expansions=0,compactions=0,context_identity_complete=True)
                runs.append(dict(task_id=task['id'],condition=c,attempt=1,success=True,usage=requests([event()]),client=client,isolation=dict(verified=True,verifier_sha256='proof',probe_artifact_sha256='probe'),duration_ms=1))
        failed=copy.deepcopy(runs[0]);failed['success']=False;runs[0]['attempt']=2;runs.insert(0,failed)
        result=evaluate(manifest,runs)
        self.assertEqual(result['aggregates']['A']['primary_per_accepted_task'],17.5)
        self.assertEqual(len(result['failures']),1)
        self.assertEqual(result['gates']['G2']['status'],'passed')
        self.assertFalse(result['target_reached'])
        for r in runs:r['success']=False
        result=evaluate(manifest,runs)
        self.assertIsNone(result['aggregates']['A']['primary_per_accepted_task'])
        self.assertFalse(result['target_reached'])

    def test_missing_boundary_is_not_measured_as_savings(self):
        manifest=dict(primary_metric='uncached_input_per_accepted_task',tasks=[dict(id=str(i),order=o,**{'class':'local'}) for i,o in enumerate(ORDERS)],limits=dict(attempts_per_cell=1),executor=dict(model=None,effort=None,isolation_verifier_sha256=None),conditions={c:dict(schema_sha256=None,harness_sha256=None,model_schema_sha256=None,loaded_graph_instructions_sha256=None) for c in 'BC'})
        result=evaluate(manifest,[])
        self.assertEqual(result['gates']['G2']['status'],'not_measured')
        self.assertEqual(result['model_runs'],0)
        self.assertFalse(result['target_reached'])


if __name__=='__main__':unittest.main()
