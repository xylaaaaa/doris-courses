"""Independent ledgers and failure-path checks for the extended Level 2 case."""

import json
import sys
import unittest
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[3] / 'doris-course/02-data-warehousing'
sys.path.insert(0, str(ROOT))
from dw_course import bi, sidecars, warehouse


class CaseLedgerTest(unittest.TestCase):
    def test_orders_resolve_valid_versions_not_delivery_order(self):
        case = warehouse.case_fixture()
        current = {}
        valid = 0
        for delivery, order, customer, created, amount, status, version in case['order_deliveries']:
            try:
                value = Decimal(amount)
            except InvalidOperation:
                continue
            valid += 1
            if order not in current or version > current[order]['version']:
                current[order] = dict(customer=customer, created=created, amount=value, status=status, version=version)
        self.assertEqual(valid, case['expected']['valid_deliveries'])
        self.assertEqual(len(current), case['expected']['clean_orders'])
        self.assertEqual(sum(r['amount'] for r in current.values()), Decimal(case['expected']['order_amount']))
        self.assertEqual(current[2102]['status'], 'REFUNDED')
        regions = dict(case['customers'])
        daily = defaultdict(lambda: [0, Decimal(0)])
        for row in current.values():
            key = (row['created'][:10], regions[row['customer']])
            daily[key][0] += 1
            daily[key][1] += row['amount']
        observed = [[*key, count, f'{amount:.2f}'] for key, (count, amount) in sorted(daily.items())]
        self.assertEqual(observed, case['expected']['order_daily'])

    def test_payment_cutoff_retry_and_refund_are_distinct(self):
        case = warehouse.case_fixture()
        payments = {}
        for _, event, order, amount, time in case['payment_deliveries']:
            payload = (order, Decimal(amount), time)
            if event in payments:
                self.assertEqual(payments[event], payload, 'Retry must keep the same business payload')
            payments[event] = payload
        self.assertEqual(len(payments), case['expected']['unique_payments'])
        window = [r for r in payments.values() if case['window_start'] <= r[2] < case['window_end']]
        self.assertEqual(len(window), 5)
        self.assertEqual(sum(r[1] for r in window), Decimal('660.00'))
        self.assertEqual(len({r[0] for r in window}), len(window), 'This case has one successful payment per order')
        customers = {r[1]: r[2] for r in case['order_deliveries']}
        counts = Counter(customers[r[0]] for r in window)
        self.assertEqual(len(counts), 3)
        self.assertEqual(sum(n >= 2 for n in counts.values()), 2)
        daily = defaultdict(set)
        for order, _, time in window:
            daily[time[:10]].add(customers[order])
        self.assertEqual(sum(map(len, daily.values())), 4)
        refunds = sum(Decimal(r[2]) for r in case['refunds'] if case['window_start'] <= r[3] < case['window_end'])
        self.assertEqual(refunds, Decimal('50.00'))
        self.assertEqual(sum(r[1] for r in window)-refunds, Decimal('610.00'))

    def test_case_has_no_external_download_dependency(self):
        self.assertEqual(warehouse.case_fixture()['as_of'], '2026-01-04 00:00:00')
        self.assertNotIn('requests', warehouse.case_fixture.__code__.co_names)


class ProfileTest(unittest.TestCase):
    def run_comparison(self, mismatched=False):
        lab = Mock(database="our_db")
        def query(sql):
            if sql.startswith('SHOW VARIABLES'):
                return [(sql, 'false')]
            return [(2,)] if mismatched and sql == 'service' else [(1,)]
        lab.query.side_effect = query
        rows = iter([[], [{'Profile ID':'detail-id','Sql Statement':'detail','Default Db':'our_db'}],
                     [], [{'Profile ID':'service-id','Sql Statement':'service','Default Db':'our_db'}]])
        profile = 'MergedProfile:\nOLAP_SCAN_OPERATOR\n- ScanRows: 8\n- ScanBytes: 64 B\nDetailProfile:\n- RowsRead: 8\n'
        with patch.object(warehouse, '_profiles', side_effect=lambda _: next(rows)), \
             patch.object(warehouse, '_profile_text', return_value=profile), \
             patch.object(warehouse, 'wait_for', side_effect=lambda read, accepts, **kw: read()), \
             patch.object(warehouse, 'show_log'), patch.object(warehouse, 'show_records'), \
             patch.object(warehouse, 'expect') as expected:
            # Keep the semantic assertion real even though display output is mocked.
            expected.side_effect = lambda actual, reference, **kw: self.assertEqual(actual, reference)
            try:
                return warehouse.compare_query_profiles(lab, [('detail','detail'),('service','service')], repeats=2)
            finally:
                restored = [call.args[0] for call in lab.execute.call_args_list if call.args[0].endswith('= %s')]
                self.assertEqual(len(restored), 5)

    def test_actual_profile_is_linked_to_each_executed_sql(self):
        rows = self.run_comparison()
        self.assertEqual([r['profile_id'] for r in rows], ['detail-id','service-id'])
        self.assertEqual([r['rows_read'] for r in rows], [8,8])

    def test_wrong_results_abort_and_restore_session_variables(self):
        with self.assertRaises(AssertionError):
            self.run_comparison(mismatched=True)

    def test_profile_http_failure_is_not_treated_as_empty_success(self):
        response = Mock()
        response.raise_for_status.side_effect = RuntimeError('HTTP failed')
        with patch.object(warehouse.requests,'get',return_value=response), \
             patch.object(warehouse,'wait_for',side_effect=lambda read, accepts, **kw: read()):
            with self.assertRaisesRegex(RuntimeError, 'HTTP failed'):
                warehouse._profile_text(Mock(user='u',password='secret'), 'query-id')


