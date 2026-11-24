# 모니터링 클러스터 Secret → Vault KV/VSO 인계 (GPU-241)

## 범위와 현재 상태

사용자 제공 `kubectl get secrets -A` 목록을 기준으로 기존 Secret 네 개를 인계한다.
목록의 존재/타입/키 수는 확인했지만 실제 값·소유권·Vault 경로·클러스터 상태는 조회하지 않았다.
**이 PR은 매니페스트 준비다. Vault 값 등록·인증 경로 생성·Argo Sync·실제 서비스 시험은 미수행이다.**

| 기존 monitoring Secret | 유지할 모든 key | KV v2 경로(mount `devoops`) | SA / VaultAuth / VSS | Vault role / read policy |
|---|---|---|---|---|
| alertmanager-secrets (Opaque) | slack_webhook_url, healthchecks_ping_url | onprem/monitoring/alertmanager-secrets | alertmanager-sync | monitoring-alertmanager-sync / monitoring-alertmanager-read |
| grafana-secrets (Opaque) | admin-user, admin-password, pg-ro-password | onprem/monitoring/grafana-secrets | grafana-sync | monitoring-grafana-sync / monitoring-grafana-read |
| postgres-exporter-secrets (Opaque) | password | onprem/monitoring/postgres-exporter-secrets | postgres-exporter-sync | monitoring-postgres-exporter-sync / monitoring-postgres-exporter-read |
| ghcr-pull (kubernetes.io/dockerconfigjson) | .dockerconfigjson | onprem/monitoring/ghcr-pull | ghcr-pull-sync | monitoring-ghcr-pull-sync / monitoring-ghcr-pull-read |

key 이름은 Monitoring main `scripts/create-secrets.sh`와 현재 GHCR 계약을 기준으로 했다.
실제 키가 다르면 먼저 조정하고 인계한다. Secret 하나의 key 일부만 Vault에 복사하지 않는다.
KV 값은 기존 Secret data를 base64 디코딩한 문자열 그대로다. GHCR도 `.dockerconfigjson`에
JSON **문자열 전체**를 넣으며 `auths`를 최상위로 펼치거나 다시 base64 인코딩하지 않는다.

제외: `loki-s3-cert`, `mimir-s3-cert`, `tempo-s3-cert`(Roles Anywhere 인증서/개인키와 회전 절차),
`kube-system/argocd-manager-token`(원격 접속 토큰), `sh.helm.release.*`(Helm 이력).
Vault 서버/DB 계정 발급/비밀번호 교체/기존 모니터링 워크로드 변경은 추가하지 않는다.

## 배치 구조

관리 클러스터 Argo CD → 등록된 원격 destination **name: monitoring**으로 배포한다.
관리 클러스터의 VSO는 원격 Secret을 직접 관리하지 않는다. 별도 monitoring 클러스터에
공식 VSO chart 1.6.0, release `vault-secrets-operator`, namespace
`vault-secrets-operator-system`을 설치한다. 목록에 Helm release가 없더라도 실제 설치 여부부터 재확인한다.

- `bootstrap/onprem/project-monitoring-vault.yaml`: Gitops/공식 HashiCorp Helm repo와 원격 두 namespace만 허용.
  기존 gpu-monitoring 저장 층 프로젝트의 허용 범위는 넓히지 않는다.
- `operator/values.yaml`: 외부 Vault VM `.81` 연결, 기본 VaultConnection 자동 생성 비활성화.
- `connections/`: monitoring namespace VaultConnection·서비스별 SA/VaultAuth와 TokenReview create RBAC.
- 대상별 디렉토리: 기존 목적지 Secret에 쓰는 VSS. `create:false`, `excludeRaw:true`, `refreshAfter:60s`.
  기존 Secret이 없으면 새로 만들지 않고 오류로 멈춘다. destination.type은 생략해 기존 타입 유지.
