from datasets import load_dataset
import json
import os

DATASET_NAME = "Mxode/Chinese-Instruct"
SUBSET_NAME = "industryinstruction"
OUTPUT_FILE = "industryinstruction.jsonl"

ds = load_dataset(DATASET_NAME, SUBSET_NAME, split="train")

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    for item in ds:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")

print(f"保存完成：{OUTPUT_FILE}")
print(f"样本数量：{len(ds)}")
print(f"文件大小：{os.path.getsize(OUTPUT_FILE) / 1024 / 1024:.2f} MB")
