"""
TARIFA DE HONORARIOS DE REFERENCIA — CONALBOS
Corporación Colegio Nacional de Abogados de Colombia

Fuente: "TARIFAS ABOGADOS COLOMBIA 2026 — CONALBOS" (Compilación LitiApp.com),
basada en la Resolución 02 de 2002 de la Dirección Nacional de CONALBOS.

ADVERTENCIA IMPORTANTE
----------------------
Estas tarifas NO son obligatorias. La Comisión Nacional de Disciplina Judicial
ha reiterado que el tarifario es una fuente supletiva de verificación, no una
regla imperativa. Se mantiene la libertad tarifaria entre abogado y cliente.
Criterios para fijar honorarios: trabajo desplegado, prestigio, complejidad,
cuantía y capacidad económica del cliente.

TODAS las cifras están expresadas en múltiplos del Salario Mínimo Mensual Legal
Vigente (SMMLV 2026 = $1.750.905). Cambiar SMMLV_VIGENTE actualiza toda la tabla.

Notación de cada ítem:
  smmlv  -> múltiplo del SMMLV (base). None = la tarifa es 100% porcentual.
  nota   -> componente variable (porcentajes adicionales, rangos, escalonados).
"""

import math

SMMLV_VIGENTE = 1_750_905  # Salario Mínimo Mensual Legal Vigente 2026 (COP)
FUENTE = "CONALBOS — Tarifas Abogados Colombia 2026 (Res. 02/2002)"

