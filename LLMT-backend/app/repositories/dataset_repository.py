"""Dataset repository."""

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.dataset import Dataset
from app.models.user import User


def get_stats(db: Session) -> dict:
    total = db.query(Dataset).count()
    total_size = db.query(Dataset).with_entities(
        Dataset.total_size
    ).all()
    size_sum = sum(s[0] for s in total_size) if total_size else 0
    completed = (
        db.query(Dataset)
        .filter(Dataset.quality_status == "passed")
        .count()
    )
    processing = (
        db.query(Dataset)
        .filter(Dataset.quality_status.in_(["checking", "repairing"]))
        .count()
    )
    by_type = {}
    rows = db.query(Dataset.data_type, Dataset.id).all()
    for dtype, _ in rows:
        by_type[dtype] = by_type.get(dtype, 0) + 1
    return {
        "total_datasets": total,
        "total_size": size_sum,
        "completed": completed,
        "processing": processing,
        "by_type": by_type,
    }


def get_dataset_by_id(db: Session, dataset_id: int) -> Dataset | None:
    return db.query(Dataset).filter(Dataset.id == dataset_id).first()


def get_datasets(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    keyword: str = "",
    data_type: str = "",
    quality_status: str = "",
) -> tuple[list[Dataset], int]:
    q = db.query(Dataset)
    if keyword:
        like = f"%{keyword}%"
        q = q.filter(Dataset.name.ilike(like) | Dataset.description.ilike(like))
    if data_type:
        q = q.filter(Dataset.data_type == data_type)
    if quality_status:
        q = q.filter(Dataset.quality_status == quality_status)
    total = q.count()
    datasets = (
        q.order_by(Dataset.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return datasets, total


def create_dataset(
    db: Session,
    name: str,
    data_type: str,
    owner_id: int,
    description: str | None = None,
    version: str = "v1.0.0",
    source: str | None = None,
    storage_path: str = "/datasets",
    file_count: int = 0,
    total_size: int = 0,
) -> Dataset:
    ds = Dataset(
        name=name,
        description=description,
        data_type=data_type,
        version=version,
        source=source,
        storage_path=storage_path,
        file_count=file_count,
        total_size=total_size,
        owner_id=owner_id,
    )
    db.add(ds)
    db.commit()
    db.refresh(ds)
    return ds


def update_dataset(db: Session, dataset: Dataset, **kwargs) -> Dataset:
    for key, value in kwargs.items():
        if value is not None:
            setattr(dataset, key, value)
    db.commit()
    db.refresh(dataset)
    return dataset


def delete_dataset(db: Session, dataset: Dataset) -> None:
    db.delete(dataset)
    db.commit()


# ============================================================================
# 处理任务（当前无独立 ProcessingJob 模型，返回模拟数据）
# ============================================================================

_MOCK_JOBS: list[dict] = []


def create_processing_job(db: Session, dataset: Dataset, job_type: str) -> dict:
    job = {
        "job_id": f"JOB-{len(_MOCK_JOBS)+1:04d}",
        "dataset_id": dataset.id,
        "dataset_name": dataset.name,
        "job_type": job_type,
        "status": "running",
        "progress": 0,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
    }
    _MOCK_JOBS.append(job)
    return job


def get_processing_jobs(
    page: int = 1, page_size: int = 20
) -> tuple[list[dict], int]:
    total = len(_MOCK_JOBS)
    start = (page - 1) * page_size
    return _MOCK_JOBS[start : start + page_size], total


def get_processing_job(job_id: str) -> dict | None:
    for j in _MOCK_JOBS:
        if j["job_id"] == job_id:
            return j
    return None


# ============================================================================
# 质量 & 血缘（当前无独立表，返回模拟数据）
# ============================================================================


def get_quality_report(dataset: Dataset) -> dict:
    return {
        "dataset_id": dataset.id,
        "dataset_name": dataset.name,
        "overall_score": 95.5,
        "completeness": True,
        "consistency": True,
        "timeliness": True,
        "anomalies": [],
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


def run_quality_check(db: Session, dataset: Dataset) -> dict:
    dataset.quality_status = "checking"
    db.commit()
    db.refresh(dataset)
    return get_quality_report(dataset)


def run_quality_repair(db: Session, dataset: Dataset) -> dict:
    dataset.quality_status = "repairing"
    db.commit()
    dataset.quality_status = "passed"
    db.commit()
    db.refresh(dataset)
    return {"status": "repaired", "fixed_anomalies": []}


def get_lineage(dataset: Dataset) -> dict:
    return {
        "dataset_id": dataset.id,
        "dataset_name": dataset.name,
        "source": dataset.source,
        "transformations": ["load", "clean", "validate"],
        "upstream": [],
        "downstream": [],
    }


def get_lineage_impact(dataset: Dataset) -> dict:
    return {
        "dataset_id": dataset.id,
        "affected_models": [],
        "affected_tasks": [],
        "affected_datasets": [],
    }
