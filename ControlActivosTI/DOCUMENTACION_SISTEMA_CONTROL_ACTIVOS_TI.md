# Documentacion del Sistema de Control de Activos de TI

## 1. Introduccion y Arquitectura

### Resumen ejecutivo del sistema

El proyecto **ControlActivosTI** es una aplicacion web desarrollada en Django para administrar el ciclo de vida de activos tecnologicos dentro de una organizacion. Su alcance actual cubre:

- Registro y mantenimiento de fichas de activos TI.
- Gestion de catalogos maestros: tipos, estados, areas, cargos, empresas, ubicaciones y centros de costo.
- Administracion de colaboradores responsables de activos.
- Asignacion de activos a colaboradores con trazabilidad por detalle.
- Registro de devoluciones parciales o totales.
- Generacion automatica de actas de entrega y recepcion.
- Seguimiento tecnico mediante eventos sobre activos.

El sistema esta orientado a mantener trazabilidad operativa, administrativa y documental del inventario TI, integrando informacion tecnica del equipo, su estado actual, responsable, historial de entrega y soporte documental asociado.

### Arquitectura del proyecto

La aplicacion sigue el patron **MVT (Model - View - Template)** de Django y esta organizada en apps de dominio.

```text
ControlActivosTI/
|-- apps/
|   |-- accounts/        # autenticacion y perfil del usuario
|   |-- activos/         # activos, fotos y eventos tecnicos
|   |-- actas/           # actas y servicios de generacion documental
|   |-- asignaciones/    # entregas, detalles y devoluciones
|   |-- auditoria/       # reservada para evolucion de auditoria
|   |-- catalogos/       # tablas maestras del negocio
|   |-- colaboradores/   # colaboradores responsables
|-- config/              # settings, urls, vistas globales, admin2
|-- templates/           # plantillas HTML y plantillas base de actas
|-- static/              # recursos estaticos
|-- media/               # evidencias, fotos y actas generadas
|-- manage.py
|-- requirements.txt
```

#### Aplicacion del patron MVT

**Model**

Los modelos concentran las reglas del dominio y la integridad del negocio:

- `apps.activos.models.Activo` genera automaticamente el codigo del activo y valida si requiere `codigo_sap`.
- `apps.asignaciones.models.AsignacionDetalle` cambia automaticamente el estado del activo cuando se asigna o devuelve.
- `apps.asignaciones.models.DevolucionDetalle` cierra lineas de asignacion y recalcula el estado general de la asignacion.
- `apps.activos.models.EventoActivo` puede modificar especificaciones tecnicas y estado del activo como efecto del evento.

**View**

Las vistas usan mayormente CBV de Django:

- `ListView` para consultas y filtros.
- `CreateView` para altas de activos y asignaciones.
- `DetailView` para historiales y detalle operativo.
- `UpdateView` para registrar devoluciones.

La logica transaccional mas sensible se apoya en `transaction.atomic()` para evitar inconsistencias entre cabeceras, detalles y actualizacion de estados.

**Template**

Las plantillas HTML en `templates/` resuelven la capa de presentacion. Adicionalmente, la app `actas` utiliza plantillas de Excel y Word para emitir documentos formales de entrega y recepcion.

#### Apps funcionales del sistema

| App | Responsabilidad |
|---|---|
| `accounts` | Login, perfil de usuario y contexto de sesion |
| `catalogos` | Datos maestros y parametrizacion del negocio |
| `colaboradores` | Registro de personas que reciben o devuelven activos |
| `activos` | Inventario, fotos, estados y eventos tecnicos |
| `asignaciones` | Entrega de activos, detalles, devoluciones y trazabilidad |
| `actas` | Persistencia y generacion automatica de actas |
| `auditoria` | App creada para evolucion futura; hoy no contiene modelos operativos |
| `config` | Configuracion global, rutas y consola administrativa `admin2` |

### Requisitos del sistema y dependencias principales

#### Requisitos base

- Python 3.12 o compatible con Django 6
- PostgreSQL
- Entorno virtual recomendado
- Variables de entorno definidas en `.env`

#### Dependencias principales

| Dependencia | Proposito |
|---|---|
| `Django==6.0.3` | Framework principal |
| `psycopg==3.3.3` y `psycopg-binary==3.3.3` | Conexion a PostgreSQL |
| `python-decouple==3.8` | Gestion de variables de entorno |
| `Pillow==12.1.1` | Procesamiento de imagenes de activos |
| `openpyxl==3.1.5` | Generacion de actas Excel |
| `asgiref`, `sqlparse`, `tzdata`, `et_xmlfile` | Soporte del stack Django/OpenPyXL |

#### Configuracion tecnica relevante

