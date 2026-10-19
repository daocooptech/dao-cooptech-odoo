"""Знак «Рабочей группы платформы»: лого coop, как в шапке, и «team» под ним.

Владелец 12.10.2026. Собирает static/src/img/team-logo.png (768×768):

    python tools/team_logo.py <рабочая папка>

Нужны Pillow и fonttools с brotli (Manrope в теме — woff2, вариативный);
если они стоят в <рабочая папка>/pylib, берутся оттуда. В рабочую папку
кладётся промежуточный manrope700.ttf и готовая картинка.
"""
import sys
sys.path.insert(0, sys.argv[1] + '/pylib')
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

import os
FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'static', 'src', 'fonts') + os.sep
out_dir = sys.argv[1]
f = TTFont(FONTS + 'manrope-700-latin.woff2'); f.flavor = None
if 'fvar' in f:                 # вариативный файл — закрепить вес 700
    from fontTools.varLib import instancer
    f = instancer.instantiateVariableFont(f, {'wght': 700})
f.save(out_dir + '/manrope700.ttf')

SS = 4                      # рисуем вчетверо крупнее и сглаживаем уменьшением
S = 768 * SS
img = Image.new('RGB', (S, S), 'white')
d = ImageDraw.Draw(img)
# Знак «coop» как в шапке: четыре кольца в ряд, у «c» разрыв справа,
# у «p» ножка слева вниз, внутри — T, E, C, H.
# Плотно к центру: на странице картинка стоит обложкой (полоса ~2,5:1) и
# обрезается сверху и снизу — знак и подпись должны уместиться в полосу.
k = 0.56 * SS
ox = (S - 800 * k) / 2
oy = 268 * SS
def X(v): return ox + v * k
def Y(v): return oy + v * k
cx, cy, r, w = [105, 300, 495, 690], 100, 78, 36
for i, x in enumerate(cx):
    box = [X(x - r - w / 2), Y(cy - r - w / 2), X(x + r + w / 2), Y(cy + r + w / 2)]
    if i == 0:
        d.arc(box, start=40, end=320, fill='black', width=int(w * k))
    else:
        d.ellipse(box, outline='black', width=int(w * k))
d.rectangle([X(cx[3] - r - w / 2), Y(cy), X(cx[3] - r + w / 2), Y(cy + 156)], fill='black')
arial = ImageFont.truetype(r'C:/Windows/Fonts/arialbd.ttf', int(34 * k))
for ch, x in zip('TECH', cx):
    d.text((X(x), Y(cy + 2)), ch, font=arial, fill='black', anchor='mm')
team = ImageFont.truetype(out_dir + '/manrope700.ttf', int(92 * SS))
d.text((S / 2, 500 * SS), 'team', font=team, fill='black', anchor='ms')
img = img.resize((768, 768), Image.LANCZOS)
img.save(out_dir + '/team-logo.png', optimize=True)
print(img.size)
