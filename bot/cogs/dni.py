import discord
from discord import app_commands
from discord.ext import commands
import datetime
import logging
import re

from bot.db import aexecute
from bot.helpers import (
    async_get_or_create_user,
    generate_id,
    generate_unique_dni,
    check_admin_permission
)
from bot.embeds import success_embed, error_embed, info_embed

logger = logging.getLogger("bot.dni")


def _parse_age_from_birth_date(birth_str: str) -> int:
    """Safely extracts or calculates age from various date formats."""
    try:
        parts = re.findall(r"\d+", birth_str)
        if len(parts) >= 3:
            # Extract 4-digit year
            y = int(parts[0]) if len(parts[0]) == 4 else int(parts[-1])
            curr_year = datetime.datetime.utcnow().year
            if 1920 <= y <= curr_year:
                return max(16, min(100, curr_year - y))
        elif len(parts) == 1 and 16 <= int(parts[0]) <= 100:
            return int(parts[0])
    except Exception:
        pass
    return 21


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

        try:
            # Check existing active DNI
            existing = await aexecute(
                "SELECT * FROM dni_records WHERE guild_id=$1 AND discord_id=$2",
                (gid, uid), fetch="one"
            )

            # Get roblox username if linked
            user_row = await async_get_or_create_user(uid, gid, username=interaction.user.name, display_name=interaction.user.display_name)
            roblox_user = user_row.get("roblox_username")
            roblox_id = user_row.get("roblox_id")

            fname = self.full_name.value.strip()
            bdate = self.birth_date.value.strip()
            age_val = _parse_age_from_birth_date(bdate)
            gender_val = self.gender.value.strip()
            nat_val = self.nationality.value.strip()
            occ_val = self.occupation.value.strip() or "Ciudadano"

            if existing:
                dni_num = existing["dni_number"]
                await aexecute(
                    """UPDATE dni_records 
                       SET full_name=$1, birth_date=$2, age=$3, gender=$4, nationality=$5, occupation=$6, 
                           roblox_username=$7, roblox_id=$8, status='active', updated_at=NOW()
                       WHERE id=$9""",
                    (fname, bdate, age_val, gender_val, nat_val, occ_val, roblox_user, roblox_id, existing["id"])
                )
                msg_desc = "Tu Documento Nacional de Identidad ha sido actualizado correctamente."
            else:
                dni_num = await generate_unique_dni(gid)
                await aexecute(
                    """INSERT INTO dni_records 
                       (id, guild_id, discord_id, dni_number, full_name, birth_date, age, gender, nationality, occupation, roblox_username, roblox_id, status, created_at, updated_at)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,'active',NOW(),NOW())""",
                    (generate_id(), gid, uid, dni_num, fname, bdate, age_val, gender_val, nat_val, occ_val, roblox_user, roblox_id)
                )
                msg_desc = "Se ha emitido tu Documento Nacional de Identidad oficial único."

            # Update users table with DNI number
            await aexecute(
                "UPDATE users SET dni_number=$1, updated_at=NOW() WHERE guild_id=$2 AND discord_id=$3",
                (dni_num, gid, uid)
            )

            card = success_embed(
                f"🪪 DOCUMENTO NACIONAL DE IDENTIDAD — CIUDAD DE MIAMI",
                f"**Número de DNI:** `{dni_num}`\n**Estado:** 🟢 Activo / Válido\n{msg_desc}"
            )
            card.set_thumbnail(url=interaction.user.display_avatar.url)
            card.add_field(name="👤 Nombre Completo", value=fname, inline=True)
            card.add_field(name="📅 Nacimiento / Edad", value=f"{bdate} ({age_val} años)", inline=True)
            card.add_field(name="⚧ Género", value=gender_val, inline=True)
            card.add_field(name="🌎 Nacionalidad", value=nat_val, inline=True)
            card.add_field(name="💼 Ocupación", value=occ_val, inline=True)
            if roblox_user:
                card.add_field(name="🎮 Perfil de Roblox", value=f"[{roblox_user}](https://www.roblox.com/search/users?keyword={roblox_user})", inline=True)
            card.set_footer(text=f"Titular: @{interaction.user.name} • Discord ID: {interaction.user.id}")

            await interaction.followup.send(embed=card, ephemeral=True)
        except Exception as e:
            logger.error(f"[DNI] Error al crear/actualizar DNI para user {uid}: {e}", exc_info=True)
            await interaction.followup.send(
                embed=error_embed("Error al Guardar DNI", f"Ocurrió un problema técnico al registrar tu documento: `{e}`"),
                ephemeral=True
            )


