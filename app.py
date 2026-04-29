import streamlit as st
import zipfile
import pdfplumber
import pandas as pd
import re
import io

st.set_page_config(page_title="PDF Bulk Parser", layout="wide")

st.title("📂 Bulk ZIP PDF Parser (CAF Forms)")

uploaded_files = st.file_uploader(
    "Upload ZIP files", type=["zip"], accept_multiple_files=True
)

def extract_data(text):
    mobile_match = re.search(r"\*Mobile No:(\d{10})", text)
    pos_match = re.search(r"\*POS Name:(.+)", text)
    date_match = re.search(r"\*Date:\s*([\d:]+)", text)

    return {
        "Mobile Number": mobile_match.group(1) if mobile_match else "",
        "POS Name": pos_match.group(1).strip() if pos_match else "",
        "Date": date_match.group(1) if date_match else ""
    }

if uploaded_files:
    all_data = []
    progress = st.progress(0)
    total_files = len(uploaded_files)
    count = 0

    for uploaded_file in uploaded_files:
        with zipfile.ZipFile(uploaded_file) as z:
            for file_name in z.namelist():
                if file_name.lower().endswith(".pdf"):
                    try:
                        with z.open(file_name) as pdf_file:
                            pdf_bytes = pdf_file.read()
                            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                                text = ""
                                for page in pdf.pages:
                                    page_text = page.extract_text()
                                    if page_text:
                                        text += page_text + "\n"

                                parsed = extract_data(text)

                                all_data.append({
                                    "ZIP File": uploaded_file.name,
                                    "PDF File": file_name,
                                    "Mobile Number": parsed["Mobile Number"],
                                    "POS Name": parsed["POS Name"],
                                    "Date": parsed["Date"]
                                })
                    except Exception as e:
                        st.warning(f"Error in {file_name}: {e}")

        count += 1
        progress.progress(count / total_files)

    df = pd.DataFrame(all_data)

    st.success("✅ Parsing Completed Successfully!")
    st.dataframe(df, use_container_width=True)

    output = io.BytesIO()
    df.to_excel(output, index=False)

    st.download_button(
        label="📥 Download Excel",
        data=output.getvalue(),
        file_name="CAF_Parsed_Output.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
