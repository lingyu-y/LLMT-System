"""Clair 镜像漏洞扫描服务 — 真实 Clair API + 模拟兜底。"""

import base64
import random
import uuid
from datetime import datetime, timezone
from urllib.parse import quote

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings

# 模拟漏洞数据库
CVE_DATABASE = [
    {
        "cve_id": "CVE-2024-45490",
        "severity": "Critical",
        "pkg_name": "libexpat1",
        "pkg_version": "2.2.10",
        "fixed_version": "2.4.1",
        "description": "libexpat 中 XML 解析存在缓冲区溢出，攻击者可通过构造恶意 XML 触发远程代码执行。",
        "fix_suggestion": "升级 libexpat1 到 2.4.1 或更高版本，或应用发行版安全补丁。",
    },
    {
        "cve_id": "CVE-2024-6387",
        "severity": "High",
        "pkg_name": "openssh-server",
        "pkg_version": "8.9p1",
        "fixed_version": "9.2p1",
        "description": "OpenSSH 信号处理存在竞态条件，未经认证的远程攻击者可导致任意代码执行(regreSSHion)。",
        "fix_suggestion": "升级 openssh-server 到 9.2p1+，或配置 LoginGraceTime 0。",
    },
    {
        "cve_id": "CVE-2024-5535",
        "severity": "High",
        "pkg_name": "libcurl4",
        "pkg_version": "7.81.0",
        "fixed_version": "7.88.1",
        "description": "libcurl 中 HTTP/2 流量处理存在越界读取，可导致信息泄露或服务拒绝。",
        "fix_suggestion": "升级 libcurl4 到 7.88.1+。",
    },
    {
        "cve_id": "CVE-2024-38077",
        "severity": "Critical",
        "pkg_name": "python3.10",
        "pkg_version": "3.10.12",
        "fixed_version": "3.10.14",
        "description": "Python 的 zipfile 模块存在路径遍历，攻击者可通过恶意 ZIP 覆盖任意文件。",
        "fix_suggestion": "升级 Python 到 3.10.14+ 或 3.11.9+。",
    },
    {
        "cve_id": "CVE-2024-25062",
        "severity": "Medium",
        "pkg_name": "libxml2",
        "pkg_version": "2.9.14",
        "fixed_version": "2.11.5",
        "description": "libxml2 在解析大型 XML 文档时存在资源耗尽，可导致 DoS。",
        "fix_suggestion": "升级 libxml2 到 2.11.5+。",
    },
    {
        "cve_id": "CVE-2024-32002",
        "severity": "Medium",
        "pkg_name": "git",
        "pkg_version": "2.34.1",
        "fixed_version": "2.39.3",
        "description": "Git 递归克隆包含符号链接的子模块时可触发代码执行。",
        "fix_suggestion": "升级 git 到 2.39.3+，或禁止递归克隆不受信任的仓库。",
    },
    {
        "cve_id": "CVE-2024-28182",
        "severity": "Low",
        "pkg_name": "libpng16-16",
        "pkg_version": "1.6.37",
        "fixed_version": "1.6.40",
        "description": "libpng 在特定条件下存在整数溢出，可导致信息泄露。",
        "fix_suggestion": "升级 libpng16-16 到 1.6.40+。",
    },
    {
        "cve_id": "CVE-2024-3094",
        "severity": "Critical",
        "pkg_name": "xz-utils",
        "pkg_version": "5.4.1",
        "fixed_version": "5.4.6",
        "description": "xz-utils 被发现植入后门(XZ Backdoor)，影响 sshd 认证流程。",
        "fix_suggestion": "降级到 5.4.0 或升级到 5.4.6+ 安全版本。",
    },
]


def simulate_clair_scan(model_code: str, model_version: str) -> list[dict]:
    """模拟 Clair 从镜像仓库拉取层信息 → 分析软件包 → 查询漏洞数据库。"""
    rng = random.Random(f"{model_code}-{model_version}")
    count = rng.randint(3, len(CVE_DATABASE))
    vulns = rng.sample(CVE_DATABASE, count)
    severity_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    return sorted(vulns, key=lambda v: severity_order.get(v["severity"], 99))


def _find_image_ref(model, override: str | None = None) -> str | None:
    meta = model.hyperparams_json or {}
    return (
        override
        or meta.get("image_ref")
        or meta.get("container_image")
        or meta.get("docker_image")
        or get_settings().CLAIR_DEFAULT_IMAGE_REF
    )


def _parse_image_ref(image_ref: str) -> tuple[str, str, str]:
    """Parse registry/repository/reference from an OCI image reference."""
    if "://" in image_ref:
        image_ref = image_ref.split("://", 1)[1]
    first, _, rest = image_ref.partition("/")
    if not rest:
        registry = "registry-1.docker.io"
        remainder = f"library/{first}"
    elif "." in first or ":" in first or first == "localhost":
        registry = first
        remainder = rest
    else:
        registry = "registry-1.docker.io"
        remainder = image_ref

    if "@" in remainder:
        repository, reference = remainder.rsplit("@", 1)
    elif ":" in remainder.rsplit("/", 1)[-1]:
        repository, reference = remainder.rsplit(":", 1)
    else:
        repository, reference = remainder, "latest"
    return registry, repository, reference


