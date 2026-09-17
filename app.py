import streamlit as st
import json
import random
import io
import requests
import pypdf
from datetime import datetime
from dateutil import parser
from google import genai
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from tenacity import retry, stop_after_attempt, wait_random_exponential

# Page Setup
st.set_page_config(page_title="Wildlife Board Bingo", layout="centered")

# --- HARDCODED BACKEND CONFIGURATION ---
DEFAULT_AGENDA_URL = "https://wildlife.utah.gov/pdf/meetings/board/2026-09-17-board-packet.pdf"

# 8 Guaranteed Core Tropes
HARDCODED_CORE_TROPES = [
    "\"Can you hear me now?\"",
    "<b>Interrupted mid-sentence</b>",
    "<b>Unsolicited history lesson</b>",
    "<b>Microphone feedback screech</b>",
    "\"...I've hunted here for x # years...\"",
    "<b>Speaker starts tearing up</b>",
    "<b>***Technical difficulties***</b>",
    "\"With all due respect...\""
]

# 16 Fallback Tropes in case AI response is empty or blocked
FALLBACK_AI_TROPES = [
    "<b>I dont have those numbers</b>",
    "\"I have a quick question\"",
    "<b>Dog hunting debate</b>",
    "<b>Public commenter over time</b>",
    "<b>Slide deck unreadable</b>",
    "\"Back in the good old days\"",
    "<b>Bag limit adjustment</b>",
    "<b>...family hunting anecdote...</b>",
    "\"We need to look that up\"",
    "<b>Boat ramp access fees</b>",
    "<b>Dramatic sigh in mic</b>",
    "\"I move to approve\"",
    "<b>I second the motion</b>",
    "\"Is this item open?\"",
    "<b>Background *coughing*</b>",
    "<b>Presenter mixes up their slides</b>"
]

# High-contrast Black & White styling
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
    .stButton>button {
        width: 100%;
        font-size: 18px !important;
        font-weight: bold !important;
        padding: 12px !important;
    }
