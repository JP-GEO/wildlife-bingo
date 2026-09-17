import streamlit as st
import json
import random
import io
from google import genai
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

# Page Setup
st.set_page_config(page_title="Wildlife Board Bingo", layout="centered")
st.title("🌲 Wildlife Board Meeting Bingo")
st.write("Paste the upcoming meeting agenda below to generate a bingo card!")

# API Key Check
if "GEMINI_API_KEY" not in st.secrets:
    st.error("Missing Gemini API Key in Streamlit Secrets!")
    st.stop()

# User Input
agenda_text = st.text_area("Meeting Agenda Text:", height=200, placeholder="Paste agenda items here...")

# PDF Generation Function
def create_pdf(bingo_matrix):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    
    cell_style = ParagraphStyle(
        'CellText',
        parent=styles['Normal'],
        fontSize=9,
        leading=11,
        alignment=1 # Center text
    )
    
    # Convert text to wrapped Paragraphs
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
        st.warning("Please paste an agenda first!")
    else:
        with st.spinner("AI is crafting your bingo tropes..."):
            try:
                # Call Gemini API using google-genai SDK
                client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
                
                prompt = f"""
                You are generating bingo cards for a state Board of Wildlife Resources meeting.
                Analyze this agenda:
                {agenda_text}

                Return EXACTLY 24 short, humorous, realistic phrases (max 6 words each) representing recurring public comment tropes, technical glitches, or topics specific to this agenda.
                Return ONLY a raw JSON array of 24 strings.
                """
                
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt,
                )
                
                # Parse JSON
                raw_json = response.text.strip().replace("```json", "").replace("```", "")
                phrases = json.loads(raw_json)
                random.shuffle(phrases)
                
                # Build 5x5 Grid
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
                
                st.success("Card Generated!")
                
                # Display Grid preview on web app
                st.table(matrix)
                
                # Download Button
                pdf_data = create_pdf(matrix)
                st.download_button(
                    label="📄 Download Printable PDF",
                    data=pdf_data,
                    file_name="wildlife_bingo.pdf",
                    mime="application/pdf"
                )
                
            except Exception as e:
                st.error(f"Something went wrong: {e}")