def _registry_headers() -> dict[str, str]:
    settings = get_settings()
    headers = {
        "Accept": ", ".join([
            "application/vnd.oci.image.manifest.v1+json",
            "application/vnd.docker.distribution.manifest.v2+json",
            "application/vnd.oci.image.index.v1+json",
            "application/vnd.docker.distribution.manifest.list.v2+json",
        ]),
    }
    if settings.CLAIR_REGISTRY_AUTH_HEADER:
        headers["Authorization"] = settings.CLAIR_REGISTRY_AUTH_HEADER
    elif settings.CLAIR_REGISTRY_USERNAME and settings.CLAIR_REGISTRY_PASSWORD:
        raw = f"{settings.CLAIR_REGISTRY_USERNAME}:{settings.CLAIR_REGISTRY_PASSWORD}".encode()
        headers["Authorization"] = f"Basic {base64.b64encode(raw).decode()}"
    return headers


def _resolve_manifest(image_ref: str) -> dict:
    """Resolve an image reference into the Clair Manifest object."""
    settings = get_settings()
    registry, repository, reference = _parse_image_ref(image_ref)
    scheme = settings.CLAIR_REGISTRY_SCHEME or "https"
    base = f"{scheme}://{registry}/v2/{repository}"
    timeout = settings.CLAIR_SCAN_TIMEOUT_SECONDS

    with httpx.Client(timeout=timeout, verify=not settings.CLAIR_REGISTRY_INSECURE, trust_env=False) as client:
        manifest_url = f"{base}/manifests/{quote(reference, safe=':')}"
        response = client.get(manifest_url, headers=_registry_headers())
        response.raise_for_status()
        manifest_digest = response.headers.get("Docker-Content-Digest") or reference
        manifest = response.json()

        media_type = manifest.get("mediaType", "")
        if "manifest.list" in media_type or "image.index" in media_type:
            manifests = manifest.get("manifests") or []
            if not manifests:
                raise RuntimeError("镜像 manifest list 为空")
            manifest_digest = manifests[0]["digest"]
            response = client.get(f"{base}/manifests/{manifest_digest}", headers=_registry_headers())
            response.raise_for_status()
            manifest = response.json()

    layers = []
    auth_headers = {}
    auth_value = _registry_headers().get("Authorization")
    if auth_value:
        auth_headers = {"Authorization": [auth_value]}
    for layer in manifest.get("layers", []):
        digest = layer.get("digest")
        if not digest:
            continue
        layer_obj = {
            "hash": digest,
            "uri": f"{base}/blobs/{quote(digest, safe=':')}",
        }
        if auth_headers:
            layer_obj["headers"] = auth_headers
        layers.append(layer_obj)

    if not layers:
        raise RuntimeError("镜像没有可扫描的 layers")

    return {"hash": manifest_digest, "layers": layers}


def _clair_headers(kind: str) -> dict[str, str]:
    if kind == "index":
        return {
            "Content-Type": "application/vnd.clair.manifest.v1+json",
            "Accept": "application/vnd.clair.index_report.v1+json",
        }
    return {"Accept": "application/vnd.clair.vulnerability_report.v1+json"}


def _severity(value: str | None) -> str:
    normalized = (value or "").lower()
    if normalized in {"critical", "crit"}:
        return "Critical"
    if normalized in {"high", "important"}:
        return "High"
    if normalized in {"medium", "moderate"}:
        return "Medium"
    if normalized in {"low", "negligible"}:
        return "Low"
    return "Medium"


def _normalize_clair_report(report: dict) -> list[dict]:
    vulnerabilities = report.get("vulnerabilities") or {}
    packages = report.get("packages") or {}
    package_vulns = report.get("package_vulnerabilities") or {}
    rows: list[dict] = []

    for package_key, vuln_ids in package_vulns.items():
        package = packages.get(package_key) or {}
        for vuln_id in vuln_ids:
            vuln = vulnerabilities.get(vuln_id) or {}
            fixed_in = vuln.get("fixed_in_version") or vuln.get("fixed_in") or ""
            rows.append({
                "cve_id": vuln.get("name") or vuln_id,
                "severity": _severity(vuln.get("normalized_severity") or vuln.get("severity")),
                "pkg_name": package.get("name") or package_key,
                "pkg_version": package.get("version") or "",
                "fixed_version": fixed_in or "请参考发行版安全公告",
                "description": vuln.get("description") or vuln.get("issued") or "Clair 未返回详细描述",
                "fix_suggestion": f"升级 {package.get('name') or package_key} 到修复版本 {fixed_in}" if fixed_in else "请升级基础镜像或应用发行版安全补丁",
            })

    severity_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    return sorted(rows, key=lambda v: severity_order.get(v["severity"], 99))


