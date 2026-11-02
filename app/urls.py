"""
urls.py — Enrutador principal de la aplicación 'app'
=====================================================
Define TODAS las rutas (URLs) que la aplicación maneja.
Cada path() mapea una URL a una función definida en views.py.

Estructura general:
  - Autenticación:  index, register, verify-2fa, logout
  - Dashboard:      dashboard, nosotros
  - Módulo ML:      modelos/ (lista, crear, detalle, ejecutar)
"""

"""
urls.py (App) — Mapa de Rutas de la Aplicación
=============================================
Define los enlaces (endpoints) disponibles para el usuario final.
Se organiza en:
  1. Sesión y Acceso: Dashboard, Nosotros, Login.
  2. Gestión de Modelos: Listado y Detalle.
  3. Operaciones Admin: Crear, Editar y Eliminar modelos.
  4. Inferencia: Interfaz para ejecutar predicciones ONNX.
"""
from django.urls import path, re_path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # ── Autenticación ────────────────────────────────────────────────────────
    # Página principal/Login — redirige al dashboard si ya está autenticado
    path('', views.index, name='index'),
    # Alias para la URL /login/ (apunta a la misma vista que la raíz)
    path('login/', views.index, name='login'),
    # Formulario de registro de nuevos usuarios
    path('register/', views.register, name='register'),
    # Verificación del código OTP enviado por e-mail (2FA)
    path('verify-2fa/', views.verify_2fa, name='verify_2fa'),

    # ── Recuperación de Contraseña (Auth Views nativas) ─────────────────────
    path('password_reset/', auth_views.PasswordResetView.as_view(
        template_name='auth_recover/password_reset_form.html',
        email_template_name='auth_recover/password_reset_email.html'
    ), name='password_reset'),
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='auth_recover/password_reset_done.html'), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='auth_recover/password_reset_confirm.html'), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(template_name='auth_recover/password_reset_complete.html'), name='password_reset_complete'),

    # ── Secciones principales ────────────────────────────────────────────────
    # Panel principal del usuario (requiere login)
    path('dashboard/', views.dashboard, name='dashboard'),
    # Página "Nosotros" / información institucional y del proyecto (requiere login)
    path('nosotros/', views.nosotros, name='nosotros'),
    # Página de estadísticas
    path('estadisticas/', views.estadisticas, name='estadisticas'),
    # Cierra la sesión activa y redirige al login
    path('logout/', views.logout_view, name='logout'),

    # ── Módulo de Modelos ML ─────────────────────────────────────────────────
    # Lista/catálogo de todos los modelos registrados (con búsqueda y filtros)
    path('modelos/', views.modelos_lista, name='modelos_lista'),
    # Formulario para registrar un nuevo modelo ML
    path('modelos/crear/', views.modelo_crear, name='modelo_crear'),
    # Vista de detalle de un modelo específico, identificado por su PK (ID)
    path('modelos/<int:pk>/', views.modelo_detalle, name='modelo_detalle'),
    # Página de inferencia: sube imagen → obtiene predicción del modelo ONNX
    path('modelos/<int:pk>/ejecutar/', views.modelo_ejecutar, name='modelo_ejecutar'),
    # Editar datos de un modelo existente (solo admin)
    path('modelos/<int:pk>/editar/', views.modelo_editar, name='modelo_editar'),
    # Eliminar un modelo del catálogo (solo admin, acepta solo POST)
    path('modelos/<int:pk>/eliminar/', views.modelo_eliminar, name='modelo_eliminar'),

    # ── Historial de Ejecuciones ─────────────────────────────────────────────
    path('historial/', views.historial_lista, name='historial_lista'),
    path('historial/<int:pk>/', views.historial_detalle, name='historial_detalle'),
    path('historial/<int:pk>/eliminar/', views.historial_eliminar, name='historial_eliminar'),

        # ── Módulo YOLO — Detección de Objetos ───────────────────────────────────
    # Catálogo de modelos YOLO registrados
    path('yolo/', views.yolo_lista, name='yolo_lista'),
    # Formulario para registrar un nuevo modelo YOLO (solo admin)
    path('yolo/crear/', views.yolo_crear, name='yolo_crear'),
    # Ficha del modelo YOLO con sus parámetros y últimas detecciones
    path('yolo/<int:pk>/', views.yolo_detalle, name='yolo_detalle'),
    # Editar un modelo YOLO ya registrado (solo admin)
    path('yolo/<int:pk>/editar/', views.yolo_editar, name='yolo_editar'),
    # Página de detección: sube imagen → cajas delimitadoras dibujadas
    path('yolo/<int:pk>/ejecutar/', views.yolo_ejecutar, name='yolo_ejecutar'),
    # Eliminar un modelo YOLO (solo admin, acepta solo POST)
    path('yolo/<int:pk>/eliminar/', views.yolo_eliminar, name='yolo_eliminar'),

    # ── Detección en vivo desde la cámara ───────────────────────────────────
    # Página con el video y las cajas dibujadas en tiempo real
    path('yolo/<int:pk>/camara/', views.yolo_camara, name='yolo_camara'),
    # Recibe un fotograma y devuelve las detecciones en JSON (no guarda nada)
    path('yolo/<int:pk>/frame/', views.yolo_frame, name='yolo_frame'),
    # Guarda la foto capturada con su resumen en el historial
    path('yolo/<int:pk>/capturar/', views.yolo_capturar, name='yolo_capturar'),

    # ── Galería de capturas de cámara ────────────────────────────────────────
    # Lista todas las fotos tomadas con la cámara (origen='camara')
    path('yolo/galeria/', views.yolo_galeria, name='yolo_galeria'),
    # Detalle de una detección: imagen en grande y lista de objetos
    path('yolo/deteccion/<int:pk>/', views.yolo_deteccion_detalle, name='yolo_deteccion_detalle'),
    # Elimina una detección desde el historial (imagen o cámara, solo POST)
    path('yolo/deteccion/<int:pk>/eliminar/', views.yolo_deteccion_eliminar, name='yolo_deteccion_eliminar'),
    # Elimina una captura de la galería (solo POST)
    path('yolo/galeria/<int:pk>/eliminar/', views.yolo_galeria_eliminar, name='yolo_galeria_eliminar'),

]
