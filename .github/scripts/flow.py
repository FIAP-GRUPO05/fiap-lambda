"""Branch routing and pull request promotion for the Phase 3 pipeline.

Uses only the Python standard library. GitHub access is limited to promotions;
route checks run without a token and are also useful in local simulations.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request


RELEASE = re.compile(r"^release/v(\d+)\.(\d+)\.(\d+)$")
FEATURE = re.compile(r"^feature/[a-z0-9][a-z0-9._/-]*$")
ROLLBACK = re.compile(r"^(?:rollback|rolback)/[a-z0-9][a-z0-9._/-]*$")
FLOW = "feature/<descricao> → develop → release/vX.Y.Z → prod → main; rollback/<descricao> → release/vX.Y.Z"


def route(source, target):
    if target == "develop":
        valid = bool(FEATURE.fullmatch(source))
    elif RELEASE.fullmatch(target):
        valid = source == "develop" or bool(ROLLBACK.fullmatch(source))
    elif target == "prod":
        valid = bool(RELEASE.fullmatch(source))
    elif target == "main":
        valid = source == "prod"
    else:
        valid = False
    if not valid:
        raise ValueError(f"Rota proibida: {source} → {target}. Fluxo correto: {FLOW}")
    return True


def bump(version, title, labels):
    major, minor, patch = version
    names = {str(label).lower() for label in labels}
    if "breaking" in names or re.search(r"\bBREAKING CHANGE\b|^[a-z]+(?:\([^)]+\))?!:", title, re.I | re.M):
        return major + 1, 0, 0
    if "semver:minor" in names or re.search(r"^feat(?:\(.+\))?:", title, re.I | re.M):
        return major, minor + 1, 0
    return major, minor, patch + 1


def request(method, path, body=None):
    token = os.environ["GH_TOKEN"]
    repo = os.environ["GITHUB_REPOSITORY"]
    url = f"https://api.github.com/repos/{repo}/{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "fiap-phase3-pipeline",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers, method=method), timeout=30) as response:
        return json.load(response)


def branch(name):
    try:
        return request("GET", f"branches/{urllib.parse.quote(name, safe='')}")
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise


def ensure_branch(name, from_branch):
    existing = branch(name)
    if existing:
        return existing
    origin = branch(from_branch)
    if not origin:
        raise RuntimeError(f"Branch-base {from_branch} ausente; crie-a antes da promoção")
    request("POST", "git/refs", {"ref": f"refs/heads/{name}", "sha": origin["commit"]["sha"]})
    return branch(name)


def open_pr(head, base, title):
    owner = os.environ["GITHUB_REPOSITORY"].split("/")[0]
    query = urllib.parse.urlencode({"state": "open", "head": f"{owner}:{head}", "base": base, "per_page": 100})
    existing = request("GET", f"pulls?{query}")
    if existing:
        print(f"PR existente: {existing[0]['html_url']}")
        return
    if not branch(head) or not branch(base):
        raise RuntimeError(f"Não foi possível abrir PR: {head} ou {base} não existe")
    try:
        pr = request("POST", "pulls", {"head": head, "base": base, "title": title,
                                         "body": f"Promoção automática. Fluxo: {FLOW}\n\nO merge permanece manual."})
    except urllib.error.HTTPError as error:
        detail = error.read().decode()
        raise RuntimeError(f"Falha ao abrir PR {head} → {base}: {detail}") from error
    print(f"PR criado: {pr['html_url']}")


def release_version():
    branches = request("GET", "branches?per_page=100")
    versions = [tuple(map(int, match.groups())) for item in branches
                if (match := RELEASE.fullmatch(item["name"]))]
    return max(versions, default=(0, 0, 0))


def active_release():
    pulls = request("GET", "pulls?state=open&base=prod&per_page=100")
    versions = [(tuple(map(int, match.groups())), item["head"]["ref"])
                for item in pulls if (match := RELEASE.fullmatch(item["head"]["ref"]))]
    if not versions:
        raise RuntimeError("Rollback exige um PR release/vX.Y.Z → prod aberto")
    return max(versions)[1]


def pending_prod():
    if not branch("prod") or not branch("main"):
        return False
    comparison = request("GET", "compare/main...prod")
    return comparison.get("ahead_by", 0) > 0


def promote(event_name, ref, event):
    if event_name == "push":
        if FEATURE.fullmatch(ref):
            open_pr(ref, "develop", f"integrate: {ref} → develop")
        elif ROLLBACK.fullmatch(ref):
            if not pending_prod():
                raise RuntimeError("Rollback direto só é permitido enquanto prod estiver à frente de main")
            release = active_release()
            open_pr(ref, release, f"rollback: {ref} → {release}")
        elif ref == "develop" or RELEASE.fullmatch(ref) or ref == "prod":
            if event.get("created"):
                return
            candidates = request("GET", f"commits/{event['after']}/pulls?per_page=100")
            merged = [item for item in candidates if item.get("merged_at") and
                      item["base"]["ref"] == ref and item.get("merge_commit_sha") == event["after"]]
            if not merged:
                raise RuntimeError("Promocao de ambiente exige push originado por merge de um PR aprovado")
            merged_pr = {**merged[0], "merged": True}
            return promote("pull_request", ref, {"action": "closed", "pull_request": merged_pr})
        return

    pr = event["pull_request"]
    if event.get("action") != "closed" or not pr.get("merged"):
        return
    source, target = pr["head"]["ref"], pr["base"]["ref"]
    route(source, target)
    if target == "develop":
        titles = [pr["title"]]
        if "number" in pr:
            commits = request("GET", f"pulls/{pr['number']}/commits?per_page=100")
            titles.extend(item["commit"]["message"] for item in commits)
        version = bump(release_version(), "\n".join(titles), [label["name"] for label in pr.get("labels", [])])
        release = "release/v" + ".".join(map(str, version))
        ensure_branch(release, "prod" if branch("prod") else "main")
        open_pr("develop", release, f"release: {release}")
    elif RELEASE.fullmatch(target):
        ensure_branch("prod", "main")
        open_pr(target, "prod", f"promote: {target} → prod")
    elif target == "prod":
        open_pr("prod", "main", "promote: prod → main")


def main():
    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    ref = os.environ.get("GITHUB_REF_NAME", "")
    with open(os.environ["GITHUB_EVENT_PATH"], encoding="utf-8") as file:
        event = json.load(file)
    command = sys.argv[1]
    if command == "route":
        pr = event["pull_request"]
        route(pr["head"]["ref"], pr["base"]["ref"])
        print("Rota válida")
    elif command == "promote":
        promote(event_name, ref, event)
    else:
        raise ValueError(command)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, RuntimeError) as error:
        print(f"::error::{error}", file=sys.stderr)
        sys.exit(1)