- Base de datos configurada en `config/settings.py` con motor PostgreSQL.
- Idioma: `es-ec`.
- Zona horaria: `America/Guayaquil`.
- Archivos cargados:
  - `MEDIA_ROOT = BASE_DIR / "media"`
  - `MEDIA_URL = "/media/"`
- Autenticacion:
  - `LOGIN_URL = "accounts:login"`
  - `LOGIN_REDIRECT_URL = "/dashboard/"`

## 2. Modelos de Datos (EDM / Base de Datos)

### Vision general del modelo

El sistema esta compuesto por entidades maestras, entidades operativas y entidades documentales:

- **Maestras**: `TipoActivo`, `EstadoActivo`, `TipoEventoActivo`, `Area`, `Cargo`, `Empresa`, `Ubicacion`, `DepartamentoEmpresa`, `CentroCosto`.
- **Operativas**: `Activo`, `FotoActivo`, `EventoActivo`, `Colaborador`, `Asignacion`, `AsignacionDetalle`, `Devolucion`, `DevolucionDetalle`.
- **Seguridad / Perfil**: `PerfilUsuario` ligado a `AUTH_USER_MODEL`.
- **Documentales**: `ActaEntrega`.

### Diccionario de datos

## `accounts.PerfilUsuario`

| Campo | Tipo Django | Atributos | Descripcion |
|---|---|---|---|
| `user` | `OneToOneField(AUTH_USER_MODEL)` | `on_delete=CASCADE`, `related_name="perfil"` | Perfil extendido del usuario autenticado |
| `foto` | `ImageField` | `blank=True`, `null=True` | Foto de perfil del usuario |
| `telefono` | `CharField(30)` | `blank=True` | Telefono de contacto |
| `cargo_visible` | `CharField(120)` | `blank=True` | Cargo mostrado en interfaz |
| `bio` | `TextField` | `blank=True` | Nota breve del usuario |
| `updated_at` | `DateTimeField` | `auto_now=True` | Ultima actualizacion del perfil |

## `catalogos.Area`

| Campo | Tipo Django | Atributos | Descripcion |
|---|---|---|---|
| `nombre` | `CharField(100)` | `unique=True` | Nombre del area organizacional |
| `descripcion` | `TextField` | `blank=True` | Descripcion funcional |
| `activo` | `BooleanField` | `default=True` | Indica si el catalogo esta vigente |
| `created_at` | `DateTimeField` | `auto_now_add=True` | Fecha de creacion |
| `updated_at` | `DateTimeField` | `auto_now=True` | Fecha de actualizacion |

## `catalogos.Cargo`

| Campo | Tipo Django | Atributos | Descripcion |
|---|---|---|---|
| `nombre` | `CharField(100)` | `unique=True` | Nombre del cargo |
| `descripcion` | `TextField` | `blank=True` | Descripcion del cargo |
| `activo` | `BooleanField` | `default=True` | Estado del registro |
| `created_at` | `DateTimeField` | `auto_now_add=True` | Fecha de creacion |
| `updated_at` | `DateTimeField` | `auto_now=True` | Fecha de actualizacion |

## `catalogos.Empresa`

| Campo | Tipo Django | Atributos | Descripcion |
|---|---|---|---|
| `nombre` | `CharField(100)` | `unique=True` | Empresa a la que pertenece el colaborador o CECO |
| `descripcion` | `TextField` | `blank=True` | Descripcion complementaria |
| `activo` | `BooleanField` | `default=True` | Estado del registro |
| `created_at` | `DateTimeField` | `auto_now_add=True` | Fecha de creacion |
| `updated_at` | `DateTimeField` | `auto_now=True` | Fecha de actualizacion |

## `catalogos.Ubicacion`

| Campo | Tipo Django | Atributos | Descripcion |
|---|---|---|---|
| `nombre` | `CharField(100)` | `unique=True` | Ubicacion fisica |
| `descripcion` | `TextField` | `blank=True` | Detalle de sede o referencia |
| `activo` | `BooleanField` | `default=True` | Estado del registro |
| `created_at` | `DateTimeField` | `auto_now_add=True` | Fecha de creacion |
| `updated_at` | `DateTimeField` | `auto_now=True` | Fecha de actualizacion |

## `catalogos.DepartamentoEmpresa`

| Campo | Tipo Django | Atributos | Descripcion |
|---|---|---|---|
| `empresa` | `ForeignKey(Empresa)` | `on_delete=PROTECT`, `related_name="departamentos"` | Empresa propietaria del departamento |
| `nombre` | `CharField(120)` | `unique_together_logico=(empresa,nombre)` | Nombre del departamento |
| `descripcion` | `TextField` | `blank=True` | Descripcion complementaria |
| `activo` | `BooleanField` | `default=True` | Estado del departamento |
| `created_at` | `DateTimeField` | `auto_now_add=True` | Fecha de creacion |
| `updated_at` | `DateTimeField` | `auto_now=True` | Fecha de actualizacion |

