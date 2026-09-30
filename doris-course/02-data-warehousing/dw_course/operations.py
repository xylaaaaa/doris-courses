"""Observe tagged queries in the course's own FE audit file."""

import subprocess

from .docker_runtime import compose_command
from .streaming import wait_for


def parse_audit_records(text, database, requests):
    """Select exact identities/tags without exposing unrelated SQL or credentials."""
    matches = {}
    for line in text.splitlines():
        fields = dict(piece.split('=', 1) for piece in line.split('|')[1:] if '=' in piece)
        for user, tag in requests:
            if (fields.get('User') == user and fields.get('Db') == database
                    and tag in fields.get('Stmt', '')):
                matches[(user, tag)] = {
                    'user': user, 'database': database, 'request_tag': tag,
                    'query_id': fields['QueryId'], 'state': fields['State'],
                    'error_code': fields['ErrorCode'], 'returned_rows': fields['ReturnRows'],
                    'execution_ms': fields['Time(ms)'],
                }
    return [matches[key] for key in requests if key in matches]


def query_audit_records(database, requests):
    """Read this single course FE; do not imply multi-node collection or retention."""
    def read():
        result = subprocess.run(
            compose_command('exec', '-T', 'doris', 'tail', '-n', '5000',
                            '/opt/apache-doris/fe/log/fe.audit.log'),
            check=True, capture_output=True, text=True, timeout=15,
        )
        return parse_audit_records(result.stdout, database, requests)

    return wait_for(read, lambda rows: len(rows) == len(requests),
                    description='Find tagged ordinary-user queries in the FE audit file', timeout=60)
