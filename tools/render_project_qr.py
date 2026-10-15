#!/usr/bin/env python3
"""Regenerate the branded QR source JPEG for the shared artwork packer."""
import base64
from collections import deque
from io import BytesIO
from pathlib import Path
import qrcode
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]

def main():
    # Extract the original high-resolution mark; exclude the adjacent slogan.
    logo = Image.open(ROOT/'assets/petrel-readme.png').convert('RGBA').crop((366,217,678,593))
    alpha = logo.convert('RGB').point(lambda p: p).split()
    from PIL import ImageChops
    mask = ImageChops.lighter(ImageChops.lighter(alpha[0],alpha[1]),alpha[2]).point(lambda p:255 if p>60 else 0)
    mask.paste(0,(140,250,312,376))
    # Discard isolated extraction debris without changing the brand silhouette.
    seen=set(); pixels=mask.load()
    for y in range(mask.height):
        for x in range(mask.width):
            if not pixels[x,y] or (x,y) in seen: continue
            group=[]; queue=deque([(x,y)]);seen.add((x,y))
            while queue:
                px,py=queue.popleft();group.append((px,py))
                for nx,ny in ((px-1,py),(px+1,py),(px,py-1),(px,py+1)):
                    if 0<=nx<mask.width and 0<=ny<mask.height and pixels[nx,ny] and (nx,ny) not in seen:
                        seen.add((nx,ny));queue.append((nx,ny))
            if len(group)<100:
                for point in group: mask.putpixel(point,0)
    logo.putalpha(mask);buffer=BytesIO();logo.save(buffer,format='PNG')
    qr=qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_H,box_size=1,border=2)
    qr.add_data('https://github.com/sezgynus/Petrel');qr.make(fit=True)
    matrix=qr.get_matrix();count=len(matrix)
    parts=['<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="168" height="168" viewBox="0 0 168 168"><rect width="168" height="168" fill="white"/>']
    for row,values in enumerate(matrix):
        for col,dark in enumerate(values):
            if dark:
                x,y=round(col*168/count),round(row*168/count)
                w,h=round((col+1)*168/count)-x,round((row+1)*168/count)-y
                parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}"/>')
    parts.append('<rect x="57" y="54" width="54" height="60" fill="white"/>')
    encoded=base64.b64encode(buffer.getvalue()).decode()
    parts.append(f'<image x="63.5" y="59" width="41" height="50" xlink:href="data:image/png;base64,{encoded}"/></svg>\n')
    source = ROOT/'assets/picture-source/project-qr.svg'
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(''.join(parts))
    import cairosvg  # Developer dependency; the service uses the shipped JPEG.
    png = cairosvg.svg2png(bytestring=source.read_bytes())
    with Image.open(BytesIO(png)) as image:
        destination = ROOT/'assets/shared-artwork/qr.jpg'
        destination.parent.mkdir(parents=True, exist_ok=True)
        image.convert('RGB').save(destination, 'JPEG', quality=100,
                                  subsampling=2, progressive=False)

if __name__=='__main__': main()
