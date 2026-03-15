"""py2app build configuration for keysay."""

from setuptools import setup

APP = ['keysay/__main__.py']

OPTIONS = {
    'argv_emulation': False,
    'iconfile': 'keysay/ui/icon.icns',
    'plist': {
        'CFBundleName': 'keysay',
        'CFBundleDisplayName': 'keysay',
        'CFBundleIdentifier': 'com.keysay.app',
        'CFBundleVersion': '0.1.0',
        'CFBundleShortVersionString': '0.1.0',
        'LSUIElement': False,
        'NSMicrophoneUsageDescription': (
            'keysay needs microphone access for speech-to-text.'
        ),
        'NSAccessibilityUsageDescription': (
            'keysay needs accessibility for global hotkeys and text pasting.'
        ),
    },
    'includes': [
        'PyQt6',
        'sounddevice',
        'mlx',
        'numpy',
        'huggingface_hub',
    ],
    'packages': [
        'keysay',
        'mlx_qwen3_asr',
        'mlx_vlm',
        'mlx_lm',
        'transformers',
        'huggingface_hub',
        'safetensors',
        'tokenizers',
    ],
    'frameworks': [
        '/System/Library/Frameworks/Quartz.framework',
        '/System/Library/Frameworks/ApplicationServices.framework',
    ],
    'resources': [
        'keysay/ui/icon.png',
        'keysay/ui/icon_256.png',
        'keysay/ui/icon.icns',
        'keysay/ui/fonts',
    ],
    'excludes': ['torch', 'tensorflow', 'jax', 'torchaudio', 'torchvision'],
}

setup(
    name='keysay',
    app=APP,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)
