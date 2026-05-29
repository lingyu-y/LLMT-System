# LLMT-System 测试说明

## 测试范围

本次补充的测试以 `LLMT-backend` 为主，覆盖课程项目核心流程：

- 单元测试：密码/JWT、数据文件校验、训练参数校验、模型版本校验、文档类型校验。
- 模块测试：数据上传、训练任务创建、模型版本管理、文档生成、系统用户和权限管理。
- 集成测试：登录权限、数据集到训练任务、训练任务到模型注册、模型到文档生成。
- 系统测试：通过后端 API 模拟登录、数据处理、训练任务、模型查询、文档生成和异常访问流程。

前端已识别为 Vue + Vite + Pinia 项目，目前未引入 Vitest/Playwright 依赖；系统级流程先用后端 API 测试模拟，避免额外依赖安装。

## 测试环境

- Python 环境：conda `llmt-backend`
- 后端测试框架：pytest + FastAPI TestClient
- 数据库：测试时使用 SQLite 文件库 `LLMT-backend/tests/_pytest_llmt.db`
- 外部依赖：MinIO、Celery/Redis、InfluxDB、Elasticsearch、GPU 训练和大模型推理均使用 mock 或最小桩对象
- Node 环境：前端项目要求 Node `^20.19.0 || >=22.12.0`，本次未新增前端测试依赖

## 运行命令

在仓库根目录：

```bash
conda activate llmt-backend
pytest LLMT-backend/tests
```

也可以按测试类型运行：

```bash
pytest LLMT-backend/tests/unit
pytest LLMT-backend/tests/module
pytest LLMT-backend/tests/integration
pytest LLMT-backend/tests/system
```

如果已经进入 `LLMT-backend` 目录，则运行：

```bash
pytest tests/unit tests/module tests/integration tests/system
```

## 测试用例概览

| 测试类型 | 测试对象 | 测试内容 | 测试文件 |
|---|---|---|---|
| 单元测试 | 安全与参数校验函数 | 密码校验、Token 校验、文件类型、训练参数、模型版本、文档类型 | `LLMT-backend/tests/unit/test_validation_helpers.py` |
| 模块测试 | 数据处理模块 | 合法文本上传、非法格式、存储错误 | `LLMT-backend/tests/module/test_dataset_training_model_document_system.py` |
| 模块测试 | 模型训练模块 | 合法任务创建、非法参数、未预处理数据集拒绝 | `LLMT-backend/tests/module/test_dataset_training_model_document_system.py` |
| 模块测试 | 模型管理模块 | 版本列表、版本创建、版本回滚 | `LLMT-backend/tests/module/test_dataset_training_model_document_system.py` |
| 模块测试 | 文档生成模块 | 模型列表、mock 推理生成、非法文档类型 | `LLMT-backend/tests/module/test_dataset_training_model_document_system.py` |
| 模块测试 | 系统管理模块 | 用户查询、角色修改、普通用户拒绝访问 | `LLMT-backend/tests/module/test_dataset_training_model_document_system.py` |
| 集成测试 | 登录 + 权限 | 登录后菜单权限、普通用户不能访问系统管理 | `LLMT-backend/tests/integration/test_cross_module_flows.py` |
| 集成测试 | 数据处理 + 模型训练 | API 创建数据集后被训练任务引用，缺失数据集失败 | `LLMT-backend/tests/integration/test_cross_module_flows.py` |
| 集成测试 | 训练 + 模型管理 | 训练任务完成后注册模型版本，回滚前校验版本存在 | `LLMT-backend/tests/integration/test_cross_module_flows.py` |
| 集成测试 | 文档生成 + 模型管理 | 文档生成读取当前模型信息，模型不可用返回错误提示 | `LLMT-backend/tests/integration/test_cross_module_flows.py` |
| 系统测试 | 主业务流程 | 登录、数据集列表、训练任务创建、任务查询、模型查询、文档生成、用户信息 | `LLMT-backend/tests/system/test_api_business_flows.py` |
| 系统测试 | 异常业务流程 | 未登录、越权、非法训练参数、缺失数据集、非法上传 | `LLMT-backend/tests/system/test_api_business_flows.py` |
