"""
ComunicaFácil - App de Comunicação Aumentativa e Alternativa (CAA)
Para crianças com autismo e outras necessidades de comunicação.
Gratuita e open-source (MIT). Feita com amor. 💙

Desktop:  pip install kivy==2.3.0 pyttsx3  &&  python main.py
Android:  ver buildozer.spec (a voz usa o TTS nativo do Android)

Ficheiros:
    main.py      -> interface e lógica
    dados.py     -> temas, categorias e cartões (edita aqui para mudar cartões)
    assets/emoji -> imagens dos emojis (Twemoji, CC-BY 4.0)
"""

import os
import re
import base64
import random
import subprocess
import queue
import threading

# ── Kivy config (antes de qualquer import kivy) ──────────────────────────────
os.environ.setdefault("KIVY_NO_ENV_CONFIG", "1")

from kivy.utils import platform
from kivy.config import Config

if platform not in ("android", "ios"):
    Config.set("graphics", "width", "1024")
    Config.set("graphics", "height", "768")
    Config.set("graphics", "resizable", "1")

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.image import Image
from kivy.uix.widget import Widget
from kivy.uix.floatlayout import FloatLayout
from kivy.graphics import Color, RoundedRectangle, Rectangle
from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.core.window import Window
from kivy.animation import Animation
from kivy.properties import BooleanProperty

from dados import TEMAS, CATEGORIAS

PASTA = os.path.dirname(os.path.abspath(__file__))

ELOGIOS = ["Muito bem!", "Boa!", "Parabéns!", "Excelente!", "Muito bom!"]


# ══════════════════════════════════════════════════════════════════════════════
#  EMOJIS COMO IMAGENS
#  (o tipo de letra por defeito do Kivy não desenha emojis, nem no PC nem no
#   Android — por isso cada emoji é uma imagem PNG em assets/emoji/)
# ══════════════════════════════════════════════════════════════════════════════

def caminho_emoji(emoji: str) -> str:
    codigo = "-".join(f"{ord(c):x}" for c in emoji if ord(c) != 0xFE0F)
    return os.path.join(PASTA, "assets", "emoji", codigo + ".png")


def criar_icone(emoji: str, **kwargs):
    """Imagem do emoji; se o ficheiro não existir, usa o texto como fallback."""
    caminho = caminho_emoji(emoji)
    if os.path.exists(caminho):
        return Image(source=caminho, fit_mode="contain", **kwargs)
    return Label(text=emoji, **kwargs)


class BotaoIcone(ButtonBehavior, Image):
    """Botão que é só uma imagem (ex.: alternar tema)."""


# ══════════════════════════════════════════════════════════════════════════════
#  TTS (TEXT-TO-SPEECH)
# ══════════════════════════════════════════════════════════════════════════════

class TTSDesktop:
    """pyttsx3 numa única thread que é dona do motor (evita erros de COM/threads)."""

    def __init__(self):
        self._fila = queue.Queue()
        self.disponivel = False
        self.erro = ""
        try:
            import pyttsx3  # noqa: F401
        except Exception:
            self.erro = "pyttsx3 não está instalado (pip install pyttsx3)"
            print("ComunicaFácil:", self.erro)
            return
        self.disponivel = True
        threading.Thread(target=self._trabalhar, daemon=True).start()

    @staticmethod
    def _escolher_voz(engine):
        melhor = None
        for v in engine.getProperty("voices"):
            nome = (v.name or "").lower()
            vid = (v.id or "").lower()
            langs = [(l.decode() if isinstance(l, bytes) else str(l)).lower()
                     for l in (v.languages or [])]
            e_pt = (any(l.startswith("pt") for l in langs) or "portugu" in nome
                    or re.search(r"pt[-_]?(pt|br)|[-_.]pt[-_.]|\bpt\b", vid))
            if not e_pt:
                continue
            if re.search(r"pt[-_]?pt|portugal", nome + " " + vid + " " + " ".join(langs)):
                return v.id            # português de Portugal tem prioridade
            melhor = melhor or v.id
        return melhor

    def _novo_motor(self):
        import pyttsx3
        engine = pyttsx3.init()
        if self._voz:
            engine.setProperty("voice", self._voz)
        engine.setProperty("rate", 140)
        engine.setProperty("volume", 1.0)
        return engine

    def _trabalhar(self):
        # Descobre a voz uma vez; depois cria um motor novo por pedido, porque no
        # Windows o pyttsx3 por vezes só fala na primeira chamada a runAndWait().
        self._voz = None
        try:
            import pyttsx3
            engine = pyttsx3.init()
            self._voz = self._escolher_voz(engine)
            if not self._voz:
                nomes = [v.name for v in engine.getProperty("voices")]
                self.erro = ("não há voz portuguesa instalada "
                             "(Definições > Hora e idioma > Voz)")
                print("ComunicaFácil:", self.erro, "| vozes disponíveis:", nomes)
            del engine
        except Exception as e:                       # noqa: BLE001
            self.disponivel = False
            self.erro = f"o motor de voz não arrancou ({e})"
            print("ComunicaFácil:", self.erro)
            return
        while True:
            textos = self._fila.get()
            while not self._fila.empty():      # só diz o pedido mais recente
                textos = self._fila.get_nowait()
            engine = None
            try:
                engine = self._novo_motor()
                for t in textos:
                    engine.say(t)
                engine.runAndWait()
                engine.stop()
            except Exception as e:                   # noqa: BLE001
                self.erro = f"erro ao falar ({e})"
                print("ComunicaFácil:", self.erro)
            finally:
                del engine

    def falar(self, *textos: str):
        """Diz os textos por ordem; um novo pedido substitui os que estão à espera."""
        if self.disponivel:
            self._fila.put(textos)

    def parar(self):
        pass


