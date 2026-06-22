"""NVIDIA NeMo Guardrails Banking Demo — Streamlit UI."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# Ensure project root on path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.guardrails.client import GuardrailsClient, GuardrailsMode, _ensure_text_response
from src.guardrails.violation_parser import (
    ViolationStore,
    is_actual_violation,
    policies_checked_and_passed,
)
from src.llm.provider import (
    CAIIS_DEFAULT_BASE_URL,
    CAIIS_DEFAULT_MODEL,
    LLMConfig,
    SafetyModelConfig,
    default_caiis_config,
    default_openai_config,
    detect_default_provider,
    get_llm_config,
    is_caiis_configured,
)
from src.simulation.batch_runner import run_batch
from src.simulation.queries import EXAMPLE_QUERIES, ExampleQuery, get_all_queries

def default_guardrails_server_url() -> str:
    """Sidebar default: GUARDRAILS_PORT (CDSW often 8001), else GUARDRAILS_SERVER_URL."""
    port = os.getenv("GUARDRAILS_PORT", "").strip()
    if port:
        return f"http://127.0.0.1:{port}"
    return os.getenv("GUARDRAILS_SERVER_URL", "http://127.0.0.1:8001")



st.set_page_config(
    page_title="NeMo Guardrails Banking Demo",
    page_icon="🏦",
    layout="wide",
)

POLICY_OPTIONS = {
    "PII / Personal Data": "pii",
    "Prompt Injection / Jailbreak": "jailbreak",
    "Topic Control": "topic",
    "Toxicity / Bias": "toxicity",
}


def init_session_state() -> None:
    defaults = {
        "chat_history": [],
        "last_result": None,
        "batch_summary": None,
        "selected_violation": None,
        "demo_suggestion": None,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


def _block_type_badge(block_type: str) -> str:
    if block_type == "Happy path":
        return "🟢"
    if block_type.startswith("Input block"):
        return "🔴"
    if block_type.startswith("Output block"):
        return "🟠"
    return "⚪"


def _format_mode_label(mode: str) -> str:
    return {
        "embedded": "Embedded",
        "server": "Centralized Server",
        "unguarded": "Unguarded Only",
    }.get(mode, mode)


def _format_policy_keys(keys: list[str]) -> str:
    if not keys:
        return "none (happy path)"
    labels = {v: k for k, v in POLICY_OPTIONS.items()}
    return ", ".join(labels.get(k, k) for k in keys)


def render_demo_guide() -> None:
    with st.expander("Demo guide: block types", expanded=False):
        st.markdown(
            """
            **Execution modes**
            - **Centralized Server** — uses `guardrails/base/config.yml` only (`self_check` input + output).
              Policy checkboxes do **not** change server config. Best for investment-advice / topic blocks
              you already see with server mode.
            - **Embedded** — composes policies from sidebar checkboxes via `config_composer`.
              Uses separate `check()` on input then output — **best for PII input blocks and output
              policy blocks** (e.g. missing FDIC disclaimer).
            """
        )
        rows = []
        for ex in EXAMPLE_QUERIES:
            rows.append(
                {
                    "Example": ex["label"],
                    "Block type": ex["block_type"],
                    "Mode": _format_mode_label(ex["recommended_mode"]),
                    "Policies": _format_policy_keys(ex["recommended_policies"]),
                    "Expected rail": ex["expected_rail"] or "— (passes)",
                }
            )
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        st.caption(
            "Output-block demos may pass if the agent already includes required disclaimers. "
            "Try Embedded mode and expand **Guardrails Log** to see `triggered_output_rail`."
        )


def apply_example_suggestion(example: ExampleQuery) -> None:
    st.session_state["query_input"] = example["query"]
    st.session_state["demo_suggestion"] = example
    st.session_state["execution_mode"] = _format_mode_label(example["recommended_mode"])
    suggested = set(example["recommended_policies"])
    for _label, policy_key in POLICY_OPTIONS.items():
        st.session_state[f"policy_{policy_key}"] = policy_key in suggested


def sidebar_settings() -> tuple[LLMConfig, SafetyModelConfig, GuardrailsMode, list[str], str]:
    st.sidebar.header("⚙️ Settings")

    provider_options = ["openai", "caiis"]
    default_provider = detect_default_provider()
    provider = st.sidebar.selectbox(
        "LLM Provider",
        provider_options,
        index=provider_options.index(default_provider),
        format_func=lambda x: "OpenAI" if x == "openai" else "Cloudera AI Inference",
        help="Defaults to OpenAI. Set DEFAULT_LLM_PROVIDER=caiis in .env to default to CAIIS.",
    )

    if provider == "openai" and is_caiis_configured():
        st.sidebar.warning(
            "CAIIS is configured in .env but OpenAI is selected. "
            "Choose **Cloudera AI Inference** to use your CAIIS endpoint."
        )

    if provider == "openai":
        default_cfg = default_openai_config()
    else:
        default_cfg = default_caiis_config()

    api_key_label = "CDP Token (Bearer)" if provider == "caiis" else "API Key"
    api_key_default = (
        default_cfg.api_key
        if provider == "caiis"
        else (default_cfg.api_key or os.getenv("OPENAI_API_KEY", ""))
    )
    api_key = st.sidebar.text_input(
        api_key_label,
        value=api_key_default,
        type="password",
        help="Read from CDP_TOKEN env or /tmp/jwt when using Cloudera AI Inference.",
    )
    base_url = st.sidebar.text_input("Base URL", value=default_cfg.base_url)
    model = st.sidebar.text_input("Model", value=default_cfg.model)

    llm_config = get_llm_config(
        provider=provider,
        api_key=api_key,
        base_url=base_url,
        model=model,
    )

    st.sidebar.subheader("Safety Model")
    safety_mode_label = st.sidebar.radio(
        "Safety Check Engine",
        ["Main LLM (self_check)", "NVIDIA NIM"],
    )
    safety_mode = "nim" if "NIM" in safety_mode_label else "self_check"
    nim_key = ""
    if safety_mode == "nim":
        nim_key = st.sidebar.text_input(
            "NVIDIA API Key",
            value=os.getenv("NVIDIA_API_KEY", ""),
            type="password",
        )
        if not nim_key:
            st.sidebar.warning("NIM not configured — will fall back to self_check behavior.")

    safety_config = SafetyModelConfig(mode=safety_mode, nim_api_key=nim_key)

    st.sidebar.subheader("Guardrails Mode")
    mode_options = ["Centralized Server", "Embedded", "Unguarded Only"]
    if "execution_mode" not in st.session_state:
        st.session_state["execution_mode"] = "Centralized Server"
    mode_label = st.sidebar.selectbox(
        "Execution Mode",
        mode_options,
        key="execution_mode",
        help="Centralized Server (recommended): NeMo server (often :8001 on CDSW). "
        "Embedded: in-process LLMRails. Unguarded: no safety rails.",
    )
    mode_map = {
        "Embedded": "embedded",
        "Centralized Server": "server",
        "Unguarded Only": "unguarded",
    }
    mode: GuardrailsMode = mode_map[mode_label]
    server_url = st.sidebar.text_input(
        "Guardrails Server URL",
        value=default_guardrails_server_url(),
    )

    suggestion = st.session_state.get("demo_suggestion")
    if suggestion:
        st.sidebar.info(
            f"**Demo tip — {suggestion['label']}**\n\n"
            f"Mode: **{_format_mode_label(suggestion['recommended_mode'])}** · "
            f"Policies: {_format_policy_keys(suggestion['recommended_policies'])}\n\n"
            f"Expected rail: `{suggestion['expected_rail'] or 'none'}`"
        )

    st.sidebar.subheader("Active Policies")
    selected_policies: list[str] = []
    for label, key in POLICY_OPTIONS.items():
        policy_key = f"policy_{key}"
        if policy_key not in st.session_state:
            st.session_state[policy_key] = True
        if st.sidebar.checkbox(label, key=policy_key):
            selected_policies.append(key)

    return llm_config, safety_config, mode, selected_policies, server_url


def render_policy_status(result) -> None:
    """Show violation banner, pass message, or infra warning — not activated rails alone."""
    output_vars = result.output_vars or {}
    log_data = result.guardrails_log or {}
    infra_error = output_vars.get("guardrails_error")
    actual_violation = result.blocked or is_actual_violation(output_vars, log_data)

    if infra_error and output_vars.get("allowed", True) and not actual_violation:
        st.warning(infra_error)
    elif actual_violation:
        st.error("Request blocked by safety policy")
        rail = (
            output_vars.get("triggered_input_rail")
            or output_vars.get("triggered_output_rail")
        )
        if rail:
            st.caption(f"Blocked by rail: {rail}")
        for v in result.violations:
            reason = v.policy_reason or v.violated_rule
            if reason:
                st.caption(f"Policy violated: {reason}")
                break
    elif policies_checked_and_passed(result.policies, output_vars, log_data):
        st.success("Policies checked — no violations")

    if actual_violation and result.violations:
        for v in result.violations:
            reason = v.policy_reason or v.violated_rule
            reason_suffix = f" | **Policy violated:** {reason}" if reason else ""
            st.warning(
                f"**Policy:** {v.policy} | **Rail:** {v.rail} | "
                f"**Blocked:** {v.blocked}{reason_suffix}"
            )


def render_guarded_panel(result) -> None:
    """Render the guarded response column with clear policy vs infra messaging."""
    st.subheader("✅ With Guardrails")
    render_policy_status(result)
    st.markdown(_ensure_text_response(result.guarded_response))


def render_chat_tab(
    llm_config: LLMConfig,
    safety_config: SafetyModelConfig,
    mode: GuardrailsMode,
    policies: list[str],
    server_url: str,
) -> None:
    st.header("💬 Chat Compare")
    st.caption("Side-by-side guarded vs unguarded responses with agent trace.")

    render_demo_guide()

    for row_start in range(0, len(EXAMPLE_QUERIES), 3):
        col_btns = st.columns(3)
        for j, example in enumerate(EXAMPLE_QUERIES[row_start : row_start + 3]):
            badge = _block_type_badge(example["block_type"])
            with col_btns[j]:
                st.caption(f"{badge} **{example['block_type']}**")
                if st.button(example["label"], key=f"ex_{row_start + j}", use_container_width=True):
                    apply_example_suggestion(example)

    if st.session_state.get("demo_suggestion"):
        ex = st.session_state["demo_suggestion"]
        st.caption(
            f"Selected demo: **{ex['label']}** — use "
            f"**{_format_mode_label(ex['recommended_mode'])}** with "
            f"{_format_policy_keys(ex['recommended_policies'])}"
        )

    query = st.text_area(
        "Customer Query",
        height=100,
        key="query_input",
    )

    if st.button("Send Query", type="primary"):
        if not query.strip():
            st.warning("Enter a query first.")
            return

        with st.spinner("Running unguarded + guarded paths…"):
            client = GuardrailsClient(llm_config, safety_config, server_url)
            result = asyncio.run(
                client.run_query(query, policies=policies, mode=mode)
            )
            st.session_state.last_result = result
            st.session_state.chat_history.append(result.to_dict())

        col_l, col_r = st.columns(2)
        with col_l:
            st.subheader("🚫 Without Guardrails")
            st.markdown(result.unguarded_response)
        with col_r:
            render_guarded_panel(result)

        with st.expander("Agent Trace"):
            st.json(result.agent_trace)
        with st.expander("Guardrails Log"):
            log_view: dict = {
                "output_vars": result.output_vars,
                "log": result.guardrails_log,
            }
            if result.violations:
                log_view["policy_violations"] = [
                    {
                        "rail": v.rail,
                        "policy": v.policy,
                        "policy_reason": v.policy_reason,
                        "violated_rule": v.violated_rule,
                    }
                    for v in result.violations
                ]
            st.json(log_view)

    elif st.session_state.last_result:
        result = st.session_state.last_result
        col_l, col_r = st.columns(2)
        with col_l:
            st.subheader("🚫 Without Guardrails")
            st.markdown(_ensure_text_response(result.unguarded_response))
        with col_r:
            render_guarded_panel(result)


def render_batch_tab(
    llm_config: LLMConfig,
    safety_config: SafetyModelConfig,
    mode: GuardrailsMode,
    policies: list[str],
    server_url: str,
) -> None:
    st.header("📊 Batch Simulation Dashboard")
    store = ViolationStore()

    col1, col2, col3 = st.columns(3)
    sample_size = col1.selectbox("Sample Size", [10, 25, 50, 100], index=3)
    effective_mode = mode if mode != "unguarded" else "embedded"
    col2.metric("Total Queries in Dataset", len(get_all_queries()))
    col3.metric("Active Policies", len(policies))

    if st.button("Run Batch Simulation", type="primary"):
        queries = get_all_queries()[:sample_size]
        progress = st.progress(0)
        status = st.empty()

        def on_progress(current: int, total: int, msg: str) -> None:
            progress.progress(current / total)
            status.text(f"[{current}/{total}] {msg}")

        with st.spinner(f"Running {sample_size} queries…"):
            summary = asyncio.run(
                run_batch(
                    policies=policies,
                    mode=effective_mode,
                    llm_config=llm_config,
                    safety_config=safety_config,
                    server_url=server_url,
                    queries=queries,
                    progress_callback=on_progress,
                )
            )
            st.session_state.batch_summary = summary
        status.text("Batch complete.")

    summary = st.session_state.batch_summary
    if summary:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Total Queries", summary["total_queries"])
        m2.metric("Violations", summary["violation_count"])
        m3.metric("Violation Rate", f"{summary['violation_rate']:.1%}")
        m4.metric("Run ID", summary["run_id"])

        if summary.get("by_policy"):
            df_policy = pd.DataFrame(
                list(summary["by_policy"].items()),
                columns=["Policy", "Count"],
            )
            fig = px.bar(df_policy, x="Policy", y="Count", title="Violations by Policy")
            st.plotly_chart(fig, use_container_width=True)

        if summary.get("by_category"):
            df_cat = pd.DataFrame(
                list(summary["by_category"].items()),
                columns=["Category", "Count"],
            )
            fig2 = px.bar(
                df_cat, x="Category", y="Count", title="Violations by Category", color="Category"
            )
            st.plotly_chart(fig2, use_container_width=True)

    st.subheader("Violation Log")
    violations = store.get_violations(
        run_id=summary["run_id"] if summary else None
    )
    if violations:
        df = pd.DataFrame(violations)
        display_cols = [
            "id",
            "query",
            "policy",
            "rail",
            "policy_reason",
            "blocked",
            "category",
            "agent",
            "timestamp",
        ]
        display_cols = [c for c in display_cols if c in df.columns]
        st.dataframe(df[display_cols], use_container_width=True, hide_index=True)

        selected_id = st.selectbox(
            "Drill-down: Select violation ID",
            options=df["id"].tolist(),
        )
        if selected_id:
            row = df[df["id"] == selected_id].iloc[0]
            st.markdown("### Drill-down Detail")
            st.markdown(f"**Query:** {row['query']}")
            if row.get("policy_reason"):
                st.markdown(f"**Policy violated:** {row['policy_reason']}")
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown("**Unguarded Response**")
                st.text(row.get("unguarded_response", "")[:2000])
            with col_b:
                st.markdown("**Guarded Response**")
                st.text(row.get("guarded_response", "")[:2000])
            st.markdown(f"**Activated Rails:** {row.get('activated_rails', [])}")
            st.markdown(f"**Agent:** {row.get('agent', 'N/A')}")
    else:
        st.info("No violations logged yet. Run a batch simulation or chat query.")


def render_architecture_tab(server_url: str) -> None:
    st.header("🏗️ Architecture")
    st.markdown("""
    This demo showcases **NVIDIA NeMo Guardrails** with a **CrewAI multi-agent** banking assistant.

    ### Components
    - **CustomerServiceAgent** — accounts, onboarding, product FAQ (CIS tools)
    - **CreditMortgageAgent** — credit cards, mortgage rates
    - **NeMo Guardrails** — modular policies: PII, jailbreak, topic, toxicity/bias

    ### Execution Modes
    | Mode | Description |
    |------|-------------|
    | **Unguarded** | CrewAI agents call LLM directly — shows raw/unsafe responses |
    | **Embedded** | `LLMRails` SDK in-process — per-request policy composition |
    | **Centralized Server** | NeMo FastAPI server (8000 or 8001 on CDSW) — enterprise governance |

    ### Data Flow
    1. User query → Router classifies intent
    2. Specialist agent uses CIS dummy data tools
    3. Parallel unguarded + guarded paths for comparison
    4. Violations logged to SQLite for dashboard drill-down
    """)

    st.code("""
    Streamlit UI (:8090)
         │
         ├── CrewAI Agents (CustomerService + CreditMortgage)
         │        └── CIS JSON Tools
         │
         └── NeMo Guardrails
                  ├── Embedded LLMRails
                  └── Server Mode (:8000 / :8001)
    """, language="text")

    st.markdown(f"""
    ### Quick Links
    - NeMo Guardrails Server UI: [{server_url}]({server_url})
    - [NeMo Guardrails Docs](https://docs.nvidia.com/nemo/guardrails/)
    - [Cloudera AI Inference](https://docs.cloudera.com/machine-learning/cloud/ai-inference/)
    - [GitHub: SuperEllipse/ai-governance](https://github.com/SuperEllipse/ai-governance)

    ### LLM providers
    - **OpenAI** `gpt-4o-mini` (default) — set `OPENAI_API_KEY` in `.env`
    - **Cloudera AI Inference (CAIIS)** — copy `.env.caiis.example` to `.env`
    - **Guardrails**: **Centralized Server** (recommended) — run `bash scripts/start_guardrails_server.sh`

    ### Switch to Cloudera AI Inference
    ```bash
    cp .env.caiis.example .env
    # Edit .env with your CAIIS endpoint and CDP token
    export CAIIS_BASE_URL="{CAIIS_DEFAULT_BASE_URL}"
    export CAIIS_MODEL="{CAIIS_DEFAULT_MODEL}"
    export CDP_TOKEN="your-cdp-bearer-token"  # or /tmp/jwt in CDSW sessions
    ```
    Then select **Cloudera AI Inference** in the sidebar LLM Provider dropdown.

    ### Switching LLM providers in the UI
    Use the sidebar **LLM Provider** dropdown:
    - **OpenAI** (default) — uses `OPENAI_API_KEY` and `gpt-4o-mini`
    - **Cloudera AI Inference** — uses `CAIIS_BASE_URL`, `CAIIS_MODEL`, and CDP token

    ### Presidio PII (one-time)
    ```bash
    python -m spacy download en_core_web_lg
    ```
    """)


def main() -> None:
    init_session_state()
    st.title("🏦 NeMo Guardrails Banking Demo")
    st.caption("CrewAI multi-agent banking assistant with modular safety policies")

    llm_config, safety_config, mode, policies, server_url = sidebar_settings()

    tab_chat, tab_batch, tab_arch = st.tabs(
        ["Chat Compare", "Batch Dashboard", "Architecture"]
    )

    with tab_chat:
        render_chat_tab(llm_config, safety_config, mode, policies, server_url)
    with tab_batch:
        render_batch_tab(llm_config, safety_config, mode, policies, server_url)
    with tab_arch:
        render_architecture_tab(server_url)


if __name__ == "__main__":
    main()
