"""
models.py — Definición de la Base de Datos (Modelos)
===================================================
Este archivo define la estructura de datos de AgroVision usando el ORM de Django.
Se divide en tres pilares:
  1. Perfiles de Usuario: Extensión del modelo User de Django para roles y 2FA.
  2. Gestión de Archivos: Almacenamiento genérico de documentos.
  3. Catálogo de Modelos ML: Modelos ONNX/PKL, metadatos técnicos y telemetría.

Además, contiene 'Signals' (señales) para la limpieza automática de archivos
físicos cuando se eliminan o actualizan registros en la BD.
"""
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save, post_delete, pre_save
from django.dispatch import receiver


# ============================================================
# 0. CATÁLOGO DE CATEGORÍAS (dinámico)
# ============================================================

# Lista de categorías predefinidas para sembrar la BD al inicio
CATEGORIAS_PREDEFINIDAS = [
    'fresa', 'cacao', 'manzana', 'tomate', 'café', 'plátano', 'palma'
]

class Categoria(models.Model):
    """Categoría de un modelo ML. El administrador puede agregar nuevas al subir un modelo."""
    nombre = models.CharField(max_length=100, unique=True, verbose_name='Nombre')

    class Meta:
        ordering = ['nombre']
        verbose_name = 'Categoría'
        verbose_name_plural = 'Categorías'

    def __str__(self):
        return self.nombre.capitalize()


# ============================================================
# 1. PERFILES Y ROLES DE USUARIO
# ============================================================

class UserProfile(models.Model):
    # Roles disponibles en la plataforma
    ROL_CHOICES = [
        ('admin', 'Administrador'),  # Puede crear, editar y eliminar modelos
        ('user',  'Usuario'),        # Solo puede ver y ejecutar (consumir) modelos
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    otp_code = models.CharField(max_length=6, blank=True, null=True)
    otp_created_at = models.DateTimeField(blank=True, null=True)

    # Rol del usuario dentro de la plataforma (independiente del sistema de permisos de Django)
    rol = models.CharField(max_length=10, choices=ROL_CHOICES, default='user',
                           verbose_name='Rol')

    def __str__(self):
        return f"Perfil de {self.user.username} ({self.get_rol_display()})"

    def es_admin(self):
        """Devuelve True si el usuario tiene rol de administrador o es superusuario de Django."""
        return self.rol == 'admin' or self.user.is_superuser


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        # Los superusuarios de Django obtienen rol admin automáticamente
        rol_inicial = 'admin' if instance.is_superuser else 'user'
        UserProfile.objects.create(user=instance, rol=rol_inicial)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if not hasattr(instance, 'profile'):
        UserProfile.objects.create(user=instance)
    instance.profile.save()

# Modelo de Archivos Genéricos (Datasets, Papers Sueltos, etc)
class Archivo(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.CASCADE)
    nombre = models.CharField(max_length=255)
    descripcion = models.TextField()
    archivo = models.FileField(upload_to='archivos/')
    fecha_subida = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.nombre

# Catálogo de Modelos Machine Learning
class ModeloML(models.Model):
    ESTADO_CHOICES = [
        ('activo', 'Activo'),
        ('inactivo', 'Inactivo'),
        ('entrenamiento', 'En Entrenamiento'),
    ]

    nombre = models.CharField(max_length=255)
    nombre_estudio = models.CharField(max_length=255, verbose_name='Nombre del Estudio')
    descripcion = models.TextField()
    # Categoría libre (sin choices fijos) — se relaciona con el modelo Categoria
    categoria = models.CharField(max_length=100)
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='activo')

    archivo_modelo = models.FileField(
        upload_to='modelos_ml/',
        verbose_name='Archivo del Modelo (.onnx, .pkl)',
        help_text='Sube el archivo de tu modelo entrenado (formatos aceptados: .onnx, .pkl)'
    )
    documento_estudio = models.FileField(
        upload_to='estudios_pdf/',
        verbose_name='Documento del Estudio (PDF)',
        blank=True,
        null=True,
        help_text='Documento PDF con la investigación o estudio relacionado'
    )

    precision = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        blank=True,
        null=True,
        verbose_name='Precisión (%)',
        help_text='Precisión del modelo en porcentaje (ej: 95.87)'
    )

    # Campos de Configuración de Inferencia Dinámica
    img_width = models.IntegerField(
        default=28,
        verbose_name='Ancho de Entrada (px)',
        help_text='Ancho esperado de la imagen por el modelo ONNX (ej: 28, 224).'
    )

    img_height = models.IntegerField(
        default=28,
        verbose_name='Alto de Entrada (px)',
        help_text='Alto esperado de la imagen por el modelo ONNX (ej: 28, 224).'
    )

    es_rgb = models.BooleanField(
        default=False,
        verbose_name='¿Es RGB (A color)?',
        help_text='Marca esta opción si el modelo fue entrenado con imágenes a color. Déjalo vacío si es en escala de grises.'
    )

    invertir_colores = models.BooleanField(
        default=False,
        verbose_name='¿Invertir Colores?',
        help_text='Ideal para modelos como MNIST que esperan trazos blancos sobre fondo negro.'
    )

    nombres_clases = models.TextField(
        blank=True,
        null=True,
        verbose_name='Nombres de las Clases',
        help_text='Nombres separados por comas. Ej: "Manzana Sana,Manzana Enferma". Convierte el resultado numérico en texto legible.'
    )

    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='modelos_ml')
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-fecha_creacion']
        verbose_name = 'Modelo ML'
        verbose_name_plural = 'Modelos ML'

    def __str__(self):
        return self.nombre


