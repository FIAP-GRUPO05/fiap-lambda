import json
from pathlib import Path
import subprocess
import unittest

from deploy_notifications import deploy


class NotificationDeploymentTests(unittest.TestCase):
    def fake(self, health, function_error=False):
        self.calls = []
        def run(args, **kwargs):
            self.calls.append(args)
            operation = args[2]
            body = {}
            if operation == "get-alias": body = {"FunctionVersion": "7"}
            if operation == "update-function-code": body = {"Version": "8"}
            if operation == "invoke":
                Path(args[-3]).write_text(json.dumps(health), encoding="utf-8")
                if function_error: body = {"FunctionError": "Unhandled"}
            return subprocess.CompletedProcess(args, 0, json.dumps(body), "")
        return run

    def test_verified_sender_promotes_candidate_only_after_health(self):
        deploy("homol", "build/email.zip", self.fake({"ready": True, "provider": "SES"}))
        self.assertEqual(self.calls[-1][2], "update-alias")
        self.assertIn("fiap-email-homol", self.calls[-1])
        self.assertEqual(self.calls[-1][-3], "8")

    def test_failed_health_or_function_error_preserves_previous_alias(self):
        for result, error in (({"ready": False, "provider": "SES"}, False), ({"ready": True, "provider": "SMTP"}, False), ({"ready": True, "provider": "SES"}, True)):
            with self.subTest(result=result, error=error), self.assertRaises(RuntimeError):
                deploy("prod", "build/email.zip", self.fake(result, error))
            self.assertFalse(any(call[2] == "update-alias" for call in self.calls))

    def test_invalid_environment_never_calls_aws(self):
        with self.assertRaises(ValueError): deploy("other", "build/email.zip", self.fake({}))
        self.assertEqual(self.calls, [])
