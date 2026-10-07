"""Synthetic comparison-v1 tests. No credentials, network, model or AI usage."""
import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from efficiency_benchmark import check_snapshot, evaluate, prepare, run, validate_manifest, write
from efficiency_comparison import campaign_lock, cell_id, cells, digest, identity, journal_append, journal_read, normalize_attempt, schedule
from efficiency_usage import requests
from test_efficiency import event
from test_token_usage import event as cumulative_event


def manifest(root, n=4, replicas=1, task_count=2):
    snapshot = root / 'source'; snapshot.mkdir(exist_ok=True)
    (snapshot / 'code.txt').write_text('source')
    command = root / 'executor'; command.write_text('unused mock executor')
    oracle = root / 'oracle'; oracle.write_text('unused independent oracle')
    names = list('ABCDE')[:n]
    tasks = [dict(id=f't{i}', snapshot='source', source_hashes={'code.txt': hashlib.sha256(b'source').hexdigest()},
                  prompt='change code', correctness_criteria=['independent check'], oracle_digest=digest(oracle),
                  **{'class': 'local' if i == 0 else 'structural'}) for i in range(task_count)]
    conditions = [dict(id=c, label=c, graph_enabled=c != 'A', treatment_sha256=c, binary_sha256='binary',
                       source_identity='source', config_sha256='config', harness_sha256='harness', schema_sha256='schema',
                       provider_artifacts={str(command): digest(command)},
                       provider_source_artifacts={str(snapshot/'code.txt'): digest(snapshot/'code.txt')}) for c in names]
    return dict(protocol_revision='comparison-v1', campaign_id='synthetic', primary_metric='uncached_input_per_accepted_task',
        snapshot_root=str(root), tasks=tasks, conditions=conditions, schedule=schedule([t['id'] for t in tasks], names, replicas),
        executor=dict(model='fixed', effort='high', version='test', command_sha256=digest(command),
                      isolation_verifier_sha256='proof', base_harness_sha256='base', isolation_verified=True,
                      credential_channel_verified=True, mcp_client_verified=True, oracle_verified=True),
        frozen_artifacts=[dict(path=str(command), sha256=digest(command), role='executor')],
        limits=dict(attempts_per_cell=2, timeout_seconds=30, max_model_requests=40, max_uncached_input_tokens=120000,
                    max_input_tokens=2000000, max_output_tokens=30000, concurrency=1,
                    enforcement=dict(timeout_seconds='enforced', max_model_requests='observed_only',
                                     max_uncached_input_tokens='observed_only', max_input_tokens='observed_only', max_output_tokens='observed_only')),
        budget=dict(execution_enabled=True, approved_phases=['P2a', 'P2b'], max_runs=100, max_uncached_input_tokens=2000000,
                    authorization='synthetic test only', granularity='after_attempt', preparation_max_runs=0, judge_max_runs=0),
        analysis=dict(reference='A', candidate='D' if 'D' in names else None, previous='C' if 'C' in names else None,
                      comparisons=[[a, b] for a, b in [('D', 'A'), ('D', 'C'), ('D', 'B'), ('C', 'A'), ('B', 'A'), ('C', 'B')] if a in names and b in names],
                      seed=20261006, bootstrap_resamples=100))


def record(m, cell, cost=15, accepted=True, attempt=1):
    task, replica, condition, phase = cell
    raw = event(f'{task}-{replica}-{condition}-{attempt}'); raw['usage']['input_tokens'] = cost-5
    return dict(campaign_id=m['campaign_id'], cell_id=cell_id(m, task, replica, condition), task_id=task, replica=replica,
        condition=condition, phase=phase, attempt=attempt, success=accepted, status='completed', usage=requests([raw]),
        oracle_sha256=m['tasks'][0]['oracle_digest'], isolation=dict(verified=True, verifier_sha256='proof', probe_artifact_sha256='probe'),
        client=dict(graph_mcp_calls=0 if condition == 'A' else 1, other_mcp_calls=2, all_tool_calls=3,
                    graph_artifacts_visible=condition != 'A', graph_surface_sha256=None if condition == 'A' else 'schema',
                    graph_harness_sha256=None if condition == 'A' else 'harness', context_identity_complete=True))