</style>
""", unsafe_allow_html=True)

st.title("Board of Wildlife Resources Bingo")
st.write("Click the button below to generate a printable 5x5 square Bingo card for today's meeting.")

# API Key Check
if "GEMINI_API_KEY" not in st.secrets:
    st.error("Missing Gemini API Key in Streamlit Secrets!")
    st.stop()

# Helper function to extract text and last modified date
def get_agenda_content_and_date(url):
    try:
        res = requests.get(url, timeout=10)
        if res.status_code == 200:
            pdf_file = io.BytesIO(res.content)
            reader = pypdf.PdfReader(pdf_file)
            
            text = ""
            for page in reader.pages:
                t = page.extract_text()
                if t:
                    text += t + "\n"
                    
            doc_date = None
            if reader.metadata:
                raw_date = reader.metadata.get('/ModDate') or reader.metadata.get('/CreationDate')
                if raw_date:
                    try:
                        clean_d = raw_date.replace("D:", "")[:8]
                        doc_date = datetime.strptime(clean_d, "%Y%m%d").strftime("%B %d, %Y")
                    except Exception:
                        doc_date = None
                        
            if not doc_date and res.headers.get('Last-Modified'):
                try:
                    doc_date = parser.parse(res.headers.get('Last-Modified')).strftime("%B %d, %Y")
                except Exception:
                    doc_date = None
                    
            return text, doc_date or datetime.now().strftime("%B %d, %Y")
    except Exception:
        pass
    return "", datetime.now().strftime("%B %d, %Y")

# Retry wrapper for API calls
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

# PDF Creator
def create_bw_square_pdf(bingo_matrix, last_updated_str):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        rightMargin=51, leftMargin=51, topMargin=36, bottomMargin=36
    )
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'BWTitle', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=20, leading=24,
        textColor=colors.black, alignment=1
    )
    subtitle_style = ParagraphStyle(
        'BWSubTitle', parent=styles['Normal'],
        fontName='Helvetica', fontSize=9.5, leading=12,
        textColor=colors.black, alignment=1
    )
    header_letter_style = ParagraphStyle(
        'BingoHeader', parent=styles['Normal'],
        fontName='Helvetica-Bold', fontSize=18, leading=20,
        textColor=colors.white, alignment=1
    )
    cell_style = ParagraphStyle(
        'SquareCellText', parent=styles['Normal'],
        fontName='Helvetica', fontSize=8.5, leading=11,
        textColor=colors.black, alignment=1
    )
    free_space_style = ParagraphStyle(
        'FreeSpaceText', parent=cell_style,
        fontName='Helvetica-Bold', fontSize=9.5, leading=12,
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

    table = Table(formatted_data, colWidths=[102]*5, rowHeights=[34] + [100]*5)
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
        'BWFooter', parent=styles['Normal'],
        fontName='Helvetica', fontSize=8, leading=10,
        textColor=colors.black, alignment=1
    )

    story = [
        Paragraph("<b>BOARD OF WILDLIFE RESOURCES BINGO</b>", title_style),
        Spacer(1, 4),
        Paragraph(f"Mark each square live during the meeting. • Agenda Last Updated: {last_updated_str}", subtitle_style),
        Spacer(1, 12),
        table,
        Spacer(1, 10),
        Paragraph("Official Meeting Bingo Card • 5 in a row horizontally, vertically, or diagonally wins", footer_style)
    ]

    doc.build(story)
    buffer.seek(0)
    return buffer


# --- SINGLE BUTTON GENERATION ---
if st.button("🎲 Generate Bingo Card", type="primary"):
    with st.spinner("Fetching latest agenda and crafting card..."):
        try:
            agenda_text, last_updated_date = get_agenda_content_and_date(DEFAULT_AGENDA_URL)
            client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
            
            prompt = f"""
            You are generating bingo cards for a state Board of Wildlife Resources meeting.
            Analyze the following meeting agenda:
            
            {agenda_text[:4000]}

            Generate EXACTLY 16 BROADER, SHORT, EASY-TO-TRIGGER phrases (max 2-4 words each) based on the topics in this agenda or common public comment habits.
            
            CRITICAL FORMATTING RULES:
            1. If spoken/yelled out by a person, wrap in quotes: "Spoken Phrase"
            2. If an action, general topic, or fact, wrap in bold: <b>Action or Topic</b>
            
            Return ONLY a raw JSON array of 16 strings.
            Example format: ["\"I disagree\"", "<b>CWD mentioned</b>", "<b>Dog hunting debate</b>", "\"Quick question\""]
            """

            response = call_gemini_with_retry(client, prompt)
            
            # Safe extraction check
            ai_phrases = []
            if response and hasattr(response, 'text') and response.text:
                try:
                    raw_json = response.text.strip().replace("```json", "").replace("```", "")
                    ai_phrases = json.loads(raw_json)
                except Exception:
                    ai_phrases = FALLBACK_AI_TROPES
            else:
                ai_phrases = FALLBACK_AI_TROPES

            # Fallback if fewer than 16 phrases returned
            if len(ai_phrases) < 16:
                ai_phrases.extend(FALLBACK_AI_TROPES[:(16 - len(ai_phrases))])

            # Combine 8 Hardcoded Core Tropes + 16 AI Agenda Phrases
            all_phrases = HARDCODED_CORE_TROPES + ai_phrases
            selected_phrases = all_phrases[:24]
            random.shuffle(selected_phrases)

            # Build 5x5 Matrix
            matrix = []
            idx = 0
            for r in range(5):
                row = []
                for c in range(5):
                    if r == 2 and c == 2:
                        row.append("FREE SPACE")
                    else:
                        row.append(selected_phrases[idx])
                        idx += 1
                matrix.append(row)

            st.success(f"Bingo Card Ready! (Agenda Updated: {last_updated_date})")

            # On-Screen Preview
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

            # Download PDF
            pdf_data = create_bw_square_pdf(matrix, last_updated_date)
            st.download_button(
                label="📄 Download Printable PDF",
                data=pdf_data,
                file_name="wildlife_board_bingo.pdf",
                mime="application/pdf"
            )

        except Exception as e:
            st.error(f"Something went wrong: {e}")