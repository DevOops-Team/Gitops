#!/usr/bin/env bash
# kustomization.yaml이 있는 모든 디렉토리를 빌드하고 kubeconform으로 스키마 검사한다.
# 필요: kustomize, kubeconform (CI는 .github/workflows/validate.yml에서 설치)
set -euo pipefail
cd "$(dirname "$0")/.."

# CRD 스키마는 datreeio/CRDs-catalog 커밋 SHA로 고정한다 — main이 바뀌어도 검사 결과가 흔들리지 않게 (GPU-294, 2026-11-22 커밋)
CRDS_CATALOG_REF='04af58d740718c4dc719441bf39fb284c784f4a8'
CRD_SCHEMAS="https://raw.githubusercontent.com/datreeio/CRDs-catalog/${CRDS_CATALOG_REF}/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json"
status=0

while IFS= read -r dir; do
  echo "::group::${dir}"
  if ! kustomize build "${dir}" \
    | kubeconform -strict -summary -ignore-missing-schemas \
        -schema-location default -schema-location "${CRD_SCHEMAS}"; then
    echo "::error::${dir} 검증 실패"
    status=1
  fi
  echo "::endgroup::"
done < <(find . -path ./.git -prune -o -name kustomization.yaml -print | xargs -n1 dirname | sort)

exit "${status}"