## `catalogos.CentroCosto`

| Campo | Tipo Django | Atributos | Descripcion |
|---|---|---|---|
| `codigo` | `CharField(30)` | `unique=True`, `db_index=True` | Codigo oficial del CECO |
| `nombre` | `CharField(150)` | obligatorio | Nombre del centro de costo |
| `empresa` | `ForeignKey(Empresa)` | `null=True`, `blank=True`, `on_delete=PROTECT` | Empresa asociada |
| `padre` | `ForeignKey("self")` | `null=True`, `blank=True`, `on_delete=PROTECT` | Permite jerarquia de CECO |
| `tipo` | `CharField(20)` | `choices=TipoCentroCosto`, `default="OPERATIVO"` | Tipo funcional del CECO |
| `responsable` | `ForeignKey(AUTH_USER_MODEL)` | `null=True`, `blank=True`, `on_delete=PROTECT` | Usuario responsable del CECO |
| `departamentos` | `ManyToManyField(DepartamentoEmpresa)` | `blank=True` | Departamentos vinculados |
| `fecha_inicio` | `DateField` | `null=True`, `blank=True` | Inicio de vigencia |
| `fecha_fin` | `DateField` | `null=True`, `blank=True` | Fin de vigencia |
| `acepta_asignaciones` | `BooleanField` | `default=True` | Habilita uso del CECO en nuevas asignaciones |
| `activo` | `BooleanField` | `default=True` | Estado general del CECO |
| `descripcion` | `TextField` | `blank=True` | Notas administrativas |
| `created_at` | `DateTimeField` | `auto_now_add=True` | Fecha de creacion |
| `updated_at` | `DateTimeField` | `auto_now=True` | Fecha de actualizacion |

## `catalogos.TipoActivo`

| Campo | Tipo Django | Atributos | Descripcion |
|---|---|---|---|
| `nombre` | `CharField(50)` | `unique=True` | Categoria del activo |
| `descripcion` | `TextField` | `blank=True` | Descripcion del tipo |
| `activo` | `BooleanField` | `default=True` | Estado del catalogo |
| `created_at` | `DateTimeField` | `auto_now_add=True` | Fecha de creacion |
| `updated_at` | `DateTimeField` | `auto_now=True` | Fecha de actualizacion |

## `catalogos.EstadoActivo`

| Campo | Tipo Django | Atributos | Descripcion |
|---|---|---|---|
| `nombre` | `CharField(50)` | `unique=True` | Estado del activo |
| `descripcion` | `TextField` | `blank=True` | Significado operativo del estado |
| `permite_asignacion` | `BooleanField` | `default=False` | Indica si puede entrar a nuevas asignaciones |
| `activo` | `BooleanField` | `default=True` | Estado del catalogo |
| `created_at` | `DateTimeField` | `auto_now_add=True` | Fecha de creacion |
| `updated_at` | `DateTimeField` | `auto_now=True` | Fecha de actualizacion |

## `catalogos.TipoEventoActivo`

| Campo | Tipo Django | Atributos | Descripcion |
|---|---|---|---|
| `nombre` | `CharField(80)` | `unique=True` | Clasificacion del evento tecnico u operativo |
| `descripcion` | `TextField` | `blank=True` | Detalle del tipo de evento |
| `activo` | `BooleanField` | `default=True` | Estado del catalogo |
| `created_at` | `DateTimeField` | `auto_now_add=True` | Fecha de creacion |
| `updated_at` | `DateTimeField` | `auto_now=True` | Fecha de actualizacion |

## `colaboradores.Colaborador`

| Campo | Tipo Django | Atributos | Descripcion |
|---|---|---|---|
| `nombres` | `CharField(100)` | obligatorio | Nombres del colaborador |
| `apellidos` | `CharField(100)` | obligatorio | Apellidos del colaborador |
| `cedula` | `CharField(10)` | `unique=True`, `db_index=True` | Identificacion unica |
| `correo_corporativo` | `EmailField` | `unique=True` | Correo institucional |
| `empresa` | `ForeignKey(Empresa)` | `null=True`, `blank=True`, `on_delete=PROTECT` | Empresa vinculada |
| `cargo` | `ForeignKey(Cargo)` | `on_delete=PROTECT` | Cargo actual |
| `area` | `ForeignKey(Area)` | `on_delete=PROTECT` | Area organizacional |
| `ubicacion` | `ForeignKey(Ubicacion)` | `null=True`, `blank=True`, `on_delete=PROTECT` | Sede o ubicacion |
| `centro_costo` | `ForeignKey(CentroCosto)` | `null=True`, `blank=True`, `on_delete=PROTECT` | CECO vigente del colaborador |
| `estado` | `CharField(15)` | `choices=EstadoColaborador`, `default="ACTIVO"` | Estado laboral u operativo |
| `fecha_ingreso` | `DateField` | obligatorio | Fecha de ingreso |
| `observaciones` | `TextField` | `blank=True` | Notas administrativas |
| `created_at` | `DateTimeField` | `auto_now_add=True` | Fecha de creacion |
| `updated_at` | `DateTimeField` | `auto_now=True` | Fecha de actualizacion |