class TTSWindows:
    """Voz do Windows (System.Speech/SAPI) através de um PowerShell que fica a correr.

    Mais fiável do que o pyttsx3, que no Windows tende a falar só no primeiro
    clique. Protocolo: uma linha por pedido, com cada frase em base64 separada
    por vírgulas (só ASCII, sem problemas de acentos); um pedido novo interrompe
    o anterior. Não precisa de instalar nada além do português nas Definições.
    """

    SCRIPT = r"""
$ErrorActionPreference = 'Stop'
try {
  Add-Type -AssemblyName System.Speech
  $s = New-Object System.Speech.Synthesis.SpeechSynthesizer
  $v = @($s.GetInstalledVoices() | Where-Object { $_.Enabled } | ForEach-Object { $_.VoiceInfo })
  $pt = $v | Where-Object { $_.Culture.Name -eq 'pt-PT' } | Select-Object -First 1
  if (-not $pt) { $pt = $v | Where-Object { $_.Culture.Name -like 'pt*' } | Select-Object -First 1 }
  if ($pt) { $s.SelectVoice($pt.Name); [Console]::Out.WriteLine('OK ' + $pt.Name) }
  else { [Console]::Out.WriteLine('SEMPT ' + (($v | ForEach-Object { $_.Name }) -join ';')) }
  $s.Rate = -2
  while (($l = [Console]::In.ReadLine()) -ne $null) {
    $s.SpeakAsyncCancelAll()
    foreach ($b in ($l -split ',')) {
      if ($b) { [void]$s.SpeakAsync([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($b))) }
    }
  }
} catch { [Console]::Out.WriteLine('ERRO ' + $_.Exception.Message) }
"""

    def __init__(self):
        self.disponivel = False
        self.erro = ""
        self._proc = None
        codigo = base64.b64encode(self.SCRIPT.encode("utf-16-le")).decode("ascii")
        try:
            self._proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy",
                 "Bypass", "-EncodedCommand", codigo],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except Exception as e:                       # noqa: BLE001
            self.erro = f"PowerShell indisponível ({e})"
            print("ComunicaFácil:", self.erro)
            return
        self.disponivel = True
        threading.Thread(target=self._ler, daemon=True).start()

    def _ler(self):
        """Lê as respostas do PowerShell (estado da voz e erros)."""
        for bruto in iter(self._proc.stdout.readline, b""):
            linha = bruto.decode("utf-8", "replace").strip()
            if linha.startswith("OK "):
                print("ComunicaFácil: voz", linha[3:])
            elif linha.startswith("SEMPT"):
                self.erro = ("não há voz portuguesa instalada "
                             "(Definições > Hora e idioma > Idioma e região)")
                print("ComunicaFácil:", self.erro, "| vozes:", linha[6:])
            elif linha.startswith("ERRO"):
                self.disponivel = False
                self.erro = "erro na voz do Windows (" + linha[5:] + ")"
                print("ComunicaFácil:", self.erro)

    def falar(self, *textos: str):
        if not (self.disponivel and self._proc):
            return
        linha = ",".join(base64.b64encode(t.encode("utf-8")).decode("ascii")
                         for t in textos) + "\n"
        try:
            self._proc.stdin.write(linha.encode("ascii"))
            self._proc.stdin.flush()
        except Exception as e:                       # noqa: BLE001
            self.disponivel = False
            self.erro = f"a voz do Windows parou ({e})"
            print("ComunicaFácil:", self.erro)

    def parar(self):
        try:
            if self._proc:
                self._proc.stdin.close()
                self._proc.terminate()
        except Exception:
            pass


