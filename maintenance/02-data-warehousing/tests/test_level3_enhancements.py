"""Failure boundaries for real audit evidence and repository preparation."""

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from botocore.exceptions import ClientError

ROOT=Path(__file__).resolve().parents[3]/'doris-course/02-data-warehousing'
sys.path.insert(0,str(ROOT))
from dw_course import backup, operations


class AuditTest(unittest.TestCase):
    record='[query] |QueryId=real-id|User=reader|Db=dw_course_l1_test|State=EOF|ErrorCode=0|ReturnRows=1|Time(ms)=9|Stmt=SELECT "our-tag",COUNT(*) FROM approved_view'

    def test_match_identity_database_and_tag_not_synthetic_ticket(self):
        rows=operations.parse_audit_records(self.record,'dw_course_l1_test',[('reader','our-tag')])
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['query_id'],'real-id')
        self.assertNotIn('Stmt',rows[0])
        self.assertEqual(operations.parse_audit_records(self.record,'other_db',[('reader','our-tag')]),[])
        self.assertEqual(operations.parse_audit_records(self.record,'dw_course_l1_test',[('other_user','our-tag')]),[])

    def test_does_not_display_unrelated_credential_statements(self):
        unrelated='[query] |User=root|Db=dw_course_l1_test|Stmt=CREATE USER x IDENTIFIED BY "do-not-print"'
        rows=operations.parse_audit_records(unrelated+'\n'+self.record,'dw_course_l1_test',[('reader','our-tag')])
        self.assertNotIn('do-not-print',str(rows))

    def test_missing_query_is_not_successful_audit_evidence(self):
        self.assertEqual(operations.parse_audit_records(self.record,'dw_course_l1_test',[('reader','missing')]),[])

    def test_collection_command_is_scoped_to_our_course_fe(self):
        with patch.object(operations.subprocess,'run',return_value=Mock(stdout=self.record)) as run, \
             patch.object(operations,'wait_for',side_effect=lambda read, accepts, **kw: read()):
            operations.query_audit_records('dw_course_l1_test',[('reader','our-tag')])
            command=run.call_args.args[0]
            self.assertIn('doris-warehousing-course',command)
            self.assertEqual(command[-5:],['doris','tail','-n','5000','/opt/apache-doris/fe/log/fe.audit.log'])


class RepositoryStorageTest(unittest.TestCase):
    def test_only_absent_bucket_is_created(self):
        client=Mock();client.head_bucket.side_effect=ClientError({'Error':{'Code':'404'}},'HeadBucket')
        with patch.object(backup,'start_service') as start,patch.object(backup.boto3,'client',return_value=client):
            self.assertIs(backup.prepare_backup_storage(Mock(),start=True),client)
            start.assert_called_once()
            client.create_bucket.assert_called_once_with(Bucket=backup.BUCKET)

    def test_existing_bucket_and_snapshots_are_not_reset(self):
        client=Mock()
        with patch.object(backup,'start_service'),patch.object(backup.boto3,'client',return_value=client):
            backup.prepare_backup_storage(Mock(),start=True)
            client.create_bucket.assert_not_called()
            client.delete_bucket.assert_not_called()

    def test_permission_failure_is_not_misreported_as_missing_bucket(self):
        client=Mock();client.head_bucket.side_effect=ClientError({'Error':{'Code':'403'}},'HeadBucket')
        with patch.object(backup,'start_service'),patch.object(backup.boto3,'client',return_value=client):
            with self.assertRaises(ClientError):backup.prepare_backup_storage(Mock(),start=True)
            client.create_bucket.assert_not_called()


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


if __name__=='__main__':unittest.main()
