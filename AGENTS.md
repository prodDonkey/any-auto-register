# any-auto-register 仓库规范

## 适用范围

- 本文件适用于仓库根目录 `/Users/yaohongliang/work/liuyao/github/AI-Account-Toolkit/any-auto-register`
- 在本仓库内工作时，优先遵循本文件，再遵循上层通用规范

## 第一原则

- 尽可能不要破坏现有项目结构
- 尽可能不要为了实现单个需求做大范围重构
- 优先做小步、可验证、可回退的改动
- 非必要不要引入新层级、新框架、新状态管理方案

## 项目结构约定

```
account_manager/
├── main.py                 # FastAPI 入口
├── api/                    # HTTP 接口层
├── core/                   # 基础设施 / 通用能力
├── platforms/              # 平台插件层
├── services/               # 后台服务
└── frontend/               # React 前端
```

### 放置规则

- 通用能力放 `core/`
  例如：共享配置读取、通用第三方平台接入、跨平台调度逻辑、复用工具模块
- HTTP 路由放 `api/`
  新增接口时优先新建独立路由文件，再在 `main.py` 挂载
- 平台专属逻辑放 `platforms/<platform>/`
  仅该平台会用到的注册、校验、切换、token 组装逻辑才放这里
- 后台进程或长期运行服务放 `services/`
- 前端页面与交互放 `frontend/src/pages/`

### 明确限制

- 不要把“多个平台都会复用”的能力继续堆在 `platforms/chatgpt/` 里
- 如果一个能力未来大概率会被 Cursor、Kiro、Trae、Grok 等复用，应优先抽到 `core/`
- 不要把复杂业务逻辑直接塞进 `main.py`
- 不要把大量业务判断直接塞进前端页面组件；前端主要负责展示、收集参数和调用接口

## 配置相关约定

- 全局配置统一走 `api/config.py` + `core/config_store.py`
- 新增配置项时，至少同步修改：
  - `api/config.py` 中的 `CONFIG_KEYS`
  - 前端设置页 `frontend/src/pages/Settings.tsx`
- 敏感字段按现有方式处理，不要把真实密钥硬编码进源码

## 前端改动约定

- 尽量沿用现有 `Settings.tsx`、`Accounts.tsx`、`Register.tsx` 的页面结构和交互风格
- 小功能优先接入现有页面，不轻易新开路由
- 如果只是设置项扩展，优先在现有设置页增加独立页签或卡片，不要重新设计整套设置系统
- 保持现有深色主题、按钮样式、提示样式一致
- 修改前端后，默认需要执行 `frontend` 构建验证

## 后端改动约定

- 新增接口尽量保持返回结构稳定、直白
- 新的通用集成能力优先提供：
  - 一个核心函数
  - 一个薄的 API 路由包装
- 调度逻辑优先复用 `core/scheduler.py` 现有线程，不额外引入新的常驻进程，除非必要

## 平台插件约定

- `platforms/<platform>/plugin.py` 负责平台适配，不承担过多通用逻辑
- `get_platform_actions()` 返回的平台操作应尽量轻量
- `execute_action()` 中如果要用到跨平台能力，优先调用 `core/` 中的通用模块

## 运行与验证命令

### 后端

```bash
.venv/bin/python3 -m uvicorn main:app --port 8000
```

### 前端构建

```bash
cd frontend
npm run build
```

### Python 基础验证

```bash
python -m compileall api core platforms
```

## 提交规范

- 提交信息使用中文
- 推荐使用简短中文 Conventional Commit 风格，例如：
  - `feat: 增加独立 Sub2Api 配置页`
  - `fix: 修复 Sub2Api 同步请求体为空问题`
  - `refactor: 抽离通用 Sub2Api 能力到 core`
- 一次提交尽量只做一类事情
- 不要把无关格式化、顺手重构、临时调试改动混进同一个提交

## 数据与敏感信息

- 不要提交真实密钥、Bearer Token、管理员密码
- 不要提交运行时临时数据，除非用户明确要求
- `account_manager.db`、`data/tokens/` 下内容默认视为运行数据，谨慎处理

## 工作方式

- 先看现有实现，再动手
- 优先复用现有模块，不重复造轮子
- 改动完成后，至少做一项可执行验证
- 如果修改了前端页面，优先补一次 `npm run build`
- 如果修改了 Python 模块，优先补一次 `compileall`
