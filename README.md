# Cloudera Blueprint: AI Governance with NVIDIA NeMo Guardrails

## Table of Contents

- [Overview](#overview)
- [Demo](#demo)
- [Use Case](#use-case)
- [Key Features](#key-features)
- [Quickstart](#quickstart--guide)
- [Architecture / Software Components](#architecture--software-components)
- [Target Audience](#target-audience)
- [Repository Structure](#repository-structure)
- [Prerequisites](#prerequisites)
- [Hardware Requirements](#hardware-requirements)
- [Documentation](#documentation)

## Overview

This blueprint puts enterprise safety controls around a generative-AI banking assistant on Cloudera AI. A CrewAI multi-agent assistant answers customer questions, and NVIDIA NeMo Guardrails checks each question and answer against policies for personal data, jailbreak attempts, off-topic advice, and toxic or biased language. A web UI shows the answer with and without guardrails side by side, and a batch dashboard measures how often each policy fires. It is for teams that need to show a generative-AI assistant is safe before production. The guardrails service and web UI run as Cloudera AI Applications, and the models run on Cloudera AI Inference Service, so customer data and safety decisions stay inside your governed environment.

## Demo

> **TODO:** add the Reprise walkthrough link.

![Chat Compare: the same question answered without and with guardrails](assets/chat-compare.png)

![Batch Dashboard: 100-query evaluation with violations by policy](assets/batch-dashboard.png)

*Screenshots use sample data.*

## Use Case

Banks want generative-AI assistants for customer service, but an unguarded assistant can leak personal data, be manipulated by jailbreak prompts, give investment advice it isn't licensed to give, or produce biased language about lending. Risk and compliance teams also need evidence that controls work.

**Outcome:** safety policies are enforced on both the customer's question and the assistant's answer, stakeholders can see the effect side by side, and every violation is measured and logged for review.

## Key Features

- **Switchable safety policies** — personal data (PII), jailbreak / prompt injection, topic control, and toxicity / bias.
- **Side-by-side proof** — each answer shown with and without guardrails, including which rule fired and why.
- **Measurable governance** — a 100-query test set with block rates, charts by policy, a violation log, and CSV export.
- **Shared or embedded guardrails** — run one central guardrails service for many apps, or run checks inside the app.
- **Private model serving** — models on Cloudera AI Inference Service (default `nvidia/nemotron-3-nano`), with OpenAI as an alternative for quick trials.
- **Choice of safety judge** — the main model, Llama Guard 3 on Cloudera AI Inference, or an NVIDIA NIM safety model.

## Quickstart / Guide

**Run in a Cloudera AI Workbench session (or locally):**

1. Clone the repository:
   ```bash
   git clone https://github.com/SuperEllipse/ai-governance.git
   cd ai-governance
   ```
2. Install dependencies and the PII detection model (one-time, ~560 MB):
   ```bash
   pip install -r requirements.txt
   python -m spacy download en_core_web_lg
   ```
3. Configure a model provider. Copy a template and fill in your values:
   ```bash
   cp .env.caiis.example .env     # Cloudera AI Inference: endpoint URL, model, CDP token
   # or
   cp .env.openai.example .env    # OpenAI: API key
   ```
4. Start the guardrails server (Terminal 1) and note the port it prints:
   ```bash
   bash scripts/start_guardrails_server.sh
   ```
5. Start the web UI (Terminal 2) and open the printed URL. In a CDSW session, open the Application on port 8090:
   ```bash
   bash scripts/start_demo.sh
   ```
6. Click an example card in **Chat Compare** and send it. The header badges confirm that dependencies, the model key, and the guardrails server are ready.

**Deploy on Cloudera AI as two Applications:**

1. Install dependencies once per engine: `pip install -r requirements.txt`.
2. Create **Application 1** (guardrails server) with script `applications/guardrails_server_app.py` and your model environment variables. Start it and copy its public URL.
3. Create **Application 2** (web UI) with script `applications/web_app.py`, the same model variables, and `GUARDRAILS_HOST` set to Application 1's hostname. Start it and open its public URL.

Both scripts detect the platform port automatically, on Cloudera AI Workbench and on Cloudera AI Inference Service.

## Architecture / Software Components

Each question is answered by the CrewAI agents first, which gives the unguarded answer. NeMo Guardrails then checks the question and answer, either inside the web UI app (Embedded mode) or through the shared guardrails server (Centralized Server mode), and produces the guarded answer. Violations are saved to SQLite for the dashboard.

```mermaid
flowchart LR
    user(["User"]) --> ui

    subgraph app2["Cloudera AI Application 2 — web UI"]
        ui["React UI"] --> api["FastAPI backend"]
        api --> crew["CrewAI agents"]
        crew --> cis[("Dummy banking data")]
        api --> emb["NeMo Guardrails<br/>embedded"]
        emb --> pii["Presidio<br/>PII detection"]
        api --> db[("SQLite<br/>violation log")]
    end

    subgraph app1["Cloudera AI Application 1"]
        srv["NeMo Guardrails server"]
    end

    subgraph caii["Cloudera AI Inference Service"]
        llm["Nemotron 3 Nano"]
        lg["Llama Guard 3<br/>optional"]
    end

    api -- "Centralized Server mode" --> srv
    crew --> llm
    emb --> llm
    srv --> llm
    api -. "optional" .-> lg
```

| Component | Role |
| --- | --- |
| Cloudera AI Workbench | Hosts the project and the two Applications |
| Cloudera AI Inference Service | Serves the models privately (Nemotron 3 Nano by default, optional Llama Guard 3) |
| NVIDIA NeMo Guardrails | Policy engine that checks questions (input rails) and answers (output rails) |
| CrewAI | Multi-agent banking assistant: a router plus customer-service and credit/mortgage agents |
| Microsoft Presidio | Detects personal data such as SSNs, card numbers, and email addresses |
| FastAPI + React | Web UI with Chat Compare, Batch Dashboard, and Architecture views |
| SQLite | Stores violations and batch-run history |

## Target Audience

- **Solution architects and sales engineers** demonstrating AI governance on Cloudera AI.
- **ML / AI engineers** adding guardrails to agent-based applications.
- **Platform engineers** deploying AI applications on Cloudera AI.
- **Risk and compliance stakeholders** evaluating what the controls catch.

## Repository Structure

| Path | Description |
| --- | --- |
| `applications/` | Cloudera AI Application entry points: guardrails server and web UI |
| `assets/` | Screenshots |
| `data/dummy_cis/` | Dummy banking data used by the agents |
| `guardrails/` | NeMo Guardrails base config, prompts, and policy modules |
| `scripts/` | Start scripts for sessions and connectivity checks |
| `src/` | Python code: agents, guardrails client, model providers, API, batch simulation |
| `interface/` | React + TypeScript frontend (`interface/dist/` is the committed build) |
| `.env.*.example` | Environment templates for Cloudera AI Inference or OpenAI |
| `requirements.txt` | Python dependencies |

## Prerequisites

- Access to **Cloudera AI** (a Cloudera AI Workbench project that can create Applications), or a local machine for development.
- A model endpoint: **Cloudera AI Inference Service** with a CDP token, or an **OpenAI API key** for quick trials.
- Optional: a Llama Guard 3 endpoint on Cloudera AI Inference, or an NVIDIA API key for NIM.
- **Python 3.10+**, `pip`, and `git`.
- Node.js 18+ only if you change the UI.

## Hardware Requirements

The app tier is CPU-only. Models run on Cloudera AI Inference Service or OpenAI. These figures are estimates.

| Deployment | Minimum |
| --- | --- |
| Launchable / demo (one session) | 2 vCPU, 8 GiB RAM, ~5 GB storage; no GPU |
| Production / enterprise (two Applications) | 2 vCPU and 8 GiB RAM per Application; GPU only to self-host models on Cloudera AI Inference, sized per the model ([docs](https://docs.cloudera.com/machine-learning/cloud/ai-inference/)) |

## Documentation

- [NVIDIA NeMo Guardrails](https://docs.nvidia.com/nemo/guardrails/)
- [Cloudera AI Inference Service](https://docs.cloudera.com/machine-learning/cloud/ai-inference/)
- [Deploying Applications on Cloudera AI Inference Service](https://docs.cloudera.com/machine-learning/cloud/ai-inference/topics/ml-caii-application-deploy.html)
- [Cloudera AI Applications](https://docs.cloudera.com/machine-learning/cloud/applications/topics/ml-applications-c.html)
- [CrewAI](https://docs.crewai.com/)
- [Microsoft Presidio](https://microsoft.github.io/presidio/)