- Argo 앱 6개는 모두 수동 sync, automated/prune/finalizer/rolloutRestartTargets 없음.
  root가 Application을 만들더라도 자식이 최초 sync를 자동 수행하지 않는다.

## 선행 준비 — 관리/모니터링 클러스터 혼동 금지

1. 모니터링 담당자와 기존 Secret 생성·회전 주체를 확인한다. ownerReferences/immutable/현재 키와
   type을 확인하고 다른 Operator 관리 중이거나 immutable이면 먼저 중단·조정한다.
   UID/type/data를 안전한 파일로 백업한다(umask 077, stdout/Git/Slack 출력 금지).
2. 네 개의 기존 값을 바꾸지 않고 위 KV 경로에 복사한다. `vault kv put -cas=0`으로
   최초 등록하고 이미 있으면 덮어쓰지 말고 원본과 비교한다. 관리자 터미널/Vault CLI로 실행하며
   root/Vault 토큰이나 KV 입력 파일을 Pod/Git에 넣지 않는다.
   예: `vault kv put -cas=0 devoops/onprem/monitoring/alertmanager-secrets @<보호된-JSON-파일>`.
   JSON은 `{"slack_webhook_url":"기존값", "healthchecks_ping_url":"기존값"}` 형태다(예시값으로 실제 등록 금지).
3. 관리 클러스터 `auth/onprem`을 재설정하지 않는다. **별도 `auth/monitoring`** Kubernetes auth mount를 준비한다.
   실제 monitoring API URL과 그 API의 CA를 사용한다. `.120` 등 관리 API를 복사하지 않는다.
   localhost/사설 접근 불가 주소가 kubeconfig에 있으면 Vault VM에서 도달 가능한 API 주소를 별도 확인한다.

Vault 관리자 터미널에서(기존 mount가 있으면 type/config부터 확인):

```bash
vault auth list
# monitoring mount가 없을 때만 실행
vault auth enable -path=monitoring kubernetes

# 운영자가 확인한 monitoring API HTTPS 주소와 공개 CA 파일이다.
# client JWT reviewer: 고정/장기 TokenReview 토큰을 저장하지 않는다.
vault write auth/monitoring/config \
  kubernetes_host="$MONITORING_API_URL" \
  kubernetes_ca_cert=@monitoring-api-ca.crt \
  disable_local_ca_jwt=true
```

Vault VM → monitoring API TokenReview 연결과 monitoring VSO → Vault `.81:8200` 연결이 모두 필요하다.
인증 SA가 TokenReview create 권한으로 자기 로그인 JWT를 검증하는 기존 client-JWT 방식을 사용한다.
서비스별 read 정책·role은 다음처럼 작성한다(나머지도 표의 이름/경로로 각각 등록):

```bash
vault policy write monitoring-alertmanager-read - <<'POLICY'
path "devoops/data/onprem/monitoring/alertmanager-secrets" {
  capabilities = ["read"]
}
POLICY
vault write auth/monitoring/role/monitoring-alertmanager-sync \
  bound_service_account_names=alertmanager-sync \
  bound_service_account_namespaces=monitoring \
  token_policies=monitoring-alertmanager-read token_ttl=10m token_max_ttl=1h
```

각 서비스의 정책 원본은 `policies/*.hcl`에 있다. 각 role은 표에 적힌 자기 SA와 정책 하나에만 연결한다.
이 매니페스트는 Vault 서버의 auth mount/정책/role/KV를 자동 생성하지 않는다.

4. **모니터링 context**에서 공개 Vault 서버 CA를 준비한다(API CA와 다른 파일).
   실제 Vault TLS 인증서를 검증하는 공개 CA만 사용하며 Secret 비밀번호/서버 개인키를 넣지 않는다.

```bash
kubectl --context "$MONITORING_CONTEXT" -n monitoring create secret generic vault-vm-ca \
  --from-file=ca.crt=vault-ca.crt --dry-run=client -o yaml | \
  kubectl --context "$MONITORING_CONTEXT" apply -f -
```

