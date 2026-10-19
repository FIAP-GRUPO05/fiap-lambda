"""Offline check of branch routing, SemVer and PR promotion."""

import importlib.util
from pathlib import Path
from unittest.mock import patch

path = Path(__file__).with_name("flow.py")
spec = importlib.util.spec_from_file_location("flow", path)
flow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(flow)

opened = []
created = []
branches = {"main": {"commit": {"sha": "main"}}, "prod": {"commit": {"sha": "candidate"}}}


def fake_ensure(name, source):
    created.append((name, source))
    branches[name] = {"commit": {"sha": "candidate"}}


with patch.object(flow, "open_pr", side_effect=lambda head, base, title: opened.append((head, base))), \
     patch.object(flow, "branch", side_effect=lambda name: branches.get(name)), \
     patch.object(flow, "pending_prod", return_value=True), \
     patch.object(flow, "ensure_branch", side_effect=fake_ensure), \
     patch.object(flow, "release_version", return_value=(0, 1, 2)), \
     patch.object(flow, "active_release", return_value="release/v0.1.3"):
    flow.promote("push", "feature/fix-cpf", {})
    flow.promote("pull_request", "", {"action": "closed", "pull_request": {
        "merged": True, "title": "fix: validação de CPF", "labels": [],
        "head": {"ref": "feature/fix-cpf"}, "base": {"ref": "develop"}}})
    flow.promote("pull_request", "", {"action": "closed", "pull_request": {
        "merged": True, "head": {"ref": "develop"}, "base": {"ref": "release/v0.1.3"}}})
    flow.promote("pull_request", "", {"action": "closed", "pull_request": {
        "merged": True, "head": {"ref": "release/v0.1.3"}, "base": {"ref": "prod"}}})
    flow.promote("push", "rollback/revert-cpf", {})
    flow.promote("push", "rolback/revert-cpf", {})

assert opened == [
    ("feature/fix-cpf", "develop"), ("develop", "release/v0.1.3"),
    ("release/v0.1.3", "prod"), ("prod", "main"),
    ("rollback/revert-cpf", "release/v0.1.3"),
    ("rolback/revert-cpf", "release/v0.1.3"),
]
assert created == [("release/v0.1.3", "prod"), ("prod", "main")]
for source, target in (("fix/cpf", "develop"), ("feature/x", "prod"), ("develop", "main")):
    try:
        flow.route(source, target)
    except ValueError:
        continue
    raise AssertionError(f"Invalid route accepted: {source} → {target}")
print("Fluxo, SemVer e rollback simulados com sucesso")
