# tools

매니페스트 생성 · 검증 스크립트. 배포 대상 아님. 담당: 노찬경

- `validate.sh`: `kustomization.yaml`이 있는 모든 디렉토리를 `kustomize build` → `kubeconform` 스키마 검사. CI(`.github/workflows/validate.yml`)가 PR · develop · main push마다 실행
  - Helm 차트로 배포하는 Traefik · cert-manager의 `values.yaml`은 검사하지 않음

- `configure.py`: 앱 이미지와 Argo CD 참조를 로컬에서 설정합니다.
- `configure-eks.py`: 선택한 EKS overlay의 큐와 매니저 큐의 합계 할당량을 갱신합니다. 입력 예시는 각 overlay의 `settings.example.yaml`입니다.
- `validate-platform.py`: Application 경로·대상, 리소스 중복 소유권, 복구 RBAC, 큐 할당량을 점검합니다.

```bash
python3 -m pip install -r tools/requirements-dev.txt
python3 tools/validate-platform.py
python3 -m unittest discover -s tests
```
