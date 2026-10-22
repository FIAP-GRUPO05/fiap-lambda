import unittest
from ci_summary import render


class SummaryTests(unittest.TestCase):
    def test_maintenance_does_not_claim_external_services_were_validated(self):
        summary = render("maintenance", "success", [{"name": "Build", "outcome": "success"}])
        self.assertIn("✅ success", summary)
        self.assertIn("não foram executadas nem aprovadas", summary)
        self.assertIn("merge é manual", summary)

    def test_failure_and_skipped_checks_remain_visible(self):
        summary = render("maintenance", "failure", [
            {"name": "Testes", "outcome": "failure"}, {"name": "AWS", "outcome": "skipped"}])
        self.assertIn("❌ failure", summary)
        self.assertIn("⏸️ skipped", summary)
        self.assertIn("`failure`", summary)

    def test_destroyed_does_not_offer_environment_promotion(self):
        summary = render("destroyed", "success", [])
        self.assertIn("promoções entre ambientes permanecem bloqueadas", summary)

    def test_active_report_does_not_assume_successful_deployment(self):
        summary = render("active", "success", [])
        self.assertIn("respectivos jobs", summary)
        self.assertNotIn("Validações externas pendentes", summary)
