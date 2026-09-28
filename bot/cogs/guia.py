"""`/guia` — manual de funcionamiento para administradores.

Documenta **todos** los comandos del bot, agrupados por area y ordenados de mas
a menos importante: lo que hay que configurar antes de abrir el servidor va
primero, y las utilidades de comodidad van al final.

Es un unico comando: al invocarlo se entrega el indice y despues todas las
secciones, paginadas para respetar los limites de Discord. No se crean
subcomandos, de modo que la lista de comandos del bot no crece.

El catalogo se declara en `SECCIONES` y se contrasta automaticamente contra el
arbol real de `app_commands`, de modo que un comando nuevo sin documentar o una
ruta mal escrita se detectan de inmediato.
"""

import logging

import discord
from discord import app_commands
from discord.ext import commands

from bot.embeds import error_embed
from bot.helpers import check_admin_permission

logger = logging.getLogger("bot.guia")

# Discord admite 25 campos por embed y 1024 caracteres por valor de campo.
EMBED_MAX_FIELDS = 25
FIELD_MAX = 1024
COLOR = discord.Colour(0x1ABC9C)


# ---------------------------------------------------------------------------
# Catalogo: un bloque por area, ordenado por prioridad (1 = lo mas vital)
# ---------------------------------------------------------------------------

