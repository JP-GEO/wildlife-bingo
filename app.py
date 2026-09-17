import streamlit as st
import json
import random
import io
import requests
import pypdf
from google import genai
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# Page Setup
st.set_page_config(page_title="Wildlife Board Bingo", layout="centered")
st.title("🌲 Wildlife Board Meeting Bingo")
st.write("Provide an agenda source below to generate custom bingo cards!")

# API Key Check
if "GEMINI_API_KEY" not in st.secrets:
    st.error("Missing Gemini API Key in Streamlit Secrets!")
    st.stop()

# Helper function to extract text from raw PDF bytes
def extract_text_from_pdf_bytes(pdf_bytes):
    pdf_file = io.BytesIO(pdf_bytes)
    reader = pypdf.PdfReader(pdf_file)
    extracted_text = ""
    for page in reader.pages:
        text = page.extract_text()
        if text:
            extracted_text += text + "\n"
    return extracted_text

# Input Options Tab Bar
tab1, tab2, tab3 = st.tabs(["🌐 PDF Web Link", "📁 Upload PDF", "✍️ Paste Text"])

agenda_text = ""

with tab1:
    pdf_url = st.text_input("Paste URL to Agenda PDF:", placeholder="https://example.gov/agendas/meeting_sept.pdf")
    if pdf_url:
        try:
            res = requests.get(pdf_url, timeout=10)
            if res.status_code == 200:
                extracted = extract_text_from_pdf_bytes(res.content)
                if extracted.strip():
                    agenda_text = extracted
                    st.success("Successfully fetched and read PDF from URL!")
                else:
                    st.error("Fetched PDF appears to be empty or image-only.")
            else:
                st.error(f"Failed to fetch PDF (HTTP Status {res.status_code}).")
        except Exception as e:
            st.error(f"Error fetching URL: {e}")

with tab2:
    uploaded_file = st.file_uploader("Upload Agenda PDF File", type=["pdf"])
    if uploaded_file:
        try:
            extracted = extract_text_from_pdf_bytes(uploaded_file.read())
            if extracted.strip():
                agenda_text = extracted
                st.success("PDF uploaded and processed successfully!")
            else:
                st.error("Uploaded PDF appears to be empty or image-only.")
        except Exception as e:
            st.error(f"Error reading uploaded PDF: {e}")

with tab3:
    pasted_text = st.text_area("Paste Agenda Text:", height=180, placeholder="Paste agenda items here...")
    if pasted_text.strip():
        agenda_text = pasted_text

# PDF Card Generation Function
def create_pdf(bingo_matrix):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    
    cell_style = ParagraphStyle(
        'CellText',
        parent=styles['Normal'],
        fontSize=8,
        leading=10,
        alignment=1 # Center text
    )
    
    formatted_data = []
    headers = [Paragraph("<b>B</b>", cell_style), Paragraph("<b>I</b>", cell_style), 
               Paragraph("<b>N</b>", cell_style), Paragraph("<b>G</b>", cell_style), Paragraph("<b>O</b>", cell_style)]
    formatted_data.append(headers)
    
    for row in bingo_matrix:
        formatted_row = []
        for cell in row:
            formatted_row.append(Paragraph(cell, cell_style))
        formatted_data.append(formatted_row)
        
    table = Table(formatted_data, colWidths=[100]*5, rowHeights=[30] + [90]*5)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2E7D32')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('GRID', (0,0), (-1,-1), 1, colors.black),
        ('BACKGROUND', (2,3), (2,3), colors.HexColor('#FFF9C4')), # Highlight FREE SPACE
    ]))
    
    story = [
        Paragraph("<b>WILDLIFE BOARD BINGO</b>", styles['Title']),
        Spacer(1, 12),
        table
    ]
    doc.build(story)
    buffer.seek(0)
    return buffer

# Generate Action
if st.button("Generate Bingo Card", type="primary"):
    if not agenda_text.strip():
        st.warning("Please provide a valid PDF URL, upload a PDF, or paste text first!")
    else:
        with st.spinner("AI is analyzing the agenda and crafting bingo tropes..."):
            try:
                client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
                
                prompt = f"""
                You are generating bingo cards for a state Board of Wildlife Resources meeting.
                Analyze the following meeting agenda:
                
                {agenda_text}

                Return EXACTLY 24 short, humorous, realistic phrases (max 6 words each) representing recurring public comment tropes, technical glitches, or specific topics found in this agenda.
                Return ONLY a raw JSON array of 24 strings. Example: ["Phrase 1", "Phrase 2", ...]
                """

                response = client.models.generate_content(
                    model='gemini-3.6-flash',
                    contents=prompt,
                )
                
                # Clean JSON Output
                raw_json = response.text.strip().replace("```json", "").replace("```", "")
                phrases = json.loads(raw_json)
                random.shuffle(phrases)
                
                # Build Matrix
                matrix = []
                idx = 0
                for r in range(5):
                    row = []
                    for c in range(5):
                        if r == 2 and c == 2:
                            row.append("<b>FREE SPACE</b>")
                        else:
                            row.append(phrases[idx])
                            idx += 1
                    matrix.append(row)
                
                st.success("Bingo Card Ready!")
                
                # Display Preview Grid
                st.subheader("Your Generated Card")
                st.table(matrix)
                
                # Download Button
                pdf_data = create_pdf(matrix)
                st.download_button(
                    label="📄 Download Printable PDF",
                    data=pdf_data,
                    file_name="wildlife_board_bingo.pdf",
                    mime="application/pdf"
                )
                
            except Exception as e:
                st.error(f"Something went wrong: {e}")