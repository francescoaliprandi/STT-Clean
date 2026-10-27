"""Builds macos/AppIcon.icns (and assets/AppIcon.png, 1024 px) from assets/LOGO.png: the logo on a
macOS-style rounded square. Run again only if the logo changes:
    python macos/make_icon.py
"""
import os
import subprocess
import tempfile

from AppKit import (NSBezierPath, NSBitmapImageRep, NSCalibratedRGBColorSpace, NSColor, NSCompositingOperationMultiply,
                    NSGradient, NSGraphicsContext, NSImage, NSPNGFileType, NSShadow)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = 1024


def master(path: str) -> None:
    rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, S, S, 8, 4, True, False, NSCalibratedRGBColorSpace, 0, 0)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.setCurrentContext_(NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep))
    body = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(((100, 100), (824, 824)), 185, 185)  # Apple icon grid
    NSGraphicsContext.saveGraphicsState()
    shadow = NSShadow.alloc().init()
    shadow.setShadowOffset_((0, -12))
    shadow.setShadowBlurRadius_(28)
    shadow.setShadowColor_(NSColor.colorWithWhite_alpha_(0, 0.28))
    shadow.set()
    NSColor.whiteColor().set()
    body.fill()
    NSGraphicsContext.restoreGraphicsState()
    body.addClip()
    NSGradient.alloc().initWithStartingColor_endingColor_(
        NSColor.whiteColor(), NSColor.colorWithSRGBRed_green_blue_alpha_(0.90, 0.965, 1, 1)).drawInBezierPath_angle_(body, -90)
    logo = NSImage.alloc().initWithContentsOfFile_(os.path.join(ROOT, "assets", "LOGO.png"))
    w, h = logo.size()
    crop = ((0, h * 0.25), (w, h * 0.5))          # the logo occupies the middle band of the square PNG
    # multiply: the logo's white background disappears into the gradient
    logo.drawInRect_fromRect_operation_fraction_(((130, 330), (764, 382)), crop, NSCompositingOperationMultiply, 1)
    NSGraphicsContext.restoreGraphicsState()
    rep.representationUsingType_properties_(NSPNGFileType, None).writeToFile_atomically_(path, True)


if __name__ == "__main__":
    png = os.path.join(ROOT, "assets", "AppIcon.png")
    master(png)
    with tempfile.TemporaryDirectory() as d:
        iconset = os.path.join(d, "AppIcon.iconset")
        os.mkdir(iconset)
        for size in (16, 32, 128, 256, 512):
            for scale in (1, 2):
                name = f"icon_{size}x{size}{'@2x' if scale == 2 else ''}.png"
                subprocess.run(["sips", "-z", str(size * scale), str(size * scale), png, "--out",
                                os.path.join(iconset, name)], check=True, capture_output=True)
        subprocess.run(["iconutil", "-c", "icns", iconset, "-o", os.path.join(ROOT, "macos", "AppIcon.icns")], check=True)
    print("wrote assets/AppIcon.png and macos/AppIcon.icns")
