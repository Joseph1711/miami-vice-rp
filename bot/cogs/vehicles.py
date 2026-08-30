import discord
from discord import app_commands
from discord.ext import commands
import datetime
import logging

from bot.db import aexecute
from bot.helpers import (
    async_get_or_create_user,
    generate_id,
    generate_unique_vehicle_plate,
    generate_unique_vin,
    check_admin_permission
)
from bot.embeds import success_embed, error_embed, info_embed, COLOR_PRIMARY

logger = logging.getLogger("bot.vehicles")

VEHICLE_TYPE_META = {
    "auto": {"emoji": "🚗", "label": "Automóvil / Deportivo / Sedán", "prefix": "MIA"},
    "suv": {"emoji": "🚙", "label": "Camioneta / SUV / Pick-Up 4x4", "prefix": "MIA"},
    "moto": {"emoji": "🏍️", "label": "Motocicleta / Scooter", "prefix": "MOT"},
    "atv": {"emoji": "🚜", "label": "ATV / Cuatrimoto / Buggy / Off-Road", "prefix": "ATV"},
    "trailer": {"emoji": "🚛", "label": "Remolque / Trailer / Plataforma", "prefix": "TRL"},
    "lancha": {"emoji": "🚤", "label": "Embarcación / Lancha / Jet Ski", "prefix": "SEA"},
    "camion": {"emoji": "🚚", "label": "Camión de Carga / Comercial", "prefix": "TRK"},
    "otro": {"emoji": "🏎️", "label": "Vehículo Especial / Otro", "prefix": "MIA"}
}

REGISTRATION_FEE = 500


