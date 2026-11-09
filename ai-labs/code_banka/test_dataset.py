import unittest
from unittest import mock

import dataset
import t1_extraction
import t3_chain
import t3_spec


class ChooseSet(unittest.TestCase):
    def test_default_is_dev(self):
        self.assertEqual(dataset.choose_set(["--tag", "x"]), ("dev", dataset.SETS["dev"]))

    def test_test_set_without_final_is_refused(self):
        with self.assertRaises(SystemExit) as cm:
            dataset.choose_set(["--set", "test"])
        self.assertIn("--final", str(cm.exception))

    def test_test_set_with_final_is_allowed(self):
        name, folder = dataset.choose_set(["--set", "test", "--final"])
        self.assertEqual((name, folder.name), ("test", "data_test"))

    def test_final_alone_does_not_switch_to_the_test_set(self):
        self.assertEqual(dataset.choose_set(["--final"])[0], "dev")

    def test_unknown_or_missing_value_is_refused(self):
        for argv in (["--set", "prod"], ["--set"]):
            with self.assertRaises(SystemExit):
                dataset.choose_set(argv)

    def test_strip_set_flags_keeps_positional_arguments(self):
        self.assertEqual(dataset.strip_set_flags(["t5_a", "--set", "test", "--final", "t5_b"]), ["t5_a", "t5_b"])


class ScriptsRefuseTheTestSetWithoutFinal(unittest.TestCase):
    def test_t3_chain(self):
        with self.assertRaises(SystemExit) as cm:
            t3_chain.main(["--set", "test", "--tag", "zz_unit"])
        self.assertIn("held out", str(cm.exception))

    def test_t3_spec(self):
        with self.assertRaises(SystemExit) as cm:
            t3_spec.main(["haiku", "--set", "test", "--tag", "zz_unit"])
        self.assertIn("held out", str(cm.exception))

    def test_t1_extraction(self):
        with self.assertRaises(SystemExit) as cm:
            t1_extraction.main(["some_tag", "--set", "test"])
        self.assertIn("held out", str(cm.exception))

    def test_t3_spec_passes_the_set_to_the_worker_and_does_not_treat_final_as_a_profile(self):
        calls = []
        def fake_run(cmd, **kw):
            calls.append(kw["env"])
            raise KeyboardInterrupt   # stop after the first worker would start
        with mock.patch("subprocess.run", fake_run), self.assertRaises(KeyboardInterrupt):
            t3_spec.main(["haiku", "--set", "test", "--final", "--tag", "zz_unit"])
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["T3_SET"], "test")
        self.assertEqual(calls[0]["LLM_PROFILE"], "haiku")


if __name__ == "__main__":
    unittest.main()
