"""Clair 镜像漏洞扫描服务 — 模拟分析 + 风险评估 + 告警。"""

import random
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

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


def compute_risk_score(vulns: list[dict]) -> int:
    """根据漏洞数量和严重程度计算安全风险评分 (0-100，越高越安全)。"""
    weights = {"Critical": 30, "High": 15, "Medium": 5, "Low": 2}
    penalty = sum(weights.get(v["severity"], 0) for v in vulns)
    return max(0, 100 - penalty)


def check_alert(vulns: list[dict]) -> list[dict]:
    """检查是否存在 Critical / High 高危漏洞，生成告警。"""
    return [v for v in vulns if v["severity"] in ("Critical", "High")]


def run_security_scan(db: Session, model, *, triggered_by: str = "admin") -> dict:
    """执行完整的安全扫描流程并持久化结果。"""

    # Step 1-5: 模拟 Clair 分析 + 生成 CVE 清单
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
            detail=f"对 {model.model_code}:{model.version} 执行安全扫描，评分 {score}，发现 {summary['critical']} 严重 / {summary['high']} 高危",
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
        "score": score,
        "summary": summary,
        "vulnerabilities": vulns,
        "alerts_triggered": len(alerts),
    }
