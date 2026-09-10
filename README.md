# Trend Intelligence Agent MVP

MVP local para analizar exportaciones de tendencias en PDF, XLSX, CSV y PPTX.

## Ejecutar

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app:app --reload
```

Abre `http://127.0.0.1:8000`.

## Diseño

- `app.py`: API, extracción, normalización y orquestación.
- `config/rules.json`: pesos configurables de los scores.
- `config/brands.json`: conocimiento inicial de marcas, ampliable a una base persistente.
- `static/`: interfaz web.

El scoring es determinístico y devuelve sus resultados aunque no haya LLM. Si se define `OPENAI_API_KEY`, el LLM únicamente interpreta los resultados y redacta una recomendación; no calcula ni modifica los scores. Para producción, sustituir los JSON por un repositorio versionado o base de datos y agregar histórico por carga.

## Robustez incorporada

- Límite de carga de 25 MB.
- Normalización específica para exportaciones XLSX de YouScan.
- Detección de campos faltantes y confianza reducida cuando falta evidencia.
- Desglose de componentes de cada score.
- Historial local en `data/history.json` y endpoint `GET /api/history`.
- Pesos separados de la lógica en `config/rules.json`.

## Autenticación

La interfaz usa Supabase Auth para registro, login, confirmación de correo y cierre de sesión. El backend valida el token de Supabase antes de permitir análisis o consultar el historial. Configura `SUPABASE_URL` y `SUPABASE_ANON_KEY` como variables de entorno. Nunca subas un archivo `.env` al repositorio.