SECCIONES = [
    {
        "clave": "acceso",
        "nombre": "Acceso, DNI e identidad",
        "emoji": "\U0001F511",
        "prioridad": 1,
        "resumen": "Sin esto un ciudadano no puede jugar. La verificacion es la puerta de entrada y "
                   "el DNI es su identidad oficial. Configuralo antes de abrir el servidor.",
        "comandos": [
            ("/verificar configurar",
             "Define que roles se entregan al pasar la verificacion, que roles se retiran y en que "
             "canal se recibe.", "Admin"),
            ("/verificar panel",
             "Publica el panel interactivo de verificacion en el canal que elijas.", "Admin"),
            ("/verificar agregar_rol",
             "Anade un rol extra a entregar al verificar. Los roles se acumulan.", "Admin"),
            ("/verificar remover_rol",
             "Quita un rol de la lista de roles que se entregan al verificar.", "Admin"),
            ("/verificar ver_config",
             "Muestra la configuracion actual de roles y canal de verificacion.", "Admin"),
            ("/verificar estado",
             "Consulta si un ciudadano, tu o el que indiques, esta verificado.", "Todos"),
            ("/verificar revocar",
             "Revoca la verificacion de un usuario y le retira sus roles.", "Admin"),
            ("/dni crear",
             "Tramita el DNI con la foto de Roblox sincronizada. Admite hasta 5 personajes por "
             "ciudadano y permite alternar el personaje activo.", "Ciudadanos"),
            ("/dni solicitar",
             "Alias de `/dni crear` para tramitar un personaje nuevo.", "Ciudadanos"),
            ("/dni mis_personajes",
             "Lista tus personajes registrados y permite cambiar el activo.", "Ciudadanos"),
            ("/dni ver",
             "Muestra el DNI oficial de un ciudadano con el avatar de su personaje.", "Todos"),
            ("/dni buscar",
             "Localiza a un ciudadano por su numero de DNI, del tipo MIA-123456.", "Todos"),
            ("/dni revocar",
             "Revoca o suspende el DNI de un ciudadano.", "Admin / Policia"),
            ("/roblox vincular",
             "Vincula tu cuenta de Roblox con tu perfil de Discord.", "Ciudadanos"),
            ("/roblox perfil",
             "Muestra el perfil de Roblox y las estadisticas de rol de un jugador.", "Todos"),
            ("/roblox desvincular",
             "Desvincula tu cuenta de Roblox de este servidor.", "Ciudadanos"),
            ("/nivel",
             "Consulta tu nivel, tu experiencia y lo que falta para el siguiente nivel.", "Ciudadanos"),
            ("/inventario",
             "Lista los objetos que posee tu personaje.", "Ciudadanos"),
        ],
    },
    {
        "clave": "dinero",
        "nombre": "Ingresos y pagos diarios",
        "emoji": "\U0001F4B5",
        "prioridad": 2,
        "resumen": "De donde sale el dinero. `/diario` y `/semanal` no dependen de nada, pero "
                   "`/sueldo` solo paga si el ciudadano tiene departamento, empresa o empleo publico "
                   "asignado.",
        "comandos": [
            ("/balance", "Muestra tu efectivo y tu saldo en banco.", "Ciudadanos"),
            ("/diario", "Reclama la recompensa diaria. La cantidad se ajusta en "
                        "`/admin configuracion diario`.", "Ciudadanos"),
            ("/semanal", "Reclama la recompensa semanal. Se ajusta en "
                         "`/admin configuracion semanal`.", "Ciudadanos"),
            ("/sueldo", "Cobra el sueldo diario completo. Las empresas con nomina manual se pagan "
                        "con `/empresa nomina`; el empleo publico se paga desde la Tesoreria "
                        "Municipal.", "Ciudadanos"),
            ("/salario", "Alias de `/sueldo`.", "Ciudadanos"),
            ("/trabajar", "Envia un reporte de trabajo secundario con evidencia para que un "
                          "administrador lo valide y lo pague.", "Ciudadanos"),
            ("/trabajo enviar", "Alias de `/trabajar`: registra la evidencia del trabajo.",
             "Ciudadanos"),
            ("/trabajo mis_trabajos", "Consulta tus reportes y en que estado estan: pendiente, "
                                      "aprobado o rechazado.", "Ciudadanos"),
            ("/trabajo pendientes", "Listado de reportes esperando revision del equipo de "
                                    "administracion.", "Admin"),
            ("/trabajo aprobar", "Aprueba un reporte y asigna la remuneracion acordada.", "Admin"),
            ("/trabajo rechazar", "Rechaza un reporte indicando el motivo.", "Admin"),
            ("/pagar", "Transfiere dinero de tu cartera a otro ciudadano.", "Ciudadanos"),
            ("/dar", "Entrega un objeto de tu inventario a otro ciudadano.", "Ciudadanos"),
            ("/donar", "Dona dinero a un jugador, a un departamento o a una empresa.", "Ciudadanos"),
            ("/tabla", "Muestra la tabla de lideres por riqueza, nivel o reputacion.", "Ciudadanos"),
        ],
    },
    {
        "clave": "banco",
        "nombre": "Banco, inversion y Tesoreria",
        "emoji": "\U0001F3E6",
        "prioridad": 3,
        "resumen": "El banco mueve dinero entre cartera y cuenta. La Tesoreria Municipal paga los "
                   "empleos publicos, asi que sin fondos en `/tesoro` el sueldo publico saldra en "
                   "cero.",
        "comandos": [
            ("/banco info", "Estado de tu cuenta: saldo, Ahorros y prestamos pendientes.",
             "Ciudadanos"),
            ("/banco depositar", "Mueve efectivo de tu cartera a tu cuenta bancaria.", "Ciudadanos"),
            ("/banco retirar", "Mueve dinero de tu cuenta a tu cartera.", "Ciudadanos"),
            ("/banco ahorros", "Abre una cuenta de Ahorros que genera un 2% de interes diario.",
             "Ciudadanos"),
            ("/banco prestamo", "Solicita un prestamo bancario.", "Ciudadanos"),
            ("/banco pagar", "Cancela una cuota o el total de un prestamo activo.", "Ciudadanos"),
            ("/invertir crear", "Crea una posicion de inversion a plazo.", "Ciudadanos"),
            ("/invertir portafolio", "Muestra tus inversiones activas y sus rendimientos.",
             "Ciudadanos"),
            ("/tesoro info", "Saldo y estado de la Tesoreria Municipal.", "Admin / Staff"),
            ("/tesoro depositar", "Ingresa fondos a la Tesoreria desde la economia del servidor.",
             "Admin / Staff"),
            ("/tesoro financiar", "Financia un departamento concreto desde la Tesoreria.",
             "Admin / Staff"),
            ("/lavar info", "Metodos de lavado disponibles, su coste y su riesgo.", "Ciudadanos"),
            ("/lavar dinero", "Convierte dinero sucio en limpio. Si te arrestan con dinero sin "
                              "lavar pueden quitartelo, asi que conviene usarlo rapido.", "Ciudadanos"),
        ],
    },
    {
        "clave": "empleos",
        "nombre": "Empleos publicos",
        "emoji": "\U0001F695",
        "prioridad": 4,
        "resumen": "Trabajo municipal que no exige fundar una empresa. La Tesoreria paga el sueldo, "
                   "de modo que sin fondos en `/tesoro` el ciudadano cobra cero.",
        "comandos": [
            ("/empleos listar", "Muestra los empleos publicos abiertos, su sueldo y sus plazas "
                                "libres.", "Ciudadanos"),
            ("/empleos entrar", "Entra en un empleo publico por su nombre y recibes su rol de "
                                "Discord. Si el servidor permite un solo empleo, el anterior se "
                                "cierra y su rol se retira.", "Ciudadanos"),
            ("/empleos mios", "Tu empleo publico vigente y la fecha de tu ultimo cobro.",
             "Ciudadanos"),
            ("/empleos renunciar", "Deja el empleo y pierde su rol de Discord.", "Ciudadanos"),
            ("/empleos crear", "Publica un empleo publico con nombre, sueldo diario, descripcion, "
                               "rol y maximo de plazas. El emoji se deduce del nombre.", "Admin"),
            ("/empleos editar", "Edita un empleo ya publicado. El sueldo nuevo se aplica a la "
                                "plantilla existente.", "Admin"),
            ("/empleos cerrar", "Deja de admitir candidatos. La plantilla actual sigue cobrando.",
             "Admin"),
            ("/empleos reanudar", "Reabre un empleo cerrado para admitir nuevos candidatos.",
             "Admin"),
            ("/empleos sueldo", "Cambia el sueldo diario de un empleo y lo sincroniza con su "
                                "plantilla.", "Admin"),
            ("/empleos empleados", "Lista quien ocupa un empleo publico.", "Admin"),
        ],
    },
    {
        "clave": "empresa",
        "nombre": "Empresas privadas",
        "emoji": "\U0001F3E2",
        "prioridad": 5,
        "resumen": "Negocio completo del ciudadano: puestos, nomina, menu, capital social y venta. "
                   "La licencia se cobra de la cartera al fundar. La nomina es manual: el dinero no "
                   "sale solo, se paga con `/empresa nomina` o se acumula con "
                   "`/empresa dinero acumular_nomina`.",
        "comandos": [
            ("/empresa crear", "Funda tu empresa indicando nombre, descripcion, sector, ubicacion e "
                               "impuestos. Cobra la licencia de tu cartera.", "Ciudadanos"),
            ("/empresa mi_empresa", "Resumen del negocio que diriges, sin escribir el nombre.",
             "Dueno / Gerente"),
            ("/empresa panel", "Abre el panel con botones de caja, nomina, menu, plantilla y "
                               "finanzas.", "Dueno / Gerente"),
            ("/empresa info", "Ficha publica de una empresa: caja, estado, plantilla y valor. La ve todo "
                             "el canal.", "Todos"),
            ("/empresa caja", "Caja actual, ultimas nominas y ultimos movimientos registrados.",
             "Dueno / Gerente"),
            ("/empresa nomina", "Paga la nomina pendiente desde la caja. Si la caja no alcanza, "
                                "paga solo el porcentaje que cubre y avisa del resto.",
             "Dueno / Gerente"),
            ("/empresa menu", "Muestra productos y servicios con los precios que fijo el dueno. Publico y "
                           "con boton de compra.", "Todos"),
            ("/empresa plantilla puestos", "Puestos definidos por el dueno, con su salario y su "
                                           "cupo.", "Dueno / Gerente"),
            ("/empresa plantilla crear_puesto", "Crea o edita un puesto con nombre, salario, rol de "
                                                "Discord, permisos y maximo de empleados.",
             "Dueno"),
            ("/empresa plantilla empleados", "Lista la plantilla de la empresa. Publico.",
             "Todos"),
            ("/empresa plantilla contratar", "Contrata a un ciudadano en un puesto. El salario sale "
                                             "de la caja y genera su primera nomina pendiente.",
             "Dueno / Gerente"),
            ("/empresa plantilla despedir", "Da de baja a un empleado, le retira el rol y liquida "
                                            "lo que debia.", "Dueno / Gerente"),
            ("/empresa plantilla mis_datos", "Tu ficha en la empresa: puesto, salario, permisos y "
                                             "nomina pendiente.", "Empleados"),
            ("/empresa dinero aportar", "Mete capital de tu bolsillo en la caja de la empresa.",
             "Dueno"),
            ("/empresa dinero invertir", "Registra una inversion de capital externa en el negocio.",
             "Dueno"),
            ("/empresa dinero retirar", "Saca dinero de la caja a tu cartera.", "Dueno"),
            ("/empresa dinero gasto", "Registra un gasto del negocio, como renta o suministros.",
             "Dueno"),
            ("/empresa dinero finanzas", "Libro mayor completo: cada movimiento con su concepto y "
                                         "su importe. Debe cuadrar con la caja.",
             "Dueno / Gerente"),
            ("/empresa dinero acumular_nomina", "Genera un dia de nomina pendiente sin pagarla, para "
                                                "acumular deuda hasta que la empresa tenga caja.",
             "Dueno"),
            ("/empresa catalogo agregar_producto", "Anade o edita un producto del menu con precio, "
                                                   "stock, emoji y rol opcional que se entrega al "
                                                   "comprar.", "Dueno / Gerente"),
            ("/empresa catalogo agregar_servicio", "Igual que el producto, pero como servicio.",
             "Dueno / Gerente"),
            ("/empresa catalogo comprar", "Compra un producto o contrata un servicio. El dinero sale "
                                          "de tu cartera y entra en la caja. El dueno no puede "
                                          "comprar a si mismo.", "Ciudadanos"),
            ("/empresa sociedad acciones", "Capital social emitido, precio por accion y "
                                           "accionistas.", "Ciudadanos"),
            ("/empresa sociedad emitir_acciones", "Define el capital social. El importe de las "
                                                  "compras posteriores entra en la caja.", "Dueno"),
            ("/empresa sociedad comprar_acciones", "Compra acciones de una empresa al precio "
                                                   "pactado.", "Ciudadanos"),
            ("/empresa sociedad vender_acciones", "Vende tus acciones a la propia empresa.",
             "Ciudadanos"),
            ("/empresa sociedad dividendo", "Reparte un dividendo entre los accionistas. Sin caja "
                                            "suficiente paga proporcionalmente.", "Dueno"),
            ("/empresa negocio estado", "Cambia el estado: activa, en pausa, cerrada o en quiebra. "
                                        "Una empresa en quiebra no vende ni contrata, pero conserva "
                                        "todos sus datos.", "Dueno"),
            ("/empresa negocio vender_empresa", "Pone tu empresa en venta al precio que decidas.",
             "Dueno"),
            ("/empresa negocio retirar_venta", "Saca tu empresa del mercado.", "Dueno"),
            ("/empresa negocio mercado", "Listado de empresas en venta con su precio y su caja.",
             "Ciudadanos"),
            ("/empresa negocio comprar_empresa", "Compra una empresa en venta. El precio va al "
                                                 "vendedor y la caja heredada se queda en el "
                                                 "negocio.", "Ciudadanos"),
        ],
    },
    {
        "clave": "departamentos",
        "nombre": "Departamentos oficiales",
        "emoji": "\U0001F3DB",
        "prioridad": 6,
        "resumen": "Cargos publicos del estado. El miembro cobra con `/sueldo` y su flota se "
                   "gestiona aparte con `/flota`.",
        "comandos": [
            ("/departamento lista", "Todos los departamentos oficiales activos del servidor.",
             "Todos"),
            ("/departamento info", "Ficha detallada de un departamento por su acronimo.", "Todos"),
            ("/departamento presupuesto", "Consulta el presupuesto disponible y gastado de un "
                                          "departamento.", "Todos"),
            ("/departamento postular", "Envia solicitud de ingreso indicando tu acronimo y tus "
                                       "motivos.", "Ciudadanos"),
            ("/departamento unirse", "Alias de `/departamento postular`.", "Ciudadanos"),
            ("/departamento mis_postulaciones", "Historial y estado de tus solicitudes de ingreso.",
             "Ciudadanos"),
            ("/departamento contratar", "Contrata o asciende a un miembro directamente.",
             "Admin / Mando"),
            ("/departamento despedir", "Da de baja a un miembro del departamento.",
             "Admin / Mando"),
            ("/departamento miembros", "Roster de oficiales y miembros del departamento.", "Todos"),
            ("/flota ver", "Vehiculos de la flota del departamento.", "Miembros / Admin"),
            ("/flota catalogo", "Vehiculos disponibles para comprar con presupuesto departamental.",
             "Miembros / Admin"),
            ("/flota comprar", "Compra un vehiculo para la flota del departamento.",
             "Admin / Mando"),
            ("/flota solicitar", "Solicita un vehiculo de la flota para patrullaje o servicio.",
             "Miembros"),
            ("/flota devolver", "Devuelve a la base el vehiculo que tienes asignado.", "Miembros"),
            ("/flota reparar", "Envia un vehiculo al taller y queda fuera de servicio.",
             "Miembros"),
            ("/flota gestionar", "Cambia el estado de un vehiculo de la flota.", "Admin / Mando"),
            ("/contrato lista", "Contratos de trabajo disponibles en el servidor.", "Ciudadanos"),
            ("/contrato crear", "Crea un contrato de trabajo nuevo.", "Admin"),
            ("/contrato aceptar", "Acepta un contrato y empieza a trabajar.", "Ciudadanos"),
            ("/contrato completar", "Marca un contrato como completado.", "Admin"),
            ("/solicitar aplicar", "Solicitud directa para unirse a un departamento o equipo.",
             "Ciudadanos"),
            ("/solicitar lista", "Solicitudes pendientes de revision.", "Admin"),
        ],
    },
    {
        "clave": "bienes",
        "nombre": "Propiedades, vehiculos y armas",
        "emoji": "\U0001F697",
        "prioridad": 7,
        "resumen": "Patrimonio del ciudadano. Los registros son unicos: escritura, matricula y "
                   "numero de serie balistico.",
        "comandos": [
            ("/propiedad lista", "Propiedades disponibles en el servidor.", "Todos"),
            ("/propiedad comprar", "Compra una propiedad.", "Ciudadanos"),
            ("/propiedad vender", "Vende tu propiedad. Recibes el 75% del valor.", "Ciudadanos"),
            ("/propiedad rentar", "Renta una propiedad por un canon periodico.", "Ciudadanos"),
            ("/propiedad mias", "Tus propiedades y su estado.", "Ciudadanos"),
            ("/vehiculo registrar", "Registra y matricula un auto, trailer, ATV o cuatrimoto a tu "
                                     "nombre.", "Ciudadanos"),
            ("/vehiculo mis_vehiculos", "Lista los vehiculos a tu nombre.", "Ciudadanos"),
            ("/vehiculo ver", "Tarjeta de circulacion completa por placa.", "Todos"),
            ("/vehiculo buscar", "Busca el registro de un vehiculo por su placa.", "Todos"),
            ("/vehiculo transferir", "Transfiere la titularidad a otro ciudadano.", "Ciudadanos"),
            ("/vehiculo reportar", "Reporta el vehiculo como robado o recuperado.", "Ciudadanos"),
            ("/vehiculo incautar", "Incauta el vehiculo y lo envia al corralon municipal.",
             "Staff / Policia"),
            ("/vehiculo liberar", "Paga la multa del corralon y recupera la circulacion.",
             "Ciudadanos"),
            ("/arma registrar", "Registra un arma con un numero de serie balistico unico.",
             "Ciudadanos"),
            ("/arma mis_armas", "Armas registradas a tu nombre.", "Ciudadanos"),
            ("/arma ver", "Consulta el registro balistico de un arma por su numero de serie.",
             "Todos"),
            ("/arma transferir", "Transfiere la titularidad de un arma a otro ciudadano.",
             "Ciudadanos"),
            ("/arma incautar", "Incauta un arma como parte de un procedimiento policial.",
             "Staff / Policia"),
        ],
    },
    {
        "clave": "comercio",
        "nombre": "Tiendas, mercado y mercado negro",
        "emoji": "\U0001F6D2",
        "prioridad": 8,
        "resumen": "Compra y venta entre ciudadanos. Carga el catalogo con `/adminshop` antes de "
                   "que la tienda tenga algo que vender.",
        "comandos": [
            ("/tienda explorar", "Objetos disponibles en la tienda legal.", "Ciudadanos"),
            ("/tienda info", "Detalle de un objeto de la tienda.", "Ciudadanos"),
            ("/tienda comprar", "Compra un objeto de la tienda con tu dinero.", "Ciudadanos"),
            ("/adminshop predeterminados", "Carga el catalogo legal de objetos en la tienda normal.",
             "Admin"),
            ("/adminshop mercadonegro", "Carga el catalogo ilegal exclusivo del mercado negro.",
             "Admin"),
            ("/adminshop agregar", "Anade un objeto a la tienda con su precio.", "Admin"),
            ("/adminshop quitar", "Quita un objeto de la tienda.", "Admin"),
            ("/mercado lista", "Objetos actualmente en venta entre ciudadanos.", "Ciudadanos"),
            ("/mercado vender", "Pone un objeto de tu inventario a la venta.", "Ciudadanos"),
            ("/mercado comprar", "Compra un objeto del mercado.", "Ciudadanos"),
            ("/mercado subasta", "Crea una subasta de objetos.", "Ciudadanos"),
            ("/mercado pujar", "Puja en una subasta activa.", "Ciudadanos"),
            ("/mercado cancelar", "Cancela un listado tuyo.", "Ciudadanos"),
            ("/mercadonegro explorar", "Stock disponible del mercado negro.", "Ciudadanos"),
            ("/mercadonegro comprar", "Compra del mercado negro. Es una accion ilegal y puedes ser "
                                      "marcado en un operativo policial.", "Ciudadanos"),
        ],
    },
    {
        "clave": "justicia",
        "nombre": "Policia, justicia y emergencias",
        "emoji": "\U0001F694",
        "prioridad": 9,
        "resumen": "Herramientas de staff. Define primero que roles son policia con "
                   "`/policia configurar_roles` para que un ciudadano no las use por error.",
        "comandos": [
            ("/policia configurar_roles", "Define que roles de Discord pueden usar los comandos "
                                          "policiales.", "Admin"),
            ("/policia arrestar", "Arresto y procesamiento judicial de un infractor. Genera "
                                  "antecedentes y puede abrir la opcion de fianza.", "Policia"),
            ("/policia multar", "Emite y cobra una multa de transito o infraccion.", "Policia"),
            ("/policia antecedentes", "Historial penal, arrestos y multas de un ciudadano.",
             "Policia"),
            ("/policia mis_multas", "Tus multas y fianzas pendientes de pago.", "Ciudadanos"),
            ("/policia pagar_multa", "Paga una multa de transito pendiente.", "Ciudadanos"),
            ("/policia pagar_fianza", "Paga la fianza de un arresto y obtiene la libertad "
                                      "inmediata.", "Ciudadanos"),
            ("/incidente crear", "Genera un reporte de incidente o llamada de emergencia 911.",
             "Ciudadanos"),
            ("/incidente lista", "Central de incidentes activos y despachos recientes.",
             "Policia / Staff"),
            ("/incidente ver", "Reporte detallado de un incidente.", "Policia / Staff"),
            ("/incidente atender", "Asigna patrullas o responde al llamado.", "Policia / EMS"),
            ("/incidente cerrar", "Cierra y archiva el reporte tras resolverlo.",
             "Policia / Staff"),
            ("/bolo emitir", "Emite una orden oficial de busqueda y captura.", "Policia"),
            ("/bolo lista", "Ordenes BOLO activas o en historial.", "Policia"),
            ("/bolo ver", "Ficha detallada de una orden por su codigo.", "Policia"),
            ("/bolo actualizar", "Cambia el estado de la orden a capturado o cancelado.",
             "Staff / Policia"),
            ("/bolo borrar", "Elimina permanentemente una orden BOLO del sistema.",
             "Admin / Mando"),
            ("/caso abrir", "Abre un expediente de investigacion policial o judicial.",
             "Policia / Staff"),
            ("/caso lista", "Casos y expedientes criminales radicados.", "Policia / Staff"),
            ("/caso ver", "Expediente completo con sospechosos y pruebas.", "Policia / Staff"),
            ("/caso nota_agregar", "Anade una nota o un avance de investigacion.",
             "Policia / Staff"),
            ("/caso sospechoso_vincular", "Vincula un sospechoso o imputado al expediente.",
             "Policia / Staff"),
            ("/caso evidencia_vincular", "Vincula un arma, un vehiculo, una propiedad o un "
                                         "documento como prueba.", "Policia / Staff"),
            ("/caso estado", "Actualiza la fase del expediente o su veredicto final.",
             "Staff / Juez"),
            ("/reputacion perfil", "Perfil de reputacion de un jugador.", "Todos"),
            ("/reputacion dar", "Da o quita reputacion a otro jugador.", "Ciudadanos"),
        ],
    },
    {
        "clave": "crimen",
        "nombre": "Actividades ilegales",
        "emoji": "\U0001F33F",
        "prioridad": 10,
        "resumen": "Todo lo que puede terminar en un arresto. El dinero que sale de aqui esta "
                   "sucio: lavalo con `/lavar` o gastalo rapido, porque la policia puede "
                   "quitartelo.",
        "comandos": [
            ("/drogas sembrar", "Inicia un cultivo de droga. Tarda un tiempo en estar listo.",
             "Ciudadanos"),
            ("/drogas info", "Estado de tus cultivos.", "Ciudadanos"),
            ("/drogas cosechar", "Cosecha el cultivo que ya esta listo.", "Ciudadanos"),
            ("/misiones lista", "Misiones criminales disponibles.", "Ciudadanos"),
            ("/misiones iniciar", "Inicia una mision criminal activa.", "Ciudadanos"),
            ("/misiones activas", "Tus misiones en curso.", "Ciudadanos"),
            ("/misiones completar", "Reclama la recompensa de una mision completada.",
             "Ciudadanos"),
        ],
    },
    {
        "clave": "soporte",
        "nombre": "Soporte, anuncios y comunicacion",
        "emoji": "\U0001F3E0",
        "prioridad": 11,
        "resumen": "Comunicacion hacia los ciudadanos. `/ticket` y `/anuncio` son los que mas se "
                   "usan en el dia a dia del servidor.",
        "comandos": [
            ("/ticket panel", "Publica el panel de tickets en el canal que elijas.", "Admin"),
            ("/ticket configurar", "Define la categoria de tickets y el rol de soporte.", "Admin"),
            ("/ticket abrir", "Abre un ticket de soporte interactivo.", "Ciudadanos"),
            ("/ticket cerrar", "Cierra el ticket actual.", "Ciudadanos"),
            ("/anuncio rapido", "Publica un anuncio rapido en el canal actual o en el que elijas.",
             "Staff"),
            ("/anuncio modal", "Editor visual de anuncios con soporte para textos largos.",
             "Staff"),
            ("/anuncio crear", "Crea y publica un anuncio oficial con estilo de embed.", "Staff"),
            ("/update configurar", "Carga la informacion y los cambios de una nueva actualizacion.",
             "Admin"),
            ("/update preview", "Muestra una previsualizacion del anuncio con la personalidad del "
                                "bot.", "Admin"),
            ("/update publicar", "Publica la actualizacion en el canal oficial.", "Admin"),
            ("/update canal", "Configura el canal de Discord para publicar actualizaciones.",
             "Admin"),
            ("/update historial", "Muestra las actualizaciones ya publicadas.", "Admin"),
            ("/update sync_github", "Sincroniza y detecta commits reales desde el repositorio de "
                                    "GitHub.", "Admin"),
            ("/help", "Centro de ayuda con lista interactiva de comandos del bot.", "Todos"),
            ("/ayuda", "Alias de `/help`.", "Todos"),
        ],
    },
    {
        "clave": "admin",
        "nombre": "Administracion del servidor",
        "emoji": "\U0001F6E0",
        "prioridad": 12,
        "resumen": "Respaldo del staff. Empieza por `/admin configuracion`: ahi se define el rol de "
                   "admin, el canal de logs y las recompensas por nivel.",
        "comandos": [
            ("/admin configuracion rol_admin", "Define que rol cuenta como administrador del bot.",
             "Admin"),
            ("/admin configuracion ver", "Muestra todas las configuraciones actuales del servidor.",
             "Admin"),
            ("/admin configuracion canal_log", "Canal donde se registran las acciones de staff.",
             "Admin"),
            ("/admin configuracion canal_trabajos", "Canal de revisiones para evidencias de trabajo.",
             "Admin"),
            ("/admin configuracion canal_postulaciones", "Canal de postulaciones a departamentos.",
             "Admin"),
            ("/admin configuracion canal_solicitudes", "Alias del canal de postulaciones.", "Admin"),
            ("/admin configuracion solicitud", "Alias de la configuracion de postulaciones.",
             "Admin"),
            ("/admin configuracion tickets", "Activa y ajusta el sistema de tickets.", "Admin"),
            ("/admin configuracion verificacion", "Configura el sistema de verificacion.", "Admin"),
            ("/admin configuracion diario", "Cantidad y cooldown de la recompensa diaria.", "Admin"),
            ("/admin configuracion semanal", "Cantidad y cooldown de la recompensa semanal.",
             "Admin"),
            ("/admin economia dar", "Suma dinero a la cartera o al banco de un jugador.", "Admin"),
            ("/admin economia quitar", "Resta dinero a un jugador sin dejar la cuenta en negativo.",
             "Admin"),
            ("/admin xp dar", "Suma experiencia a un jugador.", "Admin"),
            ("/admin xp quitar", "Resta experiencia a un jugador.", "Admin"),
            ("/admin xp multiplicador", "Ver o cambiar el multiplicador de XP del servidor.",
             "Admin"),
            ("/admin recompensas agregar", "Anade una recompensa de rol por nivel alcanzado.",
             "Admin"),
            ("/admin recompensas lista", "Recompensas de nivel configuradas.", "Admin"),
            ("/admin recompensas quitar", "Quita la recompensa de un nivel.", "Admin"),
            ("/admin objetos crear", "Crea un objeto nuevo en el catalogo global.", "Admin"),
            ("/admin objetos lista", "Lista todos los objetos del catalogo global.", "Admin"),
            ("/admin propiedad crear", "Crea una propiedad en el servidor.", "Admin"),
            ("/admin departamento crear", "Crea un departamento oficial nuevo.", "Admin"),
            ("/admin reset cooldowns", "Reinicia los cooldowns de un jugador.", "Admin"),
            ("/admin reset usuario", "Restablece por completo la economia de un jugador.", "Admin"),
        ],
    },
    {
        "clave": "servidor",
        "nombre": "Apertura, cierre y votaciones",
        "emoji": "\U0001F310",
        "prioridad": 13,
        "resumen": "Lo menos frecuente pero de mayor impacto: el control del estado del servidor "
                   "para la comunidad. Todos exigen Administrador de Discord.",
        "comandos": [
            ("/estado-servidor", "Estado operativo actual del servidor: abierto, cerrado o en "
                                 "votacion.", "Admin"),
            ("/abrir servidor", "Abre oficialmente el servidor mostrando el anuncio de apertura.",
             "Admin"),
            ("/abrir-servidor", "Alias de `/abrir servidor`.", "Admin"),
            ("/cerrar-servidor", "Cierra oficialmente el servidor de Roleplay.", "Admin"),
            ("/votacion-servidor", "Inicia una votacion comunitaria para decidir si se abre el "
                                   "servidor.", "Admin"),
            ("/finalizar-votacion", "Finaliza la votacion activa y publica los resultados.", "Admin"),
        ],
    },
]


