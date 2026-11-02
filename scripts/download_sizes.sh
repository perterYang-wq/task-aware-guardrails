#!/bin/bash
# 下载 guard 用的第二、第三个尺寸
set -x
source ~/anaconda3/etc/profile.d/conda.sh
conda activate /data/conda/envs/guard
export HF_HOME=/data/hf_cache
export HF_ENDPOINT=https://hf-mirror.com
export HF_HUB_DISABLE_XET=1

python - <<'PY'
from huggingface_hub import snapshot_download
for mid, dst in [("Qwen/Qwen2.5-3B-Instruct", "/data/hf_cache/qwen3b"),
                 ("Qwen/Qwen2.5-0.5B-Instruct", "/data/hf_cache/qwen0.5b")]:
    try:
        snapshot_download(mid, local_dir=dst)
        print("OK", mid, "->", dst, flush=True)
    except Exception as e:
        print("FAIL", mid, repr(e)[:200], flush=True)
PY
echo DOWNLOAD_DONE
du -sh /data/hf_cache/qwen3b /data/hf_cache/qwen0.5b 2>/dev/null