## `activos.Activo`

| Campo | Tipo Django | Atributos | Descripcion |
|---|---|---|---|
| `codigo` | `CharField(20)` | `unique=True`, `editable=False`, `db_index=True` | Codigo interno autogenerado del activo |
| `tipo_activo` | `ForeignKey(TipoActivo)` | `on_delete=PROTECT` | Categoria del activo |
| `marca` | `CharField(80)` | obligatorio | Marca del equipo |
| `modelo` | `CharField(80)` | obligatorio | Modelo comercial |
| `serie` | `CharField(120)` | `blank=True`, `default="S/N"`, `db_index=True` | Numero de serie |
| `codigo_sap` | `CharField(30)` | `unique=True`, `db_index=True`, `null=True`, `blank=True` | Codigo SAP unico, obligatorio para laptops y PCs |
| `cpu` | `CharField(150)` | `blank=True` | Procesador |
| `ram` | `CharField(50)` | `blank=True` | Memoria RAM |
| `disco` | `CharField(80)` | `blank=True` | Capacidad o tipo de almacenamiento |
| `sistema_operativo` | `CharField(50)` | `blank=True`, `default=""` | Sistema operativo instalado |
| `fecha_compra` | `DateField` | `null=True`, `blank=True` | Fecha de adquisicion |
| `valor` | `DecimalField(12,2)` | `null=True`, `blank=True` | Valor economico del activo |
| `estado_activo` | `ForeignKey(EstadoActivo)` | `on_delete=PROTECT` | Estado operativo actual |
| `observaciones` | `TextField` | `blank=True` | Observaciones generales |
| `created_at` | `DateTimeField` | `auto_now_add=True` | Fecha de creacion |
| `updated_at` | `DateTimeField` | `auto_now=True` | Fecha de actualizacion |

## `activos.FotoActivo`

| Campo | Tipo Django | Atributos | Descripcion |
|---|---|---|---|
| `activo` | `ForeignKey(Activo)` | `on_delete=CASCADE`, `related_name="fotos"` | Activo al que pertenece la foto |
| `imagen` | `ImageField` | `upload_to=ruta_foto_activo` | Imagen original del activo |
| `descripcion` | `CharField(255)` | `blank=True` | Descripcion de la foto |
| `orden` | `PositiveSmallIntegerField` | `null=True`, `blank=True` | Orden de visualizacion |
| `created_at` | `DateTimeField` | `auto_now_add=True` | Fecha de carga |

## `activos.EventoActivo`

| Campo | Tipo Django | Atributos | Descripcion |
|---|---|---|---|
| `activo` | `ForeignKey(Activo)` | `on_delete=CASCADE`, `related_name="eventos"` | Activo impactado |
| `tipo_evento` | `ForeignKey(TipoEventoActivo)` | `on_delete=PROTECT` | Tipo de novedad o mantenimiento |
| `fecha_evento` | `DateTimeField` | `default=timezone.now` | Fecha del evento |
| `detalle` | `TextField` | obligatorio | Descripcion del trabajo o novedad |
| `campo_afectado` | `CharField(30)` | `choices=CampoAfectado`, `default="ninguno"` | Campo tecnico que se modificara |
| `valor_anterior` | `CharField(150)` | `blank=True`, `editable=False` | Valor previo del campo afectado |
| `valor_nuevo` | `CharField(150)` | `blank=True` | Nuevo valor tecnico |
| `costo_adicional` | `DecimalField(12,2)` | `null=True`, `blank=True` | Costo del cambio o mejora |
| `sumar_costo_al_valor` | `BooleanField` | `default=False` | Indica si el costo debe sumarse al valor del activo |
| `nuevo_estado_activo` | `ForeignKey(EstadoActivo)` | `null=True`, `blank=True`, `on_delete=PROTECT` | Nuevo estado posterior al evento |
| `usuario_responsable` | `ForeignKey(AUTH_USER_MODEL)` | `on_delete=PROTECT` | Usuario que registra el evento |
| `created_at` | `DateTimeField` | `auto_now_add=True` | Fecha de creacion del registro |

