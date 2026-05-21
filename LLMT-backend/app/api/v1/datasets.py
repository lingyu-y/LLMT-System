"""Dataset management endpoints -- 数据处理接口 (Part 3 of jiekou.md)."""

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.core.responses import paginated_response, success_response
from app.dependencies.auth import get_current_user
from app.dependencies.db import get_db
from app.models.user import User
from app.repositories import dataset_repository
from app.services import dataset_service, log_service
from app.schemas.dataset import (
    DatasetCreate,
    DatasetListOut,
    DatasetOut,
    DatasetUpdate,
)

router = APIRouter(prefix="/datasets", tags=["数据处理"])

# ============================================================================
# 静态路径优先 — stats / upload / import / processing-jobs
# ============================================================================


@router.get("/stats")
def dataset_stats(
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    return success_response(dataset_repository.get_stats(db))


@router.post("/upload")
def upload_dataset_file(
    file: UploadFile,
    dataset_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ds = dataset_repository.get_dataset_by_id(db, dataset_id)
    if ds is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="数据集不存在")
    result = dataset_service.upload_file(db, ds, file, current_user.username)
    if not result.get("success"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=result.get("error"))
    log_service.create_log(
        db, user_id=current_user.id, username=current_user.username,
        action="upload", resource="dataset", resource_id=ds.id,
        detail=f"上传文件 {file.filename} ({result.get('size', 0)} bytes)",
    )
    return success_response(result, "文件上传成功")


@router.post("/upload/{upload_id}/resume")
def resume_upload(
    upload_id: str,
    _current_user: User = Depends(get_current_user),
):
    return success_response({"upload_id": upload_id, "resumed": True, "offset": 0}, "断点续传已就绪")


@router.post("/import/external")
def import_external(
    body: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    source_type = body.get("source_type", "filesystem")
    source_path = body.get("source_path", "")
    if not source_path:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="source_path 不能为空")

    result = dataset_service.import_from_external(
        db,
        name=body.get("name", f"import-{source_type}"),
        data_type=body.get("data_type", "text"),
        owner_id=current_user.id,
        source_type=source_type,
        source_path=source_path,
        description=body.get("description"),
        version=body.get("version", "v1.0.0"),
    )
    ds = result["dataset"]
    db.refresh(ds)
    log_service.create_log(
        db, user_id=current_user.id, username=current_user.username,
        action="import", resource="dataset", resource_id=ds.id,
        detail=f"从 {source_type}:{source_path} 导入 {result['imported_files']} 个文件",
    )
    return success_response({
        "dataset": DatasetOut.model_validate(ds).model_dump(),
        "imported_files": result["imported_files"],
        "total_size": result["total_size"],
        "errors": result["errors"],
    }, "外部数据导入成功")


@router.get("/processing-jobs")
def list_processing_jobs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    _current_user: User = Depends(get_current_user),
):
    jobs, total = dataset_repository.get_processing_jobs(page=page, page_size=page_size)
    return paginated_response(jobs, total, page, page_size)


@router.get("/processing-jobs/{job_id}")
def get_processing_job(
    job_id: str,
    _current_user: User = Depends(get_current_user),
):
    job = dataset_repository.get_processing_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="处理任务不存在")
    return success_response(job)


# ============================================================================
# 数据集 CRUD — 动态路径 {dataset_id}
# ============================================================================