# (area, numero, servicio, smmlv, nota/componente variable)
TARIFAS = [
    # ======================================================= 1. DERECHO CIVIL
    ("Derecho Civil", "1", "Consulta verbal", 0.5, "El 50% de un salario minimo legal vigente"),
    ("Derecho Civil", "1.1", "Consulta escrita", 1, "Un salario minimo legal vigente"),
    ("Derecho Civil", "1.2", "Conceptos", 2, "Mas el 2% adicional cuando el negocio valga mas de $60.000.000"),
    ("Derecho Civil", "1.3", "Minutas para escrituras publicas (transferencia de bienes inmuebles)", 1,
     "Mas el dos por mil adicional cuando el negocio valga mas de $80.000.000"),
    ("Derecho Civil", "1.4", "Interrogatorio de parte", 1, "Un salario minimo legal vigente"),
    ("Derecho Civil", "1.5", "Declaracion extrajudicial", 1, "Un salario minimo legal vigente"),
    ("Derecho Civil", "1.6.1", "Cancelacion de patrimonio de familia ante notaria", 2,
     "Mas el 3% adicional cuando sea superior a $80.000.000"),
    ("Derecho Civil", "1.6.2", "Cancelacion de patrimonio de familia ante juzgado de familia", 3,
     "Mas el 3% cuando supere los $80.000.000"),
    ("Derecho Civil", "1.7", "Contratos civiles mediante documento privado", 1,
     "Mas el 2% adicional cuando el contrato valga mas de $60.000.000"),
    ("Derecho Civil", "1.8", "Apertura del testamento cerrado en caso de oposicion", 2,
     "Dos salarios minimos legales vigentes"),
    ("Derecho Civil", "1.9", "Publicacion del testamento otorgado ante cinco testigos", 2,
     "Dos salarios minimos legales vigentes"),
    ("Derecho Civil", "2", "Procesos ordinarios", None,
     "Mxima cuantia 20% | menor cuantia 15% | mayor cuantia 10%. Si el negocio supera "
     "$200.000.000, sobre el excedente se cobra el 2 por mil"),
    ("Derecho Civil", "3.1", "Servidumbres e indemnizaciones", 4,
     "Mas el 5% sobre la indemnizacion"),
    ("Derecho Civil", "3.2", "Interdictos, posesorios e indemnizaciones", 3,
     "Mas un 5% sobre la indemnizacion"),
    ("Derecho Civil", "3.3", "Entrega material al adquiriente de bien inmueble", 2,
     "Mas 5% del valor comercial hasta $100.000.000 y 3% de ahi en adelante"),
    ("Derecho Civil", "3.4", "Rendicion de cuentas", 2,
     "Mas 10% hasta $50.000.000 del valor comercial que se discuta y 5% en adelante"),
    ("Derecho Civil", "3.5", "Rendicion espontanea de cuentas", 3, "Tres salarios minimos legales vigentes"),
    ("Derecho Civil", "3.6", "Pago por consignacion", 2, "Mas el 5% adicional sobre la cuantia del proceso"),
    ("Derecho Civil", "3.7", "Impugnacion de actos o decisiones de asambleas de accionistas o juntas directivas", 3,
     "Tres salarios minimos legales vigentes"),
    ("Derecho Civil", "3.8", "Declaracion de bienes vacantes, patronatos o capellanias", 4,
     "Mas 10% hasta $50.000.000 de cuantia y 5% de ahi en adelante"),
    ("Derecho Civil", "3.9", "Restitucion de inmueble arrendado", 2,
     "Mas el 15% sobre los canones de arrendamiento de un ano"),
    ("Derecho Civil", "3.10", "Restitucion de tenencia", 1, "Un salario minimo legal vigente"),
    ("Derecho Civil", "3.10.1", "Demanda del arrendatario para entrega de la cosa arrendada", None,
     "Se aplica el 50% de lo establecido para restitucion de inmuebles (item 3.9)"),
    ("Derecho Civil", "3.10.2", "Restitucion de bienes muebles", 1,
     "Mas el 10% del valor comercial del bien"),
    ("Derecho Civil", "4.1", "Controversias sobre derechos de autor no reservadas a autoridades administrativas", 5,
     "Cinco salarios minimos legales vigentes"),
    ("Derecho Civil", "4.2", "Restitucion de bienes vendidos con pacto de reserva de dominio", 2,
     "Mas 10% cuando la cuantia sea hasta $50.000.000 y 5% de ahi en adelante"),
    ("Derecho Civil", "4.3", "Derechos del comunero (arts. 2330 al 2333 del Codigo Civil)", 2,
     "Dos salarios minimos legales vigentes"),
    ("Derecho Civil", "4.4", "Prestacion de caucion extracontractual", 2, "Dos salarios minimos legales vigentes"),
    ("Derecho Civil", "4.5", "Revelo de fianza (C.C. art. 2394)", 2, "Dos salarios minimos legales vigentes"),
    ("Derecho Civil", "4.6", "Mejoramiento de hipoteca o reposicion de la prenda", 2,
     "Dos salarios minimos legales vigentes"),
    ("Derecho Civil", "4.7", "Extincion de plazo o condicion suspensiva", 2, "Dos salarios minimos legales vigentes"),
    ("Derecho Civil", "4.8", "Reduccion de la pena, hipoteca o prenda", 2, "Dos salarios minimos legales vigentes"),
    ("Derecho Civil", "4.9", "Reduccion de intereses, perdida o fijacion de intereses corrientes", 2,
     "Dos salarios minimos legales vigentes"),
    ("Derecho Civil", "4.10", "Liquidacion de perjuicios (art. 459 del Codigo de Procedimiento Civil)", 3,
     "Tres salarios minimos legales vigentes"),
    ("Derecho Civil", "4.11", "Reposicion, cancelacion o restitucion de titulos valores", 3,
     "Mas el 25% del valor del titulo"),
    ("Derecho Civil", "4.12", "Procesos verbales senalados por el Codigo de Comercio", 3,
     "Tres salarios minimos legales vigentes"),
    ("Derecho Civil", "4.13", "Proteccion al consumidor", 3, "Tres salarios minimos legales vigentes"),
    ("Derecho Civil", "4.14", "Acciones revocatorias (Ley 222 de 1995)", 3, "Tres salarios minimos legales vigentes"),
    ("Derecho Civil", "5", "Expropiacion", 3,
     "Mas 10% hasta $20.000.000; de $20.000.001 a $100.000.000 el 8%; de ahi en adelante el 5%. "
     "Por el sistema administrativo se cobran los mismos"),
    ("Derecho Civil", "6", "Deslinde y amojonamiento", 3,
     "Mas 15% hasta $50.000.000 del valor del inmueble y 10% cuando el valor sea hasta "
     "$150.000.000. Si solo se discute la fijacion de la linea divisoria el honorario se "
     "rebaja en un 30%"),
    ("Derecho Civil", "7.1", "Division material o distribucion de su producto en caso de venta", 3,
     "Mas el 2% sobre el valor respectivo"),
    ("Derecho Civil", "7.2", "Division de grandes comunidades", 5,
     "Mas el 2% sobre el valor comercial de la comunidad"),
    ("Derecho Civil", "8.1", "Elaboracion del reglamento de copropiedad", 3,
     "Mas el 2% del valor comercial del inmueble"),
    ("Derecho Civil", "8.2", "Reforma del reglamento de copropiedad", 1.5, "El 50% de la tarifa del item 8.1"),
    ("Derecho Civil", "8.3", "Representacion de copropietarios en asamblea", 1,
     "Un salario minimo legal vigente por cada copropietario representado"),
    ("Derecho Civil", "8.4", "Controversias entre copropietarios de propiedad horizontal", 3,
     "Tres salarios minimos legales vigentes. Si se tramita ante la policia: 50% de la tarifa"),
    ("Derecho Civil", "9.1", "Proceso ejecutivo singular", 1,
     "Mxima cuantia: 1 SMMLV + 15% del credito | menor cuantia: 2 SMMLV + 10% | "
     "mayor cuantia: 4 SMMLV + 8% del valor del credito"),
    ("Derecho Civil", "9.2", "Cobro prejuridico", None, "El 10% del valor del credito"),
    ("Derecho Civil", "9.3", "Ejecucion por obligacion condicional", 3, "Tres salarios minimos legales vigentes"),
    ("Derecho Civil", "9.4", "Ejecuciones por obligaciones de dar o hacer", 2,
     "Mas el 10% adicional sobre el valor del bien"),
    ("Derecho Civil", "9.5", "Perjuicios por obligacion de no hacer", 2, "Dos salarios minimos legales vigentes"),
    ("Derecho Civil", "9.6", "Ejecucion por perjuicios (CPC art. 495)", 2, "Dos salarios minimos legales vigentes"),
    ("Derecho Civil", "9.7", "Ejecucion de obligaciones alternativas", 2, "Dos salarios minimos legales vigentes"),
    ("Derecho Civil", "9.8", "Ejecutivo para suscripcion de documentos", 3, "Tres salarios minimos legales vigentes"),
    ("Derecho Civil", "9.9", "Beneficio de exclusion", 3,
     "Tres salarios minimos legales vigentes (el PDF consigna 'dos' en el texto pero "
     "el valor publicado es 3 SMMLV)"),
    ("Derecho Civil", "9.10", "Acumulacion de procesos ejecutivos", 1,
     "Un salario minimo legal vigente mas los honorarios pactados en cada proceso"),
    ("Derecho Civil", "9.11", "Ejecutivo con titulo hipotecario o prendario", 3,
     "Mas 10% hasta $50.000.000 del valor del credito y 5% de ahi en adelante"),
    ("Derecho Civil", "9.12", "Ejecuciones fiscales", None, "Los mismos honorarios del proceso ejecutivo singular (item 9.1)"),
    ("Derecho Civil", "9.13", "Concurso de acreedores", None,
     "Sobre las sumas recaudadas: 30% sobre los primeros $500.000 | de $500.001 a "
     "$2.000.000 el 25% | de $2.000.001 a $5.000.000 el 20% | de $5.000.001 a "
     "$10.000.000 el 15% | de ahi en adelante el 10%"),
    ("Derecho Civil", "10.1.1", "Juicio de sucesion ante juzgados", None,
     "Sobre la masa hereditaria: 15% sobre el primer $1.000.000 | de $1.000.001 a "
     "$5.000.000 el 10% | de $5.000.001 hasta $50.000.000 el 5% | de $50.000.001 a "
     "$100.000.000 el 4% | de $100.000.001 en adelante el 3%. Con medidas previas, "
     "incidentes o intervencion de terceros el honorario aumenta en 10%"),
    ("Derecho Civil", "10.1.2", "Juicio de sucesion ante notario", None,
     "El 50% de la tarifa del item 10.1.1"),
    ("Derecho Civil", "10.2.1", "Nulidad y liquidacion de sociedades civiles o de hecho", 1,
     "Mas: 10% hasta $5.000.000 del patrimonio | 5% de $5.000.001 a $50.000.000 | "
     "4% de $50.000.001 a $100.000.000 | 3% de ahi en adelante"),
    ("Derecho Civil", "11.1", "Declaracion de ausencia", 2, "Dos salarios minimos legales vigentes"),
    ("Derecho Civil", "11.2", "Declaracion de muerte presunta por desaparecimiento", 2,
     "Dos salarios minimos legales vigentes"),
    ("Derecho Civil", "11.3", "Insinuacion por donacion entre vivos", 2, "Mas el 1% del valor de la donacion"),
    ("Derecho Civil", "11.4", "Correccion, sustitucion o adicion de partidas del estado civil", 1,
     "Un salario minimo legal vigente"),
    ("Derecho Civil", "11.5", "Interdiccion del demente o sordomudo, o su rehabilitacion", 1,
     "Un salario minimo legal vigente"),
    ("Derecho Civil", "11.6", "Rehabilitacion del interdicto", 3, "Tres salarios minimos legales vigentes"),
    ("Derecho Civil", "11.7", "Licencia por emancipacion voluntaria", 2, "Dos salarios minimos legales vigentes"),
    ("Derecho Civil", "11.8", "Habilitacion de edad", 2, "Dos salarios minimos legales vigentes"),
    ("Derecho Civil", "11.9", "Casacion en negocios de jurisdiccion voluntaria", 5,
     "Cinco SMMLV + 2% cuando la cuantia sea mayor de $200.000.000 (solo si no se "
     "fijaron honorarios para el recurso)"),

    # ================================================== 12. DERECHO DE FAMILIA
    ("Derecho de Familia", "12.1", "Separacion de bienes y liquidacion de la sociedad conyugal", 2,
     "Mas 8% del valor de los bienes de la parte representada hasta $10.000.000 | "
     "5% de $10.000.001 a $50.000.000 | 3% de $50.000.001 a $100.000.000 | "
     "2% mas de $100.000.000"),
    ("Derecho de Familia", "12.2", "Inexistencia del matrimonio", 2, "Dos salarios minimos legales vigentes"),
    ("Derecho de Familia", "12.3", "Nulidad y disolucion del matrimonio", 4, "Cuatro salarios minimos legales vigentes"),
    ("Derecho de Familia", "12.4", "Divorcio del matrimonio civil", 5,
     "Cinco SMMLV; si hay mutuo acuerdo, tres SMMLV"),
    ("Derecho de Familia", "12.5", "Cesacion de los efectos civiles del matrimonio religioso", 5,
     "Cinco SMMLV y por mutuo acuerdo tres SMMLV"),
    ("Derecho de Familia", "12.6", "Adopcion", 3,
     "Tres SMMLV. Si el menor va a vivir fuera del pais, diez SMMLV"),
    ("Derecho de Familia", "12.7", "Filacion natural", 5,
     "Sin peticion de herencia cinco SMMLV; con peticion de herencia cinco SMMLV mas el 5% de lo adjudicado"),
    ("Derecho de Familia", "12.8", "Proceso de alimentos", None,
     "El 20% sobre el valor de la cuota alimentaria durante un ano comun"),
    ("Derecho de Familia", "12.9", "Regulacion de visitas", 2, "Dos salarios minimos legales vigentes"),
    ("Derecho de Familia", "12.10", "Impugnacion de maternidad o paternidad", 4, "Cuatro salarios minimos legales vigentes"),
    ("Derecho de Familia", "12.11", "Legitimacion", 4, "Cuatro salarios minimos legales vigentes"),
    ("Derecho de Familia", "12.12", "Regulacion de la cuota alimentaria", 3, "Tres salarios minimos legales vigentes"),
    ("Derecho de Familia", "12.13", "Alimentos para mayores de 18 anos ante juzgados civiles", 4,
     "Cuatro salarios minimos legales vigentes"),
    ("Derecho de Familia", "12.14", "Ofrecimiento de alimentos", 2, "Dos salarios minimos legales vigentes"),
    ("Derecho de Familia", "12.15", "Exoneracion de cuota alimentaria", 2, "Dos salarios minimos legales vigentes"),
    ("Derecho de Familia", "12.16", "Ejecucion para el cobro de alimentos", None, "El 25% de lo obtenido"),
    ("Derecho de Familia", "12.17", "Declaracion de la union marital de hecho y sociedad patrimonial", 5,
     "Cinco salarios minimos legales vigentes"),
    ("Derecho de Familia", "12.18", "Suspension de la patria potestad", 5, "Cinco salarios minimos legales vigentes"),
    ("Derecho de Familia", "12.19", "Privacion o perdida de la patria potestad", 5,
     "Cinco salarios minimos legales vigentes"),
    ("Derecho de Familia", "12.20", "Interdiccion del disipador, demente o sordomudo, o su rehabilitacion", 5,
     "Cinco salarios minimos legales vigentes"),
    ("Derecho de Familia", "12.21", "Custodia, cuidado personal, visita y proteccion legal de los menores", 4,
     "Cuatro salarios minimos legales vigentes"),
    ("Derecho de Familia", "12.22", "Cancelacion del patrimonio de familia", 3, "Tres salarios minimos legales vigentes"),
    ("Derecho de Familia", "12.23", "Suspension o restablecimiento de la vida comun de los conyuges", 2,
     "Dos salarios minimos legales vigentes"),
    ("Derecho de Familia", "12.24", "Desconocimiento de hijo de mujer casada", 2,
     "Dos salarios minimos legales vigentes"),
    ("Derecho de Familia", "12.25", "Reconocimiento de hijo extramatrimonial", 4, "Cuatro salarios minimos legales vigentes"),
    ("Derecho de Familia", "12.26", "Permiso de menores para salir del pais sin acuerdo de sus representantes", 2,
     "Dos salarios minimos legales vigentes"),
    ("Derecho de Familia", "12.27", "Proteccion del nombre", 1, "Un salario minimo legal vigente"),
    ("Derecho de Familia", "12.28", "Separacion de cuerpos del matrimonio civil o canonico", 3,
     "Tres salarios minimos legales vigentes"),
    ("Derecho de Familia", "12.29", "Procesos contenciosos sobre el regimen economico del matrimonio y derechos sucesorales", 5,
     "Cinco salarios minimos legales vigentes"),
    ("Derecho de Familia", "12.30", "Licencia para enajenar o gravar bienes en los casos exigidos por la ley", 3,
     "Tres salarios minimos legales vigentes"),
    ("Derecho de Familia", "12.31", "Declaracion de ausencia", 2, "Dos salarios minimos legales vigentes"),
    ("Derecho de Familia", "12.32", "Declaracion de muerte por desaparecimiento", 3,
     "Tres salarios minimos legales vigentes"),
    ("Derecho de Familia", "12.33", "Insinuacion de donacion entre vivos", 2,
     "Dos SMMLV; si la cantidad es superior a 50 salarios minimos el 2% adicional"),
    ("Derecho de Familia", "12.34", "Negocios resueltos por conciliacion judicial, centro de conciliacion o arbitraje", None,
     "Los honorarios son el 50% de los citados para los respectivos procesos"),

    # ================================================== 13. TRAMITES NOTARIALES
    ("Tramites Notariales", "13.1", "Liquidacion de herencia, separacion de bienes, divorcio y demas negocios notariales", None,
     "El 50% del honorario senalado para el respectivo proceso judicial"),
    ("Tramites Notariales", "13.2", "Matrimonio civil", 3, "Tres salarios minimos legales vigentes"),
    ("Tramites Notariales", "13.3", "Registro extemporaneo de nacimiento o correccion de registros", 1,
     "Un salario minimo legal vigente"),
    ("Tramites Notariales", "13.4", "Cambio de nombre, supresion o adicion de la particula 'DE' en el apellido de la mujer casada", 1,
     "Un salario minimo legal vigente"),
    ("Tramites Notariales", "13.5", "Insinuacion de donaciones", 2, "Un SMMLV mas el 2% del valor de la donacion"),
    ("Tramites Notariales", "13.6", "Declaraciones extraprocesales", 1, "Un salario minimo legal vigente"),
    ("Tramites Notariales", "13.7", "Protocolizacion del matrimonio extranjero", 3, "Tres salarios minimos legales vigentes"),
    ("Tramites Notariales", "13.8", "Reconocimiento de hijos por escritura publica", 3,
     "Tres salarios minimos legales vigentes"),
    ("Tramites Notariales", "13.9", "Testamento abierto o cerrado", 3, "Tres salarios minimos legales vigentes"),

    # ==================================================== 14. DERECHO LABORAL
    ("Derecho Laboral", "14.1", "Asesoria permanente a empresa o patronos (sin intervencion en procesos ni conflictos colectivos)", 2,
     "Dos salarios minimos legales vigentes"),
    ("Derecho Laboral", "14.2", "Asesoria permanente a sindicatos o asociaciones (sin intervencion en conflictos)", 2,
     "Dos salarios minimos legales vigentes"),
    ("Derecho Laboral", "14.3", "Asesoria a patronos en conciliacion ante inspecciones del trabajo o juzgado laboral", 2,
     "Dos salarios minimos legales vigentes"),
    ("Derecho Laboral", "14.4", "Asesoria a trabajadores en conciliacion", None, "El 15% sobre el valor conciliado"),
    ("Derecho Laboral", "14.5", "Gestiones sobre reconocimiento de prestaciones sociales ante entidades oficiales o fondos", None,
     "El 30% del valor reconocido. En pensiones, el 30% sobre las mesadas reconocidas"),
    ("Derecho Laboral", "14.6", "Liquidacion de prestaciones sociales a peticion del patrono", 1,
     "Un salario minimo legal vigente. Si la solicitud la hace el trabajador se rebaja en 50%"),
    ("Derecho Laboral", "14.8", "Elaboracion de contratos de trabajo", 1, "Un salario minimo legal vigente"),
    ("Derecho Laboral", "14.9", "Elaboracion de reglamento interno de trabajo y tramite de aprobacion", 3,
     "Tres salarios minimos legales vigentes"),
    ("Derecho Laboral", "14.10", "Reglamento de higiene y seguridad industrial y tramite de aprobacion", 3,
     "Tres salarios minimos legales vigentes"),
    ("Derecho Laboral", "14.11", "Estatutos y acta de fundacion para creacion de sindicatos", 3,
     "Tres salarios minimos legales vigentes"),
    ("Derecho Laboral", "14.12", "Estatutos para cooperativas o fondos mutuales", 4, "Cuatro salarios minimos legales vigentes"),
    ("Derecho Laboral", "14.13", "Elaboracion de contratos sindicales", 3, "Tres salarios minimos legales vigentes"),
    ("Derecho Laboral", "14.14", "Elaboracion de pliegos de peticiones", 2,
     "Dos SMMLV; aumenta en un SMMLV mas cuando el sindicato tenga mas de 200 trabajadores"),
    ("Derecho Laboral", "14.15", "Asesoria a sindicatos en conflictos colectivos, etapa de arreglo directo", 3,
     "Tres SMMLV; con mas de 200 afiliados, cinco SMMLV"),
    ("Derecho Laboral", "14.16", "Asesoria a empresas en la etapa de arreglo directo de conflictos colectivos", 5,
     "Cinco salarios minimos legales vigentes"),
    ("Derecho Laboral", "14.17", "Asesoria a sindicatos en tribunal de arbitramento o etapa de huelga", 5,
     "Cinco SMMLV para trabajadores y diez SMMLV para empresas"),
    ("Derecho Laboral", "14.18", "Asesoria en conflictos entre empresas y trabajadores no sindicalizados", 5,
     "Cinco SMMLV para trabajadores y diez SMMLV para empresas"),
    ("Derecho Laboral", "14.19", "Procesos ordinarios laborales en representacion del trabajador", None,
     "Hasta la segunda instancia el 30% de lo obtenido; en recurso de casacion el 10% adicional. "
     "Para el empleador: primera instancia 3 SMMLV y segunda instancia 2 SMMLV"),
    ("Derecho Laboral", "14.20", "Fuero sindical — accion de reintegro (trabajador)", None,
     "El 30% de las sumas materia de la condena; en accion de restitucion 2 SMMLV. "
     "Levantamiento del fuero sindical como empleador: 5 SMMLV"),
    ("Derecho Laboral", "14.21", "Proceso ejecutivo laboral", None,
     "10% de la suma materia de ejecucion si se inicia en el juzgado que sigue el proceso "
     "ordinario; 20% si se inicia en juzgado diferente"),
    ("Derecho Laboral", "14.22", "Ejecutivos por reconocimiento de salarios y prestaciones contra entidades publicas", None,
     "El 20% del valor del credito cuando el poderdante sea empleado publico"),
    ("Derecho Laboral", "14.23", "Solicitud y tramitacion de cierre de empresas", 10, "Diez salarios minimos legales vigentes"),
    ("Derecho Laboral", "14.24", "Proceso arbitral laboral", 3,
     "Como apoderado del trabajador el 20% de las sumas decretadas; como apoderado del "
     "patrono 3 SMMLV"),
    ("Derecho Laboral", "14.25", "Homologacion de laudos arbitrales en conflictos colectivos", 5,
     "Cinco SMMLV ante el tribunal superior; diez SMMLV ante la Sala Laboral de la Corte "
     "Suprema. Si se apodera al trabajador se reduce en 30%"),
    ("Derecho Laboral", "14.26", "Homologacion en conflictos laborales individuales", 2,
     "Dos salarios minimos legales vigentes"),
    ("Derecho Laboral", "14.27", "Recurso de casacion laboral", 3,
     "Empleadores 5 SMMLV | contestacion de la demanda 3 SMMLV | trabajadores 4 SMMLV"),
    ("Derecho Laboral", "14.28", "Consultas verbales laborales", 0.3, "El 30% de un salario minimo legal vigente"),
    ("Derecho Laboral", "14.29", "Consultas escritas o conceptos laborales", 2,
     "Para el trabajador un SMMLV y para el patrono dos SMMLV"),
    ("Derecho Laboral", "14.30", "Agotamiento de la via gubernativa", 2, "Dos salarios minimos legales vigentes"),

    # ==================================================== 15. DERECHO AGRARIO
    ("Derecho Agrario", "15.1", "Procesos declarativos sobre asuntos contenciosos sin tramite especial", None,
     "El 30% del valor comercial del respectivo bien, pagado en dinero o en especie"),
    ("Derecho Agrario", "15.2", "Procesos reivindicatorios", 2, "Mas el 25% del valor del bien reivindicado"),
    ("Derecho Agrario", "15.3", "Procesos precesorios", 2, "Mas el 15% del valor del bien"),
    ("Derecho Agrario", "15.4", "Procesos divisorios", 3, "Tres salarios minimos legales vigentes"),
    ("Derecho Agrario", "15.5", "Expropiacion para fines agrarios distintos a la reforma social agraria", 5,
     "Cinco salarios minimos legales vigentes"),
    ("Derecho Agrario", "15.6", "Juicio de pertenencia", 2, "Mas el 10% del valor comercial del bien"),
    ("Derecho Agrario", "15.7", "Saneamiento de la pequena propiedad agraria", 5, "Cinco salarios minimos legales vigentes"),
    ("Derecho Agrario", "15.8", "Accion de despojo (C.C. art. 984)", 4, "Cuatro salarios minimos legales vigentes"),
    ("Derecho Agrario", "15.9", "Accion popular para defensa de bienes publicos en zonas rurales", 3,
     "Tres salarios minimos legales vigentes"),
    ("Derecho Agrario", "15.10", "Danos a recursos naturales renovables o deterioro ambiental", 3,
     "Tres salarios minimos legales vigentes"),
    ("Derecho Agrario", "15.11", "Incumplimiento de contratos rurales de arrendamiento o aparceria", 2,
     "Dos salarios minimos legales vigentes"),
    ("Derecho Agrario", "15.12", "Derechos del comunero sobre predios agricolas, ganaderos o comunales", 2,
     "Dos salarios minimos legales vigentes"),
    ("Derecho Agrario", "15.13", "Restitucion de bienes rurales vendidos con pacto de reserva de dominio", 2,
     "Dos salarios minimos legales vigentes"),
    ("Derecho Agrario", "15.14", "Restitucion de cauciones legales", 1, "Un salario minimo legal vigente"),
    ("Derecho Agrario", "15.15", "Revelo de fianza, mejora de hipoteca, reposicion de prenda, extincion del plazo", 2,
     "Dos salarios minimos legales vigentes"),
    ("Derecho Agrario", "15.16", "Reduccion de pena, hipoteca o prenda, o reduccion de intereses", 2,
     "Dos salarios minimos legales vigentes"),
    ("Derecho Agrario", "15.17", "Juicios resueltos por el juez como arbitro o sumariamente", 2,
     "Dos salarios minimos legales vigentes"),
    ("Derecho Agrario", "15.18", "Lanzamiento por ocupacion de hecho", 3,
     "Sin oposicion 3 SMMLV; con oposicion 5 SMMLV"),
    ("Derecho Agrario", "15.19", "Lanzamientos de arrendatarios o aparceros", 5,
     "Sin oposicion 5 SMMLV; con oposicion 8 SMMLV"),
    ("Derecho Agrario", "15.20", "Restitucion de predios a solicitud de arrendatarios o aparceros", 4,
     "Sin oposicion 4 SMMLV; con oposicion 6 SMMLV"),
    ("Derecho Agrario", "15.21", "Otros procesos de restitucion de tenencia", 4,
     "Sin oposicion 4 SMMLV; con oposicion 6 SMMLV"),
    ("Derecho Agrario", "15.22.1", "Deslinde y amojonamiento — simple deslinde", 3, "Tres salarios minimos legales vigentes"),
    ("Derecho Agrario", "15.22.2", "Deslinde y amojonamiento — con amojonamiento", 5, "Cinco salarios minimos legales vigentes"),
    ("Derecho Agrario", "15.23", "Proceso de expropiacion — defensa del demandado", 5,
     "Cinco SMMLV mas el 2% del valor comercial del inmueble"),
    ("Derecho Agrario", "15.24", "Procesos divisorios de comunidades singulares", 3,
     "Tres SMMLV mas el 1% del valor de cada predio dividido"),
    ("Derecho Agrario", "15.25", "Constitucion de sociedades agrarias", 5, "Cinco salarios minimos legales vigentes"),
    ("Derecho Agrario", "15.26", "Disolucion y liquidacion de sociedades agrarias", 5, "Cinco salarios minimos legales vigentes"),
    ("Derecho Agrario", "15.27", "Servidumbres de transito, de aguas, conexiones electricas y otras", 5,
     "Cinco salarios minimos legales vigentes"),

    # =============================================== 16. DERECHO ADMINISTRATIVO
    ("Derecho Administrativo", "16.1", "Asesoria mediante contrato de prestacion de servicios a entidades oficiales", 3,
     "Tres SMMLV por un termino superior a un mes"),
    ("Derecho Administrativo", "16.2", "Asesoria a entidades administrativas para casos especiales", 5,
     "Cinco salarios minimos legales vigentes"),
    ("Derecho Administrativo", "16.3", "Elaboracion de contratos administrativos", 3, "Tres salarios minimos legales vigentes"),
    ("Derecho Administrativo", "16.4", "Asesoria en licitaciones a proponentes", 3, "Tres salarios minimos legales vigentes"),
    ("Derecho Administrativo", "16.5", "Asesoria en la ejecucion de contratos administrativos", 3,
     "Tres salarios minimos legales vigentes"),
    ("Derecho Administrativo", "16.6", "Diligencias o consultas ante funcionarios administrativos", 1,
     "Un salario minimo legal vigente"),
    ("Derecho Administrativo", "16.7", "Agotamiento de la via gubernativa", 2,
     "Dos SMMLV; suma que hara parte de los honorarios si hay juicio contencioso"),
    ("Derecho Administrativo", "16.8", "Restablecimiento de derechos de caracter laboral no contractual", None,
     "El 30% de la suma conseguida"),
    ("Derecho Administrativo", "16.9", "Tramite de revocacion directa de un acto administrativo", 2,
     "Dos salarios minimos legales vigentes"),
    ("Derecho Administrativo", "16.10", "Registro de propiedad intelectual", 3, "Tres salarios minimos legales vigentes"),
    ("Derecho Administrativo", "16.11", "Licencias para publicaciones periodicas", 3, "Tres salarios minimos legales vigentes"),
    ("Derecho Administrativo", "16.12", "Tramitacion de concesiones para explotaciones mineras u otras", 5,
     "Cinco salarios minimos legales vigentes"),
    ("Derecho Administrativo", "16.13", "Licencias o permisos de explotacion de bosques o recursos naturales", 5,
     "Cinco salarios minimos legales vigentes"),
    ("Derecho Administrativo", "16.14", "Tramitacion de concesiones de aguas", 4, "Cuatro salarios minimos legales vigentes"),
    ("Derecho Administrativo", "16.15", "Tramitacion de servicios radiotelefonicos", 3, "Tres salarios minimos legales vigentes"),
    ("Derecho Administrativo", "16.16", "Concesiones para instalacion de radio difusion", 2,
     "Sin animo de lucro 2 SMMLV; comerciales 8 SMMLV"),
    ("Derecho Administrativo", "16.17", "Tramitacion de personerias juridicas ante camaras de comercio u oficiales", 2,
     "Sin animo de lucro, dos salarios minimos legales vigentes"),
    ("Derecho Administrativo", "16.18", "Derecho de peticion en interes general", 3, "Tres salarios minimos legales mensuales"),
    ("Derecho Administrativo", "16.19", "Derecho de peticion en interes particular", 2, "Dos salarios minimos legales mensuales"),
    ("Derecho Administrativo", "16.20", "Derecho de peticion de informaciones", 1, "Un salario minimo legal vigente"),
    ("Derecho Administrativo", "16.21", "Derecho de formular consultas", 1, "Un salario minimo legal vigente"),
    ("Derecho Administrativo", "16.22", "Accion publica de nulidad de actos administrativos", 5,
     "Cinco salarios minimos legales"),
    ("Derecho Administrativo", "16.23", "Accion de nulidad y restablecimiento del derecho", None,
     "El 30% de la suma recaudada, como minimo"),
    ("Derecho Administrativo", "16.24", "Accion de cumplimiento", 5, "Cinco salarios minimos legales vigentes"),
    ("Derecho Administrativo", "16.25", "Reparacion directa", None, "El 30% de la suma conseguida, como minimo"),
    ("Derecho Administrativo", "16.26", "Controversias sobre contratos con clausula de caducidad", 5,
     "Cinco salarios minimos legales vigentes"),
    ("Derecho Administrativo", "16.27", "Reclamacion de prestaciones periodicas", None, "El 30% de las sumas decretadas"),
    ("Derecho Administrativo", "16.28", "Nulidad de laudos arbitrales", 4, "Cuatro salarios minimos legales vigentes"),
    ("Derecho Administrativo", "16.29", "Procesos especiales de nulidad de cartas de naturaleza", 5,
     "Cinco salarios minimos legales mensuales"),
    ("Derecho Administrativo", "16.30.1", "Procesos electorales de caracter municipal", 5, "Cinco salarios minimos legales vigentes"),
    ("Derecho Administrativo", "16.30.2", "Procesos electorales departamentales o distritales", 10,
     "Diez salarios minimos legales vigentes"),
    ("Derecho Administrativo", "16.31", "Procesos electorales nacionales", 15, "Quince salarios minimos legales vigentes"),
    ("Derecho Administrativo", "16.32", "Defensa del derecho de autor", 3, "Tres salarios minimos legales vigentes"),
    ("Derecho Administrativo", "16.33.1", "Procesos disciplinarios ante entidades nominadoras", 3,
     "Tres salarios minimos legales vigentes"),
    ("Derecho Administrativo", "16.33.2", "Procesos disciplinarios ante tribunal, Consejo Superior o Procuraduria", 5,
     "Cinco salarios minimos legales vigentes"),
    ("Derecho Administrativo", "16.34", "Reclamaciones sobre impuestos, contribuciones y tasas", 1,
     "Un SMMLV + 20% de las sumas hasta $50.000.000 | 15% de $50.000.001 a $100.000.000 | "
     "10% hasta $200.000.000 | 5% de ahi en adelante. Ante el Consejo de Estado en unica "
     "instancia se aumentan en 30%"),
    ("Derecho Administrativo", "16.35", "Defensa en repeticion del Estado contra servidores publicos", 5,
     "Cinco salarios minimos legales vigentes"),

    # ================================================== 17. DERECHO COMERCIAL
    ("Derecho Comercial", "17.1.1", "Tarifa minima por hora en casos de asesorias", 0.5,
     "El 50% de un salario minimo legal vigente"),
    ("Derecho Comercial", "17.1.2", "Tarifa minima por hora para asistencia a asambleas", 0.3,
     "El 30% de un salario minimo legal vigente"),
    ("Derecho Comercial", "17.2.1", "Consulta verbal comercial", 1, "Un salario minimo legal vigente"),
    ("Derecho Comercial", "17.2.2", "Consulta por escrito comercial", 2, "Dos salarios minimos legales vigentes"),
    ("Derecho Comercial", "17.3", "Conceptos relacionados con constitucion de sociedades", 1,
     "Un salario minimo legal vigente"),
    ("Derecho Comercial", "17.4", "Conceptos sobre empresas unipersonales", 0.5,
     "El 50% de un salario minimo legal vigente"),
    ("Derecho Comercial", "17.5.1", "Constitucion de sociedad colectiva o en comandita simple", 3,
     "Tres salarios minimos legales vigentes"),
    ("Derecho Comercial", "17.5.2", "Constitucion de sociedad de responsabilidad limitada o en comandita por acciones", 4,
     "Cuatro salarios minimos legales vigentes"),
    ("Derecho Comercial", "17.5.3", "Constitucion de sociedad anonima", 10, "Diez salarios minimos legales vigentes"),
    ("Derecho Comercial", "17.5.4", "Constitucion de sociedad de economia mixta", 5, "Cinco salarios minimos legales vigentes"),
    ("Derecho Comercial", "17.5.5", "Constitucion de sociedad fiduciaria", 5, "Cinco salarios minimos legales vigentes"),
    ("Derecho Comercial", "17.5.6", "Constitucion de sociedad mercantil de hecho", 2, "Dos salarios minimos legales vigentes"),
    ("Derecho Comercial", "17.5.7", "Permiso de funcionamiento de sociedades anonimas", 3, "Tres salarios minimos legales vigentes"),
    ("Derecho Comercial", "17.5.8", "Inscripcion individual de comerciantes o industriales", 1,
     "Un salario minimo legal vigente"),
    ("Derecho Comercial", "17.6", "Reformas estatutarias", 0.5, "El 50% del honorario de cada clase de sociedad"),
    ("Derecho Comercial", "17.7", "Procesos de fusion", 10, "Diez salarios minimos legales vigentes"),
    ("Derecho Comercial", "17.8", "Contratos comerciales de intercambio de flujos de dinero (swap)", 5,
     "Cinco salarios minimos legales vigentes"),
    ("Derecho Comercial", "17.9", "Contratos de compra y venta de activos (forward)", 5, "Cinco salarios minimos legales vigentes"),
    ("Derecho Comercial", "17.10", "Contratos sobre valores negociables (underwriting)", 5,
     "Cinco salarios minimos legales vigentes"),
    ("Derecho Comercial", "17.11", "Contrato de reporte sobre titulos valores", 3, "Tres salarios minimos legales vigentes"),
    ("Derecho Comercial", "17.12", "Gestion de creditos o financiamiento (factoring)", 5,
     "Cinco salarios minimos legales vigentes"),
    ("Derecho Comercial", "17.13", "Contratos de leasing", 3, "Tres salarios minimos legales vigentes"),
    ("Derecho Comercial", "17.14", "Contratos de colaboracion empresarial (franquicia)", 5,
     "Cinco salarios minimos legales vigentes"),
    ("Derecho Comercial", "17.15", "Contrato de estimulo de nuevos productos (merchandising)", 5,
     "Cinco salarios minimos legales vigentes"),
    ("Derecho Comercial", "17.16", "Aportes para realizacion de contratos (joint ventures)", 5,
     "Cinco salarios minimos legales vigentes"),
    ("Derecho Comercial", "17.17", "Contratos de domicilio con independientes (putting out system)", 5,
     "Cinco salarios minimos legales vigentes"),
    ("Derecho Comercial", "17.18", "Contratos con empresas satelite (just in time)", 3, "Tres salarios minimos legales vigentes"),
    ("Derecho Comercial", "17.19", "Contratos de arrendamiento comercial", None,
     "El valor de un canon mensual de arriendo"),
    ("Derecho Comercial", "17.20", "Contrato de compraventa de bienes comerciales", 2, "Dos salarios minimos legales mensuales"),
    ("Derecho Comercial", "17.21.1", "Concordato en representacion del deudor", 10, "Diez salarios minimos legales vigentes"),
    ("Derecho Comercial", "17.21.2", "Concordato en defensa del acreedor", None,
     "El 10% cuando el credito es menor de $1.000.000; por cada $1.000.000 adicional el 10% "
     "sobre el honorario inicial"),
    ("Derecho Comercial", "17.22", "Concurso liquidatorio en representacion del deudor", 2,
     "Dos SMMLV mas el 10% sobre el valor total de los creditos al momento de la liquidacion"),
    ("Derecho Comercial", "17.23", "Liquidacion obligatoria", None, "El mismo honorario del concordato, disminuido en 50%"),
    ("Derecho Comercial", "17.24", "Concurso liquidatorio en representacion del deudor", 5,
     "Cinco salarios minimos como minimo"),
    ("Derecho Comercial", "17.25", "Concurso en representacion de los acreedores", None, "El 70% de la tarifa fijada para el concordato"),
    ("Derecho Comercial", "17.26", "Tramite de reactivacion empresarial (Ley 550 de 1999)", 5,
     "Cinco salarios minimos legales vigentes por cada empresa"),

    # ===================================================== 18. DERECHO PENAL
    ("Derecho Penal", "18.1", "Consulta oral penal", 1, "Un salario minimo legal vigente"),
    ("Derecho Penal", "18.2", "Consulta escrita penal", 2, "Dos salarios minimos legales vigentes"),
    ("Derecho Penal", "18.3", "Presentacion de denuncia", 2, "Dos salarios minimos legales vigentes"),
    ("Derecho Penal", "18.4", "Visita a la carcel y estudio de documentos", 2, "Dos salarios minimos legales vigentes"),
    ("Derecho Penal", "18.5", "Asistencia en actuaciones preliminares", 2, "Dos salarios minimos legales vigentes"),
    ("Derecho Penal", "18.6.1", "Asistencia a indagatoria ante juez penal municipal", 1, "Un salario minimo legal vigente"),
    ("Derecho Penal", "18.6.2", "Asistencia a indagatoria ante fiscal local", 2, "Dos salarios minimos legales vigentes"),
    ("Derecho Penal", "18.6.3", "Asistencia a indagatoria ante fiscal seccional", 3, "Tres salarios minimos legales vigentes"),
    ("Derecho Penal", "18.7.1", "Etapa instructiva ante juez penal municipal", 3, "Tres salarios minimos legales vigentes"),
    ("Derecho Penal", "18.7.2", "Etapa instructiva ante fiscalia local o seccional", 5, "Cinco salarios minimos legales vigentes"),
    ("Derecho Penal", "18.7.3", "Etapa instructiva ante jueces del circuito especializados", 10,
     "Diez salarios minimos legales vigentes"),
    ("Derecho Penal", "18.7.4", "Etapa instructiva ante la Corte Suprema de Justicia (etapa del juicio)", 20,
     "Veinte salarios minimos legales vigentes"),
    ("Derecho Penal", "18.7.5", "Etapa instructiva ante juzgados penales municipales", 5, "Cinco salarios minimos legales vigentes"),
    ("Derecho Penal", "18.7.6", "Etapa instructiva ante juzgados del circuito", 10, "Diez salarios minimos legales vigentes"),
    ("Derecho Penal", "18.7.7", "Etapa instructiva ante juzgados del circuito especializados", 20,
     "Veinte salarios minimos legales vigentes"),
    ("Derecho Penal", "18.7.8", "Etapa instructiva ante tribunales superiores", 20, "Veinte salarios minimos legales vigentes"),
    ("Derecho Penal", "18.7.9", "Proceso ante la Corte Suprema de Justicia", 30, "Treinta salarios minimos legales vigentes"),
    ("Derecho Penal", "18.7.10", "Constitucion de la parte civil dentro del proceso penal", 2,
     "Dos SMMLV mas el 30% sobre las sumas recaudadas"),
    ("Derecho Penal", "18.7.11.1", "Casacion penal", 10, "Diez salarios minimos legales vigentes"),
    ("Derecho Penal", "18.7.11.2", "Revision penal", 10, "Diez salarios minimos legales vigentes"),
    ("Derecho Penal", "18.8.1", "Voceria en audiencia publica ante juzgados penales municipales", 3,
     "Tres salarios minimos legales vigentes"),
    ("Derecho Penal", "18.8.2", "Voceria en audiencia publica ante juzgados penales del circuito", 5,
     "Cinco salarios minimos legales vigentes"),
    ("Derecho Penal", "18.8.3", "Voceria en audiencia publica ante juzgados del circuito especializados", 10,
     "Diez salarios minimos legales vigentes"),
    ("Derecho Penal", "18.9.1", "Extincion de dominio en representacion de un tercero", 5,
     "Cinco SMMLV mas el 20% del valor del bien definido en el juicio"),
    ("Derecho Penal", "18.9.2", "Extincion de dominio del titular del dominio", 10,
     "Diez SMMLV mas el 30% del valor de los bienes segun avalue del juicio"),

    # ==================================================== 19. DERECHO MILITAR
    ("Derecho Militar", "19.1.1", "Asistencia de indagatoria ante juez penal militar", 3, "Tres salarios minimos legales vigentes"),
    ("Derecho Militar", "19.1.2", "Consejo de guerra ordinario", 5, "Cinco salarios minimos legales vigentes"),
    ("Derecho Militar", "19.1.3", "Tribunal Superior Militar", 10, "Diez salarios minimos legales vigentes"),
    ("Derecho Militar", "19.2.1", "Etapa instructiva en juzgados de instruccion penal militar", 10,
     "Diez salarios minimos legales vigentes"),
    ("Derecho Militar", "19.2.2", "Etapa instructiva en el tribunal superior", 15, "Quince salarios minimos legales vigentes"),
    ("Derecho Militar", "19.2.3", "Consejo de guerra con investigacion previa", 20, "Veinte salarios minimos legales vigentes"),
    ("Derecho Militar", "19.3.1", "Consejo de guerra ordinario y segunda instancia", 10,
     "Diez salarios minimos legales vigentes"),
    ("Derecho Militar", "19.3.2", "Consejo de guerra verbal con investigacion previa", 15,
     "Quince salarios minimos legales vigentes"),
    ("Derecho Militar", "19.4", "Recursos extraordinarios en jurisdiccion penal militar", 10,
     "Diez salarios minimos legales vigentes"),
    ("Derecho Militar", "19.5", "Voceria ante la justicia castrense", 5, "Cinco salarios minimos legales vigentes"),

    # ================================================= 20. DERECHO DE POLICIA
    ("Derecho de Policia", "20.1", "Diversas gestiones ante funcionarios de policia", 1,
     "Un salario minimo legal vigente"),
    ("Derecho de Policia", "20.2", "Lanzamiento por ocupacion de hecho", 3, "Tres salarios minimos legales vigentes"),
    ("Derecho de Policia", "20.3", "Querella de policia", 3, "Tres salarios minimos legales vigentes"),
    ("Derecho de Policia", "20.4", "Segunda instancia de policia", 2, "Dos salarios minimos legales vigentes"),
    ("Derecho de Policia", "20.5", "Asuntos penales de competencia de la policia", None,
     "El 50% de lo establecido para los negocios ante los jueces penales municipales"),

    # ============================================== 21. PROPIEDAD INDUSTRIAL
    ("Propiedad Industrial", "21.1", "Solicitud sobre existencia de patentes", 1, "Un salario minimo legal vigente"),
    ("Propiedad Industrial", "21.2", "Tramitacion de patentes de invencion", 5, "Cinco salarios minimos legales vigentes"),
    ("Propiedad Industrial", "21.3", "Tramite de prorroga de patente", 3, "Tres salarios minimos legales vigentes"),
    ("Propiedad Industrial", "21.4", "Tramite de traspaso de invencion", 3, "Tres salarios minimos legales vigentes"),
    ("Propiedad Industrial", "21.5", "Cambio de nombre de propietario de patente", 2, "Dos salarios minimos legales vigentes"),
    ("Propiedad Industrial", "21.6", "Cambio de domicilio de propietario de patente", 1, "Un salario minimo legal vigente"),
    ("Propiedad Industrial", "21.7", "Presentacion de objeciones", 3, "Tres salarios minimos legales vigentes"),
    ("Propiedad Industrial", "21.8", "Contestacion a objeciones de la administracion", 3, "Tres salarios minimos legales vigentes"),
    ("Propiedad Industrial", "21.9", "Obtencion de copia de la patente", 1, "Un salario minimo legal vigente"),
    ("Propiedad Industrial", "21.10", "Solicitud de prioridad o precedencia sobre la patente", 1,
     "Un salario minimo legal vigente"),
    ("Propiedad Industrial", "21.12", "Elaboracion descriptiva del invento (honorarios independientes)", None,
     "Se cobra aparte de los honorarios de la solicitud, segun la importancia del "
     "invento y complejidad de su descripcion"),
    ("Propiedad Industrial", "21.13.1", "Registro de modelo de utilidad", 2, "Dos salarios minimos legales vigentes"),
    ("Propiedad Industrial", "21.13.2", "Registro de nuevo diseno industrial", 2, "Dos salarios minimos legales vigentes"),
    ("Propiedad Industrial", "21.13.3", "Prorroga del registro del diseno", 1, "Un salario minimo legal vigente"),
    ("Propiedad Industrial", "21.13.4", "Actuacion sobre derecho de prioridad", 2, "Dos salarios minimos legales vigentes"),
    ("Propiedad Industrial", "21.13.5", "Nulidad del registro de diseno", 2, "Dos salarios minimos legales vigentes"),
    ("Propiedad Industrial", "21.14.1", "Proteccion del secreto industrial", 5, "Cinco salarios minimos legales vigentes"),
    ("Propiedad Industrial", "21.14.2.1", "Certificacion sobre inexistencia de la marca a registrar", 1,
     "Un salario minimo legal vigente"),
    ("Propiedad Industrial", "21.14.2.2", "Tramitacion del registro de marca por cada clase", 5,
     "Cinco salarios minimos legales vigentes"),
    ("Propiedad Industrial", "21.14.2.3", "Renovacion del registro de marca", 3, "Tres salarios minimos legales vigentes"),
    ("Propiedad Industrial", "21.14.2.4", "Cambio de nombre de propietario de marca", 2, "Dos salarios minimos legales vigentes"),
    ("Propiedad Industrial", "21.14.2.5", "Cambio de domicilio de propietario de marca", 1, "Un salario minimo legal vigente"),
    ("Propiedad Industrial", "21.14.2.6", "Contestacion a objeciones de la entidad respectiva", 3,
     "Tres salarios minimos legales vigentes"),
    ("Propiedad Industrial", "21.14.2.7", "Dibujo y clise de marca figurativa", 1, "Un salario minimo legal vigente"),
    ("Propiedad Industrial", "21.14.2.8", "Solicitud de prioridad de marca", 1, "Un salario minimo legal vigente"),
    ("Propiedad Industrial", "21.14.2.9", "Cancelacion voluntaria de marca", 1, "Un salario minimo legal vigente"),
    ("Propiedad Industrial", "21.14.2.10", "Contestacion a observacion de terceros", 2, "Dos salarios minimos legales vigentes"),
    ("Propiedad Industrial", "21.15", "Registro de lemas comerciales", 1,
     "Un salario minimo legal vigente en cada marca que los use"),
    ("Propiedad Industrial", "21.16.1", "Cesion y transferencia de marcas — tramite", 2, "Dos salarios minimos legales vigentes"),
    ("Propiedad Industrial", "21.16.2", "Cesion y transferencia de marcas — elaboracion del contrato", 3,
     "Tres salarios minimos legales vigentes"),
    ("Propiedad Industrial", "21.17.1", "Solicitud de marca (registro)", 5, "Cinco salarios minimos legales vigentes"),
    ("Propiedad Industrial", "21.17.2", "Tramitacion para uso y licencia", 2, "Dos salarios minimos legales vigentes"),
    ("Propiedad Industrial", "21.18.1", "Deposito o registro de nombres comerciales", 3, "Tres salarios minimos legales vigentes"),
    ("Propiedad Industrial", "21.19.1", "Denominacion de origen — solicitud", 3, "Tres salarios minimos legales vigentes"),
    ("Propiedad Industrial", "21.19.2", "Autorizacion para utilizar la denominacion de origen", 2,
     "Dos salarios minimos vigentes"),
    ("Propiedad Industrial", "21.19.3", "Tramite de nulidad de la autorizacion", 2, "Dos salarios minimos legales vigentes"),
    ("Propiedad Industrial", "21.19.4", "Proteccion de nominaciones de origen de otros paises", 5,
     "Cinco salarios minimos legales vigentes"),
    ("Propiedad Industrial", "21.20", "Disenos industriales", 3,
     "Tres SMMLV por cada una de las 31 clases"),
    ("Propiedad Industrial", "21.21.1", "Signos distintivos — nombre comercial", 3, "Tres salarios minimos legales vigentes"),
    ("Propiedad Industrial", "21.21.2", "Ensenia para identificar un establecimiento", 2, "Dos salarios minimos legales vigentes"),
    ("Propiedad Industrial", "21.22", "Marcas de productos y de servicios", 2,
     "Dos SMMLV por la elaboracion del respectivo contrato"),
    ("Propiedad Industrial", "21.23.1", "Nombres comerciales y ensenias — tramite de deposito hasta la certificacion", 3,
     "Tres salarios minimos legales vigentes"),
    ("Propiedad Industrial", "21.23.3", "Agotamiento de la via gubernativa", 2, "Dos salarios minimos legales vigentes"),
    ("Propiedad Industrial", "21.24", "Tramitacion de recurso de reposicion o apelacion", 2, "Dos salarios minimos legales vigentes"),
    ("Propiedad Industrial", "21.25.1", "Procesos judiciales o contenciosos sobre propiedad industrial — primera instancia", 5,
     "Cinco SMMLV como demandante y tres SMMLV como demandado"),
    ("Propiedad Industrial", "21.25.2", "Segunda instancia sobre propiedad industrial", 3, "Tres salarios minimos legales vigentes"),
    ("Propiedad Industrial", "21.26", "Solicitud de testimonios anticipados", 1, "Un salario minimo legal vigente"),
    ("Propiedad Industrial", "21.27", "Inspeccion judicial anticipada", 3, "Tres salarios minimos legales vigentes"),
    ("Propiedad Industrial", "21.28", "Dictamen pericial anticipado", 2, "Dos salarios minimos legales vigentes"),
    ("Propiedad Industrial", "21.29", "Recurso de casacion en propiedad industrial", 7, "Siete salarios minimos legales vigentes"),
    ("Propiedad Industrial", "21.30", "Recurso de revision en propiedad industrial", 7, "Siete salarios minimos legales vigentes"),
    ("Propiedad Industrial", "21.31.1", "Registro de propiedad intelectual literaria o artistica", 3,
     "Tres salarios minimos legales vigentes"),
    ("Propiedad Industrial", "21.31.2", "Defensa de los derechos de autor", 3, "Tres salarios minimos legales vigentes"),

    # =================================================== 22. DERECHO SANITARIO
    ("Derecho Sanitario", "22.1", "Registro de medicamentos, cosmeticos, alimentos y licores", 5,
     "Cinco salarios minimos legales vigentes"),
    ("Derecho Sanitario", "22.2", "Renovacion de registro sanitario", 3, "Tres salarios minimos legales vigentes"),
    ("Derecho Sanitario", "22.3", "Modificacion de ingredientes iniciales", 2, "Dos salarios minimos legales vigentes"),
    ("Derecho Sanitario", "22.4", "Traspaso de registro sanitario", 1, "Un salario minimo legal vigente"),
    ("Derecho Sanitario", "22.5", "Modificacion de nombre del producto o de su formula", 2,
     "Dos salarios minimos legales vigentes"),
    ("Derecho Sanitario", "22.6", "Supresion de la exigencia de venta con formula medica", 2,
     "Dos salarios minimos legales vigentes"),
    ("Derecho Sanitario", "22.7", "Cambio de nombre de titular", 1, "Un salario minimo legal vigente"),
    ("Derecho Sanitario", "22.8", "Solicitud de revision sanitaria", 2, "Dos salarios minimos legales vigentes"),
    ("Derecho Sanitario", "22.9", "Licencias sanitarias de funcionamiento e inscripcion de laboratorios", 5,
     "Cinco salarios minimos legales vigentes"),
    ("Derecho Sanitario", "22.10", "Aprobacion de etiquetas, modificaciones o propaganda", 2,
     "Dos salarios minimos legales vigentes"),
    ("Derecho Sanitario", "22.11", "Cambio de fabricante", 1, "Un salario minimo legal vigente"),
    ("Derecho Sanitario", "22.12", "Avisos de comercializacion o presentacion de muestras", 1,
     "Un salario minimo legal vigente"),
    ("Derecho Sanitario", "22.13", "Identificacion del nombre generico", 1, "Un salario minimo legal vigente"),
    ("Derecho Sanitario", "22.14", "Desistimiento de nombre o producto", 1, "Un salario minimo legal vigente"),
    ("Derecho Sanitario", "22.15", "Registro sanitario ante el ICA", 3, "Tres salarios minimos legales vigentes"),
    ("Derecho Sanitario", "22.16", "Licencia ambiental", 3, "Tres salarios minimos legales vigentes"),

    # ==================================================== 23. DERECHO MINERO
    ("Derecho Minero", "23.1.1", "Licencia de exploracion y explotacion — pequena mineria (hasta 100 ha)", 2,
     "Dos salarios minimos legales vigentes"),
    ("Derecho Minero", "23.1.2", "Licencia de exploracion y explotacion — mediana mineria (hasta 5.000 ha)", 3,
     "Tres salarios minimos legales vigentes"),
    ("Derecho Minero", "23.1.3", "Licencia de exploracion y explotacion — gran mineria (mas de 5.000 ha)", 10,
     "Diez SMMLV; con oposicion se aumenta en 50% de los honorarios fijados"),
    ("Derecho Minero", "23.1.4.1", "Preferencia en adjudicacion — pequena mineria", 1, "Un salario minimo legal vigente"),
    ("Derecho Minero", "23.1.4.3", "Preferencia en adjudicacion — gran mineria", 3, "Tres salarios minimos legales vigentes"),
    ("Derecho Minero", "23.2", "Confecion de contratos mineros", 3, "Tres salarios minimos legales vigentes"),
    ("Derecho Minero", "23.3", "Conflictos por ocupacion o perturbacion minera", 3, "Tres salarios minimos legales vigentes"),
    ("Derecho Minero", "23.4", "Permisos para minas y depositos de metales no preciosos", 2,
     "Dos SMMLV; en caso de oposicion se aumenta en un salario mas"),
    ("Derecho Minero", "23.5", "Propuesta de concesion de metales preciosos de veta o aluvion", 3,
     "Tres salarios minimos legales vigentes"),
    ("Derecho Minero", "23.6", "Contratos con el Ministerio de Minas y Energia o concesiones", 5,
     "Cinco salarios minimos legales vigentes"),
    ("Derecho Minero", "23.7", "Contratos con entidades descentralizadas", 3, "Tres salarios minimos legales vigentes"),
    ("Derecho Minero", "23.8", "Derecho para explotar al vencimiento de la exploracion", 3, "Tres salarios minimos legales vigentes"),
    ("Derecho Minero", "23.9", "Conversion de la licencia de exploracion — pequena mineria", 2, "Dos salarios minimos legales vigentes"),
    ("Derecho Minero", "23.10", "Informes anuales sobre progreso de la exploracion", 2, "Dos salarios minimos legales vigentes"),
    ("Derecho Minero", "23.11", "Aporte minero para explotacion de depositos y yacimientos", 3, "Tres salarios minimos legales vigentes"),
    ("Derecho Minero", "23.12", "Contratos con terceros en explotacion", 3, "Tres salarios minimos legales vigentes"),
    ("Derecho Minero", "23.13", "Cancelacion de licencias mineras", 2, "Dos salarios minimos legales vigentes"),
    ("Derecho Minero", "23.14", "Contratos mineros y registros", 3, "Tres salarios minimos legales vigentes"),
    ("Derecho Minero", "23.15", "Revision de contratos mineros", 2, "Dos salarios minimos legales vigentes"),
    ("Derecho Minero", "23.16", "Contratos de concesiones mineras", 3, "Tres salarios minimos legales vigentes"),
    ("Derecho Minero", "23.17", "Asesoria en revocacion de concesiones", 3, "Tres salarios minimos legales vigentes"),
    ("Derecho Minero", "23.18.1", "Minerales radioactivos — exploracion", 5, "Cinco salarios minimos legales vigentes"),
    ("Derecho Minero", "23.18.2", "Minerales radioactivos — explotacion", 10, "Diez salarios minimos legales vigentes"),
    ("Derecho Minero", "23.18.3", "Licencia para explotaciones carboniferas", 3, "Tres salarios minimos legales vigentes"),
    ("Derecho Minero", "23.19", "Licencia de exploracion de metales preciosos", 3, "Tres salarios minimos legales vigentes"),
    ("Derecho Minero", "23.20", "Licencia de explotacion de metales preciosos", 3, "Tres salarios minimos legales vigentes"),
    ("Derecho Minero", "23.21", "Exploracion de salinas", 5, "Cinco salarios minimos legales vigentes"),
    ("Derecho Minero", "23.22", "Explotacion de salinas", 3, "Tres salarios minimos legales vigentes"),
    ("Derecho Minero", "23.23", "Materiales para la construccion en todas sus clases", None,
     "Tramite ante el Ministerio de Minas y Energia: se aumenta el 30%"),
]


