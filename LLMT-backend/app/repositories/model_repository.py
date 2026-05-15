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


def rollback_version(db: Session, model: ModelVersion) -> ModelVersion:
    db.query(ModelVersion).filter(
        ModelVersion.model_code == model.model_code, ModelVersion.is_current.is_(True)
    ).update({"is_current": False})
    model.is_current = True
    db.commit()
    db.refresh(model)
    return model


def get_model_by_code_and_version(
    db: Session, model_code: str, version: str
) -> ModelVersion | None:
    return (
        db.query(ModelVersion)
        .filter(ModelVersion.model_code == model_code, ModelVersion.version == version)
        .first()
    )


def create_model(
    db: Session,
    model_name: str,
    model_code: str,
    version: str,
    tag: str | None = None,
    description: str | None = None,
    framework: str | None = None,
    dataset_version: str | None = None,
    metrics_json: dict | None = None,
    hyperparams_json: dict | None = None,
) -> ModelVersion:
    db.query(ModelVersion).filter(
        ModelVersion.model_code == model_code, ModelVersion.is_current.is_(True)
    ).update({"is_current": False})

    model = ModelVersion(
        model_name=model_name,
        model_code=model_code,
        version=version,
        tag=tag,
        description=description,
        framework=framework,
        storage_path=f"models/{model_code}/{version}",
        dataset_version=dataset_version,
        metrics_json=metrics_json or {},
        hyperparams_json=hyperparams_json or {},
        is_current=True,
    )
    db.add(model)
    db.commit()
    db.refresh(model)
    return model
