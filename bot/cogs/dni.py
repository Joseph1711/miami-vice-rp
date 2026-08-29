import discord
from discord import app_commands
from discord.ext import commands
import datetime

from bot.db import aexecute
from bot.helpers import (
    async_get_or_create_user,
    generate_id,
    generate_unique_dni,
    check_admin_permission
)
from bot.embeds import success_embed, error_embed, info_embed


class CreateDNIModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Creación de DNI — Documento de Identidad")

        self.full_name = discord.ui.TextInput(
            label="Nombre y Apellidos de tu Personaje (IC)",
            placeholder="Ej: Alejandro Morales Ruiz",
            max_length=100,
            required=True
        )
        self.birth_date = discord.ui.TextInput(
            label="Fecha de Nacimiento (DD/MM/AAAA)",
            placeholder="Ej: 14/08/1996",
            max_length=15,
            required=True
        )
        self.gender = discord.ui.TextInput(
            label="Género del Personaje",
            placeholder="Ej: Masculino / Femenino / No binario",
            max_length=30,
            required=True
        )
        self.nationality = discord.ui.TextInput(
            label="Nacionalidad / Lugar de Origen",
            placeholder="Ej: Estadounidense (Miami, Florida) / Español / Mexicano",
            max_length=60,
            required=True
        )
        self.occupation = discord.ui.TextInput(
            label="Ocupación o Profesión Principal",
            placeholder="Ej: Médico, Conductor, Abogado, Comerciante, Desempleado",
            max_length=60,
            required=False
        )

        self.add_item(self.full_name)
        self.add_item(self.birth_date)
        self.add_item(self.gender)
        self.add_item(self.nationality)
        self.add_item(self.occupation)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        gid = str(interaction.guild_id)
        uid = str(interaction.user.id)

        # Check existing active DNI
        existing = await aexecute(
            "SELECT * FROM dni_records WHERE guild_id=$1 AND discord_id=$2",
            (gid, uid), fetch="one"
        )

        # Get roblox username if linked
        user_row = await async_get_or_create_user(uid, gid, username=interaction.user.name, display_name=interaction.user.display_name)
        roblox_user = user_row.get("roblox_username")

        if existing:
            dni_num = existing["dni_number"]
            await aexecute(
                """UPDATE dni_records 
                   SET full_name=$1, birth_date=$2, gender=$3, nationality=$4, occupation=$5, 
                       roblox_username=$6, status='active', updated_at=NOW()
                   WHERE id=$7""",
                (self.full_name.value.strip(), self.birth_date.value.strip(), self.gender.value.strip(),
                 self.nationality.value.strip(), self.occupation.value.strip() or "Ciudadano", roblox_user, existing["id"])
            )
            msg_title = "🪪 DNI Actualizado con Éxito"
            msg_desc = f"Tu documento de identidad nacional ha sido actualizado."
        else:
            dni_num = await generate_unique_dni(gid)
            await aexecute(
                """INSERT INTO dni_records 
                   (id, guild_id, discord_id, dni_number, full_name, birth_date, gender, nationality, occupation, roblox_username, status, created_at, updated_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,'active',NOW(),NOW())""",
                (generate_id(), gid, uid, dni_num, self.full_name.value.strip(), self.birth_date.value.strip(),
                 self.gender.value.strip(), self.nationality.value.strip(), self.occupation.value.strip() or "Ciudadano", roblox_user)
            )
            msg_title = "🪪 DNI Expedido con Éxito"
            msg_desc = f"Se ha emitido tu documento de identidad oficial único."

        card = info_embed(
            f"🪪 DOCUMENTO NACIONAL DE IDENTIDAD — CIUDAD DE MIAMI",
            f"**Número de DNI:** `{dni_num}`\n**Estado:** 🟢 Activo / Válido"
        )
        card.set_thumbnail(url=interaction.user.display_avatar.url)
        card.add_field(name="👤 Nombre Completo", value=self.full_name.value.strip(), inline=True)
        card.add_field(name="📅 Fecha de Nacimiento", value=self.birth_date.value.strip(), inline=True)
        card.add_field(name="⚧ Género", value=self.gender.value.strip(), inline=True)
        card.add_field(name="🌎 Nacionalidad", value=self.nationality.value.strip(), inline=True)
        card.add_field(name="💼 Ocupación", value=self.occupation.value.strip() or "Ciudadano", inline=True)
        if roblox_user:
            card.add_field(name="🎮 Perfil de Roblox", value=f"[{roblox_user}](https://www.roblox.com/search/users?keyword={roblox_user})", inline=True)
        card.set_footer(text=f"Titular: @{interaction.user.name} • Discord ID: {interaction.user.id}")

        await interaction.followup.send(embed=card, ephemeral=True)


