from __future__ import annotations
import io
import struct
import zlib
import asyncio
import logging
import json
import urllib.request
import urllib.error
try:
    import discord
except ImportError:
    discord = None

try:
    import aiohttp
except ImportError:
    aiohttp = None

logger = logging.getLogger("bot.services.jail_overlay")


def _apply_jail_bars_pillow(image_bytes: bytes) -> bytes:
    """Renders prison cell bars over image using Pillow."""
    from PIL import Image, ImageDraw

    img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    w, h = img.size

    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Number of vertical iron bars
    num_bars = 6
    spacing = w / (num_bars + 1)
    bar_width = max(10, int(w * 0.045))
    half_bw = bar_width // 2

    # Draw vertical iron bars with 3D metallic gradient
    for i in range(1, num_bars + 1):
        cx = int(i * spacing)
        x0 = cx - half_bw
        x1 = cx + half_bw

        # Main dark metallic bar body
        draw.rectangle([x0, 0, x1, h], fill=(65, 70, 80, 255))
        # Left shadow edge
        draw.line([(x0, 0), (x0, h)], fill=(25, 28, 35, 255), width=max(1, bar_width // 6))
        # Specular highlight stripe (light reflection)
        highlight_x = x0 + max(2, bar_width // 4)
        draw.line([(highlight_x, 0), (highlight_x, h)], fill=(210, 220, 235, 255), width=max(1, bar_width // 5))
        # Right shadow rim
        draw.line([(x1, 0), (x1, h)], fill=(20, 22, 28, 255), width=max(1, bar_width // 5))

    # Horizontal reinforcement crossbeams
    h_positions = [int(h * 0.20), int(h * 0.80)]
    h_bar_thick = max(8, int(h * 0.035))

    for hy in h_positions:
        y0 = hy - h_bar_thick // 2
        y1 = hy + h_bar_thick // 2
        draw.rectangle([0, y0, w, y1], fill=(55, 60, 70, 255))
        # Top highlight
        draw.line([(0, y0), (w, y0)], fill=(185, 195, 210, 255), width=1)
        # Bottom shadow
        draw.line([(0, y1), (w, y1)], fill=(20, 22, 28, 255), width=1)

        # Bolts / Rivets at intersections
        for i in range(1, num_bars + 1):
            cx = int(i * spacing)
            draw.ellipse([cx - 3, hy - 3, cx + 3, hy + 3], fill=(215, 225, 240, 255), outline=(30, 32, 38, 255))

    # Dark prison vignette around borders
    vignette = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    v_draw = ImageDraw.Draw(vignette)
    v_border = max(6, int(min(w, h) * 0.04))
    v_draw.rectangle([0, 0, w, h], outline=(15, 18, 24, 180), width=v_border)

    combined = Image.alpha_composite(img, overlay)
    combined = Image.alpha_composite(combined, vignette)

    out = io.BytesIO()
    combined.save(out, format="PNG", optimize=True)
    return out.getvalue()


def _paeth_predictor(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    elif pb <= pc:
        return b
    else:
        return c


def _apply_jail_bars_pure(png_bytes: bytes) -> bytes:
    """
    Pure Python fallback: decodes PNG scanlines using built-in zlib,
    rasters realistic metallic prison bars directly onto the pixel buffer,
    and re-encodes a valid PNG. Zero external dependencies required.
    """
    if not png_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return png_bytes

    pos = 8
    width = height = 0
    idat_parts = []

    while pos < len(png_bytes):
        if pos + 8 > len(png_bytes):
            break
        length = struct.unpack(">I", png_bytes[pos:pos+4])[0]
        ctype = png_bytes[pos+4:pos+8]
        cdata = png_bytes[pos+8:pos+8+length]
        pos += 12 + length

        if ctype == b"IHDR":
            width, height, bit_depth, color_type, comp, filt, inter = struct.unpack(">IIBBBBB", cdata)
            if bit_depth != 8 or color_type != 6 or inter != 0:
                return png_bytes
        elif ctype == b"IDAT":
            idat_parts.append(cdata)
        elif ctype == b"IEND":
            break

    try:
        raw_decompressed = zlib.decompress(b"".join(idat_parts))
    except Exception:
        return png_bytes

    bpp = 4  # RGBA
    stride = width * bpp

    rows = []
    prev_row = bytearray(stride)
    raw_pos = 0

    for y in range(height):
        if raw_pos >= len(raw_decompressed):
            break
        filter_type = raw_decompressed[raw_pos]
        raw_pos += 1
        curr_bytes = bytearray(raw_decompressed[raw_pos:raw_pos+stride])
        raw_pos += stride

        if filter_type == 1:  # Sub
            for x in range(bpp, stride):
                curr_bytes[x] = (curr_bytes[x] + curr_bytes[x - bpp]) & 0xFF
        elif filter_type == 2:  # Up
            for x in range(stride):
                curr_bytes[x] = (curr_bytes[x] + prev_row[x]) & 0xFF
        elif filter_type == 3:  # Average
            for x in range(stride):
                left = curr_bytes[x - bpp] if x >= bpp else 0
                up = prev_row[x]
                curr_bytes[x] = (curr_bytes[x] + ((left + up) >> 1)) & 0xFF
        elif filter_type == 4:  # Paeth
            for x in range(stride):
                left = curr_bytes[x - bpp] if x >= bpp else 0
                up = prev_row[x]
                up_left = prev_row[x - bpp] if x >= bpp else 0
                curr_bytes[x] = (curr_bytes[x] + _paeth_predictor(left, up, up_left)) & 0xFF

        rows.append(curr_bytes)
        prev_row = curr_bytes

    num_bars = 6
    spacing = width // (num_bars + 1)
    bar_w = max(10, width // 36)
    half_bw = bar_w // 2

    h_bar_top = int(height * 0.20)
    h_bar_bot = int(height * 0.80)
    h_bar_thick = max(6, int(height * 0.025))

    bar_x_centers = [int(i * spacing) for i in range(1, num_bars + 1)]

    for y in range(len(rows)):
        row = rows[y]
        is_horiz = (abs(y - h_bar_top) <= h_bar_thick) or (abs(y - h_bar_bot) <= h_bar_thick)

        for x in range(width):
            px = x * 4
            dist_v = None
            for bx in bar_x_centers:
                d = x - bx
                if abs(d) <= half_bw:
                    dist_v = d
                    break

            if dist_v is not None:
                rel = dist_v / half_bw
                if -0.7 <= rel <= -0.2:
                    r, g, b = 210, 215, 225
                elif rel > 0.35:
                    r, g, b = 32, 35, 42
                elif rel < -0.7:
                    r, g, b = 42, 45, 52
                else:
                    r, g, b = 85, 90, 102
                row[px] = r
                row[px+1] = g
                row[px+2] = b
                row[px+3] = 255
            elif is_horiz:
                # Horizontal crossbar
                row[px] = 68
                row[px+1] = 72
                row[px+2] = 82
                row[px+3] = 255

    out_payload = bytearray()
    for row in rows:
        out_payload.append(0)  # Filter type 0
        out_payload.extend(row)

    compressed_idat = zlib.compress(bytes(out_payload), level=4)
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)

    return (
        b"\x89PNG\r\n\x1a\n" +
        struct.pack(">I", len(ihdr_data)) + b"IHDR" + ihdr_data + struct.pack(">I", zlib.crc32(b"IHDR" + ihdr_data)) +
        struct.pack(">I", len(compressed_idat)) + b"IDAT" + compressed_idat + struct.pack(">I", zlib.crc32(b"IDAT" + compressed_idat)) +
        struct.pack(">I", 0) + b"IEND" + struct.pack(">I", zlib.crc32(b"IEND"))
    )


def apply_prison_bars(png_bytes: bytes) -> bytes:
    """Applies prison bars to raw image bytes, using Pillow if available or pure Python."""
    try:
        return _apply_jail_bars_pillow(png_bytes)
    except Exception as e:
        logger.debug(f"[JailOverlay] Pillow overlay no disponible ({e}), usando rasterizador puro.")
        return _apply_jail_bars_pure(png_bytes)


async def fetch_image_bytes(url: str, timeout: int = 6) -> bytes | None:
    """Downloads image bytes from URL asynchronously."""
    if not url:
        return None

    if aiohttp is not None:
        try:
            async with aiohttp.ClientSession() as session:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                async with session.get(url, headers=headers, timeout=timeout) as res:
                    if res.status == 200:
                        return await res.read()
        except Exception as e:
            logger.debug(f"[JailOverlay] aiohttp error al descargar {url}: {e}")

    # Fallback to urllib in thread executor
    def _fetch_sync():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=timeout) as res:
                return res.read()
        except Exception as e:
            logger.warning(f"[JailOverlay] urllib error al descargar {url}: {e}")
            return None

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _fetch_sync)


async def resolve_roblox_user_id(identifier: str) -> str | None:
    """Resolves Roblox username or ID string to numeric user ID."""
    clean_id = str(identifier).strip()
    if clean_id.isdigit():
        return clean_id

    # Resolve username via Roblox API
    if aiohttp is not None:
        try:
            async with aiohttp.ClientSession() as session:
                payload = {"usernames": [clean_id], "excludeBannedUsers": False}
                async with session.post("https://users.roblox.com/v1/usernames/users", json=payload, timeout=5) as res:
                    if res.status == 200:
                        data = await res.json()
                        users = data.get("data", [])
                        if users:
                            return str(users[0].get("id"))
        except Exception as e:
            logger.debug(f"[JailOverlay] aiohttp error buscando usuario Roblox {clean_id}: {e}")

    # Fallback sync
    def _resolve_sync():
        try:
            payload = json.dumps({"usernames": [clean_id], "excludeBannedUsers": False}).encode("utf-8")
            req = urllib.request.Request(
                "https://users.roblox.com/v1/usernames/users",
                data=payload,
                headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=5) as res:
                data = json.loads(res.read().decode("utf-8"))
                users = data.get("data", [])
                if users:
                    return str(users[0].get("id"))
        except Exception as e:
            logger.debug(f"[JailOverlay] urllib error buscando usuario Roblox {clean_id}: {e}")
            return None

    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _resolve_sync)


ROBLOX_DEFAULT_AVATAR = "https://tr.rbxcdn.com/30DAY-AvatarHeadshot-B597B0D33E1DEBC30656208FBCBF9549-Png/420/420/AvatarHeadshot/Png/noFilter"


async def get_jailed_roblox_avatar(
    roblox_avatar_url: str | None = None,
    roblox_identifier: str | None = None,
    fallback_avatar_url: str | None = None
) -> tuple[discord.File | None, str | None]:
    """
    Obtains the citizen's Roblox avatar headshot strictly from their DNI or Roblox API,
    applies realistic prison bars over it, and returns a discord.File ready to be attached to the arrest embed as thumbnail.

    Returns:
        tuple (discord.File or None, attachment_uri_or_url)
    """
    image_bytes = None

    # 1. Direct Roblox avatar URL from citizen's DNI
    if roblox_avatar_url and str(roblox_avatar_url).strip().startswith("http"):
        image_bytes = await fetch_image_bytes(str(roblox_avatar_url).strip())

    # 2. Try to fetch Roblox avatar headshot from Roblox API if not loaded or failed
    if not image_bytes and roblox_identifier:
        user_id = await resolve_roblox_user_id(str(roblox_identifier).strip())
        if user_id:
            thumb_api = f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={user_id}&size=420x420&format=Png&isCircular=false"
            raw_thumb_data = None
            if aiohttp is not None:
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(thumb_api, timeout=5) as res:
                            if res.status == 200:
                                raw_thumb_data = await res.json()
                except Exception:
                    pass

            if not raw_thumb_data:
                def _fetch_thumb_sync():
                    try:
                        req = urllib.request.Request(thumb_api, headers={"User-Agent": "Mozilla/5.0"})
                        with urllib.request.urlopen(req, timeout=5) as res:
                            return json.loads(res.read().decode("utf-8"))
                    except Exception:
                        return None
                loop = asyncio.get_running_loop()
                raw_thumb_data = await loop.run_in_executor(None, _fetch_thumb_sync)

            if raw_thumb_data:
                t_list = raw_thumb_data.get("data", [])
                if t_list and t_list[0].get("imageUrl"):
                    image_bytes = await fetch_image_bytes(t_list[0]["imageUrl"])

    # 3. Fallback avatar URL if specifically provided and starts with http (Roblox only)
    if not image_bytes and fallback_avatar_url and str(fallback_avatar_url).strip().startswith("http"):
        image_bytes = await fetch_image_bytes(str(fallback_avatar_url).strip())

    # 4. Default Roblox avatar headshot placeholder if no profile image could be retrieved
    if not image_bytes:
        image_bytes = await fetch_image_bytes(ROBLOX_DEFAULT_AVATAR)

    # 5. Apply prison cell bars in a worker thread
    if image_bytes:
        try:
            loop = asyncio.get_running_loop()
            jailed_png = await loop.run_in_executor(None, apply_prison_bars, image_bytes)
            if jailed_png and jailed_png.startswith(b"\x89PNG\r\n\x1a\n"):
                if discord is not None:
                    file = discord.File(io.BytesIO(jailed_png), filename="arrestado_entre_rejas.png")
                else:
                    file = io.BytesIO(jailed_png)
                return file, "attachment://arrestado_entre_rejas.png"
        except Exception as e:
            logger.error(f"[JailOverlay] Error aplicando rejas de prisión: {e}")

    # Return fallback if rendering failed
    return None, roblox_avatar_url or ROBLOX_DEFAULT_AVATAR
