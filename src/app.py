"""Minimal Streamlit interface with validation and audit display."""
from pathlib import Path
import os
import sys

# Allow direct Streamlit execution from src/app.py and cloud hosting.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv
import streamlit as st

from src.extractor import SchemaExtractor, ExtractionProviderError, document_text

load_dotenv()
# Streamlit Community Cloud secrets are not always copied to environment variables.
# Read them here without displaying their values.
try:
    for secret_name in ("OPENAI_API_KEY", "OPENAI_MODEL"):
        if secret_name in st.secrets and not os.getenv(secret_name):
            os.environ[secret_name] = str(st.secrets[secret_name])
except FileNotFoundError:
    pass  # No local .streamlit/secrets.toml is normal when using .env.
st.set_page_config(page_title="Structured Data Extractor", layout="wide")
st.title("Resilient Invoice Data Extractor")
st.caption("PDF/HTML invoice extraction • native JSON schema • Pydantic validation • reflection • DLQ")

with st.sidebar:
    st.header("Extraction settings")
    st.caption("OpenAI native structured output")
    model = st.text_input("Model", value=os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    reflection_enabled = st.checkbox("Enable Reflection Self-Correction Loop", value=True)
    max_retries = st.slider("Maximum provider attempts", 1, 3, 3)
    demo_bad_first = st.checkbox("Demo: inject first-attempt validation error", value=False,
                                 help="Changes the first extracted total to an incorrect value to show reflection recovery.")

uploaded = st.file_uploader("Upload an invoice PDF or HTML file", type=["pdf", "html", "htm", "txt"])
pasted = st.text_area("Or paste invoice HTML or plain text", height=160)
source_text = ""
try:
    if uploaded:
        extension = uploaded.name.rsplit(".", 1)[-1].lower()
        source_text = document_text(uploaded.getvalue(), "pdf" if extension == "pdf" else "html" if extension in ("html", "htm") else "text")
    elif pasted.strip():
        source_text = document_text(pasted, "html" if "<" in pasted else "text")
except Exception as exc:
    st.error(f"Could not read document: {type(exc).__name__}")

left, right = st.columns(2)
with left:
    st.subheader("Raw document")
    st.code(source_text or "Upload a sample invoice or paste text above.", language="text")
with right:
    st.subheader("Validated JSON")
    result_holder = st.empty()
    result_holder.info("No extraction executed yet.")

run = st.button("Extract and Validate", type="primary", disabled=not bool(source_text.strip()))
simulate_dlq = st.button("Simulate Edge Case Failure (DLQ)")

if run or simulate_dlq:
    source = source_text
    if simulate_dlq:
        source = "gibberish no invoice fields, no amounts"
        def unrecoverable(_source, _correction):
            return '{"invoice_number": "", "vendor_name": "", "currency": "XYZ"}'
        extractor = SchemaExtractor(responder=unrecoverable, dlq_dir="dlq")
        st.info("Simulation mode: deliberately irrecoverable responses; no API call is made.")
    else:
        extractor = SchemaExtractor(dlq_dir="dlq", model=model)
    with st.status("Running extraction pipeline...", expanded=True) as status:
        def update(message: str):
            st.write(message)
        try:
            result = extractor.extract_with_retry(
                source, max_retries=max_retries, reflection_enabled=reflection_enabled,
                simulate_first_error=bool(demo_bad_first and not simulate_dlq), on_event=update,
            )
        except ExtractionProviderError as exc:
            st.error(str(exc))
            status.update(label="Provider error", state="error")
            st.stop()
        except Exception as exc:
            st.error(f"Extraction failed safely: {type(exc).__name__}")
            status.update(label="Extraction error", state="error")
            st.stop()
        status.update(label="Pipeline completed", state="complete")

    if result.validated_data:
        invoice = result.validated_data
        result_holder.json(invoice.model_dump(mode="json"))
        st.success("RECONCILED — line items, subtotal, tax and grand total match")
        a, b, c = st.columns(3)
        a.metric("Attempts", result.attempts_used)
        b.metric("Status", result.execution_status)
        c.metric("Invoice total", f"{invoice.currency} {invoice.total_amount:.2f}")
    else:
        result_holder.warning("No validated record produced.")
        st.error("RECONCILIATION FAILED — document sent to DLQ for human review")
        st.write("DLQ file:", result.dlq_path)
    st.subheader("Step-by-step audit log")
    st.json(result.events)
    if result.error_log:
        with st.expander("Validation error traces", expanded=True):
            for item in result.error_log:
                st.code(item, language="text")
    if result.corrective_prompts:
        with st.expander("Exact corrective prompts dispatched", expanded=True):
            for i, prompt in enumerate(result.corrective_prompts, 1):
                st.write(f"Reflection prompt {i}")
                st.code(prompt, language="text")
