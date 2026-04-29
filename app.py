import streamlit as st
import zipfile
import pdfplumber
import pandas as pd
import re
import io
import os

st.set_page_config(page_title="PDF Bulk Parser", layout="wide")
st.title("📂 Bulk ZIP/PDF Parser (CAF Forms)")

uploaded_files = st.file_uploader(
    "Upload ZIP or PDF files",
    type=["zip", "pdf"],
    accept_multiple_files=True
)

def extract_data(text, file_name=""):
    """Extract structured fields from raw PDF text with fallback patterns."""
    
    def search(patterns, txt):
        for pattern in patterns:
            m = re.search(pattern, txt, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return ""

    mobile = search([
        r"\*?Mobile\s*No[:\s]*(\d{10})",
        r"Mobile\s*Number[:\s]*(\d{10})",
        r"\b([6-9]\d{9})\b"
    ], text)

    pos_name = search([
        r"\*?POS\s*Name[:\s]*(.+)",
        r"Point\s*of\s*Sale[:\s]*(.+)",
        r"Retailer\s*Name[:\s]*(.+)"
    ], text)

    date = search([
        r"\*?Date[:\s]*([\d]{1,2}[\/\-:][\d]{1,2}[\/\-:][\d]{2,4})",
        r"\*?Date[:\s]*([\d:\/\-]+)",
        r"(\d{2}[\/\-]\d{2}[\/\-]\d{4})"
    ], text)

    customer_name = search([
        r"\*?Customer\s*Name[:\s]*(.+)",
        r"Name\s*of\s*Customer[:\s]*(.+)",
        r"Subscriber\s*Name[:\s]*(.+)"
    ], text)

    sim_no = search([
        r"\*?SIM\s*(?:No|Number)[:\s]*(\d+)",
        r"ICCID[:\s]*(\d+)",
        r"SIM\s*Card\s*No[:\s]*(\d+)"
    ], text)

    id_proof = search([
        r"\*?ID\s*Proof[:\s]*(.+)",
        r"Identity\s*Proof[:\s]*(.+)",
        r"Document\s*Type[:\s]*(.+)"
    ], text)

    return {
        "Mobile Number": mobile,
        "Customer Name": customer_name,
        "POS Name": pos_name,
        "Date": date,
        "SIM No": sim_no,
        "ID Proof": id_proof
    }


def extract_text_from_pdf_bytes(pdf_bytes, file_name=""):
    """Safely extract text from PDF bytes using pdfplumber."""
    text = ""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            if len(pdf.pages) == 0:
                return None, "PDF has no pages"
            for page in pdf.pages:
                try:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
                except Exception as pe:
                    continue  # skip bad pages, continue others
    except Exception as e:
        return None, str(e)
    return text.strip() if text.strip() else None, None


def collect_pdfs_from_zip(zip_bytes, zip_label="", depth=0, max_depth=5):
    """
    Recursively extract all PDFs from a ZIP (including nested ZIPs).
    Returns list of (label_path, pdf_bytes).
    """
    if depth > max_depth:
        st.warning(f"⚠️ Max nesting depth ({max_depth}) reached in: {zip_label}")
        return []

    results = []
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            bad_names = [n for n in z.namelist() if '..' in n or n.startswith('/')]
            if bad_names:
                st.warning(f"⚠️ Skipped unsafe paths in {zip_label}: {bad_names}")

            for file_name in z.namelist():
                # Security: skip unsafe paths
                if '..' in file_name or file_name.startswith('/'):
                    continue

                lower_name = file_name.lower()

                if lower_name.endswith('.pdf'):
                    try:
                        with z.open(file_name) as f:
                            pdf_bytes = f.read()
                        label = f"{zip_label} → {file_name}" if zip_label else file_name
                        results.append((label, file_name, pdf_bytes))
                    except Exception as e:
                        st.warning(f"⚠️ Could not read PDF `{file_name}` in `{zip_label}`: {e}")

                elif lower_name.endswith('.zip'):
                    try:
                        with z.open(file_name) as f:
                            nested_zip_bytes = f.read()
                        nested_label = f"{zip_label} → {file_name}" if zip_label else file_name
                        nested = collect_pdfs_from_zip(
                            nested_zip_bytes,
                            zip_label=nested_label,
                            depth=depth + 1,
                            max_depth=max_depth
                        )
                        results.extend(nested)
                    except Exception as e:
                        st.warning(f"⚠️ Could not open nested ZIP `{file_name}` in `{zip_label}`: {e}")

    except zipfile.BadZipFile:
        st.error(f"❌ Invalid or corrupted ZIP file: `{zip_label}`")
    except Exception as e:
        st.error(f"❌ Unexpected error in `{zip_label}`: {e}")

    return results


# ─── Main Processing ────────────────────────────────────────────────────────────

if uploaded_files:
    all_pdfs = []  # list of (source_label, pdf_file_name, pdf_bytes)
    errors = []

    # Step 1: Collect all PDFs
    with st.spinner("🔍 Scanning uploaded files for PDFs..."):
        for uploaded_file in uploaded_files:
            file_bytes = uploaded_file.read()
            name_lower = uploaded_file.name.lower()

            if name_lower.endswith('.pdf'):
                all_pdfs.append((uploaded_file.name, uploaded_file.name, file_bytes))

            elif name_lower.endswith('.zip'):
                pdfs = collect_pdfs_from_zip(file_bytes, zip_label=uploaded_file.name)
                all_pdfs.extend(pdfs)

    total = len(all_pdfs)
    if total == 0:
        st.error("❌ No PDFs found in the uploaded files.")
        st.stop()

    st.info(f"📄 Found **{total} PDF(s)**. Parsing now...")

    # Step 2: Parse each PDF
    all_data = []
    progress_bar = st.progress(0)
    status_text = st.empty()

    for idx, (source_label, pdf_file_name, pdf_bytes) in enumerate(all_pdfs):
        status_text.text(f"Processing {idx + 1}/{total}: {pdf_file_name}")

        text, error = extract_text_from_pdf_bytes(pdf_bytes, pdf_file_name)

        if error or not text:
            reason = error if error else "No text extracted (possibly scanned/image PDF)"
            errors.append({"Source": source_label, "Reason": reason})
            all_data.append({
                "Source Path": source_label,
                "PDF File": pdf_file_name,
                "Mobile Number": "",
                "Customer Name": "",
                "POS Name": "",
                "Date": "",
                "SIM No": "",
                "ID Proof": "",
                "Status": f"⚠️ {reason}"
            })
        else:
            parsed = extract_data(text, pdf_file_name)
            all_data.append({
                "Source Path": source_label,
                "PDF File": pdf_file_name,
                "Mobile Number": parsed["Mobile Number"],
                "Customer Name": parsed["Customer Name"],
                "POS Name": parsed["POS Name"],
                "Date": parsed["Date"],
                "SIM No": parsed["SIM No"],
                "ID Proof": parsed["ID Proof"],
                "Status": "✅ OK"
            })

        progress_bar.progress((idx + 1) / total)

    status_text.empty()

    df = pd.DataFrame(all_data)

    # ─── Summary ────────────────────────────────────────────────────────────────
    ok_count = len(df[df["Status"] == "✅ OK"])
    warn_count = total - ok_count

    col1, col2, col3 = st.columns(3)
    col1.metric("📄 Total PDFs", total)
    col2.metric("✅ Parsed OK", ok_count)
    col3.metric("⚠️ Warnings", warn_count)

    st.success("✅ Parsing Complete!")

    # ─── Tabs: Results + Errors ──────────────────────────────────────────────────
    tab1, tab2 = st.tabs(["📊 Parsed Data", "⚠️ Errors / Warnings"])

    with tab1:
        st.dataframe(df, use_container_width=True)

    with tab2:
        if errors:
            st.dataframe(pd.DataFrame(errors), use_container_width=True)
        else:
            st.success("No errors encountered.")

    # ─── Download ────────────────────────────────────────────────────────────────
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Parsed Data")
        if errors:
            pd.DataFrame(errors).to_excel(writer, index=False, sheet_name="Errors")
    output.seek(0)

    st.download_button(
        label="📥 Download Excel Report",
        data=output.getvalue(),
        file_name="CAF_Parsed_Output.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )