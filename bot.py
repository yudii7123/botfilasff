from flask import Flask
import threading
import io
import os
import random
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
import qrcode

app = Flask('')

@app.route('/')
def home():
    return "Bot Online!"

def run():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port)

threading.Thread(target=run, daemon=True).start()
# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()
TOKEN = os.getenv("TOKEN")

# Configuração básica do Bot com Intents necessários
intents = discord.Intents.default()
intents.message_content = True
intents.members = True


class FreeFireBot(commands.Bot):

  def __init__(self):
    super().__init__(command_prefix="!", intents=intents)

  async def setup_hook(self):
    await self.tree.sync()
    print(f"Logado como {self.user} (ID: {self.user.id})")


bot = FreeFireBot()

# Dicionário para armazenar o PIX dos mediadores {user_id: {"chave": str, "nome": str, "cidade": str, "qr_link": str}}
pix_mediadores = {}

# Lista global de mediadores que estão em plantão na fila
mediadores_em_plantao = []


# Função para verificar se um MEMBRO HUMANO tem o cargo MEDIADOR
def checar_mediador_humano(member: discord.Member) -> bool:
  if member.bot:
    return False
  if member.guild_permissions.administrator or member == member.guild.owner:
    return True
  return any("mediador" in role.name.lower() for role in member.roles)


# Evento que deteta as mensagens e reage ao 'pg'
@bot.event
async def on_message(message: discord.Message):
  if message.author.bot:
    return

  if message.content.lower().startswith("pg"):
    try:
      await message.add_reaction("✅")
    except Exception as e:
      print(f"Erro ao adicionar reação: {e}")

  await bot.process_commands(message)


# Modal para Configurar o PIX do Mediador
class ConfigurarPixModal(discord.ui.Modal, title="Configurar Pagamento"):
  chave_pix = discord.ui.TextInput(
      label="Chave de pagamento (PIX)",
      placeholder="CPF, E-mail, Telefone ou Chave Aleatória...",
      required=True,
  )
  nome_completo = discord.ui.TextInput(
      label="Nome completo",
      placeholder="Titular da conta bancária...",
      required=True,
  )
  cidade = discord.ui.TextInput(
      label="Cidade",
      placeholder="Cidade de registro da conta...",
      required=True,
  )
  qr_code_custom = discord.ui.TextInput(
      label="Link Imagem QR Code (Se Personalizado)",
      placeholder="Link ou código do QR Code (Opcional)...",
      required=False,
  )

  async def on_submit(self, interaction: discord.Interaction):
    pix_mediadores[interaction.user.id] = {
        "chave": self.chave_pix.value,
        "nome": self.nome_completo.value,
        "cidade": self.cidade.value,
        "qr_link": self.qr_code_custom.value,
    }
    await interaction.response.send_message(
        f"✅ **PIX Configurado com Sucesso!**\n\n"
        f"**Chave:** `{self.chave_pix.value}`\n"
        f"**Nome:** `{self.nome_completo.value}`\n"
        f"**Cidade:** `{self.cidade.value}`",
        ephemeral=True,
    )


