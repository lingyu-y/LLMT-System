"""Setup script for llmt-training package."""

from setuptools import setup, find_packages

# The source tree is flat: LLMT-training/{config,core,models,...}
# We need to map the Python package name "llmt_training" to the repo root "."
_sub_pkgs = find_packages(exclude=["tests", "tests.*"])
_packages = ["llmt_training"] + [f"llmt_training.{p}" for p in _sub_pkgs]

setup(
    name="llmt-training",
    version="0.1.0",
    description="Integrated PyTorch + DeepSpeed + Megatron-LM training framework",
    packages=_packages,
    package_dir={"llmt_training": "."},
    python_requires=">=3.10",
    install_requires=[
        "torch>=2.0.0",
        "pydantic>=2.0",
        "click>=8.0",
        "pyyaml>=6.0",
        "sentencepiece>=0.1.99",
    ],
    extras_require={
        "deepspeed": ["deepspeed>=0.12.0"],
        "megatron": [],  # Megatron-LM is typically installed from source
        "reporting": [
            "influxdb-client>=1.30.0",
            "minio>=7.0.0",
        ],
        "all": [
            "deepspeed>=0.12.0",
            "influxdb-client>=1.30.0",
            "minio>=7.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "llmt-train=llmt_training.cli.main:cli",
        ],
    },
)
