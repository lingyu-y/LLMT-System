"""Setup script for llmt-training package."""

from setuptools import setup, find_packages

setup(
    name="llmt-training",
    version="0.1.0",
    description="Integrated PyTorch + DeepSpeed + Megatron-LM training framework",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "torch>=2.0.0",
        "pydantic>=2.0",
        "click>=8.0",
        "pyyaml>=6.0",
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