from django.db.models.signals import post_delete, pre_save

# Señal para eliminar el archivo del almacenamiento al eliminar la instancia (Archivo)
@receiver(post_delete, sender=Archivo)
def eliminar_archivo(sender, instance, **kwargs):
    if instance.archivo:
        instance.archivo.delete(False)

# Señal para eliminar el archivo anterior antes de actualizar (Archivo)
@receiver(pre_save, sender=Archivo)
def actualizar_archivo(sender, instance, **kwargs):
    if not instance.pk:
        return
    try:
        old_instance = Archivo.objects.get(pk=instance.pk)
        if old_instance.archivo and old_instance.archivo != instance.archivo:
            old_instance.archivo.delete(save=False)
    except Archivo.DoesNotExist:
        pass


# Señales para eliminar los archivos de ModeloML (ONNX y PDF)
@receiver(post_delete, sender=ModeloML)
def eliminar_archivos_modeloml(sender, instance, **kwargs):
    if instance.archivo_modelo:
        instance.archivo_modelo.delete(False)
    if instance.documento_estudio:
        instance.documento_estudio.delete(False)

@receiver(pre_save, sender=ModeloML)
def actualizar_archivos_modeloml(sender, instance, **kwargs):
    if not instance.pk:
        return
    try:
        old_instance = ModeloML.objects.get(pk=instance.pk)
        if old_instance.archivo_modelo and old_instance.archivo_modelo != instance.archivo_modelo:
            old_instance.archivo_modelo.delete(save=False)
        if old_instance.documento_estudio and old_instance.documento_estudio != instance.documento_estudio:
            old_instance.documento_estudio.delete(save=False)
    except ModeloML.DoesNotExist:
        pass


# ============================================================
# 4. HISTORIAL DE EJECUCIONES
# ============================================================

class HistorialEjecucion(models.Model):
    """
    Registra cada vez que un usuario ejecuta (consume) un modelo ML.
    Guarda la imagen subida, la ubicación indicada por el usuario,
    el resultado de la inferencia y el modelo utilizado.
    La imagen se almacena en el backend configurado (Azure/local).
    """
    usuario = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='historial_ejecuciones',
        verbose_name='Usuario'
    )
    modelo = models.ForeignKey(
        ModeloML,
        on_delete=models.SET_NULL,
        null=True,
        related_name='historial_ejecuciones',
        verbose_name='Modelo usado'
    )
    # Imagen subida por el usuario para la inferencia
    imagen = models.ImageField(
        upload_to='historial_imagenes/',
        verbose_name='Imagen de entrada'
    )
    # Ubicación indicada por el usuario (ej: "Finca El Diamante")
    ubicacion = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name='Ubicación'
    )
    # Resultado textual de la inferencia (ej: "Fresa Sana (92.4%)")
    resultado = models.TextField(
        blank=True,
        default='',
        verbose_name='Resultado'
    )
    fecha_ejecucion = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Fecha de ejecución'
    )

    class Meta:
        ordering = ['-fecha_ejecucion']
        verbose_name = 'Historial de Ejecución'
        verbose_name_plural = 'Historial de Ejecuciones'

    def __str__(self):
        modelo_nombre = self.modelo.nombre if self.modelo else 'Modelo eliminado'
        return f"{self.usuario.username} — {modelo_nombre} ({self.fecha_ejecucion.strftime('%d/%m/%Y %H:%M')})"


# Señal: al eliminar un registro de historial, borra la imagen del almacenamiento
@receiver(post_delete, sender=HistorialEjecucion)
def eliminar_imagen_historial(sender, instance, **kwargs):
    if instance.imagen:
        instance.imagen.delete(False)

# ============================================================
# 5. MÓDULO YOLO — DETECCIÓN DE OBJETOS
# ============================================================

