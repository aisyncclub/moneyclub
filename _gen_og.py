from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 630
img = Image.new("RGB", (W, H), "#0b0b0d")
d = ImageDraw.Draw(img)

# Subtle top band
for i in range(0, 180):
    shade = int(23 + (27 - 23) * (1 - i / 180))
    d.rectangle([(0, i), (W, i + 1)], fill=(shade, shade, shade + 4))

# Left accent stripe
d.rectangle([(0, 0), (14, H)], fill="#22c55e")

font_path = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
f_logo = ImageFont.truetype(font_path, 30, index=6)
f_title = ImageFont.truetype(font_path, 96, index=8)
f_sub = ImageFont.truetype(font_path, 36, index=4)
f_tag = ImageFont.truetype(font_path, 28, index=4)
f_foot = ImageFont.truetype(font_path, 26, index=2)

# Logo pill — diamond shape + text
d.rounded_rectangle([(60, 60), (430, 118)], radius=28, fill="#0f2819", outline="#22c55e", width=2)
# Diamond shape (simple)
cx, cy = 90, 89
d.polygon([(cx, cy - 14), (cx + 14, cy), (cx, cy + 14), (cx - 14, cy)], fill="#22c55e")
d.text((118, 71), "AI SYNC 재테크클럽", font=f_logo, fill="#22c55e")

# Title
d.text((60, 170), "투자 용어집 &", font=f_title, fill="#ffffff")
d.text((60, 280), "리포트 보관함", font=f_title, fill="#60a5fa")

# Subtitle
d.text((60, 410), "매일 시장을 AI가 분석하고,", font=f_sub, fill="#a1a1aa")
d.text((60, 460), "누구나 이해할 수 있게 쉽게 풀어드립니다.", font=f_sub, fill="#a1a1aa")

# Color dot + tag
def draw_tag(x, y, text, color, bg):
    bbox = d.textbbox((0, 0), text, font=f_tag)
    w = bbox[2] - bbox[0]
    d.rounded_rectangle([(x, y), (x + w + 56, y + 54)], radius=16, fill=bg, outline=color, width=2)
    # Color dot
    d.ellipse([(x + 16, y + 20), (x + 30, y + 34)], fill=color)
    d.text((x + 40, y + 12), text, font=f_tag, fill=color)
    return x + w + 56 + 14

x = 60
y = 540
x = draw_tag(x, y, "용어집 92개", "#60a5fa", "#0f1a2e")
x = draw_tag(x, y, "매일 리포트", "#22c55e", "#0f1f18")
x = draw_tag(x, y, "부동산 포함", "#eab308", "#1f1a0a")

# URL at bottom right
url_text = "aisyncclub.github.io/moneyclub"
bbox = d.textbbox((0, 0), url_text, font=f_foot)
u_w = bbox[2] - bbox[0]
d.text((W - u_w - 60, 588), url_text, font=f_foot, fill="#5c5c66")

img.save("/Users/firstandre/dev_test_file/stock_study/_deploy_moneyclub/og-image.png", "PNG", optimize=True)
print("saved og-image.png")
