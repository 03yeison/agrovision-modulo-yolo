"""
views.py — Lógica de negocio de la aplicación AgroVision
=========================================================
Contiene TODAS las vistas (controladores) que procesan peticiones HTTP
y devuelven respuestas HTML a los templates.

Módulos cubiertos:
  1. Autenticación:  index (login), register, logout_view, verify_2fa
  2. Dashboard:      dashboard, nosotros
  3. Módulo ML:      modelos_lista, modelo_crear, modelo_detalle, modelo_ejecutar
"""

# Utilidades de Django para renderizar plantillas y redirigir
from django.shortcuts import render, redirect, get_object_or_404
# Sistema de autenticación de Django
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.models import User
# Decorador para proteger vistas que requieren sesión activa
from django.contrib.auth.decorators import login_required
# Mensajes flash (alertas de éxito, error, info que se muestran al usuario una sola vez)
from django.contrib import messages

# Envío de correo electrónico
from django.core.mail import send_mail
from django.utils import timezone
from datetime import timedelta
from django.conf import settings
import random


# ============================================================
# HELPERS DE ROL
# ============================================================

def es_admin(user):
    """
    Devuelve True si el usuario tiene rol 'admin' en su perfil
    o si es superusuario de Django.
    Se usa para controlar acceso a acciones administrativas.
    """
    try:
        return user.profile.es_admin()
    except Exception:
        return user.is_superuser


# ============================================================
# 1. AUTENTICACIÓN
# ============================================================

def index(request):
    """
    Vista de Login / Página principal.

    Flujo:
      GET  → Renderiza el formulario de inicio de sesión (index.html).
      POST → Autentica credenciales. Si son correctas:
               1. Genera un OTP de 6 dígitos y lo guarda en el perfil del usuario.
               2. Envía el OTP al correo del usuario como HTML.
               3. Guarda el ID del usuario en sesión (pre_2fa_user_id) SIN hacer
                  login permanente todavía.
               4. Redirige a la vista de verificación 2FA (verify_2fa).
             Si son incorrectas, muestra un mensaje de error.
    """
    # Si el usuario ya tiene sesión activa, no tiene sentido mostrarle el login
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        # authenticate() verifica usuario y contraseña contra la base de datos
        user = authenticate(request, username=username, password=password)

        if user is not None:
            # ── Paso 1: Generar OTP ──────────────────────────────────────────
            otp = str(random.randint(100000, 999999))

            # Asegurarse de que el perfil existe (debería crearse por señal, pero por si acaso)
            if not hasattr(user, 'profile'):
                from app.models import UserProfile
                UserProfile.objects.create(user=user)

            # Guardar el OTP y la marca de tiempo en el perfil (para validar expiración luego)
            user.profile.otp_code = otp
            user.profile.otp_created_at = timezone.now()
            user.profile.save()

            # ── Paso 2: Enviar correo con el OTP ────────────────────────────
            from django.template.loader import render_to_string
            from django.utils.html import strip_tags

            subject = '🔑 Tu código de verificación - AgroVision'
            # Renderiza el template email_2fa.html con el nombre y el código OTP
            html_message = render_to_string('email_2fa.html', {
                'nombre': user.first_name or user.username,
                'otp_code': otp
            })
            # Versión plana del correo para clientes que no soporten HTML
            plain_message = strip_tags(html_message)

            try:
                send_mail(
                    subject,
                    plain_message,
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                    html_message=html_message,
                    fail_silently=False,
                )
                messages.info(request, 'Se ha enviado un código de verificación a tu correo.')
            except Exception as e:
                # Si el SMTP no está configurado, se avisa al usuario pero no se bloquea el flujo
                messages.error(request, 'Aviso: No se pudo enviar el correo real (revisa tu consola de servidor o configura SMTP en .env).')

            # ── Paso 3: Guardar intención de login y redirigir a 2FA ────────
            # NO se llama a auth_login() aquí — el login definitivo ocurre en verify_2fa
            request.session['pre_2fa_user_id'] = user.id
            return redirect('verify_2fa')
        else:
            messages.error(request, 'Usuario o contraseña incorrectos.')

    return render(request, 'index.html')


def register(request):
    """
    Vista de Registro de nuevos usuarios.

    Flujo:
      GET  → Muestra el formulario de registro (register.html).
      POST → Valida los datos del formulario:
               - Contraseñas coincidentes y con mínimo 8 caracteres.
               - Nombre de usuario y correo únicos (no duplicados en BD).
             Si todo es correcto, crea el usuario y redirige al login.
             Si hay error, muestra mensajes descriptivos y vuelve al formulario.
    """
    # Usuarios ya autenticados no deben poder registrarse de nuevo
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        # Extraer todos los campos del formulario POST
        username = request.POST.get('username')
        email = request.POST.get('email')
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        password1 = request.POST.get('password1')
        password2 = request.POST.get('password2')

        # ── Validaciones ─────────────────────────────────────────────────────
        if password1 != password2:
            messages.error(request, 'Las contraseñas no coinciden.')
            return render(request, 'register.html')

        if len(password1) < 8:
            messages.error(request, 'La contraseña debe tener al menos 8 caracteres.')
            return render(request, 'register.html')

        # Verificar unicidad en la base de datos
        if User.objects.filter(username=username).exists():
            messages.error(request, 'El nombre de usuario ya está en uso.')
            return render(request, 'register.html')

        if User.objects.filter(email=email).exists():
            messages.error(request, 'El correo electrónico ya está registrado.')
            return render(request, 'register.html')

        # ── Crear usuario ─────────────────────────────────────────────────────
        try:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password1,       # create_user hashea automáticamente la contraseña
                first_name=first_name,
                last_name=last_name
            )
            user.save()

            messages.success(request, '¡Cuenta creada exitosamente! Por favor inicia sesión.')
            return redirect('index')

        except Exception as e:
            messages.error(request, f'Error al crear la cuenta: {str(e)}')

    return render(request, 'register.html')


# ── Decorador @login_required ────────────────────────────────────────────────
# Todas las vistas marcadas con este decorador redirigen a 'index' (login)
# si el usuario no tiene sesión activa, protegiendo el acceso.

@login_required(login_url='index')
def dashboard(request):
    """
    Panel principal del usuario autenticado.

    Muestra estadísticas básicas calculadas desde la base de datos:
      - modelos_activos:     Modelos con estado='activo'.
      - experimentos_doc:    Modelos que tienen documento de estudio adjunto.
      - ejecuciones_totales: Estimación simulada (modelos × 12).
    """
    from app.models import ModeloML, HistorialEjecucion, ModeloYOLO, DeteccionYOLO

    # Conteo de modelos activos (los que se pueden ejecutar en producción)
    modelos_activos = ModeloML.objects.filter(estado='activo').count()
    # Modelos que tienen un documento PDF de estudios académicos adjunto
    experimentos_doc = ModeloML.objects.exclude(documento_estudio='').count()
    # Total real de ejecuciones registradas en el historial
    ejecuciones_totales = HistorialEjecucion.objects.count()

    # ── Módulo YOLO ──────────────────────────────────────────────────────
    modelos_yolo = ModeloYOLO.objects.filter(estado='activo').count()
    detecciones_totales = DeteccionYOLO.objects.count()
    capturas_camara = DeteccionYOLO.objects.filter(origen='camara').count()

    context = {
        'modelos_activos': modelos_activos,
        'experimentos_doc': experimentos_doc,
        'ejecuciones_totales': ejecuciones_totales,
        'modelos_yolo': modelos_yolo,
        'detecciones_totales': detecciones_totales,
        'capturas_camara': capturas_camara,
    }
    return render(request, 'dashboard.html', context)


@login_required(login_url='index')
def logout_view(request):
    """
    Cierra la sesión del usuario actual usando auth_logout() de Django,
    muestra un mensaje de confirmación y redirige al login.
    """
    auth_logout(request)
    messages.success(request, 'Has cerrado sesión correctamente.')
    return redirect('index')


@login_required(login_url='index')
def nosotros(request):
    """
    Página de información de la plataforma AgroVision.
    Solo renderiza el template estático nosotros.html.
    """
    return render(request, 'nosotros.html')