## `asignaciones.Asignacion`

| Campo | Tipo Django | Atributos | Descripcion |
|---|---|---|---|
| `codigo_asignacion` | `CharField(20)` | `unique=True`, `editable=False`, `db_index=True`, `null=True`, `blank=True` | Codigo autogenerado de asignacion |
| `colaborador` | `ForeignKey(Colaborador)` | `on_delete=PROTECT` | Responsable receptor |
| `centro_costo` | `ForeignKey(CentroCosto)` | `null=True`, `blank=True`, `editable=False`, `on_delete=PROTECT` | Snapshot referencial del CECO vigente |
| `centro_costo_codigo` | `CharField(30)` | `blank=True`, `editable=False`, `db_index=True` | Codigo historico del CECO |
| `centro_costo_nombre` | `CharField(150)` | `blank=True`, `editable=False` | Nombre historico del CECO |
| `centro_costo_empresa` | `CharField(100)` | `blank=True`, `editable=False` | Empresa historica del CECO |
| `fecha_asignacion` | `DateField` | `default=timezone.now` | Fecha de entrega |
| `observaciones_entrega` | `TextField` | `blank=True` | Observaciones de entrega |
| `usuario_responsable` | `ForeignKey(AUTH_USER_MODEL)` | `on_delete=PROTECT` | Usuario que registra la asignacion |
| `estado_asignacion` | `CharField(10)` | `choices=EstadoAsignacion`, `default="ACTIVA"` | Estado agregado de la asignacion |
| `fecha_devolucion` | `DateField` | `null=True`, `blank=True` | Fecha de cierre total |
| `observaciones_devolucion` | `TextField` | `blank=True` | Observaciones consolidadas de devolucion |
| `usuario_recepcion` | `ForeignKey(AUTH_USER_MODEL)` | `null=True`, `blank=True`, `on_delete=PROTECT` | Usuario que recibe la devolucion total |
| `created_at` | `DateTimeField` | `auto_now_add=True` | Fecha de creacion |
| `updated_at` | `DateTimeField` | `auto_now=True` | Fecha de actualizacion |

## `asignaciones.AsignacionDetalle`

| Campo | Tipo Django | Atributos | Descripcion |
|---|---|---|---|
| `asignacion` | `ForeignKey(Asignacion)` | `on_delete=CASCADE`, `related_name="detalles"` | Cabecera de la asignacion |
| `activo` | `ForeignKey(Activo)` | `on_delete=PROTECT` | Activo entregado |
| `orden` | `PositiveIntegerField` | `default=1` | Orden de aparicion en el documento |
| `observaciones_linea` | `TextField` | `blank=True` | Observaciones particulares del activo en la entrega |
| `activa` | `BooleanField` | `default=True`, `db_index=True` | Indica si el activo sigue pendiente de devolucion |
| `estado_activo_devolucion` | `ForeignKey(EstadoActivo)` | `null=True`, `blank=True`, `on_delete=PROTECT` | Estado final del activo al devolverse |
| `observaciones_devolucion` | `TextField` | `blank=True` | Observaciones finales del activo |
| `created_at` | `DateTimeField` | `auto_now_add=True` | Fecha de creacion |
| `updated_at` | `DateTimeField` | `auto_now=True` | Fecha de actualizacion |

## `asignaciones.Devolucion`

| Campo | Tipo Django | Atributos | Descripcion |
|---|---|---|---|
| `codigo_devolucion` | `CharField(40)` | `unique=True`, `editable=False`, `db_index=True`, `null=True`, `blank=True` | Codigo autogenerado de devolucion |
| `asignacion` | `ForeignKey(Asignacion)` | `on_delete=CASCADE`, `related_name="devoluciones"` | Asignacion origen |
| `fecha_devolucion` | `DateField` | `default=timezone.now` | Fecha de devolucion |
| `observaciones` | `TextField` | `blank=True` | Observaciones globales de recepcion |
| `usuario_recepcion` | `ForeignKey(AUTH_USER_MODEL)` | `on_delete=PROTECT` | Usuario que registra la recepcion |
| `created_at` | `DateTimeField` | `auto_now_add=True` | Fecha de creacion |
| `updated_at` | `DateTimeField` | `auto_now=True` | Fecha de actualizacion |

## `asignaciones.DevolucionDetalle`