class TTSAndroid:
    """TextToSpeech nativo do Android através de pyjnius."""

    def __init__(self):
        self.disponivel = False
        self._tts = None
        self._listener = None
        try:
            self._criar()
        except Exception as e:                       # noqa: BLE001
            print("ComunicaFácil: TTS Android indisponível:", e)

    def _criar(self):
        from jnius import autoclass, PythonJavaClass, java_method
        from android.runnable import run_on_ui_thread

        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        TextToSpeech = autoclass("android.speech.tts.TextToSpeech")
        Locale = autoclass("java.util.Locale")
        self._Locale = Locale
        dono = self

        class OnInit(PythonJavaClass):
            __javainterfaces__ = ["android/speech/tts/TextToSpeech$OnInitListener"]
            __javacontext__ = "app"

            @java_method("(I)V")
            def onInit(self, status):
                if status != 0:                      # 0 = SUCCESS
                    return
                tts = dono._tts
                for loc in (Locale("pt", "PT"), Locale("pt", "BR")):
                    if tts.setLanguage(loc) >= 0:    # <0 = sem dados / sem suporte
                        break
                tts.setSpeechRate(0.85)
                dono.disponivel = True

        self._listener = OnInit()                    # guardar a referência!

        @run_on_ui_thread
        def _no_ui():
            self._tts = TextToSpeech(PythonActivity.mActivity, self._listener)

        _no_ui()

    def falar(self, *textos: str):
        """Diz os textos por ordem; o primeiro interrompe o que estiver a falar."""
        if not (self.disponivel and self._tts):
            return
        try:
            for i, texto in enumerate(textos):
                # 0 = QUEUE_FLUSH (substitui), 1 = QUEUE_ADD (junta à fila)
                self._tts.speak(texto, 0 if i == 0 else 1, None, f"cf{i}")
        except Exception as e:                                  # noqa: BLE001
            print("ComunicaFácil: erro ao falar:", e)

    def parar(self):
        try:
            if self._tts:
                self._tts.stop()
                self._tts.shutdown()
        except Exception:
            pass


def criar_tts():
    if platform == "android":
        return TTSAndroid()
    if platform == "win" and os.environ.get("COMUNICAFACIL_TTS") != "pyttsx3":
        tts = TTSWindows()
        if tts.disponivel:
            return tts
    return TTSDesktop()


# ══════════════════════════════════════════════════════════════════════════════
#  WIDGETS PERSONALIZADOS
# ══════════════════════════════════════════════════════════════════════════════

class CartaoItem(ButtonBehavior, BoxLayout):
    """Cartão clicável para cada item de comunicação."""

    def __init__(self, item_data: dict, categoria_cor: tuple, tema: dict,
                 on_selecionar=None, **kwargs):
        super().__init__(**kwargs)
        self.item_data = item_data
        self.categoria_cor = categoria_cor
        self.tema = tema
        self._on_selecionar = on_selecionar
        self.orientation = "vertical"
        self.spacing = dp(4)
        self.padding = [dp(8), dp(12), dp(8), dp(8)]
        self.size_hint = (1, None)

        self.add_widget(criar_icone(item_data["emoji"], size_hint=(1, 0.58)))

        self.lbl_nome = Label(
            text=item_data["nome"], font_size=sp(16), bold=True,
            color=tema["texto"], size_hint=(1, 0.24),
            halign="center", valign="middle",
        )
        self.lbl_nome.bind(size=lambda l, s: setattr(l, "text_size", s))
        self.add_widget(self.lbl_nome)

        self.lbl_silabas = Label(
            text=item_data["silabas"], font_size=sp(12),
            color=(*categoria_cor[:3], 0.95), size_hint=(1, 0.18),
            halign="center", valign="middle",
        )
        self.lbl_silabas.bind(size=lambda l, s: setattr(l, "text_size", s))
        self.add_widget(self.lbl_silabas)

        self.bind(size=self._desenhar, pos=self._desenhar)
        self.bind(on_press=self._ao_clicar)

    def _desenhar(self, *_):
        self.canvas.before.clear()
        with self.canvas.before:
            Color(*self.tema["sombra"])
            RoundedRectangle(pos=(self.x + dp(3), self.y - dp(3)),
                             size=self.size, radius=[dp(16)])
            Color(*self.tema["card"])
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(16)])
            r, g, b, _a = self.categoria_cor
            Color(r, g, b, 0.85)
            RoundedRectangle(pos=(self.x, self.y + self.height - dp(8)),
                             size=(self.width, dp(8)),
                             radius=[dp(16), dp(16), 0, 0])

    def _ao_clicar(self, *_):
        Animation.cancel_all(self, "opacity")
        (Animation(opacity=0.6, duration=0.08)
         + Animation(opacity=1.0, duration=0.12)).start(self)
        if self._on_selecionar:
            self._on_selecionar(self.item_data)


