# upstream

외부 프로젝트의 공식 릴리스 매니페스트를 그대로 둔다. `onprem/`과 `eks/`의 kustomization이 공용으로 참조한다 (Application이 직접 가리키지 않음).

| 디렉토리 | 원본 | sha256 |
|---|---|---|
| `kueue-v0.20.4/manifests.yaml` | https://github.com/kubernetes-sigs/kueue/releases/download/v0.20.4/manifests.yaml | `c6f68065d429240b57ade9568761a9e1cd5ea14ada2c7e9225430a0280a11823` |
| `jobset-v0.13.0/manifests.yaml` | https://github.com/kubernetes-sigs/jobset/releases/download/v0.13.0/manifests.yaml | `41b599b721eca22af5bcb7a1802b976c389933759aab510daeeb40afcc775a90` |

- `manifests.yaml`은 고치지 않는다. 바꿀 것은 같은 디렉토리 `kustomization.yaml`의 patch(모든 클러스터 공통) 또는 각 클러스터 디렉토리에서 한다
- 버전을 올릴 때는 새 디렉토리(`kueue-v0.x.y/`)를 만들고 참조를 바꾼 뒤 옛 디렉토리를 지운다 (ADR-9 버전 고정)
