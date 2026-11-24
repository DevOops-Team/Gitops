# Backend 복구 조회 API 배포 연결 (GPU-119)

## 이 변경에서 준비한 것

- Backend `RECOVERY_API_TOKEN`과 controller `BACKEND_RECOVERY_API_TOKEN`이 같은
  `platform/backend-recovery-api` Secret의 `RECOVERY_API_TOKEN` 키를 참조한다. 실제 값은 Git에 없다.
- controller config의 HTTPS origin은 `https://backend-recovery.platform.svc:8443`이다.
  `backend_metadata.enabled=false`로 준비한다. Backend의 실제 PlacementSource 연결이 선행돼야 한다.
- cert-manager로 내부 CA와 서비스 DNS SAN 인증서를 발급하는 **수동** 앱
  `gpu-backend-recovery-tls`를 추가한다. Vault PKI·Cloudflare·기존 공개 인증서는 사용하지 않는다.
- 선택 overlay `onprem/platform/backend/overlays/onprem-recovery-api`가 Backend Pod에
  nginx TLS sidecar와 ClusterIP Service `backend-recovery:8443`을 추가한다.
  API만 localhost:8000으로 프록시한다. Ingress/공인 DNS/NodePort는 만들지 않는다.
- controller는 CA Secret에서 공개 `tls.crt`만 투영한다. 루트 개인키 `tls.key`를 받지 않는다.
  init 컨테이너가 기존 시스템 CA + 내부 CA를 합쳐 Python SSL_CERT_FILE을 준비한다.
  AWS_CA_BUNDLE/기존 AWS 인증은 변경하지 않는다.

기본 gpu-backend Application path는 기존 `overlays/onprem`이다. TLS overlay는 아직 활성화하지 않는다.
토큰/CA 참조는 optional로 준비하므로 미등록 상태에서도 기존 앱이 Secret 누락으로 기동 불가해지지 않는다.
이것은 인증 우회가 아니다: Backend 토큰 미설정이면 API 503, controller 토큰 누락이면 조회 거부다.
이번 main 반영만으로 HTTPS 서비스나 API 조회가 활성화되지 않는다.

## 담당 연결

| 담당 | 필요 작업 |
|---|---|
| Backend/스케줄링 | NoPlacement를 실제 신뢰된 전체 배치 정보로 교체, 요청 세대와 placement_generation 일치 |
| 배포 운영자 | 동일 서비스 토큰 Secret 준비, cert-manager 내부 인증서 수동 발급, TLS overlay 전환 |
| 복구 담당 | Backend 응답/인증/배치 시험 후 backend_metadata.enabled=true 및 config checksum 갱신 |

Backend 코드 계약은 K8s `recovery-controller/docs/backend-metadata-api.md`다.
이 변경은 Backend/스케줄링 코드를 수정하거나 기존 HOLD를 자동 해제하지 않는다.

## 사전 준비 (운영자가 실제 관리 context에서 실행)

1. 현재 Backend/컨트롤러 이미지에 GPU-119 API/클라이언트가 포함됐는지 확인한다.
   기존 release bot의 digest pinning을 유지하며 이미지 태그를 이 문서 때문에 임의 변경하지 않는다.
2. `backend-recovery-api`가 기존에 있으면 관리자·내용을 먼저 확인한다. 새 토큰으로 자동 덮어쓰지 않는다.
   없으면 충분히 긴 임의 토큰을 보호된 파일로 생성하고 **같은 Secret 하나**에 저장한다.
   예: `umask 077` 환경에서 `openssl rand -base64 48 | tr -d '\r\n'` 출력을 보호된 임시 파일에 저장한 후
   `kubectl --context <관리-context> -n platform create secret generic backend-recovery-api --from-file=RECOVERY_API_TOKEN=<파일>`.
   토큰에 CR/LF를 넣지 않는다(컨트롤러가 거부한다). 토큰 문자열을 셸 인자·로그·Git·DM으로 전달하지 않는다. Vault로 공급하려면 동일 key를 유지하고
   별도의 KV/VSO 인계 절차로 연결한다(이 PR이 Vault에 새 값을 쓰지는 않음).
   optional 환경변수는 Secret이 나중에 생겨도 실행 중인 프로세스에 자동 반영되지 않는다.
