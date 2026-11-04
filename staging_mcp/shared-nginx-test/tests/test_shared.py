import hashlib
import importlib.machinery
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

path = Path(__file__).resolve().parents[1] / "di-shared-test"
loader = importlib.machinery.SourceFileLoader("shared_test", str(path))
spec = importlib.util.spec_from_loader(loader.name, loader)
assert spec is not None
m = importlib.util.module_from_spec(spec)
loader.exec_module(m)


class DigestTest(unittest.TestCase):
    """Check the unpatched deployment digest against the reviewed source copy."""

    def test_configured_digest_matches_reviewed_remote_source(self):
        """The pinned digest must identify the exact reviewed configuration bytes."""
        reviewed = Path(__file__).with_name("reviewed-public-test.conf")
        self.assertEqual(m.DIGEST, hashlib.sha256(reviewed.read_bytes()).hexdigest())

    def test_old_digest_matches_previous_rate_only(self):
        reviewed = Path(__file__).with_name("reviewed-public-test.conf").read_bytes()
        old = reviewed.replace(b"rate=60r/m", b"rate=10r/m").replace(
            b"burst=20", b"burst=5"
        )
        self.assertEqual(m.OLD_DIGEST, hashlib.sha256(old).hexdigest())

    def test_reviewed_config_matches_generated_public_config(self):
        """Pin both the fail-closed prefix and the complete current example."""
        prefix = (
            b"# Temporary staging public test: fail-closed IPv4 TLS default.\n"
            b"server {\n"
            b"    listen 0.0.0.0:443 ssl default_server;\n"
            b"    ssl_reject_handshake on;\n"
            b"    return 444;\n"
            b"}\n\n"
        )
        example = path.parents[1] / "nginx.conf.example"
        reviewed = Path(__file__).with_name("reviewed-public-test.conf")
        self.assertEqual(reviewed.read_bytes(), prefix + example.read_bytes())


class SharedTest(unittest.TestCase):
    """Exercise staging and rollback without touching the host nginx."""

    def setUp(self):
        """Create isolated inputs and mock privileged commands."""
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.conf = self.root / "conf"
        self.conf.mkdir()
        self.state = self.root / "state"
        self.state.mkdir()
        self.source = self.root / "source"
        self.source.write_bytes(b"public")
        self.loop = self.conf / m.LOOP
        self.loop.write_bytes(b"loopback")
        self.calls = []
        for key, val in {
            "CONF": str(self.conf),
            "STATE": str(self.state),
            "SOURCE": str(self.source),
            "DIGEST": hashlib.sha256(b"public").hexdigest(),
        }.items():
            p = patch.object(m, key, val)
            p.start()
            self.addCleanup(p.stop)
        p = patch.object(m, "trusted_dir")
        p.start()
        self.addCleanup(p.stop)
        original = m.read_regular

        def read(path, root_owned=False):
            if str(path).startswith("/usr/local/"):
                return b"installed"
            return original(path, False)

        p = patch.object(m, "read_regular", side_effect=read)
        p.start()
        self.addCleanup(p.stop)
        p = patch.object(
            m,
            "command",
            side_effect=lambda args, timeout=m.COMMAND_TIMEOUT: self.calls.append(args),
        )
        p.start()
        self.addCleanup(p.stop)

    def test_activate_then_rollback(self):
        """Activate once and restore the loopback configuration."""
        m.activate()
        self.assertEqual((self.conf / m.PUBLIC).read_bytes(), b"public")
        self.assertFalse(self.loop.exists())
        self.assertIn("systemd-run", self.calls[0][0])
        m.rollback()
        self.assertFalse((self.conf / m.PUBLIC).exists())
        self.assertEqual(self.loop.read_bytes(), b"loopback")
        with self.assertRaises(RuntimeError):
            m.activate()

    def test_timer_failure_rolls_back(self):
        """Restore the configuration when the timer cannot start."""

        def fail_timer(args, timeout=m.COMMAND_TIMEOUT):
            if "systemd-run" in args[0]:
                raise RuntimeError("timer failed")

        with patch.object(m, "command", side_effect=fail_timer):
            with self.assertRaises(RuntimeError):
                m.activate()
        self.assertTrue(self.loop.exists())
        self.assertFalse((self.conf / m.PUBLIC).exists())

    def test_expired_deadline_never_reloads_activation(self):
        """Avoid activation reload when the deadline has expired."""
        with patch.object(m, "WINDOW", -1):
            with self.assertRaises(RuntimeError):
                m.activate()
        # Only rollback reload occurs, after removing public config.
        self.assertEqual(sum("reload" in x for x in self.calls), 1)
        self.assertTrue(self.loop.exists())

    def test_reload_crosses_deadline_and_rolls_back(self):
        """Roll back if activation reload crosses the deadline."""
        clock = [0.0]
        events = []

        def run(args, timeout=m.COMMAND_TIMEOUT):
            events.append((args, (self.conf / m.PUBLIC).exists()))
            if "reload" in args and clock[0] == 0.0:
                clock[0] = 1501.0

        with (
            patch.object(m.time, "monotonic", side_effect=lambda: clock[0]),
            patch.object(m, "command", side_effect=run),
        ):
            with self.assertRaises(RuntimeError):
                m.activate()
        self.assertEqual(
            [present for args, present in events if "reload" in args], [True, False]
        )
        self.assertTrue(self.loop.exists())

    def test_stalled_reload_timeout_rolls_back(self):
        """Roll back when activation reload times out."""
        events = []

        def run(args, timeout=m.COMMAND_TIMEOUT):
            events.append((args, (self.conf / m.PUBLIC).exists()))
            if "reload" in args and events[-1][1]:
                raise subprocess.TimeoutExpired(args, timeout)

        with patch.object(m, "command", side_effect=run):
            with self.assertRaises(subprocess.TimeoutExpired):
                m.activate()
        self.assertEqual(
            [present for args, present in events if "reload" in args], [True, False]
        )
        self.assertTrue(self.loop.exists())

    def test_rejects_wrong_source_and_existing_backup(self):
        """Reject altered source and preexisting backups."""
        self.source.write_bytes(b"bad")
        with self.assertRaises(RuntimeError):
            m.activate()
        self.source.write_bytes(b"public")
        (self.conf / (m.LOOP + ".disabled")).write_text("keep")
        with self.assertRaises(RuntimeError):
            m.activate()
        self.assertTrue(self.loop.exists())

    def test_rollback_accepts_both_transition_configs(self):
        reviewed = Path(__file__).with_name("reviewed-public-test.conf").read_bytes()
        old = reviewed.replace(
            b"rate=60r/m", b"rate=10r/m"
        ).replace(b"burst=20", b"burst=5")
        with patch.object(m, "DIGEST", hashlib.sha256(reviewed).hexdigest()):
            for data in (old, reviewed):
                (self.conf / m.PUBLIC).write_bytes(data)
                m.rollback()
                self.assertFalse((self.conf / m.PUBLIC).exists())

    def test_rollback_refuses_unexpected_public(self):
        """Do not remove an unexpected public configuration."""
        (self.conf / m.PUBLIC).write_text("unrelated")
        with self.assertRaises(RuntimeError):
            m.rollback()
        self.assertEqual((self.conf / m.PUBLIC).read_text(), "unrelated")


if __name__ == "__main__":
    unittest.main()
