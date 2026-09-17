import streamlit as st
import json
import random
import io
import re
import requests
import pypdf
from bs4 import BeautifulSoup
from google import genai
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from tenacity import retry, stop_after_attempt, wait_random_exponential

# Page Setup
st.set_page_config(page_title="Utah Wildlife Board Bingo", layout="centered")

UTAH_MEETINGS_URL = "https://wildlife.utah.gov/meetings"

# --- CORE PUBLIC BOARD TROPES ---
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

# High-contrast Black & White Styling
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

st.title("🏔️ Utah Wildlife Board Bingo")
st.write("Generates instant 5x5 Bingo cards automatically using official meeting documents from Utah DWR.")

# API Key Check
if "GEMINI_API_KEY" not in st.secrets:
    st.error("Missing Gemini API Key in Streamlit Secrets!")
    st.stop()

# Helper function to extract dates from text or URLs
def extract_date_from_string(text):
    date_match = re.search(r'(?:\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})|(?:\d{4}[-_\.]\d{2}[-_\.]\d{2})|(?:\d{1,2}[-_\.]\d{1,2}[-_\.]\d{2,4})', text, re.IGNORECASE)
    return date_match.group(0) if date_match else "Upcoming / General Meetings"

# Date-grouped scraper for Agendas, Packets, and Feedback
@st.cache_data(ttl=43200)
def discover_utah_docs_by_date():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    grouped_dates = {}
    
    try:
        response = requests.get(UTAH_MEETINGS_URL, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, "html.parser")
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"].lower()
                text = a_tag.text.strip()
                combined_target = f"{href} {text.lower()}"
                
                if href.endswith(".pdf"):
                    doc_type = None
                    if "agenda" in combined_target:
                        doc_type = "Agenda"
                    elif "packet" in combined_target:
                        doc_type = "Packet"
                    elif "feedback" in combined_target:
                        doc_type = "Feedback"
                    
                    if doc_type:
                        full_url = a_tag["href"] if a_tag["href"].startswith("http") else f"https://wildlife.utah.gov{a_tag['href']}"
                        parent_text = a_tag.parent.text if a_tag.parent else ""
                        detected_date = extract_date_from_string(f"{text} {parent_text} {href}")
                        
                        if detected_date not in grouped_dates:
                            grouped_dates[detected_date] = {}
                        grouped_dates[detected_date][doc_type] = full_url
    except Exception:
        pass
    
    if not grouped_dates:
        grouped_dates["Default Board Meeting"] = {
            "Agenda": "https://wildlife.utah.gov/pdf/meetings/2026_schedule.pdf"
        }
        
    return grouped_dates