class ModeloYOLO(models.Model):
    """
    Catálogo de modelos YOLO (detección de objetos) en formato ONNX.

    A diferencia de ModeloML —que ejecuta modelos de clasificación y devuelve
    una sola clase con su confianza—, un modelo YOLO devuelve múltiples objetos
    detectados, cada uno con su caja delimitadora, su clase y su confianza.
    """

    ESTADO_CHOICES = [
        ('activo', 'Activo'),
        ('inactivo', 'Inactivo'),
    ]

    nombre = models.CharField(max_length=255, verbose_name='Nombre del Modelo')
    descripcion = models.TextField(verbose_name='Descripción')

    archivo_modelo = models.FileField(
        upload_to='modelos_yolo/',
        verbose_name='Archivo del Modelo YOLO (.onnx)',
        help_text='Modelo YOLO exportado a formato ONNX (ej: yolov8n.onnx)'
    )

    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='activo')

    tamano_entrada = models.IntegerField(
        default=640,
        verbose_name='Tamaño de Entrada (px)',
        help_text='Tamaño al que se redimensiona la imagen antes de la inferencia. YOLOv8 usa 640.'
    )

    umbral_confianza = models.FloatField(
        default=0.4,
        verbose_name='Umbral de Confianza',
        help_text='Descarta detecciones por debajo de este valor (0.0 a 1.0). Por defecto 0.4 (40%).'
    )

    umbral_iou = models.FloatField(
        default=0.45,
        verbose_name='Umbral IoU (NMS)',
        help_text='Umbral para eliminar cajas duplicadas sobre el mismo objeto. Por defecto 0.45.'
    )

    nombres_clases = models.TextField(
        blank=True,
        null=True,
        verbose_name='Nombres de las Clases',
        help_text='Nombres separados por comas, en el orden del entrenamiento. Si se deja vacío, se usan las 80 clases del dataset COCO.'
    )

    usuario = models.ForeignKey(User, on_delete=models.CASCADE, related_name='modelos_yolo')
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-fecha_creacion']
        verbose_name = 'Modelo YOLO'
        verbose_name_plural = 'Modelos YOLO'

    def __str__(self):
        return self.nombre

    def lista_clases(self):
        """Devuelve la lista de nombres de clases configurada, o None si está vacía."""
        if not self.nombres_clases:
            return None
        return [n.strip() for n in self.nombres_clases.split(',') if n.strip()]


class DeteccionYOLO(models.Model):
    """
    Historial de detecciones ejecutadas con un modelo YOLO.
    Guarda la imagen original, la imagen con las cajas dibujadas y el resumen.
    """

    ORIGEN_CHOICES = [
        ('imagen', 'Imagen cargada'),
        ('camara', 'Cámara en vivo'),
    ]

    usuario = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='detecciones_yolo', verbose_name='Usuario'
    )
    modelo = models.ForeignKey(
        ModeloYOLO, on_delete=models.SET_NULL, null=True,
        related_name='detecciones', verbose_name='Modelo usado'
    )

    imagen_original = models.ImageField(
        upload_to='yolo_entradas/', verbose_name='Imagen de entrada'
    )
    imagen_resultado = models.ImageField(
        upload_to='yolo_resultados/', blank=True, null=True,
        verbose_name='Imagen con detecciones'
    )

    total_detecciones = models.IntegerField(default=0, verbose_name='Objetos detectados')

    origen = models.CharField(
        max_length=10,
        choices=ORIGEN_CHOICES,
        default='imagen',
        verbose_name='Origen de la detección'
    )

    resumen = models.TextField(blank=True, default='', verbose_name='Resumen de detecciones')
    fecha_ejecucion = models.DateTimeField(auto_now_add=True, verbose_name='Fecha de ejecución')

    class Meta:
        ordering = ['-fecha_ejecucion']
        verbose_name = 'Detección YOLO'
        verbose_name_plural = 'Detecciones YOLO'

    def __str__(self):
        nombre_modelo = self.modelo.nombre if self.modelo else 'Modelo eliminado'
        return f"{self.usuario.username} — {nombre_modelo} ({self.total_detecciones} objetos)"

# Señales de limpieza de archivos del módulo YOLO
@receiver(post_delete, sender=ModeloYOLO)
def eliminar_archivo_modelo_yolo(sender, instance, **kwargs):
    if instance.archivo_modelo:
        instance.archivo_modelo.delete(False)


@receiver(post_delete, sender=DeteccionYOLO)
def eliminar_imagenes_deteccion_yolo(sender, instance, **kwargs):
    if instance.imagen_original:
        instance.imagen_original.delete(False)
    if instance.imagen_resultado:
        instance.imagen_resultado.delete(False)