"""Extract plain text from SDIE v3.3 docx."""
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
docx = Path(__file__).resolve().parents[1] / "docs" / "SDIE v3.3 Enterprise Implementation Package.docx"
out = Path(__file__).resolve().parents[1] / "docs" / "Prompt_extracted.txt"

with zipfile.ZipFile(docx) as z:
    root = ET.fromstring(z.read("word/document.xml"))

paras = []
for p in root.iter(f"{W_NS}p"):
    texts = []
    for t in p.iter(f"{W_NS}t"):
        if t.text:
            texts.append(t.text)
        if t.tail:
            texts.append(t.tail)
    line = "".join(texts).strip()
    if line:
        paras.append(line)

text = "\n".join(paras)
out.write_text(text, encoding="utf-8")
print(f"Wrote {out} ({len(paras)} paragraphs, {len(text)} chars)")