| Campo | Tipo Django | Atributos | Descripcion |
|---|---|---|---|
| `devolucion` | `ForeignKey(Devolucion)` | `on_delete=CASCADE`, `related_name="detalles"` | Evento de devolucion |
| `detalle_asignacion` | `ForeignKey(AsignacionDetalle)` | `on_delete=PROTECT` | Linea original de la asignacion |
| `estado_activo_devolucion` | `ForeignKey(EstadoActivo)` | `on_delete=PROTECT` | Estado con el que retorna el activo |
| `observaciones` | `TextField` | `blank=True` | Novedades de recepcion |
| `created_at` | `DateTimeField` | `auto_now_add=True` | Fecha de creacion |
| `updated_at` | `DateTimeField` | `auto_now=True` | Fecha de actualizacion |

## `actas.ActaEntrega`

| Campo | Tipo Django | Atributos | Descripcion |
|---|---|---|---|
| `asignacion` | `ForeignKey(Asignacion)` | `on_delete=CASCADE`, `related_name="actas"` | Asignacion asociada |
| `devolucion` | `ForeignKey(Devolucion)` | `null=True`, `blank=True`, `on_delete=CASCADE` | Devolucion asociada cuando es acta de recepcion |
| `tipo` | `CharField(10)` | `choices=TipoActa`, `default="ENTREGA"`, `db_index=True` | Tipo documental |
| `archivo` | `FileField` | `blank=True`, `null=True` | Archivo fisico generado |
| `nombre_archivo` | `CharField(255)` | `blank=True` | Nombre logico del archivo |
| `version_plantilla` | `CharField(20)` | `default="2.0"` | Version de plantilla utilizada |
| `usuario_generador` | `ForeignKey(AUTH_USER_MODEL)` | `on_delete=PROTECT` | Usuario que genero el documento |
| `fecha_generacion` | `DateTimeField` | `auto_now_add=True` | Fecha de emision |
| `updated_at` | `DateTimeField` | `auto_now=True` | Fecha de regeneracion o ajuste |

### Notas de integridad y relacion

- Un `Activo` puede tener multiples `FotoActivo` y multiples `EventoActivo`.
- Un `Activo` solo puede tener **una asignacion activa** al mismo tiempo, garantizado por restriccion condicional en `AsignacionDetalle`.
- Una `Asignacion` puede incluir multiples activos mediante `AsignacionDetalle`.
- Una `Asignacion` puede tener multiples devoluciones, permitiendo devolucion parcial.
- Cada `DevolucionDetalle` se vincula a una sola linea de asignacion.
- `ActaEntrega` cubre dos contextos:
  - entrega inicial de una asignacion
  - recepcion documental de una devolucion

## 3. Flujos Principales y Logica de Negocio

### a) Ingreso y categorizacion de un nuevo activo

1. Un usuario autenticado ingresa al modulo de activos.
2. La vista `ActivoCreateView` presenta `ActivoAdminForm` y el formset de fotos.
3. El usuario selecciona `tipo_activo`, `estado_activo` e ingresa la ficha tecnica.
4. El formulario valida reglas por tipo:
   - si el tipo es laptop o PC, `codigo_sap` es obligatorio;
   - si el tipo no requiere especificaciones tecnicas, se limpian `cpu`, `ram`, `disco` y `sistema_operativo`.
5. El modelo `Activo` genera automaticamente `codigo` usando un prefijo derivado del tipo.
6. Se ejecuta `full_clean()` antes de guardar para asegurar integridad.
7. Si existen imagenes, cada `FotoActivo`:
   - se normaliza a WEBP,
   - genera variantes `thumb`, `medium` y `large`,
   - se almacena en `media/activos/<codigo>/`.
8. El activo queda disponible para consulta en inventario y puede entrar al flujo de asignacion segun su `estado_activo`.

**Resultado del flujo**

- Se crea la ficha tecnica oficial del activo.
- Se asegura nomenclatura consistente.
- Queda lista la evidencia grafica del equipo.

### b) Asignacion o responsabilidad de un activo a un colaborador

1. Un usuario autenticado accede a la vista `AsignacionCreateView`.
2. El formulario carga solo:
   - colaboradores activos;
   - activos cuyo estado permita asignacion.
3. Al seleccionar un colaborador, el sistema exige que tenga un `centro_costo` vigente, activo y habilitado para asignaciones.
4. El usuario selecciona uno o varios activos.
5. `AsignacionCreateForm.clean_activos()` valida que ninguno este en estado no asignable.
6. Al guardar:
   - se crea la cabecera `Asignacion`;
   - se copia el snapshot historico del CECO del colaborador;
   - se genera `codigo_asignacion` con formato `ASG-<anio>-<secuencia>`.
7. Por cada activo seleccionado se crea un `AsignacionDetalle`.
8. Cada `AsignacionDetalle.save()` cambia automaticamente el `estado_activo` del activo a `Asignado`.
9. Despues de guardar, la vista intenta generar el acta de entrega con `generar_o_actualizar_acta(...)`.
10. El documento se persiste en `ActaEntrega` y se guarda en `media/actas/`.