@login_required(login_url='index')
def estadisticas(request):
    """
    Página de estadísticas de la plataforma.
    Calcula y prepara los datos para los gráficos y contadores.
    """
    from app.models import ModeloML, HistorialEjecucion, ModeloYOLO, DeteccionYOLO
    from django.db.models import Count
    import json

    total_ejecuciones = HistorialEjecucion.objects.count()
    total_modelos = ModeloML.objects.count()

    # ── Categoría a mostrar: todas | ml | yolo ──────────────────────────
    categoria_vista = request.GET.get('categoria', 'todas')
    if categoria_vista not in ('todas', 'ml', 'yolo'):
        categoria_vista = 'todas'

    # ── Módulo YOLO: modelos registrados y detecciones realizadas ───────
    total_modelos_yolo = ModeloYOLO.objects.count()
    total_detecciones = DeteccionYOLO.objects.count()
    detecciones_imagen = DeteccionYOLO.objects.filter(origen='imagen').count()
    detecciones_camara = DeteccionYOLO.objects.filter(origen='camara').count()
    # Suma de todos los objetos detectados en toda la plataforma
    from django.db.models import Sum
    objetos_detectados = DeteccionYOLO.objects.aggregate(t=Sum('total_detecciones'))['t'] or 0

    # Detecciones agrupadas por modelo YOLO (para el gráfico de barras)
    por_modelo_yolo = (DeteccionYOLO.objects
                       .values('modelo__nombre')
                       .annotate(total=Count('id'))
                       .order_by('-total')[:8])
    yolo_modelos_nombres = [i['modelo__nombre'] or 'Modelo eliminado' for i in por_modelo_yolo]
    yolo_modelos_datos = [i['total'] for i in por_modelo_yolo]

    # Promedio de objetos por detección, útil como métrica del informe
    promedio_objetos = round(objetos_detectados / total_detecciones, 2) if total_detecciones else 0

    # Agrupar modelos por categoría para el gráfico de dona
    modelos_por_categoria = ModeloML.objects.values('categoria').annotate(total=Count('id')).order_by('-total')
    categorias_nombres = [item['categoria'] for item in modelos_por_categoria]
    categorias_datos = [item['total'] for item in modelos_por_categoria]

    # Agrupar ejecuciones por categoría del modelo (usando la relación)
    ejecuciones_por_categoria = HistorialEjecucion.objects.values('modelo__categoria').annotate(total=Count('id')).order_by('-total')
    
    ejec_nombres = []
    ejec_datos = []
    ejecuciones_porcentajes = []
    
    for item in ejecuciones_por_categoria:
        nombre_cat = item['modelo__categoria'] if item['modelo__categoria'] else 'Desconocida'
        total_ejec = item['total']
        ejec_nombres.append(nombre_cat)
        ejec_datos.append(total_ejec)
        
        porcentaje = (total_ejec / total_ejecuciones * 100) if total_ejecuciones > 0 else 0
        ejecuciones_porcentajes.append({
            'nombre': nombre_cat,
            'porcentaje': porcentaje
        })

    context = {
        'total_ejecuciones': total_ejecuciones,
        'total_modelos': total_modelos,
        'total_modelos_yolo': total_modelos_yolo,
        'total_detecciones': total_detecciones,
        'detecciones_imagen': detecciones_imagen,
        'detecciones_camara': detecciones_camara,
        'objetos_detectados': objetos_detectados,
        'promedio_objetos': promedio_objetos,
        'categoria_vista': categoria_vista,
        'yolo_modelos_nombres_json': json.dumps(yolo_modelos_nombres),
        'yolo_modelos_datos_json': json.dumps(yolo_modelos_datos),
        'origen_datos_json': json.dumps([detecciones_imagen, detecciones_camara]),
        'ejecuciones_porcentajes': ejecuciones_porcentajes,
        'categorias_nombres_json': json.dumps(categorias_nombres),
        'categorias_datos_json': json.dumps(categorias_datos),
        'ejec_nombres_json': json.dumps(ejec_nombres),
        'ejec_datos_json': json.dumps(ejec_datos),
    }
    return render(request, 'estadisticas.html', context)


def verify_2fa(request):
    """
    Verificación del segundo factor de autenticación (OTP por correo).

    Flujo:
      - Lee el ID de usuario guardado en sesión (pre_2fa_user_id) por la vista index().
      - Si no existe, redirige al login (sesión inválida o expirada).
      GET  → Muestra el formulario de ingreso del código OTP, con el correo enmascarado.
      POST → Valida el código:
               1. Verifica que existe un código OTP pendiente.
               2. Verifica que no haya expirado (límite: 5 minutos).
               3. Compara el código ingresado con el almacenado.
             Si es correcto → llama a auth_login() para iniciar sesión permanente
             y redirige al dashboard.
             Si es incorrecto → muestra mensaje de error.
    """
    # Recuperar el ID del usuario que está en proceso de login 2FA
    user_id = request.session.get('pre_2fa_user_id')
    if not user_id:
        # Sin este dato en sesión, no hay contexto de 2FA válido
        return redirect('index')

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return redirect('index')

    if request.method == 'POST':
        entered_code = request.POST.get('otp_code')

        # ── Validar que el OTP existe ────────────────────────────────────────
        if not hasattr(user, 'profile') or not user.profile.otp_code or not user.profile.otp_created_at:
            messages.error(request, 'No hay código pendiente de verificación.')
            return redirect('index')

        # ── Verificar expiración: máximo 5 minutos desde la generación ───────
        if timezone.now() > user.profile.otp_created_at + timedelta(minutes=5):
            messages.error(request, 'El código de verificación ha expirado. Por favor, inicia sesión de nuevo.')
            # Limpiar el OTP ya expirado para evitar reutilización
            user.profile.otp_code = None
            user.profile.save()
            try:
                del request.session['pre_2fa_user_id']
            except KeyError:
                pass
            return redirect('index')

        # ── Comparar el código ingresado con el almacenado ───────────────────
        if entered_code == user.profile.otp_code:
            # ✅ Código correcto: limpiar OTP y establecer sesión permanente
            user.profile.otp_code = None
            user.profile.save()
            try:
                del request.session['pre_2fa_user_id']
            except KeyError:
                pass

            # Aquí sí se hace el login definitivo en Django
            auth_login(request, user)
            messages.success(request, f'¡Bienvenido de vuelta, {user.first_name or user.username}!', extra_tags='success')
            return redirect('dashboard')
        else:
            messages.error(request, 'El código de verificación es incorrecto.')

    # ── Enmascarar el correo para mostrar en el template (ej: r****l@gmail.com) ──
    email = user.email
    if '@' in email:
        username_part, domain_part = email.split('@')
        if len(username_part) > 2:
            obfuscated_email = f"{username_part[0]}{'*' * (len(username_part)-2)}{username_part[-1]}@{domain_part}"
        else:
            obfuscated_email = f"{username_part[0]}***@{domain_part}"
    else:
        obfuscated_email = "***"

    return render(request, 'verify_2fa.html', {'email': obfuscated_email})


# ============================================================
# 2. MÓDULO DE CATÁLOGO DE MODELOS ML
# ============================================================

@login_required(login_url='index')
def modelos_lista(request):
    """
    Lista/Catálogo de todos los modelos ML registrados.
    Las categorías para el filtro se obtienen dinámicamente de la BD.
    La búsqueda por texto filtra nombre, nombre_estudio y descripción.
    """
    from app.models import ModeloML, Categoria

    query = request.GET.get('q', '')
    categoria = request.GET.get('categoria', '')

    modelos = ModeloML.objects.all().order_by('-fecha_creacion')

    if query:
        modelos = (
            modelos.filter(nombre__icontains=query) |
            modelos.filter(nombre_estudio__icontains=query) |
            modelos.filter(descripcion__icontains=query)
        )
    if categoria:
        modelos = modelos.filter(categoria__iexact=categoria)

    # Obtener las categorías que realmente existen en modelos registrados
    categorias_en_uso = (
        ModeloML.objects.values_list('categoria', flat=True)
        .distinct()
        .order_by('categoria')
    )

    return render(request, 'modelos_lista.html', {
        'modelos': modelos,
        'categorias': categorias_en_uso,
        'query': query,
        'categoria_activa': categoria,
    })


@login_required(login_url='index')
def modelo_crear(request):
    """
    Registrar un nuevo modelo ML en el catálogo.

    Flujo:
      GET  → Muestra el formulario vacío (modelo_form.html) con los choices de
             categoría y estado cargados desde el modelo.
      POST → Extrae todos los campos del formulario, aplica validaciones y crea
             el registro en base de datos.

    Campos del formulario:
      Básicos:   nombre, nombre_estudio, descripcion, categoria, estado, precision.
      Archivos:  archivo_modelo (.onnx/.pkl), documento_estudio (PDF).
      Inferencia: img_width, img_height, es_rgb, invertir_colores, nombres_clases.

    Validaciones:
      - Todos los campos básicos y el archivo del modelo son obligatorios.
      - El archivo del modelo debe ser .onnx o .pkl (validación de extensión).
    """
    from app.models import ModeloML

    # Solo los administradores pueden subir/registrar modelos
    if not es_admin(request.user):
        messages.error(request, 'No tienes permisos para agregar modelos. Contacta a un administrador.')
        return redirect('modelos_lista')

    if request.method == 'POST':
        # ── Extraer datos del formulario ─────────────────────────────────────
        nombre = request.POST.get('nombre')
        nombre_estudio = request.POST.get('nombre_estudio')
        descripcion = request.POST.get('descripcion')
        categoria = request.POST.get('categoria')
        estado = request.POST.get('estado', 'activo')
        # precision es opcional; si viene vacío se guarda como None (NULL en BD)
        precision = request.POST.get('precision') or None
        # Archivos subidos (request.FILES en lugar de request.POST)
        archivo_modelo = request.FILES.get('archivo_modelo')
        documento_estudio = request.FILES.get('documento_estudio')

        # ── Metadatos de inferencia ──────────────────────────────────────────
        img_width = request.POST.get('img_width', 28)
        img_height = request.POST.get('img_height', 28)
        # Los checkboxes HTML envían 'on' si marcados, nada si no marcados
        es_rgb = request.POST.get('es_rgb') == 'on'
        invertir_colores = request.POST.get('invertir_colores') == 'on'
        # Nombres de clases separados por coma: "Sano, Enfermo, Muerto"
        nombres_clases = request.POST.get('nombres_clases', '')

        # ── Validar campos obligatorios ──────────────────────────────────────
        if not nombre or not nombre_estudio or not descripcion or not categoria or not archivo_modelo:
            messages.error(request, 'Por favor completa todos los campos obligatorios.')
            return render(request, 'modelo_form.html', {
                'categorias': ModeloML.CATEGORIA_CHOICES,
                'estados': ModeloML.ESTADO_CHOICES,
            })

        # ── Validar extensión del archivo de modelo ──────────────────────────
        if not (archivo_modelo.name.endswith('.onnx') or archivo_modelo.name.endswith('.pkl')):
            messages.error(request, 'Error: El archivo del modelo debe ser estrictamente formato .onnx o .pkl')
            return render(request, 'modelo_form.html', {
                'categorias': ModeloML.CATEGORIA_CHOICES,
                'estados': ModeloML.ESTADO_CHOICES,
            })

        # ── Crear el registro en base de datos ───────────────────────────────
        try:
            modelo = ModeloML.objects.create(
                nombre=nombre,
                nombre_estudio=nombre_estudio,
                descripcion=descripcion,
                categoria=categoria,
                estado=estado,
                precision=precision,
                archivo_modelo=archivo_modelo,
                documento_estudio=documento_estudio,
                # Convertir a entero con fallback a 28 en caso de valor vacío
                img_width=int(img_width) if img_width else 28,
                img_height=int(img_height) if img_height else 28,
                es_rgb=es_rgb,
                invertir_colores=invertir_colores,
                nombres_clases=nombres_clases,
                usuario=request.user,   # Asociar con el usuario que lo registra
            )
            messages.success(request, f'¡Modelo "{modelo.nombre}" registrado exitosamente!')
            return redirect('modelos_lista')
        except Exception as e:
            messages.error(request, f'Error al guardar el modelo: {str(e)}')

    # GET: renderizar formulario
    return render(request, 'modelo_form.html', {
        'categorias': __import__('app.models', fromlist=['Categoria']).Categoria.objects.all(),
        'estados': ModeloML.ESTADO_CHOICES,
    })


