import discord
from discord import app_commands
from discord.ext import commands
import datetime

from bot.db import aexecute
from bot.helpers import (
    async_get_or_create_user,
    generate_id,
    generate_unique_weapon_serial,
    check_admin_permission
)
from bot.embeds import success_embed, error_embed, info_embed


class RegisterWeaponModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Registro y Licencia Balística de Arma")

        self.weapon_name = discord.ui.TextInput(
            label="Modelo y Nombre del Arma",
            placeholder="Ej: Glock 19, Colt 1911, Remington 870, AR-15",
            max_length=80,
            required=True
        )
        self.caliber = discord.ui.TextInput(
            label="Calibre del Arma",
            placeholder="Ej: 9x19mm Parabellum, .45 ACP, 12 Gauge, 5.56x45mm NATO",
            max_length=50,
            required=True
        )
        self.reason = discord.ui.TextInput(
            label="Motivo o Justificación de Porte/Posesión",
            placeholder="Ej: Defensa personal y protección ciudadana, Caza deportiva, Servicio de seguridad",
            style=discord.TextStyle.paragraph,
            max_length=300,
            required=True
        )

        self.add_item(self.weapon_name)
        self.add_item(self.caliber)
        self.add_item(self.reason)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        gid = str(interaction.guild_id)
        uid = str(interaction.user.id)

        # Check citizen DNI
        dni = await aexecute(
            "SELECT * FROM dni_records WHERE guild_id=$1 AND discord_id=$2 AND status='active'",
            (gid, uid), fetch="one"
        )
        if not dni:
            await interaction.followup.send(embed=error_embed(
                "Requiere DNI",
                "Para registrar legalmente un arma de fuego debes contar con un DNI válido y activo. Tramítalo con `/dni crear`."
            ), ephemeral=True)
            return

        serial_num = await generate_unique_weapon_serial(gid)
        reg_id = generate_id()

        await aexecute(
            """INSERT INTO weapon_registries 
               (id, guild_id, discord_id, weapon_name, serial_number, caliber, status, notes, registered_at, created_at, updated_at)
               VALUES ($1,$2,$3,$4,$5,$6,'registered',$7,NOW(),NOW(),NOW())""",
            (reg_id, gid, uid, self.weapon_name.value.strip(), serial_num, self.caliber.value.strip(), self.reason.value.strip())
        )

        card = success_embed(
            f"🔫 Licencia y Registro Balístico Emitido",
            f"Tu arma ha sido registrada exitosamente en la base de datos balística de Miami."
        )
        card.add_field(name="🔫 Modelo", value=self.weapon_name.value.strip(), inline=True)
        card.add_field(name="🔢 Número de Serie Único", value=f"`{serial_num}`", inline=True)
        card.add_field(name="🎯 Calibre", value=self.caliber.value.strip(), inline=True)
        card.add_field(name="🪪 Titular y DNI", value=f"{dni['full_name']} (`{dni['dni_number']}`)", inline=True)
        card.add_field(name="📜 Justificación", value=self.reason.value.strip(), inline=False)
        card.set_footer(text=f"ID Balístico: {reg_id[:8]} • Fecha: {datetime.datetime.utcnow().strftime('%Y-%m-%d')}")

        await interaction.followup.send(embed=card, ephemeral=True)