3. cert-manager 정상 확인 후 `gpu-backend-recovery-tls`만 수동 Sync한다.
   `backend-recovery-root-ca`와 `backend-recovery-tls` Certificate Ready, CA Issuer Ready를 확인한다.
   root 개인키는 Kubernetes Secret에 cert-manager가 관리한다. 백업/권한·10년 CA 만료/갱신은 운영 책임이다.
   이 Secret을 VSO로 동시에 덮어쓰지 않는다.

## 활성화 순서 — 준비 확인 후 별도 Git 변경

1. `bootstrap/onprem/applications/gpu-backend.yaml`의 source.path를
   `onprem/platform/backend/overlays/onprem-recovery-api`로 바꾼다. 같은 Deployment를
   두 Argo Application으로 관리하지 않는다. 기존 gpu-backend의 자동 Sync가 동작하므로
   토큰/Certificate Ready를 **path 변경 전에** 확인한다.
2. Backend rollout을 확인한다. 기존 HTTP Service는 계속 8000이며, 복구 Service만 8443이다.
   nginx는 non-root/read-only 파일시스템으로 실행하고 TLS Secret을 디렉토리 mount한다.
   인증서 갱신 시 10초 주기로 변화 확인 → nginx -t → reload한다. 개인키/토큰은 로그에 출력하지 않는다.
3. controller를 새로 rollout해 Secret env와 내부 CA가 실제 반영되게 한다.
   초기 CA 앱 Sync 전 시작했던 Pod에는 public CA만 있을 수 있다. trust init은 매 Pod 시작 때 실행된다.
4. credential 값을 출력하지 않는 내부 시험으로 HTTP 200·정확한 JSON을 확인한다.
   토큰 없음/틀림은 401, 실제 배치 미연결은 503, 옛 작업 해시 없음은 422다.
   잘못된 CA/호스트명에서는 TLS 검증이 실패해야 한다. curl -k/skipTLSVerify는 사용하지 않는다.
5. 컨트롤러 `backend_metadata.enabled`만 true로 바꾸고 config.json SHA-256 annotation도 갱신한다.
   이 설정 변경으로 controller Pod가 재생성되어 같은 토큰과 올바른 trust bundle을 읽는다.
6. 신규 시험 작업·새 사건으로 API 조회 → job# 조건부 생성 → 세대 증가/RR →
   별도 새 배치/복원/첫 step 증거 → COMPLETED까지 검증한다.
   기존 metadata missing HOLD는 자동 재개하지 않는다.

## 갱신·중단·롤백

- Secret env는 자동 재로딩되지 않는다. 토큰 교체 시 컨트롤러 신규 조회를 먼저 중단하고
  Backend와 controller를 같은 값으로 계획적으로 rollout한다. 두 값이 다르면 401/HOLD가 될 수 있다.
- leaf 인증서는 자동 갱신/reload하지만 루트 CA 교체·만료는 별도 계획이 필요하다.
  controller trust bundle은 init에서 고정되므로 CA 변경 후 반드시 새 rollout과 TLS 시험을 한다.
- nginx/TLS 문제 시 먼저 backend_metadata를 false로 되돌리고 checksum 갱신 후
  Backend source.path를 기존 onprem으로 복원한다. 인증서·Secret을 자동 삭제하지 않는다.
- 기존 HTTP 경로는 frontend용으로 유지한다. 새 TLS Service의 인증 성공은 네트워크 접근 통제 자체를
  대신하지 않으며 서비스 토큰은 조회 용도로만 사용한다.

## 검증

`python tools/recovery/validate_backend_connection.py`는 기본/선택 overlay, 같은 Secret 참조,
TLS DNS SAN·공개 CA만 mount·기존 시스템 trust 보존·기본 disabled·checksum·수동 인증서 앱을 검증한다.
실제 서비스 토큰 발급·cert-manager reconciliation·Pod rollout·Backend 배치 API 연결 시험은 별도다.
