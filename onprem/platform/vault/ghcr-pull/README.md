# 기존 GHCR 이미지 pull Secret 인계 (GPU-241)

현재는 코드 준비 상태다. 실제 Vault 값 등록·Argo Sync·운영 검증은 실행하지 않았다.

| namespace | 기존 Secret / key | Vault KV v2 경로 (mount devoops) | Vault policy / role |
|---|---|---|---|
| platform | ghcr-pull / .dockerconfigjson | onprem/platform/ghcr-pull | platform-ghcr-pull-read / platform-ghcr-pull-sync |
| data-system | ghcr-pull / .dockerconfigjson | onprem/data-system/ghcr-pull | data-system-ghcr-pull-read / data-system-ghcr-pull-sync |

namespace별 SA·VaultAuth 이름은 `ghcr-pull-sync`다. 기존 common이 관리하는 각 namespace의
`vault-vm` VaultConnection과 `vault-vm-ca`를 재사용한다. Vault role 이름은 auth/onprem 내에서
겹치지 않도록 namespace 접두어를 쓴다. 정책은 표의 자기 경로 read만 허용한다.

## 기존 형식과 값을 유지하는 조건

- 기존 Secret type은 `kubernetes.io/dockerconfigjson`, key는 `.dockerconfigjson`이다.
- KV에는 `.dockerconfigjson`이라는 key에 기존 Secret을 base64 디코딩한 **JSON 문자열 전체**를 넣는다.
  `auths` 객체를 KV 최상위로 펼치거나 문자열을 다시 base64 인코딩하지 않는다.
- namespace별 값이 같다고 가정하지 않는다. 두 Secret의 실제 원본을 각각 복사한다.
- VSS는 `create:false`, `excludeRaw:true`, `60s`다. 기존 Secret이 없으면 생성하지 않고 오류로 멈춘다.
- VSO 1.6.0 CRD의 destination.type은 create:true용이다. 여기서는 생략하고 기존 타입을 유지한다.
- 토큰 재발급·Deployment imagePullSecrets 변경·자동 rollout·자동 prune은 하지 않는다.

## 등록·배포 순서

1. 관리 context에서 기존 Secret UID/type/data·ownerReferences/immutable과 관리 주체를 확인한다.
   기존 생성/회전 자동화와 동시 쓰기가 없도록 인계한다. 비밀값을 화면·로그·Git에 출력하지 않는다.
2. 각 Secret의 모든 data key가 `.dockerconfigjson` 하나인지 검사한다. 디코딩 결과가 JSON 객체이며
   auths가 유효한 객체인지 검사한다. root 권한 또는 umask 077로 보호된 임시 파일에 원본과
   `{".dockerconfigjson":"<기존 JSON 문자열>"}` 형태의 KV 입력 파일을 보관·전송한다.
3. 표의 KV 경로에 `vault kv put -cas=0 devoops/onprem/<namespace>/ghcr-pull @<입력파일>`로
   최초 등록한다. 이미 있으면 덮어쓰지 않고 기존 값과 먼저 비교한다. 등록 후 Vault 값을
   파일로 읽어 원본 JSON 문자열과 바이트가 같은지 검사한다.
4. Vault 정책·role을 namespace별로 준비한다. 기존 auth/onprem과 TokenReview 인증 경로를 재사용한다.
   예를 들어 platform용은 아래와 같고, data-system은 platform을 data-system으로 바꾼다.

```bash
vault policy write platform-ghcr-pull-read - <<'POLICY'
path "devoops/data/onprem/platform/ghcr-pull" {
  capabilities = ["read"]
}
POLICY
vault write auth/onprem/role/platform-ghcr-pull-sync \
  bound_service_account_names=ghcr-pull-sync \
  bound_service_account_namespaces=platform \
  token_policies=platform-ghcr-pull-read token_ttl=10m token_max_ttl=1h
```

5. PR 리뷰·main 반영 후 `gpu-vault-connections`의 기존 연결 Ready를 확인한다. 새로운 수동 앱
   `gpu-vault-ghcr-pull`의 Diff를 확인한다. Vault 값·role·기존 목적지 Secret이 모두 준비되기 전에는 Sync하지 않는다.
6. Sync 직전과 SecretSynced 후 기존 Secret UID/type/key/data가 원본 백업과 모두 같은지 비교한다.
   namespace별 VSS `ghcr-pull-sync`의 Ready·SecretSynced를 확인한다.
7. 실제 소비자의 이미지 pull을 검증한다. 기존 Running Pod는 캐시된 이미지로 실행 중일 수 있어
   새 토큰 인증 성공을 증명하지 않는다. 담당자가 승인한 비파괴 시험에서 private GHCR 이미지와
   imagePullPolicy:Always를 사용하고 해당 ServiceAccount/imagePullSecrets 연결을 확인한다.
   실제 ImagePullBackOff/ErrImagePull 여부와 GHCR 토큰 권한·만료를 함께 확인한다.

## 초기 기동과 장애 복구

- 이미 존재하는 ghcr-pull은 VSO 장애 시에도 남는다. 기존 유효 토큰으로 이미지 다운로드를 계속할 수 있다.
- 새 클러스터 초기 복구 시 VSO 자체 이미지·Argo Git 접근에 필요한 인증을 Vault에만 두지 않는다.
  별도의 초기 인증/복구 경로를 유지한다. 공개 VSO 이미지를 쓰는 경우에도 실제 pull 조건을 확인한다.
- IaC의 VSO 관리 대상 보호 목록에 `platform/ghcr-pull`, `data-system/ghcr-pull`을 인계한다.
  이번 Gitops 커밋이 IaC 실행 설정을 자동 변경하지는 않는다.
- 실패 시 VSS 동기화를 중단하고 원본 백업과 비교한다. VSS 삭제는 값 복원이 아니며 기존 Secret은 삭제하지 않는다.
- 등록·검증 후 비밀값 임시 복사본은 팀의 보관/삭제 절차로 정리한다.
