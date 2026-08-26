"""Injects brand icon directly into Windows PE executable using native Windows Resource Update APIs with MAKEINTRESOURCE."""

import ctypes
import os
import struct
import sys
from pathlib import Path
from PIL import Image

kernel32 = ctypes.windll.kernel32

def MAKEINTRESOURCE(i):
    return ctypes.cast(ctypes.c_void_p(i), ctypes.c_wchar_p)

def create_raw_ico(png_path: str, ico_path: str):
    """Creates a strictly formatted multi-resolution Windows ICO file."""
    img = Image.open(png_path).convert("RGBA")
    sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
    img.save(ico_path, format="ICO", sizes=sizes)
    print(f"[OK] Generated strictly formatted ICO: {ico_path}")

def inject_icon_via_win32(exe_path: str, ico_path: str):
    """Directly replaces RT_ICON and RT_GROUP_ICON in PE executable."""
    with open(ico_path, "rb") as f:
        ico_data = f.read()

    reserved, ico_type, count = struct.unpack_from("<HHH", ico_data, 0)
    if ico_type != 1:
        raise ValueError("Invalid ICO file")

    print(f"[*] Processing {count} icon layers from {ico_path}...")

    # Begin PE Resource Update (False = do not delete existing resources)
    h_update = kernel32.BeginUpdateResourceW(exe_path, False)
    if not h_update:
        err = ctypes.GetLastError()
        raise OSError(f"BeginUpdateResourceW failed with error code: {err}")

    RT_ICON = MAKEINTRESOURCE(3)
    RT_GROUP_ICON = MAKEINTRESOURCE(14)

    group_header = struct.pack("<HHH", 0, 1, count)
    group_entries = []

    for i in range(count):
        offset = 6 + i * 16
        b_width, b_height, b_color_count, b_reserved, w_planes, w_bit_count, dw_bytes_in_res, dw_image_offset = struct.unpack_from("<BBBBHHII", ico_data, offset)
        
        image_data = ico_data[dw_image_offset : dw_image_offset + dw_bytes_in_res]
        icon_id = i + 1

        # Write RT_ICON
        res_ok = kernel32.UpdateResourceW(
            h_update,
            RT_ICON,
            MAKEINTRESOURCE(icon_id),
            0, # Neutral language
            image_data,
            len(image_data)
        )
        if not res_ok:
            err = ctypes.GetLastError()
            print(f"[Warn] UpdateResource for icon {icon_id} returned error {err}")

        group_entry = struct.pack("<BBBBHHIH", b_width, b_height, b_color_count, b_reserved, w_planes, w_bit_count, dw_bytes_in_res, icon_id)
        group_entries.append(group_entry)

    group_data = group_header + b"".join(group_entries)

    # Write RT_GROUP_ICON ID: 1
    res_grp = kernel32.UpdateResourceW(
        h_update,
        RT_GROUP_ICON,
        MAKEINTRESOURCE(1),
        0,
        group_data,
        len(group_data)
    )
    if not res_grp:
        print(f"[Warn] UpdateResource for GROUP_ICON returned error {ctypes.GetLastError()}")

    # Commit changes
    end_ok = kernel32.EndUpdateResourceW(h_update, False)
    if not end_ok:
        err = ctypes.GetLastError()
        raise OSError(f"EndUpdateResourceW commit failed with error code: {err}")

    print(f"[SUCCESS] Native Windows Icon Injection Completed for {exe_path}!")

if __name__ == "__main__":
    exe = r"c:\dna\dist\ChannelDNA.exe"
    png = r"c:\dna\app_icon.png"
    ico = r"c:\dna\official_logo.ico"
    
    create_raw_ico(png, ico)
    inject_icon_via_win32(exe, ico)
