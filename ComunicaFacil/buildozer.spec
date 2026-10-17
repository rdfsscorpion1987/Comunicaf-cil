[app]
title = ComunicaFácil
package.name = comunicafacil
package.domain = org.comunicafacil
version = 0.2.0

source.dir = .
source.include_exts = py,png,jpg,kv,atlas
source.exclude_dirs = bin, .buildozer, .git, .github, __pycache__

requirements = python3,kivy==2.3.0,pyjnius,android

icon.filename = %(source.dir)s/icon.png
orientation = all
fullscreen = 0

# Sem permissões especiais: a voz usa o motor de TTS já instalado no telemóvel
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.allow_backup = True
android.extra_manifest_xml = ./extra_manifest.xml

[buildozer]
log_level = 2
warn_on_root = 1
