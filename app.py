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
from tenacity import retry, stop_after_attempt, wait_random_exponential

# Page Setup
st.set_page_config(page_title="Wildlife Board Bingo", layout="centered")

# Custom CSS for crisp Black & White on-screen bingo grid
st.markdown("""
<style>
    .bingo-grid {
        display: grid;
        grid-template-columns: repeat(5, 1fr);
        gap: 6px;
        background-color: #000000;
        padding: 8px;
        border: 2px solid #000000;
        margin: 20px 0;
    }
    .bingo-header {
        background-color: #000000;
        color: #ffffff;
        font-weight: 900;
        font-size: 22px;
        text-align: center;
        padding: 8px 0;
        font-family: Arial, sans-serif;
    }
    .bingo-cell {
        background-color: #ffffff;
        color: #000000;
        font-size: 11px;
        text-align: center;
        aspect-ratio: 1 / 1;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 6px;
        line-height: 1.2;
        font-family: Arial, sans-serif;
    }
    .bingo-free {
        background-color: #f0f0f0 !important;
        font-weight: 900;
    }
</style>
""", unsafe_allow_html=True)

st.title("Board of Wildlife Resources Bingo")
st.write("Generate a printable, high-contrast 5x5 square Bingo card from any meeting agenda.")

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

# Retry function to handle 503 high-demand errors gracefully
@retry(
    wait=wait_random_exponential(min=1, max=10),
    stop=stop_after_attempt(3),
    retry_error_callback=lambda retry_state: None
)
def call_gemini_with_retry(client, prompt):
    return client.models.generate_content(
        model='gemini-3.6-flash',
        contents=prompt,
    )

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


# --- HIGH-CONTRAST BLACK & WHITE PRINTABLE PDF CREATOR ---
def create_bw_square_pdf(bingo_matrix):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=51,
        leftMargin=51,
        topMargin=36,
        bottomMargin=36
    )
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'BWTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=22,
        leading=26,
        textColor=colors.black,
        alignment=1
    )

    subtitle_style = ParagraphStyle(
        'BWSubTitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=13,
        textColor=colors.black,
        alignment=1
    )

    header_letter_style = ParagraphStyle(
        'BingoHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=20,
        textColor=colors.white,
        alignment=1
    )

    cell_style = ParagraphStyle(
        'SquareCellText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11,
        textColor=colors.black,
        alignment=1
    )

    free_space_style = ParagraphStyle(
        'FreeSpaceText',
        parent=cell_style,
        fontName='Helvetica-Bold',
        fontSize=9.5,
        leading=12,
        textColor=colors.black
    )

    formatted_data = []
    headers = [Paragraph(f"<b>{letter}</b>", header_letter_style) for letter in ["B", "I", "N", "G", "O"]]
    formatted_data.append(headers)

    for row_idx, row in enumerate(bingo_matrix):
        formatted_row = []
        for col_idx, cell in enumerate(row):
            if row_idx == 2 and col_idx == 2:
                formatted_row.append(Paragraph("<b>FREE SPACE<br/><font size=6.5>PUBLIC COMMENT BEEP</font></b>", free_space_style))
            else:
                formatted_row.append(Paragraph(cell, cell_style))
        formatted_data.append(formatted_row)

    cell_w = 102
    cell_h = 100
    table = Table(
        formatted_data,
        colWidths=[cell_w] * 5,
        rowHeights=[34] + [cell_h] * 5
    )

    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('RIGHTPADDING', (0, 0), (-1, -1), 6),
        ('INNERGRID', (0, 0), (-1, -1), 1, colors.black),
        ('BOX', (0, 0), (-1, -1), 2, colors.black),
        ('BACKGROUND', (2, 3), (2, 3), colors.HexColor('#E5E5E5')),
    ]))

    footer_style = ParagraphStyle(
        'BWFooter',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=10,
        textColor=colors.black,
        alignment=1
    )

    story = [
        Paragraph("<b>BOARD OF WILDLIFE RESOURCES BINGO</b>", title_style),
        Spacer(1, 4),
        Paragraph("Mark each square as it happens live during the meeting.", subtitle_style),
        Spacer(1, 14),
        table,
        Spacer(1, 12),
        Paragraph("Official Meeting Bingo Card • 5 in a row horizontally, vertically, or diagonally wins", footer_style)
    ]

    doc.build(story)
    buffer.seek(0)
    return buffer


# --- GENERATION BLOCK ---
if st.button("Generate Bingo Card", type="primary"):
    if not agenda_text.strip():
        st.warning("Please provide an agenda first (paste URL, upload PDF, or paste text)!")
    else:
        with st.spinner("Analyzing agenda and generating meeting tropes..."):
            try:
                client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

                prompt = f"""
                You are generating bingo cards for a state Board of Wildlife Resources meeting.
                Analyze the following meeting agenda:
                
                {agenda_text}

                Return EXACTLY 24 short, humorous, realistic bingo phrases (max 5-6 words each) representing recurring tropes, audience comments, or agenda topics.
                
                CRITICAL FORMATTING RULES FOR PHRASES:
                1. If a phrase is something spoken or yelled out by a person (e.g. Can you hear me now?, I've been hunting here 40 years), wrap it in quotation marks: "Spoken Phrase"
                2. If a phrase is an action, physical behavior, or fact (e.g. Board member sleeps, Audio cuts out, CWD debate), wrap it in HTML bold tags: <b>Action or Fact</b>
                
                Return ONLY a raw JSON array of 24 strings using this exact formatting.
                Example format: ["\"Can you hear me?\"", "<b>Audio cuts out</b>", "\"I have a question\"", "<b>Public comment beep</b>"]
                """

                # Executing Gemini call with retry protection
                response = call_gemini_with_retry(client, prompt)

                raw_json = response.text.strip().replace("```json", "").replace("```", "")
                phrases = json.loads(raw_json)
                random.shuffle(phrases)

                # 5x5 Matrix construction
                matrix = []
                idx = 0
                for r in range(5):
                    row = []
                    for c in range(5):
                        if r == 2 and c == 2:
                            row.append("FREE SPACE")
                        else:
                            row.append(phrases[idx])
                            idx += 1
                    matrix.append(row)

                st.success("Bingo Card Ready!")

                # B&W On-Screen Card Preview
                html_grid = ['<div class="bingo-grid">']
                for letter in ["B", "I", "N", "G", "O"]:
                    html_grid.append(f'<div class="bingo-header">{letter}</div>')
                for r_i, row in enumerate(matrix):
                    for c_i, cell in enumerate(row):
                        if r_i == 2 and c_i == 2:
                            html_grid.append('<div class="bingo-cell bingo-free">FREE SPACE<br/><small>Timer Beep</small></div>')
                        else:
                            html_grid.append(f'<div class="bingo-cell">{cell}</div>')
                html_grid.append('</div>')

                st.markdown("".join(html_grid), unsafe_allow_html=True)

                # Download PDF Button
                pdf_data = create_bw_square_pdf(matrix)
                st.download_button(
                    label="📄 Download Printable PDF (Black & White)",
                    data=pdf_data,
                    file_name="wildlife_board_bingo.pdf",
                    mime="application/pdf"
                )

            except Exception as e:
                st.error(f"Something went wrong: {e}")