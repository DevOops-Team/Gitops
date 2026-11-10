# tools

매니페스트 생성 · 검증 스크립트. 배포 대상 아님. 담당: 노찬경

- `validate.sh`: `kustomization.yaml`이 있는 모든 디렉토리를 `kustomize build` → `kubeconform` 스키마 검사. CI(`.github/workflows/validate.yml`)가 PR · develop · main push마다 실행
  - Helm 차트로 배포하는 Traefik · cert-manager의 `values.yaml`은 검사하지 않음
