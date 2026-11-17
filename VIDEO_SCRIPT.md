# Full recording script and exact screen directions

**Target duration: approximately 6:20 (must be 5:00–7:00).** Keep your face visible in a corner webcam overlay the whole time. Use Loom, OBS, or Zoom. Record one full practice take first. Narration below is designed to be read aloud and aligned with the instructor's required five segments.

## Before recording (not shown)

1. In VS Code open `structured-data-extractor`. Expand `src`, `tests`, and `samples` in the Explorer sidebar.
2. Make sure `.env` has a working OPENAI_API_KEY, and **never open `.env` on camera**.
3. Run `PYTHONPATH=. uv run streamlit run src/app.py` in the VS Code terminal. Have browser `localhost:8501` ready.
4. First test a normal invoice on `samples/invoice_messy.pdf`, then turn on the demo error checkbox and confirm it either recovers or displays traceable retry failures; also test DLQ simulation.
5. Run `uv run pytest -v`, verify all pass, and clear terminal before recording so you can rerun it visibly.
6. Have GitHub repository ready but avoid showing account credentials or the real API keys.

## Part 1: Architecture and schema (0:00–1:00)

**Screen:** Start in VS Code. Display the entire project tree. Open `src/schemas.py`, zoom in if needed. Scroll to `LineItem` then `InvoiceExtraction`, highlighting `model_validator` and the `Decimal("0.02")` tolerance.

**Say:**

"Hello, my name is Tian Huang. Today I'll demonstrate my Resilient Unstructured Data Extraction project. The goal is to convert invoice documents into accurate, structured data that other programs could use. The application accepts PDF files and HTML or plain text, and uses an AI model to extract invoice fields. After extraction, Pydantic checks the data against strict validation rules. Here are the main folders. The schemas file defines invoice and line-item models. The extractor file makes the AI request, the fallback file manages retries and failures, and the app file builds the Streamlit interface. The schema requires positive quantities, allowed currencies, valid dates and consistent invoice totals. I use Decimal amounts to avoid ordinary floating-point rounding problems."

## Part 2: AI code audit (1:00–2:20)

**Screen:** Open `ai_prompt_log.md`, show the original coding prompt. Scroll to Issue 1 (floating point and reconciliation), then Issue 2 (unbounded retry context). Switch to `src/fallback.py` and briefly show `raw_text[:5000]` and `validation_summary()`.

**Say:**

"I used ChatGPT to help create the initial extraction code. My prompt asked for a Python invoice extractor that supports Pydantic validation, structured model outputs, a correction loop and a dead-letter queue. I reviewed the draft rather than trusting it automatically. The first issue was using ordinary floating point and exact equality to check financial amounts. That could produce inaccurate comparisons, so I changed the validation to use Decimal values and a two-cent tolerance. The second issue was inserting an entire document into every retry prompt. On large PDFs, this could waste tokens and increase costs. I corrected this by limiting the document and previous JSON lengths, while including the exact field names and validation errors. I also made sure a repaired JSON string must pass Pydantic validation before it is accepted."

## Part 3: Live extraction (2:20–3:45)

**Screen:** Switch to browser at `localhost:8501`. Turn OFF the demo-injection checkbox. Upload `samples/invoice_messy.pdf`. Show raw left column. Click **Extract and Validate**. Wait for AI completion, then show JSON on right, green reconciliation message, invoice total, and audit log.

**Say:**

"Now I'll show the application. I'll upload the sample invoice PDF included in the repository. On the left, we can see the document text, including the vendor, date, line items and amounts. I have the reflection option enabled, but first I'll run a normal extraction. When I click Extract and Validate, the application sends the document to OpenAI with a structured output schema. It then checks the returned values using Pydantic. On the right, we can see the clean JSON record. The line items total 150 dollars, tax is 12 dollars, and the grand total is 162 dollars. The reconciliation status confirms the calculations match. The audit also records the steps performed by the pipeline."

## Part 4: Reflection and DLQ demonstration (3:45–5:45)

**Screen:** Keep the PDF uploaded. Enable **Demo: inject first-attempt validation error**; keep reflection enabled; click **Extract and Validate**. Scroll to the validation error and corrective prompt; show resulting repaired status if it succeeds. Then click **Simulate Edge Case Failure (DLQ)**, show red failure status, saved file path and the three attempts in the audit. In VS Code Explorer show the generated file in `dlq/`, but do not display sensitive real customer documents.

**Say:**

"Next, I'll demonstrate how the application responds to invalid data. For this demonstration, I enabled an option that deliberately changes the first extracted total to an incorrect number. This is a simulated error so the test is repeatable. Pydantic detects that the invoice total does not match the subtotal plus tax. The pipeline records the exact validation error and prepares a corrective prompt with the original text and the invalid output. It then asks the AI model to try again. If the correction succeeds, the result is labeled repaired via reflection. This shows how the system can attempt to recover instead of immediately failing.

Now I'll test the dead-letter queue. This button uses deliberately invalid mock responses, so it does not use API credits. After three failed attempts, the system tries JSON syntax repair, checks the schema again, and then records the unrecoverable document in a DLQ file for manual review. The application remains running and reports the error clearly."

**Important:** If the real reflection call does not recover, say "The automatic correction did not succeed in this run; the system correctly recorded the failure in the DLQ" rather than falsely claiming success. Rehearse the live API flow beforehand.

## Part 5: Automated QA and wrap-up (5:45–6:20)

**Screen:** Switch back to VS Code. In the project terminal run `uv run pytest -v`. Show the list of passing tests. End on GitHub repository file tree and README flowchart if time allows.

**Say:**

"Finally, I'll run the automated test suite with pytest. These tests cover successful PDF extraction, invalid quantities, reconciliation failures, HTML parsing, date and currency validation, reflection retries and dead-letter queue handling. The test cases use mock AI responses so their results are repeatable. I've also included a README with the architecture diagram and setup instructions, along with the code audit log. This project helped me understand how to combine AI extraction with deterministic validation and reliable error handling. Thank you for watching."

## Recording checklist

- 5:00–7:00 minutes exactly; preferably ~6:20
- Webcam overlay visible for entire recording
- Show `schemas.py`, initial AI prompt, and at least two concrete corrections
- Show messy sample PDF, extracted record, JSON and reconciliation
- Show both the reflection corrective prompt and DLQ file
- Show `pytest -v` passing (fix failures before final recording)
- Upload video to YouTube as **Unlisted** or **Public**
