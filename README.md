# OKX AI Trader

ai-trade-in-okx 集成okx api，通过ai策略进行自动化交易，支持永续合约交易。

## 功能特性

-  **AI自动交易**: 基于技术因子的AI决策系统
-  **手动交易**: Web界面手动下单和管理持仓
-  **实时数据**: WebSocket实时价格和账户数据推送
-  **多账户管理**: 支持多个OKX账户管理
-  **永续合约**: 支持BTC、ETH、SOL等主流币种永续合约
-  **数据持久化**: PostgreSQL存储交易记录和账户数据
-  **交易监控**: 实时监控持仓、订单和交易历史

## 技术栈

### 后端
- **FastAPI**: 高性能API服务
- **CCXT**: 加密货币交易所API统一接口
- **SQLAlchemy**: ORM数据库操作
- **PostgreSQL**: 生产级数据库
- **WebSocket**: 实时数据推送

### 前端
- **React 18**: 现代化UI框架
- **TypeScript**: 类型安全
- **Vite**: 快速构建工具
- **Tailwind CSS**: 实用优先的CSS框架
- **Recharts**: 数据可视化

## 快速开始

### 环境要求

- Node.js 18+
- Python 3.10+
- PostgreSQL 12+
- PNPM 包管理器

### 安装步骤

1. **克隆项目**
```bash
git clone https://github.com/machsh64/open-alpha-trade-in-okx.git
cd open-alpha-trade-in-okx
```

2. **启用PNPM**
```bash
corepack enable pnpm
```

3. **安装依赖**
```bash
pnpm install:all
```

4. **配置环境变量**

在 `backend/` 目录创建 `.env` 文件：

```env
# 数据库配置
DATABASE_URL=postgresql://username:password@ip:port/ai-trade

# AI交易配置（可选）
AI_TRADE_INTERVAL=1800  # AI交易检查间隔（秒），默认1800（30分钟）

# 代理配置（可选）：
# PROXY_URL=http://127.0.0.1:7890

# 其他可选配置
# 默认交易对类型 (spot: 现货, swap: 永续合约)
DEFAULT_TRADING_TYPE=swap

# 日志级别
LOG_LEVEL=INFO
```

5. **初始化数据库**
```bash
cd backend
uv run python init_database.py
```

6. **启动服务**

开发模式（同时启动前后端）所有环境通用：
```bash
pnpm dev
```

或分别启动：
```bash
# 仅后端 (端口 5611)
# Windows
pnpm run dev:backend:win

# Linux/Mac
pnpm run dev:backend:unix

# 仅前端 (端口 5621)
pnpm run dev:frontend
```

**注意**: 
- 项目使用内置的Python环境（`.conda/`目录），**无需额外安装Python**
- 首次运行前确保执行了 `pnpm install:all`
- 启动脚本会自动查找项目Python环境

7. **访问应用**

打开浏览器访问: http://localhost:5621

## 项目架构模式
### v-1.0.0 AI交易架构
```mermaid
flowchart TD

subgraph A["数据输入层"]
  A1["交易所 api<br/>(价格、深度、成交、Funding Rate 等)"]
  A2["新闻与舆情接口"]
  A3["账户与持仓状态"]
  A4["最近交易数据及决策原因"]
end

subgraph B["指标监控层"]
  B1["实时指标计算<br/>(RSI、波动率、价格变化、MACD 等)"]
  B2["阈值检测器<br/>检测上阈/下阈"]
  B3["事件订阅控制<br/>触发AI调用"]
end

subgraph C["自适应调度器"]
  C1["周期计时器<br/>默认12分钟"]
end

subgraph D["AI决策引擎"]
  D1["上下文拼接器<br/>(行情 + 持仓 + 账户 + 决策历史)"]
  D2["Prompt生成器"]
  D3["AI模型调用<br/>(Qwen / GPT / DeepSeek)"]
  D4["结构化输出解析器<br/>JSON决策结果"]
end

subgraph E["风险控制与执行"]
  E1["风控审查器<br/>(限额 / 滑点 / 杠杆 / 熔断)"]
  E2["订单执行器<br/>(REST / WebSocket)"]
  E3["执行结果回写<br/>日志与状态"]
end

subgraph F["状态存储与反馈"]
  F2["数据库<br/>交易记录与决策日志"]
end

A1 --> B1
A2 --> B1
A3 --> B1
A4 --> B1
B1 --> B2
B2 -->|指标上阈触发| C1
C1 -->|周期到达| D1
D1 --> D2
D2 --> D3
D3 --> D4
E3 --> F2
F2 --> D1
D4 --> E1
E1 --> E2
E2 --> E3
```

