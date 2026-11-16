#!/usr/bin/env python3
"""develop → main PR 본문의 '릴리스 노트'로 다음 버전 · 이미지 description · Release 노트를 만든다 (GPU-136).

PR 본문 형식 (`## 릴리스 노트` 섹션 안, 항목 사이는 빈 줄):

    ## 릴리스 노트

    feat: 이미지에 semver 태그 추가
    Refs: GPU-136

    fix!: 체크포인트 경로 변경
    Refs: GPU-150, GPU-151
    BREAKING CHANGE: 기존 ckpt 경로를 읽지 못함

type: feat → minor, `!` 또는 BREAKING CHANGE → major, 그 밖(fix · perf · refactor · chore …) → patch.
버전은 레포 단위 하나다 (git 태그 vX.Y.Z). 태그가 없으면 첫 릴리스는 1.0.0.

    release.py plan --body-file pr.md [--repo-dir .] [--pr 13] [--jira-url URL]
      → stdout JSON {version, tag, previous, tag_exists, bump, description, notes, entries}
      → 형식 오류면 ::error:: 줄을 찍고 종료 코드 1

Python 3.9+ 표준 라이브러리만 쓴다.
"""
import argparse
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from typing import List, Optional, Tuple

SECTION = "릴리스 노트"
TYPES = ("feat", "fix", "perf", "refactor", "revert", "docs", "style", "test", "build", "ci", "chore")
HEADER_RE = re.compile(r"^(?P<type>[a-z]+)(?:\((?P<scope>[^()\s]+)\))?(?P<bang>!)?: (?P<summary>\S.*)$")
REFS_RE = re.compile(r"^Refs:\s*(?P<keys>.+)$")
BREAKING_RE = re.compile(r"^BREAKING[ -]CHANGE:\s*(?P<text>.+)$")
JIRA_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]+-[0-9]+$")
SEMVER_TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
DESCRIPTION_MAX = 512  # GHCR org.opencontainers.image.description 한도
JIRA_URL = "https://devoops-team.atlassian.net"
SECTIONS = (("breaking", "⚠ 호환성 깨짐"), ("feat", "기능"), ("fix", "버그 수정"), ("other", "기타"))


class NotesError(Exception):
    def __init__(self, problems: List[str]):
        super().__init__("\n".join(problems))
        self.problems = problems


@dataclass
class Entry:
    type: str
    summary: str
    refs: List[str]
    scope: Optional[str] = None
    breaking: bool = False
    breaking_note: Optional[str] = None

    @property
    def header(self) -> str:
        scope = f"({self.scope})" if self.scope else ""
        return f"{self.type}{scope}{'!' if self.breaking else ''}: {self.summary}"


def _section_lines(body: str) -> List[str]:
    body = re.sub(r"<!--.*?-->", "", body.replace("\r\n", "\n"), flags=re.S)
    lines, inside, found = [], False, False
    for line in body.split("\n"):
        heading = re.match(r"^#{1,6}\s+(.*?)\s*#*\s*$", line)
        if heading:
            inside = heading.group(1) == SECTION
            found = found or inside
            continue
        if inside:
            lines.append(line.strip())
    if not found:
        raise NotesError([f"PR 본문에 '## {SECTION}' 섹션이 없음"])
    return lines


def parse_notes(body: str) -> List[Entry]:
    blocks, cur = [], []
    for line in _section_lines(body) + [""]:
        if line:
            cur.append(line)
        elif cur:
            blocks.append(cur)
            cur = []
    if not blocks:
        raise NotesError([f"'{SECTION}' 섹션에 항목이 없음"])

    entries, problems = [], []
    for block in blocks:
        head, rest = block[0], block[1:]
        m = HEADER_RE.match(head)
        if not m or m.group("type") not in TYPES:
            problems.append(f"형식이 '<type>: 요약'이 아님 (type: {', '.join(TYPES)}): '{head}'")
            continue
        entry = Entry(type=m.group("type"), summary=m.group("summary").strip(), refs=[],
                      scope=m.group("scope"), breaking=bool(m.group("bang")))
        for line in rest:
            refs, brk = REFS_RE.match(line), BREAKING_RE.match(line)
            if refs:
                keys = [k.strip() for k in refs.group("keys").split(",") if k.strip()]
                bad = [k for k in keys if not JIRA_KEY_RE.match(k)]
                if bad:
                    problems.append(f"Jira 키 형식(GPU-123)이 아님: {', '.join(bad)} — '{head}'")
                entry.refs.extend(keys)
            elif brk:
                entry.breaking, entry.breaking_note = True, brk.group("text").strip()
            else:
                problems.append(f"알 수 없는 줄 (Refs: · BREAKING CHANGE:만 가능): '{line}' — '{head}'")
        if not entry.refs:
            problems.append(f"Refs: GPU-n 줄이 없음 — '{head}'")
        entries.append(entry)
    if problems:
        raise NotesError(problems)
    return entries