# ---------------------------------------------------------------------------
# Construccion del tarifario
# ---------------------------------------------------------------------------
def valor_por_smmlv(multiplo):
    """Convierte un multiplo de SMMLV a pesos (redondeo half-up)."""
    if not multiplo:
        return 0
    return int(math.floor(SMMLV_VIGENTE * multiplo + 0.5))


def _construir(area, numero, servicio, smmlv, nota):
    return {
        "area": area,
        "numero": numero,
        "servicio": servicio,
        "smmlv": smmlv,
        "valor": valor_por_smmlv(smmlv),
        # sin base SMMLV la tarifa es 100% porcentual: el admin debe calcularla
        "autocompleta": bool(smmlv),
        "nota": nota,
        # clave para el <datalist> y el JS de autocompletado
        "clave": "%s %s" % (numero, servicio),
    }


CATALOGO = [_construir(*fila) for fila in TARIFAS]

# Indice clave -> tarifa
POR_SERVICIO = {t["clave"]: t for t in CATALOGO}


def areas(propias=None):
    """
    Areas del derecho en el orden del tarifario, sin repetir.

    `propias` es una lista de areas creadas por el despacho
    (['Derecho de Datos', ...]): se anaden al final para que la tabla las
    agrupe con nombre propio en vez de dejarlas en el grupo de huerfanos.
    """
    vista = []
    for t in CATALOGO:
        if t["area"] not in vista:
            vista.append(t["area"])
    for a in propias or []:
        if a and a not in vista:
            vista.append(a)
    return vista


