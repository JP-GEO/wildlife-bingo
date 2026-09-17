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

# --- CORE HARDCODED PUBLIC BOARD TROPES (8 Guaranteed Items) ---
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

# --- ARCHIVED HISTORICAL PUBLIC FEEDBACK COMMENTS ---
HISTORICAL_FEEDBACK_ARCHIVE = [
    "\"Opposes tag reduction\"",
    "<b>Archery optics debate</b>",
    "<b>Wasatch elk permit dispute</b>",
    "<b>Shed hunting fee objection</b>",
    "<b>Cougar hound hunting argument</b>",
    "\"Requests more youth tags\"",
    "<b>Trail camera ban pushback</b>",
    "<b>CWD management dispute</b>",
    "<b>Water rights complaint</b>",
    "\"I move to table this\"",
    "<b>Non-resident quota debate</b>",
    "<b>Walk-in access funding</b>",
    "\"Public comment timer beep\"",
    "<b>Over-grazing accusation</b>",
    "<b>Private landowner tag dispute</b>",
    "<b>Bighorn sheep buffer rule</b>"
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
st.write("Generates randomized Bingo cards from current and historical DWR public comment feedback.")

if "GEMINI_API_KEY" not in st.secrets:
    st.error("Missing Gemini API Key in Streamlit Secrets!")
    st.stop()

def extract_flexible_date(text_context):
    pattern = r'(?:\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2}(?:\s*[-–&]\s*\d{1,2})?,?\s*(?:\d{4})?)|(?:\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4})'
    match = re.search(pattern, text_context, re.IGNORECASE)
    if match:
        return match.group(0).strip()
    return None

# Scraper prioritizing Feedback, Public Comment, and RAC Summary Documents
@st.cache_data(ttl=43200)
def discover_feedback_documents_only():
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    documents_map = {}
    target_keywords = ["feedback", "comment", "summary", "recommendations"]
    
    try:
        response = requests.get(UTAH_MEETINGS_URL, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, "html.parser")
            
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"]
                href_lower = href.lower()
                link_text = a_tag.text.strip()
                link_text_lower = link_text.lower()
                
                if href_lower.endswith(".pdf"):
                    combined_target = f"{href_lower} {link_text_lower}"
                    if any(kw in combined_target for kw in target_keywords):
                        full_url = href if href.startswith("http") else f"https://wildlife.utah.gov{href}"
                        
                        parent = a_tag.find_parent(["tr", "li", "p", "div"])
                        parent_text = parent.text.strip() if parent else ""
                        heading = a_tag.find_previous(["h2", "h3", "h4"])
                        heading_text = heading.text.strip() if heading else ""
                        
                        combined_context = f"{link_text} {parent_text} {heading_text} {href}"
                        detected_date = extract_flexible_date(combined_context)
                        
                        doc_label = link_text if len(link_text) > 3 else "Public Feedback PDF"
                        
                        if detected_date:
                            display_key = f"💬 {detected_date} — {doc_label}"
                        elif heading_text:
                            display_key = f"📌 {heading_text[:30]} — {doc_label}"
                        else:
                            display_key = f"📄 {doc_label}"
                            
                        documents_map[display_key] = full_url

    except Exception:
        pass
    
    if not documents_map:
        documents_map["💬 Public Feedback & RAC Summary PDF"] = "https://wildlife.utah.gov/pdf/meetings/2026_schedule.pdf"
        
    return documents_map

def download_pdf_bytes(pdf_url):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        res = requests.get(pdf_url, headers=headers, timeout=10)
        if res.status_code == 200:
            return res.content
    except Exception:
        pass
    return None

def extract_pdf_text_from_bytes(pdf_bytes):
    try:
        pdf_file = io.BytesIO(pdf_bytes)
        reader = pypdf.PdfReader(pdf_file)
        extracted_text = ""
        max_pages = min(len(reader.pages), 10)
        for i in range(max_pages):
            text = reader.pages[i].extract_text()
            if text:
                extracted_text += text + "\n"
        return extracted_text[:6000]
    except Exception:
        return ""

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

def create_multi_card_pdf(matrices_list, doc_title):
    buffer = io.BytesIO()
    
    # Explicit float bounds to fix ReportLab calculation error on Python 3.14
    page_width, page_height = float(letter[0]), float(letter[1])
    
    doc = SimpleDocTemplate(
        buffer,
        pagesize=(page_width, page_height),
        rightMargin=51.0,
        leftMargin=51.0,
        topMargin=36.0,
        bottomMargin=36.0
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
        fontName='Helvetica', fontSize=8, leading=10,
        textColor=colors.black, alignment=1
    )
    free_space_style = ParagraphStyle(
        'FreeSpaceText', parent=cell_style,
        fontName='Helvetica-Bold', fontSize=9, leading=11,
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

        table = Table(formatted_data, colWidths=[100]*5, rowHeights=[30] + [95]*5)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.black),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('INNERGRID', (0, 0), (-1, -1), 1, colors.black),
            ('BOX', (0, 0), (-1, -1), 2, colors.black),
            ('BACKGROUND', (2, 3), (2, 3), colors.HexColor('#E5E5E5')),
        ]))

        story.append(Paragraph("<b>UTAH WILDLIFE BOARD BINGO</b>", title_style))
        story.append(Spacer(1, 4))
        story.append(Paragraph(f"Mark each square live during the meeting. • Source: {doc_title[:45]} • Card #{card_idx + 1} of {total_cards}", subtitle_style))
        story.append(Spacer(1, 10))
        story.append(table)
        story.append(Spacer(1, 8))
        story.append(Paragraph("Official Meeting Bingo Card • 5 in a row horizontally, vertically, or diagonally wins", footer_style))

        if card_idx < total_cards - 1:
            story.append(PageBreak())

    doc.build(story)
    buffer.seek(0)
    return buffer