class Weapons(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    arma_group = app_commands.Group(name="arma", description="Sistema de registro balístico y licencias de armas")

    @arma_group.command(name="registrar", description="Registrar un arma con un número de serie balístico único")
    async def arma_registrar(self, interaction: discord.Interaction):
        modal = RegisterWeaponModal()
        await interaction.response.send_modal(modal)

    @arma_group.command(name="mis_armas", description="Ver todas las armas registradas a tu nombre")
    async def arma_mis_armas(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = str(interaction.guild_id)
        uid = str(interaction.user.id)

        records = await aexecute(
            "SELECT * FROM weapon_registries WHERE guild_id=$1 AND discord_id=$2 ORDER BY registered_at DESC",
            (gid, uid), fetch="all"
        ) or []

        e = info_embed("🔫 Tus Armas Registradas")
        if not records:
            e.description = "No tienes ningún arma registrada a tu nombre. Usa `/arma registrar` para tramitar la licencia de porte."
        else:
            status_map = {
                "registered": "🟢 Legal / Registrada",
                "confiscated": "🔴 Incautada / Confiscada",
                "revoked": "❌ Licencia Revocada",
                "transferred": "🔄 Transferida"
            }
            for r in records:
                status_txt = status_map.get(r.get("status"), r.get("status"))
                reg_date = str(r.get("registered_at", ""))[:10]
                e.add_field(
                    name=f"🔫 {r['weapon_name']} — `{r['serial_number']}`",
                    value=f"• **Calibre:** {r.get('caliber', 'N/A')}\n• **Estado:** {status_txt}\n• **Fecha:** {reg_date}",
                    inline=False
                )

        await interaction.followup.send(embed=e, ephemeral=True)

    @arma_group.command(name="ver", description="Consultar el registro balístico de un arma por su número de serie")
    @app_commands.describe(numero_serie="Número de serie único del arma (ej: MV-WPN-123456-FL)")
    async def arma_ver(self, interaction: discord.Interaction, numero_serie: str):
        await interaction.response.defer()
        gid = str(interaction.guild_id)
        cleaned = numero_serie.strip().upper()

        record = await aexecute(
            "SELECT * FROM weapon_registries WHERE guild_id=$1 AND serial_number ILIKE $2",
            (gid, cleaned), fetch="one"
        )

        if not record:
            await interaction.followup.send(embed=error_embed(
                "Arma No Registrada",
                f"No existe ningún arma registrada con el número de serie **{cleaned}**. Podría ser un arma ilegal no matriculada."
            ), ephemeral=True)
            return

        dni = await aexecute(
            "SELECT * FROM dni_records WHERE guild_id=$1 AND discord_id=$2",
            (gid, record["discord_id"]), fetch="one"
        )

        status_map = {
            "registered": "🟢 Legal y Matriculada",
            "confiscated": "🔴 Incautada por la Autoridad",
            "revoked": "❌ Registro Revocado",
            "transferred": "🔄 Transferida"
        }

        e = info_embed(
            f"🔫 Registro Balístico — {record['serial_number']}",
            f"**Modelo:** {record['weapon_name']}\n**Estado Balístico:** {status_map.get(record.get('status'), record.get('status'))}"
        )
        e.add_field(name="🎯 Calibre", value=record.get("caliber", "N/A"), inline=True)
        e.add_field(name="🔢 Serie Única", value=f"`{record['serial_number']}`", inline=True)

        if dni:
            e.add_field(name="🪪 Propietario Legal", value=f"{dni['full_name']} (`{dni['dni_number']}`)\n<@{record['discord_id']}>", inline=True)
        else:
            e.add_field(name="🪪 Propietario Legal", value=f"<@{record['discord_id']}>", inline=True)

        if record.get("notes"):
            e.add_field(name="📝 Notas de Registro", value=record["notes"], inline=False)

        await interaction.followup.send(embed=e)

    @arma_group.command(name="transferir", description="Transferir legalmente la titularidad de un arma a otro ciudadano")
    @app_commands.describe(numero_serie="Número de serie del arma", nuevo_titular="Ciudadano al que transferirás el arma")
    async def arma_transferir(self, interaction: discord.Interaction, numero_serie: str, nuevo_titular: discord.Member):
        await interaction.response.defer()
        gid = str(interaction.guild_id)
        uid = str(interaction.user.id)
        cleaned = numero_serie.strip().upper()

        record = await aexecute(
            "SELECT * FROM weapon_registries WHERE guild_id=$1 AND discord_id=$2 AND serial_number ILIKE $3",
            (gid, uid, cleaned), fetch="one"
        )

        if not record:
            await interaction.followup.send(embed=error_embed(
                "No Encontrada",
                f"No posees ningún arma registrada con el número de serie **{cleaned}**."
            ), ephemeral=True)
            return

        if record.get("status") != "registered":
            await interaction.followup.send(embed=error_embed(
                "No Transferible",
                f"Esta arma no puede ser transferida debido a que su estado actual es **{record.get('status')}**."
            ), ephemeral=True)
            return

        # Check target DNI
        target_dni = await aexecute(
            "SELECT * FROM dni_records WHERE guild_id=$1 AND discord_id=$2 AND status='active'",
            (gid, str(nuevo_titular.id)), fetch="one"
        )
        if not target_dni:
            await interaction.followup.send(embed=error_embed(
                "Destinatario sin DNI",
                f"{nuevo_titular.mention} no tiene un DNI activo. Requiere uno para poseer armas registradas legalmente."
            ), ephemeral=True)
            return

        await aexecute(
            "UPDATE weapon_registries SET discord_id=$1, updated_at=NOW() WHERE id=$2",
            (str(nuevo_titular.id), record["id"])
        )

        await interaction.followup.send(embed=success_embed(
            "🔫 Titularidad Transferida",
            f"El arma **{record['weapon_name']}** (Serie `{record['serial_number']}`) ha sido transferida exitosamente a {nuevo_titular.mention} ({target_dni['full_name']})."
        ))

    @arma_group.command(name="incautar", description="Incautar/confiscar un arma en procedimiento policial (Admin/Policía)")
    @app_commands.describe(numero_serie="Número de serie del arma", motivo="Motivo de la incautación")
    async def arma_incautar(self, interaction: discord.Interaction, numero_serie: str, motivo: str):
        await interaction.response.defer()
        if not await check_admin_permission(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores y fuerzas autorizadas"), ephemeral=True)
            return

        gid = str(interaction.guild_id)
        cleaned = numero_serie.strip().upper()

        record = await aexecute(
            "SELECT * FROM weapon_registries WHERE guild_id=$1 AND serial_number ILIKE $2",
            (gid, cleaned), fetch="one"
        )

        if not record:
            await interaction.followup.send(embed=error_embed("No Encontrada", f"Arma con serie **{cleaned}** no encontrada."), ephemeral=True)
            return

        await aexecute(
            "UPDATE weapon_registries SET status='confiscated', notes=$1, updated_at=NOW() WHERE id=$2",
            (f"Incautada por <@{interaction.user.id}>. Motivo: {motivo}", record["id"])
        )

        await interaction.followup.send(embed=success_embed(
            "🚨 Arma Incautada",
            f"El arma **{record['weapon_name']}** (Serie `{record['serial_number']}`) fue marcada como **INCAUTADA**.\n**Motivo:** {motivo}"
        ))


async def setup(bot):
    await bot.add_cog(Weapons(bot))