**Como se construye el historial**

Aunque no existe un modelo separado llamado `HistorialAsignacion`, el historial operativo del activo se materializa en:

- `AsignacionDetalle` para saber en que asignacion participo el activo.
- `Asignacion` para conocer responsable, fechas y contexto organizacional.
- `Devolucion` y `DevolucionDetalle` para el cierre parcial o total.
- `ActaEntrega` para la evidencia documental.

En la practica, `AsignacionDetalle` funciona como el historial trazable de custodia del activo.

### c) Proceso de auditoria o baja de un activo por obsolescencia o dano

#### Flujo actual implementado

1. El usuario registra un `EventoActivo`.
2. Selecciona:
   - el activo afectado,
   - el tipo de evento,
   - el detalle,
   - opcionalmente el campo tecnico impactado,
   - opcionalmente el nuevo estado final.
3. Si el evento modifica especificaciones, el sistema exige `valor_nuevo`.
4. Si el evento implica un costo y se marca `sumar_costo_al_valor`, el costo se agrega al valor del activo.
5. Si se define `nuevo_estado_activo`, el modelo actualiza directamente el estado del activo.
6. Para casos de baja, obsolescencia, cuarentena o mantenimiento, el estado final queda reflejado en `Activo.estado_activo`.

#### Flujo de devolucion con auditoria operativa

1. Desde una asignacion abierta, el usuario ingresa a `AsignacionDevolucionView`.
2. Selecciona una o varias lineas pendientes.
3. Para cada activo devuelto, define el `estado_activo_devolucion`.
4. Se crea una cabecera `Devolucion` y luego uno o varios `DevolucionDetalle`.
5. Cada `DevolucionDetalle`:
   - marca la linea de asignacion como inactiva;
   - graba observaciones de recepcion;
   - actualiza el estado del activo con el estado final recibido.
6. La asignacion recalcula automaticamente si queda:
   - `ACTIVA`,
   - `PARCIAL`,
   - `CERRADA`.
7. El sistema genera acta de recepcion en Word para la devolucion.

#### Consideracion arquitectonica

La app `auditoria` ya existe pero todavia no contiene modelos ni servicios propios. En el estado actual, la auditoria funcional del sistema se sostiene en:

- `EventoActivo`
- `AsignacionDetalle`
- `DevolucionDetalle`
- `ActaEntrega`
- metadatos `created_at`, `updated_at` y usuarios responsables

Para una siguiente fase, la app `auditoria` podria consolidar bitacoras transversales, evidencias, hallazgos, conciliaciones fisicas y reportes de cumplimiento.

## 4. Seguridad y Roles (Control de Acceso)

### Estado actual de seguridad

Hoy el sistema implementa principalmente:

- autenticacion con el sistema nativo de Django;
- proteccion de vistas con `LoginRequiredMixin`;
- acceso privilegiado a `/admin2/` solo para usuarios `is_staff` o `is_superuser`;
- uso de Django Admin para administracion avanzada de modelos, usuarios, grupos y permisos.

No existe todavia una capa RBAC fina implementada por permisos por modulo dentro de las vistas funcionales del negocio. Sin embargo, el sistema esta bien posicionado para adoptar RBAC nativo de Django usando `Group` y `Permission`.

### Propuesta de roles RBAC

#### 1. Administrador de TI

**Perfil sugerido**

- Usuario `is_staff=True`
- Miembro del grupo `Administradores TI`

**Permisos recomendados**

- CRUD completo de activos
- CRUD completo de catalogos
- CRUD completo de colaboradores
- Crear asignaciones y registrar devoluciones
- Registrar eventos de mantenimiento, baja o cambio tecnico
- Generar y descargar actas
- Acceder a `/admin2/` y Django Admin

#### 2. Auditor

**Perfil sugerido**

- Usuario autenticado con grupo `Auditores`
- `is_staff` opcional segun politica interna

**Permisos recomendados**

- Ver activos, asignaciones, devoluciones y actas
- Ver historiales y eventos
- Descargar documentos
- Consultar reportes y trazabilidad
- Sin permisos de modificar catalogos sensibles ni eliminar informacion operativa

#### 3. Empleado o Usuario final

**Perfil sugerido**

- Usuario autenticado sin privilegios administrativos

**Permisos recomendados**

- Ver su perfil
- Consultar activos que le han sido asignados si se habilita una vista personal futura
- Descargar su propia acta si el sistema evoluciona a autoservicio
- Sin permisos para crear activos, asignaciones ni devoluciones

### Matriz sugerida de permisos

