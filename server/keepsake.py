"""Printable family stories. No credentials or private AI profiles enter exports."""
import io
import os
import threading
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, Image

from .community import media_path
from fastapi import HTTPException

_font_lock = threading.Lock()


def font_name():
    with _font_lock:
        if 'MemorialKorean' in pdfmetrics.getRegisteredFontNames():
            return 'MemorialKorean'
        paths = [os.getenv('MEMORIAL_PDF_FONT', ''), 'C:/Windows/Fonts/malgun.ttf',
                 '/usr/share/fonts/truetype/nanum/NanumGothic.ttf']
        for path in paths:
            if path and Path(path).is_file():
                pdfmetrics.registerFont(TTFont('MemorialKorean', path))
                return 'MemorialKorean'
        pdfmetrics.registerFont(UnicodeCIDFont('HYSMyeongJo-Medium'))
        return 'HYSMyeongJo-Medium'


def make_pdf(data):
    output = io.BytesIO()
    font = font_name()
    body = ParagraphStyle('body', fontName=font, fontSize=10, leading=18, wordWrap='CJK', spaceAfter=10, textColor=colors.HexColor('#304640'))
    heading = ParagraphStyle('heading', parent=body, fontSize=18, leading=28, spaceBefore=20, spaceAfter=16)
    title = ParagraphStyle('title', parent=heading, fontSize=28, leading=40)
    small = ParagraphStyle('small', parent=body, fontSize=8, textColor=colors.HexColor('#64736c'))
    def p(text, style=body):
        return Paragraph(escape(str(text or '')).replace('\n', '<br/>'), style)
    story = [p('기억을 담은 책', title), p('가족이 함께 남긴 소중한 순간과 마음', small), Spacer(1, 24)]
    for person in data['deceased']:
        story += [HRFlowable(width='100%', color=colors.HexColor('#d9ded7')), p(person['name']+' 님', heading),
                  p(f"{person['birth_date']} — {person['death_date']}", small)]
        memories = [r for r in data['memories'] if r['deceased_id'] == person['id']]
        if not memories:
            story.append(p('아직 등록된 가족 이야기가 없습니다.'))
        for memory in memories:
            story += [p(memory['title'], heading), p(memory.get('occurred_on') or '날짜 미기록', small)]
            if memory.get('image_path'):
                try:
                    picture = Image(str(media_path(memory['image_path'])))
                    ratio = min(430 / picture.imageWidth, 260 / picture.imageHeight)
                    picture.drawWidth = picture.imageWidth * ratio
                    picture.drawHeight = picture.imageHeight * ratio
                    story += [picture, Spacer(1, 12)]
                except (HTTPException, OSError, ValueError):
                    story.append(p('사진 파일을 불러올 수 없습니다.', small))
            story.append(p(memory['story']))
    story.append(p('가족의 마음', heading))
    for message in data['guestbook']:
        story += [p(message['author']+' · '+message['created_at'][:10], small), p(message['message'])]
    def footer(canvas, doc):
        canvas.setFont(font, 8)
        canvas.setFillColor(colors.HexColor('#64736c'))
        canvas.drawString(48, 30, '가족 추모 기록 · 가족 보관용')
        canvas.drawRightString(A4[0]-48, 30, str(doc.page))
    SimpleDocTemplate(output, pagesize=A4, leftMargin=48, rightMargin=48, topMargin=48, bottomMargin=52,
                      title='기억을 담은 책', author='가족 추모 공간').build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()