class BotaoAcao(ButtonBehavior, BoxLayout):
    """Botão grande e colorido (ex.: "Bem!", "Ouvir")."""

    def __init__(self, texto: str, emoji: str, cor: tuple, **kwargs):
        super().__init__(**kwargs)
        self.cor = cor
        self.orientation = "horizontal"
        self.spacing = dp(8)
        self.padding = [dp(14), dp(6)]
        self.add_widget(criar_icone(emoji, size_hint=(None, 1), width=dp(34)))
        self.add_widget(Label(text=texto, font_size=sp(18), bold=True,
                              color=(1, 1, 1, 1)))
        self.bind(pos=self._desenhar, size=self._desenhar, state=self._desenhar)

    def _desenhar(self, *_):
        self.canvas.before.clear()
        r, g, b, _a = self.cor
        with self.canvas.before:
            Color(r, g, b, 0.75 if self.state == "down" else 1)
            RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(14)])


class BotaoCategoria(ButtonBehavior, BoxLayout):
    """Botão de categoria (barra lateral no PC/tablet, barra no topo no telemóvel)."""

    ativa = BooleanProperty(False)

    def __init__(self, cat_data: dict, tema: dict, on_press_cb=None, **kwargs):
        super().__init__(**kwargs)
        self.cat_data = cat_data
        self.tema = tema
        self._cb = on_press_cb
        self.orientation = "vertical"
        self.spacing = dp(2)
        self.padding = [dp(4), dp(6)]

        self.add_widget(criar_icone(cat_data["emoji"], size_hint=(1, 0.6)))
        self.lbl_nome = Label(
            text=cat_data["nome"], font_size=sp(11), bold=True,
            color=tema["texto_claro"], size_hint=(1, 0.4),
            halign="center", valign="middle",
        )
        self.lbl_nome.bind(size=lambda l, s: setattr(l, "text_size", s))
        self.add_widget(self.lbl_nome)

        self.bind(size=self._redesenhar, pos=self._redesenhar, ativa=self._redesenhar)
        self.bind(on_press=lambda *_: self._cb and self._cb(self.cat_data))
        self._desenhar()

    def _redesenhar(self, *_):
        self._desenhar()

    def _desenhar(self):
        self.canvas.before.clear()
        if self.ativa:
            with self.canvas.before:
                Color(1, 1, 1, 0.22)
                RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(12)])
                Color(1, 1, 1, 0.95)
                RoundedRectangle(pos=(self.x, self.y), size=(dp(4), self.height),
                                 radius=[0, dp(4), dp(4), 0])
        self.lbl_nome.color = (1, 1, 1, 1) if self.ativa else (1, 1, 1, 0.8)

    def aplicar_tema(self, tema: dict):
        self.tema = tema
        self._desenhar()


# ══════════════════════════════════════════════════════════════════════════════
#  ECRÃ PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

