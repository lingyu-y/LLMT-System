"""Model repository."""

from sqlalchemy.orm import Session

from app.models.model_version import ModelVersion


def get_models(
    db: Session,
    page: int = 1,
    page_size: int = 20,
    keyword: str = "",
) -> tuple[list[ModelVersion], int]:
    q = db.query(ModelVersion).filter(ModelVersion.is_current.is_(True))
    if keyword:
        like = f"%{keyword}%"
        q = q.filter(
            ModelVersion.model_name.ilike(like)
            | ModelVersion.model_code.ilike(like)
            | ModelVersion.framework.ilike(like)
        )
    total = q.count()
    models = (
        q.order_by(ModelVersion.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return models, total


def get_model_by_code(db: Session, model_code: str) -> ModelVersion | None:
    return (
        db.query(ModelVersion)
        .filter(ModelVersion.model_code == model_code, ModelVersion.is_current.is_(True))
        .first()
    )


def get_model_by_id(db: Session, model_id: int) -> ModelVersion | None:
    return db.query(ModelVersion).filter(ModelVersion.id == model_id).first()


def get_versions(db: Session, model_code: str) -> list[ModelVersion]:
    return (
        db.query(ModelVersion)
        .filter(ModelVersion.model_code == model_code)
        .order_by(ModelVersion.id.desc())
        .all()
    )


def rollback_version(db: Session, model: ModelVersion) -> dict:
    """回滚到指定版本，返回 {rolled_back_to, previous_current}。"""
    previous = (
        db.query(ModelVersion)
        .filter(ModelVersion.model_code == model.model_code, ModelVersion.is_current.is_(True))
        .first()
    )
    previous_version = previous.version if previous else None

    db.query(ModelVersion).filter(
        ModelVersion.model_code == model.model_code, ModelVersion.is_current.is_(True)
    ).update({"is_current": False})
    model.is_current = True
    db.commit()
    db.refresh(model)

    return {
        "rolled_back_to": {
            "version": model.version,
            "model_name": model.model_name,
            "framework": model.framework,
            "storage_path": model.storage_path,
        },
        "previous_current": {"version": previous_version} if previous_version else None,
    }


def get_model_by_code_and_version(
    db: Session, model_code: str, version: str
) -> ModelVersion | None:
    return (
        db.query(ModelVersion)
        .filter(ModelVersion.model_code == model_code, ModelVersion.version == version)
        .first()
    )


def auto_version(db: Session, model_code: str) -> str:
    """自动生成语义化版本号：查已有版本，累加 patch；首个版本为 v1.0.0。"""
    existing = (
        db.query(ModelVersion.version)
        .filter(ModelVersion.model_code == model_code)
        .all()
    )
    max_patch = -1
    max_minor = 0
    max_major = 1
    for (ver,) in existing:
        try:
            parts = ver.lstrip("v").split(".")
            if len(parts) == 3:
                maj, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
                if patch > max_patch:
                    max_major, max_minor, max_patch = maj, minor, patch
        except (ValueError, IndexError):
            pass
    return f"v{max_major}.{max_minor}.{max_patch + 1}"


def create_model(
    db: Session,
    model_name: str,
    model_code: str,
    tag: str | None = None,
    description: str | None = None,
    framework: str | None = None,
    metrics: dict | None = None,
    training_metadata: dict | None = None,
    task_id: int | None = None,
    creator_id: int | None = None,
) -> ModelVersion:
    version = auto_version(db, model_code)

    db.query(ModelVersion).filter(
        ModelVersion.model_code == model_code, ModelVersion.is_current.is_(True)
    ).update({"is_current": False})

    model = ModelVersion(
        model_name=model_name,
        model_code=model_code,
        version=version,
        tag=tag,
        description=description,
        framework=framework or (training_metadata or {}).get("framework"),
        storage_path=f"models/{model_code}/{version}",
        dataset_version=(training_metadata or {}).get("dataset_version"),
        metrics_json=metrics or {},
        hyperparams_json=training_metadata or {},
        task_id=task_id,
        created_by_id=creator_id,
        is_current=True,
    )
    db.add(model)
    db.commit()
    db.refresh(model)
    return model


def delete_model(db: Session, model_code: str, version: str | None = None) -> int:
    """Delete model version(s). If version is None, delete all versions.

    Also deletes files from MinIO models bucket.
    Returns count of deleted records.
    """
    query = db.query(ModelVersion).filter(ModelVersion.model_code == model_code)
    if version:
        query = query.filter(ModelVersion.version == version)

    rows = query.all()
    if not rows:
        return 0

    # Delete from MinIO
    try:
        from app.core.config import get_settings
        from app.core.database import get_minio_client
        minio = get_minio_client()
        bucket = get_settings().MINIO_BUCKET_MODELS
        for r in rows:
            prefix = r.storage_path or f"models/{r.model_code}/{r.version}"
            if minio.bucket_exists(bucket):
                objects = list(minio.list_objects(bucket, prefix=prefix, recursive=True))
                for obj in objects:
                    try:
                        minio.remove_object(bucket, obj.object_name)
                    except Exception:
                        pass
    except Exception:
        pass  # MinIO cleanup is best-effort

    count = len(rows)
    for r in rows:
        db.delete(r)
    db.commit()
    return count
