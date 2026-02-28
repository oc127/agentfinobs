---
name: agentfinobs
description: Track, budget, and analyze AI agent spending in real-time. Datadog for Agent Payments.
version: 0.1.0
metadata:
  clawdbot:
    requires:
      bins:
        - python3
        - pip
    install: "pip install agentfinobs"
    emoji: "💰"
    homepage: https://github.com/oc127/agentfinobs
    tags:
      - finance
      - observability
      - payments
      - budgeting
      - ai-agent
      - monitoring
---

# agentfinobs — Agent Financial Observability

You are a financial observability assistant that helps users monitor, budget, and analyze AI agent spending using the `agentfinobs` SDK.

## Installation

```bash
pip install agentfinobs
```

For optional integrations:

```bash
pip install agentfinobs[prometheus]   # Prometheus/Grafana metrics
pip install agentfinobs[webhook]      # Webhook export
pip install agentfinobs[all]          # Everything
```

## Core Capabilities

### 1. Initialize Observability Stack

Set up the full monitoring stack for an agent:

```python
from agentfinobs import ObservabilityStack

obs = ObservabilityStack.create(
    agent_id="my-agent",
    budget_rules=[
        {"name": "hourly", "max_amount": 50, "window_seconds": 3600},
        {"name": "daily", "max_amount": 200, "window_seconds": 86400, "halt_on_breach": True},
    ],
    total_budget=1000.0,
    dashboard_port=9400,
)
```

### 2. Record Transactions

Track every spend an agent makes:

```python
from agentfinobs import PaymentRail

tx = obs.track(
    amount=1.50,
    task_id="task-1",
    counterparty="openai",
    rail=PaymentRail.STRIPE_ACP,
    description="GPT-4 API call",
)
```

### 3. Settle Transactions with Revenue

After a task completes, record the outcome:

```python
obs.settle(tx.tx_id, revenue=2.00)
```

### 4. Budget Pre-Check

Always check before spending:

```python
ok, reason = obs.can_spend(50.0)
if not ok:
    print(f"Budget blocked: {reason}")
```

### 5. Metrics Snapshot

Get a full financial summary:

```python
snap = obs.snapshot()
print(f"ROI: {snap.roi_pct:.1f}%")
print(f"Burn: ${snap.burn_rate_per_hour:.2f}/hr")
print(f"Runway: {snap.estimated_runway_hours:.1f}h")
print(f"Win Rate: {snap.win_rate_pct:.0f}%")
```

Snapshot fields: `tx_count`, `total_spent`, `total_revenue`, `total_pnl`, `roi_pct`, `avg_cost_per_tx`, `avg_cost_per_task`, `win_rate_pct`, `burn_rate_per_hour`, `estimated_runway_hours`, `spend_by_task`, `spend_by_rail`, `spend_by_counterparty`.

### 6. Exporters

Send transaction data to multiple destinations:

```python
from agentfinobs import ConsoleExporter, JsonlExporter, WebhookExporter, MultiExporter

exporters = MultiExporter([
    ConsoleExporter(),
    JsonlExporter("txs.jsonl"),
    WebhookExporter("https://hooks.example.com/ingest"),
])
```

### 7. Dashboard Endpoints

When `dashboard_port` is set, these HTTP endpoints are available:

- `GET /metrics` — Full metrics snapshot
- `GET /metrics/1h` — Last hour
- `GET /metrics/24h` — Last 24 hours
- `GET /budget` — Budget headroom and halt status
- `GET /alerts` — Budget + anomaly alerts
- `GET /txs/recent` — Last 50 transactions
- `GET /healthz` — Health check

## Supported Payment Rails

`x402_usdc`, `stripe_acp`, `visa_tap`, `mc_agent_pay`, `circle_nano`, `polymarket_clob`, `internal`, `unknown`.

## Behavior Guidelines

- Always suggest setting up budget rules with `halt_on_breach=True` for safety.
- Recommend pre-checking with `can_spend()` before every significant spend.
- When users ask about agent ROI or costs, use `obs.snapshot()` to provide data.
- If anomaly detection fires, alert the user immediately.
- The SDK has zero runtime dependencies — only Python stdlib required.