class DNI(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    dni_group = app_commands.Group(name="dni", description="Sistema de Documento Nacional de Identidad (DNI)")

    @dni_group.command(name="crear", description="Crear o tramitar tu Documento Nacional de Identidad (DNI)")
    async def dni_crear(self, interaction: discord.Interaction):
        modal = CreateDNIModal()
        await interaction.response.send_modal(modal)

    @dni_group.command(name="ver", description="Ver el DNI de un ciudadano")
    @app_commands.describe(usuario="Ciudadano a consultar (omite para ver el tuyo)")
    async def dni_ver(self, interaction: discord.Interaction, usuario: discord.Member = None):
        await interaction.response.defer()
        target = usuario or interaction.user
        gid = str(interaction.guild_id)
        uid = str(target.id)

        record = await aexecute(
            "SELECT * FROM dni_records WHERE guild_id=$1 AND discord_id=$2",
            (gid, uid), fetch="one"
        )

        if not record:
            if target.id == interaction.user.id:
                await interaction.followup.send(embed=error_embed(
                    "Sin DNI",
                    "Aún no has tramitado tu DNI. Puedes crearlo gratis ahora mismo usando el comando `/dni crear`."
                ), ephemeral=True)
            else:
                await interaction.followup.send(embed=error_embed(
                    "Sin DNI",
                    f"{target.mention} no tiene un DNI registrado en el sistema."
                ), ephemeral=True)
            return

        # Fetch Roblox user info if available
        user_row = await aexecute(
            "SELECT * FROM users WHERE guild_id=$1 AND discord_id=$2",
            (gid, uid), fetch="one"
        ) or {}
        roblox_name = user_row.get("roblox_username") or record.get("roblox_username")
        roblox_id = user_row.get("roblox_id")

        status = record.get("status", "active")
        status_map = {
            "active": "🟢 Válido / Activo",
            "revoked": "🔴 Revocado / Anulado",
            "suspended": "🟡 Suspendido"
        }

        card = info_embed(
            f"🪪 DOCUMENTO NACIONAL DE IDENTIDAD",
            f"**Número Único:** `{record['dni_number']}`\n**Estado Legal:** {status_map.get(status, status)}"
        )
        card.set_thumbnail(url=target.display_avatar.url)
        card.add_field(name="👤 Nombre Completo", value=f"**{record.get('full_name', 'N/A')}**", inline=True)
        card.add_field(name="📅 Fecha Nacimiento", value=record.get('birth_date', 'N/A'), inline=True)
        card.add_field(name="⚧ Género", value=record.get('gender', 'N/A'), inline=True)
        card.add_field(name="🌎 Nacionalidad", value=record.get('nationality', 'N/A'), inline=True)
        card.add_field(name="💼 Ocupación", value=record.get('occupation', 'Ciudadano'), inline=True)

        if roblox_name:
            roblox_link = f"https://www.roblox.com/users/{roblox_id}/profile" if roblox_id else f"https://www.roblox.com/search/users?keyword={roblox_name}"
            card.add_field(name="🎮 Roblox Vinculado", value=f"[{roblox_name}]({roblox_link})", inline=True)
        else:
            card.add_field(name="🎮 Roblox", value="*Sin vincular (`/roblox vincular`)*", inline=True)

        issue_date = str(record.get("created_at", ""))[:10]
        card.set_footer(text=f"Expedido: {issue_date} • Titular: @{target.name} ({target.id})")
        await interaction.followup.send(embed=card)

    @dni_group.command(name="buscar", description="Buscar a un ciudadano por su número de DNI")
    @app_commands.describe(numero_dni="Número de DNI exacto (ej: MIA-123456)")
    async def dni_buscar(self, interaction: discord.Interaction, numero_dni: str):
        await interaction.response.defer()
        gid = str(interaction.guild_id)
        cleaned = numero_dni.strip().upper()

        record = await aexecute(
            "SELECT * FROM dni_records WHERE guild_id=$1 AND dni_number ILIKE $2",
            (gid, cleaned), fetch="one"
        )

        if not record:
            await interaction.followup.send(embed=error_embed(
                "DNI No Encontrado",
                f"No existe ningún registro ciudadano con el DNI **{cleaned}**."
            ), ephemeral=True)
            return

        status = record.get("status", "active")
        status_map = {
            "active": "🟢 Válido / Activo",
            "revoked": "🔴 Revocado / Anulado",
            "suspended": "🟡 Suspendido"
        }

        user_row = await aexecute(
            "SELECT * FROM users WHERE guild_id=$1 AND discord_id=$2",
            (gid, record["discord_id"]), fetch="one"
        ) or {}
        roblox_name = user_row.get("roblox_username") or record.get("roblox_username")

        card = info_embed(
            f"🪪 Registro Ciudadano — {record['dni_number']}",
            f"**Titular:** <@{record['discord_id']}>\n**Estado:** {status_map.get(status, status)}"
        )
        card.add_field(name="👤 Nombre Completo", value=record.get('full_name', 'N/A'), inline=True)
        card.add_field(name="📅 Nacimiento", value=record.get('birth_date', 'N/A'), inline=True)
        card.add_field(name="⚧ Género", value=record.get('gender', 'N/A'), inline=True)
        card.add_field(name="🌎 Nacionalidad", value=record.get('nationality', 'N/A'), inline=True)
        card.add_field(name="💼 Ocupación", value=record.get('occupation', 'Ciudadano'), inline=True)
        if roblox_name:
            card.add_field(name="🎮 Roblox", value=roblox_name, inline=True)

        await interaction.followup.send(embed=card)

    @dni_group.command(name="revocar", description="Revocar o suspender el DNI de un usuario (Admin/Policía)")
    @app_commands.describe(usuario="Ciudadano a sancionar", motivo="Motivo de la revocación")
    async def dni_revocar(self, interaction: discord.Interaction, usuario: discord.Member, motivo: str):
        await interaction.response.defer()
        if not await check_admin_permission(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores autorizados"), ephemeral=True)
            return

        gid = str(interaction.guild_id)
        record = await aexecute(
            "SELECT * FROM dni_records WHERE guild_id=$1 AND discord_id=$2",
            (gid, str(usuario.id)), fetch="one"
        )

        if not record:
            await interaction.followup.send(embed=error_embed("Sin DNI", f"{usuario.mention} no tiene un DNI registrado."), ephemeral=True)
            return

        await aexecute(
            "UPDATE dni_records SET status='revoked', updated_at=NOW() WHERE id=$1",
            (record["id"],)
        )

        await interaction.followup.send(embed=success_embed(
            "🪪 DNI Revocado",
            f"El DNI `{record['dni_number']}` de {usuario.mention} ha sido marcado como **REVOCADO**.\n**Motivo:** {motivo}"
        ))


async def setup(bot):
    await bot.add_cog(DNI(bot))
