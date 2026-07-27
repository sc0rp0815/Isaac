"""Unit tests for chrome secrets parsers and owner-action detect (no live Magisk)."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path


def _make_cookies_db() -> bytes:
    path = Path(tempfile.mkstemp(suffix=".db")[1])
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE cookies ("
        "creation_utc INTEGER, host_key TEXT, top_frame_site_key TEXT, name TEXT, "
        "value TEXT, encrypted_value BLOB, path TEXT, expires_utc INTEGER, "
        "is_secure INTEGER, is_httponly INTEGER, last_access_utc INTEGER, "
        "has_expires INTEGER, is_persistent INTEGER, priority INTEGER, "
        "samesite INTEGER, source_scheme INTEGER, source_port INTEGER, "
        "last_update_utc INTEGER, source_type INTEGER, has_cross_site_ancestor INTEGER)"
    )
    con.execute(
        "INSERT INTO cookies VALUES (1,'.example.com','','sid','',?, '/',0,1,1,9,1,1,1,0,2,443,9,0,0)",
        (b"v10" + b"\x00" * 20,),
    )
    con.execute(
        "INSERT INTO cookies VALUES (1,'.google.com','','NID','',?, '/',0,1,1,8,1,1,1,0,2,443,8,0,0)",
        (b"v10" + b"\x01" * 20,),
    )
    con.commit()
    con.close()
    raw = path.read_bytes()
    path.unlink(missing_ok=True)
    return raw


def _make_webdata_db() -> bytes:
    path = Path(tempfile.mkstemp(suffix=".db")[1])
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE autofill (name TEXT, value TEXT, value_lower TEXT, "
        "date_created INTEGER, date_last_used INTEGER, count INTEGER)"
    )
    con.execute(
        "INSERT INTO autofill VALUES ('email','a@b.de','a@b.de',1,2,5)"
    )
    con.execute(
        "CREATE TABLE address_type_tokens (guid TEXT, type INTEGER, value TEXT, "
        "verification_status INTEGER, observations BLOB)"
    )
    con.execute(
        "INSERT INTO address_type_tokens VALUES ('g1',3,'Ada',1,X'')"
    )
    con.execute(
        "INSERT INTO address_type_tokens VALUES ('g1',5,'Lovelace',1,X'')"
    )
    con.commit()
    con.close()
    raw = path.read_bytes()
    path.unlink(missing_ok=True)
    return raw


class TestChromeSecretsParse(unittest.TestCase):
    def test_parse_cookies(self):
        from chrome_secrets import parse_cookies_db

        r = parse_cookies_db(_make_cookies_db(), limit=10)
        self.assertTrue(r["ok"])
        self.assertEqual(r["total"], 2)
        self.assertEqual(r["encrypted_in_page"], 2)
        self.assertTrue(any(c["host"] == ".example.com" for c in r["cookies"]))

    def test_parse_autofill(self):
        from chrome_secrets import parse_web_data

        r = parse_web_data(_make_webdata_db())
        self.assertTrue(r["ok"])
        self.assertEqual(r["autofill"][0]["value"], "a@b.de")
        self.assertTrue(r["addresses"])


class TestChromeSecretsDetect(unittest.TestCase):
    def test_detect(self):
        from owner_action import detect_owner_action

        a = detect_owner_action("chrome secrets")
        self.assertIsNotNone(a)
        self.assertEqual(a.kind, "chrome_secrets")
        a2 = detect_owner_action("chrome cookies")
        self.assertEqual(a2.kind, "chrome_secrets")
        self.assertEqual(a2.params.get("section"), "cookies")
        a3 = detect_owner_action("apps list whatsapp")
        self.assertEqual(a3.kind, "apps_list")
        self.assertIn("whatsapp", a3.params.get("query", ""))
        a4 = detect_owner_action("tippe Anmelden")
        self.assertEqual(a4.kind, "android_input")
        a5 = detect_owner_action("öffne app de.number26.android")
        self.assertEqual(a5.kind, "app_open")
        a6 = detect_owner_action("chrome decrypt")
        self.assertEqual(a6.kind, "chrome_decrypt")
        self.assertTrue(a6.params.get("reveal"))
        a7 = detect_owner_action("chrome decrypt mask")
        self.assertEqual(a7.kind, "chrome_decrypt")
        self.assertFalse(a7.params.get("reveal"))


class TestLiveDecryptHelpers(unittest.TestCase):
    def test_guess_host_and_mask(self):
        from chrome_secrets import _guess_host_for_name, _mask_value, format_live_decrypt_report

        self.assertEqual(_guess_host_for_name("SID"), ".google.com")
        self.assertEqual(_guess_host_for_name("access_token"), "(oauth-token)")
        self.assertIn("…", _mask_value("abcdefghijklmnop", reveal=False))
        text = format_live_decrypt_report(
            {
                "ok": True,
                "items": [
                    {
                        "host": ".google.com",
                        "name": "SID",
                        "value": "secretvalue123",
                        "value_len": 14,
                        "reveal": True,
                    }
                ],
                "meta": {"pid": 1, "regions": 2, "method": "process_memory"},
                "note": "test",
            },
            reveal=True,
        )
        self.assertIn("SID=secretvalue123", text)


class TestAndroidAppsSearch(unittest.TestCase):
    def test_search(self):
        from android_apps import search_packages

        pkgs = ["com.whatsapp", "com.android.chrome", "de.number26.android"]
        hits = search_packages(pkgs, "whatsapp")
        self.assertEqual(hits[0], "com.whatsapp")
        hits2 = search_packages(pkgs, "n26")
        self.assertIn("de.number26.android", hits2)


if __name__ == "__main__":
    unittest.main()
