"""Guard the public/private budget boundary in the deployed Gateway configuration."""
from pathlib import Path
import re
import unittest

SOURCE = (Path(__file__).resolve().parents[2] / "infra/managed/gateway.tf").read_text(encoding="utf-8")
PUBLIC_SECTION = SOURCE.split("public_routes =", 1)[1].split("resource ", 1)[0]
PUBLIC_ROUTES = re.findall(r'"((?:GET|POST|PUT|PATCH|DELETE|ANY|HEAD) /[^"\n]+)"', PUBLIC_SECTION)


def is_public(method, path):
    for route in PUBLIC_ROUTES:
        verb, pattern = route.split(" ", 1)
        expression = re.sub(r'\{[^}]+\}', lambda match: '.+' if '+' in match.group() else '[^/]+', pattern)
        if verb in {method, "ANY"} and re.fullmatch(expression, path):
            return True
    return False


class BudgetGatewayTests(unittest.TestCase):
    def test_only_identification_landing_is_public(self):
        self.assertTrue(is_public("GET", "/service-orders/11111111-1111-1111-1111-111111111111/budget/decision"))
        for method, suffix in (("GET", ""), ("GET", "/decision/view"), ("POST", "/approve"), ("POST", "/reject")):
            with self.subTest(method=method, suffix=suffix):
                self.assertFalse(is_public(method, "/service-orders/11111111-1111-1111-1111-111111111111/budget" + suffix))

    def test_remaining_budget_routes_require_jwt_authorizer(self):
        protected = SOURCE.split('resource "aws_apigatewayv2_route" "protected"', 1)[1].split('resource "', 1)[0]
        self.assertRegex(protected, r'route_key\s*=\s*"ANY /\{proxy\+\}"')
        self.assertRegex(protected, r'authorization_type\s*=\s*"JWT"')
        self.assertRegex(protected, r'authorizer_id\s*=\s*aws_apigatewayv2_authorizer\.jwt\[each\.key\]\.id')


if __name__ == "__main__":
    unittest.main()
