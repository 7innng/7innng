import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

START = "<!-- open-source:start -->"
END = "<!-- open-source:end -->"
CHINA = timezone(timedelta(hours=8))
QUERY = """
query($q: String!) {
  search(query: $q, type: ISSUE, first: 100) {
    nodes {
      ... on PullRequest {
        number
        title
        url
        state
        isDraft
        createdAt
        mergedAt
        additions
        deletions
        changedFiles
        repository { nameWithOwner url }
      }
    }
  }
}
"""


def fetch_pull_requests(login, token):
    search = f"is:pr is:public author:{login} -user:{login}"
    payload = json.dumps({"query": QUERY, "variables": {"q": search}}).encode()
    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=payload,
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        body = json.load(response)
    if body.get("errors"):
        raise SystemExit(json.dumps(body["errors"], ensure_ascii=False))
    return [node for node in body["data"]["search"]["nodes"] if node]


def is_listed(pull):
    if pull["state"] == "MERGED":
        return True
    return pull["state"] == "OPEN" and not pull["isDraft"]


def sort_key(pull):
    merged_first = 0 if pull["state"] == "MERGED" else 1
    moment = pull["mergedAt"] or pull["createdAt"]
    return (merged_first, -datetime.fromisoformat(moment.replace("Z", "+00:00")).timestamp())


def table_text(value):
    return value.replace("|", "\\|").replace("<", "&lt;").replace(">", "&gt;")


def china_date(moment):
    return datetime.fromisoformat(moment.replace("Z", "+00:00")).astimezone(CHINA).date().isoformat()


def render_row(pull, notes):
    repo = pull["repository"]["nameWithOwner"]
    stars = (
        f'<img alt="GitHub stars" src="https://img.shields.io/github/stars/{repo}'
        f'?style=flat-square&label=stars&color=1C6CB0">'
    )
    project = f'[**{repo}**]({pull["repository"]["url"]})<br>{stars}'

    note = notes.get(pull["url"])
    if note:
        contribution = f'[#{pull["number"]} {note["title"]}]({pull["url"]})：{note["zh"]}<br><sub>{note["en"]}</sub>'
    else:
        contribution = f'[#{pull["number"]} {table_text(pull["title"])}]({pull["url"]})'

    size = f'+{pull["additions"]} / −{pull["deletions"]}<br><sub>{pull["changedFiles"]} 个文件 files</sub>'

    if pull["state"] == "MERGED":
        status = f'已合并<br><sub>Merged {china_date(pull["mergedAt"])}</sub>'
    else:
        status = "审核中<br><sub>In review</sub>"

    return f"| {project} | {contribution} | {size} | {status} |"


def render_section(pulls, notes):
    if not pulls:
        return ""
    rows = "\n".join(render_row(pull, notes) for pull in pulls)
    return (
        "## 开源贡献 / Open source\n\n"
        "| 项目<br>Project | 贡献<br>Contribution | 规模<br>Size | 状态<br>Status |\n"
        "| --- | --- | :-: | :-: |\n"
        f"{rows}\n"
    )


def main():
    readme_path, notes_path = Path(sys.argv[1]), Path(sys.argv[2])
    login = os.environ["PROFILE_LOGIN"]
    notes = json.loads(notes_path.read_text(encoding="utf-8"))
    pulls = sorted(filter(is_listed, fetch_pull_requests(login, os.environ["GITHUB_TOKEN"])), key=sort_key)

    readme = readme_path.read_text(encoding="utf-8")
    head, rest = readme.split(START, 1)
    _, tail = rest.split(END, 1)
    section = render_section(pulls, notes)
    updated = f"{head}{START}\n{section}{END}{tail}"

    if updated == readme:
        print(f"Open-source section unchanged ({len(pulls)} pull requests)")
        return
    readme_path.write_text(updated, encoding="utf-8")
    print(f"Open-source section updated ({len(pulls)} pull requests)")


main()
