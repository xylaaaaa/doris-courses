"""Build a real local Superset dashboard from the reviewed Level 2 SQL contract."""

import hashlib
import json
import os
import secrets
from urllib.parse import quote

import pymysql
import requests

from .sidecars import start_service
from .runtime import expect
from .ui import show_records

URL = 'http://127.0.0.1:51888'
ADMIN = 'course_admin'
ADMIN_PASSWORD = 'course_local_only'


class SupersetAPI:
    def __init__(self):
        self.session = requests.Session()
        login = self.request('POST', 'security/login', {
            'username': ADMIN, 'password': ADMIN_PASSWORD, 'provider': 'db', 'refresh': True,
        })
        self.session.headers['Authorization'] = 'Bearer ' + login['access_token']
        token = self.request('GET', 'security/csrf_token/')['result']
        self.session.headers['X-CSRFToken'] = token

    def request(self, method, endpoint, payload=None):
        response = self.session.request(method, URL + '/api/v1/' + endpoint,
                                        json=payload, timeout=120)
        if not response.ok:
            # Server errors can contain connection strings. Never echo a payload or URI.
            raise RuntimeError(f'Superset {method} {endpoint} returned HTTP {response.status_code}')
        return response.json()

    def upsert(self, endpoint, key, value, payload, *, update_payload=None):
        page = 0
        while True:
            records = self.request('GET', f'{endpoint}/?q=(page:{page},page_size:100)')
            for row in records['result']:
                if row[key] == value:
                    self.request('PUT', f'{endpoint}/{row["id"]}', payload if update_payload is None else update_payload)
                    return row['id']
            page += 1
            if page * 100 >= records['count']:
                break
        return self.request('POST', endpoint + '/', payload)['id']


