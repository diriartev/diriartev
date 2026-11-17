#!/usr/bin/env python3
"""Generate self-hosted GitHub stats SVG cards for the profile README.

Runs inside GitHub Actions with the default GITHUB_TOKEN, so it does not depend
on any third-party service (github-readme-stats, streak-stats, etc.).

Outputs (into OUT_DIR, default ./dist):
  stats.svg   general stats
  streak.svg  contribution streak
  langs.svg   top languages by bytes in public, non-fork repos
"""
import datetime as dt
import html
import json
import os
import sys
import urllib.request

LOGIN = os.environ.get("GH_LOGIN", "diriartev")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
OUT_DIR = os.environ.get("OUT_DIR", "dist")
SAMPLE = os.environ.get("SAMPLE_JSON")  # local testing only

# Theme (matches the rest of the profile README)
BG_A, BG_B = "#0d1117", "#0f3460"
ACCENT = "#00b4d8"
TEXT = "#c9d1d9"
MUTED = "#8b949e"
TRACK = "#21262d"
FONT = "'Segoe UI', Ubuntu, 'Helvetica Neue', Sans-Serif"
W = 495


def gql(query, variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)
    if payload.get("errors"):
        raise RuntimeError(payload["errors"])
    return payload["data"]


USER_Q = """
query($login: String!, $cursor: String) {
  user(login: $login) {
    name
    createdAt
    followers { totalCount }
    pullRequests { totalCount }
    issues { totalCount }
    repositories(ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC,
                 first: 100, after: $cursor) {
      totalCount
      pageInfo { hasNextPage endCursor }
      nodes {
        stargazerCount
        languages(first: 20, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""

YEAR_Q = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      totalCommitContributions
      restrictedContributionsCount
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""


def fetch():
    cursor, repos, user = None, [], None
    while True:
        data = gql(USER_Q, {"login": LOGIN, "cursor": cursor})["user"]
        user = user or data
        repos += data["repositories"]["nodes"]
        page = data["repositories"]["pageInfo"]
        if not page["hasNextPage"]:
            break
        cursor = page["endCursor"]

    created = dt.datetime.fromisoformat(user["createdAt"].replace("Z", "+00:00"))
    now = dt.datetime.now(dt.timezone.utc)
    days, commits, contributions = {}, 0, 0
    for year in range(created.year, now.year + 1):
        start = max(created, dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc))
        end = min(now, dt.datetime(year, 12, 31, 23, 59, 59, tzinfo=dt.timezone.utc))
        cc = gql(YEAR_Q, {"login": LOGIN, "from": start.isoformat(), "to": end.isoformat()})
        cc = cc["user"]["contributionsCollection"]
        commits += cc["totalCommitContributions"] + cc["restrictedContributionsCount"]
        contributions += cc["contributionCalendar"]["totalContributions"]
        for w in cc["contributionCalendar"]["weeks"]:
            for d in w["contributionDays"]:
                days[d["date"]] = d["contributionCount"]

    langs = {}
    for repo in repos:
        for e in repo["languages"]["edges"]:
            name = e["node"]["name"]
            entry = langs.setdefault(name, {"size": 0, "color": e["node"]["color"] or MUTED})
            entry["size"] += e["size"]

    return {
        "name": user["name"] or LOGIN,
        "stars": sum(r["stargazerCount"] for r in repos),
        "repos": user["repositories"]["totalCount"],
        "followers": user["followers"]["totalCount"],
        "prs": user["pullRequests"]["totalCount"],
        "issues": user["issues"]["totalCount"],
        "commits": commits,
        "contributions": contributions,
        "days": days,
        "langs": langs,
        "today": now.date().isoformat(),
    }


# ---------------------------------------------------------------- helpers
def esc(s):
    return html.escape(str(s), quote=True)


def fmt(n):
    return f"{n/1000:.1f}k" if n >= 10000 else f"{n:,}"


def card(height, body, title):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{height}" viewBox="0 0 {W} {height}" role="img" aria-label="{esc(title)}">
<title>{esc(title)}</title>
<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0%" stop-color="{BG_A}"/><stop offset="100%" stop-color="{BG_B}"/>
  </linearGradient>
</defs>
<style>
  text {{ font-family: {FONT}; }}
  .t {{ font-size: 18px; font-weight: 600; fill: {ACCENT}; }}
  .l {{ font-size: 14px; fill: {TEXT}; }}
  .v {{ font-size: 14px; font-weight: 700; fill: {TEXT}; }}
  .m {{ font-size: 12px; fill: {MUTED}; }}
  .big {{ font-size: 28px; font-weight: 700; fill: {TEXT}; }}
  .fade {{ opacity: 0; animation: in .5s ease-out forwards; }}
  @keyframes in {{ to {{ opacity: 1; }} }}
</style>
<rect width="{W}" height="{height}" rx="10" fill="url(#bg)"/>
<text x="25" y="38" class="t">{esc(title)}</text>
{body}
</svg>
"""


