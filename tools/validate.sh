#!/usr/bin/env bash
# kustomization.yaml이 있는 모든 디렉토리를 빌드하고 kubeconform으로 스키마 검사한다.
# 필요: kustomize, kubeconform (CI는 .github/workflows/validate.yml에서 설치)
set -euo pipefail
cd "$(dirname "$0")/.."

CRD_SCHEMAS='https://raw.githubusercontent.com/datreeio/CRDs-catalog/main/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json'
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
