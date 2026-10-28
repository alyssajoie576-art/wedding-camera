"""
Generates a printable QR "table card" guests can scan to open the photobooth.

Usage:
    python generate_qr_card.py https://your-deployed-url.com

Run this AFTER you've deployed the app and know its public URL.
Outputs: qr_card.png  (print this and place on tables / at the entrance)
"""

import sys
import qrcode
from PIL import Image, ImageDraw, ImageFont

# Match these to what you set in app.py
PARTNER_1 = "Gab"
PARTNER_2 = "Aly"
CAPTION = "Scan to open the Guest Photobooth"


def find_font(size, bold=False):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def main():
    if len(sys.argv) < 2:
        print("Usage: python generate_qr_card.py <your-deployed-url>")
        sys.exit(1)

    url = sys.argv[1]

    CARD_W, CARD_H = 1200, 1600
    CREAM = (247, 242, 234)
    INK = (43, 44, 36)
    GOLD = (198, 161, 91)

    card = Image.new("RGB", (CARD_W, CARD_H), CREAM)
    draw = ImageDraw.Draw(card)

    # Decorative border
    margin = 40
    draw.rectangle([margin, margin, CARD_W - margin, CARD_H - margin], outline=INK, width=2)
    margin2 = 55
    draw.rectangle([margin2, margin2, CARD_W - margin2, CARD_H - margin2], outline=GOLD, width=2)

    # Names
    name_font = find_font(90, bold=True)
    names_text = f"{PARTNER_1} & {PARTNER_2}"
    bbox = draw.textbbox((0, 0), names_text, font=name_font)
    draw.text(((CARD_W - (bbox[2] - bbox[0])) / 2, 150), names_text, font=name_font, fill=INK)

    # QR code
    qr = qrcode.QRCode(border=2, box_size=14)
    qr.add_data(url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color=INK, back_color=CREAM).convert("RGB")
    qr_size = 700
    qr_img = qr_img.resize((qr_size, qr_size))
    card.paste(qr_img, ((CARD_W - qr_size) // 2, 340))

    # Caption
    cap_font = find_font(46)
    bbox = draw.textbbox((0, 0), CAPTION, font=cap_font)
    draw.text(((CARD_W - (bbox[2] - bbox[0])) / 2, 1090), CAPTION, font=cap_font, fill=INK)

    # Sub caption
    sub_font = find_font(34)
    sub_text = "Every photo lands straight in our shared album"
    bbox = draw.textbbox((0, 0), sub_text, font=sub_font)
    draw.text(((CARD_W - (bbox[2] - bbox[0])) / 2, 1160), sub_text, font=sub_font, fill=(90, 90, 78))

    out_path = "qr_card.png"
    card.save(out_path)
    print(f"Saved {out_path} — print at 4x6in or larger for table cards.")


if __name__ == "__main__":
    main()