### v-2.0.0 将要拓展的 自适应AI交易调度架构
```mermaid
flowchart TD

%% ===================== A. 数据输入层 =====================
subgraph A[数据输入层]
  A1["交易所WS\n价格·深度·成交·Funding"]
  A2["新闻与舆情接口"]
  A3["账户与持仓状态"]
  A4["最近交易数据及决策原因"]
end

%% ===================== B. 指标监控层 =====================
subgraph B[指标监控层]
  B1["实时特征与指标计算 
    RSI·波动率·价格变化·盘口不平衡"]
  B2["阈值与迟滞检测
    上阈与下阈 双阈 Hysteresis"]
  B4["显著度评分器
    score 0到1"]
  B3["事件总线与优先队列
    合并 Grace Window 15到30秒 与 去重"]
end

%% ===================== C. 自适应调度器 =====================
subgraph C[自适应调度器]
  C1["长周期计时器
    默认12分钟"]
  C2["短周期计时器
    5分钟模式"]
  C3["周期管理器
    边沿触发→短周期
    回落稳定→长周期"]
  C4["冷却与幂等
    Idempotency Key·TTL·合并策略"]
  C5["预算与限流
    并发·QPS·费用·超时"]
end

%% ===================== L. Letta-AI 服务（中间层） =====================
subgraph L[Letta-AI 服务]
  L1["Core Memory策略原则·风控红线·输出规范"]
  L2["Episodic Memory
    往期交易与理由
    会话级临时记忆"]
  L3["Prompt 模板与工具
    由 Letta 统一管理"]
  L4["模型路由
    model_id 与 后端模型地址"]
end

%% ===================== D. 决策适配器（本地） =====================
subgraph D[AI 决策适配器]
  D1["上下文封装器
    把 行情·账户·持仓·新闻
    封成 单轮消息"]
  D2["Letta API 客户端
    传入 session_id 与 model_id
    仅单轮对话"]
  D3["结构化输出校验
    严格 JSON Schema 解析"]
end

%% ===================== E. 风控与执行 =====================
subgraph E[风险控制与执行]
  E1["风控审查
    限额·滑点·仓位暴露·跨所价差·熔断"]
  E2["订单执行
    条件单·保护单 触发价·超时撤单"]
  E3["执行结果回写
    订单·拒单原因·延迟"]
end

%% ===================== F. 状态存储与反馈 =====================
subgraph F[状态存储与反馈]
  F1["Redis 缓存
    指标快照·周期状态·冷却与幂等键"]
  F2["数据库 或 ES 或 ClickHouse
    交易记录·决策日志·审计可重放"]
  F3["周期恢复逻辑
    指标回落稳定→恢复12分钟"]
end

%% ===================== G. 观测与灰度 =====================
subgraph G[观测与灰度发布]
  G1["影子与灰度开关
    按品种与时段控制权重"]
  G2["可观测性仪表盘
    触发来源占比·响应时延·拒单Top5·影子vs实盘"]
  G3["全局熔断控制
    日内最大回撤超阈→冷静期"]
end

%% ===== 数据流 =====
A1 --> B1
A2 --> B1
A3 --> B1
A4 --> B1

B1 --> B2
B2 --> B4
B4 --> B3

C1 -- "周期到达" --> B3
B3 -- "高优先 Up·Down·Spike" --> C3
B3 -- "定时事件" --> C3

C3 --> C4
C4 --> C5
C3 -- "触发AI 或 切短周期" --> D1
C2 -- "短周期触发" --> D1

%% 本地仅封装与调用 Letta
D1 --> D2
D2 --> L4
L1 --> L3
L2 --> L3
L3 --> L4
L4 --> D2
D2 --> D3
D3 --> E1 --> E2 --> E3

%% 回写与记忆
E3 --> F1
E3 --> F2
F1 --> B1
F1 --> C3

%% 把结果事实写回 Letta 作为记忆（通过 D2 再次调用 Letta 的记忆接口或同会话消息）
E3 -. "结果与理由 写入会话记忆" .-> D2

%% 观测与灰度
E3 --> G2
D3 --> G2
G1 --> E2
G1 --> C5
G3 --> C3
G3 --> C1

%% 恢复逻辑
F2 -. "复盘与审计重放" .-> D1
F3 -. "回落稳定→恢复12分钟" .-> C3
```

## 项目结构

```
.
├── backend/                  # 后端服务
│   ├── api/                 # API路由
│   │   ├── okx_account_routes.py    # OKX账户API
│   │   ├── order_routes.py          # 订单管理
│   │   └── ws.py                    # WebSocket
│   ├── config/              # 配置文件
│   ├── database/            # 数据库连接和模型
│   ├── factors/             # 技术因子
│   ├── repositories/        # 数据访问层
│   ├── schemas/             # 数据模型
│   ├── services/            # 业务逻辑
│   │   ├── okx_market_data.py       # OKX市场数据
│   │   ├── auto_trader.py           # AI自动交易
│   │   └── order_executor.py        # 订单执行
│   ├── main.py              # FastAPI主入口
│   └── models.py            # SQLAlchemy模型
│
├── frontend/                # 前端应用
│   ├── app/
│   │   ├── components/      # React组件
│   │   │   ├── trading/     # 交易界面
│   │   │   ├── portfolio/   # 资产组合
│   │   │   └── layout/      # 布局组件
│   │   ├── lib/             # 工具函数和API
│   │   └── main.tsx         # 应用入口
│   └── vite.config.ts       # Vite配置
│
├── package.json             # 工作区配置
├── pnpm-workspace.yaml      # PNPM工作区
└── README.md               # 本文件
```

