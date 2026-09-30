"""Local teaching case and Profile observations; transformation SQL stays in Labs."""

import json
import math
import os
import time
from pathlib import Path

import pymysql
import requests

from ._shared import load_component
from .runtime import expect, normalized
from .streaming import wait_for
from .ui import show_log, show_records

_shared_lab = load_component('doris_client').DorisLab


def case_fixture():
    """Read the small committed Level 2 case; no external dataset download is involved."""
    path = Path(__file__).resolve().parents[1] / 'datasets/warehouse_case.json'
    return json.loads(path.read_text(encoding='utf-8'))


def _profiles(lab):
    with lab.connection.cursor(pymysql.cursors.DictCursor) as cursor:
        cursor.execute('SHOW QUERY PROFILE')
        return list(cursor.fetchall())


def _profile_text(lab, profile_id):
    endpoint = os.environ.get('DW_FE_HTTP_URL', 'http://127.0.0.1:51030').rstrip('/')
    url = endpoint + '/rest/v2/manager/query/profile/text/' + profile_id

    def read():
        response = requests.get(url, auth=(lab.user, lab.password), timeout=10)
        response.raise_for_status()
        payload = response.json()
        return payload.get('data', {}).get('profile', '')

    return wait_for(read, lambda value: 'OLAP_SCAN_OPERATOR' in value,
                    description='Fetch the completed scan Profile', timeout=30)


def compare_query_profiles(lab, cases, *, repeats=20):
    """Execute equal-result SQL and report real scan evidence and bounded timing samples."""
    settings = {'enable_profile': 'true', 'profile_level': '2',
                'enable_condition_cache': 'false', 'enable_query_cache': 'false',
                'enable_sql_cache': 'false'}
    previous = {name: lab.query(f'SHOW VARIABLES LIKE "{name}"')[0][1] for name in settings}
    observations = []
    reference = None
    try:
        for name, value in settings.items():
            lab.execute(f'SET {name} = {value}')
        for label, statement in cases:
            excluded = {str(row['Profile ID']) for row in _profiles(lab)}
            result = lab.query(statement)
            if reference is None:
                reference = result
            else:
                expect(result, reference, title='Optimization preserves all result rows')
            fingerprint = _shared_lab._normalize_statement(statement)

            def find_profile():
                return [row for row in _profiles(lab)
                        if str(row['Profile ID']) not in excluded
                        and _shared_lab._normalize_statement(str(row['Sql Statement'])) == fingerprint
                        and row['Default Db'] == lab.database]

            profile_row = wait_for(find_profile, bool, description='Locate this query Profile', timeout=30)[0]
            profile_id = str(profile_row['Profile ID'])
            profile = _profile_text(lab, profile_id)
            merged = profile.split('MergedProfile:', 1)[-1].split('DetailProfile', 1)[0]
            observations.append({'query': label, 'profile_id': profile_id,
                                 'scan_rows': _shared_lab._profile_metric(merged, 'ScanRows'),
                                 'rows_read': _shared_lab._profile_row_sum(profile, 'RowsRead'),
                                 'scan_bytes': _shared_lab._profile_metric(merged, 'ScanBytes')})
            show_log(label + ': complete measured Profile', profile)
        show_records('Actual scan evidence; not an EXPLAIN estimate', observations)
        # Timing samples omit Profile collection. One warm-up is explicit; storage caches are not flushed.
        lab.execute('SET enable_profile=false')
        timings = []
        for label, statement in cases:
            expect(lab.query(statement), reference)
            samples = []
            for _ in range(repeats):
                started = time.perf_counter()
                result = lab.query(statement)
                samples.append((time.perf_counter() - started) * 1000)
                if normalized(result) != normalized(reference):
                    raise AssertionError("Optimization changed a timing-sample result")
            timings.append({'query': label, 'samples': repeats, 'concurrency': 1,
                            'empirical_p95_ms': round(sorted(samples)[math.ceil(0.95 * repeats) - 1], 2),
                            'sql_result_cache': 'disabled', 'storage_cache': 'one warm-up; not flushed'})
        show_records('Illustrative same-host latency samples, not a production SLA', timings)
    finally:
        for name, value in previous.items():
            lab.execute(f'SET {name} = %s', (value,))
    return observations