# --- UI LAYOUT ---
doc_options = discover_feedback_documents_only()

c1, c2 = st.columns([4, 1])
with c1:
    st.subheader("1. Select Feedback Document")
with c2:
    if st.button("🔄 Refresh"):
        st.cache_data.clear()
        st.rerun()

selected_doc_title = st.selectbox("Choose a public feedback document from Utah DWR:", list(doc_options.keys()))
selected_pdf_url = doc_options[selected_doc_title]

st.subheader("2. Source Feedback Document")
pdf_bytes = download_pdf_bytes(selected_pdf_url)

document_text = ""
if pdf_bytes:
    st.download_button(
        label="📥 Download Selected Feedback PDF",
        data=pdf_bytes,
        file_name="selected_utah_dwr_feedback.pdf",
        mime="application/pdf"
    )
    document_text = extract_pdf_text_from_bytes(pdf_bytes)

with st.expander("➕ Optional: Add Custom Public Feedback PDF"):
    custom_pdf = st.file_uploader("Upload a local PDF file instead", type=["pdf"])
    if custom_pdf:
        custom_text = extract_pdf_text_from_bytes(custom_pdf.read())
        if custom_text:
            document_text = custom_text
            st.success("Custom Feedback PDF loaded as primary source!")

st.subheader("3. Card Quantity")
num_cards = st.number_input("How many unique Bingo cards do you want to generate?", min_value=1, max_value=20, value=1, step=1)

if st.button("🎲 Generate Bingo Cards", type="primary"):
    with st.spinner("Analyzing public comments and assembling randomized phrase pool..."):
        try:
            client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

            ai_phrases = []
            if document_text.strip():
                prompt = f"""
                You are generating bingo cards for Utah Wildlife Board / RAC meetings.
                Analyze this public comment feedback summary from Utah DWR:

                ----------------------------------------
                {document_text[:5000]}
                ----------------------------------------

                Extract EXACTLY 20 SPECIFIC public complaints, debate topics, requested rule changes, or hot-button species issues mentioned directly in this feedback document (max 2-4 words each).

                FORMATTING REQUIREMENTS:
                - If a spoken quote: "Spoken Quote"
                - If a regulation/action topic: <b>Topic Name</b>
                
                Return ONLY a raw JSON array of 20 strings.
                """

                response = call_gemini_with_retry(client, prompt)
                if response and hasattr(response, 'text') and response.text:
                    try:
                        raw_json = response.text.strip().replace("```json", "").replace("```", "")
                        parsed_list = json.loads(raw_json)
                        if isinstance(parsed_list, list):
                            ai_phrases = [str(x) for x in parsed_list if isinstance(x, str)]
                    except Exception:
                        ai_phrases = []

            combined_feedback_pool = list(set(ai_phrases + HISTORICAL_FEEDBACK_ARCHIVE))
            
            generated_matrices = []
            card_count_int = int(num_cards)

            for i in range(card_count_int):
                selected_core = list(HARDCODED_CORE_TROPES)
                
                needed_feedback = 16
                if len(combined_feedback_pool) >= needed_feedback:
                    selected_feedback = random.sample(combined_feedback_pool, needed_feedback)
                else:
                    selected_feedback = list(combined_feedback_pool)
                    while len(selected_feedback) < needed_feedback:
                        selected_feedback.append(random.choice(HISTORICAL_FEEDBACK_ARCHIVE))

                card_pool = selected_core + selected_feedback
                random.shuffle(card_pool)

                matrix = []
                idx = 0
                for r in range(5):
                    row = []
                    for c in range(5):
                        if r == 2 and c == 2:
                            row.append("FREE SPACE")
                        else:
                            row.append(card_pool[idx])
                            idx += 1
                    matrix.append(row)
                generated_matrices.append(matrix)

            st.session_state["matrices"] = generated_matrices
            st.session_state["selected_doc"] = selected_doc_title
            st.session_state["card_count"] = card_count_int

        except Exception as e:
            st.error(f"Something went wrong: {e}")

if "matrices" in st.session_state and st.session_state["matrices"]:
    card_count_int = st.session_state["card_count"]
    generated_matrices = st.session_state["matrices"]
    doc_title = st.session_state["selected_doc"]

    st.success(f"{card_count_int} Bingo Card(s) Ready!")

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

    pdf_data = create_multi_card_pdf(generated_matrices, doc_title)
    st.download_button(
        label=f"📄 Download Printable PDF ({card_count_int} Card{'s' if card_count_int > 1 else ''})",
        data=pdf_data,
        file_name="utah_wildlife_bingo.pdf",
        mime="application/pdf"
    )