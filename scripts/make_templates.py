"""Generate the three sample templates (with logo, brand colours, header/footer, tables, master design).
Run:  python scripts/make_templates.py"""
import copy
from pathlib import Path
from PIL import Image, ImageDraw
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls, qn
from pptx import Presentation
from pptx.util import Inches as PI, Pt as PPt
from pptx.dml.color import RGBColor as PRGB
from pptx.enum.shapes import MSO_SHAPE
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment
from openpyxl.formatting.rule import CellIsRule
from openpyxl.worksheet.datavalidation import DataValidation

OUT = Path(__file__).resolve().parents[1] / "samples" / "templates"
OUT.mkdir(parents=True, exist_ok=True)
NAVY, TEAL = "1F3A5F", "2A9D8F"


def logo(path):
    im = Image.new("RGBA", (360, 120), (255, 255, 255, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, 359, 119), 18, fill=(31, 58, 95, 255))
    d.ellipse((24, 24, 96, 96), fill=(42, 157, 143, 255))
    d.rectangle((120, 40, 330, 52), fill=(255, 255, 255, 255))
    d.rectangle((120, 68, 270, 80), fill=(255, 255, 255, 200))
    im.save(path)
    return path


LOGO = logo(OUT / "acme_logo.png")


def make_docx():
    d = Document()
    s = d.sections[0]
    s.left_margin = s.right_margin = Inches(0.9)
    s.top_margin, s.bottom_margin = Inches(1.1), Inches(0.9)
    st = d.styles
    st["Normal"].font.name, st["Normal"].font.size = "Calibri", Pt(11)
    st["Title"].font.name, st["Title"].font.size, st["Title"].font.color.rgb = "Georgia", Pt(26), RGBColor.from_string(NAVY)
    for n, sz in (("Heading 1", 16), ("Heading 2", 13)):
        st[n].font.name, st[n].font.size, st[n].font.color.rgb, st[n].font.bold = "Georgia", Pt(sz), RGBColor.from_string(TEAL), True
    # header: logo + company line; footer: page number
    hp = s.header.paragraphs[0]
    hp.add_run().add_picture(str(LOGO), width=Inches(1.3))
    r = hp.add_run("\tAcme Corp — Confidential")
    r.font.size, r.font.color.rgb = Pt(9), RGBColor(0x66, 0x66, 0x66)
    fp = s.footer.paragraphs[0]
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    fp.add_run("Acme Corp · Quarterly Report · Page ").font.size = Pt(9)
    fp._p.append(parse_xml(f'<w:fldSimple {nsdecls("w")} w:instr="PAGE"><w:r><w:t>1</w:t></w:r></w:fldSimple>'))
    d.add_paragraph("Quarterly Business Report", style="Title")
    d.add_paragraph("Prepared for the Executive Team · Q3 2026")
    d.add_heading("1. Executive Summary", 1)
    d.add_paragraph("Acme Corp delivered steady growth in Q3 2026. Revenue increased 12% year over year, driven by strong demand in the enterprise segment.")
    d.add_heading("2. Regional Performance", 1)
    d.add_paragraph("The table below summarises revenue by region.")
    t = d.add_table(rows=1, cols=3)
    t.style = "Table Grid"
    for c, h in zip(t.rows[0].cells, ["Region", "Revenue (USD M)", "Growth"]):
        c.text = h
        c.paragraphs[0].runs[0].font.bold = True
        c.paragraphs[0].runs[0].font.color.rgb = RGBColor(255, 255, 255)
        c._tc.get_or_add_tcPr().append(parse_xml(f'<w:shd {nsdecls("w")} w:val="clear" w:color="auto" w:fill="{NAVY}"/>'))
    for row in (("North America", "42.1", "+11%"), ("Europe", "28.7", "+9%"), ("Asia Pacific", "19.4", "+18%")):
        cells = t.add_row().cells
        for c, v in zip(cells, row):
            c.text = v
    d.add_heading("3. Outlook", 1)
    d.add_paragraph("We expect continued momentum in Q4, supported by new product launches and expanded partnerships.")
    d.save(OUT / "acme_report_template.docx")


