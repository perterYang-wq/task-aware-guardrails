set -x
export PIP_CACHE_DIR=/data/pip_cache
source ~/anaconda3/etc/profile.d/conda.sh
~/anaconda3/bin/conda create --prefix /data/conda/envs/vllm python=3.10 -y
conda activate /data/conda/envs/vllm
pip install -q -i https://pypi.tuna.tsinghua.edu.cn/simple vllm
python -c 'import torch,vllm; print("VLLM_OK",vllm.__version__,torch.__version__)'
