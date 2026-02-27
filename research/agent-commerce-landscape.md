# Agent Commerce 全景地图

> 研究日期: 2026-02-27
> 目标: 打通 Agent Payment / Agent Marketplace / Agent Price Discovery 三个方向的逻辑关系

---

## 一、全局架构：Agent Commerce 的七层协议栈

```
┌─────────────────────────────────────────────────────────────────────┐
│  Layer 7: APPLICATION                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │ ChatGPT 购物  │  │ Agent 采购系统 │  │ Agent↔Agent  │              │
│  │ (B2C)        │  │ (B2B)        │  │ 交易市场      │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 6: PRICE DISCOVERY (❌ 最大空白)                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │ Agent 议价协议 │  │ 预测市场式    │  │ Agent-native  │              │
│  │              │  │ 质量定价      │  │ 拍卖机制      │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 5: COMMERCE PROTOCOL                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │ ACP (OpenAI  │  │ UCP (Google  │  │ Shopify/     │              │
│  │  + Stripe)   │  │  + Walmart)  │  │ commercetools│              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 4: PAYMENT RAILS                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐           │
│  │ x402     │  │ ACP/SPT  │  │ Visa TAP │  │ MC Agent │           │
│  │ (USDC)   │  │ (Stripe) │  │ (Card)   │  │ Pay(Card)│           │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘           │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 3: IDENTITY & TRUST (⚠️ 关键缺失)                            │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │ ERC-8004     │  │ Visa TAP     │  │ Skyfire KYA  │              │
│  │ (链上身份)    │  │ (可信代理)    │  │ (企业级)      │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 2: AGENT COMMUNICATION                                       │
│  ┌──────────────┐  ┌──────────────┐                                │
│  │ MCP          │  │ A2A          │                                │
│  │ (Agent↔Tool) │  │ (Agent↔Agent)│                                │
│  └──────────────┘  └──────────────┘                                │
├─────────────────────────────────────────────────────────────────────┤
│  Layer 1: SETTLEMENT                                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐              │
│  │ Base/Polygon │  │ Circle Arc   │  │ 传统银行/    │              │
│  │ (L2)        │  │ (专用L1)     │  │ 卡组织       │              │
│  └──────────────┘  └──────────────┘  └──────────────┘              │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 二、付款方式：三条轨道对比

### 2.1 传统卡轨道

| 方案 | 做法 | 状态 | 局限 |
|------|------|------|------|
| **Visa Intelligent Commerce** | Agent Token（受限凭证），代人类在接受 Visa 的商户消费 | 100+ 合作伙伴，30+ 在沙箱中 | 人类预授权，不适合高频微支付 |
| **Mastercard Agent Pay** | Agentic Token，类似思路 | 全美开放，2026/02 扩展拉美 | 同上 |
| **PayOS** | 同时接入 Visa + MC，发放 network-issued Agent Token | 2025/09 完成首笔 MC Agent 支付 | 依赖卡组织 |

### 2.2 Crypto 原生轨道（最 Agent-Native）

| 方案 | 做法 | 状态 | 优势 |
|------|------|------|------|
| **x402** | HTTP 402 + USDC 链上支付，嵌入 HTTP 协议本身 | 100M+ 支付，35M+ Solana 交易 | 支付 = HTTP 请求，天然微支付 |
| **Stripe x402** | PaymentIntents API + USDC on Base | 2026/02 Preview | 传统 Stripe 商户无缝接入 |
| **Circle Gateway** | 跨链统一 USDC 余额，<500ms | 主网上线 | 链抽象，agent 不需要关心在哪条链 |
| **Circle Nanopayments** | 免 gas USDC 转账，最小 $0.000001 | 2026/02 私有测试 | 真正的纳米级微支付 |
| **Circle Arc** | USDC 为原生 gas 的专用 L1 | 测试网 | 为稳定币金融定制的链 |
| **Skyfire** | 企业存 USD → 自动转 USDC → agent 钱包 | 已退出 beta | 企业友好的法币入口 |

### 2.3 平台闭环

| 方案 | 做法 | 状态 |
|------|------|------|
| **OpenAI ACP** | ChatGPT 内购物，Stripe 结算，4% 平台费 | 上线（Etsy, 即将 Shopify 100万+ 商户）|
| **Google AP2** | 三层授权，可审计 | 上线 |
| **Amazon Buy for Me** | Agent 在 Amazon 内完成购买 | 上线 |

### 关键洞察

```
传统卡:    人 → 授权 → Agent 拿 Token → 消费（人的系统，agent 适配）
x402:     Agent → HTTP 请求 → 402 → 签名支付 → 交付（原生为机器设计）
平台闭环:  Agent → 平台内 → 平台规则 → 结算（围墙花园）
```

**最大机会：跨轨道路由层** — 一个 agent 不应该关心"用什么付"，而是有一个智能路由层自动选择最便宜/最快的支付方式。目前没人做这个。

---

## 三、购物平台：从"人的平台"到 "Agent-Native 平台"

### 3.1 现有平台的 Agent 化进程

| 平台 | Agent 策略 | 关键能力 |
|------|-----------|---------|
| **Shopify** | 所有商店默认暴露 MCP 端点 `/api/mcp` | Storefront MCP, Global Cart（跨店结算）, MCP-UI |
| **commercetools** | 无头架构 + Commerce MCP | 模块化 API，支持 OpenAI SDK/LangChain/CrewAI |
| **Amazon** | Buy for Me（闭环） | 利用现有巨大商品目录 |
| **OpenAI** | Instant Checkout（ACP + Stripe） | ChatGPT 内直接购买 |

### 3.2 Agent-Native 市场：已存在的

| 项目 | 类型 | 特点 |
|------|------|------|
| **Nevermined** | 基础设施 | 实时计量 + 即时结算，支持 A2A/MCP/x402 |
| **Molt Road** | 纯 Agent 市场 | 无人类账户，只有 agent 可以注册/买卖，USDC 链上托管 |
| **Vercel Marketplace** | 开发者 + Agent | Agent 和 Service 两类，统一计费 |
| **Payman AI** | Agent→人类 | Agent 付钱给人类做任务（反向市场）|

### 3.3 重新设计的维度

**现有平台为什么不适合 Agent？**

```
问题 1: HTML/图片/营销文案 → Agent 不需要"看"
问题 2: 反爬虫/验证码       → Agent 就是 bot
问题 3: 非结构化数据        → Agent 要解析 HTML
问题 4: 人类身份体系        → Agent 没有"手指"点击
问题 5: 人类速度定价        → Agent 可以毫秒级决策
```

**Agent-Native 平台的设计原则：**

1. **API-First** — 无 UI，全 JSON/GraphQL，结构化商品目录
2. **Machine-Readable Catalog** — JSON-LD / Schema.org，不是网页
3. **Agent Identity (KYA)** — Agent 有自己的身份、信用、权限
4. **Programmatic Pricing** — 价格不是"标签"，而是 API 返回的动态值
5. **Outcome-Contingent** — 支付可以基于结果（交付质量）而非预付
6. **Protocol-Native** — 内置 MCP/A2A/ACP/x402，不是后期集成

---

## 四、价格发现：最大的空白地带

### 4.1 现状

| 领域 | 成熟度 | 谁在做 |
|------|--------|--------|
| Agent 议价协议 | 早期生产 | Google UCP, Virtuals Protocol, Keelvar |
| 预测市场→通用商品 | 概念阶段 | **没人做** |
| Agent 动态定价 | 增长期 | MARL 研究者, Wendy's, ESL 零售商 |
| Agent 原生拍卖 | 改装阶段 | Keelvar, Procol（企业采购）|
| DeFi 机制映射 | 活跃开发 | DeFAI 生态（$1B+）|

### 4.2 Polymarket → 通用商品价格发现

**Polymarket 的核心机制：**
```
CLOB (Central Limit Order Book) + Conditional Tokens (ERC-1155)
P_YES + P_NO = $1.00 → 任何偏离 = 套利机会
价格 = 概率 = 市场对信息的集体判断
```

**映射到商品/服务定价：**

```
Polymarket:  "事件发生的概率" → 价格
Commerce:    "服务按时按质交付的概率" → 价格