# View do Painel da Central de Pagamentos
class PainelPixView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)

  @discord.ui.button(
      label="Configurar Pix",
      style=discord.ButtonStyle.success,
      emoji="💸",
      custom_id="btn_configurar_pix_painel",
  )
  async def abrir_modal_pix(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    if not checar_mediador_humano(interaction.user):
      await interaction.response.send_message(
          "❌ Apenas membros com o cargo **MEDIADOR** podem configurar o PIX!",
          ephemeral=True,
      )
      return

    await interaction.response.send_modal(ConfigurarPixModal())


# Modal para o mediador fornecer ID e Senha da Sala
class FornecerSalaModal(discord.ui.Modal, title="Fornecer Dados da Sala"):
  id_sala = discord.ui.TextInput(
      label="ID da Sala",
      placeholder="Digite o ID da sala customizada...",
      required=True,
  )
  senha_sala = discord.ui.TextInput(
      label="Senha da Sala", placeholder="Digite a senha...", required=True
  )

  async def on_submit(self, interaction: discord.Interaction):
    embed_dados = discord.Embed(
        title="🎮 Dados da Sala Customizada",
        description=(
            f"**ID da Sala:** `{self.id_sala.value}`\n**Senha:**"
            f" `{self.senha_sala.value}`\n\nEntrem na sala e boa sorte!"
        ),
        color=discord.Color.green(),
    )
    await interaction.response.send_message(embed_dados, ephemeral=False)


# View para copiar o PIX
class PixCopiaColaView(discord.ui.View):

  def __init__(self, payload_pix: str):
    super().__init__(timeout=None)
    self.payload_pix = payload_pix

  @discord.ui.button(
      label="Copiar PIX",
      style=discord.ButtonStyle.success,
      emoji="🟢",
      custom_id="btn_copiar_pix",
  )
  async def copiar_pix(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await interaction.response.send_message(
        f"```\n{self.payload_pix}\n```\n*Copie o código acima e pague no aplicativo do seu banco.*",
        ephemeral=True,
    )


# Select Menu para escolher o Vencedor
class VencedorSelect(discord.ui.Select):

  def __init__(self, jogadores, eh_wo: bool = False):
    self.jogadores = jogadores
    self.eh_wo = eh_wo
    options = [
        discord.SelectOption(
            label=j.display_name, value=str(j.id), emoji="🏆"
        )
        for j in jogadores
    ]
    super().__init__(
        placeholder="Selecione o vencedor...",
        min_values=1,
        max_values=1,
        options=options,
    )

  async def callback(self, interaction: discord.Interaction):
    vencedor_id = int(self.values[0])
    vencedor = interaction.guild.get_member(vencedor_id)

    tipo_win = "Vitória por W.O" if self.eh_wo else "Vitória Confirmada"
    embed_win = discord.Embed(
        title=f"🏆 {tipo_win}!",
        description=(
            f"Parabéns {vencedor.mention}! A partida foi finalizada com sucesso.\n\n"
            f"**Vencedor:** {vencedor.mention}\n"
            f"**Mediador Responsável:** {interaction.user.mention}"
        ),
        color=discord.Color.gold(),
    )
    await interaction.response.send_message(
        content=vencedor.mention, embed=embed_win, ephemeral=False
    )


class VencedorSelectView(discord.ui.View):

  def __init__(self, jogadores, eh_wo: bool = False):
    super().__init__(timeout=120)
    self.add_item(VencedorSelect(jogadores, eh_wo))


# Select Menu com as opções do Painel do Mediador
class MediadorMenuSelect(discord.ui.Select):

  def __init__(self, confirm_view):
    self.confirm_view = confirm_view
    options = [
        discord.SelectOption(
            label="Definir Vencedor",
            description="Finaliza a partida definindo o vencedor.",
            value="definir_vencedor",
            emoji="🏆",
        ),
        discord.SelectOption(
            label="Liberar Pagamento",
            description="Libera o pagamento para o mediador.",
            value="liberar_pagamento",
            emoji="💸",
        ),
        discord.SelectOption(
            label="Vitória por W.O",
            description="Clique nessa opção para dar vitória por W.O.",
            value="vitoria_wo",
            emoji="👤",
        ),
        discord.SelectOption(
            label="Finalizar aposta",
            description="Clique nessa opção para finalizar a aposta.",
            value="finalizar_aposta",
            emoji="✖️",
        ),
    ]
    super().__init__(
        placeholder="Escolha uma opção de mediação...",
        min_values=1,
        max_values=1,
        options=options,
    )

  async def callback(self, interaction: discord.Interaction):
    if not checar_mediador_humano(interaction.user):
      await interaction.response.send_message(
          "❌ Apenas membros com o cargo **MEDIADOR** podem mexer neste painel!",
          ephemeral=True,
      )
      return

    escolha = self.values[0]

    if escolha == "definir_vencedor":
      await interaction.response.send_message(
          "🏆 **Selecione o vencedor:**",
          view=VencedorSelectView(self.confirm_view.jogadores, eh_wo=False),
          ephemeral=True,
      )

    elif escolha == "liberar_pagamento":
      try:
        preco_base = float(self.confirm_view.preco_str.replace(",", "."))
      except ValueError:
        preco_base = 0.20

      valor_com_taxa = preco_base + 0.15
      valor_formatado = f"{valor_com_taxa:.2f}".replace(".", ",")

      dados_pix = pix_mediadores.get(interaction.user.id, None)
      chave_pix = dados_pix["chave"] if dados_pix else "NÃO CADASTRADA"
      nome_recebedor = (
          dados_pix["nome"] if dados_pix else interaction.user.display_name
      )

      payload_pix = (
          f"PIX-PAGAMENTO-SALA|CHAVE:{chave_pix}|VALOR:{valor_formatado}"
      )

      qr_img = qrcode.make(payload_pix)
      img_buffer = io.BytesIO()
      qr_img.save(img_buffer, format="PNG")
      img_buffer.seek(0)
      arquivo_qr = discord.File(img_buffer, filename="qrcode_pix.png")

      embed_pagamento = discord.Embed(
          title="💸 Pagamento Liberado",
          description=(
              "Escaneie o QR Code abaixo ou use o botão **\"Copiar PIX\"** para"
              " realizar o pagamento.\n\n"
              f"**Valor:** R$ {valor_formatado}\n"
              f"**Recebedor:** {nome_recebedor} ({interaction.user.mention})"
          ),
          color=discord.Color.red(),
      )
      embed_pagamento.set_image(url="attachment://qrcode_pix.png")

      view_pix = PixCopiaColaView(payload_pix=payload_pix)
      await interaction.response.send_message(
          embed=embed_pagamento, file=arquivo_qr, view=view_pix, ephemeral=False
      )

    elif escolha == "vitoria_wo":
      await interaction.response.send_message(
          "👤 **Selecione quem venceu por W.O:**",
          view=VencedorSelectView(self.confirm_view.jogadores, eh_wo=True),
          ephemeral=True,
      )

    elif escolha == "finalizar_aposta":
      await interaction.response.send_message(
          "✖️ **Aposta Finalizada.** O canal será excluído em 5 segundos..."
      )
      await discord.utils.sleep_until(
          discord.utils.utcnow() + discord.utils.datetime.timedelta(seconds=5)
      )
      await interaction.channel.delete()


class MediadorMenuView(discord.ui.View):

  def __init__(self, confirm_view):
    super().__init__(timeout=120)
    self.add_item(MediadorMenuSelect(confirm_view))


# View para a Fila de Mediadores
class FilaMediadoresView(discord.ui.View):

  def __init__(self):
    super().__init__(timeout=None)

  @discord.ui.button(
      label="Entrar",
      style=discord.ButtonStyle.success,
      emoji="✅",
      custom_id="btn_entrar_fila_mediador",
  )
  async def entrar_fila(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    if not checar_mediador_humano(interaction.user):
      await interaction.response.send_message(
          "❌ Apenas membros com o cargo **MEDIADOR** podem entrar na fila de mediação!",
          ephemeral=True,
      )
      return

    if interaction.user in mediadores_em_plantao:
      await interaction.response.send_message(
          "⚠️ Você já está na fila de mediadores!", ephemeral=True
      )
      return

    mediadores_em_plantao.append(interaction.user)
    await self.atualizar_embed_mediadores(interaction)
    await interaction.response.send_message(
        "✅ Você entrou na fila de mediadores com sucesso!", ephemeral=True
    )

  @discord.ui.button(
      label="Sair",
      style=discord.ButtonStyle.danger,
      emoji="🚪",
      custom_id="btn_sair_fila_mediador",
  )
  async def sair_fila(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    if interaction.user not in mediadores_em_plantao:
      await interaction.response.send_message(
          "❌ Você não está na fila de mediadores!", ephemeral=True
      )
      return

    mediadores_em_plantao.remove(interaction.user)
    await self.atualizar_embed_mediadores(interaction)
    await interaction.response.send_message(
        "✅ Você saiu da fila de mediadores.", ephemeral=True
    )

  @discord.ui.button(
      label="🔄",
      style=discord.ButtonStyle.secondary,
      custom_id="btn_atualizar_fila_mediador",
  )
  async def atualizar_fila(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    await self.atualizar_embed_mediadores(interaction)
    await interaction.response.send_message(
        "🔄 Fila atualizada!", ephemeral=True
    )

  async def atualizar_embed_mediadores(self, interaction: discord.Interaction):
    embed = interaction.message.embeds[0]
    lista_texto = (
        "\n".join(
            f"{i + 1}. {m.mention}" for i, m in enumerate(mediadores_em_plantao)
        )
        if mediadores_em_plantao
        else "Nenhum mediador na fila..."
    )
    embed.description = (
        f"ℹ️ Seja bem-vindo(a) ao painel de mediação ORG TROOP | TAXA 15C!\n\n"
        f"**Status atual:** {len(mediadores_em_plantao)} mediador(es) na fila\n"
        f"{lista_texto}"
    )
    await interaction.message.edit(embed=embed, view=self)


# View principal dentro do canal privado
class ConfirmacaoView(discord.ui.View):

  def __init__(
      self,
      jogadores,
      formato: str,
      plataforma: str,
      preco: str,
      modo: str,
      mediador: discord.Member,
  ):
    super().__init__(timeout=None)
    self.jogadores = jogadores
    self.confirmados = []
    self.formato = formato
    self.plataforma = plataforma
    self.preco_str = preco
    self.modo = modo
    self.mediador = mediador

  @discord.ui.button(
      label="Confirmar",
      style=discord.ButtonStyle.success,
      custom_id="btn_confirmar",
      row=0,
  )
  async def confirmar(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    user = interaction.user

    if user not in self.jogadores:
      await interaction.response.send_message(
          "❌ Você não faz parte desta partida!", ephemeral=True
      )
      return

    if user in self.confirmados:
      await interaction.response.send_message(
          "⚠️ Você já confirmou a sua participação!", ephemeral=True
      )
      return

    self.confirmados.append(user)
    await interaction.response.send_message(
        f"✅ {user.mention} confirmou a participação.", ephemeral=False
    )

    embed = interaction.message.embeds[0]
    status_texto = "\n".join([
        f"[✅] {p.mention}" if p in self.confirmados else f"[ ] {p.mention}"
        for p in self.jogadores
    ])

    for field_index, field in enumerate(embed.fields):
      if "Status de Confirmação" in field.name:
        embed.set_field_at(
            field_index,
            name="Status de Confirmação:",
            value=status_texto,
            inline=False,
        )

    if len(self.confirmados) == len(self.jogadores):
      canal = interaction.channel
      try:
        await canal.edit(name=f"✅ | {canal.name}")
      except Exception:
        pass

    await interaction.message.edit(embed=embed, view=self)

  @discord.ui.button(
      label="Cancelar",
      style=discord.ButtonStyle.danger,
      custom_id="btn_cancelar",
      row=0,
  )
  async def cancelar(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    user = interaction.user

    if user not in self.jogadores and not checar_mediador_humano(user):
      await interaction.response.send_message(
          "❌ Você não faz parte desta partida!", ephemeral=True
      )
      return

    for child in self.children:
      child.disabled = True
    await interaction.message.edit(view=self)

    await interaction.response.send_message(
        f"❌ **Partida Cancelada** por {user.mention}. O canal será excluído em"
        " 3 segundos...",
        ephemeral=False,
    )

    await discord.utils.sleep_until(
        discord.utils.utcnow() + discord.utils.datetime.timedelta(seconds=3)
    )
    await interaction.channel.delete()

  # --- PAINEL DO MEDIADOR ---
  @discord.ui.button(
      label="Painel do mediador",
      style=discord.ButtonStyle.primary,
      emoji="👤",
      custom_id="btn_painel_mediador",
      row=1,
  )
  async def painel_mediador(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    if not checar_mediador_humano(interaction.user):
      await interaction.response.send_message(
          "❌ Apenas membros com o cargo **MEDIADOR** podem usar este painel!",
          ephemeral=True,
      )
      return

    await interaction.response.send_message(
        "🛠️ **Painel do Mediador:** Escolha uma opção no menu abaixo:",
        view=MediadorMenuView(self),
        ephemeral=True,
    )

  @discord.ui.button(
      label="Liberar pagamento",
      style=discord.ButtonStyle.success,
      emoji="💸",
      custom_id="btn_liberar_pagamento",
      row=1,
  )
  async def liberar_pagamento(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    if not checar_mediador_humano(interaction.user):
      await interaction.response.send_message(
          "❌ Apenas membros com o cargo **MEDIADOR** podem liberar pagamentos!",
          ephemeral=True,
      )
      return

    try:
      preco_base = float(self.preco_str.replace(",", "."))
    except ValueError:
      preco_base = 0.20

    valor_com_taxa = preco_base + 0.15
    valor_formatado = f"{valor_com_taxa:.2f}".replace(".", ",")

    dados_pix = pix_mediadores.get(interaction.user.id, None)
    chave_pix = dados_pix["chave"] if dados_pix else "NÃO CADASTRADA"
    nome_recebedor = (
        dados_pix["nome"] if dados_pix else interaction.user.display_name
    )

    payload_pix = f"PIX-PAGAMENTO-SALA|CHAVE:{chave_pix}|VALOR:{valor_formatado}"

    qr_img = qrcode.make(payload_pix)
    img_buffer = io.BytesIO()
    qr_img.save(img_buffer, format="PNG")
    img_buffer.seek(0)
    arquivo_qr = discord.File(img_buffer, filename="qrcode_pix.png")

    embed_pagamento = discord.Embed(
        title="💸 Pagamento Liberado",
        description=(
            "Escaneie o QR Code abaixo ou use o botão **\"Copiar PIX\"** para"
            " realizar o pagamento.\n\n"
            f"**Valor:** R$ {valor_formatado}\n"
            f"**Recebedor:** {nome_recebedor} ({interaction.user.mention})"
        ),
        color=discord.Color.red(),
    )
    embed_pagamento.set_image(url="attachment://qrcode_pix.png")

    view_pix = PixCopiaColaView(payload_pix=payload_pix)
    await interaction.response.send_message(
        embed=embed_pagamento, file=arquivo_qr, view=view_pix, ephemeral=False
    )

  @discord.ui.button(
      label="Fornecer sala",
      style=discord.ButtonStyle.secondary,
      emoji="🎮",
      custom_id="btn_fornecer_sala",
      row=1,
  )
  async def fornecer_sala(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    if not checar_mediador_humano(interaction.user):
      await interaction.response.send_message(
          "❌ Apenas membros com o cargo **MEDIADOR** podem fornecer dados da"
          " sala!",
          ephemeral=True,
      )
      return

    await interaction.response.send_modal(FornecerSalaModal())

  @discord.ui.button(
      label="SS Emulador",
      style=discord.ButtonStyle.danger,
      emoji="📚",
      custom_id="btn_ss_emulador",
      row=2,
  )
  async def ss_emulador(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    if not checar_mediador_humano(interaction.user):
      await interaction.response.send_message(
          "❌ Apenas membros com o cargo **MEDIADOR** podem solicitar SS!",
          ephemeral=True,
      )
      return

    await interaction.response.send_message(
        "📸 **Solicitação de SS (Emulador):** Enviem a print/screen das"
        " configurações do emulador no canal.",
        ephemeral=False,
    )

  @discord.ui.button(
      label="SS Mobile",
      style=discord.ButtonStyle.danger,
      emoji="📱",
      custom_id="btn_ss_mobile",
      row=2,
  )
  async def ss_mobile(
      self, interaction: discord.Interaction, button: discord.ui.Button
  ):
    if not checar_mediador_humano(interaction.user):
      await interaction.response.send_message(
          "❌ Apenas membros com o cargo **MEDIADOR** podem solicitar SS!",
          ephemeral=True,
      )
      return

    await interaction.response.send_message(
        "📱 **Solicitação de SS (Mobile):** Enviem a print da tela inteira do"
        " jogo.",
        ephemeral=False,
    )


# View da fila principal
class FilaModosView(discord.ui.View):

  def __init__(
      self,
      formato: str,
      plataforma: str,
      preco: str,
      limite_max: int = 2,
  ):
    super().__init__(timeout=None)
    self.formato = formato
    self.plataforma = plataforma
    self.preco = preco
    self.limite_max = limite_max
    self.jogadores = []
    self.modo_escolhido = "Não selecionado"

    formato_normalizado = formato.strip().lower()
    plataforma_normalizada = plataforma.strip().lower()

    # 2v2 Misto: 1 Emu
    if plataforma_normalizada == "misto" and formato_normalizado == "2v2":
      botoes_modo = [("1 Emu", discord.ButtonStyle.primary, None, "1_emu")]
    # 3v3 Misto: 1 Emu e 2 Emu
    elif plataforma_normalizada == "misto" and formato_normalizado == "3v3":
      botoes_modo = [
          ("1 Emu", discord.ButtonStyle.primary, None, "1_emu"),
          ("2 Emu", discord.ButtonStyle.primary, None, "2_emu"),
      ]
    # 4v4 Misto: 1 Emu, 2 Emu e 3 Emu
    elif plataforma_normalizada == "misto" and formato_normalizado == "4v4":
      botoes_modo = [
          ("1 Emu", discord.ButtonStyle.primary, None, "1_emu"),
          ("2 Emu", discord.ButtonStyle.primary, None, "2_emu"),
          ("3 Emu", discord.ButtonStyle.primary, None, "3_emu"),
      ]
    # 2v2, 3v3 e 4v4 Emulador: Normal e Full Ump e Xm8
    elif plataforma_normalizada == "emulador" and formato_normalizado in {
        "2v2",
        "3v3",
        "4v4",
    }:
      botoes_modo = [
          ("Normal", discord.ButtonStyle.primary, "✅", "normal"),
          ("Full Ump e Xm8", discord.ButtonStyle.primary, "🔫", "full_ump_xm8"),
      ]
    # 2v2, 3v3 e 4v4 Mobile
    elif plataforma_normalizada == "mobile" and formato_normalizado in {
        "2v2",
        "3v3",
        "4v4",
    }:
      botoes_modo = [
          ("Normal", discord.ButtonStyle.primary, "✅", "normal"),
          ("full ump e xm8", discord.ButtonStyle.primary, "🔫", "full_ump_xm8"),
          ("mobilador", discord.ButtonStyle.primary, "📱", "mobilador"),
      ]
    # 1v1 Emulador
    elif plataforma_normalizada == "emulador" and formato_normalizado == "1v1":
      botoes_modo = [
          ("gelo infinito", discord.ButtonStyle.primary, "🧊", "gelo_infinito"),
          ("gelo normal", discord.ButtonStyle.primary, "🧊", "gelo_normal"),
      ]
    # Padrão para outros casos
    else:
      botoes_modo = [
          ("Gelo Infinito", discord.ButtonStyle.primary, None, "gelo_infinito"),
          ("Gelo Normal", discord.ButtonStyle.success, None, "gelo_normal"),
          ("Modo Padrão", discord.ButtonStyle.secondary, None, "modo_padrao"),
      ]

    for label, style, emoji, slug in botoes_modo:
      botao = discord.ui.Button(
          label=label,
          style=style,
          emoji=emoji,
          custom_id=(
              f"fila_{plataforma_normalizada}_{formato_normalizado}_{slug}"
          ),
      )
      botao.callback = self._criar_callback_modo(label)
      self.add_item(botao)

    botao_sair = discord.ui.Button(
        label="Sair",
        style=discord.ButtonStyle.danger,
        emoji="❌",
        custom_id=(
            f"fila_{plataforma_normalizada}_{formato_normalizado}_sair"
        ),
    )
    botao_sair.callback = self.sair_fila
    self.add_item(botao_sair)

  def _criar_callback_modo(self, modo: str):

    async def callback(interaction: discord.Interaction):
      await self.inscrever_jogador(interaction, modo)

    return callback

  async def sair_fila(self, interaction: discord.Interaction):
    user = interaction.user
    if user not in self.jogadores:
      await interaction.response.send_message(
          "❌ Você não está inscrito nesta fila!", ephemeral=True
      )
      return

    self.jogadores.remove(user)
    if not self.jogadores:
      self.modo_escolhido = "Não selecionado"

    await self.atualizar_embed(interaction)
    await interaction.response.send_message(
        "✅ Você saiu da fila com sucesso!", ephemeral=True
    )

  async def inscrever_jogador(
      self, interaction: discord.Interaction, modo: str
  ):
    user = interaction.user

    if user in self.jogadores:
      await interaction.response.send_message(
          "❌ Você já está inscrito nesta fila!", ephemeral=True
      )
      return

    if len(self.jogadores) >= self.limite_max:
      await interaction.response.send_message(
          "⚠️ A fila está cheia!", ephemeral=True
      )
      return

    self.modo_escolhido = modo
    self.jogadores.append(user)

    if len(self.jogadores) >= self.limite_max:
      guild = interaction.guild
      overwrites = {
          guild.default_role: discord.PermissionOverwrite(read_messages=False),
          interaction.client.user: discord.PermissionOverwrite(
              read_messages=True, send_messages=True
          ),
      }

      jogadores_desta_sala = list(self.jogadores)
      for jogador in jogadores_desta_sala:
        overwrites[jogador] = discord.PermissionOverwrite(
            read_messages=True, send_messages=True
        )

      mediador_escolhido = None

      # Sorteia um mediador diretamente da fila de plantão de mediadores
      if mediadores_em_plantao:
        mediador_escolhido = random.choice(mediadores_em_plantao)
        overwrites[mediador_escolhido] = discord.PermissionOverwrite(
            read_messages=True, send_messages=True
        )

      canal_privado = await guild.create_text_channel(
          name=f"fila-{random.randint(10000, 99999)}",
          overwrites=overwrites,
      )
      await interaction.response.send_message(
          f"🔒 **Sala Fechada!** Canal criado: {canal_privado.mention}",
          ephemeral=True,
      )

      mencoes_jogadores_status = "\n".join(
          f"[ ] {p.mention}" for p in jogadores_desta_sala
      )
      texto_mediador = (
          mediador_escolhido.mention
          if mediador_escolhido
          else "Nenhum mediador na fila de plantão"
      )

      try:
        p_base = float(self.preco.replace(",", "."))
        venc_valor = f"{(p_base * 2):.2f}".replace(".", ",")
      except ValueError:
        venc_valor = "0,40"

      try:
        val_taxa = f"{(float(self.preco.replace(',', '.')) + 0.15):.2f}".replace(
            ".", ","
        )
      except ValueError:
        val_taxa = self.preco

      embed_confirmacao = discord.Embed(
          title="⚔️ Confirmação de Partida",
          description=(
              "Uma nova partida foi detectada. Todos os jogadores precisam"
              " confirmar para prosseguir."
          ),
          color=discord.Color.red(),
      )
      embed_confirmacao.add_field(
          name="📁 Detalhes da Partida",
          value=(
              f"📂 **Modo:** {self.formato}\n"
              f"📱 **Plataforma:** {self.plataforma.capitalize()} |"
              f" {self.modo_escolhido}\n"
              f"🎮 **Jogo:** Free Fire\n"
              f"💎 **Valor:** R$ {val_taxa}\n"
              f"💸 **Pagar ao vencedor:** R$ {venc_valor}\n"
              f"👤 **Mediador:** {texto_mediador}"
          ),
          inline=False,
      )
      embed_confirmacao.add_field(
          name="Status de Confirmação:",
          value=mencoes_jogadores_status,
          inline=False,
      )

      mencoes_geral = (
          f"{' '.join(p.mention for p in jogadores_desta_sala)} {texto_mediador if mediador_escolhido else ''}"
      )
      view_conf = ConfirmacaoView(
          jogadores_desta_sala,
          self.formato,
          self.plataforma,
          self.preco,
          self.modo_escolhido,
          mediador_escolhido,
      )
      await canal_privado.send(
          content=mencoes_geral, embed=embed_confirmacao, view=view_conf
      )

      self.jogadores = []
      self.modo_escolhido = "Não selecionado"
      await self.atualizar_embed(interaction)
    else:
      await self.atualizar_embed(interaction)
      await interaction.response.send_message(
          f"✅ Entraste na fila com o modo **{modo}**! "
          f"({len(self.jogadores)}/{self.limite_max})",
          ephemeral=True,
      )

  async def atualizar_embed(self, interaction: discord.Interaction):
    embed = interaction.message.embeds[0]
    lista_jogadores = (
        "\n".join(
            f"{i + 1}. {p.mention} | {self.modo_escolhido}"
            for i, p in enumerate(self.jogadores)
        )
        if self.jogadores
        else "Sem jogadores..."
    )
    embed.description = (
        f"**Formato:** {self.formato}\n"
        f"**Preço:** R$ {self.preco}\n\n"
        f"**Jogadores:**\n{lista_jogadores}"
    )
    await interaction.message.edit(embed=embed, view=self)


# Comando para criar o Painel de Configurar PIX
@bot.tree.command(
    name="painel_pix",
    description="Cria o painel Central de Pagamentos dos Mediadores",
)
async def painel_pix(interaction: discord.Interaction):
  embed = discord.Embed(
      title="💸 Central de Pagamentos: Mediadores",
      description=(
          "Bem-vindo ao sistema de remuneração. Para garantir o recebimento"
          " ágil de suas participações, mantenha seus dados PIX sempre"
          " atualizados.\n\n"
          "🔑 **Chave PIX:** CPF, E-mail, Telefone ou Chave Aleatória\n"
          "👤 **Nome Completo:** Titular da conta bancária\n"
          "💬 **Cidade:** Cidade de registro da conta\n\n"
          "⚠️ **Importante:** Os pagamentos são processados com base nestes"
          " dados. Verifique cuidadosamente antes de salvar."
      ),
      color=discord.Color.dark_gray(),
  )
  view = PainelPixView()
  await interaction.channel.send(embed=embed, view=view)
  await interaction.response.send_message(
      "✅ Painel de Pagamentos criado com sucesso!", ephemeral=True
  )


# Comando direto para criar o Painel de Mediadores (Fila)
@bot.tree.command(
    name="painel_mediadores",
    description="Cria o painel da Fila de Mediadores",
)
async def painel_mediadores(interaction: discord.Interaction):
  embed = discord.Embed(
      title="👤 Fila de Mediadores",
      description=(
          "ℹ️ Seja bem-vindo(a) ao painel de mediação ORG TROOP | TAXA 15C!\n\n"
          "**Status atual:** 0 mediador(es) na fila\n"
          "Nenhum mediador na fila..."
      ),
      color=discord.Color.red(),
  )
  view = FilaMediadoresView()
  await interaction.channel.send(embed=embed, view=view)
  await interaction.response.send_message(
      "✅ Painel da Fila de Mediadores criado com sucesso!", ephemeral=True
  )


# Comando para criar automaticamente todos os painéis de partidas
@bot.tree.command(
    name="criar_fila",
    description=(
        "Cria todos os painéis de fila com preços invertidos e limite correto"
    ),
)
@app_commands.describe(
    formato="Escolha o formato da partida",
    plataforma="Escolha o tipo de dispositivo permitido",
)
@app_commands.choices(
    formato=[
        app_commands.Choice(name="1v1", value="1v1"),
        app_commands.Choice(name="2v2", value="2v2"),
        app_commands.Choice(name="3v3", value="3v3"),
        app_commands.Choice(name="4v4", value="4v4"),
    ],
    plataforma=[
        app_commands.Choice(name="Mobile", value="mobile"),
        app_commands.Choice(name="Emulador", value="emulador"),
        app_commands.Choice(name="Misto", value="misto"),
    ],
)
async def criar_fila(
    interaction: discord.Interaction,
    formato: app_commands.Choice[str],
    plataforma: app_commands.Choice[str],
):
  limites = {"1v1": 2, "2v2": 2, "3v3": 2, "4v4": 2}

  limite_max = limites.get(formato.value, 2)

  precos = [
      "100,00",
      "55,00",
      "50,00",
      "35,00",
      "30,00",
      "25,00",
      "20,00",
      "10,00",
      "5,00",
      "3,50",
      "3,00",
      "2,50",
      "2,00",
      "1,50",
      "1,00",
      "0,50",
      "0,25",
      "0,20",
  ]

  await interaction.response.send_message(
      f"🚀 A criar todos os painéis para **{formato.name} | {plataforma.name}**"
      f" (Limite: {limite_max} jogadores) do R$ 100,00 ao R$ 0,20...",
      ephemeral=True,
  )

  for preco in precos:
    titulo_painel = f"{formato.value} | {plataforma.value}"

    embed = discord.Embed(
        title=titulo_painel,
        description=(
            f"**Formato:** {formato.value}\n"
            f"**Preço:** R$ {preco}\n\n"
            f"**Jogadores:**\nSem jogadores..."
        ),
        color=discord.Color.red(),
    )
    view = FilaModosView(
        formato=formato.value,
        plataforma=plataforma.value,
        preco=preco,
        limite_max=limite_max,
    )
    await interaction.channel.send(embed=embed, view=view)


bot.run(os.getenv("TOKEN"))