@login_required(login_url='index')
def modelo_detalle(request, pk):
    """
    Vista de detalle de un modelo ML específico.

    Parámetros:
      pk (int): Clave primaria del modelo en la base de datos.

    Usa get_object_or_404 para devolver 404 automáticamente si el ID no existe.
    Renderiza modelo_detalle.html con el objeto completo del modelo.
    """
    from app.models import ModeloML
    modelo = get_object_or_404(ModeloML, pk=pk)
    return render(request, 'modelo_detalle.html', {
        'modelo': modelo,
        'es_admin': es_admin(request.user),
    })


@login_required(login_url='index')
def modelo_editar(request, pk):
    """
    Editar los datos de un modelo ML existente.

    Solo disponible para usuarios con rol 'admin'.
    GET  → Muestra el formulario pre-poblado con los datos actuales.
    POST → Valida y guarda los cambios. Si se sube un nuevo archivo
            reemplaza el anterior; si se deja en blanco, conserva el original.
    """
    from app.models import ModeloML, Categoria

    if not es_admin(request.user):
        messages.error(request, 'No tienes permisos para editar modelos.')
        return redirect('modelos_lista')

    modelo = get_object_or_404(ModeloML, pk=pk)

    if request.method == 'POST':
        nombre        = request.POST.get('nombre')
        nombre_estudio= request.POST.get('nombre_estudio')
        descripcion   = request.POST.get('descripcion')
        categoria_sel = request.POST.get('categoria')
        categoria_nueva = request.POST.get('categoria_nueva', '').strip()
        estado        = request.POST.get('estado', 'activo')
        precision     = request.POST.get('precision') or None
        img_width     = request.POST.get('img_width', 28)
        img_height    = request.POST.get('img_height', 28)
        es_rgb_val    = request.POST.get('es_rgb') == 'on'
        invertir      = request.POST.get('invertir_colores') == 'on'
        nombres_clases= request.POST.get('nombres_clases', '')

        # Resolver categoría, igual que en modelo_crear
        if categoria_sel == 'otro':
            if not categoria_nueva:
                messages.error(request, 'Debes escribir el nombre de la nueva categoría.')
            else:
                cat_obj, _ = Categoria.objects.get_or_create(nombre=categoria_nueva.lower())
                categoria_final = cat_obj.nombre
        else:
            categoria_final = categoria_sel
            Categoria.objects.get_or_create(nombre=categoria_final)

        if not nombre or not nombre_estudio or not descripcion or not categoria_final:
            messages.error(request, 'Por favor completa todos los campos obligatorios.')
        else:
            modelo.nombre          = nombre
            modelo.nombre_estudio  = nombre_estudio
            modelo.descripcion     = descripcion
            modelo.categoria       = categoria_final
            modelo.estado          = estado
            modelo.precision       = precision
            modelo.img_width       = int(img_width) if img_width else 28
            modelo.img_height      = int(img_height) if img_height else 28
            modelo.es_rgb          = es_rgb_val
            modelo.invertir_colores= invertir
            modelo.nombres_clases  = nombres_clases

            nuevo_archivo = request.FILES.get('archivo_modelo')
            nuevo_doc     = request.FILES.get('documento_estudio')
            if nuevo_archivo:
                modelo.archivo_modelo = nuevo_archivo
            if nuevo_doc:
                modelo.documento_estudio = nuevo_doc

            modelo.save()
            messages.success(request, f'Modelo "{modelo.nombre}" actualizado correctamente.')
            return redirect('modelo_detalle', pk=pk)

    return render(request, 'modelo_form.html', {
        'categorias': Categoria.objects.all(),
        'estados'   : ModeloML.ESTADO_CHOICES,
        'modelo'    : modelo,
        'modo_editar': True,
    })


@login_required(login_url='index')
def modelo_eliminar(request, pk):
    """
    Eliminar un modelo ML del catálogo.

    Solo acepta POST (el botón de confirmación del modal envía el form).
    Solo disponible para usuarios con rol 'admin'.
    Después de eliminar, redirige a la lista de modelos con un mensaje de éxito.
    Las señales de post_delete en models.py se encargan de borrar los archivos
    del almacenamiento (Azure/local) automáticamente.
    """
    from app.models import ModeloML

    if not es_admin(request.user):
        messages.error(request, 'No tienes permisos para eliminar modelos.')
        return redirect('modelos_lista')

    modelo = get_object_or_404(ModeloML, pk=pk)

    if request.method == 'POST':
        nombre = modelo.nombre
        modelo.delete()
        messages.success(request, f'Modelo "{nombre}" eliminado correctamente.')
        return redirect('modelos_lista')

    # Si alguien intenta GET, redirigir al detalle
    return redirect('modelo_detalle', pk=pk)



