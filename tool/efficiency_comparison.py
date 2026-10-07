"""Comparison-v1 extension of the existing runner, with no model client of its own.

Historical protocols/parsers remain unchanged. All raw data and the append-only
journal belong in an ignored campaign directory. Synthetic tests are not AI runs.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import random
import re
import shutil
import statistics
import subprocess
import time
from pathlib import Path

from efficiency_benchmark import COMPONENTS, bounded_process, check_snapshot, digest, read, valid_money, write
from efficiency_usage import codex_metadata, requests, verify


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def safe_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,95}', value):
        raise ValueError('unsafe/missing campaign, task or condition ID')
    return value


def condition_map(manifest):
    values = manifest['conditions']
    result = {safe_id(c['id']): c for c in values}
    if not 2 <= len(result) <= 16 or len(result) != len(values):
        raise ValueError('need 2..16 uniquely identified conditions')
    return result


def schedule(task_ids, condition_ids, replicas=2, seed=20261006):
    """Freeze balanced sequences; no assumption about the letters in actual IDs."""
    if not 1 <= replicas <= 16 or not 1 <= len(task_ids) <= 128:
        raise ValueError('bounded task/replica count required')
    ids = list(condition_ids)
    if not 2 <= len(ids) <= 16 or len(set(ids)) != len(ids):
        raise ValueError('invalid condition schedule')
    if len(ids) == 4:
        patterns = ((0, 1, 3, 2), (1, 2, 0, 3), (2, 3, 1, 0), (3, 0, 2, 1))
    elif len(ids) <= 3:
        patterns = tuple(itertools.permutations(range(len(ids))))
    else:
        patterns = tuple(tuple((i + shift) % len(ids) for i in range(len(ids))) for shift in range(len(ids)))
    blocks = [(task, replica) for replica in range(1, replicas + 1) for task in task_ids]
    assignments = [patterns[i % len(patterns)] for i in range(len(blocks))]
    random.Random(seed).shuffle(assignments)
    return [dict(task_id=task, replica=replica, phase='P2a' if replica == 1 else 'P2b',
                 order=[ids[i] for i in pattern]) for (task, replica), pattern in zip(blocks, assignments)]


def cells(manifest):
    for block in manifest['schedule']:
        for condition in block['order']:
            yield (block['task_id'], block['replica'], condition, block['phase'])


def cell_id(manifest, task, replica, condition):
    return f"{manifest['campaign_id']}/{task}/r{replica}/{condition}"


def validate(manifest, repository, launch=False):
    safe_id(manifest['campaign_id'])
    if manifest['primary_metric'] != 'uncached_input_per_accepted_task':
        raise ValueError('comparison-v1 freezes uncached input as primary')
    conditions = condition_map(manifest)
    tasks = {safe_id(t['id']): t for t in manifest['tasks']}
    if not 1 <= len(tasks) <= 128 or len(tasks) != len(manifest['tasks']):
        raise ValueError('duplicate/invalid task identity')
    root = Path(manifest['snapshot_root'])
    if not root.is_absolute() or root.is_symlink():
        raise ValueError('trusted absolute snapshot root required')
    missing = []
    for task in tasks.values():
        check_snapshot(root / task['snapshot'], task['source_hashes'], root)
        if not task.get('prompt') or not task.get('correctness_criteria') or not task.get('class'):
            raise ValueError('missing private task prompt, class or oracle criteria')
        if not task.get('oracle_digest'):
            missing.append(f"{task['id']}: independent oracle identity")
    keys = set()
    if not 1 <= len(manifest['schedule']) <= 2048:
        raise ValueError('bounded nonempty schedule required')
    for block in manifest['schedule']:
        key = (block['task_id'], block['replica'])
        if (key[0] not in tasks or type(key[1]) is not int or not 1 <= key[1] <= 16
                or key in keys or sorted(block['order']) != sorted(conditions)
                or block['phase'] not in ('P1', 'P2a', 'P2b', 'P3')):
            raise ValueError('duplicate/invalid schedule block')
        keys.add(key)
    limits = manifest['limits']
    for field, upper in (('attempts_per_cell', 3), ('timeout_seconds', 1200), ('max_model_requests', 1000),
                         ('max_uncached_input_tokens', 2000000), ('max_input_tokens', 10000000),
                         ('max_output_tokens', 1000000)):
        if type(limits.get(field)) is not int or not 1 <= limits[field] <= upper:
            raise ValueError(f'explicit bounded {field} required')
    if limits.get('concurrency') != 1:
        raise ValueError('comparison-v1 is serial')
    for field in ('timeout_seconds', 'max_model_requests', 'max_uncached_input_tokens', 'max_input_tokens', 'max_output_tokens'):
        if limits.get('enforcement', {}).get(field) not in ('enforced', 'observed_only', 'unsupported'):
            raise ValueError(f'missing real enforcement status: {field}')
    no_graph = manifest['analysis']['reference']
    if no_graph not in conditions or conditions[no_graph].get('graph_enabled') is not False:
        raise ValueError('reference must exclude graph artifacts/schemas/instructions')
    seen = set()
    for name, condition in conditions.items():
        fingerprint = condition.get('treatment_sha256')
        if not fingerprint:
            missing.append(f'{name}: frozen complete treatment identity')
        elif fingerprint in seen:
            raise ValueError('duplicate complete condition identity; deduplicate before launch')
        seen.add(fingerprint)
        if condition.get('graph_enabled'):
            for field in ('binary_sha256', 'source_identity', 'config_sha256', 'harness_sha256', 'schema_sha256'):
                if not condition.get(field):
                    missing.append(f'{name}: {field}')
            if not condition.get('provider_artifacts'):
                missing.append(f'{name}: version-matched provider identities')
            if not condition.get('provider_source_artifacts'):
                missing.append(f'{name}: frozen provider source artifacts')
            for field in ('provider_artifacts', 'provider_source_artifacts'):
                for path, expected in condition.get(field, {}).items():
                    if digest(Path(path)) != expected:
                        raise ValueError(f'{name}: {field} changed after freeze')
    for comparison in manifest['analysis']['comparisons']:
        if len(comparison) != 2 or any(c not in conditions for c in comparison) or comparison[0] == comparison[1]:
            raise ValueError('invalid registered comparison')
    executor = manifest['executor']
    for field in ('model', 'effort', 'version', 'command_sha256', 'isolation_verifier_sha256', 'base_harness_sha256'):
        if not executor.get(field):
            missing.append(f'executor: {field}')
    for field in ('isolation_verified', 'credential_channel_verified', 'mcp_client_verified', 'oracle_verified'):
        if executor.get(field) is not True:
            missing.append(f'executor: {field}')
    if not manifest.get('frozen_artifacts'):
        missing.append('frozen artifacts absent')
    for artifact in manifest.get('frozen_artifacts', []):
        if digest(Path(artifact['path'])) != artifact['sha256']:
            raise ValueError('artifact changed after freeze: ' + artifact['role'])
    budget = manifest['budget']
    if budget.get('execution_enabled') is not True:
        missing.append('AI execution not authorized')
    phases = budget.get('approved_phases', [])
    if not phases or not set(phases) <= {'P1', 'P2a', 'P2b', 'P3'}:
        missing.append('no approved AI phases')
    for field in ('max_runs', 'max_uncached_input_tokens'):
        if type(budget.get(field)) is not int or budget[field] <= 0:
            missing.append(f'budget: explicit positive {field} required')
    if not budget.get('authorization') or budget.get('granularity') != 'after_attempt':
        missing.append('explicit authorization accepting after-attempt control required')
    if type(budget.get('preparation_max_runs')) is not int or budget['preparation_max_runs'] < 0:
        missing.append('explicit preparation AI budget required')
    if budget.get('judge_max_runs') != 0:
        missing.append('comparison-v1 supports deterministic oracles; judge AI budget must be zero')
    if launch and missing:
        raise ValueError('launch blocked: ' + '; '.join(missing))
    return missing


def prepare_campaign(manifest, repository, work):
    validate(manifest, repository)
    if work.exists():
        raise ValueError('refusing to overwrite prepared campaign; resume with run')
    conditions = condition_map(manifest)
    tasks = {t['id']: t for t in manifest['tasks']}
    jobs = []
    work.mkdir(parents=True)
    for task_id, replica, condition, phase in cells(manifest):
        task = tasks[task_id]
        local = work / 'cells' / task_id / f'r{replica}' / condition
        workspace = local / 'attempt-1' / 'workspace'
        shutil.copytree(Path(manifest['snapshot_root']) / task['snapshot'], workspace)
        request = dict(campaign_id=manifest['campaign_id'], cell_id=cell_id(manifest, task_id, replica, condition),
                       task_id=task_id, replica=replica, condition=condition, phase=phase, attempt=1,
                       prompt=task['prompt'], workspace=str(workspace.resolve()),
                       model=manifest['executor']['model'], effort=manifest['executor']['effort'],
                       graph=conditions[condition], limits=manifest['limits'])
        # No manifest, source hashes, other cells, oracle or reference answer given to solver.
        write(local / 'request.json', request)
        jobs.append(dict(cell_id=request['cell_id'], task_id=task_id, replica=replica, condition=condition,
                         phase=phase, request=str((local / 'request.json').resolve()), request_sha256=identity(request)))
    result = dict(manifest_sha256=identity(manifest), jobs=jobs)
    write(work / 'jobs.json', result)
    return result


def journal_append(path, event):
    with path.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(event, sort_keys=True) + '\n')
        stream.flush()
        import os
        os.fsync(stream.fileno())


def journal_read(path):
    """Started but unfinished attempts remain unknown; never rerun them silently."""
    started, finished, records = {}, set(), []
    if not path.exists():
        return records, set(), False
    for line in path.read_text().splitlines():
        event = json.loads(line)
        key = event['attempt_id']
        if event['event'] == 'started':
            if key in started:
                raise ValueError('duplicate journal start')
            started[key] = event
        elif event['event'] == 'finished':
            if key not in started or key in finished:
                raise ValueError('invalid journal finish')
            if digest(Path(event['result_path'])) != event['result_sha256']:
                raise ValueError('journal result changed')
            records.append(read(Path(event['result_path'])))
            finished.add(key)
        else:
            raise ValueError('unknown journal event')
    interrupted = False
    for key in started.keys() - finished:
        record = dict(started[key]['identity'], success=False, status='interrupted_unknown', usage=None)
        records.append(record)
        interrupted = True
    return records, set(started), interrupted


def normalize_attempt(observed):
    """One explicit accounting scope: inclusive parent OR disjoint streams."""
    if observed.get('usage_complete') is False:
        raise ValueError('partial/unknown usage after interrupted executor; retain private known subtotal')
    streams = observed.get('usage_streams')
    if streams is None:
        choices = [key for key in ('usage_events', 'codex_usage_metadata') if key in observed]
        if len(choices) != 1:
            raise ValueError('choose request events or cumulative metadata; turn totals are not additive')
        return codex_metadata(observed[choices[0]]) if choices[0] == 'codex_usage_metadata' else requests(observed[choices[0]])
    if any(k in observed for k in ('usage_events', 'codex_usage_metadata')):
        raise ValueError('mixed stream and top-level usage')
    if not streams or len({s['id'] for s in streams}) != len(streams):
        raise ValueError('duplicate/missing usage stream')
    parents = [s for s in streams if s.get('scope') == 'inclusive_attempt']
    if parents:
        if len(parents) != 1:
            raise ValueError('overlapping inclusive usage streams')
        return normalize_attempt(parents[0])
    if any(s.get('scope') != 'disjoint_requests' or 'codex_usage_metadata' in s for s in streams):
        raise ValueError('subagent streams need proven disjoint request identities or inclusive attempt usage')
    return requests([event for s in streams for event in s['usage_events']])


def campaign_lock(path):
    """Exclusive nonblocking journal lock on Unix and Windows."""
    from contextlib import contextmanager
    import os

    @contextmanager
    def held():
        with path.open('a+b') as lock:
            if os.name == 'nt':
                import msvcrt
                lock.seek(0)
                if not lock.read(1):
                    lock.write(b'0')
                    lock.flush()
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                try:
                    yield
                finally:
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                try:
                    yield
                finally:
                    fcntl.flock(lock, fcntl.LOCK_UN)
    return held()


def run_campaign(manifest, jobs, command, oracle, work):
    validate(manifest, Path(__file__).resolve().parent.parent, launch=True)
    if jobs['manifest_sha256'] != identity(manifest) or read(work / 'jobs.json') != jobs:
        raise ValueError('jobs differ from frozen manifest')
    if [(j['task_id'], j['replica'], j['condition'], j['phase']) for j in jobs['jobs']] != list(cells(manifest)):
        raise ValueError('jobs differ from registered schedule')
    if digest(command) != manifest['executor']['command_sha256']:
        raise ValueError('executor changed after freeze')
    tasks = {t['id']: t for t in manifest['tasks']}
    if any(digest(oracle) != t['oracle_digest'] for t in tasks.values()):
        raise ValueError('oracle changed after freeze')
    with campaign_lock(work / 'campaign.lock'):
        journal = work / 'attempts.jsonl'
        runs, started_ids, interrupted = journal_read(journal)
        if interrupted or any(r.get('status') != 'completed' for r in runs):
            return runs
        limits, budget = manifest['limits'], manifest['budget']
        for job in jobs['jobs']:
            if job['phase'] not in budget['approved_phases']:
                break
            local = Path(job['request']).parent
            if not local.resolve().is_relative_to(work.resolve()) or local.is_symlink():
                raise ValueError('request outside campaign')
            prepared = read(Path(job['request']))
            if identity(prepared) != job['request_sha256']:
                raise ValueError('prepared request changed')
            prior = [r for r in runs if r['cell_id'] == job['cell_id']]
            if prior and (prior[-1]['success'] or len(prior) >= limits['attempts_per_cell']):
                continue
            for attempt in range(len(prior) + 1, limits['attempts_per_cell'] + 1):
                # Reserve a full attempt at the registered cap. No new block after unknown usage.
                if any(not r.get('usage') for r in runs):
                    return runs
                consumed = sum(verify(r['usage'])['totals']['uncached_input_tokens'] for r in runs)
                if len(runs) >= budget['max_runs'] or budget['max_uncached_input_tokens'] - consumed < limits['max_uncached_input_tokens']:
                    return runs
                attempt_id = f"{job['cell_id']}/a{attempt}"
                if attempt_id in started_ids:
                    raise ValueError('attempt already started')
                attempt_dir = local / f'attempt-{attempt}'
                workspace = attempt_dir / 'workspace'
                task = tasks[job['task_id']]
                if attempt > 1:
                    if attempt_dir.exists():
                        raise ValueError('refusing to overwrite retry workspace')
                    shutil.copytree(Path(manifest['snapshot_root']) / task['snapshot'], workspace)
                check_snapshot(workspace, task['source_hashes'], work)
                request = dict(prepared, attempt=attempt, attempt_id=attempt_id, workspace=str(workspace.resolve()))
                # Recheck every frozen artifact immediately before each attempt, including resume.
                validate(manifest, Path(__file__).resolve().parent.parent, launch=True)
                metadata = {k: request[k] for k in ('campaign_id', 'cell_id', 'task_id', 'replica', 'condition', 'phase', 'attempt', 'attempt_id')}
                journal_append(journal, dict(event='started', attempt_id=attempt_id, identity=metadata))
                started_ids.add(attempt_id)
                usage, observed = None, {}
                begin = time.monotonic()
                record = dict(metadata, success=False, status='measurement_error')
                try:
                    observed = bounded_process(command, request, attempt_dir, 'executor', limits['timeout_seconds'])
                    record['duration_solver_ms'] = (time.monotonic() - begin) * 1000
                    usage = normalize_attempt(observed)
                    if observed.get('attempt_id') != attempt_id or usage['model_settings'][1:] != [request['model'], request['effort']]:
                        raise ValueError('executor identity/model/effort mismatch')
                    cap_values = dict(max_uncached_input_tokens=usage['totals']['uncached_input_tokens'], max_input_tokens=usage['totals']['input_tokens'],
                                      max_output_tokens=usage['totals']['output_tokens'], max_model_requests=usage['model_requests'])
                    if any(value > limits[k] for k, value in cap_values.items()):
                        record.update(status='budget_exhausted', reason_code='observed_attempt_cap_exceeded')
                    else:
                        oracle_begin = time.monotonic()
                        validation = bounded_process(oracle, dict(task_id=task['id'], workspace=str(workspace.resolve()),
                            answer=observed.get('answer'), criteria=task['correctness_criteria']), attempt_dir, 'oracle', 120)
                        if type(validation.get('accepted')) is not bool:
                            raise ValueError('independent oracle acceptance unknown')
                        record.update(success=validation['accepted'], status='completed', reason_code=validation.get('reason_code'),
                                      duration_oracle_ms=(time.monotonic() - oracle_begin) * 1000)
                    record.update(oracle_sha256=digest(oracle), client=observed.get('client_measurement', {}),
                                  isolation=observed.get('isolation', {}), monetary_cost=observed.get('monetary_cost'))
                except (ValueError, KeyError, TypeError, subprocess.TimeoutExpired) as error:
                    record.update(status='timeout' if isinstance(error, subprocess.TimeoutExpired) else 'measurement_error', reason_code=type(error).__name__)
                    (attempt_dir / 'error.txt').write_text(str(error))
                record['usage'] = usage
                record.setdefault('duration_solver_ms', (time.monotonic() - begin) * 1000)
                result_path = attempt_dir / 'result.json'
                if result_path.exists():
                    raise ValueError('refusing to overwrite attempt result')
                write(result_path, record)
                journal_append(journal, dict(event='finished', attempt_id=attempt_id, result_path=str(result_path.resolve()), result_sha256=digest(result_path)))
                runs.append(record)
                if record['status'] != 'completed':
                    return runs
                if record['success']:
                    break
        return runs


def component(usage, key):
    if key == 'cache_creation_input_tokens' and 'request_events' in usage:
        if any(e['provider'] in ('openai', 'codex') and 'cache_write_input_tokens' not in e['usage'] for e in usage['request_events']):
            return None  # Historical parser default zero is not evidence of an exposed cache-write counter.
    return usage['totals'].get(key)


def aggregate(records):
    verified, errors = [], []
    for record in records:
        try:
            verified.append(verify(record['usage']))
        except (ValueError, TypeError, KeyError):
            errors.append('usage_unknown_or_invalid')
    complete = bool(records) and not errors
    components = {k: sum(component(u, k) for u in verified) if complete and all(component(u, k) is not None for u in verified) else None for k in COMPONENTS}
    grouped = {}
    for r in records:
        grouped.setdefault(r['cell_id'], []).append(r)
    accepted = sum(rs[-1]['success'] is True for rs in grouped.values())
    executed = len(grouped)
    cost = components['uncached_input_tokens']
    counters = ('graph_mcp_calls', 'other_mcp_calls', 'all_tool_calls', 'pages', 'errors', 'retries', 'expansions', 'compactions')
    clients = [r.get('client', {}) for r in records]
    money = [r.get('monetary_cost') for r in records]
    monetary = None
    if money and all(valid_money(v) for v in money) and len({v['currency'] for v in money}) == 1:
        monetary = dict(amount=sum(v['amount'] for v in money), currency=money[0]['currency'], verified=True)
    return dict(executed_cells=executed, attempts=len(records), accepted_cells=accepted, success_rate=accepted/executed if executed else None,
        components=components, observed_uncached_subtotal=sum(u['totals']['uncached_input_tokens'] for u in verified) if verified else None,
        primary_per_accepted_task=cost/accepted if cost is not None and accepted else None,
        consumption_per_executed_cell={k: v/executed if v is not None and executed else None for k, v in components.items()},
        model_requests=sum(u['model_requests'] for u in verified) if complete else None,
        client_counters={k: sum(c[k] for c in clients) if clients and all(type(c.get(k)) is int and c[k] >= 0 for c in clients) else None for k in counters},
        monetary_cost=monetary, usage_errors=errors,
        duration_solver_ms=sum(r['duration_solver_ms'] for r in records) if records and all(type(r.get('duration_solver_ms')) in (int, float) and r['duration_solver_ms'] >= 0 for r in records) else None,
        duration_oracle_ms=sum(r['duration_oracle_ms'] for r in records) if records and all(type(r.get('duration_oracle_ms')) in (int, float) and r['duration_oracle_ms'] >= 0 for r in records) else None,
        graph_used_cells=sum(any(r.get('client', {}).get('graph_mcp_calls', 0) > 0 for r in rs) for rs in grouped.values()),
        graph_avoided_cells=sum(all(r.get('client', {}).get('graph_mcp_calls') == 0 for r in rs) for rs in grouped.values()))


def ratio(numerator, denominator):
    n, d = numerator['primary_per_accepted_task'], denominator['primary_per_accepted_task']
    return n/d if n is not None and d is not None and d > 0 else None


def paired_bootstrap(manifest, per_task, candidate, reference):
    """Sample independent task IDs, keeping all paired conditions and replicas."""
    count = manifest['analysis'].get('bootstrap_resamples', 2000)
    if type(count) is not int or not 100 <= count <= 10000:
        raise ValueError('bounded registered bootstrap count required')
    ids = list(per_task)
    if len(ids) < 2 or any(per_task[t][c]['components']['uncached_input_tokens'] is None for t in ids for c in (candidate, reference)):
        return dict(status='not_estimable', interval95=None, interval90=None)
    rng = random.Random(manifest['analysis']['seed'])
    values, undefined = [], 0
    for _ in range(count):
        picked = rng.choices(ids, k=len(ids))
        sums = {c: (sum(per_task[t][c]['components']['uncached_input_tokens'] for t in picked),
                    sum(per_task[t][c]['accepted_cells'] for t in picked)) for c in (candidate, reference)}
        nc, na = sums[candidate]; dc, da = sums[reference]
        if not na or not da or dc == 0:
            undefined += 1
        else:
            values.append((nc/na)/(dc/da))
    if undefined:
        return dict(status='unstable_zero_acceptance', undefined_resamples=undefined, interval95=None, interval90=None)
    values.sort()
    def interval(lo, hi):
        return [values[int((count-1)*lo)], values[int((count-1)*hi)]]
    return dict(status='exploratory', sampling_unit='paired_task_all_replicas', resamples=count,
                interval95=interval(.025, .975), interval90=interval(.05, .95))


def evaluate_campaign(manifest, runs):
    conditions = condition_map(manifest)
    planned = list(cells(manifest))
    order = [(t, r, c) for t, r, c, _ in planned]
    seen, by_cell, measured, isolation_errors, quality_errors, attribution_errors = [], {}, [], [], [], []
    settings = set()
    for record in runs:
        key = (record['task_id'], record['replica'], record['condition'])
        if key not in order or record.get('campaign_id') != manifest['campaign_id'] or type(record.get('success')) is not bool:
            raise ValueError('unexpected run identity/correctness')
        if record.get('cell_id') != cell_id(manifest, *key):
            raise ValueError('cell identity mismatch')
        if key not in by_cell:
            seen.append(key)
            if seen != order[:len(seen)]:
                raise ValueError('runs differ from frozen schedule')
        elif seen[-1] != key:
            raise ValueError('non-contiguous retry')
        attempts = by_cell.setdefault(key, [])
        if record['attempt'] != len(attempts)+1 or record['attempt'] > manifest['limits']['attempts_per_cell'] or (attempts and attempts[-1]['success']):
            raise ValueError('duplicate/invalid attempt')
        attempts.append(record)
        try:
            usage = verify(record['usage']); settings.add(tuple(usage['model_settings']))
        except (KeyError, ValueError, TypeError):
            measured.append('unknown usage: ' + record['cell_id'])
        proof = record.get('isolation', {})
        if proof.get('verified') is not True or proof.get('verifier_sha256') != manifest['executor']['isolation_verifier_sha256'] or not proof.get('probe_artifact_sha256'):
            isolation_errors.append(record['cell_id'])
        task = next(t for t in manifest['tasks'] if t['id'] == key[0])
        if record.get('oracle_sha256') != task.get('oracle_digest'):
            quality_errors.append('oracle identity unknown: ' + record['cell_id'])
        client = record.get('client', {})
        graph_calls = client.get('graph_mcp_calls')
        if type(graph_calls) is not int or graph_calls < 0:
            measured.append('graph namespace unknown: ' + record['cell_id'])
        condition = conditions[key[2]]
        if not condition['graph_enabled']:
            if graph_calls != 0 or client.get('graph_artifacts_visible') is not False or client.get('graph_surface_sha256') is not None:
                isolation_errors.append('graph contamination: ' + record['cell_id'])
        elif client.get('graph_surface_sha256') != condition.get('schema_sha256') or client.get('graph_harness_sha256') != condition.get('harness_sha256'):
            measured.append('unidentified graph surface: ' + record['cell_id'])
        if client.get('context_identity_complete') is not True:
            attribution_errors.append(record['cell_id'])
    if settings and (len(settings) != 1 or next(iter(settings))[1:] != (manifest['executor']['model'], manifest['executor']['effort'])):
        measured.append('model/effort differ from preregistration')
    aggregates = {c: aggregate([r for r in runs if r['condition'] == c]) for c in conditions}
    per_task = {t['id']: {c: aggregate([r for r in runs if r['task_id'] == t['id'] and r['condition'] == c]) for c in conditions} for t in manifest['tasks']}
    classes = {t['class'] for t in manifest['tasks']}
    per_class = {cl: {c: aggregate([r for r in runs if r['condition'] == c and next(t['class'] for t in manifest['tasks'] if t['id'] == r['task_id']) == cl]) for c in conditions} for cl in sorted(classes)}
    per_cell = [dict(task_id=t, replica=replica, condition=c, phase=phase,
                     **aggregate(by_cell.get((t, replica, c), []))) for t, replica, c, phase in planned]
    comparisons = {f'{a}/{b}': dict(ratio=ratio(aggregates[a], aggregates[b]), uncertainty=paired_bootstrap(manifest, per_task, a, b)) for a, b in manifest['analysis']['comparisons']}
    complete = len(by_cell) == len(order)
    consumption = complete and bool(runs) and not measured
    isolation = bool(runs) and not isolation_errors
    correctness = bool(runs) and not quality_errors
    decision = 'HOLD_MEASUREMENT'
    candidate, reference = manifest['analysis'].get('candidate'), manifest['analysis']['reference']
    local_guard = None
    if candidate in conditions and 'local' in per_class:
        local = ratio(per_class['local'][candidate], per_class['local'][reference])
        local_guard = local is not None and local > 1.10
    if consumption and isolation and correctness:
        decision = 'INCONCLUSIVE'
        if candidate in conditions:
            d, a = aggregates[candidate], aggregates[reference]
            previous = manifest['analysis'].get('previous')
            da = ratio(d, a)
            dc = ratio(d, aggregates[previous]) if previous in conditions else None
            poorer = d['success_rate'] < a['success_rate'] or (previous in conditions and d['success_rate'] < aggregates[previous]['success_rate'])
            if poorer or (dc is not None and dc > 1.10):
                decision = 'REGRESSION'
            elif da is not None and da > 1.05 and dc is not None and dc <= .85:
                decision = 'PROGRESS_NOT_COMPETITIVE'
            elif da is not None and .95 <= da <= 1.05:
                decision = 'NEAR_PARITY_UNCERTAIN'
            # Screening never upgrades to a confirmed holdout verdict or economic stop.
    return dict(protocol_revision='comparison-v1', status='not_run' if not runs else 'complete' if complete else 'partial',
        primary_metric=manifest['primary_metric'], decision=decision, executed_cells=len(by_cell), planned_cells=len(order), attempts=len(runs),
        consumption_evidence=dict(comparable=consumption, errors=measured), isolation_evidence=dict(verified=isolation, errors=isolation_errors),
        quality_evidence=dict(verified=correctness, errors=quality_errors), attribution_evidence=dict(complete=consumption and not attribution_errors, errors=attribution_errors),
        aggregates=aggregates, per_task=per_task, per_class=per_class, per_cell=per_cell, comparisons=comparisons, local_guard_alert=local_guard,
        failed_attempts=[{k:r.get(k) for k in ('task_id', 'replica', 'condition', 'attempt', 'status', 'reason_code')} for r in runs if not r['success']],
        limits='Known-task screening; uncertainty samples tasks, not requests or replicas. No general advantage or holdout confirmation.')
