# 🌱 AgroVision - Plataforma de Machine Learning

<div align="center">
  <img src="https://img.shields.io/badge/Django-092E20?style=for-the-badge&logo=django&logoColor=green" alt="Django" />
  <img src="https://img.shields.io/badge/ONNX_Runtime-005CED?style=for-the-badge&logo=onnx&logoColor=white" alt="ONNX" />
  <img src="https://img.shields.io/badge/Alpine_js-8BC0D0?style=for-the-badge&logo=alpine.js&logoColor=white" alt="Alpine JS" />
  <img src="https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
</div>

<br />

**AgroVision** es una plataforma web desarrollada en Python con el framework **Django**. Funciona como un orquestador centralizado (*AI File Manager y Plataforma de Inferencia*) para gestionar, documentar y ejecutar modelos de Machine Learning aplicados principalmente al sector agrícola.

## ✨ Características Principales

*   🔒 **Autenticación Moderna y Segura**: 
    *   Diseño visual *Glassmorphism* interactivo.
    *   Verificación en dos pasos (2FA) con envío de códigos OTP vía correo electrónico (SMTP config).
    *   Flujo nativo de recuperación de contraseñas seguro mediante correos enmascarados y tokens cifrados.
*   🧠 **Motor de Inferencia Universal ONNX**: 
    *   Ejecución y pruebas de inferencia nativas de modelos de Inteligencia Artificial exportados en formato estándar (`.onnx`).
    *   Integración optimizada con `onnxruntime` y Pillow para análisis predictivo sobre imágenes omitiendo dependencias muy pesadas (ej. PyTorch/TensorFlow).
*   📊 **Dashboard Administrativo Interactivo**: 
    *   Panel de control con diseño a doble columna que resume la actividad de los investigadores.
    *   Métricas en vivo del ecosistema de modelos activos y total acumulado de predicciones documentadas.
*   📜 **Historial de Ejecuciones (Trazabilidad)**: 
    *   Registro granular con filtros de búsqueda para los experimentos realizados por los usuarios.
    *   Almacena información visual (imágenes procesadas), el modelo ML utilizado, los resultados arrojados y un registro crítico de Ubicación geográfica de la Finca / Parcela para monitoreos agrícolas a largo plazo.
*   🎨 **UI/UX Dinámica y Fluida**: 
    *   Desarrollada combinando la potencia de variables puras de CSS y componentes funcionales bajo la reactividad rápida de **Alpine.js**.

## 🚀 Requisitos del Sistema

- **Python 3.10+** u otra versión base actual.
- **pip** (Gestor de libreirías de Python).
- Un Entorno Virtual preconfigurado (`venv`, `conda`) de tu preferencia.

## 🛠 Instalación y Despliegue Local

Sigue estos simples pasos para correr todo el ecosistema de AgroVision en tu máquina de desarrollo o para pruebas locales:

### 1. Ubicar el Repositorio
Abre tu consola o terminal favorita y ubícate en la raíz del proyecto (donde se sitúa el archivo fundamental `manage.py`):

```bash
# Navegar directorio central
cd ruta/del/proyecto-2026/proyecto
```

### 2. Variables de Entorno `.env`
Para el correcto funcionamiento del 2FA (OTP) y correos reales, asegúrate de mantener un archivo llamado `.env` en la misma ruta que tu `manage.py` con directivas similares a estas:

```env
DEBUG=True
DOMINIO=http://127.0.0.1:8000
EMAIL_HOST_USER=tu_correo@gmail.com
EMAIL_HOST_PASSWORD=tu_clave_secreta_smtp
```

> **Nota para Desarrolladores:** Si omites el `.env`, Django imprimirá los correos con OTPs y de validación directamente sobre la terminal que ejecuta el entorno para no interrumpir el desarrollo.

### 3. Sincronización de Base de Datos
Actualiza e instaura el ecosistema relacional de SQLite para el inicio normal del proyecto:

```bash
python manage.py makemigrations
python manage.py migrate
```

### 4. Lanzamiento del Servidor
Inicia la capa de red del servidor interno de Django corriendo:

```bash
python manage.py runserver
```

Una vez observes el banner de inicio, visita desde cualquier navegador: **`http://localhost:8000`**

---

## 📂 Estructura del Código

El trabajo pesado lo realiza una única _App_ interna configurada llamada `/app/`:

- `/app/templates/`: Contiene la totalidad de los archivos `HTML` visuales. 
  - `auth_recover/`: Plantillas para los sistemas de recuperación de contraseña de Django.
  - `base.html`: Interfaz maestra y menú central (Navbar) para propagación estructural.
- `/app/views.py`: Contiene toda la lógica neuronal e interacciones cliente-servidor (Ruteadores, validaciones ONNX, 2FA y Dashboard).
- `/app/models.py`: Arquitectura y relacionamiento de de la Base de Datos predeterminada (Tablas como: `ModeloML`, `HistorialEjecucion`, etc.).

---
<div align="center">
  <p>💡 <i>Desarrollado en Colombia para transformar y centralizar la investigación académica empleando lo último en Inteligencia Artificial y Machine Learning.</i></p>
</div>
