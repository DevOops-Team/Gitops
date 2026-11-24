"""Offline render/connection checks; no credentials or cluster access."""
import hashlib
import json
from pathlib import Path
import subprocess
import yaml

ROOT = Path(__file__).resolve().parents[2]


def build(path):
    return list(yaml.safe_load_all(subprocess.check_output(['kubectl', 'kustomize', str(ROOT/path)], text=True)))


def named(docs, kind, name):
    return next(d for d in docs if d and d['kind'] == kind and d['metadata']['name'] == name)


def main():
    backend = build('onprem/platform/backend/overlays/onprem')
    tls = build('onprem/platform/backend/overlays/onprem-recovery-api')
    controller = build('onprem/controllers/recovery-controller/overlays/onprem')
    certs = build('onprem/platform/backend/recovery-api/tls')
    default_pod = named(backend, 'Deployment', 'backend')['spec']['template']['spec']
    tls_pod = named(tls, 'Deployment', 'backend')['spec']['template']['spec']
    deployment = named(controller, 'Deployment', 'recovery-controller')
    control_pod = deployment['spec']['template']['spec']
    assert not any(c['name'] == 'recovery-tls' for c in default_pod['containers'])
    assert not any(d['kind'] == 'Ingress' for d in tls)
    proxy = next(c for c in tls_pod['containers'] if c['name'] == 'recovery-tls')
    assert '@sha256:' in proxy['image']
    assert proxy['securityContext']['readOnlyRootFilesystem'] is True
    assert proxy['ports'][0]['containerPort'] == 8443
    service = named(tls, 'Service', 'backend-recovery')
    assert service['spec']['type'] == 'ClusterIP'
    assert service['spec']['ports'][0] == {'name':'recovery-https', 'port':8443, 'targetPort':'recovery-https'}
    back_app = named(build('bootstrap/onprem/applications'), 'Application', 'gpu-backend')
    assert back_app['spec']['source']['path'] == 'onprem/platform/backend/overlays/onprem'
    tls_app = named(build('bootstrap/onprem/applications'), 'Application', 'gpu-backend-recovery-tls')
    assert 'automated' not in tls_app['spec']['syncPolicy']
    assert not tls_app['metadata'].get('finalizers')
    root_ca = named(certs, 'Certificate', 'backend-recovery-root-ca')
    server = named(certs, 'Certificate', 'backend-recovery-tls')
    assert root_ca['spec']['isCA'] is True
    assert server['spec']['issuerRef']['name'] == 'backend-recovery-ca'
    assert server['spec']['privateKey']['rotationPolicy'] == 'Always'
    ca_volume = next(v for v in control_pod['volumes'] if v['name'] == 'backend-api-ca')
    assert ca_volume['secret']['items'] == [{'key':'tls.crt','path':'ca.crt'}]
    assert ca_volume['secret']['secretName'] == root_ca['spec']['secretName']
    references = []
    for pod, cname, env in ((default_pod,'backend','RECOVERY_API_TOKEN'),
                            (control_pod,'controller','BACKEND_RECOVERY_API_TOKEN')):
        container = next(c for c in pod['containers'] if c['name'] == cname)
        value = next(v for v in container['env'] if v['name'] == env)
        assert 'value' not in value
        references.append(value['valueFrom']['secretKeyRef'])
    assert references[0] == references[1] == {'name':'backend-recovery-api','key':'token','optional':True}
    init = next(c for c in control_pod['initContainers'] if c['name'] == 'backend-api-trust')
    app = next(c for c in control_pod['containers'] if c['name'] == 'controller')
    assert init['image'] == app['image']
    compile(init['command'][2], '<backend-api-trust>', 'exec')
    assert 'get_default_verify_paths' in init['command'][2]
    assert 'tls.key' not in init['command'][2]
    cfg_path=ROOT/'onprem/controllers/recovery-controller/overlays/onprem/config.json'
    cfg=json.loads(cfg_path.read_text())
    assert cfg['backend_metadata']['enabled'] is False
    assert cfg['backend_metadata']['base_url'] == 'https://backend-recovery.platform.svc:8443'
    assert 'backend-recovery.platform.svc' in server['spec']['dnsNames']
    checksum=deployment['spec']['template']['metadata']['annotations']['devoops/config-sha256']
    assert checksum == hashlib.sha256(cfg_path.read_bytes()).hexdigest()
    configmap=named(tls,'ConfigMap',next(d['metadata']['name'] for d in tls if d['kind']=='ConfigMap' and 'nginx.conf' in d.get('data',{})))
    assert 'proxy_pass http://127.0.0.1:8000' in configmap['data']['nginx.conf']
    assert 'location / { return 404; }' in configmap['data']['nginx.conf']
    assert 'sha256sum' in configmap['data']['run.sh'] and 'kill -HUP' in configmap['data']['run.sh']
    subprocess.run(['sh','-n',str(ROOT/'onprem/platform/backend/overlays/onprem-recovery-api/run.sh')],check=True)
    print('Backend token/HTTPS/CA/disabled activation render contract passed')


if __name__ == '__main__':
    main()