# Download raw binary for direct document downloading
def download_pdf_bytes(pdf_url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        res = requests.get(pdf_url, headers=headers, timeout=10)
        if res.status_code == 200:
            return res.content
    except Exception:
        pass
    return None

# Extract text from PDF bytes
def extract_pdf_text_from_bytes(pdf_bytes):
    try:
        pdf_file = io.BytesIO(pdf_bytes)
        reader = pypdf.PdfReader(pdf_file)
        extracted_text = ""
        max_pages = min(len(reader.pages), 5)
        for i in range(max_pages):
            text = reader.pages[i].extract_text()
            if text:
                extracted_text += text + "\n"
        return extracted_text[:3000]
    except Exception:
        return ""

# Retry Wrapper for Gemini API
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
def create_multi_card_pdf(matrices_list, doc_title):
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
    footer_style = ParagraphStyle(
        'BWFooter', parent=styles['Normal'],
        fontName='Helvetica', fontSize=8, leading=10,
        textColor=colors.black, alignment=1
    )

    story = []
    total_cards = len(matrices_list)

    for card_idx, matrix in enumerate(matrices_list):
        formatted_data = []
        headers = [Paragraph(f"<b>{letter}</b>", header_letter_style) for letter in ["B", "I", "N", "G", "O"]]
        formatted_data.append(headers)

        for row_idx, row in enumerate(matrix):
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

        story.append(Paragraph("<b>UTAH WILDLIFE BOARD BINGO</b>", title_style))
        story.append(Spacer(1, 4))
        story.append(Paragraph(f"Mark each square live during the meeting. • Date: {doc_title} • Card #{card_idx + 1}", subtitle_style))
        story.append(Spacer(1, 12))
        story.append(table)
        story.append(Spacer(1, 10))
        story.append(Paragraph("Official Meeting Bingo Card • 5 in a row horizontally, vertically, or diagonally wins", footer_style))

        if card_idx < total_cards - 1:
            story.append(PageBreak())

    doc.build(story)
    buffer.seek(0)
    return buffer

# Discover grouped documents by date
grouped_docs = discover_utah_docs_by_date()

# UI Layout
st.subheader("1. Select Meeting Date")
selected_date = st.selectbox("Choose meeting date:", list(grouped_docs.keys()))
available_files = grouped_docs[selected_date]

# File Download Options
st.subheader("2. Available Source Documents for Selected Date")
cols = st.columns(3)

file_texts = []
for idx, doc_type in enumerate(["Agenda", "Packet", "Feedback"]):
    with cols[idx]:
        if doc_type in available_files:
            file_bytes = download_pdf_bytes(available_files[doc_type])
            if file_bytes:
                st.download_button(
                    label=f"📥 Download {doc_type}",
                    data=file_bytes,
                    file_name=f"{selected_date}_{doc_type}.pdf",
                    mime="application/pdf"
                )
                text_content = extract_pdf_text_from_bytes(file_bytes)
                if text_content:
                    file_texts.append(f"--- {doc_type.upper()} CONTENT ---\n" + text_content)
        else:
            st.info(f"No {doc_type} PDF")

combined_date_text = "\n\n".join(file_texts)

st.subheader("3. Card Quantity")
num_cards = st.number_input("How many unique Bingo cards do you want to generate?", min_value=1, max_value=20, value=1, step=1)

# Generation Action
if st.button("🎲 Generate Bingo Cards", type="primary"):
    with st.spinner(f"Analyzing all documents for {selected_date} and generating {num_cards} card(s)..."):
        try:
            client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

            ai_phrases = []
            if combined_date_text.strip():
                prompt = f"""
                You are generating bingo cards for Utah Wildlife Board / RAC meetings.
                Analyze this combined text extracted from official meeting documents for {selected_date}:
                
                {combined_date_text[:4000]}

                Generate EXACTLY 16 BROADER, SHORT, EASY-TO-TRIGGER phrases (max 2-4 words each) based on topics in this agenda/packet or common public comment habits.
                
                CRITICAL FORMATTING RULES:
                1. If spoken/yelled out by a person, wrap in quotes: "Spoken Phrase"
                2. If an action, general topic, or fact, wrap in bold: <b>Action or Topic</b>
                
                Return ONLY a raw JSON array of 16 strings.
                """

                response = call_gemini_with_retry(client, prompt)
                
                if response and hasattr(response, 'text') and response.text:
                    try:
                        raw_json = response.text.strip().replace("```json", "").replace("```", "")
                        parsed_list = json.loads(raw_json)
                        if isinstance(parsed_list, list):
                            ai_phrases = [str(x) for x in parsed_list if isinstance(x, str)]
                        else:
                            ai_phrases = list(FALLBACK_AI_TROPES)
                    except Exception:
                        ai_phrases = list(FALLBACK_AI_TROPES)
                else:
                    ai_phrases = list(FALLBACK_AI_TROPES)
            else:
                ai_phrases = list(FALLBACK_AI_TROPES)

            # Strict integer count safeguard
            count_ai = int(len(ai_phrases))
            if count_ai < 16:
                needed = 16 - count_ai
                ai_phrases.extend(FALLBACK_AI_TROPES[:needed])

            all_phrases_pool = list(HARDCODED_CORE_TROPES) + list(ai_phrases)

            # Generate N unique matrices
            generated_matrices = []
            card_count_int = int(num_cards)
            for i in range(card_count_int):
                current_pool = list(all_phrases_pool[:24])
                random.shuffle(current_pool)
                
                matrix = []
                idx = 0
                for r in range(5):
                    row = []
                    for c in range(5):
                        if r == 2 and c == 2:
                            row.append("FREE SPACE")
                        else:
                            row.append(current_pool[idx])
                            idx += 1
                    matrix.append(row)
                generated_matrices.append(matrix)

            st.success(f"{num_cards} Bingo Card(s) Ready!")

            # Preview Card #1
            st.subheader("Card #1 Preview")
            html_grid = ['<div class="bingo-grid">']
            for letter in ["B", "I", "N", "G", "O"]:
                html_grid.append(f'<div class="bingo-header">{letter}</div>')
            for r_i, row in enumerate(generated_matrices[0]):
                for c_i, cell in enumerate(row):
                    if r_i == 2 and c_i == 2:
                        html_grid.append('<div class="bingo-cell bingo-free">FREE SPACE<br/><small>Timer Beep</small></div>')
                    else:
                        html_grid.append(f'<div class="bingo-cell">{cell}</div>')
            html_grid.append('</div>')

            st.markdown("".join(html_grid), unsafe_allow_html=True)

            # Download Multipage PDF
            pdf_data = create_multi_card_pdf(generated_matrices, selected_date)
            st.download_button(
                label=f"📄 Download Printable PDF ({num_cards} Card{'s' if num_cards > 1 else ''})",
                data=pdf_data,
                file_name=f"utah_wildlife_bingo_{selected_date}.pdf",
                mime="application/pdf"
            )

        except Exception as e:
            st.error(f"Something went wrong: {e}")