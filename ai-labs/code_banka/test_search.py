import json
import unittest
from unittest import mock

import search


class FindRelevantTests(unittest.TestCase):
    def setUp(self):
        self.tmp = search.Path(__file__).parent / "_test_thresholds.json"
        self.tmp.write_text(json.dumps([{"model": search.PROFILE, "threshold": 0.6}]))
        patcher = mock.patch.object(search, "THRESHOLDS_FILE", self.tmp)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.unlink)

    def test_drops_rows_below_threshold(self):
        rows = [{"similarity": 0.7}, {"similarity": 0.59}]
        with mock.patch.object(search, "find_similar", return_value=rows):
            self.assertEqual(search.find_relevant("q", "C01"), [{"similarity": 0.7}])

    def test_waiver_absent_skips_search(self):
        with mock.patch.object(search, "has_doc_type", return_value=False), \
             mock.patch.object(search, "find_similar") as fs:
            self.assertEqual(search.find_waiver("q", "C01"), [])
            fs.assert_not_called()

    def test_waiver_present_searches_only_waivers(self):
        with mock.patch.object(search, "has_doc_type", return_value=True), \
             mock.patch.object(search, "find_similar", return_value=[{"similarity": 0.9}]) as fs:
            self.assertEqual(len(search.find_waiver("q", "C05")), 1)
            self.assertEqual(fs.call_args.args[2], ("waiver",))

    def test_company_required(self):
        with self.assertRaises(ValueError):
            search.has_doc_type("", "waiver")


if __name__ == "__main__":
    unittest.main()
