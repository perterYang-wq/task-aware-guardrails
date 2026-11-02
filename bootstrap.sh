set -x
export HF_HOME=/data/hf_cache PIP_CACHE_DIR=/data/pip_cache HF_ENDPOINT=https://hf-mirror.com
source ~/anaconda3/etc/profile.d/conda.sh
~/anaconda3/bin/conda create --prefix /data/conda/envs/guard python=3.10 -y
conda activate /data/conda/envs/guard
pip install -q -i https://pypi.tuna.tsinghua.edu.cn/simple torch --index-url https://download.pytorch.org/whl/cu124
pip install -q -i https://pypi.tuna.tsinghua.edu.cn/simple transformers peft accelerate datasets scikit-learn pandas tqdm pyyaml
pip install -q -i https://pypi.tuna.tsinghua.edu.cn/simple agentdojo
cd /data/projects/guardrails/repos
curl -sL -o ad.tar.gz https://codeload.github.com/ethz-spylab/agentdojo/tar.gz/refs/heads/main && tar xzf ad.tar.gz && mv agentdojo-main agentdojo && rm ad.tar.gz
curl -sL -o ts.tar.gz https://codeload.github.com/MurrayTom/ToolSafe/tar.gz/refs/heads/main && tar xzf ts.tar.gz && mv ToolSafe-main toolsafe && rm ts.tar.gz
pip install -q -i https://pypi.tuna.tsinghua.edu.cn/simple huggingface_hub
huggingface-cli download Qwen/Qwen2.5-1.5B-Instruct --local-dir /data/hf_cache/qwen1.5b
echo BOOTSTRAP_DONE
