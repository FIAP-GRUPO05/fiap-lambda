"""Regression checks for branch promotion and semantic release versions."""
import unittest
from unittest.mock import patch
import flow

class PromotionTests(unittest.TestCase):
    def test_develop_push_uses_merged_pr_and_feature_commits(self):
        pr = {"number": 7, "merged_at": "2026-01-01", "merge_commit_sha": "abc",
              "head": {"ref": "feature/catalogo"}, "base": {"ref": "develop"},
              "title": "integrate: catalogo", "labels": []}
        responses = [[pr], [{"commit": {"message": "docs: descreve a API"}},
                            {"commit": {"message": "feat(catalogo): adiciona recurso"}}]]
        with patch.object(flow, "request", side_effect=responses), \
             patch.object(flow, "release_version", return_value=(0, 1, 2)), \
             patch.object(flow, "branch", return_value={"name": "prod"}), \
             patch.object(flow, "ensure_branch") as ensure, patch.object(flow, "open_pr") as opened:
            flow.promote("push", "develop", {"after": "abc", "created": False})
            ensure.assert_called_once_with("release/v0.2.0", "prod")
            opened.assert_called_once_with("develop", "release/v0.2.0", "release: release/v0.2.0")

    def test_direct_push_cannot_promote_without_a_merged_pr(self):
        with patch.object(flow, "request", return_value=[]), patch.object(flow, "open_pr") as opened:
            with self.assertRaises(RuntimeError):
                flow.promote("push", "develop", {"after": "abc", "created": False})
            opened.assert_not_called()

    def test_creating_release_branch_does_not_promote_it(self):
        with patch.object(flow, "request") as request:
            flow.promote("push", "release/v0.2.0", {"created": True})
            request.assert_not_called()

    def test_scoped_breaking_commit_bumps_major(self):
        self.assertEqual(flow.bump((1, 2, 3), "docs: contexto\nfeat(api)!: altera contrato", []), (2, 0, 0))

    def test_invalid_source_cannot_promote_to_prod(self):
        with self.assertRaises(ValueError):
            flow.route("feature/atalho", "prod")

if __name__ == "__main__":
    unittest.main()

