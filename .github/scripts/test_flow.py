"""Regression checks for branch promotion and semantic release versions."""
import os
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
             patch.object(flow, "release_for_commit", return_value=None), \
             patch.object(flow, "pending_messages", return_value=[]), \
             patch.object(flow, "release_version", return_value=(0, 1, 2)), \
             patch.object(flow, "branch", return_value={"name": "prod"}), \
             patch.object(flow, "ensure_branch") as ensure, patch.object(flow, "open_pr") as opened:
            flow.promote("push", "develop", {"after": "abc", "created": False})
            ensure.assert_called_once_with("release/v0.2.0", "prod")
            opened.assert_called_once_with("develop", "release/v0.2.0", "release: release/v0.2.0", source_sha="abc")

    def test_retry_of_same_merge_does_not_allocate_another_version(self):
        pr = {"number": 7, "merged_at": "2026-01-01", "merge_commit_sha": "abc",
              "head": {"ref": "feature/catalogo"}, "base": {"ref": "develop"}}
        with patch.object(flow, "request", return_value=[pr]), \
             patch.object(flow, "release_for_commit", return_value={"html_url": "https://github.com/org/repo/pull/8"}), \
             patch.object(flow, "release_version") as version, patch.object(flow, "open_pr") as opened:
            flow.promote("push", "develop", {"after": "abc", "created": False})
            version.assert_not_called()
            opened.assert_not_called()

    def test_pending_feature_is_included_when_latest_merge_is_only_a_fix(self):
        pr = {"number": 7, "merged": True, "merge_commit_sha": "abc", "title": "fix: automacao",
              "head": {"ref": "feature/automacao"}, "base": {"ref": "develop"}, "labels": []}
        with patch.object(flow, "request", return_value=[{"commit": {"message": "fix(ci): corrige manutencao"}}]), \
             patch.object(flow, "release_for_commit", return_value=None), \
             patch.object(flow, "pending_messages", return_value=["feat(config): adiciona operacao"]), \
             patch.object(flow, "release_version", return_value=(0, 2, 0)), \
             patch.object(flow, "branch", return_value={"name": "prod"}), \
             patch.object(flow, "ensure_branch") as ensure, patch.object(flow, "open_pr"):
            flow.promote("pull_request", "develop", {"action": "closed", "pull_request": pr})
            ensure.assert_called_once_with("release/v0.3.0", "prod")

    def test_release_history_lookup_reuses_closed_or_merged_promotion(self):
        recorded = {"base": {"ref": "release/v0.3.0"}, "body": "<!-- fiap-promotion-source:abc -->", "state": "closed"}
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "org/repo"}), \
             patch.object(flow, "request", return_value=[recorded]):
            self.assertIs(flow.release_for_commit("abc"), recorded)

    def test_pending_commit_history_is_paginated(self):
        page = [{"commit": {"message": "fix: item"}}] * 100
        with patch.object(flow, "request", side_effect=[{"commits": page}, {"commits": [{"commit": {"message": "feat: ultimo"}}]}]) as request:
            messages = flow.pending_messages("prod")
            self.assertEqual(len(messages), 101)
            self.assertEqual(messages[-1], "feat: ultimo")
            self.assertIn("page=2", request.call_args_list[-1].args[1])

    def test_destroy_states_block_environment_promotion_before_api_calls(self):
        for state in ("destroying", "destroyed"):
            for ref in ("develop", "release/v0.3.0", "prod"):
                with self.subTest(state=state, ref=ref), patch.dict(os.environ, {"FIAP_INFRA_STATE": state}), \
                     patch.object(flow, "request") as request:
                    with self.assertRaises(RuntimeError):
                        flow.promote("push", ref, {"after": "abc", "created": False})
                    request.assert_not_called()

    def test_maintenance_preserves_release_to_prod_and_prod_to_main_sequence(self):
        pairs = [("develop", "release/v0.3.0", ("release/v0.3.0", "prod", "promote: release/v0.3.0 → prod")),
                 ("release/v0.3.0", "prod", ("prod", "main", "promote: prod → main"))]
        for source, target, expected in pairs:
            pr = {"head": {"ref": source}, "base": {"ref": target}, "merged": True}
            with self.subTest(target=target), patch.dict(os.environ, {"FIAP_INFRA_STATE": "maintenance"}), \
                 patch.object(flow, "ensure_branch"), patch.object(flow, "open_pr") as opened:
                flow.promote("pull_request", target, {"action": "closed", "pull_request": pr})
                opened.assert_called_once_with(*expected)

    def test_maintenance_pr_description_identifies_pending_external_checks(self):
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "org/repo", "FIAP_INFRA_STATE": "maintenance"}), \
             patch.object(flow, "request", side_effect=[[], {"html_url": "https://github.com/org/repo/pull/8"}]) as request, \
             patch.object(flow, "branch", return_value={"name": "existing"}):
            flow.open_pr("develop", "release/v0.3.0", "release", source_sha="abc")
            body = request.call_args.args[2]["body"]
            self.assertIn("deploys AWS bloqueados", body)
            self.assertIn("continuam pendentes", body)
            self.assertLessEqual(len(body.splitlines()), 10)

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

    def test_rollback_finds_release_after_its_prod_pr_was_merged(self):
        deployed = {"merged_at": "2026-01-01", "merge_commit_sha": "deployed",
                    "head": {"ref": "release/v0.2.0"}, "base": {"ref": "prod"}}
        pending = {"merged_at": None, "head": {"ref": "release/v0.3.0"}, "base": {"ref": "prod"}}
        with patch.object(flow, "branch", side_effect=[{"commit": {"sha": "deployed"}}, {"name": "release/v0.2.0"}]), \
             patch.object(flow, "request", return_value=[pending, deployed]) as request:
            self.assertEqual(flow.active_release(), "release/v0.2.0")
            request.assert_called_once_with("GET", "commits/deployed/pulls?per_page=100")

    def test_rollback_does_not_choose_an_unrelated_release(self):
        unrelated = {"merged_at": "2026-01-01", "merge_commit_sha": "old",
                     "head": {"ref": "release/v0.1.0"}, "base": {"ref": "prod"}}
        with patch.object(flow, "branch", return_value={"commit": {"sha": "deployed"}}), \
             patch.object(flow, "request", return_value=[unrelated]):
            with self.assertRaises(RuntimeError):
                flow.active_release()

    def test_rollback_requires_prod_ahead_of_main(self):
        with patch.object(flow, "pending_prod", return_value=False), patch.object(flow, "open_pr") as opened:
            with self.assertRaises(RuntimeError):
                flow.promote("push", "rollback/restaurar", {})
            opened.assert_not_called()

if __name__ == "__main__":
    unittest.main()