class EcraPrincipal(FloatLayout):

    def __init__(self, tts, **kwargs):
        super().__init__(**kwargs)
        self.tts = tts
        self.modo_escuro = False
        self.tema = TEMAS["claro"]
        self.categoria_atual = CATEGORIAS[0]
        self.compacto = None          # True = telemóvel/retrato (barra no topo)
        self._botoes_cat = []
        self.item_ativo = None
        self._ev_repor = None

        self._construir_ui()
        self._aplicar_tema()
        self._selecionar_categoria(CATEGORIAS[0])
        self.bind(size=self._atualizar_layout)
        Clock.schedule_once(self._atualizar_layout, 0)

    # ── construção ────────────────────────────────────────────────────────────

    def _construir_ui(self):
        t = self.tema

        with self.canvas.before:
            self._cor_fundo = Color(*t["fundo"])
            self._rect_fundo = Rectangle(pos=self.pos, size=self.size)
        self.bind(size=self._redesenhar_fundo, pos=self._redesenhar_fundo)

        self.raiz = BoxLayout(orientation="horizontal", size_hint=(1, 1))
        self.add_widget(self.raiz)

        # ── Barra de categorias ─────────────────────────────────────────────
        self.barra = BoxLayout(orientation="vertical", size_hint=(None, 1),
                               width=dp(110), spacing=dp(4),
                               padding=[dp(8), dp(12), dp(4), dp(12)])
        with self.barra.canvas.before:
            self._cor_barra = Color(*t["barra"])
            self._rect_barra = Rectangle(pos=self.barra.pos, size=self.barra.size)
        self.barra.bind(
            pos=lambda *_: setattr(self._rect_barra, "pos", self.barra.pos),
            size=lambda *_: setattr(self._rect_barra, "size", self.barra.size),
        )

        self.logo = BoxLayout(orientation="vertical", size_hint=(1, None), height=dp(80))
        self.logo.add_widget(criar_icone("💬", size_hint=(1, 0.6)))
        self.lbl_logo = Label(text="Comunica\nFácil", font_size=sp(12), bold=True,
                              halign="center", color=t["texto_claro"], size_hint=(1, 0.4))
        self.logo.add_widget(self.lbl_logo)
        self.barra.add_widget(self.logo)

        for cat in CATEGORIAS:
            btn = BotaoCategoria(cat_data=cat, tema=self.tema,
                                 on_press_cb=self._selecionar_categoria)
            self._botoes_cat.append(btn)
            self.barra.add_widget(btn)
        self.espaco = Widget(size_hint=(1, 1))
        self.barra.add_widget(self.espaco)
        self.raiz.add_widget(self.barra)

        # ── Área principal ──────────────────────────────────────────────────
        area = BoxLayout(orientation="vertical", size_hint=(1, 1))
        self.raiz.add_widget(area)

        self.cab = BoxLayout(orientation="horizontal", size_hint=(1, None),
                             height=dp(120),
                             padding=[dp(20), dp(12), dp(12), dp(10)], spacing=dp(8))
        with self.cab.canvas.before:
            self._cor_cab = Color(*t["fundo2"])
            self._rect_cab = Rectangle(pos=self.cab.pos, size=self.cab.size)
        self.cab.bind(
            pos=lambda *_: setattr(self._rect_cab, "pos", self.cab.pos),
            size=lambda *_: setattr(self._rect_cab, "size", self.cab.size),
        )

        texto_cab = BoxLayout(orientation="vertical", spacing=dp(4))
        self.lbl_categoria = Label(text="", font_size=sp(14), bold=True,
                                   halign="left", valign="middle",
                                   color=t["primaria"], size_hint=(1, None), height=dp(22))
        self.lbl_categoria.bind(size=lambda l, s: setattr(l, "text_size", s))
        texto_cab.add_widget(self.lbl_categoria)

        self.lbl_frase = Label(text="Escolhe um cartão para comunicar!",
                               font_size=sp(24), bold=True,
                               halign="left", valign="middle",
                               color=t["texto"], size_hint=(1, 1))
        self.lbl_frase.bind(size=lambda l, s: setattr(l, "text_size", s))
        texto_cab.add_widget(self.lbl_frase)
        self.cab.add_widget(texto_cab)

        self.btn_tema = BotaoIcone(source=caminho_emoji("🌙"), fit_mode="contain",
                                   size_hint=(None, None), size=(dp(44), dp(44)))
        self.btn_tema.bind(on_press=self._alternar_tema)
        self.cab.add_widget(self.btn_tema)
        area.add_widget(self.cab)

        # Painel do exercício de repetição (só aparece depois de escolher um cartão)
        self.painel = BoxLayout(orientation="horizontal", size_hint=(1, None),
                                height=0, opacity=0, disabled=True,
                                spacing=dp(12), padding=[dp(16), dp(8)])
        self.btn_ouvir = BotaoAcao("Ouvir", "🔊", t["primaria_esc"])
        self.btn_ouvir.bind(on_press=self._ouvir_outra_vez)
        self.btn_bem = BotaoAcao("Bem!", "👍", t["sucesso"])
        self.btn_bem.bind(on_press=self._disse_bem)
        self.painel.add_widget(self.btn_ouvir)
        self.painel.add_widget(self.btn_bem)
        area.add_widget(self.painel)

        self.scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False, bar_width=dp(4))
        self.grelha = GridLayout(cols=2, size_hint_y=None, row_force_default=True)
        self.grelha.bind(minimum_height=self.grelha.setter("height"))
        self.scroll.add_widget(self.grelha)
        self.scroll.bind(width=self._ajustar_grelha)
        area.add_widget(self.scroll)

    # ── layout responsivo ─────────────────────────────────────────────────────

    def _atualizar_layout(self, *_):
        if self.width < 10 or self.height < 10:
            return
        compacto = self.width < dp(640) or self.width < self.height
        if compacto != self.compacto:
            self.compacto = compacto
            if compacto:                       # barra horizontal no topo
                self.raiz.orientation = "vertical"
                self.barra.orientation = "horizontal"
                self.barra.size_hint = (1, None)
                self.barra.height = dp(78)
                self.barra.spacing = dp(2)
                self.barra.padding = [dp(4), dp(4)]
                self.logo.size_hint = (None, None)
                self.logo.size = (0, 0)
                self.logo.opacity = 0
                self.espaco.size_hint = (None, None)
                self.espaco.size = (0, 0)
                for b in self._botoes_cat:
                    b.size_hint = (1, 1)
                self.cab.height = dp(104)
                self.lbl_frase.font_size = sp(20)
            else:                              # barra lateral
                self.raiz.orientation = "horizontal"
                self.barra.orientation = "vertical"
                self.barra.size_hint = (None, 1)
                self.barra.width = dp(110)
                self.barra.spacing = dp(4)
                self.barra.padding = [dp(8), dp(12), dp(4), dp(12)]
                self.logo.size_hint = (1, None)
                self.logo.height = dp(80)
                self.logo.opacity = 1
                self.espaco.size_hint = (1, 1)
                for b in self._botoes_cat:
                    b.size_hint = (1, None)
                    b.height = dp(80)
                self.cab.height = dp(120)
                self.lbl_frase.font_size = sp(24)
        self._ajustar_grelha()

    def _ajustar_grelha(self, *_):
        larg = self.scroll.width
        if larg < 10:
            return
        pad = dp(12) if self.compacto else dp(20)
        esp = dp(12) if self.compacto else dp(16)
        minimo = dp(130) if self.compacto else dp(150)
        cols = max(2, int((larg - 2 * pad + esp) // (minimo + esp)))
        largura_cartao = (larg - 2 * pad - esp * (cols - 1)) / cols
        self.grelha.cols = cols
        self.grelha.spacing = esp
        self.grelha.padding = [pad, pad, pad, pad]
        self.grelha.row_default_height = largura_cartao * 1.15
        for c in self.grelha.children:
            c.height = largura_cartao * 1.15

    # ── lógica ────────────────────────────────────────────────────────────────

    def _selecionar_categoria(self, cat_data: dict):
        self.categoria_atual = cat_data
        for btn in self._botoes_cat:
            btn.ativa = btn.cat_data["id"] == cat_data["id"]

        self._esconder_painel()
        self._repor_cabecalho()

        self.grelha.clear_widgets()
        for item in cat_data["itens"]:
            self.grelha.add_widget(CartaoItem(
                item_data=item, categoria_cor=cat_data["cor"], tema=self.tema,
                on_selecionar=self._ao_selecionar_item))
        self.scroll.scroll_y = 1
        self._ajustar_grelha()

    # Fluxo: a criança escolhe → ouve a frase → "Agora tu! Repete comigo" →
    #        o adulto carrega em "Bem!" → "Muito bem! <frase>" + reforço positivo.

    def _ao_selecionar_item(self, item_data: dict):
        self.item_ativo = item_data
        self._cancelar_reposicao()
        self.lbl_frase.text = item_data["frase"]
        erro = getattr(self.tts, "erro", "")
        if erro:                                     # avisa em vez de falhar em silêncio
            self.lbl_categoria.text = "AVISO: " + erro.upper()
            self.lbl_categoria.color = (0.85, 0.2, 0.2, 1)
        else:
            self.lbl_categoria.text = "AGORA TU! REPETE COMIGO"
            self.lbl_categoria.color = self.categoria_atual["cor"]
        self._mostrar_painel()
        self.tts.falar(item_data["frase"], "Agora tu! Repete comigo.")

    def _ouvir_outra_vez(self, *_):
        if self.item_ativo:
            self.tts.falar(self.item_ativo["frase"], "Agora tu! Repete comigo.")

    def _disse_bem(self, *_):
        if not self.item_ativo:
            return
        frase = self.item_ativo["frase"]
        elogio = random.choice(ELOGIOS)
        self._cancelar_reposicao()
        self._esconder_painel()
        self.lbl_categoria.text = elogio.upper()
        self.lbl_categoria.color = self.tema["texto"]
        self.lbl_frase.text = frase
        self.tts.falar(f"{elogio} {frase}")
        # reforço positivo: o cabeçalho "acende" a verde e volta ao normal
        t = self.tema
        verde = tuple(0.65 * a + 0.35 * b for a, b in zip(t["fundo2"], t["sucesso"]))
        Animation.cancel_all(self._cor_cab)
        (Animation(rgba=verde, duration=0.2)
         + Animation(rgba=t["fundo2"], duration=2.0)).start(self._cor_cab)
        self._ev_repor = Clock.schedule_once(self._repor_cabecalho, 3.5)

    def _mostrar_painel(self):
        self.painel.height = dp(68)
        self.painel.opacity = 1
        self.painel.disabled = False

    def _esconder_painel(self):
        self.item_ativo = None
        self.painel.height = 0
        self.painel.opacity = 0
        self.painel.disabled = True

    def _cancelar_reposicao(self):
        if self._ev_repor:
            self._ev_repor.cancel()
            self._ev_repor = None

    def _repor_cabecalho(self, *_):
        self._ev_repor = None
        if self.item_ativo:          # há um exercício a decorrer: não mexer
            return
        self.lbl_categoria.text = self.categoria_atual["nome"].upper()
        self.lbl_categoria.color = self.categoria_atual["cor"]
        self.lbl_frase.text = "Escolhe um cartão para comunicar!"

    def _alternar_tema(self, *_):
        self.modo_escuro = not self.modo_escuro
        self.tema = TEMAS["escuro" if self.modo_escuro else "claro"]
        self.btn_tema.source = caminho_emoji("☀️" if self.modo_escuro else "🌙")
        self._aplicar_tema()
        self._selecionar_categoria(self.categoria_atual)

    def _aplicar_tema(self):
        t = self.tema
        Window.clearcolor = t["fundo"]
        self._cor_fundo.rgba = t["fundo"]
        self._cor_barra.rgba = t["barra"]
        Animation.cancel_all(self._cor_cab)
        self._cor_cab.rgba = t["fundo2"]        # (o cabeçalho ficava branco no modo escuro)
        self.btn_ouvir.cor = t["primaria_esc"]
        self.btn_bem.cor = t["sucesso"]
        self.btn_ouvir._desenhar()
        self.btn_bem._desenhar()
        self.lbl_logo.color = t["texto_claro"]
        self.lbl_frase.color = t["texto"]
        for btn in self._botoes_cat:
            btn.aplicar_tema(t)

    def _redesenhar_fundo(self, *_):
        self._rect_fundo.pos = self.pos
        self._rect_fundo.size = self.size


# ══════════════════════════════════════════════════════════════════════════════
#  APP
# ══════════════════════════════════════════════════════════════════════════════

class ComunicaFacilApp(App):

    def build(self):
        self.title = "ComunicaFácil"
        icone = os.path.join(PASTA, "icon.png")
        if os.path.exists(icone):
            self.icon = icone
        Window.clearcolor = TEMAS["claro"]["fundo"]
        self.tts = criar_tts()
        return EcraPrincipal(tts=self.tts)

    def on_pause(self):
        return True            # Android: não fechar a app ao mudar para outra

    def on_stop(self):
        self.tts.parar()


if __name__ == "__main__":
    ComunicaFacilApp().run()