def build_payment_dashboard(lab, *, start=False):
    """Start on explicit opt-in, persist a view-only account, create and query three charts."""
    expected = [("660.00", 5, 5, 8)]
    expect(lab.query('SELECT paid_gmv,paid_orders,converted_orders,created_orders FROM bi_paid_kpis_l2'),
           expected, title='Validate the reviewed SQL contract before BI publication')
    start_service(lab, 'bi', start=start)
    suffix = hashlib.sha256(lab.database.encode()).hexdigest()[:12]
    user = 'course_bi_' + suffix
    password = secrets.token_urlsafe(24)
    identity = f"'{user}'@'%'"
    # This course-owned identity remains so the published dashboard remains usable.
    lab.execute(f"CREATE USER IF NOT EXISTS '{user}'@'%%' IDENTIFIED BY %s", (password,))
    lab.execute(f"SET PASSWORD FOR '{user}'@'%%' = PASSWORD(%s)", (password,))
    lab.execute(f'GRANT SELECT_PRIV ON internal.{lab.database}.bi_paid_kpis_l2 TO {identity}')
    reader = pymysql.connect(host=os.environ['DW_HOST'], port=int(os.environ['DW_PORT']),
                             user=user, password=password, autocommit=True, connect_timeout=5)
    try:
        with reader.cursor() as cursor:
            cursor.execute(f'SELECT paid_gmv,paid_orders,converted_orders,created_orders FROM {lab.database}.bi_paid_kpis_l2')
            expect(list(cursor.fetchall()), expected, title='Dashboard identity can read the reviewed view')
            try:
                cursor.execute(f'SELECT COUNT(*) FROM {lab.database}.dwd_payments_l2')
            except pymysql.err.OperationalError as error:
                if error.args[0] != 1105 or not any(t in error.args[1] for t in ('Access denied','Permission denied')):
                    raise
            else:
                raise AssertionError('Dashboard identity unexpectedly read payment detail')
    finally:
        reader.close()
    api = SupersetAPI()
    try:
        database_name = 'Course payments ' + suffix
        uri = f'doris://{user}:{quote(password, safe="")}@course-doris:9030/internal.{lab.database}'
        database_id = api.upsert('database', 'database_name', database_name, {
            'database_name': database_name, 'sqlalchemy_uri': uri,
            'expose_in_sqllab': False, 'allow_dml': False, 'allow_ctas': False, 'allow_cvas': False,
        })
        dataset_name = 'reviewed_paid_kpis_' + suffix
        dataset_id = api.upsert('dataset', 'table_name', dataset_name, {
            'database': database_id, 'table_name': dataset_name,
            'sql': f'SELECT * FROM {lab.database}.bi_paid_kpis_l2',
        }, update_payload={'database_id': database_id, 'table_name': dataset_name,
                           'sql': f'SELECT * FROM {lab.database}.bi_paid_kpis_l2'})
        # Refresh inferred column metadata before creating chart metrics.
        api.request('PUT', f'dataset/{dataset_id}/refresh')
        charts, observations = [], []
        specifications = [('Paid GMV', 'SUM(paid_gmv)', 660.0, ',.2f'),
                          ('Paid orders', 'SUM(paid_orders)', 5, ',.0f'),
                          ('Created-cohort conversion', 'SUM(converted_orders)*1.0/NULLIF(SUM(created_orders),0)', 0.625, '.1%')]
        for title, expression, expected_value, number_format in specifications:
            metric = {'expressionType': 'SQL', 'sqlExpression': expression,
                      'label': title, 'optionName': 'metric_' + title.replace(' ', '_')}
            query = {'metrics': [metric], 'columns': [], 'filters': [], 'extras': {},
                     'row_limit': 1, 'time_range': 'No filter'}
            context = {'datasource': {'id': dataset_id, 'type': 'table'},
                       'queries': [query], 'force': True, 'result_format': 'json', 'result_type': 'full'}
            params = {'datasource': f'{dataset_id}__table', 'viz_type': 'big_number_total',
                      'metric': metric, 'time_range': 'No filter', 'y_axis_format': number_format,
                      'subheader': 'Asia/Shanghai; payments before January 4; refunds separate'}
            chart_id = api.upsert('chart', 'slice_name', title + ' ' + suffix, {
                'slice_name': title + ' ' + suffix, 'viz_type': 'big_number_total',
                'datasource_id': dataset_id, 'datasource_type': 'table',
                'params': json.dumps(params), 'query_context': json.dumps(context),
            })
            executed = api.request('POST', 'chart/data', context)['result'][0]
            if executed.get('error'):
                raise RuntimeError('Dashboard chart execution failed: ' + title)
            value = executed['data'][0][title]
            expect(float(value), float(expected_value), title='Real Superset chart value: ' + title)
            observations.append({'chart': title, 'actual_value': value, 'chart_id': chart_id})
            charts.append(chart_id)
        layout = {
            'DASHBOARD_VERSION_KEY': 'v2',
            'ROOT_ID': {'type': 'ROOT', 'id': 'ROOT_ID', 'children': ['GRID_ID']},
            'GRID_ID': {'type': 'GRID', 'id': 'GRID_ID', 'parents': ['ROOT_ID'], 'children': ['ROW-1']},
            'ROW-1': {'type': 'ROW', 'id': 'ROW-1', 'parents': ['ROOT_ID','GRID_ID'],
                      'children': [], 'meta': {'background': 'BACKGROUND_TRANSPARENT'}},
        }
        for index, chart_id in enumerate(charts):
            key = f'CHART-{chart_id}'
            layout['ROW-1']['children'].append(key)
            layout[key] = {'type': 'CHART', 'id': key, 'parents': ['ROOT_ID','GRID_ID','ROW-1'],
                           'children': [], 'meta': {'chartId': chart_id, 'height': 50, 'width': 4}}
        slug = 'course-payments-' + suffix
        dashboard_id = api.upsert('dashboard', 'slug', slug, {
            'dashboard_title': 'Reviewed payment metrics', 'slug': slug, 'published': True,
            'position_json': json.dumps(layout), 'json_metadata': json.dumps({'native_filter_configuration': []}),
        })
        for chart_id in charts:
            api.request('PUT', f'chart/{chart_id}', {'dashboards': [dashboard_id]})
        attached = api.request('GET', f'dashboard/{dashboard_id}/charts')['result']
        expect(sorted(row['id'] for row in attached), sorted(charts), title='All three charts belong to the published dashboard')
        show_records('Verified Superset executions; not notebook-only mock charts', observations)
        show_records('Local dashboard access', [{'url': URL + f'/superset/dashboard/{dashboard_id}/',
                                              'local_ui_user': ADMIN, 'doris_reader': user,
                                              'as_of': '2026-01-04 00:00:00 Asia/Shanghai'}])
        return {'dashboard_id': dashboard_id, 'url': URL + f'/superset/dashboard/{dashboard_id}/',
                'charts': charts, 'reader': user}
    finally:
        api.session.close()