@login_required(login_url='index')
def modelo_ejecutar(request, pk):
    """
    Motor de inferencia en línea usando ONNX Runtime.

    Permite al usuario subir una imagen, preprocesarla y obtener la predicción
    del modelo ONNX almacenado en la base de datos.

    Parámetros:
      pk (int): Clave primaria del modelo a ejecutar.

    Flujo completo (POST):
      1. Verificar que el modelo no esté inactivo.
      2. Leer la imagen subida con Pillow.
      3. Preprocesar según la configuración del modelo:
           - Convertir a RGB o Grayscale.
           - Invertir colores si se requiere (ej: dígitos MNIST fondo blanco).
           - Redimensionar a las dimensiones esperadas (img_width × img_height).
           - Normalizar píxeles al rango [0, 1].
      4. Adaptar la forma (shape) del tensor al formato que espera el ONNX:
           - Rank 4 → imagen 2D con batch y canales (NCHW o NHWC detectado automático).
           - Rank 3 → imagen 2D sin canal explícito.
           - Rank 2 → vector aplanado (MLP tabular).
      5. Ejecutar la sesión ONNX (session.run()).
      6. Postprocesar resultados:
           - Argmax para obtener la clase predicha.
           - Softmax manual para convertir logits crudos a probabilidades (%).
           - Mapear el índice de clase a su nombre humano (si nombres_clases está configurado).
      7. Devolver resultado al template: {'clase': ..., 'confianza': ...}.

    Variables de contexto del template:
      modelo:    Objeto ModeloML con toda la info del modelo.
      resultado: Dict {'clase': str, 'confianza': float} — None si aún no se ejecutó.
      error:     Mensaje de error en cadena — None si no hubo error.
    """
    from app.models import ModeloML
    import os
    from django.conf import settings

    # Obtener el modelo o retornar 404 si no existe
    modelo = get_object_or_404(ModeloML, pk=pk)

    # ── Guardia: modelos inactivos no pueden ejecutarse ───────────────────────
    if modelo.estado == 'inactivo':
        messages.error(request, 'Este modelo está inactivo. No se pueden realizar inferencias.')
        return redirect('modelo_detalle', pk=modelo.pk)

    resultado = None   # Resultado de la predicción (diccionario)
    error = None       # Mensaje de error para mostrar en el template

    if request.method == 'POST':
        # ── Validar que se subió una imagen ──────────────────────────────────
        if 'imagen' not in request.FILES:
            error = "Debes subir una imagen para ejecutar la inferencia."
        else:
            imagen = request.FILES['imagen']
            try:
                # Importar librerías pesadas solo cuando se necesitan (no al arrancar el servidor)
                import onnxruntime as ort
                import numpy as np
                from PIL import Image, ImageOps

                # ── Paso 1: Abrir imagen con Pillow ──────────────────────────
                img = Image.open(imagen)

                # ── Paso 2: Convertir espacio de color ────────────────────────
                # 'RGB'  → 3 canales (rojo, verde, azul)
                # 'L'    → 1 canal (escala de grises)
                if modelo.es_rgb:
                    img = img.convert('RGB')
                else:
                    img = img.convert('L')

                # ── Paso 3: Invertir colores si el modelo lo requiere ─────────
                # Útil para modelos entrenados con MNIST donde los dígitos
                # son blancos sobre fondo negro, pero la foto capturada suele
                # tener fondo claro y trazos oscuros.
                if modelo.invertir_colores:
                    img = ImageOps.invert(img)

                # ── Paso 4: Redimensionar al tamaño que espera el modelo ──────
                # LANCZOS es un filtro de alta calidad para reducción de imágenes
                img = img.resize((modelo.img_width, modelo.img_height), Image.Resampling.LANCZOS)

                # ── Paso 5: Convertir a NumPy y normalizar [0, 255] → [0.0, 1.0] ──
                img_data = np.array(img).astype('float32') / 255.0

                # ── Paso 6: Resolver la ruta del archivo ONNX ─────────────────
                import tempfile
                import urllib.request

                file_url = modelo.archivo_modelo.url

                with tempfile.NamedTemporaryFile(delete=False, suffix=".onnx") as tmp_file:
                    if file_url.startswith('http'):
                        # El archivo está en almacenamiento remoto (ej: S3, CDN)
                        urllib.request.urlretrieve(file_url, tmp_file.name)
                        onnx_path = tmp_file.name
                    else:
                        # El archivo está en MEDIA_ROOT local del servidor
                        local_path = file_url.replace(settings.MEDIA_URL, '')
                        onnx_path = os.path.join(settings.MEDIA_ROOT, local_path)

                # ── Paso 7: Crear sesión de ONNX Runtime ──────────────────────
                # InferenceSession carga el modelo ONNX en memoria y lo optimiza
                session = ort.InferenceSession(onnx_path)

                # Obtener metadatos del nodo de entrada del grafo ONNX
                input_meta = session.get_inputs()[0]
                input_name = input_meta.name           # Nombre del tensor de entrada (ej: 'input')
                input_shape = input_meta.shape         # Forma esperada (ej: [None, 3, 224, 224])

                # ── Paso 8: Adaptar el tensor de imagen al shape del modelo ───
                rank = len(input_shape)           # Número de dimensiones del tensor
                C = 3 if modelo.es_rgb else 1    # Número de canales (3=RGB, 1=Grayscale)

                if rank == 4:
                    # Caso más común: imagen con batch y canal explícito
                    # Pillow devuelve (H, W, C) para RGB y (H, W) para Grayscale
                    if not modelo.es_rgb:
                        # Añadir dimensión de canal: (H, W) → (H, W, 1)
                        img_data = np.expand_dims(img_data, axis=-1)

                    # Autodetectar si el modelo espera NCHW o NHWC comparando shapes
                    is_channels_first = True  # Asumimos NCHW por defecto (PyTorch/ONNX estándar)

                    if input_shape[3] == C or str(input_shape[3]) == str(C):
                        # El 4° elemento es el número de canales → el modelo espera NHWC (TensorFlow style)
                        is_channels_first = False
                    elif input_shape[1] == C or str(input_shape[1]) == str(C):
                        # El 2° elemento es el número de canales → el modelo espera NCHW (PyTorch style)
                        is_channels_first = True

                    if is_channels_first:
                        # Convertir (H, W, C) → (C, H, W) → (1, C, H, W) con batch
                        img_data = np.transpose(img_data, (2, 0, 1))
                        input_data = img_data.reshape(1, C, modelo.img_height, modelo.img_width)
                    else:
                        # Mantener (H, W, C) y añadir batch: → (1, H, W, C)
                        input_data = img_data.reshape(1, modelo.img_height, modelo.img_width, C)

                elif rank == 3:
                    # El modelo espera [Batch, Height, Width] sin canal explícito
                    input_data = img_data.reshape(1, modelo.img_height, modelo.img_width)
                else:
                    # Fallback: el modelo es un MLP que espera un vector 1D
                    # Aplanar todos los píxeles en un solo vector
                    flat_size = modelo.img_height * modelo.img_width * (3 if modelo.es_rgb else 1)
                    input_data = img_data.reshape(1, flat_size)

                # ── Paso 9: Ejecutar el modelo ONNX ───────────────────────────
                # session.run(None, {input_name: input_data}) devuelve lista de tensores
                result = session.run(None, {input_name: input_data})

                # ── Paso 10: Postprocesar la salida ───────────────────────────
                # result[0] contiene el tensor de salida principal
                # Puede ser logits crudos (antes de softmax) o probabilidades
                log_probs = result[0]

                # Argmax: encontrar el índice de la clase con mayor puntuación
                clase_predicha = np.argmax(log_probs)

                # Softmax manual para convertir logits a probabilidades reales
                # Se resta el máximo antes de exp() para estabilidad numérica
                exp_vals = np.exp(log_probs - np.max(log_probs))
                softmax_probs = exp_vals / np.sum(exp_vals)
                confianza_pct = float(softmax_probs[0][clase_predicha]) * 100

                # ── Paso 11: Mapear índice numérico a nombre de clase ─────────
                # Por defecto se muestra el número (0, 1, 2...)
                clase_nombre = str(clase_predicha)
                if modelo.nombres_clases:
                    # Parsear la cadena "Sano, Enfermo, Muerto" a lista ['Sano', 'Enfermo', 'Muerto']
                    nombres = [n.strip() for n in modelo.nombres_clases.split(',')]
                    if 0 <= clase_predicha < len(nombres):
                        clase_nombre = nombres[clase_predicha]

                # Empaquetar el resultado final para el template
                resultado = {
                    'clase': clase_nombre,
                    'confianza': round(confianza_pct, 2)
                }

                # ── Guardar en historial de ejecuciones ───────────────────────
                # La imagen original se sube al almacenamiento (Azure/local)
                # junto con la ubicación y el resultado textual.
                try:
                    from app.models import HistorialEjecucion
                    ubicacion = request.POST.get('ubicacion', '').strip()
                    # Rewind the file to read it again for storage
                    imagen.seek(0)
                    HistorialEjecucion.objects.create(
                        usuario=request.user,
                        modelo=modelo,
                        imagen=imagen,
                        ubicacion=ubicacion,
                        resultado=f"{clase_nombre} ({round(confianza_pct, 2)}%)"
                    )
                except Exception as hist_err:
                    # Guardar historial es no-bloqueante: si falla, no interrumpimos la inferencia
                    pass

                # ── Limpieza: borrar archivo temporal si se descargó ──────────
                if file_url.startswith('http') and os.path.exists(onnx_path):
                    os.remove(onnx_path)

            except Exception as e:
                error = f"Error durante la inferencia: {str(e)}"

    return render(request, 'modelo_ejecutar.html', {
        'modelo': modelo,
        'resultado': resultado,
        'error': error
    })


# ============================================================
# 3. PÁGINA 404 PERSONALIZADA
# ============================================================

def pagina_404(request, exception):
    """
    Handler personalizado para errores 404 (página no encontrada).

    Django llama automáticamente a esta función cuando ninguna URL
    coincide con la ruta solicitada, siempre que DEBUG=False y
    handler404 esté configurado en urls.py del proyecto.
    Renderiza el template 404.html con el código HTTP 404.
    """
    return render(request, '404.html', status=404)


def ruta_no_encontrada(request):
    """
    Vista catch-all: captura cualquier URL no definida en urlpatterns.
    Renderiza la plantilla 404.html con código de estado 404.
    """
    return render(request, '404.html', status=404)


# ============================================================
# 4. HISTORIAL DE EJECUCIONES
# ============================================================

@login_required(login_url='index')
def historial_lista(request):
    """
    Historial unificado de ejecuciones del usuario (o de todos, si es admin).

    Reúne los dos tipos de ejecución que maneja la plataforma:
      - Modelos ML (clasificación)  -> HistorialEjecucion
      - Detección YOLO              -> DeteccionYOLO

    Se pueden filtrar por categoría con ?categoria=ml | yolo | todas.
    Como son dos modelos distintos, cada registro se normaliza a un
    diccionario con las mismas llaves para poder mostrarlos en una
    sola tabla y paginarlos juntos.
    """
    from app.models import HistorialEjecucion, DeteccionYOLO
    from django.core.paginator import Paginator
    from django.urls import reverse

    admin = es_admin(request.user)
    categoria = request.GET.get('categoria', 'todas')
    if categoria not in ('todas', 'ml', 'yolo'):
        categoria = 'todas'

    filas = []

    # ── Ejecuciones de modelos ML (clasificación) ───────────────────────
    if categoria in ('todas', 'ml'):
        qs_ml = HistorialEjecucion.objects.select_related('usuario', 'modelo')
        if not admin:
            qs_ml = qs_ml.filter(usuario=request.user)
        for h in qs_ml:
            filas.append({
                'tipo': 'ml',
                'tipo_label': 'Modelo ML',
                'imagen_url': h.imagen.url if h.imagen else '',
                'usuario': h.usuario.username if h.usuario else '—',
                'modelo_nombre': h.modelo.nombre if h.modelo else None,
                'modelo_sub': h.modelo.categoria.capitalize() if h.modelo and h.modelo.categoria else '',
                'resultado': h.resultado,
                'ubicacion': h.ubicacion,
                'fecha': h.fecha_ejecucion,
                'url_ver': reverse('historial_detalle', args=[h.pk]),
                'url_eliminar': reverse('historial_eliminar', args=[h.pk]),
            })

    # ── Detecciones con YOLO (imagen cargada y cámara) ──────────────────
    if categoria in ('todas', 'yolo'):
        qs_yolo = DeteccionYOLO.objects.select_related('usuario', 'modelo')
        if not admin:
            qs_yolo = qs_yolo.filter(usuario=request.user)
        for d in qs_yolo:
            imagen = d.imagen_resultado or d.imagen_original
            filas.append({
                'tipo': 'yolo',
                'tipo_label': f'YOLO · {d.get_origen_display()}',
                'imagen_url': imagen.url if imagen else '',
                'usuario': d.usuario.username if d.usuario else '—',
                'modelo_nombre': d.modelo.nombre if d.modelo else None,
                'modelo_sub': 'Detección de objetos',
                'resultado': d.resumen or 'Sin detecciones',
                'ubicacion': '',
                'fecha': d.fecha_ejecucion,
                'url_ver': reverse('yolo_deteccion_detalle', args=[d.pk]),
                'url_eliminar': reverse('yolo_deteccion_eliminar', args=[d.pk]),
            })

    # Más recientes primero, mezclando los dos tipos
    filas.sort(key=lambda f: f['fecha'], reverse=True)

    per_page = int(request.GET.get('per_page', 10))
    if per_page not in [5, 10, 25]:
        per_page = 10

    paginator = Paginator(filas, per_page)
    page_obj = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'historial_lista.html', {
        'page_obj': page_obj,
        'per_page': per_page,
        'total': len(filas),
        'categoria': categoria,
        'es_admin': admin,
    })


