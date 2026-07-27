"""Unit tests for authorized bug-bounty scope helpers."""

from __future__ import annotations

import unittest
from unittest import mock


class TestBugBountyScope(unittest.TestCase):
    def test_host_in_scope(self):
        from bug_bounty import _host_in_scope

        prog = {
            "in_scope_hosts": ["example.com", "*.api.example.com"],
            "out_of_scope": ["blog.example.com"],
        }
        self.assertTrue(_host_in_scope("example.com", prog))
        self.assertTrue(_host_in_scope("www.example.com", prog))
        self.assertTrue(_host_in_scope("v1.api.example.com", prog))
        self.assertFalse(_host_in_scope("blog.example.com", prog))
        self.assertFalse(_host_in_scope("evil.com", prog))

    def test_detect_commands(self):
        from owner_action import detect_owner_action

        a = detect_owner_action("bug bounty list")
        self.assertIsNotNone(a)
        self.assertEqual(a.kind, "bug_bounty")
        self.assertEqual(a.params.get("op"), "list")
        a2 = detect_owner_action("bug bounty scan example-public-demo")
        self.assertEqual(a2.kind, "bug_bounty")
        self.assertEqual(a2.params.get("op"), "scan")
        self.assertEqual(a2.params.get("program_id"), "example-public-demo")

    def test_scan_requires_authorized(self):
        from bug_bounty import run_program_scan

        with mock.patch("bug_bounty.is_owner_equivalent_mode", return_value=True):
            with mock.patch(
                "bug_bounty.get_program",
                return_value={
                    "id": "x",
                    "enabled": True,
                    "authorized": False,
                    "in_scope_hosts": ["example.com"],
                },
            ):
                r = run_program_scan("x")
        self.assertFalse(r.get("ok"))
        self.assertIn("authorized", r.get("error", "").lower())


if __name__ == "__main__":
    unittest.main()
