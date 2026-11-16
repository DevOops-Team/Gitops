"""release.py 테스트 (GPU-136). 실행: python3 -m unittest discover -s tools/release -v"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import release  # noqa: E402

BODY = """\
develop → main 릴리스입니다.

## 릴리스 노트

<!-- 형식: <type>: 요약 + Refs: GPU-n -->
feat: 이미지에 semver 태그 추가
Refs: GPU-136

fix: 실험 ID를 제출에 전달
Refs: GPU-150, GPU-151

## 검증

- feat: 이건 릴리스 노트 밖이라 무시
"""


class ParseTest(unittest.TestCase):
    def test_parses_entries_in_section_only(self):
        entries = release.parse_notes(BODY)
        self.assertEqual(
            [(e.type, e.summary, e.refs) for e in entries],
            [("feat", "이미지에 semver 태그 추가", ["GPU-136"]),
             ("fix", "실험 ID를 제출에 전달", ["GPU-150", "GPU-151"])],
        )

    def test_crlf_body(self):
        self.assertEqual(len(release.parse_notes(BODY.replace("\n", "\r\n"))), 2)

    def test_breaking_by_bang_and_footer(self):
        body = ("## 릴리스 노트\nfeat!: API 응답 형식 변경\nRefs: GPU-140\n\n"
                "fix: 저장 경로 변경\nRefs: GPU-141\nBREAKING CHANGE: ckpt 경로가 바뀜\n")
        a, b = release.parse_notes(body)
        self.assertTrue(a.breaking)
        self.assertTrue(b.breaking)
        self.assertEqual(b.breaking_note, "ckpt 경로가 바뀜")

    def test_optional_scope(self):
        (e,) = release.parse_notes("## 릴리스 노트\nfix(dispatcher): 큐 이름 수정\nRefs: GPU-131\n")
        self.assertEqual(e.scope, "dispatcher")

    def test_missing_section(self):
        with self.assertRaisesRegex(release.NotesError, "릴리스 노트"):
            release.parse_notes("feat: 섹션 없음\nRefs: GPU-1\n")

    def test_empty_section(self):
        with self.assertRaisesRegex(release.NotesError, "항목이 없"):
            release.parse_notes("## 릴리스 노트\n<!-- 비어 있음 -->\n\n## 다음\n")

    def test_missing_refs(self):
        with self.assertRaisesRegex(release.NotesError, "Refs"):
            release.parse_notes("## 릴리스 노트\nfeat: 키 없음\n")

    def test_bad_jira_key(self):
        with self.assertRaisesRegex(release.NotesError, "Jira"):
            release.parse_notes("## 릴리스 노트\nfeat: 소문자 키\nRefs: gpu-136\n")

    def test_unknown_type(self):
        with self.assertRaisesRegex(release.NotesError, "형식"):
            release.parse_notes("## 릴리스 노트\nfeature: 오타\nRefs: GPU-1\n")

    def test_unknown_line_inside_entry(self):
        with self.assertRaisesRegex(release.NotesError, "알 수 없는 줄"):
            release.parse_notes("## 릴리스 노트\nfeat: 요약\n설명 줄\nRefs: GPU-1\n")

    def test_errors_list_all_problems(self):
        with self.assertRaises(release.NotesError) as cm:
            release.parse_notes("## 릴리스 노트\nfeat: a\n\nfix: b\n")
        self.assertEqual(len(cm.exception.problems), 2)


class BumpTest(unittest.TestCase):
    def entries(self, text):
        return release.parse_notes("## 릴리스 노트\n" + text)

    def test_bumps(self):
        fix = self.entries("fix: a\nRefs: GPU-1\n")
        feat = self.entries("fix: a\nRefs: GPU-1\n\nfeat: b\nRefs: GPU-2\n")
        major = self.entries("feat!: c\nRefs: GPU-3\n")
        chore = self.entries("chore: d\nRefs: GPU-4\n")
        self.assertEqual(release.next_version("1.4.2", fix), "1.4.3")
        self.assertEqual(release.next_version("1.4.2", feat), "1.5.0")
        self.assertEqual(release.next_version("1.4.2", major), "2.0.0")
        self.assertEqual(release.next_version("1.4.2", chore), "1.4.3")

    def test_first_release(self):
        self.assertEqual(release.next_version(None, self.entries("feat!: a\nRefs: GPU-1\n")), "1.0.0")


class RenderTest(unittest.TestCase):
    def test_description_has_version_and_keys(self):
        d = release.description("1.2.0", release.parse_notes(BODY))
        self.assertEqual(d, "1.2.0 · feat: 이미지에 semver 태그 추가 (GPU-136) · "
                            "fix: 실험 ID를 제출에 전달 (GPU-150, GPU-151)")

    def test_description_truncated_to_512(self):
        body = "## 릴리스 노트\n" + "".join(f"feat: {'가' * 80}\nRefs: GPU-{i}\n\n" for i in range(20))
        d = release.description("1.0.0", release.parse_notes(body))
        self.assertLessEqual(len(d), 512)
        self.assertTrue(d.endswith("…"))

    def test_release_notes_link_jira(self):
        md = release.release_notes("1.2.0", release.parse_notes(BODY), "https://x.atlassian.net", pr=13)
        self.assertIn("### 기능", md)
        self.assertIn("- 이미지에 semver 태그 추가 ([GPU-136](https://x.atlassian.net/browse/GPU-136))", md)
        self.assertIn("### 버그 수정", md)
        self.assertIn("#13", md)


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})


class TagsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        git(self.dir, "init", "-q", "-b", "main")
        git(self.dir, "commit", "-q", "--allow-empty", "-m", "a")

    def tearDown(self):
        self.tmp.cleanup()

    def test_no_tags(self):
        self.assertEqual(release.current_versions(self.dir), (None, None))

    def test_latest_semver_and_head_tag(self):
        for t in ("v1.9.0", "v1.10.0", "backend-old", "v2.0.0-rc.1"):
            git(self.dir, "tag", t)
        self.assertEqual(release.current_versions(self.dir), ("1.10.0", "1.10.0"))
        git(self.dir, "commit", "-q", "--allow-empty", "-m", "b")
        self.assertEqual(release.current_versions(self.dir), ("1.10.0", None))

    def test_plan_is_idempotent_on_rerun(self):
        git(self.dir, "tag", "v1.0.0")
        git(self.dir, "commit", "-q", "--allow-empty", "-m", "b")
        entries = release.parse_notes(BODY)
        self.assertEqual(release.plan(self.dir, entries)["version"], "1.1.0")
        git(self.dir, "tag", "v1.1.0")  # 태그 만든 뒤 같은 커밋에서 재실행
        p = release.plan(self.dir, entries)
        self.assertEqual((p["version"], p["previous"], p["tag_exists"]), ("1.1.0", "1.0.0", True))


class CliTest(unittest.TestCase):
    def test_plan_cli_json(self):
        with tempfile.TemporaryDirectory() as d:
            git(d, "init", "-q", "-b", "main")
            git(d, "commit", "-q", "--allow-empty", "-m", "a")
            body = os.path.join(d, "body.md")
            with open(body, "w", encoding="utf-8") as f:
                f.write(BODY)
            out = subprocess.run([sys.executable, release.__file__, "plan", "--body-file", body,
                                  "--repo-dir", d, "--pr", "7"],
                                 check=True, capture_output=True, text=True).stdout
            p = json.loads(out)
            self.assertEqual((p["version"], p["tag"], p["previous"]), ("1.0.0", "v1.0.0", None))
            self.assertIn("GPU-136", p["description"])
            self.assertIn("#7", p["notes"])

    def test_plan_cli_reports_errors(self):
        with tempfile.TemporaryDirectory() as d:
            body = os.path.join(d, "body.md")
            with open(body, "w", encoding="utf-8") as f:
                f.write("## 릴리스 노트\nfeat: 키 없음\n")
            r = subprocess.run([sys.executable, release.__file__, "plan", "--body-file", body,
                                "--repo-dir", d], capture_output=True, text=True)
            self.assertEqual(r.returncode, 1)
            self.assertIn("::error::", r.stdout)


if __name__ == "__main__":
    unittest.main()