class RegisterVehicleModal(discord.ui.Modal):
    def __init__(self, vehicle_type: str = "auto"):
        v_meta = VEHICLE_TYPE_META.get(vehicle_type, VEHICLE_TYPE_META["auto"])
        super().__init__(title=f"Registro Oficial: {v_meta['label'][:35]}")
        self.vehicle_type = vehicle_type

        self.brand_model = discord.ui.TextInput(
            label="Marca y Modelo del Vehículo/Trailer/ATV",
            placeholder="Ej: Yamaha Raptor 700R / Trailer Doble Eje / Ford F-150",
            max_length=80,
            required=True
        )

        self.color = discord.ui.TextInput(
            label="Color Predominante / Acabado",
            placeholder="Ej: Negro Mate / Rojo Fuego / Gris Nardo / Camuflado",
            max_length=40,
            required=True
        )

        self.notes = discord.ui.TextInput(
            label="Detalles o Equipamiento Especial (Opcional)",
            placeholder="Ej: Suspensión elevada, winche 4x4, luces LED, enganche para remolque...",
            style=discord.TextStyle.paragraph,
            max_length=400,
            required=False
        )

        self.add_item(self.brand_model)
        self.add_item(self.color)
        self.add_item(self.notes)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = str(interaction.guild_id)
        uid = str(interaction.user.id)

        try:
            # 1. Comprobar DNI del ciudadano
            dni = await aexecute(
                "SELECT * FROM dni_records WHERE guild_id=$1 AND discord_id=$2 AND status='active'",
                (gid, uid), fetch="one"
            )
            if not dni:
                await interaction.followup.send(embed=error_embed(
                    "Requiere DNI Activo",
                    "Para matricular legalmente un vehículo, remolque o ATV debes poseer un DNI activo en la ciudad. Tramítalo con `/dni crear`."
                ), ephemeral=True)
                return

            # 2. Comprobar balance económico para arancel de matriculación
            user_data = await async_get_or_create_user(uid, gid, interaction.user.name, interaction.user.display_name)
            cash = float(user_data.get("cash", 0))
            bank = float(user_data.get("bank", 0))

            if cash < REGISTRATION_FEE and bank < REGISTRATION_FEE:
                await interaction.followup.send(embed=error_embed(
                    "Fondos Insuficientes",
                    f"La tasa municipal de registro y expedición de placas cuesta **${REGISTRATION_FEE:,.2f}**.\n"
                    f"Tienes `${cash:,.2f}` en efectivo y `${bank:,.2f}` en banco."
                ), ephemeral=True)
                return

            # Cobrar tasa
            if cash >= REGISTRATION_FEE:
                await aexecute("UPDATE users SET cash = cash - $1, updated_at=NOW() WHERE discord_id=$2 AND guild_id=$3",
                               (REGISTRATION_FEE, uid, gid))
            else:
                await aexecute("UPDATE users SET bank = bank - $1, updated_at=NOW() WHERE discord_id=$2 AND guild_id=$3",
                               (REGISTRATION_FEE, uid, gid))

            # 3. Generar Placa y VIN únicos
            plate = await generate_unique_vehicle_plate(gid, self.vehicle_type)
            vin = await generate_unique_vin(gid, self.vehicle_type)
            reg_id = generate_id()

            b_model = self.brand_model.value.strip()
            v_color = self.color.value.strip()
            v_notes = self.notes.value.strip() if self.notes.value else None

            # 4. Guardar registro en base de datos
            await aexecute(
                """INSERT INTO vehicle_registries 
                   (id, guild_id, discord_id, dni_id, dni_number, vehicle_type, brand_model, color, plate, vin_number, status, registration_fee, insurance_status, notes, registered_at, created_at, updated_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, 'active', $11, 'basic', $12, NOW(), NOW(), NOW())""",
                (reg_id, gid, uid, dni.get("id"), dni.get("dni_number"), self.vehicle_type, b_model, v_color, plate, vin, REGISTRATION_FEE, v_notes)
            )

            # 5. Generar Tarjeta de Circulación oficial
            type_info = VEHICLE_TYPE_META.get(self.vehicle_type, VEHICLE_TYPE_META["auto"])
            citizen_name = f"{dni.get('first_name', '')} {dni.get('last_name', '')}".strip() or interaction.user.display_name
            roblox_tag = dni.get("roblox_username") or user_data.get("roblox_username")

            embed = discord.Embed(
                title=f"{type_info['emoji']} Título de Propiedad y Tarjeta de Circulación",
                description=(
                    f"El Departamento de Vehículos y Tránsito de **Miami Vice** ha matriculado legalmente esta unidad.\n"
                    f"La placa oficial y el número de chasis han sido emitidos."
                ),
                color=COLOR_PRIMARY
            )

            embed.add_field(name="🏷️ Placa Oficial", value=f"```fix\n{plate}\n```", inline=True)
            embed.add_field(name="🔢 Número de Chasis (VIN)", value=f"`{vin}`", inline=True)
            embed.add_field(name="🚦 Tipo de Unidad", value=f"{type_info['emoji']} {type_info['label']}", inline=True)

            embed.add_field(name="🚘 Marca y Modelo", value=f"**{b_model}**", inline=True)
            embed.add_field(name="🎨 Color / Acabado", value=f"{v_color}", inline=True)
            embed.add_field(name="🛡️ Seguro Obligatorio", value="🟢 Cobertura Básica Activa", inline=True)

            owner_text = f"{interaction.user.mention} (`{citizen_name}`)\n🪪 **DNI:** `{dni.get('dni_number', 'N/A')}`"
            if roblox_tag:
                owner_text += f"\n🎮 **Roblox:** `{roblox_tag}`"

            embed.add_field(name="👤 Propietario Registrado", value=owner_text, inline=False)

            if v_notes:
                embed.add_field(name="📝 Equipamiento / Notas", value=f"*{v_notes}*", inline=False)

            embed.set_footer(text=f"Miami Vice DMV • Tasa abonada: ${REGISTRATION_FEE:,.2f} • ID: {reg_id[:8]}")
            embed.timestamp = discord.utils.utcnow()

            await interaction.followup.send(embed=embed, ephemeral=False)

        except Exception as e:
            logger.error(f"[Vehicles] Error al registrar vehículo: {e}", exc_info=True)
            await interaction.followup.send(embed=error_embed("Error en Registro", f"Ocurrió un error al procesar la matrícula: `{e}`"), ephemeral=True)