例如：
  - Vendor A 的按时交付概率 = 0.95 → 你愿意付 $95/$100
  - Vendor B 的按时交付概率 = 0.70 → 你只愿意付 $70/$100

  → 市场自动发现"质量调整后的公平价格"
```

**没人做的事：** 一个基于条件代币的通用服务市场，agent 交易"供应商 X 能按约交付"的概率代币。这是预测市场最大的未开发应用。

### 4.3 DeFi 机制 → Agent 商务的映射

| DeFi 概念 | Agent Commerce 对应 | 机会 |
|-----------|---------------------|------|
| AMM (x*y=k) | 标准化服务的自动定价（计算、存储、带宽）| 服务流动性池 |
| CLOB 订单簿 | 差异化服务的买卖撮合 | Agent 服务交易所 |
| 集中流动性 | Agent 专注于特定价格/质量区间 | 精细化服务分层 |
| 预言机 (Oracle) | 验证服务交付质量的外部数据 | 质量证明系统 |
| Flash Loan | "先试后买"的服务承诺（不满意自动回滚）| 零风险试用 |
| 套利 | 跨平台价格差异利用 | **你已经在做这个！**|
| am-AMM | 拍卖 + AMM 混合机制 | 最佳价格发现 |

### 4.4 关键洞察：Polymarket 自身的演进

```
Polymarket v1: AMM → 流动性好但价格发现差
Polymarket v2: CLOB → 价格发现好但需要做市商
教训: 不同市场结构需要不同机制
  - 标准化服务 → AMM（简单、自动）
  - 差异化服务 → CLOB（精确、灵活）
  - 混合场景   → am-AMM（两者结合）