@router.get("")
def list_datasets(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: str = Query(""),
    data_type: str = Query(""),
    quality_status: str = Query(""),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    datasets, total = dataset_repository.get_datasets(
        db, page=page, page_size=page_size,
        keyword=keyword, data_type=data_type, quality_status=quality_status,
    )
    return paginated_response(
        [DatasetListOut.model_validate(d) for d in datasets], total, page, page_size
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_dataset(
    body: DatasetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ds = dataset_repository.create_dataset(
        db,
        name=body.name,
        data_type=body.data_type,
        owner_id=current_user.id,
        description=body.description,
        version=body.version,
        source=body.source,
        storage_path=body.storage_path,
        file_count=body.file_count,
        total_size=body.total_size,
    )
    log_service.create_log(
        db, user_id=current_user.id, username=current_user.username,
        action="create", resource="dataset", resource_id=ds.id,
        detail=f"创建数据集 {ds.name}",
    )
    return success_response(DatasetOut.model_validate(ds), "数据集创建成功")


@router.get("/{dataset_id}")
def get_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    ds = dataset_repository.get_dataset_by_id(db, dataset_id)
    if ds is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="数据集不存在")
    return success_response(DatasetOut.model_validate(ds))


@router.put("/{dataset_id}")
def update_dataset(
    dataset_id: int,
    body: DatasetUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ds = dataset_repository.get_dataset_by_id(db, dataset_id)
    if ds is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="数据集不存在")
    ds = dataset_repository.update_dataset(db, ds, **body.model_dump(exclude_unset=True))
    log_service.create_log(
        db, user_id=current_user.id, username=current_user.username,
        action="update", resource="dataset", resource_id=ds.id,
        detail=f"修改数据集 {ds.name}",
    )
    return success_response(DatasetOut.model_validate(ds), "数据集修改成功")


@router.delete("/{dataset_id}")
def delete_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ds = dataset_repository.get_dataset_by_id(db, dataset_id)
    if ds is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="数据集不存在")
    dataset_repository.delete_dataset(db, ds)
    log_service.create_log(
        db, user_id=current_user.id, username=current_user.username,
        action="delete", resource="dataset", resource_id=dataset_id,
        detail=f"删除数据集 {ds.name}",
    )
    return success_response(message="数据集删除成功")


@router.post("/{dataset_id}/preprocess")
def start_preprocess(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ds = dataset_repository.get_dataset_by_id(db, dataset_id)
    if ds is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="数据集不存在")
    job = dataset_service.start_preprocess(db, ds)
    log_service.create_log(
        db, user_id=current_user.id, username=current_user.username,
        action="preprocess", resource="dataset", resource_id=ds.id,
        detail=f"启动预处理任务 {job['job_id']}",
    )
    return success_response(job, "预处理任务已启动")


# ============================================================================
# 质量 & 血缘
# ============================================================================


@router.get("/{dataset_id}/quality")
def get_quality_report(
    dataset_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    ds = dataset_repository.get_dataset_by_id(db, dataset_id)
    if ds is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="数据集不存在")
    return success_response(dataset_service.check_quality(db, ds))


@router.post("/{dataset_id}/quality/check")
def trigger_quality_check(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ds = dataset_repository.get_dataset_by_id(db, dataset_id)
    if ds is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="数据集不存在")
    report = dataset_service.check_quality(db, ds)
    log_service.create_log(
        db, user_id=current_user.id, username=current_user.username,
        action="quality_check", resource="dataset", resource_id=ds.id,
        detail=f"质量校验数据集 {ds.name}",
    )
    return success_response(report, "质量校验完成")


@router.post("/{dataset_id}/quality/repair")
def trigger_quality_repair(
    dataset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ds = dataset_repository.get_dataset_by_id(db, dataset_id)
    if ds is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="数据集不存在")
    result = dataset_service.repair_quality(db, ds)
    log_service.create_log(
        db, user_id=current_user.id, username=current_user.username,
        action="quality_repair", resource="dataset", resource_id=ds.id,
        detail=f"修复数据集 {ds.name}",
    )
    return success_response(result, "数据修复完成")


@router.get("/{dataset_id}/lineage")
def get_lineage(
    dataset_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    ds = dataset_repository.get_dataset_by_id(db, dataset_id)
    if ds is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="数据集不存在")
    return success_response(dataset_service.get_lineage(db, ds))


@router.get("/{dataset_id}/lineage/impact")
def get_lineage_impact(
    dataset_id: int,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    ds = dataset_repository.get_dataset_by_id(db, dataset_id)
    if ds is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="数据集不存在")
    return success_response(dataset_service.get_lineage_impact(db, ds))
