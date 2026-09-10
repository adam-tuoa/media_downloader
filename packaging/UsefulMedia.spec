# PyInstaller spec: onedir build of the desktop app (backend + built UI + yt-dlp/ffmpeg/qjs).
# Build from the repo root:  pyinstaller --noconfirm packaging/UsefulMedia.spec
import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
from app import __version__  # noqa: E402

a = Analysis(
    [str(BACKEND / "app" / "launcher.py")],
    pathex=[str(BACKEND)],
    binaries=[],
    # NOTE: backend/bin (yt-dlp, ffmpeg, qjs) is deliberately NOT listed here. PyInstaller
    # re-signs/rewrites executables it collects, which breaks yt-dlp's own PyInstaller build.
    # scripts/bundle_binaries.py copies bin/ into the finished bundle verbatim instead.
    datas=[
        (str(BACKEND / "app" / "static"), "app/static"),  # `npm run build` output
    ],
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.loops.asyncio",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.http.httptools_impl",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "uvicorn.lifespan.off",
    ],
    excludes=["tkinter", "pytest", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="UsefulMedia",
    debug=False,
    strip=False,
    upx=False,
    console=False,  # windowed: no black terminal window; logs go to app.log
    icon=None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="UsefulMedia")
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="UsefulMedia.app",
        icon=None,
        bundle_identifier="au.com.tuoa.usefulmedia",
        info_plist={
            "CFBundleName": "UsefulMedia",
            "CFBundleDisplayName": "UsefulMedia",
            "CFBundleShortVersionString": __version__,
            "CFBundleVersion": __version__,
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
            "NSHumanReadableCopyright": "MIT licence · tuoa-tools/usefulmedia",
        },
    )
