# ExamGrader - Guía de Pruebas Paso a Paso

## Servidores
- **Backend**: http://localhost:8000 (Swagger: http://localhost:8000/docs)
- **Frontend**: http://localhost:5173

---

## CHECKPOINT DE REQUERIMIENTOS

### PARTE 1: Grouping Secuencial
| # | Requerimiento | Estado | Archivo |
|---|--------------|--------|---------|
| 1.1 | Función `detect_name_in_text()` con regex robusto | ✅ | `backend/app/services/grouping_service.py` |
| 1.2 | Función `group_photos_by_student_sequential()` | ✅ | `backend/app/services/grouping_service.py` |
| 1.3 | Foto CON nombre → nuevo grupo de estudiante | ✅ | Probado con test unitario |
| 1.4 | Foto SIN nombre → continúa estudiante anterior | ✅ | Probado con test unitario |
| 1.5 | Primera foto sin nombre → crea "Unknown_Student" | ✅ | Probado con test unitario |
| 1.6 | Logs claros en cada paso del grouping | ✅ | Box-drawing chars en logs |

### PARTE 2: Soporte PDF
| # | Requerimiento | Estado | Archivo |
|---|--------------|--------|---------|
| 2.1 | `PDFService` para convertir PDF a imágenes | ✅ | `backend/app/services/pdf_service.py` (nuevo) |
| 2.2 | Upload endpoint acepta PDF + imágenes | ✅ | `backend/app/api/v1/sessions.py` |
| 2.3 | PDF se convierte a JPEGs y cada página se sube | ✅ | `sessions.py` upload handler |
| 2.4 | Frontend acepta PDF en file upload | ✅ | `frontend/src/pages/NewSession.jsx` |
| 2.5 | FileUpload muestra mensaje correcto de tipos | ✅ | `frontend/src/components/ui/FileUpload.jsx` |
| 2.6 | `pdf2image` agregado a requirements.txt | ✅ | `backend/requirements.txt` |
| 2.7 | Tamaño máximo subido a 20MB para PDFs | ✅ | `sessions.py` |

### PARTE 3: UI Editar Respuestas + Backend
| # | Requerimiento | Estado | Archivo |
|---|--------------|--------|---------|
| 3.1 | Schema `ExamUpdateAnswersRequest` | ✅ | `backend/app/schemas/exam.py` |
| 3.2 | Endpoint PATCH `/exams/{id}/extracted-answers` | ✅ | `backend/app/api/v1/exams.py` |
| 3.3 | Endpoint POST `/exams/{id}/regrade` | ✅ | `backend/app/api/v1/exams.py` |
| 3.4 | Frontend API methods (`updateExtractedAnswers`, `regrade`) | ✅ | `frontend/src/services/sessions.js` |
| 3.5 | Botón "Edit Answers" en ExamDetail | ✅ | `frontend/src/pages/ExamDetail.jsx` |
| 3.6 | Inputs editables inline para cada respuesta | ✅ | `ExamDetail.jsx` |
| 3.7 | Botón "Save & Re-grade" que guarda y recalifica | ✅ | `ExamDetail.jsx` |
| 3.8 | Botón "Cancel" que restaura respuestas originales | ✅ | `ExamDetail.jsx` |

### PARTE 4: Testing
| # | Requerimiento | Estado | Archivo |
|---|--------------|--------|---------|
| 4.1 | Tests unitarios `detect_name_in_text` (9/9) | ✅ | `backend/tests/test_sequential_grouping.py` |
| 4.2 | Tests unitarios grouping secuencial (4/4) | ✅ | `backend/tests/test_sequential_grouping.py` |
| 4.3 | Test edge case: primera foto sin nombre | ✅ | `backend/tests/test_sequential_grouping.py` |
| 4.4 | Integración: Health check API | ✅ | Probado via curl |
| 4.5 | Integración: Register + Login + Auth/me | ✅ | Probado via curl |
| 4.6 | Integración: Crear template + session | ✅ | Probado via curl |
| 4.7 | Integración: Endpoints nuevos registrados | ✅ | Probado via curl |

### FIX ADICIONAL
| # | Fix | Estado | Archivo |
|---|-----|--------|---------|
| F.1 | Puerto del API corregido (8001 → 8000) | ✅ | `frontend/src/services/api.js` |

---

## GUÍA PASO A PASO PARA PROBAR EN LA PLATAFORMA

### Paso 1: Registrarse / Iniciar Sesión
1. Abre http://localhost:5173
2. Si no tienes cuenta, haz clic en **"Create one"**
3. Llena: Nombre, Email, Contraseña
4. Haz clic en **"Create account"**
5. Inicia sesión con tus credenciales

> **Cuenta de prueba ya creada:**
> - Email: `test@examgrader.com`
> - Password: `Test123456!`

### Paso 2: Crear un Template de Examen
1. En el Dashboard, haz clic en **"New Template"** o **"+"**
2. Llena los campos:
   - **Name**: nombre del examen (ej: "Examen Final Matemáticas")
   - **Subject**: materia (ej: "Matemáticas")
   - **Mode**: "integrated" (examen con respuestas en la misma hoja)
   - **Max Score**: puntuación máxima (ej: 20)