ICONS = {  # 16x16 octicon-like paths
    "star": "M8 .25a.75.75 0 0 1 .673.418l1.882 3.815 4.21.612a.75.75 0 0 1 .416 1.279l-3.046 2.97.719 4.192a.75.75 0 0 1-1.088.791L8 12.347l-3.766 1.98a.75.75 0 0 1-1.088-.79l.72-4.194L.818 6.374a.75.75 0 0 1 .416-1.28l4.21-.611L7.327.668A.75.75 0 0 1 8 .25Z",
    "commit": "M11.93 8.5a4.002 4.002 0 0 1-7.86 0H.75a.75.75 0 0 1 0-1.5h3.32a4.002 4.002 0 0 1 7.86 0h3.32a.75.75 0 0 1 0 1.5Zm-1.43-.75a2.5 2.5 0 1 0-5 0 2.5 2.5 0 0 0 5 0Z",
    "pr": "M1.5 3.25a2.25 2.25 0 1 1 3 2.122v5.256a2.251 2.251 0 1 1-1.5 0V5.372A2.25 2.25 0 0 1 1.5 3.25Zm5.677-.177L9.573.677A.25.25 0 0 1 10 .854V2.5h1A2.5 2.5 0 0 1 13.5 5v5.628a2.251 2.251 0 1 1-1.5 0V5a1 1 0 0 0-1-1h-1v1.646a.25.25 0 0 1-.427.177L7.177 3.427a.25.25 0 0 1 0-.354Z",
    "issue": "M8 9.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3ZM8 0a8 8 0 1 1 0 16A8 8 0 0 1 8 0ZM1.5 8a6.5 6.5 0 1 0 13 0 6.5 6.5 0 0 0-13 0Z",
    "repo": "M2 2.5A2.5 2.5 0 0 1 4.5 0h8.75a.75.75 0 0 1 .75.75v12.5a.75.75 0 0 1-.75.75h-2.5a.75.75 0 0 1 0-1.5h1.75v-2h-8a1 1 0 0 0-.714 1.7.75.75 0 1 1-1.072 1.05A2.495 2.495 0 0 1 2 11.5Zm10.5-1h-8a1 1 0 0 0-1 1v6.708A2.486 2.486 0 0 1 4.5 9h8Z",
    "people": "M2 5.5a3.5 3.5 0 1 1 5.898 2.549 5.508 5.508 0 0 1 3.034 4.084.75.75 0 1 1-1.482.235 4 4 0 0 0-7.9 0 .75.75 0 0 1-1.482-.236A5.507 5.507 0 0 1 3.102 8.05 3.493 3.493 0 0 1 2 5.5ZM5.5 3.5a2 2 0 1 0 0 4 2 2 0 0 0 0-4Z",
    "fire": "M9.533.753V.752c.217 2.385 1.463 3.626 2.653 4.81C13.37 6.74 14.498 7.863 14.498 10c0 3.5-3 6-6.5 6S1.5 13.512 1.5 10c0-1.298.536-2.56 1.425-3.286.376-.308.862 0 1.035.454C4.46 8.487 5.581 8.419 6 8c.282-.282.341-.811-.003-1.5C4.34 3.187 7.035.75 8.77.146c.39-.137.726.194.763.607Z",
}