## 使用说明

### 手动交易

1. 点击左侧导航栏的 **Trade** 按钮
2. 选择交易对（BTC-USDT-SWAP, ETH-USDT-SWAP等）
3. 输入交易数量
4. 选择订单类型（市价/限价）
5. 点击 **Buy** 或 **Sell** 按钮下单

### AI自动交易

系统会定期运行AI决策引擎分析市场，在 **Arena** 页面可以查看：
- AI决策记录
- 持仓情况
- 订单历史
- 资产曲线

**AI交易特点**：
-  **检查频率**: 默认每30分钟检查一次市场（可通过环境变量 `AI_TRADE_INTERVAL` 调整）
-  **保守策略**: AI采用保守策略，**不会每次检查都交易**，只在有明确信号时才执行
-  **决策因素**: 基于市场价格、持仓情况、新闻资讯等多维度分析
- ️ **风险控制**: 
  - 单次交易不超过总资产的5-20%
  - 倾向于选择 `hold`（不交易）而非频繁操作
  - 避免过度集中单一币种

**调整AI交易频率**：

在 `backend/.env` 文件中添加：
```env
# AI交易检查间隔（秒）
AI_TRADE_INTERVAL=1800  # 30分钟（默认）
# AI_TRADE_INTERVAL=3600  # 1小时
# AI_TRADE_INTERVAL=7200  # 2小时
```

**注意**: 即使设置为30分钟检查一次，AI也经常会选择 `hold`（不交易），实际交易频率会更低。

### OKX账户查看

点击 **OKX** 按钮查看：
- 账户余额
- 当前持仓
- 未成交订单
- 历史交易记录

## 支持的交易对

- BTC-USDT-SWAP 
- ETH-USDT-SWAP 
- SOL-USDT-SWAP 
- DOGE-USDT-SWAP 
- XRP-USDT-SWAP 
- ADA-USDT-SWAP 
- AVAX-USDT-SWAP
- DOT-USDT-SWAP
- MATIC-USDT-SWAP 
- LTC-USDT-SWAP 

## 重要参数说明

### OKX永续合约参数

- **posSide**: 持仓方向
  - `long`: 做多（buy订单）
  - `short`: 做空（sell订单）

- **tdMode**: 交易模式
  - `cross`: 全仓模式（默认）
  - `isolated`: 逐仓模式

### 符号格式转换

系统自动处理以下格式转换：
- 输入: `BTC-USDT-SWAP` → 转换为: `BTC/USDT:USDT`
- 输入: `ETH-USDT-SWAP` → 转换为: `ETH/USDT:USDT`

## 开发命令

```bash
# 安装依赖
pnpm install
pnpm install:all

# 开发模式
pnpm dev

# 仅后端
pnpm run dev:backend

# 仅前端
pnpm run dev:frontend

# 构建生产版本
pnpm run build

# Python代码格式化
uv run black backend

# Python代码检查
uv run ruff check backend

# 运行测试
uv run pytest backend/tests
```

## 测试脚本

```bash
cd backend

# 测试数据库连接
uv run python test_db_connection.py

# 测试OKX账户
uv run python test_okx_account.py

# 测试OKX价格获取
uv run python test_okx_price.py

# 测试符号格式转换
uv run python test_symbol_format.py

# 测试WebSocket连接
uv run python test_websocket.py
```

## 常见问题

### 1. 数据库连接失败

检查 `.env` 文件中的 `DATABASE_URL` 是否正确，确保PostgreSQL服务运行中。

### 2. OKX API错误

- 检查API密钥是否正确
- 确认API权限包含交易权限
- 沙盒环境和生产环境的密钥不同

### 3. WebSocket连接失败

确保后端服务运行在 `http://localhost:5611`，前端会自动连接 `ws://localhost:5611/ws`。

### 4. 下单失败

- 检查账户余额是否充足
- 确认交易对格式正确（如 `BTC-USDT-SWAP`）
- 查看后端日志了解具体错误

## 安全建议

⚠️ **重要安全提示**

1. **不要提交 `.env` 文件到git**
2. **生产环境使用独立的API密钥**
3. **限制API密钥权限（只开启交易权限）**
4. **定期更换API密钥**
5. **启用OKX的IP白名单**
6. **小额测试后再大额交易**

## 许可证

MIT License

## 贡献

欢迎提交Issue和Pull Request！

## 联系方式

如有问题请提交Issue或联系项目维护者。

## 风险说明
任何使用本项目进行的交易行为均由使用者自行承担风险。加密货币市场波动较大，投资需谨慎。

---

**免责声明**: 本项目仅供学习和研究使用，使用本系统进行实盘交易的风险由使用者自行承担。加密货币交易存在高风险，可能导致资金损失。