def secciones_ordenadas():
    """Secciones de mas a menos importante (prioridad 1 = lo mas critico)."""
    return sorted(SECCIONES, key=lambda s: s["prioridad"])


def total_comandos():
    return sum(len(s["comandos"]) for s in SECCIONES)


def _paginas(comandos):
    """Trocea la lista en bloques que caben dentro de un embed."""
    for inicio in range(0, len(comandos), EMBED_MAX_FIELDS):
        yield comandos[inicio:inicio + EMBED_MAX_FIELDS]


async def _permiso(interaction) -> bool:
    """Responde con un error si quien llama no es administrador."""
    if await check_admin_permission(interaction):
        return True
    await interaction.response.send_message(
        embed=error_embed("Sin permisos", "La guia es solo para administradores."),
        ephemeral=True,
    )
    return False


def _indice_embed() -> discord.Embed:
    """Portada: el mapa completo ordenado de mas a menos importante."""
    secciones = secciones_ordenadas()
    embed = discord.Embed(
        title="\U0001F4D6 Guia de funcionamiento \u2014 Miami Vice RP",
        description=(
            f"Manual de los **{total_comandos()} comandos** del bot, ordenados de mas a menos "
            f"importante.\nCada seccion explica **que hace** cada comando, **como se usa** y **quien "
            f"puede** usarlo. A continuacion se envian todas las secciones en orden."
        ),
        colour=COLOR,
    )
    for seccion in secciones:
        embed.add_field(
            name=f"{seccion['emoji']} {seccion['prioridad']}. {seccion['nombre']}",
            value=f"{seccion['resumen']}\n**{len(seccion['comandos'])} comandos**"[:FIELD_MAX],
            inline=False,
        )
    embed.set_footer(text="MVERP \u00b7 Solo administradores")
    return embed


