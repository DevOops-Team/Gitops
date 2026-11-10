# Gitops

Argo CD가 보는 매니페스트 저장소입니다. 클러스터(온프레미스 · EKS A/B/C)에 들어갈 상태를 이곳에서 관리합니다.
컨트롤러 코드(복구 컨트롤러 · 디스패처 · 재배치기 · 잡 투입기)와 이미지 빌드는 `K8s` 레포에 있습니다.

```text
bootstrap/    Argo CD root · project · 클러스터별 Application 목록
onprem/       매니저 클러스터: platform · controllers · multikueue
eks/          워커 클러스터: scheduling (base + overlays/eks-{a,b,c})
monitoring/   onprem 저장 층 · eks 수집 층
tools/        매니페스트 생성 · 검증 스크립트 (배포 대상 아님)
```

## 규칙 (ADR-21)

- 클러스터 차이는 `overlays/<cluster>`에만 둡니다. `base`에는 클러스터 이름을 넣지 않습니다.
- Argo CD Application 하나는 디렉토리 경로 하나를 가리킵니다.
- Argo CD가 배포하는 것만 둡니다. kind · kwok · examples 같은 개발용 매니페스트는 `K8s` 레포에 둡니다.
- 시크릿은 커밋하지 않습니다.

## 브랜치 (ADR-20)

`develop`에서 기능마다 feature 브랜치 → `develop` PR → `main` PR. `main` PR 리뷰어는 관련 있는 사람 또는 부담당.
