"""Receipt audit regressions; no model calls or indexed application execution."""

import unittest

from efficiency_read_audit import audit


def receipt(tool, file="source.ts", identity="a" * 64, success=True, changed=True):
    return dict(
        tool=tool,
        arguments={"file": file},
        result={"file": file, "source_sha256": identity, "changed": changed},
        success=success,
    )


class ReadAudit(unittest.TestCase):
    def test_write_receipt_distinguishes_same_source_from_an_intervening_edit(self):
        result = audit(
            [
                receipt("source_read"),
                receipt("source_replace"),
                receipt("source_read"),
                receipt("source_read", identity="b" * 64),
                receipt("source_read", identity="a" * 64),
                receipt("source_replace", identity="b" * 64),
                receipt("source_read", identity="b" * 64),
            ]
        )
        self.assertEqual(result["counts"]["post_edit_same_hash_reads"], 2)
        self.assertEqual(result["counts"]["post_edit_changed_hash_reads"], 1)
        self.assertEqual(result["counts"]["post_edit_unknown_hash_reads"], 1)
        self.assertEqual(result["read_necessity"], "unknown")
        self.assertEqual(result["model_retention"], "unknown")

    def test_failed_or_missing_write_identity_never_justifies_reuse(self):
        for event in (
            receipt("source_replace", success=False),
            receipt("source_replace", identity=None),
        ):
            result = audit([receipt("source_replace"), event, receipt("source_read")])
            self.assertEqual(result["counts"]["post_edit_same_hash_reads"], 0)
            self.assertEqual(result["counts"]["post_edit_unknown_hash_reads"], 1)

    def test_unknown_or_mismatched_read_invalidates_the_previous_receipt(self):
        for identity in (None, "not-sha256"):
            result = audit(
                [
                    receipt("source_replace"),
                    receipt("source_read", identity=identity),
                    receipt("source_read"),
                ]
            )
            self.assertEqual(result["counts"]["post_edit_same_hash_reads"], 0)
            self.assertEqual(result["counts"]["post_edit_unknown_hash_reads"], 2)
        wrong = receipt("source_read")
        wrong["result"]["file"] = "other.ts"
        self.assertEqual(audit([wrong])["counts"]["reads_with_unknown_identity"], 1)

    def test_files_are_independent_and_eviction_is_visible(self):
        events = [
            receipt("source_replace", file="a"),
            receipt("source_replace", file="b"),
            receipt("source_read", file="a"),
        ]
        self.assertEqual(audit(events)["counts"]["post_edit_same_hash_reads"], 1)
        bounded = audit(events, max_files=1)
        self.assertEqual(bounded["counts"]["post_edit_same_hash_reads"], 0)
        self.assertEqual(bounded["counts"]["evicted_file_identities"], 1)
        self.assertEqual(bounded["counts"]["untracked_reads_after_eviction"], 1)
        self.assertFalse(bounded["post_edit_classification_complete"])

    def test_noop_write_with_different_source_and_failed_read_invalidate_receipts(self):
        for event in (
            receipt("source_replace", changed=False, identity="b" * 64),
            receipt("source_read", success=False),
        ):
            result = audit([receipt("source_replace"), event, receipt("source_read")])
            self.assertEqual(result["counts"]["post_edit_same_hash_reads"], 0)
            self.assertEqual(result["counts"]["post_edit_unknown_hash_reads"], 1)

    def test_invalid_or_excess_evidence_cannot_be_reported_complete(self):
        with self.assertRaises(ValueError):
            audit([receipt("source_read"), receipt("source_read")], max_records=1)
        with self.assertRaises(ValueError):
            audit([{"tool": "source_read"}])
        with self.assertRaises(ValueError):
            audit([], max_files=0)


if __name__ == "__main__":
    unittest.main()
