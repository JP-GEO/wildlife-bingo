import streamlit as st
import json
import random
import io
import requests
import pypdf
from google import genai
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from tenacity import retry, stop_after_attempt, wait_random_exponential

# Page Setup
st.set_page_config(page_title="Wildlife Board Bingo", layout="centered")

# --- CORE HARDCODED TROPES ---
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

st.title("Board of Wildlife Resources Bingo")
st.write("Generate printable 5x5 square Bingo cards from any meeting agenda PDF or text.")

# API Key Check
if "GEMINI_API_KEY" not in st.secrets:
    st.error("Missing Gemini API Key in Streamlit Secrets!")
    st.stop()

# Helper function to extract text from PDF bytes
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
    pdf_url = st.text_input("Paste URL to Agenda PDF:", placeholder="https://wildlife.utah.gov/pdf/meetings/agenda.pdf")
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
    pasted_text = st.text_area("Paste Agenda Text:", height=180, placeholder="Paste meeting agenda items here...")
    if pasted_text.strip():
        agenda_text = pasted_text

# Card Quantity
num_cards = st.number_input("How many unique Bingo cards do you want to print?", min_value=1, max_value=20, value=1, step=1)

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
def create_multi_card_pdf(matrices_list):
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

        story.append(Paragraph("<b>BOARD OF WILDLIFE RESOURCES BINGO</b>", title_style))
        story.append(Spacer(1, 4))
        story.append(Paragraph(f"Mark each square live during the meeting. • Card #{card_idx + 1}", subtitle_style))
        story.append(Spacer(1, 12))
        story.append(table)
        story.append(Spacer(1, 10))
        story.append(Paragraph("Official Meeting Bingo Card • 5 in a row horizontally, vertically, or diagonally wins", footer_style))

        if card_idx < total_cards - 1:
            story.append(PageBreak())

    doc.build(story)
    buffer.seek(0)
    return buffer


# --- GENERATION TRIGGER ---
if st.button("🎲 Generate Bingo Cards", type="primary"):
    if not agenda_text.strip():
        st.warning("Please provide an agenda first (paste URL, upload PDF, or paste text)!")
    else:
        with st.spinner("Analyzing agenda and crafting card(s)..."):
            try:
                client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])

                prompt = f"""
                You are generating bingo cards for a state Board of Wildlife Resources meeting.
                Analyze the following meeting agenda:
                
                {agenda_text[:4000]}

                Return EXACTLY 16 short, easy-to-trigger phrases (2-4 words each) representing meeting tropes, audience comments, or specific topics found in this agenda.
                
                CRITICAL FORMATTING RULES FOR PHRASES:
                1. If a phrase is something spoken/yelled out by a person, wrap in quotation marks: "Spoken Phrase"
                2. If a phrase is an action or topic, wrap in HTML bold tags: <b>Action or Topic</b>
                
                Return ONLY a raw JSON array of 16 strings.
                """

                response = call_gemini_with_retry(client, prompt)
                
                ai_phrases = []
                if response and hasattr(response, 'text') and response.text:
                    try:
                        raw_json = response.text.strip().replace("```json", "").replace("```", "")
                        parsed = json.loads(raw_json)
                        if isinstance(parsed, list):
                            ai_phrases = [str(x) for x in parsed if isinstance(x, str)]
                    except Exception:
                        ai_phrases = list(FALLBACK_AI_TROPES)
                else:
                    ai_phrases = list(FALLBACK_AI_TROPES)

                # Ensure 16 phrases
                if len(ai_phrases) < 16:
                    needed = 16 - len(ai_phrases)
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

                # Download PDF
                pdf_data = create_multi_card_pdf(generated_matrices)
                st.download_button(
                    label=f"📄 Download Printable PDF ({num_cards} Card{'s' if num_cards > 1 else ''})",
                    data=pdf_data,
                    file_name="wildlife_board_bingo_set.pdf",
                    mime="application/pdf"
                )

            except Exception as e:
                st.error(f"Something went wrong: {e}")