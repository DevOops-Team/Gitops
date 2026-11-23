# Cloudflare DNS API 토큰 인계 (GPU-241)

기존 `cert-manager/cloudflare-dns-api-token`의 **현재 토큰을 그대로** Vault로 이전한다.
ClusterIssuer의 Secret 이름/key(`api-token`), `frontend-tls`, ACME 계정 Secret과 cert-manager Deployment는 변경하지 않는다.
이 코드 push/머지만으로 Vault에 실제 값이 생기지는 않는다. 토큰을 문서·Git·로그에 출력하지 않는다.

## 경로와 관리 주체

| 대상 | 값 |
|---|---|
| Vault KV v2 | mount `devoops`, path `onprem/cert-manager/cloudflare-dns-api-token` |
| 정책 / 인증 role·SA | `cloudflare-dns-read` / `cloudflare-dns-sync` |
| Kubernetes auth | `auth/onprem` (기존 관리 클러스터 인증 재사용) |
| 공개 CA | `cert-manager/vault-vm-ca`, key `ca.crt` |
| 기존 목적지 | `cert-manager/cloudflare-dns-api-token`, key `api-token` |
| Argo Application | `gpu-vault-cloudflare-dns`, 수동 Sync |

## 1. 현재 값 추출 (master1의 kubectl 터미널)

같은 셸에서 순서대로 실행한다. 먼저 관리 context를 확인하고 다른 토큰 교체 작업·Secret 생성 스크립트를 동시에 실행하지 않는다.

```bash
kubectl config current-context
umask 077
CF_TRANSFER_DIR=$(mktemp -d "$HOME/cloudflare-vault.XXXXXX")
kubectl -n cert-manager get secret cloudflare-dns-api-token -o json > "$CF_TRANSFER_DIR/original.json"

python3 - "$CF_TRANSFER_DIR" <<'PY'
import base64, json, pathlib, sys
p = pathlib.Path(sys.argv[1])
s = json.loads((p / 'original.json').read_text())
if s.get('immutable') or s['metadata'].get('ownerReferences'):
    raise SystemExit('중단: 변경 불가 또는 다른 관리 주체가 있습니다.')
if s.get('type', 'Opaque') != 'Opaque' or 'api-token' not in s.get('data', {}):
    raise SystemExit('중단: Secret 종류 또는 api-token key를 확인하세요.')
v = {k: base64.b64decode(x, validate=True).decode('utf-8') for k, x in s['data'].items()}
(p / 'values.json').write_text(json.dumps(v, ensure_ascii=False))
print('현재 값을 변환했습니다. 비밀값은 출력하지 않았습니다.')
PY
```

Python 검사가 성공했을 때만 전송한다. 임시 파일은 비밀정보이므로 Git 밖에서 권한을 제한해 보관한다.

```bash
ssh vault1@172.30.0.81 'umask 077; mkdir -p "$HOME/vault-import/cloudflare"; chmod 700 "$HOME/vault-import/cloudflare"'
scp "$CF_TRANSFER_DIR/values.json" vault1@172.30.0.81:vault-import/cloudflare/values.json
```

## 2. Vault 등록과 인증 (vault1 VM)

Vault가 unseal되고 CLI에 로그인된 상태에서 실행한다. 첫 경로 생성에만 CAS=0을 사용한다.
이미 존재한다면 조건을 제거해 덮어쓰지 말고 현재 원본과 먼저 비교한다.

```bash
(
set -eu
umask 077
export VAULT_ADDR=https://172.30.0.81:8200
export VAULT_CACERT="$HOME/vault-ca.crt"
vault kv put -cas=0 devoops/onprem/cert-manager/cloudflare-dns-api-token @"$HOME/vault-import/cloudflare/values.json"
vault kv get -format=json devoops/onprem/cert-manager/cloudflare-dns-api-token > "$HOME/vault-import/cloudflare/stored.json"
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home() / 'vault-import/cloudflare'
a = json.loads((p / 'values.json').read_text())
b = json.loads((p / 'stored.json').read_text())['data']['data']
if a != b:
    raise SystemExit('불일치: 동기화를 진행하지 마세요.')
print('원본과 Vault 값이 일치합니다.')
PY
)
```

위 검사가 성공한 뒤 정책과 role을 만든다.