class DNI(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    dni_group = app_commands.Group(name="dni", description="Sistema de Documento Nacional de Identidad (DNI)")

    @dni_group.command(name="crear", description="Crear o tramitar tu Documento Nacional de Identidad (DNI)")
    async def dni_crear(self, interaction: discord.Interaction):
        modal = CreateDNIModal()
        await interaction.response.send_modal(modal)

    @dni_group.command(name="solicitar", description="Alias: Tramitar tu Documento Nacional de Identidad (DNI)")
    async def dni_solicitar(self, interaction: discord.Interaction):
        modal = CreateDNIModal()
        await interaction.response.send_modal(modal)

    @dni_group.command(name="ver", description="Ver el DNI de un ciudadano")
    @app_commands.describe(usuario="Ciudadano a consultar (omite para ver el tuyo)")
    async def dni_ver(self, interaction: discord.Interaction, usuario: discord.Member = None):
        await interaction.response.defer()
        target = usuario or interaction.user
        gid = str(interaction.guild_id)
        uid = str(target.id)

        try:
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
            roblox_id = user_row.get("roblox_id") or record.get("roblox_id")

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
            
            bdate_val = record.get('birth_date', 'N/A')
            age_val = record.get('age')
            age_str = f" ({age_val} años)" if age_val else ""
            card.add_field(name="📅 Nacimiento / Edad", value=f"{bdate_val}{age_str}", inline=True)
            
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
        except Exception as e:
            logger.error(f"[DNI] Error al consultar DNI de {uid}: {e}", exc_info=True)
            await interaction.followup.send(
                embed=error_embed("Error al Consultar DNI", f"Ocurrió un error al cargar el registro: `{e}`"),
                ephemeral=True
            )

    @dni_group.command(name="buscar", description="Buscar a un ciudadano por su número de DNI")
    @app_commands.describe(numero_dni="Número de DNI exacto (ej: MIA-123456)")
    async def dni_buscar(self, interaction: discord.Interaction, numero_dni: str):
        await interaction.response.defer()
        gid = str(interaction.guild_id)
        cleaned = numero_dni.strip().upper()

        try:
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
            
            bdate_val = record.get('birth_date', 'N/A')
            age_val = record.get('age')
            age_str = f" ({age_val} años)" if age_val else ""
            card.add_field(name="📅 Nacimiento / Edad", value=f"{bdate_val}{age_str}", inline=True)
            
            card.add_field(name="⚧ Género", value=record.get('gender', 'N/A'), inline=True)
            card.add_field(name="🌎 Nacionalidad", value=record.get('nationality', 'N/A'), inline=True)
            card.add_field(name="💼 Ocupación", value=record.get('occupation', 'Ciudadano'), inline=True)
            if roblox_name:
                card.add_field(name="🎮 Roblox", value=roblox_name, inline=True)

            await interaction.followup.send(embed=card)
        except Exception as e:
            logger.error(f"[DNI] Error en busqueda de DNI {cleaned}: {e}", exc_info=True)
            await interaction.followup.send(
                embed=error_embed("Error en Búsqueda", f"Ocurrió un error: `{e}`"),
                ephemeral=True
            )

    @dni_group.command(name="revocar", description="Revocar o suspender el DNI de un usuario (Admin/Policía)")
    @app_commands.describe(usuario="Ciudadano a sancionar", motivo="Motivo de la revocación")
    async def dni_revocar(self, interaction: discord.Interaction, usuario: discord.Member, motivo: str):
        await interaction.response.defer()
        if not await check_admin_permission(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores autorizados"), ephemeral=True)
            return

        gid = str(interaction.guild_id)
        try:
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
        except Exception as e:
            logger.error(f"[DNI] Error al revocar DNI: {e}", exc_info=True)
            await interaction.followup.send(
                embed=error_embed("Error al Revocar DNI", f"Ocurrió un error: `{e}`"),
                ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(DNI(bot))