def _bloques(seccion):
    """Todos los embeds de una seccion, paginados segun el limite de Discord."""
    comandos = seccion["comandos"]
    total = -(-len(comandos) // EMBED_MAX_FIELDS)
    embeds = []
    for numero, bloque in enumerate(_paginas(comandos), start=1):
        embed = discord.Embed(
            title=f"{seccion['emoji']} {seccion['nombre']}",
            description=(f"**Prioridad {seccion['prioridad']}** \u00b7 {len(comandos)} comandos\n"
                         f"{seccion['resumen']}" if numero == 1
                         else f"{seccion['nombre']} \u00b7 continuacion"),
            colour=COLOR,
        )
        for ruta, que_hace, quien in bloque:
            embed.add_field(name=f"`{ruta}`",
                            value=f"{que_hace}\n*Acceso:* {quien}"[:FIELD_MAX],
                            inline=False)
        embed.set_footer(text=f"MVERP \u00b7 Pagina {numero}/{total}")
        embeds.append(embed)
    return embeds


def _todos_los_embeds():
    """Indice seguido de todas las secciones, ya paginado para Discord."""
    embeds = [_indice_embed()]
    for seccion in secciones_ordenadas():
        embeds += _bloques(seccion)
    return embeds


class Guia(commands.Cog):
    """Manual completo de funcionamiento, reservado a administradores."""

    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(
        name="guia",
        description="Manual de funcionamiento de todos los comandos, de mayor a menor importancia",
    )
    async def guia(self, interaction: discord.Interaction):
        """Envia el indice y todas las secciones del manual."""
        if not await _permiso(interaction):
            return
        embeds = _todos_los_embeds()
        total = len(embeds)
        for numero, embed in enumerate(embeds, start=1):
            embed.set_footer(text=f"MVERP \u00b7 {numero}/{total}")
            if numero == 1:
                await interaction.response.send_message(embed=embed, ephemeral=True)
            else:
                await interaction.followup.send(embed=embed, ephemeral=True)

    async def cog_load(self):
        logger.info("[Guia] %d secciones y %d comandos documentados en un unico comando",
                    len(SECCIONES), total_comandos())


async def setup(bot: commands.Bot):
    await bot.add_cog(Guia(bot))
