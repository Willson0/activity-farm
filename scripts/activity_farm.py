"""ActivityFarm: один шаг GitHub-практики за запуск + уведомление в Telegram.

Слоты (номер активности за день):
  1, 3, 5 — коммит в main
  2, 4    — новая ветка с коммитом + Pull Request (слот 4 сразу мерджится)
"""
import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

GH_TOKEN = os.environ["GH_TOKEN"]
REPO = os.environ["GITHUB_REPOSITORY"]  # владелец/репозиторий, Actions подставляет сам
TG_TOKEN = os.environ["TG_BOT_TOKEN"]
TG_CHAT_ID = os.environ["TG_CHAT_ID"]
START_DATE = os.environ["START_DATE"]  # YYYY-MM-DD, это будет день 1
SLOT = int(os.environ.get("SLOT", "1"))
BASE = "main"
YEKT = timezone(timedelta(hours=5))


class GHError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def gh(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {GH_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "activity-farm",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raise GHError(e.code, f"GitHub {method} {path}: {e.code} {e.read().decode()}") from None


def read_file(path, branch):
    """Возвращает (sha, текст). Если файла на ветке нет — (None, '')."""
    try:
        info = gh("GET", f"/repos/{REPO}/contents/{path}?ref={branch}")
    except GHError as e:
        if e.code == 404:
            return None, ""
        raise
    return info["sha"], base64.b64decode(info["content"]).decode()


def append_line(path, line, branch, message):
    sha, text = read_file(path, branch)
    body = {
        "message": message,
        "content": base64.b64encode((text + line + "\n").encode()).decode(),
        "branch": branch,
    }
    if sha:
        body["sha"] = sha
    gh("PUT", f"/repos/{REPO}/contents/{path}", body)


def create_branch(name):
    head = gh("GET", f"/repos/{REPO}/git/ref/heads/{BASE}")["object"]["sha"]
    gh("POST", f"/repos/{REPO}/git/refs", {"ref": f"refs/heads/{name}", "sha": head})


def open_pr(branch, title):
    return gh(
        "POST",
        f"/repos/{REPO}/pulls",
        {"title": title, "head": branch, "base": BASE, "body": "Ежедневная практика"},
    )


def merge_pr(number):
    gh("PUT", f"/repos/{REPO}/pulls/{number}/merge", {"merge_method": "squash"})


def notify(text):
    data = urllib.parse.urlencode({"chat_id": TG_CHAT_ID, "text": text}).encode()
    urllib.request.urlopen(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", data=data)


def main():
    now = datetime.now(YEKT)
    start = datetime.strptime(START_DATE, "%Y-%m-%d").replace(tzinfo=YEKT)
    day = (now.date() - start.date()).days + 1
    if day < 1:
        sys.exit(f"START_DATE {START_DATE} ещё не наступил")

    log = f"practice/day-{day:03d}.md"
    log_line = f"- {now:%H:%M} (ЕКБ), активность {SLOT}/5"
    repo_url = f"https://github.com/{REPO}"

    try:
        if SLOT in (2, 4):
            branch = f"practice/day-{day:03d}-slot-{SLOT}"
            create_branch(branch)
            append_line(log, log_line, branch, f"День {day}: активность {SLOT} (ветка)")
            pr = open_pr(branch, f"День {day}: активность {SLOT}")
            if SLOT == 4:
                merge_pr(pr["number"])
                action = f"ветка + PR #{pr['number']} смержен"
            else:
                action = f"ветка + открыт PR #{pr['number']}"
            link = pr["html_url"]
        else:
            append_line(log, log_line, BASE, f"День {day}: активность {SLOT} (коммит)")
            action = f"коммит в {BASE}"
            link = f"{repo_url}/blob/{BASE}/{log}"
    except GHError as e:
        notify(f"❌ ActivityFarm, день {day}, активность {SLOT}/5 упала:\n{e}")
        raise

    notify(f"🔥 День {day} · активность {SLOT}/5\n{action}\n{link}")
    print(f"OK: день {day}, слот {SLOT}, {action}")


if __name__ == "__main__":
    main()
