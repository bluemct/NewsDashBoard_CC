# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

a = Analysis(
    ['edm_gui.py'],
    pathex=['_edm_build'],
    binaries=[],
    datas=[
        ('config.json', '.'),
        ('Tokenmapping.json', '.'),
        ('xlsx_search_dir.json', '.'),
        ('verify_list_contacts.py', '.'),
        ('deep_verify_list.py', '.'),
    ],
    hiddenimports=[
        'olefile',
        'olefile.olefile',
        'extract_msg',
        'openpyxl',
        'win32com',
        'win32com.client',
        'win32com.server',
        'win32com.util',
        'pythoncom',
        'requests',
        'unimarketing_test_list',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'pygments',
        'rich',
        'lxml.isoschematron',
        'lxml.objectify',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='EDM Email Processor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='EDM Email Processor',
)
