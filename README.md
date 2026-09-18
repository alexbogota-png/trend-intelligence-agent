# Trend Intelligence Agent

MVP local y desplegable en Vercel para analizar exportaciones de tendencias y evaluar su viabilidad para Pond's, Dove y Rexona.

## Qué tiene hoy el proyecto

### Trend Intelligence

Permite cargar archivos PDF, XLSX, CSV y PPTX, seleccionar una marca o comparar las tres marcas iniciales y obtener:

- Trend Strength Score.
- Brand Fit Score.
- Actionability Score.
- Nivel de confianza.
- Componentes que explican cada score.
- Evidencia de entrada.
- Recomendación de activación.
- Comparación y ranking de marcas.

Los scores son determinísticos y se configuran en `config/rules.json`. El conocimiento inicial de cada marca está en `config/brands.json`.

### One Page semanal

Permite cargar datos semanales y construir una lectura para:

1. Qué fue tendencia esta semana.
2. Cómo impacta a Rexona, Pond's y Dove por separado.
3. Sección pendiente, reservada para una taxonomía futura.
4. Qué hizo la categoría y qué posibles competidores aparecen.

El análisis compara la semana más reciente contra la anterior cuando existen fechas y registros suficientes. Identifica conversaciones por temas, cuenta menciones, calcula movimientos y conserva evidencia para la lectura.

### Autenticación

La interfaz utiliza Supabase Auth para registro, inicio de sesión, confirmación de correo y cierre de sesión. El backend valida el token antes de permitir análisis, historial o páginas semanales.

### Persistencia actual

El MVP tiene persistencia local opcional en `data/history.json` y `data/weekly_pages.json`. En Vercel el sistema de archivos de la función no debe considerarse almacenamiento permanente. Para conservar resultados entre despliegues se debe migrar esta información a Supabase o BigQuery.

## Arquitectura actual

```text
Frontend estático
  static/index.html
  static/app.js
  static/navigation.js
       ↓
FastAPI
  app.py
       ↓
Extractores y normalización
  core/extractors.py
  core/normalizer.py
       ↓
Reglas determinísticas
  core/scoring.py
  core/weekly.py
       ↓
Orquestación
  core/agent_graph.py
       ↓
Interpretación opcional
  core/llm.py
       ↓
Supabase, BigQuery o persistencia local
```

## Integración de LangGraph y LangChain

`core/agent_graph.py` contiene dos flujos:

- `run_trend_agent`: calcula scores, interpreta cada marca, ordena resultados y arma la respuesta.
- `run_weekly_agent`: clasifica la semana, solicita la interpretación estructurada, mantiene la sección pendiente vacía y valida la salida.

LangGraph coordina los nodos y conserva el estado del flujo. LangChain se usa para la interpretación estructurada del LLM cuando existe `OPENAI_API_KEY`.

El LLM no calcula ni modifica los scores. Tampoco debe inventar menciones, fechas, marcas, competencia o evidencia. Si LangChain no está disponible o falla, el sistema conserva la ruta determinística y el fallback actual de OpenAI.

## Variables de entorno

Copia `.env.example` a `.env` para ejecución local y completa:

```text
SUPABASE_URL=
SUPABASE_ANON_KEY=
OPENAI_API_KEY=
OPENAI_MODEL=gpt-4o-mini
```

No subas `.env` al repositorio ni expongas claves privadas en el frontend.

## Ejecución local en Windows

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app:app --reload
```

Abre `http://127.0.0.1:8000`.

## API principal

- `GET /api/brands`: devuelve las marcas disponibles.
- `POST /api/analyze`: analiza una tendencia por marca.
- `GET /api/history`: devuelve el historial del usuario autenticado.
- `POST /api/weekly/draft`: construye el One Page semanal.
- `GET /api/weekly`: lista páginas semanales guardadas.
- `PUT /api/weekly`: guarda una página semanal cuando existe almacenamiento persistente.

## Estructura del proyecto

```text
app.py
requirements.txt
config/
  brands.json
  rules.json
core/
  agent_graph.py
  extractors.py
  llm.py
  normalizer.py
  scoring.py
  weekly.py
static/
  index.html
  app.js
  auth.js
  navigation.js
  styles.css
  weekly.css
examples/
  sample_trend.csv
```

## Limitaciones conocidas

- El histórico todavía no está conectado a BigQuery.
- Las reglas de conversación y competencia siguen siendo una primera taxonomía configurable.
- El histórico local no es persistente en Vercel.
- La cuenta de servicio para consultar BigQuery desde Vercel todavía no está configurada.
- La calidad del análisis depende de que el archivo incluya fechas, texto, fuente, tendencia y campos de menciones.
- La interpretación del LLM está condicionada por `OPENAI_API_KEY`; sin esa variable funciona el análisis determinístico, pero no la redacción generativa.

## Próximas mejoras recomendadas

1. Conectar Google Sheets o una tabla externa de BigQuery para el histórico.
2. Materializar el histórico en una tabla nativa particionada por semana.
3. Guardar resultados y páginas semanales en Supabase.
4. Añadir trazabilidad por evidencia, con identificadores de registros.
5. Incorporar LangGraph Checkpointing cuando se necesite reanudar análisis largos.
6. Crear pruebas con archivos reales de YouScan y casos sin semana anterior.
7. Ajustar la taxonomía de conversaciones y competidores con validación del equipo de marca.
