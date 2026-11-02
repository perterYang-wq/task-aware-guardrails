"""阶段 1：冻结现有实验。只读复制 + 指纹记录，不移动、不覆盖任何现有文件。"""
import json, os, shutil, hashlib, subprocess, datetime

ROOT = '/data/projects/guardrails'
DEST = os.path.join(ROOT, 'results/ad_v3/FREEZE_STAGE1')
os.makedirs(DEST, exist_ok=True)
for sub in ('code', 'artifacts', 'logs', 'configs'):
    os.makedirs(os.path.join(DEST, sub), exist_ok=True)


def sha(p, n=1 << 20):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for c in iter(lambda: f.read(n), b''):
            h.update(c)
    return h.hexdigest()


def sh(cmd):
    try:
        return subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.STDOUT).strip()
    except Exception as e:
        return 'ERR: %s' % e


CODE = [f for f in os.listdir(os.path.join(ROOT, 'scripts')) if f.endswith('.py')]
CODE += ['guard/router.py', 'guard/schema.py']
for rel in CODE:
    src = rel if os.path.isabs(rel) else os.path.join(ROOT, rel if rel.startswith('guard/') else 'scripts/' + rel)
    if os.path.exists(src):
        dst = os.path.join(DEST, 'code', os.path.basename(src))
        shutil.copy2(src, dst)

ART = []
for d in ('results/ad_v2',):
    for f in sorted(os.listdir(os.path.join(ROOT, d))):
        p = os.path.join(ROOT, d, f)
        if os.path.isfile(p) and os.path.getsize(p) < 5 << 20:
            shutil.copy2(p, os.path.join(DEST, 'artifacts', f))
            ART.append(p)

LOGS = []
for f in ('ad_ws2.log', 'ad_bank2.log', 'ad_baseline.log', 'vllm12.log',
          'ad_lenconfound.py', 'ad_pg2_trunc.py', 'ad_lencheck2.py'):
    p = os.path.join('/tmp', f)
    if os.path.exists(p):
        shutil.copy2(p, os.path.join(DEST, 'logs', f))
        LOGS.append(p)

# 只记录 hash，不复制（大文件）
BIG = ['runs/ad_ws2_trace.jsonl', 'runs/ad_bank2_trace.jsonl', 'runs/ad_trace_baseline.jsonl']
manifest = {
    'frozen_at': datetime.datetime.now().isoformat(timespec='seconds'),
    'git': sh('cd %s && git rev-parse HEAD 2>/dev/null || echo "NO_GIT_REPO"' % ROOT),
    'gpu': sh('nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader'),
    'disk': sh('df -h /data | tail -1'),
    'python': sh('/data/conda/envs/guard/bin/python -V'),
    'code': {os.path.basename(p): {'sha256': sha(os.path.join(DEST, 'code', os.path.basename(p)))}
             for p in CODE if os.path.exists(os.path.join(DEST, 'code', os.path.basename(p)))},
    'artifacts': {os.path.basename(p): {'sha256': sha(p), 'bytes': os.path.getsize(p)} for p in ART},
    'logs': {os.path.basename(p): {'sha256': sha(p)} for p in LOGS},
    'big_files_not_copied': {p: {'sha256': sha(os.path.join(ROOT, p)),
                                 'bytes': os.path.getsize(os.path.join(ROOT, p))}
                             for p in BIG if os.path.exists(os.path.join(ROOT, p))},
    'frozen_elsewhere': {
        'results/frozen/taskaware/': 'taskaware-v1，check_taskaware_freeze.py 复核 74/74',
        'results/ad_v2/backup_20261031/': '旧预测/标签/分数备份，未覆盖',
    },
    'agent_config': {
        'model': '/home/linux/.cache/huggingface/hub/models--Qwen--Qwen2.5-7B-Instruct/snapshots/a09a35458c702b33eeacc393d103063234e8bc28',
        'served_name': 'qwen7b', 'dtype': 'float16',
        'max_model_len': 12288, 'gpu_memory_utilization': 0.80, 'port': 8000,
        'temperature': 0.0, 'top_p': 1.0,
        'vllm_env': '/data/conda/envs/vllm12 (vllm 0.6.6.post1, torch 2.5.1+cu124, transformers 4.45.2)',
        'parser': 'tolerant_parse.install_tolerant_parser() 覆盖 LocalLLM._parse_model_output',
        'attack_name_override': 'iia.get_model_name_from_pipeline -> "AI model"',
    },
    'guard_config': {
        'adapter': 'guard/adapters/p1_15b_task_l2_s0（taskaware-v1 冻结）',
        'base': '/data/hf_cache/qwen1.5b', 'bs': 16, 'max_new_tokens': 6, 'do_sample': False,
    },
    'pg2_config': {
        'weights': '/data/hf_cache/pg2-86m', 'id2label': {0: 'BENIGN', 1: 'MALICIOUS'},
        'score': 'softmax(logits)[:,1] = P(MALICIOUS)',
        'chunk': 400, 'stride': 64, 'max_length': 512, 'aggregation': 'max over chunks',
    },
    'seeds': {'fold_split': 'np.random.default_rng(0).permutation, K=5',
              'bootstrap': 'B=2000, seed=0, cluster=task_id'},
    'prereg': {'path': 'results/ad_v2/prereg.json', 'sha256': sha(os.path.join(ROOT, 'results/ad_v2/prereg.json'))},
}
json.dump(manifest, open(os.path.join(DEST, 'MANIFEST.json'), 'w'), ensure_ascii=False, indent=1)

# 新实验目录
for p in ('results/ad_v3/ws_fix', 'results/ad_v3/runs', 'reports/ad_v3'):
    os.makedirs(os.path.join(ROOT, p), exist_ok=True)

print('freeze ->', DEST)
print('  code %d, artifacts %d, logs %d' % (len(manifest['code']), len(ART), len(LOGS)))
print('  workspace trace sha256 =', manifest['big_files_not_copied']['runs/ad_ws2_trace.jsonl']['sha256'][:20])
print('  ad_v3 目录已建：results/ad_v3/{ws_fix,runs}, reports/ad_v3')
