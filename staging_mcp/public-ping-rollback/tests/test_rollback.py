import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'rollback'


class RollbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state = self.root / 'state'
        self.state.mkdir()
        self.public = self.root / 'public.conf'
        self.public.write_text('public')
        self.log = self.root / 'log'
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        # Rewrite fixed locations only in this disposable test copy.
        script = SOURCE.read_text().replace('/var/lib/staging-ping-rollback', str(self.state))
        script = script.replace('/etc/nginx-staging-ping/conf.d/public-ping.conf', str(self.public))
        script = script.replace('PATH=/usr/sbin:/usr/bin:/sbin:/bin', f'PATH={self.bin}:/usr/bin:/bin')
        self.script = self.root / 'rollback'
        self.script.write_text(script)
        for name, body in {
            'date': 'echo 1000000000',
            'flock': 'exit 0',  # macOS lacks util-linux flock; locking needs host integration testing.
            'nginx': 'echo nginx >> "$LOG"; exit "${NGINX_RESULT:-0}"',
            'systemctl': 'echo "$*" >> "$LOG"; [ "$1" != reload ] || exit "${RELOAD_RESULT:-0}"',
        }.items():
            p = self.bin / name
            p.write_text('#!/bin/sh\n' + body + '\n')
            p.chmod(0o755)

    def run_check(self, arg='check', **env):
        return subprocess.run(['sh', str(self.script), arg], env={**os.environ, 'LOG': str(self.log), **env}, capture_output=True)

    def deadline(self, value):
        (self.state / 'deadline').write_text(value)

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_future_deadline_keeps_configuration(self):
        self.deadline('1000000100')
        self.assertEqual(self.run_check().returncode, 0)
        self.assertTrue(self.public.exists())
        self.assertEqual(self.calls(), [])

    def test_guard_removes_expired_without_service_operations(self):
        self.deadline('1000000000')
        self.assertEqual(self.run_check('guard').returncode, 0)
        self.assertFalse(self.public.exists())
        self.assertEqual(self.calls(), [])

    def test_missing_malformed_and_too_far_deadlines_expire(self):
        for value in (None, 'oops', '1000001801', '999999999999999999999'):
            with self.subTest(value=value):
                self.public.write_text('public')
                if value is not None:
                    self.deadline(value)
                self.assertEqual(self.run_check().returncode, 0)
                self.assertFalse(self.public.exists())
        self.assertIn('reload nginx-staging-ping.service', self.calls())

    def test_validation_or_reload_failure_stops_and_retry_succeeds(self):
        for failure in ('NGINX_RESULT', 'RELOAD_RESULT'):
            with self.subTest(failure=failure):
                self.public.write_text('public')
                self.assertNotEqual(self.run_check(**{failure: '1'}).returncode, 0)
                self.assertFalse(self.public.exists())
                self.assertIn('stop nginx-staging-ping.service', self.calls())
                self.assertEqual(self.run_check().returncode, 0)

    def test_remove_failure_guard_blocks_start_check_stops(self):
        self.public.unlink()
        self.public.mkdir()  # rm -f cannot remove a directory
        self.assertNotEqual(self.run_check('guard').returncode, 0)
        self.assertEqual(self.calls(), [])
        self.assertNotEqual(self.run_check().returncode, 0)
        self.assertIn('stop nginx-staging-ping.service', self.calls())


if __name__ == '__main__':
    unittest.main()