```

---

## 五、市场规模与时间线

| 预测 | 来源 | 数字 |
|------|------|------|
| Agent Commerce 全球市场 | McKinsey | **$3-5T by 2030** |
| AI Agent 驱动的 B2B 采购 | Gartner | **$15T by 2028** |
| 美国 Agent 电商 | Morgan Stanley | **$190-385B by 2030** |
| AI Agent 市场规模 | 行业分析 | $7.84B (2025) → **$52.62B (2030)** |
| Agent 市场需求 | 行业预测 | **$47B in next 5 years** |
| DeFAI 市场 | 当前 | **$1B+** |

**时间线：**
```
2025: 协议年 — x402, ACP, A2A, TAP, AP2 全部发布
2026: 部署年 — 主流商业落地（Visa 预测2026节假日百万级用户）
2027: 整合年 — 协议竞争胜出者出现
2028: 规模年 — 33% 企业软件含 agentic AI (Gartner)
2030: 成熟年 — 万亿级市场
```

---

## 六、最大的 8 个空白（创业机会）

### 空白 1: 🔴 跨协议支付路由层
**问题**: x402, ACP, Visa TAP, MC Agent Pay, AP2 互不兼容
**机会**: 一个智能路由层，agent 发起支付 → 自动选最优轨道
**类比**: 像 Plaid 统一了银行 API，这里需要统一 agent 支付协议
**难度**: ★★★★☆

### 空白 2: 🔴 通用价格发现协议
**问题**: 所有协议都解决了通信和支付，但没人解决"公平价格怎么来"
**机会**: 基于预测市场/条件代币的服务定价市场
**类比**: 从 Polymarket（事件概率）→ 通用服务（交付概率）
**难度**: ★★★★★（最难也最大）

### 空白 3: 🟡 Agent 身份 + 信用系统
**问题**: 没有跨平台的 agent 身份标准，信用不可移植
**机会**: 开放的 KYA 系统，链上信用评分
**现有**: ERC-8004（24000+ agent 注册），但没有统一搜索/验证
**难度**: ★★★☆☆

### 空白 4: 🟡 争议解决 + 托管协议
**问题**: x402 无退款，ACP 依赖传统退款，agent 间交易无仲裁
**机会**: Agent 原生的托管 + 争议解决协议
**类比**: 像 Klarna 的"先买后付"但为 agent 设计
**难度**: ★★★☆☆

### 空白 5: 🟡 Agent 金融可观测性 ("Datadog for Agent Payments")
**问题**: 没有工具监控 agent 集群的支出、ROI、异常
**机会**: 实时仪表盘 — 每个 agent 的花费、成本/任务、预算消耗率
**难度**: ★★☆☆☆（相对简单，可以快速切入）

### 空白 6: 🟡 法币 On/Off Ramp for Agents
**问题**: 企业财务系统是法币，agent 世界是 USDC，桥接很痛苦
**机会**: Agent 原生的财务管理层（法币入金→自动转换→agent 消费→结算回法币）
**现有**: Natural.co ($9.8M seed) 在做 B2B，但通用方案缺失
**难度**: ★★★☆☆

### 空白 7: 🟠 条件代币式服务市场
**问题**: 没人用预测市场机制来定价服务质量
**机会**: "付 $X IF 质量指标 Y 达标" — 条件代币 + 质量预言机
**你的优势**: 你已经理解 Polymarket 的条件代币 + CLOB
**难度**: ★★★★☆

### 空白 8: 🟠 多 Agent 金融协调
**问题**: 多个 agent 协作购买时，如何分摊成本、管理共享预算
**机会**: 共享钱包、层级支出策略、agent 间结算
**难度**: ★★★☆☆

---

## 七、从 Polymarket Arb Bot 出发的自然延伸路径

```
你现在有的:
  ✅ 链上交易经验 (Polygon/Base)
  ✅ 条件代币理解 (Gnosis CTF / ERC-1155)
  ✅ CLOB 机制理解
  ✅ 套利逻辑 (跨市场价差捕捉)
  ✅ Agent 自主决策
  ✅ DeFi 协议交互