@login_required(login_url='index')
def historial_detalle(request, pk):
    """
    Muestra toda la información de una ejecución en detalle:
    imagen completa, resultado, ubicación, modelo y fecha.
    Los usuarios solo pueden ver las suyas; el admin puede ver cualquiera.
    """
    from app.models import HistorialEjecucion

    historial = get_object_or_404(HistorialEjecucion, pk=pk)

    # Verificar que el user sólo accede a lo suyo (admin puede ver todo)
    if not es_admin(request.user) and historial.usuario != request.user:
        messages.error(request, 'No tienes permiso para ver esta ejecución.')
        return redirect('historial_lista')

    return render(request, 'historial_detalle.html', {
        'historial': historial,
        'es_admin': es_admin(request.user),
    })


@login_required(login_url='index')
def historial_eliminar(request, pk):
    """
    Elimina un registro de historial de ejecución.
    El usuario solo puede eliminar los suyos; el admin puede eliminar cualquiera.
    Solo acepta POST para evitar eliminaciones accidentales por GET.
    La señal post_delete del modelo borra la imagen del almacenamiento automáticamente.
    """
    from app.models import HistorialEjecucion

    historial = get_object_or_404(HistorialEjecucion, pk=pk)

    if not es_admin(request.user) and historial.usuario != request.user:
        messages.error(request, 'No tienes permiso para eliminar esta ejecución.')
        return redirect('historial_lista')

    if request.method == 'POST':
        historial.delete()
        messages.success(request, 'Ejecución eliminada del historial correctamente.')
        return redirect('historial_lista')

    return redirect('historial_detalle', pk=pk)

# ============================================================
# 5. MÓDULO YOLO — DETECCIÓN DE OBJETOS
# ============================================================

@login_required(login_url='index')
def yolo_lista(request):
    """Catálogo de modelos YOLO registrados en la plataforma."""
    from app.models import ModeloYOLO

    query = request.GET.get('q', '')
    modelos = ModeloYOLO.objects.all()

    if query:
        modelos = (
            modelos.filter(nombre__icontains=query) |
            modelos.filter(descripcion__icontains=query)
        )

    return render(request, 'yolo_lista.html', {
        'modelos': modelos,
        'query': query,
        'es_admin': es_admin(request.user),
    })


@login_required(login_url='index')
def yolo_crear(request):
    """Registrar un nuevo modelo YOLO (.onnx). Solo administradores."""
    from app.models import ModeloYOLO

    if not es_admin(request.user):
        messages.error(request, 'No tienes permisos para agregar modelos YOLO.')
        return redirect('yolo_lista')

    if request.method == 'POST':
        nombre = request.POST.get('nombre')
        descripcion = request.POST.get('descripcion')
        estado = request.POST.get('estado', 'activo')
        archivo_modelo = request.FILES.get('archivo_modelo')
        tamano_entrada = request.POST.get('tamano_entrada') or 640
        umbral_confianza = request.POST.get('umbral_confianza') or 0.4
        umbral_iou = request.POST.get('umbral_iou') or 0.45
        nombres_clases = request.POST.get('nombres_clases', '')

        if not nombre or not descripcion or not archivo_modelo:
            messages.error(request, 'Por favor completa todos los campos obligatorios.')
            return render(request, 'yolo_form.html', {'estados': ModeloYOLO.ESTADO_CHOICES})

        if not archivo_modelo.name.endswith('.onnx'):
            messages.error(request, 'El modelo YOLO debe estar en formato .onnx')
            return render(request, 'yolo_form.html', {'estados': ModeloYOLO.ESTADO_CHOICES})

        try:
            modelo = ModeloYOLO.objects.create(
                nombre=nombre,
                descripcion=descripcion,
                estado=estado,
                archivo_modelo=archivo_modelo,
                tamano_entrada=int(tamano_entrada),
                umbral_confianza=float(umbral_confianza),
                umbral_iou=float(umbral_iou),
                nombres_clases=nombres_clases,
                usuario=request.user,
            )
            messages.success(request, f'¡Modelo YOLO "{modelo.nombre}" registrado exitosamente!')
            return redirect('yolo_lista')
        except Exception as e:
            messages.error(request, f'Error al guardar el modelo: {str(e)}')

    return render(request, 'yolo_form.html', {'estados': ModeloYOLO.ESTADO_CHOICES})


@login_required(login_url='index')
def yolo_detalle(request, pk):
    """
    Ficha completa de un modelo YOLO: sus parámetros de inferencia,
    el archivo cargado y las últimas detecciones hechas con él.
    """
    from app.models import ModeloYOLO, DeteccionYOLO

    modelo = get_object_or_404(ModeloYOLO, pk=pk)

    detecciones = DeteccionYOLO.objects.filter(modelo=modelo).select_related('usuario')[:8]
    total_detecciones = DeteccionYOLO.objects.filter(modelo=modelo).count()

    return render(request, 'yolo_detalle.html', {
        'modelo': modelo,
        'detecciones': detecciones,
        'total_detecciones': total_detecciones,
        'clases': modelo.lista_clases(),
        'es_admin': es_admin(request.user),
    })


@login_required(login_url='index')
def yolo_editar(request, pk):
    """
    Editar un modelo YOLO ya registrado. Solo administradores.

    Permite cambiar nombre, descripción, estado y los parámetros de
    inferencia (tamaño de entrada, umbrales y nombres de clases).
    El archivo .onnx es opcional: si no se sube uno nuevo, se conserva
    el que ya estaba.
    """
    from app.models import ModeloYOLO

    if not es_admin(request.user):
        messages.error(request, 'No tienes permisos para editar modelos YOLO.')
        return redirect('yolo_lista')

    modelo = get_object_or_404(ModeloYOLO, pk=pk)

    if request.method == 'POST':
        nombre = request.POST.get('nombre')
        descripcion = request.POST.get('descripcion')
        estado = request.POST.get('estado', modelo.estado)
        archivo_modelo = request.FILES.get('archivo_modelo')
        tamano_entrada = request.POST.get('tamano_entrada') or modelo.tamano_entrada
        umbral_confianza = request.POST.get('umbral_confianza') or modelo.umbral_confianza
        umbral_iou = request.POST.get('umbral_iou') or modelo.umbral_iou
        nombres_clases = request.POST.get('nombres_clases', '')

        if not nombre or not descripcion:
            messages.error(request, 'El nombre y la descripción son obligatorios.')
            return render(request, 'yolo_form.html', {
                'modelo': modelo,
                'estados': ModeloYOLO.ESTADO_CHOICES,
            })

        if archivo_modelo and not archivo_modelo.name.endswith('.onnx'):
            messages.error(request, 'El modelo YOLO debe estar en formato .onnx')
            return render(request, 'yolo_form.html', {
                'modelo': modelo,
                'estados': ModeloYOLO.ESTADO_CHOICES,
            })

        try:
            modelo.nombre = nombre
            modelo.descripcion = descripcion
            modelo.estado = estado
            modelo.tamano_entrada = int(tamano_entrada)
            modelo.umbral_confianza = float(umbral_confianza)
            modelo.umbral_iou = float(umbral_iou)
            modelo.nombres_clases = nombres_clases
            if archivo_modelo:
                modelo.archivo_modelo = archivo_modelo
            modelo.save()
            messages.success(request, f'Modelo YOLO "{modelo.nombre}" actualizado correctamente.')
            return redirect('yolo_detalle', pk=modelo.pk)
        except Exception as e:
            messages.error(request, f'Error al actualizar el modelo: {str(e)}')

    return render(request, 'yolo_form.html', {
        'modelo': modelo,
        'estados': ModeloYOLO.ESTADO_CHOICES,
    })


@login_required(login_url='index')
def yolo_eliminar(request, pk):
    """Eliminar un modelo YOLO del catálogo. Solo administradores."""
    from app.models import ModeloYOLO

    if not es_admin(request.user):
        messages.error(request, 'No tienes permisos para eliminar modelos YOLO.')
        return redirect('yolo_lista')

    modelo = get_object_or_404(ModeloYOLO, pk=pk)

    if request.method == 'POST':
        nombre = modelo.nombre
        modelo.delete()
        messages.success(request, f'Modelo YOLO "{nombre}" eliminado correctamente.')

    return redirect('yolo_lista')


