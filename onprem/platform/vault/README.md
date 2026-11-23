# 외부 Vault VM + VSO 공통 설정 (GPU-241)

## 현재 진행 상황 — 2026-11-23

| 항목 | 확인 수준 |
|---|---|
| Vault VM | 사용자 제공 출력에서 `.81`의 Vault 2.2.2·Raft·systemd 실행과 최초 미초기화 상태를 확인. 이후 초기 설정은 사용자가 진행 |
| Kubernetes 인증 | 관리 API `.120:6443`, mount `onprem`, 서비스별 동기화 SA/role 사용 |
| Backend DB | 사용자 연결 성공 보고. `platform/backend-db` → KV `devoops/onprem/platform/backend-db` |
| Collector DB | 사용자 연결 성공 보고. `data-system/collector-db` → KV `devoops/onprem/data-system/collector-db` |
| VSO | 위 DB 연결 성공 보고에 따른 동기화 경로. 실제 live Helm values·이미지·권한은 이번 코드 작성 중 조회하지 않음 |
| 코드화 | IaC PR #51 + 이 매니페스트. push/PR/머지와 운영 적용은 별개 |
| Cloudflare | 매니페스트 준비. 실제 토큰의 Vault 등록·cert-manager namespace 공개 CA 준비·수동 Sync는 별도 |
| HA/추가 Secret | `.82`·`.83` 가입, Vault 접속 주소 HA, Cloudflare 실제 연결·Kafka·모니터링 등 추가 인계는 미완료 |

본 문서는 **사용자 보고와 이전 출력**을 정리한 것이며 새 운영 점검 결과가 아니다.

## 코드 역할

| 위치 | 역할 |
|---|---|
| IaC `ansible/playbooks/vault/configure-vms.yml` | 기존 VM의 Vault 버전·Raft·TLS·systemd 구성 |
| IaC `ansible/playbooks/vault/configure-kubernetes-auth.yml` | `auth/onprem` API/CA 연결, 서비스별 read 정책·role, 공개 CA Secret 등록 |
| `operator/values.yaml` | VSO Helm 1.6.0, release `vault-secrets-operator`, namespace `vault-secrets-operator-system` |
| `common/` | namespace별 VaultConnection·VaultAuth·동기화 전용 SA·최소 TokenReview RBAC |
| `backend-db/`, `collector-db/`, `cloudflare-dns/` | 기존 Secret으로 값을 동기화하는 VaultStaticSecret. 비밀값 없음 |
| `bootstrap/onprem/applications/gpu-vault-*.yaml` | 위 요소의 수동 동기화용 Argo Application |

Vault 서버 Pod·Agent 사이드카·Vault PKI·동적 DB 계정은 추가하지 않는다.
Backend·Collector Deployment, 기존 Secret 참조와 AWS 인증은 바꾸지 않는다.
`vault-vm-ca`는 공개 인증서만 포함하지만 실제 인증서 내용은 IaC가 외부 파일에서 등록한다.
VSO/앱에서 이 공개 CA를 Vault로부터 받아야 하는 순환 의존을 만들지 않는다.

## 최초 인계 순서

1. IaC의 Vault VM·인증 설정을 검토한다. 운영자가 Vault CLI에 로그인해야 하며 root token을 Pod/Git에 넣지 않는다.
2. 현재 Helm release의 version·values·namespace와 실제 `VaultAuth`/Secret을 확인한다. 다른 배포 주체의 리소스면 자동 인계하지 않는다.
3. `gpu-foundation`과 AppProject를 먼저 반영해 VSO namespace와 chart repository를 허용한다.
4. `gpu-vault-operator`의 diff를 확인하고 **수동 sync**한다. 기존 Helm release와 같은 이름/namespace를 쓴다.
   Helm 삭제 후 재설치하는 절차가 아니다. Argo 관리로 넘긴 뒤 IaC Helm bootstrap으로 동시에 upgrade하지 않는다.
5. IaC가 두 namespace에 공개 CA `vault-vm-ca`(key `ca.crt`)를 등록했는지 확인한 뒤 `gpu-vault-connections`를 수동 sync한다.
6. 원본 Secret과 KV의 모든 key/byte가 같은지 확인한다. 이전 중 외부 비밀번호 교체나 기존 Secret 생성 스크립트를 동시에 실행하지 않는다.
7. 이미 성공한 `backend-db-sync`, `collector-db-sync`와 이름·경로가 일치하는지 확인한 뒤 각 Application을 수동 sync한다.
8. VSO의 실제 `SecretSynced` 사건·성공 상태와 기존 Secret UID/type/data 유지, 서비스 DB 접속을 확인한다.
   Secret의 `resourceVersion`이나 VSO HMAC/annotation 같은 메타데이터는 변경될 수 있다.

다섯 Vault Application에는 `automated`·자동 prune·앱 rollout restart 설정이 없다.
부모 root의 수동/자동 설정과 별개로 **Application 생성만으로 자식의 초기 sync를 수행하지 않는다**.
이미 존재하는 VaultStaticSecret은 VSO가 계속 처리하므로, 수동 sync 설정이 기존 동기화를 정지시키는 것은 아니다.

## 변경 없이 인계하는 계약

```text
Vault 원본 경로                          Kubernetes 목적지
devoops/onprem/platform/backend-db       platform/backend-db
devoops/onprem/data-system/collector-db  data-system/collector-db
devoops/onprem/cert-manager/cloudflare-dns-api-token  cert-manager/cloudflare-dns-api-token
```

`destination.create: false`는 기존 Secret에 쓰는 설정이다. 읽기 전용 의미가 아니다.
`excludeRaw: true`로 `_raw` 추가를 막고, `refreshAfter: 60s`로 조회한다.
DB 사용자/비밀번호는 변경하지 않는다. VSO는 DB 서버 계정을 만들거나 비밀번호를 교체하지 않는다.
원본 값이 달라지면 Secret도 바뀔 수 있으므로 비밀번호 교체는 별도 운영 절차로 진행한다.
다른 Secret 변경 감시 도구가 설치되어 있다면 그 재시작 동작도 확인한다.

인증용 SA `backend-db-sync`, `collector-db-sync`는 기존 앱 SA와 다르다.
자동 토큰 마운트가 없어도 VSO가 TokenRequest로 단기 JWT를 요청할 수 있다.
외부 Vault의 client-JWT reviewer 방식에 필요한 TokenReview create만 허용한다.
VSO 자체 SA의 TokenRequest·Secret 접근 권한은 공식 chart가 관리한다.
audience는 현재 수동 설정과 동일하게 비워 두며, 강화 시 Vault role·VSO·TokenReview 검증을 함께 맞춘다.

## 후속 대상

Cloudflare API 토큰은 [cloudflare-dns/README.md](cloudflare-dns/README.md)의 사전 준비 후 수동 Sync한다. cert-manager 인증서 Secret과 구분해 이전한다.
`frontend-tls`는 cert-manager가 계속 관리한다. Kafka는 실제 인증이 있는 경우만 추가한다.
모니터링의 Slack/DB Secret은 담당 생성 도구와 인계한 뒤 대상별로 추가한다.
AWS Pod Identity·Roles Anywhere, 워커 kubeconfig 발급/갱신/삭제 경로는 이번에 이전하지 않는다.
각 대상은 전용 KV 경로·read 정책·VaultAuth·VaultStaticSecret으로 추가한다.

[프로젝트 설계](https://devoops-team.atlassian.net/wiki/spaces/GPUF/pages/29949958) ·
[IaC PR #51](https://github.com/DevOops-Team/IaC/pull/51)
