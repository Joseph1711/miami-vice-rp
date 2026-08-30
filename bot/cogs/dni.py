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
from bot.cogs.roblox import fetch_roblox_user

logger = logging.getLogger("bot.dni")

MAX_CHARACTERS_PER_USER = 5


def _parse_age_from_birth_date(birth_str: str) -> int:
    """Safely extracts or calculates age from various date formats."""
    try:
        parts = re.findall(r"\d+", birth_str)
        if len(parts) >= 3:
            y = int(parts[0]) if len(parts[0]) == 4 else int(parts[-1])
            curr_year = datetime.datetime.utcnow().year
            if 1920 <= y <= curr_year:
                return max(14, min(100, curr_year - y))
        elif len(parts) == 1 and 14 <= int(parts[0]) <= 100:
            return int(parts[0])
    except Exception:
        pass
    return 21


class CreateDNIModal(discord.ui.Modal):
    def __init__(self, character_slot: int = 1, existing_dni_id: str = None):
        title = f"DNI — Personaje #{character_slot}" if character_slot > 1 else "Creación de DNI (Personaje IC)"
        super().__init__(title=title[:45])
        self.character_slot = character_slot
        self.existing_dni_id = existing_dni_id

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
            label="Nacionalidad / Origen",
            placeholder="Ej: Estadounidense / Mexicano / Español / Colombiano",
            max_length=60,
            required=True
        )
        self.occupation = discord.ui.TextInput(
            label="Ocupación o Profesión Principal",
            placeholder="Ej: Policía, Médico, Conductor, Abogado, Mecánico",
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
            # Obtener datos del usuario base
            user_row = await async_get_or_create_user(uid, gid, username=interaction.user.name, display_name=interaction.user.display_name)
            roblox_user = user_row.get("roblox_username")
            roblox_id = user_row.get("roblox_id")

            # Obtener avatar oficial de Roblox si está vinculado
            avatar_url = None
            if roblox_user:
                u_data, av_url = await fetch_roblox_user(roblox_user)
                if av_url:
                    avatar_url = av_url
                    if u_data and u_data.get("id"):
                        roblox_id = u_data.get("id")

            fname = self.full_name.value.strip().title()
            bdate = self.birth_date.value.strip()
            age_val = _parse_age_from_birth_date(bdate)
            gender_val = self.gender.value.strip().capitalize()
            nat_val = self.nationality.value.strip().title()
            occ_val = self.occupation.value.strip().title() or "Ciudadano"

            # Verificar límite de 5 personajes
            user_dnis = await aexecute(
                "SELECT * FROM dni_records WHERE guild_id=$1 AND discord_id=$2 ORDER BY created_at ASC",
                (gid, uid), fetch="all"
            ) or []

            if self.existing_dni_id:
                # Actualización de un DNI existente
                existing_dni = await aexecute("SELECT * FROM dni_records WHERE id=$1", (self.existing_dni_id,), fetch="one")
                dni_num = existing_dni["dni_number"] if existing_dni else await generate_unique_dni(gid)
                
                await aexecute(
                    """UPDATE dni_records 
                       SET full_name=$1, birth_date=$2, age=$3, gender=$4, nationality=$5, occupation=$6, 
                           roblox_username=$7, roblox_id=$8, avatar_url=$9, status='active', updated_at=NOW()
                       WHERE id=$10""",
                    (fname, bdate, age_val, gender_val, nat_val, occ_val, roblox_user, roblox_id, avatar_url, self.existing_dni_id)
                )
                msg_desc = f"Documento Nacional de Identidad actualizado con éxito para **{fname}**."
            else:
                if len(user_dnis) >= MAX_CHARACTERS_PER_USER:
                    await interaction.followup.send(
                        embed=error_embed("Límite de Personajes", f"Has alcanzado el límite máximo permitido de **{MAX_CHARACTERS_PER_USER} personajes/DNIs**. Usa `/dni mis_personajes` para gestionarlos."),
                        ephemeral=True
                    )
                    return

                dni_num = await generate_unique_dni(gid)
                await aexecute(
                    """INSERT INTO dni_records 
                       (id, guild_id, discord_id, dni_number, full_name, birth_date, age, gender, nationality, occupation, roblox_username, roblox_id, avatar_url, status, is_active, created_at, updated_at)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,'active',TRUE,NOW(),NOW())""",
                    (generate_id(), gid, uid, dni_num, fname, bdate, age_val, gender_val, nat_val, occ_val, roblox_user, roblox_id, avatar_url)
                )
                msg_desc = f"Se ha emitido un nuevo Documento Nacional de Identidad (Personaje #{len(user_dnis) + 1})."

            # Actualizar users con el DNI activo más reciente
            await aexecute(
                "UPDATE users SET dni_number=$1, updated_at=NOW() WHERE guild_id=$2 AND discord_id=$3",
                (dni_num, gid, uid)
            )

            card = success_embed(
                f"🪪 DOCUMENTO NACIONAL DE IDENTIDAD — CIUDAD DE MIAMI",
                f"**Número de DNI:** `{dni_num}`\n**Estado:** 🟢 Activo / Válido\n{msg_desc}"
            )
            if avatar_url:
                card.set_thumbnail(url=avatar_url)
            else:
                card.set_thumbnail(url=interaction.user.display_avatar.url)

            card.add_field(name="👤 Nombre Completo", value=fname, inline=True)
            card.add_field(name="📅 Nacimiento / Edad", value=f"{bdate} ({age_val} años)", inline=True)
            card.add_field(name="⚧ Género", value=gender_val, inline=True)
            card.add_field(name="🌎 Nacionalidad", value=nat_val, inline=True)
            card.add_field(name="💼 Ocupación", value=occ_val, inline=True)
            
            if roblox_user:
                r_link = f"https://www.roblox.com/users/{roblox_id}/profile" if roblox_id else f"https://www.roblox.com/search/users?keyword={roblox_user}"
                card.add_field(name="🎮 Roblox Sincronizado", value=f"[{roblox_user}]({r_link})", inline=True)
            else:
                card.add_field(name="🎮 Roblox", value="*Sin vincular (`/roblox vincular`)*", inline=True)

            card.set_footer(text=f"Personaje #{len(user_dnis) + 1} de {MAX_CHARACTERS_PER_USER} • Titular: @{interaction.user.name}")

            await interaction.followup.send(embed=card, ephemeral=True)
        except Exception as e:
            logger.error(f"[DNI] Error al crear/actualizar DNI para user {uid}: {e}", exc_info=True)
            await interaction.followup.send(
                embed=error_embed("Error al Guardar DNI", f"Ocurrió un problema técnico al registrar tu documento: `{e}`"),
                ephemeral=True
            )


class CharacterSelectView(discord.ui.View):
    """Permite seleccionar cuál de tus hasta 5 personajes deseas activar o consultar."""
    def __init__(self, characters: list, user_id: str):
        super().__init__(timeout=60)
        self.characters = characters
        self.user_id = user_id

        options = []
        for idx, char in enumerate(characters, 1):
            name = char.get("full_name") or f"Personaje #{idx}"
            dni = char.get("dni_number", "S/D")
            occ = char.get("occupation") or "Ciudadano"
            options.append(discord.SelectOption(
                label=f"#{idx}: {name[:40]}",
                description=f"DNI: {dni} • {occ}"[:100],
                value=str(char["id"]),
                emoji="🪪"
            ))

        select = discord.ui.Select(
            placeholder="Selecciona uno de tus personajes para activarlo...",
            options=options,
            min_values=1,
            max_values=1
        )
        select.callback = self.select_callback
        self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("❌ Este menú no te pertenece.", ephemeral=True)
            return

        selected_id = interaction.data["values"][0]
        selected_char = next((c for c in self.characters if str(c["id"]) == selected_id), None)
        if not selected_char:
            await interaction.response.send_message("❌ Personaje no encontrado.", ephemeral=True)
            return

        gid = str(interaction.guild_id)
        uid = str(interaction.user.id)

        # Activar en users
        await aexecute(
            "UPDATE users SET dni_number=$1, updated_at=NOW() WHERE guild_id=$2 AND discord_id=$3",
            (selected_char["dni_number"], gid, uid)
        )

        card = success_embed(
            "Personaje Activo Seleccionado",
            f"Ahora estás usando a **{selected_char.get('full_name', 'Personaje')}** (DNI: `{selected_char['dni_number']}`) como tu identidad activa principal."
        )
        if selected_char.get("avatar_url"):
            card.set_thumbnail(url=selected_char["avatar_url"])
        else:
            card.set_thumbnail(url=interaction.user.display_avatar.url)

        card.add_field(name="👤 Nombre", value=selected_char.get("full_name", "N/A"), inline=True)
        card.add_field(name="🎂 Edad", value=f"{selected_char.get('age', 'N/A')} años", inline=True)
        card.add_field(name="💼 Ocupación", value=selected_char.get("occupation", "Ciudadano"), inline=True)
        
        await interaction.response.edit_message(embed=card, view=None)


class DNI(commands.Cog, name="DNI"):
    def __init__(self, bot):
        self.bot = bot

    dni_group = app_commands.Group(name="dni", description="Sistema de Documento Nacional de Identidad y Multipersoanjes")

    @dni_group.command(name="crear", description="Crear o tramitar un Documento Nacional de Identidad (hasta 5 personajes)")
    async def dni_crear(self, interaction: discord.Interaction):
        gid = str(interaction.guild_id)
        uid = str(interaction.user.id)

        user_dnis = await aexecute(
            "SELECT * FROM dni_records WHERE guild_id=$1 AND discord_id=$2 ORDER BY created_at ASC",
            (gid, uid), fetch="all"
        ) or []

        if len(user_dnis) >= MAX_CHARACTERS_PER_USER:
            await interaction.response.send_message(
                embed=error_embed("Límite de Personajes", f"Ya tienes **{len(user_dnis)}/{MAX_CHARACTERS_PER_USER} personajes**. Usa `/dni mis_personajes` para cambiarlos o gestionarlos."),
                ephemeral=True
            )
            return

        slot = len(user_dnis) + 1
        modal = CreateDNIModal(character_slot=slot)
        await interaction.response.send_modal(modal)

    @dni_group.command(name="solicitar", description="Alias: Tramitar un nuevo personaje (DNI)")
    async def dni_solicitar(self, interaction: discord.Interaction):
        await self.dni_crear(interaction)

    @dni_group.command(name="mis_personajes", description="Ver y alternar entre todos tus personajes registrados (hasta 5)")
    async def mis_personajes(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = str(interaction.guild_id)
        uid = str(interaction.user.id)

        user_dnis = await aexecute(
            "SELECT * FROM dni_records WHERE guild_id=$1 AND discord_id=$2 ORDER BY created_at ASC",
            (gid, uid), fetch="all"
        ) or []

        if not user_dnis:
            await interaction.followup.send(
                embed=error_embed("Sin Personajes", "No tienes ningún DNI tramitado aún. Usa `/dni crear` para dar vida a tu primer personaje."),
                ephemeral=True
            )
            return

        user_row = await aexecute("SELECT dni_number FROM users WHERE guild_id=$1 AND discord_id=$2", (gid, uid), fetch="one") or {}
        active_dni = user_row.get("dni_number")

        e = info_embed(
            f"🪪 Tus Personajes Registrados ({len(user_dnis)}/{MAX_CHARACTERS_PER_USER})",
            "A continuación puedes ver tus identidades registradas en Miami Vice RP. Selecciona uno en el menú inferior para activarlo como tu personaje principal."
        )

        for idx, char in enumerate(user_dnis, 1):
            is_active = (char.get("dni_number") == active_dni)
            active_badge = " [🟢 ACTIVO]" if is_active else ""
            name = char.get("full_name") or f"Personaje #{idx}"
            dni = char.get("dni_number", "S/D")
            age = char.get("age", "N/A")
            occ = char.get("occupation", "Ciudadano")
            e.add_field(
                name=f"#{idx} {name}{active_badge}",
                value=f"• **DNI:** `{dni}`\n• **Edad:** {age} años\n• **Ocupación:** {occ}",
                inline=False
            )

        view = CharacterSelectView(user_dnis, uid)
        await interaction.followup.send(embed=e, view=view, ephemeral=True)

    @dni_group.command(name="ver", description="Ver el DNI de un ciudadano")
    @app_commands.describe(usuario="Ciudadano a consultar (omite para ver tu personaje activo)", numero_dni="Consultar un DNI específico")
    async def dni_ver(self, interaction: discord.Interaction, usuario: discord.Member = None, numero_dni: str = None):
        await interaction.response.defer()
        target = usuario or interaction.user
        gid = str(interaction.guild_id)
        uid = str(target.id)

        try:
            record = None
            if numero_dni:
                record = await aexecute(
                    "SELECT * FROM dni_records WHERE guild_id=$1 AND dni_number ILIKE $2",
                    (gid, numero_dni.strip().upper()), fetch="one"
                )
            else:
                user_row = await aexecute("SELECT dni_number FROM users WHERE guild_id=$1 AND discord_id=$2", (gid, uid), fetch="one")
                active_dni = user_row.get("dni_number") if user_row else None
                if active_dni:
                    record = await aexecute("SELECT * FROM dni_records WHERE guild_id=$1 AND dni_number=$2", (gid, active_dni), fetch="one")
                if not record:
                    record = await aexecute(
                        "SELECT * FROM dni_records WHERE guild_id=$1 AND discord_id=$2 ORDER BY created_at DESC LIMIT 1",
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

            # Usar foto de perfil de Roblox si existe
            avatar = record.get("avatar_url")
            if not avatar and record.get("roblox_username"):
                _, av_url = await fetch_roblox_user(record["roblox_username"])
                if av_url:
                    avatar = av_url
            
            if avatar:
                card.set_thumbnail(url=avatar)
            else:
                card.set_thumbnail(url=target.display_avatar.url)

            card.add_field(name="👤 Nombre Completo", value=f"**{record.get('full_name', 'N/A')}**", inline=True)
            
            bdate_val = record.get('birth_date', 'N/A')
            age_val = record.get('age')
            age_str = f" ({age_val} años)" if age_val else ""
            card.add_field(name="📅 Nacimiento / Edad", value=f"{bdate_val}{age_str}", inline=True)
            
            card.add_field(name="⚧ Género", value=record.get('gender', 'N/A'), inline=True)
            card.add_field(name="🌎 Nacionalidad", value=record.get('nationality', 'N/A'), inline=True)
            card.add_field(name="💼 Ocupación", value=record.get('occupation', 'Ciudadano'), inline=True)

            roblox_name = record.get("roblox_username")
            roblox_id = record.get("roblox_id")
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
        await self.dni_ver(interaction, numero_dni=numero_dni)

    @dni_group.command(name="revocar", description="Revocar o suspender el DNI de un usuario (Admin/Policía)")
    @app_commands.describe(usuario="Ciudadano a sancionar", motivo="Motivo de la revocación")
    async def dni_revocar(self, interaction: discord.Interaction, usuario: discord.Member, motivo: str):
        await interaction.response.defer()
        if not await check_admin_permission(interaction):
            await interaction.followup.send(embed=error_embed("Sin permisos", "Solo administradores o policía autorizada"), ephemeral=True)
            return

        gid = str(interaction.guild_id)
        try:
            record = await aexecute(
                "SELECT * FROM dni_records WHERE guild_id=$1 AND discord_id=$2 ORDER BY created_at DESC LIMIT 1",
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
