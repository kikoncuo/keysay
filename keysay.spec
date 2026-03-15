# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for keysay macOS .app bundle."""

import os
import sys

block_cipher = None

# Find MLX metallib (required for Metal GPU operations)
import importlib.util
mlx_spec = importlib.util.find_spec('mlx')
mlx_datas = []
if mlx_spec and mlx_spec.submodule_search_locations:
    mlx_dir = mlx_spec.submodule_search_locations[0]
    mlx_lib_dir = os.path.join(mlx_dir, 'lib')
    if os.path.isdir(mlx_lib_dir):
        for f in os.listdir(mlx_lib_dir):
            if f.endswith('.metallib'):
                mlx_datas.append((os.path.join(mlx_lib_dir, f), os.path.join('mlx', 'lib')))

# Find mlx_qwen3_asr asset files (mel filters, dictionaries)
asr_spec = importlib.util.find_spec('mlx_qwen3_asr')
asr_datas = []
if asr_spec and asr_spec.submodule_search_locations:
    asr_dir = asr_spec.submodule_search_locations[0]
    assets_dir = os.path.join(asr_dir, 'assets')
    if os.path.isdir(assets_dir):
        for f in os.listdir(assets_dir):
            asr_datas.append((os.path.join(assets_dir, f), os.path.join('mlx_qwen3_asr', 'assets')))

# Find font files
font_dir = os.path.join('keysay', 'ui', 'fonts')
font_datas = []
if os.path.isdir(font_dir):
    for f in os.listdir(font_dir):
        if f.endswith('.ttf'):
            font_datas.append((os.path.join(font_dir, f), os.path.join('keysay', 'ui', 'fonts')))

a = Analysis(
    ['keysay/__main__.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('keysay/ui/icon.png', 'keysay/ui'),
        ('keysay/ui/icon_256.png', 'keysay/ui'),
        ('keysay/ui/icon.icns', 'keysay/ui'),
    ] + font_datas + mlx_datas + asr_datas,
    hiddenimports=[
        'keysay',
        'keysay.app',
        'keysay.config',
        'keysay.history',
        'keysay.models',
        'keysay.screenshot',
        'keysay.asr',
        'keysay.asr.engine',
        'keysay.audio',
        'keysay.audio.recorder',
        'keysay.hotkey',
        'keysay.hotkey.cgevent_listener',
        'keysay.llm',
        'keysay.llm._patches',
        'keysay.llm.context_extractor',
        'keysay.llm.corrector',
        'keysay.llm.presets',
        'keysay.paste',
        'keysay.paste.paster',
        'keysay.ui',
        'keysay.ui.theme',
        'keysay.ui.pill',
        'keysay.ui.tray',
        'keysay.ui.settings_window',
        'keysay.ui.permissions_dialog',
        'PyQt6',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PyQt6.sip',
        'sounddevice',
        '_sounddevice_data',
        'soundfile',
        'numpy',
        'mlx',
        'mlx._reprlib_fix',
        'mlx.core',
        'mlx.nn',
        'mlx_qwen3_asr',
        'mlx_vlm',
        'mlx_vlm.models',
        'mlx_vlm.models.qwen3_5',
        'mlx_lm',
        'transformers',
        'huggingface_hub',
        'safetensors',
        'tokenizers',
        'objc',
        'AppKit',
        'Quartz',
        'ApplicationServices',
        'Cocoa',
        'Foundation',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'torch',
        'tensorflow',
        'jax',
        'torchaudio',
        'torchvision',
        'matplotlib',
        'scipy',
        'pandas',
        'IPython',
        'jupyter',
        'notebook',
        'pytest',
        'tkinter',
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='keysay',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='keysay/ui/icon.icns',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='keysay',
)

app = BUNDLE(
    coll,
    name='keysay.app',
    icon='keysay/ui/icon.icns',
    bundle_identifier='com.keysay.app',
    info_plist={
        'CFBundleName': 'keysay',
        'CFBundleDisplayName': 'keysay',
        'CFBundleVersion': '0.1.0',
        'CFBundleShortVersionString': '0.1.0',
        'LSUIElement': False,
        'NSMicrophoneUsageDescription': 'keysay needs microphone access for speech-to-text.',
        'NSAccessibilityUsageDescription': 'keysay needs accessibility for global hotkeys and text pasting.',
        'NSHighResolutionCapable': True,
    },
)