@login_required(login_url='index')
def yolo_ejecutar(request, pk):
    """
    Motor de detección de objetos con YOLO (ONNX Runtime).

    Flujo completo (POST):
      1. Abrir la imagen subida y guardar sus dimensiones originales.
      2. Preprocesar: redimensionar a tamano_entrada, normalizar, HWC -> CHW.
      3. Ejecutar la sesión ONNX -> salida cruda (1, 84, 8400).
      4. Decodificar: filtrar por confianza y convertir coordenadas.
      5. Aplicar Non-Max Suppression para eliminar cajas duplicadas.
      6. Dibujar las cajas delimitadoras sobre la imagen original.
      7. Guardar en el historial y devolver el resultado al template.
    """
    from app.models import ModeloYOLO, DeteccionYOLO
    import os
    from django.conf import settings

    modelo = get_object_or_404(ModeloYOLO, pk=pk)

    if modelo.estado == 'inactivo':
        messages.error(request, 'Este modelo YOLO está inactivo. No se pueden realizar detecciones.')
        return redirect('yolo_lista')

    resultado = None
    error = None

    if request.method == 'POST':
        if 'imagen' not in request.FILES:
            error = "Debes subir una imagen para ejecutar la detección."
        else:
            imagen = request.FILES['imagen']
            onnx_path = None
            es_temporal = False
            try:
                import onnxruntime as ort
                import numpy as np
                from PIL import Image

                # ── Paso 0: Validar tipo y tamaño antes de cargar nada ───────
                TIPOS_PERMITIDOS = ('image/jpeg', 'image/png', 'image/webp')
                PESO_MAXIMO_MB = 10
                if imagen.content_type not in TIPOS_PERMITIDOS:
                    raise ValueError("Formato no soportado. Sube una imagen JPG, PNG o WEBP.")
                if imagen.size > PESO_MAXIMO_MB * 1024 * 1024:
                    raise ValueError(f"La imagen pesa demasiado (máximo {PESO_MAXIMO_MB} MB).")

                # ── Paso 1: Abrir imagen y guardar dimensiones originales ────
                try:
                    img = Image.open(imagen).convert('RGB')
                except Exception:
                    raise ValueError("El archivo no es una imagen válida o está dañado.")
                ancho_orig, alto_orig = img.size
                img_para_dibujar = img.copy()

                # ── Paso 2: Preprocesar para YOLO ────────────────────────────
                tam = modelo.tamano_entrada
                img_redim = img.resize((tam, tam))
                entrada = np.array(img_redim).astype('float32') / 255.0
                entrada = entrada.transpose(2, 0, 1)        # HWC -> CHW
                entrada = np.expand_dims(entrada, axis=0)   # (1, 3, tam, tam)

                # ── Paso 3: Resolver la ruta del archivo .onnx ───────────────
                file_url = modelo.archivo_modelo.url
                if file_url.startswith('http'):
                    import tempfile, urllib.request
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".onnx") as tmp_file:
                        urllib.request.urlretrieve(file_url, tmp_file.name)
                        onnx_path = tmp_file.name
                        es_temporal = True
                else:
                    local_path = file_url.replace(settings.MEDIA_URL, '')
                    onnx_path = os.path.join(settings.MEDIA_ROOT, local_path)

                # ── Paso 4: Ejecutar la inferencia ───────────────────────────
                session = ort.InferenceSession(onnx_path)
                input_name = session.get_inputs()[0].name
                salida = session.run(None, {input_name: entrada})[0]

                # ── Paso 5: Decodificar la salida cruda + NMS ────────────────
                cajas, confianzas, clases_ids = _decodificar_yolo(
                    salida, ancho_orig, alto_orig, tam, modelo.umbral_confianza
                )
                indices = _nms_yolo(cajas, confianzas, modelo.umbral_iou)

                # ── Paso 6: Nombres de clases (configurados o COCO) ──────────
                nombres = modelo.lista_clases() or CLASES_COCO

                # ── Paso 7: Dibujar las cajas sobre la imagen original ───────
                img_resultado = _dibujar_detecciones_yolo(
                    img_para_dibujar, cajas, confianzas, clases_ids, indices, nombres
                )

                # ── Paso 8: Armar la lista de detecciones ────────────────────
                detecciones = []
                for i in indices:
                    nombre_clase = nombres[clases_ids[i]] if clases_ids[i] < len(nombres) else str(clases_ids[i])
                    detecciones.append({
                        'clase': nombre_clase,
                        'confianza': round(confianzas[i] * 100, 2)
                    })
                detecciones.sort(key=lambda d: d['confianza'], reverse=True)

                # ── Paso 9: Guardar en el historial ──────────────────────────
                from io import BytesIO
                from django.core.files.base import ContentFile
                import uuid

                buffer = BytesIO()
                img_resultado.save(buffer, format='JPEG', quality=90)

                resumen = ', '.join(
                    f"{d['clase']} ({d['confianza']}%)" for d in detecciones
                ) or 'Sin detecciones'

                imagen.seek(0)
                deteccion = DeteccionYOLO(
                    usuario=request.user,
                    modelo=modelo,
                    imagen_original=imagen,
                    total_detecciones=len(detecciones),
                    resumen=resumen,
                )
                deteccion.imagen_resultado.save(
                    f"deteccion_{uuid.uuid4().hex}.jpg",
                    ContentFile(buffer.getvalue()),
                    save=False
                )
                deteccion.save()

                resultado = {
                    'imagen_url': deteccion.imagen_resultado.url,
                    'detecciones': detecciones,
                    'total': len(detecciones),
                    'candidatos': len(cajas),
                }

            except ValueError as e:
                error = str(e)
            except Exception as e:
                error = f"Error durante la detección: {str(e)}"
            finally:
                # Limpiar el archivo temporal si se descargó de un almacenamiento remoto
                if es_temporal and onnx_path and os.path.exists(onnx_path):
                    os.remove(onnx_path)

    historial = DeteccionYOLO.objects.filter(modelo=modelo, usuario=request.user)[:5]

    return render(request, 'yolo_ejecutar.html', {
        'modelo': modelo,
        'resultado': resultado,
        'error': error,
        'historial': historial,
    })

@login_required(login_url='index')
def yolo_camara(request, pk):
    """
    Página de detección en vivo desde la cámara del dispositivo.
    Solo renderiza la plantilla; todo el trabajo lo hacen las dos vistas de abajo.
    """
    from app.models import ModeloYOLO

    modelo = get_object_or_404(ModeloYOLO, pk=pk)

    if modelo.estado == 'inactivo':
        messages.error(request, 'Este modelo YOLO está inactivo.')
        return redirect('yolo_lista')

    return render(request, 'yolo_camara.html', {'modelo': modelo})


def _filtrar_por_clases(res, clases):
    """
    RF12: deja solo las detecciones de las clases que el usuario quiere ver
    (por ejemplo, perros y gatos), sin cambiar el modelo cargado.

    'clases' es la lista de nombres que manda el navegador. Si viene vacía,
    no se filtra nada y se devuelve todo lo que detectó el modelo.
    """
    permitidas = {str(c).strip().lower() for c in (clases or []) if str(c).strip()}
    if not permitidas:
        return res

    nombres = res['nombres']

    def nombre_de(i):
        cid = res['clases_ids'][i]
        return (nombres[cid] if cid < len(nombres) else str(cid)).lower()

    res['indices'] = [i for i in res['indices'] if nombre_de(i) in permitidas]
    res['detecciones'] = [d for d in res['detecciones']
                          if str(d['clase']).lower() in permitidas]
    return res


@login_required(login_url='index')
def yolo_frame(request, pk):
    """
    Recibe un fotograma de la cámara y devuelve las detecciones en JSON.

    El navegador manda la imagen codificada en base64. Acá se decodifica,
    se pasa por el modelo y se devuelven las cajas con sus coordenadas,
    para que el navegador las dibuje encima del video.

    No guarda nada: esto corre varias veces por segundo.
    """
    from app.models import ModeloYOLO
    from django.http import JsonResponse

    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Método no permitido'}, status=405)

    modelo = get_object_or_404(ModeloYOLO, pk=pk)

    if modelo.estado == 'inactivo':
        return JsonResponse({'ok': False, 'error': 'El modelo está inactivo'}, status=400)

    try:
        import base64, json
        from io import BytesIO
        from PIL import Image

        datos = json.loads(request.body)
        imagen_b64 = datos.get('imagen', '')

        # El navegador manda "data:image/jpeg;base64,XXXX" — nos quedamos con XXXX
        if ',' in imagen_b64:
            imagen_b64 = imagen_b64.split(',', 1)[1]

        # Un fotograma de video no debería pesar más de esto; si pesa más,
        # algo anda mal (o alguien está mandando algo que no es un fotograma)
        if len(imagen_b64) > 8 * 1024 * 1024:
            return JsonResponse({'ok': False, 'error': 'Fotograma demasiado pesado'}, status=200)

        img = Image.open(BytesIO(base64.b64decode(imagen_b64))).convert('RGB')

        res = _detectar_en_imagen(modelo, img)
        res = _filtrar_por_clases(res, datos.get('clases'))   # RF12

        return JsonResponse({
            'ok': True,
            'detecciones': res['detecciones'],
            'total': len(res['detecciones']),
            'candidatos': res['candidatos'],
            'ancho': img.size[0],
            'alto': img.size[1],
        })

    except Exception as e:
        # Un error en un fotograma no debe tumbar la sesión de cámara
        return JsonResponse({'ok': False, 'error': str(e)}, status=200)