自然延伸路径:

  Step 1: Polymarket 套利 Bot
     │
     ▼
  Step 2: 跨预测市场套利 (Polymarket ↔ 其他平台)
     │
     ▼
  Step 3: 预测市场机制 → 服务质量定价
     │  "事件概率" → "交付概率"
     ▼
  Step 4: Agent-Native 服务市场
     │  条件代币 + CLOB + 质量预言机
     ▼
  Step 5: 通用 Agent Commerce 基础设施
     │  支付路由 + 身份 + 价格发现
     ▼
  Step 6: Agent Economy 操作系统
```

---

## 八、竞争格局总结

### 巨头在做什么

| 公司 | 策略 | 你能切入的缝隙 |
|------|------|----------------|
| **Stripe** | ACP + x402，成为 "agent 支付的默认 PSP" | 他们不做价格发现 |
| **Visa** | TAP + VIC，保住卡组织地位 | 他们只做卡轨道 |
| **Coinbase** | x402 + CDP，成为 crypto agent 支付基础设施 | 他们不做商务逻辑 |
| **Circle** | USDC + Gateway + Arc + Nanopayments | 结算层，不做应用层 |
| **OpenAI** | ACP + ChatGPT Checkout，控制 agent 入口 | 围墙花园，不开放 |
| **Google** | A2A + AP2 + UCP，协议标准制定者 | 他们擅长定标准但不擅长产品化 |
| **Shopify** | MCP 端点 + Global Cart，agent 化最积极的电商 | 他们是平台，不是基础设施 |

### 创业公司在做什么

| 公司 | 融资 | 做什么 | 空白 |
|------|------|--------|------|
| **Skyfire** | $9.5M | 企业级 agent 支付网络 | 只做支付，不做发现 |
| **PayOS** | Stealth | 卡原生 agent 支付 | 只做卡轨道 |
| **Natural.co** | $9.8M | B2B agentic 支付工作流 | 垂直领域，不做通用 |
| **Payman AI** | $13.8M | Agent 付钱给人类 | 单向（agent→人）|
| **Nevermined** | — | Agent 计量 + 结算 | 不做价格发现 |
| **Molt Road** | — | 纯 Agent 市场 | 安全/合规问题 |

### 没人在做的

```
❌ 跨协议支付路由
❌ 通用价格发现协议
❌ 预测市场式服务定价
❌ Agent 金融可观测性
❌ 条件代币式服务市场
❌ Agent 间议价公平性层
```

---

## 九、关键数据点

- x402: 100M+ 支付已处理, 98.7% 是 USDC
- USDC 流通: $75.3B (YoY +72%)
- USDC 链上季度交易量: $11.9T (YoY +247%)
- Circle 2025 营收: $2.7B
- AI Agent 驱动的零售流量增长: 4,700% (Visa)
- Agentic 流量 8 个月增长: 6,900%
- ChatGPT 日购物查询: 50M+
- Polymarket 2025 交易量: $44B+
- Polymarket 套利利润 (2024/04-2025/04): $40M
- 只有 29% 英国消费者信任 AI 支付
- 只有 16% 美国消费者信任 agent 支付
- 62% 消费者认为动态定价 = 价格欺诈
- 80% 金融机构预计 agent 商务将增加欺诈
- Gartner: 40% agentic AI 项目将在 2027 前取消（可靠性差距）
- McKinsey: AI 推荐转化率高 4.4x，但 agent 商务比联盟流量转化低 86%

---

## 十、Sources

### Payment Infrastructure
- [x402.org](https://www.x402.org/)
- [x402 V2 Launch](https://www.x402.org/writing/x402-v2-launch)
- [DWF Labs x402 Deep Dive](https://www.dwf-labs.com/research/inside-x402-how-a-forgotten-http-code-becomes-the-future-of-autonomous-payments)
- [Coinbase x402 GitHub](https://github.com/coinbase/x402)
- [Stripe x402 Integration](https://www.theblock.co/post/389352/stripe-adds-x402-integration-usdc-agent-payments)
- [Stripe ACP Blog](https://stripe.com/blog/developing-an-open-standard-for-agentic-commerce)
- [Circle Gateway](https://www.circle.com/blog/circle-gateway-redefining-crosschain-ux)
- [Circle Nanopayments](https://mpost.io/circle-expands-usdc-infrastructure-with-nanopayments-launch-aiming-at-ai-agents-and-digital-payments/)
- [Circle Arc L1](https://www.circle.com/blog/introducing-arc-an-open-layer-1-blockchain-purpose-built-for-stablecoin-finance)
- [Skyfire Payment Network](https://skyfire.xyz/)
- [PayOS + Visa + MC](https://www.globenewswire.com/news-release/2025/04/30/3071744/0/en/PayOS-Teams-Up-with-Mastercard-and-Visa-Intelligent-Commerce-Emerges-From-Stealth-to-Power-AI-Driven-Payments.html)
- [Payman AI](https://paymanai.com/)
- [Natural.co Seed Round](https://www.businesswire.com/news/home/20251023151615/en/Fintech-Natural-Launches-With-$9.8M-Seed-Round-to-Power-Agentic-Payments)

### Marketplace & Commerce
- [OpenAI Agentic Commerce](https://developers.openai.com/commerce/)
- [ACP GitHub](https://github.com/agentic-commerce-protocol/agentic-commerce-protocol)
- [Google A2A Protocol](https://developers.googleblog.com/en/a2a-a-new-era-of-agent-interoperability/)
- [Google AP2](https://cloud.google.com/blog/products/ai-machine-learning/announcing-agents-to-payments-ap2-protocol)
- [Shopify MCP Integration](https://www.francescatabor.com/articles/2025/8/14/shopify-and-the-model-context-protocol-mcp-in-e-commerce)
- [commercetools Commerce MCP](https://commercetools.com/commerce-platform/commerce-mcp)
- [Agent-Native: Shopify vs commercetools](https://composable.com/insights/agent-native-commerce-shopify-vs-commercetools)
- [Gartner Machine Customers](https://www.gartner.com/en/articles/prepare-for-the-future-of-ai-powered-customers)
- [McKinsey Agentic Commerce](https://www.mckinsey.com/capabilities/quantumblack/our-insights/the-agentic-commerce-opportunity-how-ai-agents-are-ushering-in-a-new-era-for-consumers-and-merchants)
- [Nevermined Agent Monetization](https://nevermined.ai/blog/ai-agent-monetization-strategies)
- [Visa Trusted Agent Protocol](https://investor.visa.com/news/news-details/2025/Visa-Introduces-Trusted-Agent-Protocol-An-Ecosystem-Led-Framework-for-AI-Commerce/default.aspx)
- [ERC-8004 Agent Identity](https://blog.onfinality.io/erc-8004/)

### Price Discovery & Negotiation
- [Stanford HAI: Art of Automated Negotiation](https://hai.stanford.edu/news/the-art-of-the-automated-negotiation)
- [IEEE Spectrum: AI Contract Negotiations](https://spectrum.ieee.org/ai-contracts)
- [Polymarket CLOB Docs](https://docs.polymarket.com/developers/CLOB/introduction)
- [am-AMM Paper (Springer)](https://link.springer.com/chapter/10.1007/978-3-032-07024-1_6)
- [DeFAI Explained (Ledger)](https://www.ledger.com/academy/topics/defi/defai-explained-how-ai-agents-are-transforming-decentralized-finance)
- [MARL Dynamic Pricing](https://arxiv.org/html/2507.02698v1)
- [LLM Negotiation Games](https://arxiv.org/abs/2411.05990)
- [Agent-Based Modeling in Economics](https://www.aeaweb.org/articles?id=10.1257/jel.20221319)
- [Prediction Markets 2025 (a16z)](https://a16zcrypto.com/posts/podcast/prediction-markets-explained/)
- [Sequoia: Agent Economy Foundations](https://inferencebysequoia.substack.com/p/the-agent-economy-building-the-foundations)