def run_clair_scan(image_ref: str) -> list[dict]:
    """Call Clair v4 API to index an image and retrieve vulnerabilities."""
    settings = get_settings()
    manifest = _resolve_manifest(image_ref)
    clair = settings.CLAIR_API_URL.rstrip("/")
    timeout = settings.CLAIR_SCAN_TIMEOUT_SECONDS
    with httpx.Client(timeout=timeout, trust_env=False) as client:
        index_response = client.post(
            f"{clair}/indexer/api/v1/index_report",
            json=manifest,
            headers=_clair_headers("index"),
        )
        index_response.raise_for_status()
        digest = (index_response.json().get("manifest_hash") or manifest["hash"])

        report_response = client.get(
            f"{clair}/matcher/api/v1/vulnerability_report/{quote(digest, safe=':')}",
            headers=_clair_headers("report"),
        )
        report_response.raise_for_status()
        return _normalize_clair_report(report_response.json())


def compute_risk_score(vulns: list[dict]) -> int:
    """根据漏洞数量和严重程度计算安全风险评分 (0-100，越高越安全)。"""
    weights = {"Critical": 30, "High": 15, "Medium": 5, "Low": 2}
    penalty = sum(weights.get(v["severity"], 0) for v in vulns)
    return max(0, 100 - penalty)


def check_alert(vulns: list[dict]) -> list[dict]:
    """检查是否存在 Critical / High 高危漏洞，生成告警。"""
    return [v for v in vulns if v["severity"] in ("Critical", "High")]


def run_security_scan(
    db: Session,
    model,
    *,
    triggered_by: str = "admin",
    image_ref: str | None = None,
) -> dict:
    """执行完整的安全扫描流程并持久化结果。"""

    settings = get_settings()
    resolved_image_ref = _find_image_ref(model, image_ref)
    scanner = "simulated"
    scan_error = None
    if settings.CLAIR_SCAN_ENABLED and resolved_image_ref:
        try:
            vulns = run_clair_scan(resolved_image_ref)
            scanner = "clair"
        except Exception as exc:
            scan_error = str(exc)
            if not settings.CLAIR_SIMULATION_FALLBACK:
                raise RuntimeError(f"Clair真实扫描失败: {scan_error}") from exc
            vulns = simulate_clair_scan(model.model_code, model.version)
    else:
        vulns = simulate_clair_scan(model.model_code, model.version)

    # Step 6: 风险评估
    score = compute_risk_score(vulns)

    # Step 7: 生成报告（JSON，后续可渲染为 HTML/PDF）
    scan_id = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc).isoformat()
    summary = {
        "total": len(vulns),
        "critical": sum(1 for v in vulns if v["severity"] == "Critical"),
        "high": sum(1 for v in vulns if v["severity"] == "High"),
        "medium": sum(1 for v in vulns if v["severity"] == "Medium"),
        "low": sum(1 for v in vulns if v["severity"] == "Low"),
    }

    report = {
        "scan_id": scan_id,
        "scanned_at": now,
        "model_code": model.model_code,
        "version": model.version,
        "scanner": scanner,
        "image_ref": resolved_image_ref,
        "scan_error": scan_error,
        "score": score,
        "summary": summary,
        "vulnerabilities": vulns,
    }

    # Step 8: 高危漏洞自动告警
    alerts = check_alert(vulns)

    # Step 9: 保存到数据库 (hyperparams_json)
    existing = model.hyperparams_json or {}
    scans = existing.get("security_scans", [])
    scans.append(report)
    # 只保留最近 10 次扫描
    if len(scans) > 10:
        scans = scans[-10:]
    model.hyperparams_json = {**existing, "security_scans": scans}
    db.commit()

    # 记录操作日志
    try:
        from app.services import log_service
        log_service.create_log(
            db, user_id=None, username=triggered_by,
            action="security_scan", resource="model_version", resource_id=model.id,
            detail=(
                f"对 {model.model_code}:{model.version} 执行安全扫描"
                f"({scanner})，评分 {score}，发现 {summary['critical']} 严重 / {summary['high']} 高危"
                + (f"，Clair错误: {scan_error}" if scan_error else "")
            ),
        )
        for alert_v in alerts:
            log_service.create_log(
                db, user_id=None, username=triggered_by,
                action="security_alert", resource="model_version", resource_id=model.id,
                detail=f"[{alert_v['severity']}] {alert_v['cve_id']}: {alert_v['pkg_name']} {alert_v['pkg_version']} → {alert_v['fixed_version']}",
            )
    except Exception:
        pass

    return {
        "scan_id": scan_id,
        "scanned_at": now,
        "scanner": scanner,
        "image_ref": resolved_image_ref,
        "scan_error": scan_error,
        "score": score,
        "summary": summary,
        "vulnerabilities": vulns,
        "alerts_triggered": len(alerts),
    }