@login_required(login_url='index')
def yolo_capturar(request, pk):
    """
    Guarda una captura tomada desde la cámara.

    Recibe el fotograma del momento, vuelve a correr la detección sobre él
    (para que lo guardado coincida exactamente con lo que se guarda, no con
    el último fotograma procesado), dibuja las cajas y lo registra en el
    historial igual que una detección sobre imagen cargada.
    """
    from app.models import ModeloYOLO, DeteccionYOLO
    from django.http import JsonResponse

    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'Método no permitido'}, status=405)

    modelo = get_object_or_404(ModeloYOLO, pk=pk)

    try:
        import base64, json, uuid
        from io import BytesIO
        from PIL import Image
        from django.core.files.base import ContentFile

        datos = json.loads(request.body)
        imagen_b64 = datos.get('imagen', '')
        if ',' in imagen_b64:
            imagen_b64 = imagen_b64.split(',', 1)[1]

        if len(imagen_b64) > 12 * 1024 * 1024:
            return JsonResponse({'ok': False, 'error': 'La captura pesa demasiado'}, status=200)

        bytes_imagen = base64.b64decode(imagen_b64)
        img = Image.open(BytesIO(bytes_imagen)).convert('RGB')

        # Volver a detectar sobre este fotograma exacto
        res = _detectar_en_imagen(modelo, img)
        res = _filtrar_por_clases(res, datos.get('clases'))   # RF12

        # Dibujar las cajas sobre la foto capturada
        img_resultado = _dibujar_detecciones_yolo(
            img.copy(), res['cajas'], res['confianzas'],
            res['clases_ids'], res['indices'], res['nombres']
        )

        buffer = BytesIO()
        img_resultado.save(buffer, format='JPEG', quality=90)

        resumen = _resumen_por_clase(res['detecciones'])

        deteccion = DeteccionYOLO(
            usuario=request.user,
            modelo=modelo,
            total_detecciones=len(res['detecciones']),
            resumen=resumen,
            origen='camara',
        )
        # La foto original tal como la tomó la cámara
        deteccion.imagen_original.save(
            f"camara_{uuid.uuid4().hex}.jpg",
            ContentFile(bytes_imagen),
            save=False
        )
        # La misma foto con las cajas dibujadas
        deteccion.imagen_resultado.save(
            f"camara_det_{uuid.uuid4().hex}.jpg",
            ContentFile(buffer.getvalue()),
            save=False
        )
        deteccion.save()

        return JsonResponse({
            'ok': True,
            'id': deteccion.pk,
            'resumen': resumen,
            'total': len(res['detecciones']),
            'detecciones': res['detecciones'],
            'imagen_url': deteccion.imagen_resultado.url,
        })

    except Exception as e:
        return JsonResponse({'ok': False, 'error': str(e)}, status=200)


@login_required(login_url='index')
def yolo_galeria(request):
    """
    Galería de capturas tomadas con la cámara en vivo.

    Muestra únicamente las detecciones con origen='camara' del usuario
    (el admin ve las de todos), paginadas, con la imagen ya dibujada,
    el resumen de objetos y el modelo usado.
    """
    from app.models import DeteccionYOLO
    from django.core.paginator import Paginator

    if es_admin(request.user):
        qs = DeteccionYOLO.objects.select_related('usuario', 'modelo').filter(origen='camara')
    else:
        qs = DeteccionYOLO.objects.select_related('modelo').filter(origen='camara', usuario=request.user)

    per_page = int(request.GET.get('per_page', 12))
    if per_page not in [12, 24, 48]:
        per_page = 12

    paginator = Paginator(qs, per_page)
    page_number = request.GET.get('page', 1)
    page_obj = paginator.get_page(page_number)

    return render(request, 'yolo_galeria.html', {
        'page_obj': page_obj,
        'per_page': per_page,
        'total': qs.count(),
        'es_admin': es_admin(request.user),
    })


@login_required(login_url='index')
def yolo_deteccion_detalle(request, pk):
    """
    Detalle de una detección: la imagen con las cajas en grande,
    el resumen de objetos, el modelo usado y su origen.
    El usuario solo ve las suyas; el admin puede ver cualquiera.
    """
    from app.models import DeteccionYOLO

    deteccion = get_object_or_404(DeteccionYOLO, pk=pk)

    if not es_admin(request.user) and deteccion.usuario != request.user:
        messages.error(request, 'No tienes permiso para ver esta detección.')
        return redirect('yolo_galeria')

    return render(request, 'yolo_deteccion_detalle.html', {
        'deteccion': deteccion,
        'es_admin': es_admin(request.user),
    })


@login_required(login_url='index')
def yolo_deteccion_eliminar(request, pk):
    """
    Elimina una detección desde el historial, sea de imagen o de cámara.
    Solo POST; el dueño o el admin. Vuelve al historial.
    """
    from app.models import DeteccionYOLO

    deteccion = get_object_or_404(DeteccionYOLO, pk=pk)

    if not es_admin(request.user) and deteccion.usuario != request.user:
        messages.error(request, 'No tienes permiso para eliminar esta detección.')
        return redirect('historial_lista')

    if request.method == 'POST':
        deteccion.delete()
        messages.success(request, 'Detección eliminada del historial.')

    return redirect('historial_lista')


@login_required(login_url='index')
def yolo_galeria_eliminar(request, pk):
    """Elimina una captura de la galería. Solo POST; el dueño o el admin."""
    from app.models import DeteccionYOLO

    deteccion = get_object_or_404(DeteccionYOLO, pk=pk, origen='camara')

    if not es_admin(request.user) and deteccion.usuario != request.user:
        messages.error(request, 'No tienes permiso para eliminar esta captura.')
        return redirect('yolo_galeria')

    if request.method == 'POST':
        deteccion.delete()
        messages.success(request, 'Captura eliminada de la galería.')

    return redirect('yolo_galeria')

# ============================================================
# 6. FUNCIONES AUXILIARES DEL MÓDULO YOLO
# ============================================================
# Estas funciones son el "traductor" entre la salida cruda del modelo YOLO
# y algo que se pueda mostrar en pantalla. Es el paso que la plataforma
# no tenía y que impedía ejecutar modelos de detección.

# Las 80 clases del dataset COCO, en el orden exacto en que YOLO las entrega.
# Se usan cuando el modelo no trae nombres de clases configurados.
CLASES_COCO = [
    'persona', 'bicicleta', 'carro', 'motocicleta', 'avion', 'bus', 'tren', 'camion',
    'bote', 'semaforo', 'hidrante', 'senal de pare', 'parquimetro', 'banca', 'pajaro',
    'gato', 'perro', 'caballo', 'oveja', 'vaca', 'elefante', 'oso', 'cebra', 'jirafa',
    'mochila', 'sombrilla', 'bolso', 'corbata', 'maleta', 'frisbee', 'esquis',
    'tabla de snowboard', 'pelota', 'cometa', 'bate de beisbol', 'guante de beisbol',
    'patineta', 'tabla de surf', 'raqueta', 'botella', 'copa de vino', 'taza', 'tenedor',
    'cuchillo', 'cuchara', 'tazon', 'banano', 'manzana', 'sandwich', 'naranja', 'brocoli',
    'zanahoria', 'perro caliente', 'pizza', 'dona', 'pastel', 'silla', 'sofa', 'planta',
    'cama', 'mesa', 'inodoro', 'televisor', 'portatil', 'mouse', 'control remoto',
    'teclado', 'celular', 'microondas', 'horno', 'tostadora', 'lavaplatos', 'refrigerador',
    'libro', 'reloj', 'jarron', 'tijeras', 'oso de peluche', 'secador', 'cepillo de dientes'
]


def _color_clase(clase_id):
    """Asigna un color fijo a cada clase, para que siempre se vea igual."""
    paleta = [(239, 68, 68), (16, 185, 129), (59, 130, 246), (245, 158, 11),
              (168, 85, 247), (236, 72, 153), (20, 184, 166), (249, 115, 22),
              (132, 204, 22), (99, 102, 241)]
    return paleta[clase_id % len(paleta)]


def _decodificar_yolo(salida, ancho_orig, alto_orig, tam_entrada, umbral_confianza):
    """
    Traduce la salida cruda de YOLOv8 a cajas utilizables.

    El modelo NO devuelve las detecciones listas: entrega un tensor de forma
    (1, 84, 8400), que son 8400 recuadros candidatos. De esos 84 valores por
    candidato, los 4 primeros son la posición (centro x, centro y, ancho, alto)
    y los 80 restantes son el puntaje de cada clase posible.

    Esta función recorre esos candidatos, se queda con los que superan el umbral
    de confianza, y convierte las coordenadas del tamaño del modelo (640x640)
    al tamaño real de la imagen que subió el usuario.

    Devuelve tres listas paralelas: cajas, confianzas y id de clase.
    """
    import numpy as np

    pred = np.squeeze(salida)              # (1, 84, 8400) -> (84, 8400)
    if pred.shape[0] < pred.shape[1]:
        pred = pred.transpose()            # (84, 8400)   -> (8400, 84)

    cajas, confianzas, clases_ids = [], [], []
    if pred.size == 0:
        return cajas, confianzas, clases_ids

    # Factores para pasar de las coordenadas del modelo a las de la imagen real
    escala_x = ancho_orig / float(tam_entrada)
    escala_y = alto_orig / float(tam_entrada)

    puntajes = pred[:, 4:]                 # columnas de clases
    mejor_confianza = puntajes.max(axis=1) # mejor puntaje de cada candidato
    mejor_id = puntajes.argmax(axis=1)     # a qué clase corresponde ese puntaje

    # Solo nos interesan los candidatos que superan el umbral
    validos = np.where(mejor_confianza >= float(umbral_confianza))[0]

    for i in validos:
        cx, cy, w, h = pred[i, 0], pred[i, 1], pred[i, 2], pred[i, 3]
        # De (centro, ancho, alto) a (esquina superior izq, esquina inferior der)
        x1 = int(max(0, (cx - w / 2) * escala_x))
        y1 = int(max(0, (cy - h / 2) * escala_y))
        x2 = int(min(ancho_orig, (cx + w / 2) * escala_x))
        y2 = int(min(alto_orig,  (cy + h / 2) * escala_y))

        if x2 <= x1 or y2 <= y1:           # descartar cajas degeneradas
            continue

        cajas.append([x1, y1, x2, y2])
        confianzas.append(float(mejor_confianza[i]))
        clases_ids.append(int(mejor_id[i]))

    return cajas, confianzas, clases_ids