class Vehicles(commands.Cog):
    """Sistema de Registro Vehicular, Remolques y ATVs (Cuatrimotos) de Miami Vice RP."""

    vehicle_group = app_commands.Group(
        name="vehiculo",
        description="Sistema oficial de registro y control vehicular, trailers y ATVs de Miami"
    )

    def __init__(self, bot):
        self.bot = bot

    # ==========================================
    # COMANDO 1: /vehiculo registrar
    # ==========================================
    @vehicle_group.command(name="registrar", description="Registra y matricula un automóvil, trailer, ATV o cuatrimoto a tu nombre")
    @app_commands.describe(
        tipo="Categoría del vehículo a matricular",
        marca_modelo="Marca y modelo específico (opcional, abre modal si se omite)",
        color="Color del vehículo (opcional)",
        detalles="Detalles o equipamiento adicional (opcional)"
    )
    @app_commands.choices(tipo=[
        app_commands.Choice(name="🚗 Automóvil / Sedán / Deportivo", value="auto"),
        app_commands.Choice(name="🚙 Camioneta / SUV / Pick-Up 4x4", value="suv"),
        app_commands.Choice(name="🏍️ Motocicleta / Scooter", value="moto"),
        app_commands.Choice(name="🚜 ATV / Cuatrimoto / Buggy / Off-Road", value="atv"),
        app_commands.Choice(name="🚛 Remolque / Trailer / Plataforma", value="trailer"),
        app_commands.Choice(name="🚤 Embarcación / Lancha / Moto de Agua", value="lancha"),
        app_commands.Choice(name="🚚 Camión de Carga / Comercial", value="camion"),
        app_commands.Choice(name="🏎️ Vehículo Especial / Otro", value="otro")
    ])
    async def vehiculo_registrar(
        self,
        interaction: discord.Interaction,
        tipo: str,
        marca_modelo: str = None,
        color: str = None,
        detalles: str = None
    ):
        # Si faltan campos, abrir Modal interactivo
        if not marca_modelo or not color:
            modal = RegisterVehicleModal(vehicle_type=tipo)
            await interaction.response.send_modal(modal)
            return

        await interaction.response.defer()
        gid = str(interaction.guild_id)
        uid = str(interaction.user.id)

        try:
            # 1. Comprobar DNI
            dni = await aexecute(
                "SELECT * FROM dni_records WHERE guild_id=$1 AND discord_id=$2 AND status='active'",
                (gid, uid), fetch="one"
            )
            if not dni:
                await interaction.followup.send(embed=error_embed(
                    "Requiere DNI Activo",
                    "Para matricular legalmente un vehículo, remolque o ATV debes poseer un DNI activo en la ciudad. Tramítalo con `/dni crear`."
                ), ephemeral=True)
                return

            # 2. Comprobar fondos
            user_data = await async_get_or_create_user(uid, gid, interaction.user.name, interaction.user.display_name)
            cash = float(user_data.get("cash", 0))
            bank = float(user_data.get("bank", 0))

            if cash < REGISTRATION_FEE and bank < REGISTRATION_FEE:
                await interaction.followup.send(embed=error_embed(
                    "Fondos Insuficientes",
                    f"La tasa municipal de registro vehicular cuesta **${REGISTRATION_FEE:,.2f}**.\n"
                    f"Tienes `${cash:,.2f}` en efectivo y `${bank:,.2f}` en banco."
                ), ephemeral=True)
                return

            if cash >= REGISTRATION_FEE:
                await aexecute("UPDATE users SET cash = cash - $1, updated_at=NOW() WHERE discord_id=$2 AND guild_id=$3",
                               (REGISTRATION_FEE, uid, gid))
            else:
                await aexecute("UPDATE users SET bank = bank - $1, updated_at=NOW() WHERE discord_id=$2 AND guild_id=$3",
                               (REGISTRATION_FEE, uid, gid))

            # 3. Generar Placa y VIN
            plate = await generate_unique_vehicle_plate(gid, tipo)
            vin = await generate_unique_vin(gid, tipo)
            reg_id = generate_id()

            b_model = marca_modelo.strip()
            v_color = color.strip()
            v_notes = detalles.strip() if detalles else None

            # 4. Inserción en DB
            await aexecute(
                """INSERT INTO vehicle_registries 
                   (id, guild_id, discord_id, dni_id, dni_number, vehicle_type, brand_model, color, plate, vin_number, status, registration_fee, insurance_status, notes, registered_at, created_at, updated_at)
                   VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, 'active', $11, 'basic', $12, NOW(), NOW(), NOW())""",
                (reg_id, gid, uid, dni.get("id"), dni.get("dni_number"), tipo, b_model, v_color, plate, vin, REGISTRATION_FEE, v_notes)
            )

            # 5. Embed
            type_info = VEHICLE_TYPE_META.get(tipo, VEHICLE_TYPE_META["auto"])
            citizen_name = f"{dni.get('first_name', '')} {dni.get('last_name', '')}".strip() or interaction.user.display_name
            roblox_tag = dni.get("roblox_username") or user_data.get("roblox_username")

            embed = discord.Embed(
                title=f"{type_info['emoji']} Título de Propiedad y Tarjeta de Circulación",
                description=(
                    f"El Departamento de Tránsito y Transporte de **Miami Vice** ha registrado oficialmente esta unidad.\n"
                    f"La placa de circulación y el número de chasis han sido emitidos."
                ),
                color=COLOR_PRIMARY
            )

            embed.add_field(name="🏷️ Placa Oficial", value=f"```fix\n{plate}\n```", inline=True)
            embed.add_field(name="🔢 Número de Chasis (VIN)", value=f"`{vin}`", inline=True)
            embed.add_field(name="🚦 Tipo de Unidad", value=f"{type_info['emoji']} {type_info['label']}", inline=True)

            embed.add_field(name="🚘 Marca y Modelo", value=f"**{b_model}**", inline=True)
            embed.add_field(name="🎨 Color / Acabado", value=f"{v_color}", inline=True)
            embed.add_field(name="🛡️ Seguro Obligatorio", value="🟢 Cobertura Básica Activa", inline=True)

            owner_text = f"{interaction.user.mention} (`{citizen_name}`)\n🪪 **DNI:** `{dni.get('dni_number', 'N/A')}`"
            if roblox_tag:
                owner_text += f"\n🎮 **Roblox:** `{roblox_tag}`"

            embed.add_field(name="👤 Propietario Registrado", value=owner_text, inline=False)

            if v_notes:
                embed.add_field(name="📝 Equipamiento / Notas", value=f"*{v_notes}*", inline=False)

            embed.set_footer(text=f"Miami Vice DMV • Tasa abonada: ${REGISTRATION_FEE:,.2f} • ID: {reg_id[:8]}")
            embed.timestamp = discord.utils.utcnow()

            await interaction.followup.send(embed=embed)

        except Exception as e:
            logger.error(f"[Vehicles] Error al registrar: {e}", exc_info=True)
            await interaction.followup.send(embed=error_embed("Error en Registro", f"Ocurrió un error: `{e}`"), ephemeral=True)

    # ==========================================
    # COMANDO 2: /vehiculo mis_vehiculos
    # ==========================================
    @vehicle_group.command(name="mis_vehiculos", description="Consulta la lista de vehículos, remolques y ATVs registrados a tu nombre")
    @app_commands.describe(tipo="Filtrar por categoría de vehículo")
    @app_commands.choices(tipo=[
        app_commands.Choice(name="Todos los tipos", value="todos"),
        app_commands.Choice(name="🚗 Automóviles / SUVs", value="autos_suvs"),
        app_commands.Choice(name="🚜 ATVs / Cuatrimotos", value="atv"),
        app_commands.Choice(name="🚛 Remolques / Trailers", value="trailer"),
        app_commands.Choice(name="🏍️ Motocicletas", value="moto"),
        app_commands.Choice(name="🚤 Embarcaciones", value="lancha")
    ])
    async def vehiculo_mis_vehiculos(self, interaction: discord.Interaction, tipo: str = "todos"):
        await interaction.response.defer(ephemeral=True)
        gid = str(interaction.guild_id)
        uid = str(interaction.user.id)

        query = "SELECT * FROM vehicle_registries WHERE guild_id=$1 AND discord_id=$2"
        params = [gid, uid]

        if tipo == "autos_suvs":
            query += " AND vehicle_type IN ('auto', 'suv')"
        elif tipo in ("atv", "trailer", "moto", "lancha"):
            query += " AND vehicle_type=$3"
            params.append(tipo)

        query += " ORDER BY registered_at DESC"

        rows = await aexecute(query, tuple(params), fetch="all") or []

        if not rows:
            await interaction.followup.send(embed=info_embed(
                "Garage Vacío",
                "No tienes ningún vehículo, trailer o ATV registrado en el sistema.\n"
                "Para matricular uno nuevo utiliza `/vehiculo registrar`."
            ), ephemeral=True)
            return

        embed = info_embed(
            f"Garage & Parque Automotor de {interaction.user.display_name}",
            f"Tienes un total de **{len(rows)}** unidades matriculadas en el Departamento de Tránsito:"
        )

        status_emojis = {
            "active": "🟢 En Circulación",
            "impounded": "🔴 Incautado / Corralón",
            "stolen": "🚨 Reportado Robado",
            "sold": "⚪ Transferido",
            "scrapped": "⚫ Dado de Baja"
        }

        for row in rows:
            v_type = row.get("vehicle_type", "auto")
            t_meta = VEHICLE_TYPE_META.get(v_type, VEHICLE_TYPE_META["auto"])
            plate = row.get("plate", "SIN-PLACA")
            vin = row.get("vin_number", "SIN-VIN")
            model = row.get("brand_model", "Desconocido")
            color = row.get("color", "N/A")
            status = row.get("status", "active")
            status_text = status_emojis.get(status, "🟢 Activo")

            field_val = (
                f"**Modelo:** {model} ({color})\n"
                f"**VIN:** `{vin}`\n"
                f"**Estado:** {status_text}"
            )
            if status == "impounded" and row.get("impound_fine"):
                field_val += f" (Multa: `${float(row['impound_fine']):,.2f}`)"

            embed.add_field(
                name=f"{t_meta['emoji']} Placa: {plate} [{t_meta['label'].split('/')[0].strip()}]",
                value=field_val,
                inline=False
            )

        embed.set_footer(text="Miami Vice RP • Usa /vehiculo ver [placa] para más información")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ==========================================
    # COMANDO 3: /vehiculo ver
    # ==========================================
    @vehicle_group.command(name="ver", description="Consulta la tarjeta de circulación completa de un vehículo por su placa o VIN")
    @app_commands.describe(placa_o_vin="Número de placa oficial (ej: MIA-4829, ATV-1092, TRL-8402) o VIN")
    async def vehiculo_ver(self, interaction: discord.Interaction, placa_o_vin: str):
        await interaction.response.defer()
        gid = str(interaction.guild_id)
        search_term = placa_o_vin.strip().upper()

        row = await aexecute(
            """SELECT v.*, u.display_name, u.roblox_username, d.first_name, d.last_name, d.dni_number as citizen_dni
               FROM vehicle_registries v
               LEFT JOIN users u ON v.discord_id = u.discord_id AND v.guild_id = u.guild_id
               LEFT JOIN dni_records d ON v.dni_id = d.id
               WHERE v.guild_id=$1 AND (UPPER(v.plate)=$2 OR UPPER(v.vin_number)=$2)""",
            (gid, search_term), fetch="one"
        )

        if not row:
            await interaction.followup.send(embed=error_embed(
                "Unidad No Encontrada",
                f"No se encontró ningún vehículo, remolque o ATV registrado con la placa o VIN `{search_term}`.\n"
                f"Verifica que el número esté bien escrito."
            ), ephemeral=True)
            return

        v_type = row.get("vehicle_type", "auto")
        t_meta = VEHICLE_TYPE_META.get(v_type, VEHICLE_TYPE_META["auto"])
        plate = row.get("plate")
        vin = row.get("vin_number")
        model = row.get("brand_model")
        color = row.get("color")
        status = row.get("status", "active")
        notes = row.get("notes")

        status_text = {
            "active": "🟢 Activo / Habilitado para Circular",
            "impounded": "🔴 Incautado en Depósito Municipal",
            "stolen": "🚨 REPORTADO COMO ROBADO",
            "sold": "⚪ Transferido / Cambio de Titular",
            "scrapped": "⚫ Dado de Baja / Fuera de Servicio"
        }.get(status, "🟢 Activo")

        embed = discord.Embed(
            title=f"{t_meta['emoji']} Registro Vehicular Oficial de Miami",
            description=f"Expediente de matriculación vehicular para la unidad **{plate}**.",
            color=COLOR_PRIMARY
        )

        embed.add_field(name="🏷️ Placa de Circulación", value=f"```fix\n{plate}\n```", inline=True)
        embed.add_field(name="🔢 Número de Chasis (VIN)", value=f"`{vin}`", inline=True)
        embed.add_field(name="🚦 Tipo de Unidad", value=f"{t_meta['emoji']} {t_meta['label']}", inline=True)

        embed.add_field(name="🚘 Marca y Modelo", value=f"**{model}**", inline=True)
        embed.add_field(name="🎨 Color Registrado", value=f"{color}", inline=True)
        embed.add_field(name="📋 Estado Legal", value=f"**{status_text}**", inline=True)

        owner_id = row.get("discord_id")
        owner_name = f"{row.get('first_name', '')} {row.get('last_name', '')}".strip() or row.get("display_name") or "Ciudadano"
        dni_num = row.get("dni_number") or row.get("citizen_dni") or "N/A"
        roblox_tag = row.get("roblox_username")

        owner_str = f"<@{owner_id}>\n👤 **Nombre IC:** {owner_name}\n🪪 **DNI:** `{dni_num}`"
        if roblox_tag:
            owner_str += f"\n🎮 **Roblox:** `{roblox_tag}`"

        embed.add_field(name="👤 Titular Registrado", value=owner_str, inline=False)

        if status == "impounded":
            imp_reason = row.get("impound_reason", "Infracción de tránsito / delito")
            imp_fine = float(row.get("impound_fine", 0))
            embed.add_field(
                name="⚠️ Datos de Incautación",
                value=f"**Motivo:** {imp_reason}\n**Multa de liberación:** `${imp_fine:,.2f}`\n*Usa `/vehiculo liberar placa:{plate}` para pagar y retirar del corralón.*",
                inline=False
            )

        if notes:
            embed.add_field(name="📝 Equipamiento & Modificaciones", value=f"*{notes}*", inline=False)

        reg_at = row.get("registered_at")
        reg_str = str(reg_at)[:10] if reg_at else "Reciente"
        embed.set_footer(text=f"Departamento de Vehículos Motorizados • Fecha de Registro: {reg_str}")
        embed.timestamp = discord.utils.utcnow()

        await interaction.followup.send(embed=embed)

    # ==========================================
    # COMANDO 4: /vehiculo buscar
    # ==========================================
    @vehicle_group.command(name="buscar", description="Busca el registro de vehículos matriculados por ciudadano")
    @app_commands.describe(usuario="Ciudadano a inspeccionar en el registro vehicular")
    async def vehiculo_buscar(self, interaction: discord.Interaction, usuario: discord.Member):
        await interaction.response.defer()
        gid = str(interaction.guild_id)
        uid = str(usuario.id)

        rows = await aexecute(
            "SELECT * FROM vehicle_registries WHERE guild_id=$1 AND discord_id=$2 ORDER BY registered_at DESC",
            (gid, uid), fetch="all"
        ) or []

        if not rows:
            await interaction.followup.send(embed=info_embed(
                "Sin Registros Vehiculares",
                f"El ciudadano {usuario.mention} no tiene ningún vehículo, remolque ni ATV registrado a su nombre."
            ), ephemeral=True)
            return

        embed = info_embed(
            f"Parque Automotor Registrado de {usuario.display_name}",
            f"Expediente del DMV con **{len(rows)}** unidades a nombre del titular:"
        )

        for row in rows:
            v_type = row.get("vehicle_type", "auto")
            t_meta = VEHICLE_TYPE_META.get(v_type, VEHICLE_TYPE_META["auto"])
            plate = row.get("plate")
            model = row.get("brand_model")
            color = row.get("color")
            status = row.get("status", "active")
            status_tag = "🟢 Activo" if status == "active" else f"🔴 {status.upper()}"

            embed.add_field(
                name=f"{t_meta['emoji']} Placa: `{plate}` — {model}",
                value=f"**Color:** {color} | **Estado:** {status_tag} | **VIN:** `{row.get('vin_number')}`",
                inline=False
            )

        embed.set_footer(text="Miami Vice DMV • Consulta Oficial")
        await interaction.followup.send(embed=embed)

    # ==========================================
    # COMANDO 5: /vehiculo transferir
    # ==========================================
    @vehicle_group.command(name="transferir", description="Transfiere legalmente la titularidad de un vehículo o trailer a otro ciudadano")
    @app_commands.describe(
        placa="Placa del vehículo a transferir",
        nuevo_dueno="Ciudadano que recibirá la titularidad",
        precio="Monto en dinero acordado por la venta/traspaso (0 si es traspaso gratuito)"
    )
    async def vehiculo_transferir(
        self,
        interaction: discord.Interaction,
        placa: str,
        nuevo_dueno: discord.Member,
        precio: float = 0.0
    ):
        await interaction.response.defer()
        gid = str(interaction.guild_id)
        seller_id = str(interaction.user.id)
        buyer_id = str(nuevo_dueno.id)
        plate_search = placa.strip().upper()

        if seller_id == buyer_id:
            await interaction.followup.send(embed=error_embed("Error", "No puedes transferirte un vehículo a ti mismo."), ephemeral=True)
            return

        # 1. Comprobar que el vendedor es el dueño legítimo
        veh = await aexecute(
            "SELECT * FROM vehicle_registries WHERE guild_id=$1 AND UPPER(plate)=$2 AND discord_id=$3",
            (gid, plate_search, seller_id), fetch="one"
        )
        if not veh:
            await interaction.followup.send(embed=error_embed(
                "Operación No Autorizada",
                f"No posees ningún vehículo matriculado con la placa `{plate_search}`."
            ), ephemeral=True)
            return

        if veh.get("status") == "impounded":
            await interaction.followup.send(embed=error_embed(
                "Vehículo Incautado",
                "No puedes transferir un vehículo que se encuentra incautado en el corralón. Debes liberarlo primero."
            ), ephemeral=True)
            return

        # 2. Comprobar DNI del comprador
        buyer_dni = await aexecute(
            "SELECT * FROM dni_records WHERE guild_id=$1 AND discord_id=$2 AND status='active'",
            (gid, buyer_id), fetch="one"
        )
        if not buyer_dni:
            await interaction.followup.send(embed=error_embed(
                "Comprador Sin DNI",
                f"{nuevo_dueno.mention} no posee un DNI activo. Requiere tramitarlo con `/dni crear` para ser titular de vehículos."
            ), ephemeral=True)
            return

        # 3. Comprobar fondos si hay precio
        if precio > 0:
            buyer_user = await async_get_or_create_user(buyer_id, gid, nuevo_dueno.name, nuevo_dueno.display_name)
            buyer_cash = float(buyer_user.get("cash", 0))
            buyer_bank = float(buyer_user.get("bank", 0))

            if buyer_cash < precio and buyer_bank < precio:
                await interaction.followup.send(embed=error_embed(
                    "Fondos Insuficientes",
                    f"{nuevo_dueno.mention} no dispone de `${precio:,.2f}` para completar la transferencia."
                ), ephemeral=True)
                return

            # Procesar pago
            if buyer_cash >= precio:
                await aexecute("UPDATE users SET cash = cash - $1 WHERE discord_id=$2 AND guild_id=$3", (precio, buyer_id, gid))
            else:
                await aexecute("UPDATE users SET bank = bank - $1 WHERE discord_id=$2 AND guild_id=$3", (precio, buyer_id, gid))

            # Dar dinero al vendedor
            await aexecute("UPDATE users SET bank = bank + $1 WHERE discord_id=$2 AND guild_id=$3", (precio, seller_id, gid))

        # 4. Actualizar titularidad en DB
        await aexecute(
            """UPDATE vehicle_registries 
               SET discord_id=$1, dni_id=$2, dni_number=$3, updated_at=NOW()
               WHERE id=$4""",
            (buyer_id, buyer_dni.get("id"), buyer_dni.get("dni_number"), veh["id"])
        )

        v_type = veh.get("vehicle_type", "auto")
        t_meta = VEHICLE_TYPE_META.get(v_type, VEHICLE_TYPE_META["auto"])

        embed = success_embed(
            "Transferencia Vehicular Completada",
            f"El título de propiedad del vehículo **{veh.get('brand_model')}** con placa `{veh.get('plate')}` ha sido transferido exitosamente.\n\n"
            f"📤 **Antiguo Titular:** {interaction.user.mention}\n"
            f"📥 **Nuevo Titular:** {nuevo_dueno.mention}\n"
            f"💵 **Importe de Transferencia:** `${precio:,.2f}`\n"
            f"🪪 **Nuevo DNI Registrado:** `{buyer_dni.get('dni_number')}`"
        )
        embed.set_footer(text="Miami Vice DMV • Registro Notarial de Traspaso")

        await interaction.followup.send(embed=embed)

    # ==========================================
    # COMANDO 6: /vehiculo reportar
    # ==========================================
    @vehicle_group.command(name="reportar", description="Reporta un vehículo como robado o como recuperado")
    @app_commands.describe(
        placa="Placa del vehículo a reportar",
        estado="Estado del reporte ante las autoridades"
    )
    @app_commands.choices(estado=[
        app_commands.Choice(name="🚨 Reportar como ROBADO", value="stolen"),
        app_commands.Choice(name="🟢 Marcar como RECUPERADO / Seguro", value="active")
    ])
    async def vehiculo_reportar(self, interaction: discord.Interaction, placa: str, estado: str):
        await interaction.response.defer(ephemeral=True)
        gid = str(interaction.guild_id)
        uid = str(interaction.user.id)
        plate_search = placa.strip().upper()

        veh = await aexecute(
            "SELECT * FROM vehicle_registries WHERE guild_id=$1 AND UPPER(plate)=$2 AND discord_id=$3",
            (gid, plate_search, uid), fetch="one"
        )
        if not veh:
            await interaction.followup.send(embed=error_embed(
                "Vehículo No Encontrado",
                f"No posees ningún vehículo registrado con la placa `{plate_search}`."
            ), ephemeral=True)
            return

        if veh.get("status") == "impounded":
            await interaction.followup.send(embed=error_embed(
                "Vehículo en Depósito",
                "El vehículo está incautado por las autoridades. No puedes cambiar su estado mediante reporte."
            ), ephemeral=True)
            return

        await aexecute("UPDATE vehicle_registries SET status=$1, updated_at=NOW() WHERE id=$2", (estado, veh["id"]))

        if estado == "stolen":
            embed = success_embed(
                "Alerta Policial de Robo Emitida",
                f"La unidad **{veh.get('brand_model')}** con placa `{veh.get('plate')}` ha sido marcada como **ROBADA** en la base de datos central.\n"
                f"Las patrullas de policía de Miami recibirán la orden de detención e incautación preventiva si es detectada."
            )
        else:
            embed = success_embed(
                "Vehículo Marcado como Recuperado",
                f"La unidad **{veh.get('brand_model')}** con placa `{veh.get('plate')}` ha sido restablecida a estado **ACTIVO** y habilitada para circular legalmente."
            )

        await interaction.followup.send(embed=embed, ephemeral=True)

    # ==========================================
    # COMANDO 7: /vehiculo incautar (Solo Staff / Policía)
    # ==========================================
    @vehicle_group.command(name="incautar", description="[STAFF/POLICÍA] Incauta un vehículo y envíalo al corralón municipal con una multa")
    @app_commands.describe(
        placa="Placa del vehículo a incautar",
        motivo="Razón oficial de la incautación",
        multa="Monto de la fianza/multa para liberar la unidad (por defecto $1,000)"
    )
    async def vehiculo_incautar(
        self,
        interaction: discord.Interaction,
        placa: str,
        motivo: str,
        multa: float = 1000.0
    ):
        await interaction.response.defer()
        if not await check_admin_permission(interaction):
            await interaction.followup.send(embed=error_embed("Sin Permisos", "Solo el personal de Policía o Staff autorizado puede incautar vehículos."), ephemeral=True)
            return

        gid = str(interaction.guild_id)
        plate_search = placa.strip().upper()

        veh = await aexecute(
            "SELECT * FROM vehicle_registries WHERE guild_id=$1 AND UPPER(plate)=$2",
            (gid, plate_search), fetch="one"
        )
        if not veh:
            await interaction.followup.send(embed=error_embed(
                "Vehículo No Encontrado",
                f"No existe ningún vehículo registrado con la placa `{plate_search}`."
            ), ephemeral=True)
            return

        await aexecute(
            """UPDATE vehicle_registries 
               SET status='impounded', impound_reason=$1, impound_fine=$2, updated_at=NOW() 
               WHERE id=$3""",
            (motivo.strip(), max(0.0, multa), veh["id"])
        )

        embed = success_embed(
            "🚨 Vehículo Remolcado al Corralón Municipal",
            f"La unidad **{veh.get('brand_model')}** con placa `{veh.get('plate')}` ha sido incautada oficialmente.\n\n"
            f"👤 **Titular:** <@{veh.get('discord_id')}>\n"
            f"⚖️ **Motivo:** {motivo.strip()}\n"
            f"💰 **Multa de Liberación:** `${multa:,.2f}`\n"
            f"👮 **Oficial Responsable:** {interaction.user.mention}"
        )
        embed.set_footer(text="Miami Police Department • Depósito Vehicular")

        await interaction.followup.send(embed=embed)

    # ==========================================
    # COMANDO 8: /vehiculo liberar
    # ==========================================
    @vehicle_group.command(name="liberar", description="Paga la multa de corralón y recupera la circulación de tu vehículo incautado")
    @app_commands.describe(placa="Placa del vehículo incautado")
    async def vehiculo_liberar(self, interaction: discord.Interaction, placa: str):
        await interaction.response.defer()
        gid = str(interaction.guild_id)
        uid = str(interaction.user.id)
        plate_search = placa.strip().upper()

        veh = await aexecute(
            "SELECT * FROM vehicle_registries WHERE guild_id=$1 AND UPPER(plate)=$2 AND discord_id=$3",
            (gid, plate_search, uid), fetch="one"
        )
        if not veh:
            await interaction.followup.send(embed=error_embed(
                "Vehículo No Encontrado",
                f"No se encontró ningún vehículo tuyo con la placa `{plate_search}`."
            ), ephemeral=True)
            return

        if veh.get("status") != "impounded":
            await interaction.followup.send(embed=info_embed(
                "No Incautado",
                f"El vehículo con placa `{plate_search}` no se encuentra incautado en el corralón."
            ), ephemeral=True)
            return

        fine = float(veh.get("impound_fine", 1000.0))
        user_data = await async_get_or_create_user(uid, gid, interaction.user.name, interaction.user.display_name)
        cash = float(user_data.get("cash", 0))
        bank = float(user_data.get("bank", 0))

        if cash < fine and bank < fine:
            await interaction.followup.send(embed=error_embed(
                "Fondos Insuficientes",
                f"La multa para liberar la unidad es de **${fine:,.2f}**.\n"
                f"Tienes `${cash:,.2f}` en efectivo y `${bank:,.2f}` en banco."
            ), ephemeral=True)
            return

        if cash >= fine:
            await aexecute("UPDATE users SET cash = cash - $1 WHERE discord_id=$2 AND guild_id=$3", (fine, uid, gid))
        else:
            await aexecute("UPDATE users SET bank = bank - $1 WHERE discord_id=$2 AND guild_id=$3", (fine, uid, gid))

        await aexecute(
            """UPDATE vehicle_registries 
               SET status='active', impound_reason=NULL, impound_fine=0, updated_at=NOW() 
               WHERE id=$1""",
            (veh["id"],)
        )

        embed = success_embed(
            "Unidad Liberada del Corralón",
            f"Has abonado la multa de **${fine:,.2f}**.\n"
            f"El vehículo **{veh.get('brand_model')}** con placa `{veh.get('plate')}` ha sido devuelto a tu posesión y habilitado para circular."
        )
        embed.set_footer(text="Miami Vice DMV • Comprobante de Salida de Depósito")

        await interaction.followup.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Vehicles(bot))
