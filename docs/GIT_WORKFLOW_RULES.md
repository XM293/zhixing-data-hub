# 知行数枢 · Git 研发与版本管理规范
> **版本**：v1.0.0 (2026-09-17)  
> **适用主体**：知行数枢（Zhixing Data Hub）代码仓库所有协作者与 AI 辅助开发助手。

---

## 一、代码托管与仓库身份

1. **托管平台与归属**：
   - 托管服务：GitHub (Private Repository)
   - 官方命名空间：`XM293/zhixing-data-hub`
   - 统一 SSH 仓库地址：`git@github.com:XM293/zhixing-data-hub.git`
   - 统一 HTTPS 仓库地址：`https://github.com/XM293/zhixing-data-hub.git`
2. **Git 提交身份基准**：
   - 用户名 (Name)：`XM293`
   - 提交邮箱 (Email)：`lonedream@foxmail.com`
   - 本地仓库配置命令：
     ```bash
     git config --local user.name "XM293"
     git config --local user.email "lonedream@foxmail.com"
     ```

---

## 二、分支与版本管理策略

本项目采用以 `main` 为稳定主干的主干开发（Trunk-based Development）与短生命周期特性分支相结合的敏捷策略：

```text
main (生产就绪基线，永远保持可编译、测试全绿)
  ├── feature/twin-assistant (特性功能开发分支)
  ├── fix/reconciliation-tolerance (缺陷修复分支)
  └── docs/knowledge-update (文档与标准更新)
```

1. **主干保护（`main` 分支）**：
   - `main` 为受控核心分支，代表当前随时可在测试机/生产机部署的稳定版本；
   - 严禁在测试未通过、存在编译报错（TypeScript 报错或 Python 语法错）的状态下推送到 `main`；
2. **特性分支命名约定**：
   - `feat/<模块名>-<简短动作>`：例如 `feat/twin-drawer-ux`
   - `fix/<缺陷模块>-<修复点>`：例如 `fix/ai-provider-404`
   - `docs/<主题>`：例如 `docs/project-knowledge-base`
3. **里程碑打标（Tagging）**：
   - 凡是达成阶段性业务交付（如第一阶段上线、第二阶段对账闭环、第三阶段分身激活），均以语义化版本打标：
     ```bash
     git tag -a v0.1.0-m0 -m "M0 阶段基线达成：星云铁皮柜11个月对账与AI分身激活"
     git push origin --tags
     ```

---

## 三、Commit 提交信息标准（规范化语义提交）

统一遵循业界标准 Conventional Commits 规范，方便历史追溯与自动化变更日志生成：

| 类型前缀 | 适用场景 | 示例 |
| :--- | :--- | :--- |
| **`feat`** | 新增业务功能或核心页面 | `feat(twin): 接入自建 gpt-6-astra 原生 responses 协议` |
| **`fix`** | 修复业务逻辑或运行期缺陷 | `fix(reconciliation): 统一 0.5% 容差对账计算口径` |
| **`docs`** | 仅修改文档、注释或基线文件 | `docs(baseline): 新增 PROJECT_KNOWLEDGE_BASE 事实源` |
| **`style`** | 代码格式调整，不影响逻辑 | `style(web): 优化 3D 画布与驾驶舱布局层叠样式` |
| **`refactor`** | 代码重构，无功能新增或缺陷修复 | `refactor(api): 抽象 AIProvider 路由与协议降级容灾` |
| **`test`** | 新增或修复测试用例 | `test(knowledge): 补充 DeepSeek 结构化输出单测` |
| **`chore`** | 构建配置、依赖、工具链更新 | `chore(git): 配置 XM293 提交身份与 .gitignore 规则` |

---

## 四、代码安全与敏感信息过滤铁律（Zero Secret Leaks）

为防止企业真实秘钥泄露到公共网络，执行最高级别秘钥隔离策略：

1. **绝对禁止提交的内容**：
   - 本地环境配置文件：`.env`、`.env.*`（仅允许提交脱敏模板 `.env.example`）；
   - 任何云数据库账号密码、API Key（如 `sk-...`）、私钥证书（`*.pem`, `*.key`）；
   - 本地运行时数据库文件：`services/api/var/*.db*`；
   - 本地构建与依赖目录：`node_modules/`、`.next/`、`.venv/`、`dist/`、`output/`、`outputs/`。
2. **预检守则**：
   - 每次执行 `git add` 与 `git commit` 前，必须检查 `git status`，确保无未受控敏感文件误入暂存区。

---

## 五、AI 辅助编程（Antigravity 2.0）Git 执行守则

AI 智能体在参与代码管理时，恪守以下工程操守：
1. **测试前置**：在提交代码前，优先执行 `vitest` 与 `pytest` 确认代码无破坏性改动。
2. **提交自洁**：提交前核对 `git diff`，清理调试用的临时文件或临时注释。
3. **回溯保障**：若后续业务迭代出现重大异常，利用清晰的 commit 记录执行 `git revert` 或 `git reset` 安全回滚到上一稳定检查点。