def icon(name, x, y):
    return f'<path transform="translate({x},{y})" fill="{ACCENT}" d="{ICONS[name]}"/>'


def parse(d):
    return dt.date.fromisoformat(d)


def short(d):
    return parse(d).strftime("%b %-d, %Y")


def span(a, b):
    a, b = parse(a), parse(b)
    if a == b:
        return b.strftime("%b %-d, %Y")
    if a.year == b.year:
        return f"{a.strftime('%b %-d')} - {b.strftime('%b %-d, %Y')}"
    return f"{a.strftime('%b %-d, %Y')} - {b.strftime('%b %-d, %Y')}"


# ---------------------------------------------------------------- cards
def stats_card(s):
    rows = [
        ("commit", "Total Commits", s["commits"]),
        ("star", "Stars Earned", s["stars"]),
        ("repo", "Public Repositories", s["repos"]),
        ("pr", "Pull Requests", s["prs"]),
        ("issue", "Issues", s["issues"]),
        ("people", "Followers", s["followers"]),
    ]
    body = []
    for i, (ic, label, val) in enumerate(rows):
        y = 70 + i * 25
        body.append(
            f'<g class="fade" style="animation-delay:{150 + i * 120}ms">'
            f'{icon(ic, 25, y - 12)}'
            f'<text x="50" y="{y}" class="l">{label}:</text>'
            f'<text x="230" y="{y}" class="v">{fmt(val)}</text></g>'
        )
    # ring: contributions in the last 365 days
    cutoff = (parse(s["today"]) - dt.timedelta(days=365)).isoformat()
    last_year = sum(v for k, v in s["days"].items() if k > cutoff)
    cx, cy, r = 395, 110, 50
    body.append(
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{TRACK}" stroke-width="6"/>'
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{ACCENT}" stroke-width="6" '
        f'stroke-linecap="round" stroke-dasharray="{2*3.1416*r:.1f}" transform="rotate(-90 {cx} {cy})"/>'
        f'<text x="{cx}" y="{cy - 2}" text-anchor="middle" class="big">{fmt(last_year)}</text>'
        f'<text x="{cx}" y="{cy + 18}" text-anchor="middle" class="m">last 365 days</text>'
    )
    return card(70 + len(rows) * 25 + 5, "\n".join(body), f"{s['name']}'s GitHub Stats")


def streaks(days, today):
    dates = sorted(days)
    longest = (0, None, None)
    run, start = 0, None
    for d in dates:
        if days[d] > 0:
            if run == 0:
                start = d
            run += 1
            if run > longest[0]:
                longest = (run, start, d)
        else:
            run = 0
    # current: walk back from today (today may still be 0)
    cur, cur_end = 0, None
    t = parse(today)
    if days.get(today, 0) == 0:
        t -= dt.timedelta(days=1)
    cur_end = t.isoformat()
    while days.get(t.isoformat(), 0) > 0:
        cur += 1
        t -= dt.timedelta(days=1)
    cur_start = (t + dt.timedelta(days=1)).isoformat()
    first = next((d for d in dates if days[d] > 0), today)
    return cur, cur_start, cur_end, longest, first