| Accion | Administrador TI | Auditor | Empleado |
|---|---|---|---|
| Ver inventario de activos | Si | Si | Limitado o no |
| Crear/editar activos | Si | No | No |
| Registrar eventos tecnicos | Si | No o limitado | No |
| Ver historial de activos | Si | Si | No |
| Crear asignaciones | Si | No | No |
| Registrar devoluciones | Si | No o limitado | No |
| Descargar actas | Si | Si | Limitado |
| Administrar catalogos | Si | No | No |
| Administrar usuarios/grupos | Si | No | No |
| Acceder a `/admin2/` | Si | Segun politica | No |
| Acceder a Django Admin | Si | Segun politica | No |

### Implementacion recomendada con Django

La estrategia recomendada es:

1. Crear grupos:
   - `Administradores TI`
   - `Auditores`
   - `Usuarios Finales`
2. Asignar permisos `add`, `change`, `delete`, `view` por modelo.
3. Incorporar `PermissionRequiredMixin` o validaciones por grupo en vistas clave.
4. Separar permisos de consulta, operacion y configuracion.
5. Agregar bitacora de accesos o cambios sensibles en la futura app `auditoria`.

## 5. Guia de Despliegue y Mantenimiento Basico

### Pasos para levantar el proyecto en desarrollo

#### 1. Crear y activar entorno virtual

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

#### 2. Instalar dependencias

```powershell
pip install -r requirements.txt
```

#### 3. Configurar variables de entorno

Crear o completar el archivo `.env` con al menos:

```env
SECRET_KEY=tu_clave_secreta
DEBUG=True
DB_NAME=control_activos_ti
DB_USER=postgres
DB_PASSWORD=tu_password
DB_HOST=127.0.0.1
DB_PORT=5432
```

#### 4. Aplicar migraciones

```powershell
python manage.py makemigrations
python manage.py migrate
```

#### 5. Crear superusuario

```powershell
python manage.py createsuperuser
```

#### 6. Levantar servidor de desarrollo

```powershell
python manage.py runserver
```

#### 7. Accesos principales

- Aplicacion: `http://127.0.0.1:8000/`
- Dashboard: `http://127.0.0.1:8000/dashboard/`
- Django Admin: `http://127.0.0.1:8000/admin/`
- Admin2: `http://127.0.0.1:8000/admin2/`

### Comandos Django utiles para mantenimiento

#### Migraciones

```powershell
python manage.py makemigrations
python manage.py migrate
python manage.py showmigrations
```

#### Administracion de usuarios

```powershell
python manage.py createsuperuser
python manage.py changepassword <usuario>
```

#### Shell de inspeccion

```powershell
python manage.py shell
```

Ejemplos utiles en shell:

```python
from apps.activos.models import Activo
from apps.asignaciones.models import Asignacion

Activo.objects.count()
Asignacion.objects.filter(estado_asignacion="ACTIVA").count()
```

#### Recoleccion de estaticos para despliegue

```powershell
python manage.py collectstatic
```

#### Ejecucion de pruebas

```powershell
python manage.py test
```

### Mantenimiento funcional recomendado

#### Catalogos base antes de operar

Antes de usar el sistema en un entorno nuevo, se recomienda cargar:

- Tipos de activo
- Estados de activo
- Tipos de evento
- Areas
- Cargos
- Empresas
- Ubicaciones
- Centros de costo

#### Estados minimos sugeridos para activos

- `Disponible`
- `Asignado`
- `Mantenimiento`
- `Cuarentena`
- `Danado`
- `Baja`
- `Obsoleto`

El estado `Disponible` deberia marcar `permite_asignacion=True`. El estado `Asignado` se usa automaticamente durante la entrega. Estados como `Cuarentena` o `Mantenimiento` no deberian habilitar nuevas asignaciones.

#### Controles operativos recomendados

- Validar periodicamente activos sin fotos.
- Revisar asignaciones activas sin acta generada.
- Verificar colaboradores sin CECO vigente.
- Auditar devoluciones parciales pendientes de cierre.
- Revisar usuarios `is_staff` y `is_superuser` de manera periodica.

## Conclusiones tecnicas

El proyecto ya cuenta con una base funcional solida para control de activos TI, especialmente en:

- inventario estructurado;
- trazabilidad por asignacion y devolucion;
- control de estados del activo;
- soporte documental automatizado;
- base apropiada para evolucionar a auditoria formal y RBAC detallado.

Las principales oportunidades de evolucion son:

1. Formalizar la app `auditoria` con bitacoras y reportes de control.
2. Implementar RBAC fino por grupos y permisos en vistas funcionales.
3. Incorporar reportes ejecutivos y tableros de cumplimiento.
4. Agregar flujos de aprobacion o firmas digitales en actas si el proceso lo requiere.