def _nms_yolo(cajas, confianzas, umbral_iou):
    """
    Supresión de No Máximos (NMS): elimina las cajas repetidas.

    YOLO suele marcar el mismo objeto varias veces, con recuadros casi encima
    uno del otro. Esta función ordena las cajas de mayor a menor confianza,
    se queda con la mejor, y descarta todas las que se solapen demasiado con
    ella. El solapamiento se mide con IoU (área compartida / área total).

    Devuelve los índices de las cajas que sobreviven.
    """
    import numpy as np

    if not cajas:
        return []

    c = np.array(cajas, dtype=float)
    s = np.array(confianzas, dtype=float)
    x1, y1, x2, y2 = c[:, 0], c[:, 1], c[:, 2], c[:, 3]
    areas = np.maximum(0, x2 - x1) * np.maximum(0, y2 - y1)

    orden = s.argsort()[::-1]              # de mayor a menor confianza
    conservadas = []

    while orden.size > 0:
        i = int(orden[0])
        conservadas.append(i)
        if orden.size == 1:
            break

        resto = orden[1:]
        # Área de intersección entre la caja ganadora y todas las demás
        xx1 = np.maximum(x1[i], x1[resto]); yy1 = np.maximum(y1[i], y1[resto])
        xx2 = np.minimum(x2[i], x2[resto]); yy2 = np.minimum(y2[i], y2[resto])
        interseccion = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
        union = areas[i] + areas[resto] - interseccion
        iou = np.where(union > 0, interseccion / union, 0)

        # Se conservan solo las que NO se solapan demasiado
        orden = resto[iou <= float(umbral_iou)]

    return conservadas


def _fuente_etiqueta(tamano):
    """Busca una fuente disponible en el sistema; si no hay, usa la de Pillow."""
    from PIL import ImageFont
    rutas = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
             "DejaVuSans-Bold.ttf", "arialbd.ttf"]
    for ruta in rutas:
        try:
            return ImageFont.truetype(ruta, tamano)
        except Exception:
            continue
    return ImageFont.load_default()


def _dibujar_detecciones_yolo(img, cajas, confianzas, clases_ids, indices, nombres):
    """
    Dibuja sobre la imagen original las cajas que sobrevivieron al NMS,
    cada una con su etiqueta (nombre de la clase y porcentaje de confianza).
    El grosor y el tamaño del texto se ajustan al tamaño de la imagen.
    """
    from PIL import ImageDraw

    draw = ImageDraw.Draw(img)
    lado_menor = min(img.size)
    grosor = max(2, int(lado_menor / 250))
    fuente = _fuente_etiqueta(max(13, int(lado_menor / 38)))

    for i in indices:
        x1, y1, x2, y2 = cajas[i]
        clase_id = clases_ids[i]
        color = _color_clase(clase_id)

        # El recuadro del objeto
        draw.rectangle([x1, y1, x2, y2], outline=color, width=grosor)

        nombre = nombres[clase_id] if clase_id < len(nombres) else str(clase_id)
        etiqueta = "%s %.0f%%" % (nombre, confianzas[i] * 100)

        # Medir el texto para dibujarle un fondo del mismo color
        try:
            izq, arr, der, aba = draw.textbbox((0, 0), etiqueta, font=fuente)
            ancho_txt, alto_txt = der - izq, aba - arr
        except Exception:
            ancho_txt, alto_txt = fuente.getsize(etiqueta)

        # La etiqueta va encima de la caja; si no cabe, va adentro
        y_etiqueta = y1 - alto_txt - 6
        if y_etiqueta < 0:
            y_etiqueta = y1 + 2

        draw.rectangle([x1, y_etiqueta, x1 + ancho_txt + 10, y_etiqueta + alto_txt + 6],
                       fill=color)
        draw.text((x1 + 5, y_etiqueta + 3), etiqueta, fill=(255, 255, 255), font=fuente)

    return img

# ============================================================
# 7. MOTOR REUTILIZABLE DEL MÓDULO YOLO
# ============================================================
# La sesión de ONNX Runtime es cara de crear: hay que leer el archivo del
# modelo desde el disco y optimizarlo. Para una imagen suelta no se nota,
# pero con la cámara enviando varios fotogramas por segundo haría que todo
# se arrastre. Por eso la sesión se crea una sola vez y se deja en memoria.

_SESIONES_YOLO = {}   # {clave: (sesion, nombre_entrada)}


def _obtener_sesion_yolo(modelo):
    """
    Devuelve la sesión ONNX del modelo, creándola solo la primera vez.

    La clave de caché incluye la fecha de actualización, así que si el
    administrador reemplaza el archivo del modelo, la sesión se recrea sola.
    """
    import onnxruntime as ort
    import os
    from django.conf import settings

    clave = f"{modelo.pk}-{modelo.fecha_actualizacion.timestamp()}"

    if clave in _SESIONES_YOLO:
        return _SESIONES_YOLO[clave]

    # Resolver dónde está el archivo .onnx
    try:
        ruta = modelo.archivo_modelo.path          # almacenamiento local
    except (NotImplementedError, ValueError):
        # Almacenamiento remoto: descargarlo una vez a un temporal
        import tempfile, urllib.request
        with tempfile.NamedTemporaryFile(delete=False, suffix=".onnx") as tmp:
            urllib.request.urlretrieve(modelo.archivo_modelo.url, tmp.name)
            ruta = tmp.name

    sesion = ort.InferenceSession(ruta)
    nombre_entrada = sesion.get_inputs()[0].name

    # Se guardan máximo 3 modelos en memoria para no llenar la RAM del servidor
    if len(_SESIONES_YOLO) >= 3:
        _SESIONES_YOLO.pop(next(iter(_SESIONES_YOLO)))

    _SESIONES_YOLO[clave] = (sesion, nombre_entrada)
    return _SESIONES_YOLO[clave]

def _detectar_en_imagen(modelo, img):
    """
    Corre el modelo YOLO sobre una imagen PIL y devuelve las detecciones.

    Es el mismo proceso que ya hacía yolo_ejecutar, pero separado para que
    lo puedan usar tanto la subida de imagen como la cámara en vivo.

    Devuelve un diccionario con:
      detecciones: lista de {clase, confianza, caja} ordenada por confianza
      candidatos:  cuántas cajas propuso el modelo antes de filtrar
      cajas, confianzas, clases_ids, indices, nombres: datos crudos por si
      hay que dibujar las cajas sobre la imagen
    """
    import numpy as np
    from PIL import Image

    ancho_orig, alto_orig = img.size
    tam = modelo.tamano_entrada

    # ── Encajar la imagen en el cuadrado del modelo sin deformarla ────────
    # Si se redimensiona directo a 640x640 una foto vertical de celular,
    # los objetos quedan aplastados y el modelo detecta mucho peor.
    # Por eso se escala conservando la proporción y el resto se rellena
    # con gris. Después hay que quitarle ese relleno a las coordenadas.
    escala = min(tam / ancho_orig, tam / alto_orig)
    nuevo_w = max(1, int(round(ancho_orig * escala)))
    nuevo_h = max(1, int(round(alto_orig * escala)))
    dx = (tam - nuevo_w) // 2
    dy = (tam - nuevo_h) // 2

    lienzo = Image.new('RGB', (tam, tam), (114, 114, 114))
    lienzo.paste(img.resize((nuevo_w, nuevo_h)), (dx, dy))

    entrada = np.array(lienzo).astype('float32') / 255.0
    entrada = entrada.transpose(2, 0, 1)
    entrada = np.expand_dims(entrada, axis=0)

    sesion, nombre_entrada = _obtener_sesion_yolo(modelo)
    salida = sesion.run(None, {nombre_entrada: entrada})[0]

    # Se decodifica en el espacio del cuadrado (tam x tam)
    cajas_lb, confianzas_lb, clases_lb = _decodificar_yolo(
        salida, tam, tam, tam, modelo.umbral_confianza
    )

    # Y luego se le quita el relleno para volver a las coordenadas reales
    cajas, confianzas, clases_ids = [], [], []
    for (x1, y1, x2, y2), conf, cid in zip(cajas_lb, confianzas_lb, clases_lb):
        rx1 = int(max(0, min(ancho_orig, (x1 - dx) / escala)))
        ry1 = int(max(0, min(alto_orig,  (y1 - dy) / escala)))
        rx2 = int(max(0, min(ancho_orig, (x2 - dx) / escala)))
        ry2 = int(max(0, min(alto_orig,  (y2 - dy) / escala)))
        if rx2 <= rx1 or ry2 <= ry1:
            continue
        cajas.append([rx1, ry1, rx2, ry2])
        confianzas.append(conf)
        clases_ids.append(cid)

    indices = _nms_yolo(cajas, confianzas, modelo.umbral_iou)
    nombres = modelo.lista_clases() or CLASES_COCO

    detecciones = []
    for i in indices:
        clase_id = clases_ids[i]
        nombre_clase = nombres[clase_id] if clase_id < len(nombres) else str(clase_id)
        detecciones.append({
            'clase': nombre_clase,
            'confianza': round(confianzas[i] * 100, 2),
            'caja': cajas[i],
        })
    detecciones.sort(key=lambda d: d['confianza'], reverse=True)

    return {
        'detecciones': detecciones,
        'candidatos': len(cajas),
        'cajas': cajas,
        'confianzas': confianzas,
        'clases_ids': clases_ids,
        'indices': indices,
        'nombres': nombres,
    }
    
def _resumen_por_clase(detecciones):
    """
    Arma el texto del resumen agrupando por clase.
    Ejemplo: "2 perros, 1 gato" en vez de repetir cada detección.
    """
    from collections import Counter

    if not detecciones:
        return 'Sin detecciones'

    conteo = Counter(d['clase'] for d in detecciones)
    partes = []
    for clase, cantidad in conteo.most_common():
        partes.append(f"{cantidad} {clase}" if cantidad == 1 else f"{cantidad} {clase}s")
    return ', '.join(partes)