def make_pptx():
    prs = Presentation()  # 4:3 default layouts
    m = prs.slide_master
    # master design: brand font + colour for titles, top colour band and logo on every slide
    tdef = m._element.find(".//{*}titleStyle/{*}lvl1pPr/{*}defRPr")
    for ch in list(tdef):
        if ch.tag.endswith("solidFill"):
            tdef.remove(ch)
    tdef.insert(0, parse_xml(f'<a:solidFill xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:srgbClr val="{NAVY}"/></a:solidFill>'))
    for ch in tdef:
        if ch.tag.endswith("latin"):
            ch.set("typeface", "Georgia")
    tmp = prs.slides.add_slide(prs.slide_layouts[6])
    band = tmp.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, PI(0.25))
    band.fill.solid(); band.fill.fore_color.rgb = PRGB.from_string(NAVY); band.line.fill.background()
    pic = tmp.shapes.add_picture(str(LOGO), PI(8.2), PI(0.35), width=PI(1.5))
    blip = pic._element.blipFill.find("{http://schemas.openxmlformats.org/drawingml/2006/main}blip")
    rid_attr = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
    part = tmp.part.related_part(blip.get(rid_attr))
    from pptx.opc.constants import RELATIONSHIP_TYPE as RT
    blip.set(rid_attr, m.part.relate_to(part, RT.IMAGE))
    for el in (band._element, pic._element):
        m.shapes._spTree.append(el)
    sld = list(prs.slides._sldIdLst)[-1]
    prs.part.drop_rel(sld.rId); prs.slides._sldIdLst.remove(sld)
    # slides
    s = prs.slides.add_slide(prs.slide_layouts[0])
    s.shapes.title.text = "Acme Corp Product Roadmap"
    s.placeholders[1].text = "Strategy briefing · 2026"
    s = prs.slides.add_slide(prs.slide_layouts[1])
    s.shapes.title.text = "Key Priorities"
    tf = s.placeholders[1].text_frame
    tf.text = "Grow enterprise revenue by 15%"
    for line in ("Launch the analytics suite in Q4", "Expand partner network in APAC"):
        tf.add_paragraph().text = line
    s = prs.slides.add_slide(prs.slide_layouts[5])
    s.shapes.title.text = "Regional Revenue"
    gt = s.shapes.add_table(4, 3, PI(0.7), PI(2.0), PI(8.6), PI(2.2)).table
    for ci, h in enumerate(("Region", "Revenue (USD M)", "Growth")):
        gt.cell(0, ci).text = h
    for ri, row in enumerate((("North America", "42.1", "+11%"), ("Europe", "28.7", "+9%"), ("Asia Pacific", "19.4", "+18%")), 1):
        for ci, v in enumerate(row):
            gt.cell(ri, ci).text = v
    prs.save(OUT / "acme_deck_template.pptx")


def make_xlsx():
    wb = Workbook()
    ws = wb.active
    ws.title = "Sales"
    ws.sheet_properties.tabColor = TEAL
    ws.merge_cells("A1:F1")
    ws["A1"] = "Acme Corp — Sales Tracker"
    ws["A1"].font = Font(name="Arial", size=16, bold=True, color=NAVY)
    ws["A2"], ws["D2"] = "Total revenue:", "=SUM(E5:E500)"
    ws["A2"].font = ws["D2"].font = Font(name="Arial", bold=True)
    ws["D2"].number_format = '"$"#,##0.00'
    thin = Side(style="thin", color="B0B0B0")
    heads = ["Date", "Customer", "Product", "Status", "Amount", "Owner"]
    for ci, h in enumerate(heads, 1):
        c = ws.cell(4, ci, h)
        c.font = Font(name="Arial", bold=True, color="FFFFFF")
        c.fill = PatternFill("solid", fgColor=NAVY)
        c.alignment = Alignment(horizontal="center")
        c.border = Border(left=thin, right=thin, top=thin, bottom=thin)
    import datetime as dt
    rows = [(dt.date(2026, 7, 5), "Globex", "Analytics Suite", "Won", 12500, "Priya"),
            (dt.date(2026, 7, 19), "Initech", "Platform", "Open", 8200, "Marco"),
            (dt.date(2026, 8, 2), "Umbrella", "Analytics Suite", "Won", 15400, "Priya")]
    for ri, row in enumerate(rows, 5):
        for ci, v in enumerate(row, 1):
            c = ws.cell(ri, ci, v)
            c.font = Font(name="Arial", size=10)
            c.border = Border(left=thin, right=thin, top=thin, bottom=thin)
            if ci == 1: c.number_format = "dd-mmm-yyyy"
            if ci == 5: c.number_format = '"$"#,##0.00'
    for L, w in zip("ABCDEF", (14, 18, 20, 12, 14, 12)):
        ws.column_dimensions[L].width = w
    ws.freeze_panes = "A5"
    dv = DataValidation(type="list", formula1='"Won,Open,Lost"', allow_blank=True)
    ws.add_data_validation(dv); dv.add("D5:D500")
    ws.conditional_formatting.add("D5:D500", CellIsRule(operator="equal", formula=['"Won"'], fill=PatternFill("solid", bgColor="C6EFCE")))
    img = XLImage(str(LOGO)); img.width, img.height = 120, 40
    ws.add_image(img, "H1")
    ws.oddFooter.center.text = "Acme Corp — Confidential"
    wb.save(OUT / "acme_sales_template.xlsx")


if __name__ == "__main__":
    make_docx(); make_pptx(); make_xlsx()
    print("templates written to", OUT)