## 수동 적용 순서

1. 관리 클러스터의 bootstrap/onprem AppProject 반영 후 root가 새 앱을 인식하는지 확인한다.
2. `gpu-monitoring-vault-operator` diff 확인 → 수동 Sync.
   namespace만 CreateNamespace=true이며 공식 CRD는 ServerSideApply로 설치한다. 기존 Helm 설치가 있으면
   릴리스/version/values 소유권을 비교하고 삭제 후 재설치하지 않는다.
3. VSO·CRD 정상 및 공개 CA·Vault auth 준비 후 `gpu-monitoring-vault-connections` 수동 Sync.
   VaultConnection/VaultAuth 정상 여부 확인. 모니터링 앱의 SA 자체에는 Vault read 권한을 추가하지 않는다.
4. **KV와 기존 Secret의 전체 키·바이트 일치**를 먼저 비교한 다음
   `gpu-monitoring-vault-alertmanager`, `gpu-monitoring-vault-grafana`,
   `gpu-monitoring-vault-postgres-exporter`, `gpu-monitoring-vault-ghcr-pull`을 하나씩 수동 Sync한다.
   Prune/Force/Replace 및 전체 모니터링 재배포를 사용하지 않는다.
5. 각 VSS의 SecretSynced 이벤트·성공 상태와 UID/type/key/data 유지 여부 확인.
   resourceVersion/HMAC 등 메타데이터 변화는 가능하다. 첫 동기화 성공은 실제 앱 반영 시험과 별개다.
6. Alertmanager 테스트 알림·Watchdog 수신, Grafana 로그인/DB 조회, exporter 수집, private 이미지 pull을
   담당자와 비파괴 시험으로 확인한다. Running Pod의 캐시된 이미지만으로 GHCR 인증 성공을 판단하지 않는다.

```bash
kubectl --context "$MONITORING_CONTEXT" -n monitoring get vaultconnection,vaultauth,vaultstaticsecret
kubectl --context "$MONITORING_CONTEXT" -n monitoring get events --field-selector reason=SecretSynced
```

## 기존 생성 스크립트와 회전·복구

- Monitoring `scripts/create-secrets.sh`는 현재 기존 Secret을 덮어쓰는 도구다.
  이 Gitops PR이 그 스크립트를 바꾸지는 않는다. 인계한 세 Secret에 대해 재실행하지 않도록
  담당자와 보호/사용 중단을 먼저 합의한다. GHCR을 만드는 기존 도구도 동일하게 인계한다.
- KV 동기화는 실제 DB 비밀번호나 Grafana 내부 DB의 관리자 암호를 변경하는 기능이 아니다.
  Secret 갱신과 앱 적용은 별개이며 env/시작 시 파일 읽기는 재시작/재로드가 필요할 수 있다.
  이번에는 **현재 값을 그대로** 옮긴다. 추후 교체 시 DB 계정·Grafana·Alertmanager reload 절차를 함께 관리한다.
- Vault/VSO 장애 시 기존 Secret은 남는다. 초기 부트스트랩과 Argo 원격 접속 자격 증명은
  Vault만 살아야 복구할 수 있는 순환 의존으로 만들지 않는다.
- 문제 시 대상별 VSS 동기화를 중단하고 보호된 백업과 비교해 복원한다. VSS 삭제만으로
  값이 이전 버전으로 복원되는 것은 아니며 기존 Secret/Helm 이력을 삭제하지 않는다.
- `loki/mimir/tempo-s3-cert`는 이번에 인계하지 않는다. 인증서 발급·만료·교체 담당과 별도 설계한다.

## 로컬 검증

`python tools/vault/validate.py`: 공식 chart 1.6.0 CRD schema·원격 destination·인증 mount 분리·
동기화 대상·TokenReview 범위·수동 인계 조건을 검사한다. 실제 Vault 로그인·원격 클러스터는 호출하지 않는다.
