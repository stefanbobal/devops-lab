import unittest

import t3_chain


def row(case_id, expected, got, stage=None):
    return dict(case_id=case_id, expected=expected, got=got, stage=stage)


class SummaryTests(unittest.TestCase):
    def test_counts_missed_breach_and_false_alarm_separately(self):
        rows = [row("a", "breach", "no_breach"), row("b", "no_breach", "breach"),
                row("c", "breach", "breach"), row("d", "human_review", "human_review", "verify"),
                row("e", "no_breach", "human_review", "spec")]
        s = t3_chain.summarize(rows)
        self.assertEqual((s["exact"], s["missed_breach"], s["false_alarm"]), (2, ["a"], ["b"]))
        self.assertEqual((s["review_expected"], s["review_got"]), (1, 2))
        self.assertEqual(s["stopped_at"], {"verify": 1, "spec": 1})
        self.assertEqual(s["matrix"]["breach -> no_breach"], 1)

    def test_first_stop_names_the_failing_step(self):
        steps = [dict(step="extract", status="ok"), dict(step="check_items", status="problems")]
        self.assertEqual(t3_chain.first_stop(dict(steps=steps)), "check_items")
        self.assertIsNone(t3_chain.first_stop(dict(steps=[dict(step="evaluate", status="breach")])))

    def test_tag_is_required(self):
        with self.assertRaises(SystemExit):
            t3_chain.main([])


if __name__ == "__main__":
    unittest.main()