3. Sube la foto del template del examen (la hoja en blanco sin respuestas)
4. El sistema extraerá la estructura automáticamente
5. Configura la clave de respuestas (answer key)

### Paso 3: Crear una Sesión de Calificación
1. En el Dashboard, haz clic en **"New Session"**
2. Selecciona el template que creaste
3. Dale un nombre a la sesión (ej: "Parcial Marzo 2026")
4. Haz clic en **"Create"**

### Paso 4: Subir Fotos de Exámenes (NUEVA FUNCIONALIDAD: acepta PDF)
1. En la sesión creada, ve al paso de **Upload**
2. Arrastra archivos o haz clic para seleccionar
3. **Tipos aceptados**: JPG, PNG, WEBP, **PDF** (nuevo)
4. Para **imágenes individuales**: sube una foto por página de examen
5. Para **PDFs multi-página**: sube un PDF y el sistema convierte cada página a imagen automáticamente
6. Haz clic en **"Upload"**
7. Espera que termine la barra de progreso

> **IMPORTANTE sobre el orden de las fotos (Grouping Secuencial):**
> - La PRIMERA foto de cada estudiante debe tener su nombre visible (ej: "Nombre: Juan Pérez")
> - Las fotos SIGUIENTES del mismo estudiante (páginas 2, 3, etc.) NO necesitan nombre
> - El sistema agrupa automáticamente: foto CON nombre = nuevo estudiante, foto SIN nombre = continúa el anterior
> - Ejemplo correcto de orden:
>   1. foto_camila_p1.jpg (tiene "Nombre: Camila Rodriguez") → Nuevo grupo: Camila
>   2. foto_camila_p2.jpg (sin nombre, solo respuestas) → Se agrega a Camila
>   3. foto_juan_p1.jpg (tiene "Nombre: Juan Pérez") → Nuevo grupo: Juan
>   4. foto_juan_p2.jpg (sin nombre) → Se agrega a Juan

### Paso 5: Procesar la Sesión
1. Después del upload, haz clic en **"Process"** o **"Start Grading"**
2. El sistema:
   - Agrupa las fotos por estudiante (grouping secuencial)
   - Extrae respuestas con OCR + Vision AI
   - Califica cada examen comparando con el answer key
3. Espera que el progreso llegue a 100%

### Paso 6: Revisar Resultados
1. Haz clic en un examen individual para ver el detalle
2. Verás:
   - Fotos del examen del estudiante
   - Score obtenido
   - Respuestas extraídas por el sistema
   - Feedback por pregunta

### Paso 7: Editar Respuestas y Recalificar (NUEVA FUNCIONALIDAD)
1. En la vista de detalle del examen, busca la sección **"Extracted Answers"**
2. Haz clic en el botón **"Edit Answers"** (ícono de lápiz)
3. Los campos se vuelven editables (inputs de texto)
4. Corrige las respuestas que el OCR haya leído mal
5. Opciones:
   - **"Save & Re-grade"**: guarda los cambios Y recalifica el examen automáticamente
   - **"Cancel"**: descarta los cambios y vuelve al modo de lectura
6. Después de recalificar, el score se actualiza automáticamente

### Paso 8: Exportar Resultados
1. En la vista de sesión, haz clic en **"Export"**
2. Descarga el Excel con todos los resultados

---

## PRUEBAS ESPECÍFICAS DE LAS NUEVAS FUNCIONALIDADES

### Test A: Grouping Secuencial (con fotos)
1. Prepara 4 fotos de examen:
   - Foto 1: examen de Estudiante A, página 1 (con nombre visible)
   - Foto 2: examen de Estudiante A, página 2 (sin nombre)
   - Foto 3: examen de Estudiante B, página 1 (con nombre visible)
   - Foto 4: examen de Estudiante B, página 2 (sin nombre)
2. Sube las 4 fotos EN ORDEN
3. Procesa la sesión
4. **Esperado**: 2 estudiantes, cada uno con 2 páginas

### Test B: Upload de PDF Multi-página
1. Escanea o crea un PDF con varias páginas de exámenes
2. En el upload, selecciona el archivo PDF
3. Sube el PDF
4. **Esperado**: el sistema convierte cada página a imagen y las lista individualmente

### Test C: Editar Respuestas y Recalificar
1. Abre un examen ya calificado
2. Haz clic en "Edit Answers"
3. Cambia una respuesta (ej: de "B" a "A")
4. Haz clic en "Save & Re-grade"
5. **Esperado**: el score cambia según la corrección

---

## Notas Técnicas
- El backend requiere `poppler` instalado para la conversión de PDF. Si `pdf2image` falla, usa Pillow como fallback.
- Los logs del backend muestran el proceso de grouping con caracteres de caja (╔═══, ║, ╚═══) para fácil lectura.
- La detección de nombres usa patrones: "Name:", "Nombre:", "Student:", "Alumno:", "Estudiante:"
