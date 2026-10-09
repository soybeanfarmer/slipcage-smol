"""Offline QEMU/KVM research tests: bounded public metadata, no target execution."""
from contextlib import redirect_stdout
from datetime import date
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

APP = Path(__file__).resolve().parents[1] / "app"
sys.path.insert(0, str(APP))
import isolab


def entry(cve_id, summary):
    return {"cve": {"id": cve_id, "published": "2026-10-01T00:00:00.000",
                    "lastModified": "2026-10-07T00:00:00.000",
                    "descriptions": [{"lang": "en", "value": summary}],
                    "references": [{"url": "https://github.com/qemu/qemu/commit/" + "a"*40}]}}


class QemuDiscoveryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.db = str(Path(tmp.name) / "research.sqlite3")

    def test_only_qemu_kvm_metadata_is_ingested_in_focus_mode(self):
        with isolab.connect(self.db) as conn:
            container = {"source": "nvd", "source_id": "CVE-2026-11111",
                         "cve": "CVE-2026-11111", "title": "containerd issue",
                         "summary": "runc may have an issue", "url": "https://nvd.nist.gov/vuln/detail/CVE-2026-11111"}
            qemu = {**container, "source_id": "CVE-2026-22222",
                    "title": "QEMU virtual device issue", "summary": "Reviewed metadata"}
            kvm = {**container, "source_id": "CVE-2026-33333",
                   "title": "Linux KVM issue", "summary": "Reviewed metadata"}
            self.assertFalse(isolab.record(conn, container, focus="qemu"))
            self.assertTrue(isolab.record(conn, qemu, focus="qemu"))
            self.assertTrue(isolab.record(conn, kvm, focus="qemu"))
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM candidates").fetchone()[0], 2)
            self.assertEqual(set(r[0] for r in conn.execute("SELECT track FROM candidates")),
                             {"hypervisor"})
            with self.assertRaises(ValueError):
                isolab.record(conn, qemu, focus="unknown")

    def test_incidental_qemu_guest_mentions_do_not_qualify(self):
        # This mirrors the real NVD pattern: a Linux device bug was
        # reproduced *inside* QEMU, but QEMU is not the affected subsystem.
        irrelevant = entry("CVE-2026-98238",
            "In the Linux kernel, the following vulnerability has been resolved:\n\n"
            "net: wwan: t7xx: validate the netif index in t7xx_ccmni_recv_skb()\n\n"
            "Verified in a QEMU guest with a fault injector.")
        relevant = entry("CVE-2026-98164",
            "In the Linux kernel, the following vulnerability has been resolved:\n\n"
            "KVM: x86/mmu: Check write tracking in all address spaces\n\n"
            "The issue affects KVM page tracking.")
        self.assertEqual(isolab.primary_advisory_subject(
            "CVE-2026-98238: Linux kernel issue",
            irrelevant["cve"]["descriptions"][0]["value"]),
            "net: wwan: t7xx: validate the netif index in t7xx_ccmni_recv_skb()")
        with isolab.connect(self.db) as conn:
            self.assertFalse(isolab.record(conn, isolab.nvd_item(irrelevant), focus="qemu"))
            self.assertTrue(isolab.record(conn, isolab.nvd_item(relevant), focus="qemu"))
        fetch = lambda url: {"totalResults": 2, "vulnerabilities": [irrelevant, relevant]}
        found = isolab.nvd_qemu_publications(
            date(2026, 10, 1), date(2026, 10, 7), fetcher=fetch)
        self.assertEqual([item["source_id"] for item in found], ["CVE-2026-98164"])

    def test_leads_hide_prior_false_positives_without_deleting_them(self):
        examples = [
            ("CVE-2026-98238", "net: wwan: t7xx: bounds check",
             "Verified in a QEMU guest.", "reviewed"),
            ("CVE-2026-98283", "KVM: PPC: Book3S HV: use-after-free",
             "Memory issue in KVM PPC.", "pending"),
            ("CVE-2026-98164", "KVM: x86/mmu: Check write tracking",
             "MMU code in KVM x86.", "pending"),
            ("CVE-2024-7409", "QEMU NBD Server synchronization flaw",
             "QEMU NBD socket closing.", "reviewed"),
        ]
        with isolab.connect(self.db) as conn:
            for cv, heading, detail, status in examples:
                item = {"source": "nvd", "source_id": cv, "cve": cv,
                        "title": cv + ": In the Linux kernel, the following vulnerability has been resolved:\n\n" + heading,
                        "summary": "In the Linux kernel, the following vulnerability has been resolved:\n\n"
                                   + heading + "\n\n" + detail,
                        "url": "https://nvd.nist.gov/vuln/detail/" + cv}
                # Ordinary mixed-scope sync may already have admitted a
                # body-only match; the shortlist must exclude it.
                self.assertTrue(isolab.record(conn, item))
                conn.execute("UPDATE candidates SET status=? WHERE source_id=?", (status, cv))
            conn.commit()
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(isolab.qemu_leads(self.db, limit=15), 0)
        leads = json.loads(out.getvalue())["leads"]
        self.assertEqual([x["cve"] for x in leads],
            ["CVE-2026-98164", "CVE-2024-7409", "CVE-2026-98283"])
        self.assertEqual([x["lab_fit"] for x in leads],
            ["x86_64", "architecture_unspecified", "other_architecture"])
        self.assertEqual(leads[0]["affected_subsystem"],
                         "KVM: x86/mmu: Check write tracking")
        with isolab.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM candidates").fetchone()[0], 4)
            self.assertEqual(conn.execute(
                "SELECT status FROM candidates WHERE source_id='CVE-2026-98238'"
            ).fetchone()[0], "reviewed")


    def test_bounded_publication_search_only_calls_nvd_with_fixed_keywords(self):
        seen = []
        fixtures = {
            "QEMU": [entry("CVE-2026-10001", "QEMU device regression"),
                     entry("CVE-2026-10002", "QEMU security fix")],
            "KVM": [entry("CVE-2026-10001", "QEMU device regression"),
                    entry("CVE-2026-10003", "Linux KVM regression"),
                    entry("CVE-2026-99999", "Unrelated containerd issue")],
        }
        def fetch(url):
            seen.append(url)
            parts = urlsplit(url)
            self.assertEqual(parts.netloc, "services.nvd.nist.gov")
            self.assertEqual(parts.path, "/rest/json/cves/2.0")
            q = parse_qs(parts.query)
            self.assertEqual(q["resultsPerPage"], ["200"])
            self.assertEqual(q["startIndex"], ["0"])
            self.assertEqual(q["pubStartDate"], ["2026-09-01T00:00:00.000+00:00"])
            self.assertEqual(q["pubEndDate"], ["2026-09-14T23:59:59.000+00:00"])
            term = q["keywordSearch"][0]
            return {"totalResults": len(fixtures[term]),
                    "vulnerabilities": fixtures[term]}
        items = isolab.nvd_qemu_publications(date(2026, 9, 1),
                                              date(2026, 9, 14), fetcher=fetch)
        self.assertEqual([i["source_id"] for i in items],
                         ["CVE-2026-10001", "CVE-2026-10002", "CVE-2026-10003"])
        self.assertEqual(len(seen), 2)
        self.assertTrue(all("https://services.nvd.nist.gov/" in x for x in seen))

    def test_publication_backfill_is_idempotent_and_enriched(self):
        e = entry("CVE-2026-10042", "QEMU memory corruption fixed in release")
        def fetch(url):
            return {"totalResults": 1, "vulnerabilities": [e]}
        for _ in range(2):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(isolab.backfill_qemu(
                    self.db, date(2026, 10, 1), date(2026, 10, 7),
                    fetcher=fetch), 0)
        with isolab.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM candidates").fetchone()[0], 1)
            row = conn.execute("SELECT track,status FROM candidates").fetchone()
            self.assertEqual(tuple(row), ("hypervisor", "pending"))
            self.assertEqual(conn.execute(
                "SELECT COUNT(*) FROM candidate_intelligence").fetchone()[0], 1)
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(isolab.qemu_leads(self.db, limit=5), 0)
        report = json.loads(out.getvalue())
        self.assertFalse(report["vulnerability_reproduced"])
        self.assertEqual(report["focus"], "QEMU/KVM")
        self.assertEqual(len(report["leads"]), 1)
        self.assertIn("qemu/qemu/commit", report["leads"][0]["unverified_patch_refs"][0])
        self.assertNotIn("summary", report["leads"][0])

    def test_backfill_refuses_bad_window_before_network_or_db(self):
        call = lambda _: self.fail("must not fetch")
        for start,end in [(date(2026, 9, 1), date(2026, 10, 2)),
                          (date(2026, 10, 2), date(2026, 10, 1))]:
            with self.assertRaises(ValueError):
                isolab.backfill_qemu(self.db, start, end, fetcher=call)
        self.assertFalse(Path(self.db).exists())

    def test_incomplete_and_oversized_response_never_creates_partial_db(self):
        for total, items in [
            (601, [entry("CVE-2026-10001", "QEMU regression")]),
            (201, [entry("CVE-2026-10001", "QEMU regression")]),
            (2, [entry("CVE-2026-10001", "QEMU regression")]),
        ]:
            with self.subTest(total=total):
                with self.assertRaises(ValueError):
                    isolab.backfill_qemu(
                        self.db, date(2026, 10, 1), date(2026, 10, 2),
                        fetcher=lambda _: {"totalResults": total, "vulnerabilities": items})
                self.assertFalse(Path(self.db).exists())

    def test_failed_second_keyword_does_not_commit_first(self):
        def fetch(url):
            keyword = parse_qs(urlsplit(url).query)["keywordSearch"][0]
            if keyword == "KVM":
                raise OSError("NVD unavailable")
            return {"totalResults": 1,
                    "vulnerabilities": [entry("CVE-2026-10001", "QEMU regression")]}
        with self.assertRaises(OSError):
            isolab.backfill_qemu(self.db, date(2026, 10, 1), date(2026, 10, 2),
                                  fetcher=fetch)
        self.assertFalse(Path(self.db).exists())

    def test_qemu_lead_bounds_and_no_report_execution(self):
        for limit in (0, 26):
            with self.assertRaises(ValueError):
                isolab.qemu_leads(self.db, limit=limit)
        self.assertFalse(Path(self.db).exists())

    def test_native_discovery_keeps_container_scope_and_has_no_dagu(self):
        root = APP.parent
        script = (root / "scripts/discover.sh").read_text()
        self.assertIn("isolab.py sync --db /srv/isolab/research.sqlite3", script)
        self.assertNotIn("--focus qemu", script)
        self.assertNotIn("dagu", script)
        self.assertNotIn("enqueue", script)
        # Scheduled discovery continues to collect the default mixed scope.
        container = {"source": "nvd", "source_id": "CVE-2026-99998",
                     "title": "containerd advisory", "summary": "runc metadata",
                     "url": "https://nvd.nist.gov/vuln/detail/CVE-2026-99998"}
        with isolab.connect(self.db) as conn:
            self.assertTrue(isolab.record(conn, container))
            self.assertEqual(conn.execute("SELECT track FROM candidates").fetchone()[0],
                             "container")

    def test_rebackfill_preserves_reviewed_candidate(self):
        e = entry("CVE-2026-10042", "QEMU memory corruption fixed in release")
        fetch = lambda _: {"totalResults": 1, "vulnerabilities": [e]}
        with redirect_stdout(io.StringIO()):
            isolab.backfill_qemu(self.db, date(2026, 10, 1),
                                date(2026, 10, 7), fetcher=fetch)
        with isolab.connect(self.db) as conn:
            conn.execute("UPDATE candidates SET status='reviewed'")
            conn.commit()
        with redirect_stdout(io.StringIO()):
            isolab.backfill_qemu(self.db, date(2026, 10, 1),
                                date(2026, 10, 7), fetcher=fetch)
        with isolab.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT status FROM candidates").fetchone()[0],
                             "reviewed")
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM candidates").fetchone()[0],
                             1)

    def test_backfill_refuses_changed_total_between_nvd_pages(self):
        rows = [entry(f"CVE-2026-{30000+i}", "QEMU device advisory")
                for i in range(200)]
        def fetch(url):
            q = parse_qs(urlsplit(url).query)
            if q["startIndex"] == ["0"]:
                return {"totalResults": 201, "vulnerabilities": rows}
            return {"totalResults": 1, "vulnerabilities": []}
        with self.assertRaises(ValueError):
            isolab.backfill_qemu(self.db, date(2026, 10, 1),
                                date(2026, 10, 2), fetcher=fetch)
        self.assertFalse(Path(self.db).exists())


if __name__ == "__main__":
    unittest.main()