def streak_card(s):
    cur, cs, ce, (lng, ls, le), first = streaks(s["days"], s["today"])
    cur_range = span(cs, ce) if cur else "Start a new streak"
    lng_range = span(ls, le) if lng else "—"
    h = 195
    col = W / 3
    body = f"""
<line x1="{col:.0f}" y1="60" x2="{col:.0f}" y2="{h-25}" stroke="{TRACK}"/>
<line x1="{2*col:.0f}" y1="60" x2="{2*col:.0f}" y2="{h-25}" stroke="{TRACK}"/>
<g class="fade" style="animation-delay:150ms">
  <text x="{col/2:.0f}" y="110" text-anchor="middle" class="big">{fmt(s['contributions'])}</text>
  <text x="{col/2:.0f}" y="138" text-anchor="middle" class="l">Total Contributions</text>
  <text x="{col/2:.0f}" y="160" text-anchor="middle" class="m">{short(first)} - Present</text>
</g>
<g class="fade" style="animation-delay:300ms">
  <circle cx="{W/2:.0f}" cy="98" r="36" fill="none" stroke="{ACCENT}" stroke-width="5"/>
  <g transform="translate({W/2-8:.0f},52)"><circle cx="8" cy="8" r="11" fill="{BG_A}"/>{icon('fire', 0, 0)}</g>
  <text x="{W/2:.0f}" y="108" text-anchor="middle" class="big">{cur}</text>
  <text x="{W/2:.0f}" y="155" text-anchor="middle" class="v" style="fill:{ACCENT}">Current Streak</text>
  <text x="{W/2:.0f}" y="175" text-anchor="middle" class="m">{cur_range}</text>
</g>
<g class="fade" style="animation-delay:450ms">
  <text x="{2.5*col:.0f}" y="110" text-anchor="middle" class="big">{lng}</text>
  <text x="{2.5*col:.0f}" y="138" text-anchor="middle" class="l">Longest Streak</text>
  <text x="{2.5*col:.0f}" y="160" text-anchor="middle" class="m">{lng_range}</text>
</g>"""
    return card(h, body, "Contribution Streak")


def langs_card(s, top=8):
    items = sorted(s["langs"].items(), key=lambda kv: kv[1]["size"], reverse=True)[:top]
    total = sum(v["size"] for _, v in items) or 1
    bar_w = W - 50
    x = 25
    segs = []
    for name, v in items:
        w = bar_w * v["size"] / total
        segs.append(f'<rect x="{x:.2f}" y="55" width="{w:.2f}" height="10" fill="{v["color"]}"/>')
        x += w
    rows = []
    for i, (name, v) in enumerate(items):
        cx = 25 + (i % 2) * (bar_w / 2)
        cy = 95 + (i // 2) * 25
        pct = 100 * v["size"] / total
        rows.append(
            f'<g class="fade" style="animation-delay:{150 + i * 100}ms">'
            f'<circle cx="{cx + 5:.0f}" cy="{cy - 5}" r="5" fill="{v["color"]}"/>'
            f'<text x="{cx + 18:.0f}" y="{cy}" class="l">{esc(name)}</text>'
            f'<text x="{cx + bar_w / 2 - 20:.0f}" y="{cy}" text-anchor="end" class="m">{pct:.1f}%</text></g>'
        )
    h = 95 + ((len(items) + 1) // 2) * 25
    body = (
        f'<clipPath id="bar"><rect x="25" y="55" width="{bar_w}" height="10" rx="5"/></clipPath>'
        f'<g clip-path="url(#bar)">{"".join(segs)}</g>' + "".join(rows)
    )
    return card(h, body, "Most Used Languages")


def main():
    if SAMPLE:
        with open(SAMPLE) as f:
            s = json.load(f)
    else:
        if not TOKEN:
            sys.exit("GITHUB_TOKEN is required")
        s = fetch()
    os.makedirs(OUT_DIR, exist_ok=True)
    for name, svg in (("stats.svg", stats_card(s)), ("streak.svg", streak_card(s)), ("langs.svg", langs_card(s))):
        with open(os.path.join(OUT_DIR, name), "w", encoding="utf-8") as f:
            f.write(svg)
        print("wrote", name)


if __name__ == "__main__":
    main()
