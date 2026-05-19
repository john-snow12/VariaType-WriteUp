# generate_fonts.py
# Kompatibel dengan fontTools >= 4.28 (diuji pada 4.55+ / 2025-2026)
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.ttGlyphPen import TTGlyphPen


def draw_notdef(pen):
    """Gambar glyph .notdef sederhana berbentuk kotak."""
    pen.moveTo((50, 0))
    pen.lineTo((50, 700))
    pen.lineTo((450, 700))
    pen.lineTo((450, 0))
    pen.closePath()


def build_font(path, family, style):
    fb = FontBuilder(1000, isTTF=True)

    # 1. Glyph order & character map
    fb.setupGlyphOrder([".notdef"])
    fb.setupCharacterMap({})

    # 2. Gambar glyph menggunakan TTGlyphPen
    pen = TTGlyphPen(None)
    draw_notdef(pen)
    glyph = pen.glyph()
    fb.setupGlyf({".notdef": glyph})

    # 3. Horizontal metrics: (advanceWidth, lsb)
    fb.setupHorizontalMetrics({".notdef": (500, 50)})

    # 4. Header tabel
    fb.setupHorizontalHeader(ascent=800, descent=-200)

    # 5. Name table — format dict dengan key standar OpenType
    fb.setupNameTable({
        "familyName": family,
        "styleName": style,
    })

    # 6. OS/2 — sTypoAscender/Descender wajib disebutkan eksplisit
    fb.setupOS2(
        sTypoAscender=800,
        sTypoDescender=-200,
        sTypoLineGap=0,
        usWinAscent=800,
        usWinDescent=200,
    )

    # 7. Post & simpan
    fb.setupPost()
    fb.font.save(path)
    print(f"[+] Font tersimpan: {path}")


build_font("source-light.ttf",   "SourceTest", "Light")
build_font("source-regular.ttf", "SourceTest", "Regular")
