# Backend recovery API Vault 인계 (GPU-241)

기존 platform/backend-recovery-api Secret (Opaque, RECOVERY_API_TOKEN)을 동일 이름의 VSS로 관리한다. 실제 토큰은 Git에 저장하지 않는다. KV v2: devoops/onprem/platform/backend-recovery-api, policy: platform-backend-recovery-api-read (data 경로 read), role: platform-backend-recovery-api-sync (platform/backend-recovery-api-sync).

운영자: 기존 VSS Ready 및 Secret UID/type/키를 값 출력 없이 확인하고 Vault 원본과 동일한지 안전하게 비교한다. 기존 VSS와 Secret은 삭제하지 않는다. 수동 Sync 전 Argo 공유 리소스 여부와 변경 diff를 확인한다. create:false 및 excludeRaw:true 전환은 기존 Secret 보존을 의도하며 _raw 제거 여부와 UID/토큰 유지 여부를 실제 Sync 후 검증한다. 자동 prune/replace/force 및 rolloutRestartTargets는 사용하지 않는다.

새 TokenReview 전용 binding으로 인증 성공을 확인한 뒤 기존 수동 binding platform-backend-recovery-api-tokenreview의 대상과 roleRef를 확인하고, 동일 SA에 대한 중복 권한일 때만 운영자가 제거한다. 새 binding 성공 전에 제거하지 않는다.

Backend RECOVERY_API_TOKEN과 controller BACKEND_RECOVERY_API_TOKEN은 동일 Secret의 RECOVERY_API_TOKEN 키를 참조한다. 환경변수 반영은 Pod rollout이 필요하다. TLS 및 backend_metadata 활성화는 별도 작업이다.