```bash
vault policy write cloudflare-dns-read - <<'EOF'
path "devoops/data/onprem/cert-manager/cloudflare-dns-api-token" {
  capabilities = ["read"]
}
EOF

vault write auth/onprem/role/cloudflare-dns-sync \
  bound_service_account_names=cloudflare-dns-sync \
  bound_service_account_namespaces=cert-manager \
  token_policies=cloudflare-dns-read token_ttl=10m token_max_ttl=1h
```

## 3. 공개 CA 준비 (master1)

```bash
scp vault1@172.30.0.81:vault-ca.crt "$CF_TRANSFER_DIR/vault-ca.crt"
kubectl -n cert-manager create secret generic vault-vm-ca \
  --from-file=ca.crt="$CF_TRANSFER_DIR/vault-ca.crt" \
  --dry-run=client -o yaml | kubectl apply -f -
```

CA는 공개 인증서이며 Vault 개인키를 복사하지 않는다. 인증 SA/RBAC/VaultConnection은
`common/cloudflare-auth.yaml`이 관리한다. 다른 namespace의 VaultConnection을 그대로 참조하지 않는다.

## 4. main 반영과 수동 Sync

1. Vault 원본 일치와 CA 준비를 완료한다. develop push는 Argo 배포가 아니다. main은 별도 리뷰 PR로 반영한다.
2. 아래 비교를 **Sync 직전** 수행해 이전 중 원본 변경이 없었는지 확인한다.
3. `gpu-vault-connections`를 Diff 확인 후 수동 Sync한다. 기존 Backend/Collector 연결도 유지한다.
4. 새 `gpu-vault-cloudflare-dns`를 수동 Sync한다. `create: false`, `excludeRaw: true`, `60s`이며 자동 재시작/자동 prune이 없다.
5. `SecretSynced` 성공 사건을 확인한 뒤 아래 비교를 다시 수행한다.

```bash
kubectl -n cert-manager get secret cloudflare-dns-api-token -o json > "$CF_TRANSFER_DIR/current.json"
python3 - "$CF_TRANSFER_DIR" <<'PY'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1])
a = json.loads((p / 'original.json').read_text())
b = json.loads((p / 'current.json').read_text())
if (a['metadata']['uid'] != b['metadata']['uid'] or a.get('type') != b.get('type') or a.get('data') != b.get('data')):
    raise SystemExit('불일치: 진행을 멈추고 원본과 Vault 값을 확인하세요.')
print('기존 Secret 객체·종류·모든 key와 값이 유지됩니다.')
PY

kubectl -n cert-manager describe vaultstaticsecret cloudflare-dns-sync
kubectl get clusterissuer letsencrypt-cloudflare-production
kubectl get certificates -A
```

기존 Certificate Ready는 다음 갱신의 DNS-01 검증을 대신하지 않는다. 토큰 조회/인증서 발급·갱신 시험은 담당자와 따로 수행한다.
문제가 있으면 새 Application의 자동 동기화가 없는지 확인하고 해당 VaultStaticSecret의 동기화를 중단한다.
`create:false`의 CR 삭제는 값 복원이 아니므로 원본 백업과 대조해 복원한다. 기존 인증서/ClusterIssuer/토큰 Secret은 삭제하지 않는다.
검증이 끝나면 비밀값 임시 복사본은 승인된 보관/삭제 절차로 정리한다.

## Ansible 관리 주체 연결

IaC main의 seed-secrets는 VaultStaticSecret 목적지를 발견하면 해당 Cloudflare Secret에 쓰지 않는다.
장애로 CRD가 사라진 경우에도 옛 값으로 재등록하지 않게 하려면 `bootstrap.local.yml`의
`gitops_vso_managed_secrets`에 `cert-manager/cloudflare-dns-api-token`을 인계 완료 후 추가한다.
이 PR은 Gitops만 수정하며 IaC 기본 `vault_common_targets`에 Cloudflare를 자동 추가하지 않는다.
공통 인증을 Ansible로 재구성하려면 기존 Backend/Collector 항목을 유지하면서 아래 항목도 추가한다.

```yaml
- namespace: cert-manager
  name: cloudflare-dns-sync
  policy: cloudflare-dns-read
  kv_path: onprem/cert-manager/cloudflare-dns-api-token
```