class ServiceAndAPITest(unittest.TestCase):
    def test_service_start_requires_opt_in(self):
        with patch.object(sidecars.subprocess,'run') as run:
            with self.assertRaises(RuntimeError):
                sidecars.start_service(Mock(),'bi')
            run.assert_not_called()

    def test_attach_only_course_container_and_restore_session(self):
        lab = Mock()
        outputs = ['our-doris\n','our-superset\n',json.dumps({'doris-warehousing-bi_default':{}}),json.dumps({'original_default':{}})]
        with patch.object(sidecars.subprocess,'check_output',side_effect=outputs), patch.object(sidecars.subprocess,'run') as run:
            sidecars.start_service(lab,'bi',start=True)
            self.assertEqual(run.call_args_list[-1].args[0], ['docker','network','connect','--alias','course-doris','doris-warehousing-bi_default','our-doris'])
            lab.restore_session.assert_called_once()

    def test_existing_network_does_not_duplicate_attachment(self):
        lab = Mock(); net={'doris-warehousing-bi_default':{}}
        with patch.object(sidecars.subprocess,'check_output',side_effect=['ours','sidecar',json.dumps(net),json.dumps(net)]), patch.object(sidecars.subprocess,'run') as run:
            sidecars.start_service(lab,'bi',start=True)
            self.assertEqual(run.call_count,1)
            lab.restore_session.assert_not_called()

    def test_superset_error_does_not_echo_credentials(self):
        api=bi.SupersetAPI.__new__(bi.SupersetAPI);api.session=Mock()
        api.session.request.return_value=Mock(ok=False,status_code=422)
        with self.assertRaisesRegex(RuntimeError,'HTTP 422') as caught:
            api.request('POST','database/',{'sqlalchemy_uri':'doris://reader:do-not-print@host/db'})
        self.assertNotIn('do-not-print',str(caught.exception))

    def test_dataset_update_uses_its_distinct_database_id_schema(self):
        api=bi.SupersetAPI.__new__(bi.SupersetAPI)
        api.request=Mock(side_effect=[{'count':1,'result':[{'id':9,'table_name':'ours'}]},{}])
        api.upsert('dataset','table_name','ours',{'database':4}, update_payload={'database_id':4})
        self.assertEqual(api.request.call_args.args,('PUT','dataset/9',{'database_id':4}))

    def test_superset_upsert_updates_existing_named_objects(self):
        api=bi.SupersetAPI.__new__(bi.SupersetAPI)
        api.request=Mock(side_effect=[{'count':1,'result':[{'id':7,'slice_name':'ours'}]},{}])
        self.assertEqual(api.upsert('chart','slice_name','ours',{'slice_name':'ours'}),7)
        self.assertEqual(api.request.call_args.args[:2],('PUT','chart/7'))


class SessionRecoveryTest(unittest.TestCase):
    def test_reconnect_restores_database_timezone_and_write_mode(self):
        from dw_course.runtime import WarehouseLab
        lab = WarehouseLab.__new__(WarehouseLab)
        lab.database = 'dw_course_l1_session_test'
        lab.connection = Mock()
        lab.execute = Mock()
        lab.restore_session()
        lab.connection.ping.assert_called_once_with(reconnect=True)
        self.assertEqual([c.args[0] for c in lab.execute.call_args_list], [
            'USE dw_course_l1_session_test', "SET time_zone = '+08:00'", "SET group_commit = 'off_mode'",
        ])


if __name__ == '__main__':
    unittest.main()