def por_area(area):
    """Todos los items de un area del derecho."""
    return [t for t in CATALOGO if t["area"] == area]


MARCA_DERECHOS_ON = "Derechos On"


def _desde_extra(f):
    """Convierte una fila de la tabla tarifario_extra en un item del catalogo."""
    numero = (f.get("numero") or "").strip()
    servicio = (f.get("servicio") or "").strip()
    valor = float(f.get("valor") or 0)
    return {
        "area": f.get("area") or ("Tarifas " + MARCA_DERECHOS_ON),
        "numero": numero,
        "servicio": servicio,
        "smmlv": f.get("smmlv"),
        "valor": valor,
        "autocompleta": True,
        "nota": f.get("nota") or ("Tarifa %s (no proviene del tarifario oficial)."
                                 % MARCA_DERECHOS_ON),
        "clave": "%s %s" % (numero, servicio),
        "extra": True,
        "marca": MARCA_DERECHOS_ON,
        "fuente": f.get("fuente") or "Tarifa fijada por el despacho",
        "creado_el": f.get("creado_el") or "",
    }


def con_extras(extras, areas_propias=None):
    """
    Une el tarifario oficial de CONALBOS con los servicios que agrego el usuario.
    Los propios van al final y se marcan con 'extra': True para que la interfaz
    los distinga y el abogado sepa que no son una tarifa oficial.

    `areas_propias` es la lista de areas creadas por el despacho
    ([{'numero', 'nombre'}, ...]). Si un servicio propio pertenece a una de esas
    areas, se muestra con el nombre real del area, no con el texto generico
    "Tarifas Derechos On". Asi la tabla agrupa bien aunque el servicio se haya
    guardado antes de que existiera el area.
    """
    nombres = {str(a.get("numero", "")).strip(): a.get("nombre")
               for a in areas_propias or [] if a.get("numero")}
    catalogo = list(CATALOGO)
    indice = dict(POR_SERVICIO)
    for f in extras or []:
        item = _desde_extra(f)
        raiz = str(f.get("area_numero") or "").strip()
        if raiz and raiz in nombres:
            item["area"] = nombres[raiz]
            item["clave"] = "%s %s" % (item["numero"], item["servicio"])
        if not item["clave"] or item["clave"] in indice:
            continue
        indice[item["clave"]] = item
        catalogo.append(item)
    return catalogo, indice