class Comparison(unittest.TestCase):
    def test_campaign_lock_excludes_concurrent_writer_and_releases(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'campaign.lock'
            with campaign_lock(path):
                with self.assertRaises(OSError):
                    with campaign_lock(path):
                        self.fail('two campaign writers acquired the same lock')
            with campaign_lock(path):
                pass

    def test_snapshot_root_alias_preserves_internal_symlink_rejection(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            trusted = root / 'trusted'; trusted.mkdir()
            base = trusted / 'snapshot'; base.mkdir()
            source = base / 'code.txt'; source.write_text('source')
            alias = root / 'alias'
            try:
                alias.symlink_to(root, target_is_directory=True)
            except OSError:
                self.skipTest('host does not permit test symlink creation')
            expected = {'code.txt': digest(source)}
            check_snapshot(base, expected, alias / 'trusted')
            internal = trusted / 'internal'
            internal.symlink_to(base, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'symlink snapshot ancestor'):
                check_snapshot(internal, expected, trusted)
            external = root / 'external'; external.mkdir()
            with self.assertRaisesRegex(ValueError, 'outside declared repository'):
                check_snapshot(external, {}, trusted)

    def test_n_conditions_and_absent_candidate(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for n in (2, 3, 4, 5):
                m = manifest(root, n)
                self.assertEqual(validate_manifest(m, root), [])
                result = evaluate(m, [record(m, c) for c in cells(m)])
                self.assertEqual(len(result['aggregates']), n)
                self.assertTrue(result['consumption_evidence']['comparable'])
                self.assertEqual(result['executed_cells'], n*2)
                self.assertEqual(result['decision'], 'NEAR_PARITY_UNCERTAIN' if n >= 4 else 'INCONCLUSIVE')

    def test_duplicates_and_unsafe_ids_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); m = manifest(root)
            for mutate in (lambda x: x['conditions'].append(x['conditions'][0]),
                           lambda x: x['tasks'].append(x['tasks'][0]),
                           lambda x: x['schedule'].append(x['schedule'][0]),
                           lambda x: x['conditions'][1].update(treatment_sha256='A'),
                           lambda x: x.update(campaign_id='../escape')):
                wrong = copy.deepcopy(m); mutate(wrong)
                with self.assertRaises(ValueError): validate_manifest(wrong, root)
            runs = [record(m, c) for c in cells(m)]
            runs.insert(1, copy.deepcopy(runs[0]))
            with self.assertRaisesRegex(ValueError, 'attempt'): evaluate(m, runs)

    def test_balance_and_replicas(self):
        blocks = schedule(list('abcdef'), list('ABCD'), 2)
        self.assertEqual(len(blocks), 12)
        for position in range(4):
            self.assertEqual({c: sum(b['order'][position] == c for b in blocks) for c in 'ABCD'}, dict.fromkeys('ABCD', 3))
        self.assertEqual(blocks, schedule(list('abcdef'), list('ABCD'), 2))

    def test_failed_retry_cost_zero_acceptance_and_partial_denominator(self):
        with tempfile.TemporaryDirectory() as temp:
            m = manifest(Path(temp)); cs = list(cells(m))
            runs = [record(m, cs[0], accepted=False), record(m, cs[0], attempt=2)] + [record(m, c) for c in cs[1:]]
            result = evaluate(m, runs)
            cond = cs[0][2]
            self.assertEqual(result['aggregates'][cond]['primary_per_accepted_task'], 22.5)
            for r in runs: r['success'] = False
            result = evaluate(m, runs)
            self.assertIsNone(result['aggregates'][cond]['primary_per_accepted_task'])
            self.assertEqual(result['comparisons']['D/A']['uncertainty']['status'], 'unstable_zero_acceptance')
            result = evaluate(m, [record(m, cs[0])])
            self.assertEqual(result['status'], 'partial')
            self.assertEqual(result['aggregates'][cond]['success_rate'], 1)
            self.assertEqual(result['aggregates'][cond]['consumption_per_executed_cell']['uncached_input_tokens'], 15)
            self.assertEqual(result['decision'], 'HOLD_MEASUREMENT')

    def test_unknown_timeout_is_not_zero_and_attribution_separate(self):
        with tempfile.TemporaryDirectory() as temp:
            m = manifest(Path(temp)); runs = [record(m, c) for c in cells(m)]
            runs[0]['client']['context_identity_complete'] = False
            result = evaluate(m, runs)
            self.assertTrue(result['consumption_evidence']['comparable'])
            self.assertFalse(result['attribution_evidence']['complete'])
            runs[0].update(status='timeout', success=False, usage=None)
            result = evaluate(m, runs)
            self.assertIsNone(result['aggregates'][runs[0]['condition']]['components']['uncached_input_tokens'])
            self.assertEqual(result['decision'], 'HOLD_MEASUREMENT')
            self.assertIsNone(evaluate(m, [])['comparisons']['D/A']['ratio'])

    def test_ordinary_mcp_in_a_is_allowed_graph_is_not(self):
        with tempfile.TemporaryDirectory() as temp:
            m = manifest(Path(temp)); runs = [record(m, c) for c in cells(m)]
            self.assertTrue(evaluate(m, runs)['isolation_evidence']['verified'])
            next(r for r in runs if r['condition'] == 'A')['client']['graph_mcp_calls'] = 1
            result = evaluate(m, runs)
            self.assertFalse(result['isolation_evidence']['verified'])
            self.assertEqual(result['decision'], 'HOLD_MEASUREMENT')

    def test_worse_candidate_negative_verdict_not_success(self):
        with tempfile.TemporaryDirectory() as temp:
            m = manifest(Path(temp)); runs = [record(m, c, cost=30 if c[2] == 'D' else 15) for c in cells(m)]
            result = evaluate(m, runs)
            self.assertEqual(result['decision'], 'REGRESSION')
            self.assertEqual(result['comparisons']['D/A']['ratio'], 2)
            self.assertTrue(result['local_guard_alert'])
            self.assertEqual(result['comparisons']['D/A']['uncertainty']['interval95'], [2, 2])

    def test_request_parent_child_and_turn_cumulative_not_double_counted(self):
        e = event()
        observed = dict(usage_streams=[dict(id='parent', scope='inclusive_attempt', usage_events=[e]),
                                      dict(id='child', scope='disjoint_requests', usage_events=[e])])
        self.assertEqual(normalize_attempt(observed)['model_requests'], 1)
        observed['usage_streams'][0]['scope'] = 'disjoint_requests'
        self.assertEqual(normalize_attempt(observed)['model_requests'], 1)
        observed['usage_streams'][1]['usage_events'] = [event('r2')]
        self.assertEqual(normalize_attempt(observed)['totals']['uncached_input_tokens'], 30)
        with self.assertRaises(ValueError): normalize_attempt(dict(usage_events=[e], codex_usage_metadata=[]))
        cumulative = [dict(type='turn_context', payload=dict(model='fixed', effort='high')), cumulative_event(1), cumulative_event(1), cumulative_event(2, 1), cumulative_event(1)]
        self.assertEqual(normalize_attempt(dict(codex_usage_metadata=cumulative))['totals']['uncached_input_tokens'], 150)

    def test_unknown_cache_write_and_reasoning_subset(self):
        with tempfile.TemporaryDirectory() as temp:
            m = manifest(Path(temp)); r = record(m, next(cells(m)))
            raw = dict(request_id='r', provider='openai', model='fixed', effort='high',
                       usage=dict(input_tokens=10, cached_input_tokens=5, output_tokens=3, reasoning_output_tokens=2))
            r['usage'] = requests([raw])
            a = evaluate(m, [r])['aggregates'][r['condition']]
            self.assertEqual(a['components']['total_tokens'], 13)
            self.assertIsNone(a['components']['cache_creation_input_tokens'])
            del raw['usage']['cached_input_tokens']
            with self.assertRaises(ValueError): requests([raw])

    def test_prepare_no_overwrite_and_no_oracle_in_solver_input(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); m = manifest(root); work = root/'campaign'
            jobs = prepare(m, root, work)
            self.assertEqual(len(jobs['jobs']), 8)
            self.assertNotIn('correctness_criteria', json.loads(Path(jobs['jobs'][0]['request']).read_text()))
            with self.assertRaisesRegex(ValueError, 'overwrite'): prepare(m, root, work)

    def test_partial_executor_usage_remains_unknown(self):
        with self.assertRaisesRegex(ValueError, 'partial/unknown usage'):
            normalize_attempt(dict(usage_complete=False, usage_events=[event()]))

    def test_launch_denied_no_budget_or_frozen_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); m = manifest(root); work = root/'campaign'; jobs = prepare(m, root, work)
            m['budget']['execution_enabled'] = False
            with patch('efficiency_comparison.bounded_process') as model:
                with self.assertRaisesRegex(ValueError, 'not authorized'): run(m, jobs, root/'executor', root/'oracle', work)
                model.assert_not_called()
            m['budget']['execution_enabled'] = True
            (root/'executor').write_text('mutated')
            with self.assertRaisesRegex(ValueError, 'changed after freeze'): validate_manifest(m, root, launch=True)

    def test_provider_source_mutation_is_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); m = manifest(root)
            # A provider source outside the application snapshot must also be frozen.
            source = root/'provider.py'; source.write_text('resolver')
            m['conditions'][1]['provider_source_artifacts'] = {str(source): digest(source)}
            self.assertEqual(validate_manifest(m, root), [])
            source.write_text('different resolver')
            with self.assertRaisesRegex(ValueError, 'provider_source_artifacts changed'): validate_manifest(m, root, launch=True)

    def test_resume_only_not_started_budget_stop_and_unknown_interruption(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); m = manifest(root); m['budget']['max_runs'] = 1
            work = root/'campaign'; jobs = prepare(m, root, work)
            calls = []
            def execute(command, payload, local, label, timeout):
                if label == 'oracle': return dict(accepted=True, reason_code='independent')
                calls.append(payload['attempt_id'])
                r = record(m, next(cells(m)))
                return dict(attempt_id=payload['attempt_id'], usage_events=[event()], answer='answer', client_measurement=r['client'], isolation=r['isolation'])
            with patch('efficiency_comparison.bounded_process', side_effect=execute):
                first = run(m, jobs, root/'executor', root/'oracle', work)
                self.assertEqual(len(first), 1)
                second = run(m, jobs, root/'executor', root/'oracle', work)
                self.assertEqual(first, second)
                self.assertEqual(len(calls), 1)
            journal = root/'interrupted.jsonl'; metadata = {k: first[0][k] for k in ('campaign_id', 'cell_id', 'task_id', 'replica', 'condition', 'phase', 'attempt')}
            journal_append(journal, dict(event='started', attempt_id='new/a1', identity=metadata))
            records, started, interrupted = journal_read(journal)
            self.assertTrue(interrupted)
            self.assertIsNone(records[0]['usage'])
            self.assertFalse(records[0]['success'])

    def test_executor_timeout_stops_and_accounts_unknown(self):
        import subprocess
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); m = manifest(root); work = root/'campaign'; jobs = prepare(m, root, work)
            with patch('efficiency_comparison.bounded_process', side_effect=subprocess.TimeoutExpired('synthetic', 1)) as execute:
                runs = run(m, jobs, root/'executor', root/'oracle', work)
                self.assertEqual(execute.call_count, 1)
                self.assertEqual(runs[0]['status'], 'timeout')
                self.assertIsNone(runs[0]['usage'])
                with patch('efficiency_comparison.bounded_process') as resumed:
                    self.assertEqual(run(m, jobs, root/'executor', root/'oracle', work), runs)
                    resumed.assert_not_called()


if __name__ == '__main__':
    unittest.main()
