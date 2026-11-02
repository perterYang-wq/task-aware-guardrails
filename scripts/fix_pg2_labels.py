# -*- coding: utf-8 -*-
"""把 Prompt Guard 2 的 config.json 标签映射改成语义标签。

原始 config.json 里根本没有 id2label/label2id，因此 transformers 回退到
LABEL_0/LABEL_1；下游任何 `argmax -> 名字` 的代码都会拿到无意义字符串。
本脚本按原字段顺序写入 BENIGN=0 / MALICIOUS=1，并留 .bak 备份。
"""
import json
import os
import shutil

PATHS = ["/data/hf_cache/pg2-86m", "/data/hf_cache/pg2-22m"]
ID2LABEL = {"0": "BENIGN", "1": "MALICIOUS"}
LABEL2ID = {"BENIGN": 0, "MALICIOUS": 1}

for path in PATHS:
    cfg_p = os.path.join(path, "config.json")
    bak_p = cfg_p + ".bak"
    if not os.path.exists(bak_p):          # 只备份一次，避免把改后的文件当原始版
        shutil.copy2(cfg_p, bak_p)

    with open(cfg_p, encoding="utf-8") as f:
        cfg = json.load(f)

    old_id2 = cfg.get("id2label")
    old_l2id = cfg.get("label2id")
    old_n = cfg.get("num_labels")

    # 保持原字段顺序，把三个标签字段追加在末尾（transformers 不关心位置）
    cfg["num_labels"] = 2
    cfg["id2label"] = dict(ID2LABEL)
    cfg["label2id"] = dict(LABEL2ID)

    with open(cfg_p, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print("%-26s old id2label=%s label2id=%s num_labels=%s" % (
        os.path.basename(path), old_id2, old_l2id, old_n))
    print("%-26s -> id2label=%s" % ("", cfg["id2label"]))
    print("%-26s -> label2id=%s num_labels=%d" % ("", cfg["label2id"], cfg["num_labels"]))
    print("    backup: %s" % bak_p)
