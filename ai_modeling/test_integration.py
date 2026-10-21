"""Cross-domain contract tests; Python standard library only."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from load_scores import load_scores

ROOT = Path(__file__).resolve().parent


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for domain in ("economy", "safety"):
            name = f"{domain}/results/{domain}_scores.json"
            dest = self.root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes((ROOT / name).read_bytes())

    def edit_economy(self, fn):
        path = self.root / "economy/results/economy_scores.json"
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        fn(data)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def load(self):
        return load_scores(target_month="2026-10", base_dir=self.root)

    def test_join_keeps_scores_and_nulls(self):
        result = self.load()
        self.assertEqual(len(result["items"]), 427)
        originals = {}
        for domain in ("economy", "safety"):
            data = json.loads((self.root / f"{domain}/results/{domain}_scores.json").read_text(encoding="utf-8-sig"))
            originals[domain] = {r["region"]["region_code"]: r for r in data["items"]}
        for row in result["items"]:
            code = row["region"]["region_code"]
            for domain in ("economy", "safety"):
                self.assertEqual(row["scores"][domain], originals[domain][code]["scores"][domain])
                self.assertEqual(row["metadata"][domain], originals[domain][code]["metadata"][domain])
            for domain in ("energy", "comfort", "health"):
                self.assertIsNone(row["scores"][domain])

    def test_wrong_month_fails(self):
        with self.assertRaises(ValueError):
            load_scores(target_month="2026-11", base_dir=self.root)

    def test_ten_digit_code_fails(self):
        self.edit_economy(lambda d: d["items"][0]["region"].update(region_code="1111051500"))
        with self.assertRaises(ValueError): self.load()

    def test_duplicate_code_fails(self):
        self.edit_economy(lambda d: d["items"].__setitem__(1, deepcopy(d["items"][0])))
        with self.assertRaises(ValueError): self.load()

    def test_gu_mismatch_fails(self):
        self.edit_economy(lambda d: d["items"][0]["region"].update(sigungu_code="99999"))
        with self.assertRaises(ValueError): self.load()

    def test_missing_score_fails(self):
        self.edit_economy(lambda d: d["items"][0]["scores"].update(economy=None))
        with self.assertRaises(ValueError): self.load()

    def test_other_domain_overwrite_fails(self):
        self.edit_economy(lambda d: d["items"][0]["scores"].update(safety=0))
        with self.assertRaises(ValueError): self.load()

    def test_estimate_label_required(self):
        self.edit_economy(lambda d: d["items"][0]["metadata"]["economy"].update(status="observed"))
        with self.assertRaises(ValueError): self.load()


if __name__ == "__main__": unittest.main(verbosity=2)
