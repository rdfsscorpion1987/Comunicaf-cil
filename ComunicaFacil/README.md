# 💬 ComunicaFácil

> App gratuita e open-source de Comunicação Aumentativa e Alternativa (CAA)  
> para crianças com autismo e outras necessidades de comunicação.

---

## ✨ O que tem esta versão

| Funcionalidade | Estado |
|---|---|
| 5 categorias (Comida, Emoções, Atividades, Corpo, Escola) | ✅ |
| 50 cartões com emoji + nome + sílabas | ✅ |
| Voz em português (TTS) ao clicar | ✅ |
| Frases completas ("Quero água, por favor.") | ✅ |
| Exercício de repetição: ouve a frase → "Agora tu! Repete comigo" → o adulto carrega em **Bem!** → elogio + repete a frase | ✅ |
| Modo escuro / alto contraste | ✅ |
| Interface responsiva (tablet e PC) | ✅ |
| Grelha adaptável ao tamanho do ecrã (telemóvel, tablet, PC) | ✅ |
| Emojis desenhados como imagens (funcionam em Android) | ✅ |

---

## 🚀 Instalar e correr

**PC (para testar):**

```bash
pip install -r requirements-desktop.txt
python main.py
```

> Em Windows a voz vem do sintetizador do sistema (via PowerShell) — precisa do
> português instalado em Definições → Hora e idioma → Idioma e região. Se algo
> correr mal, o cabeçalho da app mostra um aviso. Para forçar o `pyttsx3`:
> `set COMUNICAFACIL_TTS=pyttsx3`.

**Android (APK):**

- A voz usa o motor de TTS nativo do Android (`TextToSpeech` via `pyjnius`);
  o `pyttsx3` só é usado no PC. Convém ter "Português" instalado nas definições
  de Texto para voz do telemóvel.
- Compilar com [Buildozer](https://github.com/kivy/buildozer) (Linux/WSL/Colab): `buildozer android debug`
  → o APK fica em `bin/`.
- Ou sem instalar nada: pôr este projeto num repositório GitHub — o workflow
  `.github/workflows/build-apk.yml` compila o APK e deixa-o em *Actions → Artifacts*.

**Estrutura:** `main.py` (interface), `dados.py` (temas e cartões — edita aqui),
`assets/emoji/` (imagens dos emojis; ver `CREDITOS.md`).

---

## 🗂️ Adicionar imagens reais (opcional)

Por defeito, a app usa emojis como ícones — funciona sem qualquer imagem.

Se quiseres usar fotos reais dos alimentos/objetos (recomendado para crianças
que ainda não associam bem emojis):

```
assets/
  items/
    comida/agua.png
    comida/leite.png
    emocoes/feliz.png
    ...
```

Depois, no `main.py`, adiciona `"imagem": "assets/items/comida/agua.png"` a
cada item no dicionário `CATEGORIAS`.

---

## 🛣️ Roadmap — próximas funcionalidades

### 🔴 Prioridade alta
- [ ] **Modo personalização** — pais/terapeutas podem adicionar/remover cartões
- [ ] **Sons gravados** — gravar a voz real dos pais para cada cartão
- [ ] **Perfis por criança** — cada criança tem os seus cartões preferidos
- [ ] **Favoritos** — marcar cartões usados mais frequentemente

### 🟡 Prioridade média
- [ ] **Construtor de frases** — combinar vários cartões ("Quero" + "Leite" + "Por favor")
- [x] **Reforço positivo** — elogio falado + cabeçalho a verde quando o adulto carrega em "Bem!"
- [ ] **Reconhecimento de voz** — detetar automaticamente que a criança repetiu (opcional)
- [ ] **Histórico** — registo do que a criança comunicou durante o dia
- [ ] **Tamanho de cartão ajustável** — acessibilidade para motricidade fina

### 🟢 Ideias futuras
- [x] **Versão Android** (Buildozer / Kivy for Android) — a testar
- [ ] **Modo offline total** — sem internet obrigatória
- [ ] **Sincronização entre dispositivos** (opcional, com consentimento)
- [ ] **Relatórios para terapeutas** — exportar histórico de comunicação
- [ ] **Suporte multi-idioma** (inglês, espanhol, francês...)
- [ ] **Símbolos ARASAAC** — sistema de pictogramas standardizado

---

## 🤝 Contribuir

Este projeto é para as crianças, não para ganhar dinheiro.  
Se és terapeuta, pai/mãe, designer ou programador e queres ajudar, és muito bem-vindo!

---

## 📄 Licença

MIT — usa, modifica e distribui à vontade. Só não cobres por isso. 💙
