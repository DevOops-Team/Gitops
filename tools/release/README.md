# 이미지 버전 (GPU-136)

이미지는 digest로 배포하고, 거기에 **레포 단위 버전 `X.Y.Z`** 와 **description** 을 붙인다.
둘 다 develop → main PR 본문의 `## 릴리스 노트` 섹션에서 나온다. develop 쪽 개별 커밋 메시지는 버전에 쓰지 않는다.

```text
## 릴리스 노트

feat: 이미지에 semver 태그 추가
Refs: GPU-136

fix!: 체크포인트 경로 변경
Refs: GPU-150, GPU-151
BREAKING CHANGE: 기존 ckpt 경로를 읽지 못함
```

| 규칙 | 내용 |
|---|---|
| 항목 | `<type>: 요약` + `Refs: GPU-n[, GPU-m]` (필수), 선택으로 `BREAKING CHANGE: 설명`. 항목 사이는 빈 줄 |
| type | `feat` → minor · `fix` `perf` `refactor` `revert` `docs` `style` `test` `build` `ci` `chore` → patch · `type!` 또는 `BREAKING CHANGE` → major |
| 첫 릴리스 | 태그가 없으면 `1.0.0` |
| 멀티 이미지 레포 (K8s · Data) | 버전은 레포에 하나. 이번 머지에서 바뀐 이미지에만 그 버전 태그가 붙는다 |

## 흐름

```text
develop → main PR   release-notes / release notes   형식 검사 + 다음 버전 미리보기 (본문 고치면 다시 돎, main 필수 검사)
main 머지 (push)    version / release notes          머지 커밋의 PR 본문 → 버전 계산 (GITHUB_TOKEN 읽기만)
                    image                             ghcr.io/devoops-team/<이름>:{X.Y.Z, X.Y, main, sha-xxxxxxx}
                                                      label · annotation org.opencontainers.image.description
                    release / tag · release           버전 봇 → 태그 vX.Y.Z + GitHub Release (Jira 링크)
                    gitops deploy                     배포 봇 → overlay images에 newTag: X.Y.Z + digest
```

릴리스 노트가 없거나 PR 머지가 아닌 main push는 이미지 push · 배포를 하지 않는다.
로직은 `release.py` (테스트 `python3 -m unittest discover -s tools/release -v`), 워크플로는 `.github/workflows/release-{plan,publish}.yml` · `update-image.yml`.

## 봇 두 개 (최소 권한)

| | 배포 봇 `devoops-deploy-bot` | 버전 봇 (새로 만듦) |
|---|---|---|
| App 권한 | Contents: write · Metadata: read | Contents: write · Metadata: read |
| 설치 레포 | Gitops만 | Backend · Frontend · K8s · Data만 |
| 토큰 | Gitops 한 레포, `permission-contents: write` | 호출 레포 한 곳, `permission-contents: write` |
| 비밀키 위치 | 각 코드 레포 Environment `gitops-deploy` Secret `DEPLOY_APP_PRIVATE_KEY` | 각 코드 레포 Environment `release` Secret `VERSION_APP_PRIVATE_KEY` |
| Environment 배포 브랜치 | main만 | main만 |
| ruleset 우회 | Gitops main: PR 필수 · 상태 검사만 (삭제 · force-push는 우회 없음) | 코드 레포 태그 `v*`: 생성만 (수정 · 삭제는 아무도 못 함) |
| App ID | Variable `DEPLOY_APP_ID` | Variable `VERSION_APP_ID` |

두 봇 모두 `workflows` 권한이 없어서 `.github/workflows/`를 바꿀 수 없다.
Environment가 없는 레포에서 `environment:` job이 돌면 GitHub이 보호 규칙 없이 자동으로 만들므로, **워크플로를 main에 올리기 전에 Environment를 먼저 만든다.**
