# LLMT Frontend

离线大数据训练与应用系统前端，基于 Vue 3、TypeScript、Vite、Pinia、Vue Router、Element Plus 和 ECharts 开发。

## 环境要求

- Node.js：`^20.19.0 || >=22.12.0`
- 包管理器：npm

## 启动开发

```sh
npm install
npm run dev
```

默认开发服务由 Vite 启动。后端接口通过 `vite.config.ts` 中的代理转发：

```ts
/api -> http://127.0.0.1:8000
```

前端接口默认基地址在 `src/api/http.ts`：

```ts
const API_BASE = import.meta.env.VITE_API_BASE_URL ?? '/api/v1'
```

本地联调时一般保持默认即可，也就是前端请求 `/api/v1/*`，由 Vite 代理到后端 FastAPI 服务。

## 常用命令

```sh
npm run dev          # 启动开发环境
npm run build        # 类型检查并打包
npm run type-check   # 只做类型检查
npm run lint         # 运行 oxlint 和 eslint 自动修复
npm run format       # 格式化 src 目录
npm run preview      # 预览生产构建结果
```

## 目录说明

```text
src/main.ts          应用入口，注册 Pinia、Router、Element Plus 和全局样式
src/App.vue          根组件，承载 router-view
src/router           路由配置和登录/权限守卫
src/stores           Pinia 状态管理，目前核心是 auth store
src/api              所有后端接口封装
src/views            业务页面
src/components       通用组件
src/layouts          系统主布局
src/styles           全局样式和变量
src/utils            工具函数
src/mock             演示数据和前端兜底权限配置
```

## 接口联调入口

所有请求都会经过 `src/api/http.ts`：

- 自动拼接 `/api/v1`
- 自动携带 `Authorization: Bearer token`
- 自动处理 JSON 请求头
- 请求失败时抛出 `ApiError`
- 对 `{ message, data }` 结构可使用 `unwrap()` 取出 `data`

业务接口按模块拆分：

```text
src/api/auth.ts       登录、注册、当前用户
src/api/dashboard.ts  仪表盘
src/api/datasets.ts   数据集、上传、质量、血缘
src/api/training.ts   模型训练任务
src/api/models.ts     模型管理、版本、安全扫描、限流
src/api/inference.ts  在线推理
src/api/documents.ts  文档生成、草稿、下载
src/api/system.ts     用户、角色、菜单、日志
src/api/federated.ts  联邦学习
src/api/resources.ts  GPU 等资源信息
```

新增接口时，优先在对应 `src/api/*.ts` 文件里封装，再在页面组件中调用。

## 权限和路由

路由配置在 `src/router/index.ts`。页面权限通过 `meta.menuKeys` 控制：

```ts
meta: { title: '模型训练', menuKeys: ['training'] }
```

全局导航守卫会：

1. 拦截未登录用户访问业务页面。
2. 已登录用户访问登录/注册页时跳转仪表盘。
3. 根据当前用户菜单权限决定是否允许进入页面。

登录态和权限集中在 `src/stores/auth.ts`：

- `isLoggedIn`：是否已登录
- `visibleMenuKeys`：当前用户可见菜单
- `hasPermission()`：判断是否有单个菜单权限
- `hasAnyPermission()`：判断是否拥有任一菜单权限

## 页面模块

```text
Dashboard.vue          仪表盘
DataProcessing.vue     数据处理，包含上传、质量检查、血缘分析
ModelTraining.vue      模型训练，包含任务创建、日志、指标、checkpoint
FederatedLearning.vue  联邦学习
ModelManagement.vue    模型管理，包含版本、扫描、推理测试、限流
DocGeneration.vue      文档生成和草稿管理
SystemManagement.vue   用户、角色、菜单、系统日志
MyLogs.vue             当前用户操作日志
Login.vue              登录
Register.vue           注册
Forbidden.vue          403 无权限页
```

## 开发注意

- 接口返回结构不完全统一，使用 `unwrap()` 前先确认后端是否返回 `{ message, data }`。
- 上传接口使用 `XMLHttpRequest` 获取进度，不走普通 `fetch` 封装。
- 训练、联邦学习、数据预处理属于长任务，页面通常需要轮询状态、日志或指标。
- 权限展示不要只靠页面按钮隐藏，路由层也要配置对应 `menuKeys`。
- `src/mock` 中的数据主要用于演示或兜底，真实联调应优先看 `src/api` 和后端 `/api/v1`。