def _git_tags(repo_dir: str, *args: str) -> List[str]:
    out = subprocess.run(["git", "tag", *args], cwd=repo_dir, check=True,
                         capture_output=True, text=True).stdout
    return [t for t in out.split() if SEMVER_TAG_RE.match(t)]


def _key(tag: str) -> Tuple[int, ...]:
    return tuple(int(x) for x in SEMVER_TAG_RE.match(tag).groups())


def current_versions(repo_dir: str) -> Tuple[Optional[str], Optional[str]]:
    """(HEAD에 도달하는 가장 높은 vX.Y.Z, HEAD에 직접 붙은 vX.Y.Z) — 'v'는 뗀다."""
    merged = sorted(_git_tags(repo_dir, "--merged", "HEAD"), key=_key)
    at_head = sorted(_git_tags(repo_dir, "--points-at", "HEAD"), key=_key)
    strip = lambda t: t[1:] if t else None  # noqa: E731
    return strip(merged[-1] if merged else None), strip(at_head[-1] if at_head else None)


def bump_of(entries: List[Entry]) -> str:
    if any(e.breaking for e in entries):
        return "major"
    return "minor" if any(e.type == "feat" for e in entries) else "patch"


def next_version(previous: Optional[str], entries: List[Entry]) -> str:
    if previous is None:
        return "1.0.0"
    major, minor, patch = (int(x) for x in previous.split("."))
    bump = bump_of(entries)
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def description(version: str, entries: List[Entry]) -> str:
    text = " · ".join([version] + [f"{e.header} ({', '.join(e.refs)})" for e in entries])
    return text if len(text) <= DESCRIPTION_MAX else text[:DESCRIPTION_MAX - 1] + "…"


def release_notes(version: str, entries: List[Entry], jira_url: str = JIRA_URL, pr: Optional[int] = None) -> str:
    def link(e: Entry) -> str:
        keys = ", ".join(f"[{k}]({jira_url.rstrip('/')}/browse/{k})" for k in e.refs)
        scope = f"**{e.scope}:** " if e.scope else ""
        return f"- {scope}{e.summary} ({keys})"

    groups = {"breaking": [], "feat": [], "fix": [], "other": []}
    for e in entries:
        if e.breaking:
            groups["breaking"].append(f"- {e.breaking_note or e.summary} ({', '.join(e.refs)})")
        groups[e.type if e.type in ("feat", "fix") else "other"].append(
            link(e) if e.type in ("feat", "fix") else f"- `{e.type}` " + link(e)[2:])
    out = [f"## {version}"]
    for key, title in SECTIONS:
        if groups[key]:
            out += ["", f"### {title}", *groups[key]]
    if pr:
        out += ["", f"PR: #{pr}"]
    return "\n".join(out) + "\n"


def plan(repo_dir: str, entries: List[Entry], jira_url: str = JIRA_URL, pr: Optional[int] = None) -> dict:
    latest, at_head = current_versions(repo_dir)
    if at_head:  # 같은 커밋 재실행 — 이미 만든 버전을 그대로 쓴다
        older = [t for t in _git_tags(repo_dir, "--merged", "HEAD") if t != f"v{at_head}"]
        version, previous = at_head, (max(older, key=_key)[1:] if older else None)
    else:
        version, previous = next_version(latest, entries), latest
    return {
        "version": version,
        "tag": f"v{version}",
        "previous": previous,
        "tag_exists": bool(at_head),
        "bump": "initial" if previous is None else bump_of(entries),
        "description": description(version, entries),
        "notes": release_notes(version, entries, jira_url, pr),
        "entries": [asdict(e) for e in entries],
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--body-file", required=True)
    p.add_argument("--repo-dir", default=".")
    p.add_argument("--pr", type=int)
    p.add_argument("--jira-url", default=JIRA_URL)
    args = ap.parse_args(argv)

    with open(args.body_file, encoding="utf-8") as f:
        body = f.read()
    try:
        entries = parse_notes(body)
    except NotesError as e:
        for problem in e.problems:
            print(f"::error::릴리스 노트: {problem}")
        return 1
    json.dump(plan(args.repo_dir, entries, args.jira_url, args.pr), sys.stdout, ensure_ascii=False)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
