# BRIEFING — pégame completo al iniciar tu sesión de chat

> Este archivo es para **chats de navegador** (chatgpt.com, gemini.google.com, claude.ai):
> no tienen el repo, no leen archivos y no pueden commitear. La sincronización la haces tú.
> Si usas un agente **con acceso a archivos** (Claude Code, Cursor, Gemini CLI, Codex,
> Copilot en el editor) NO necesitas esto: ese lee `AGENTS.md` solo.

---

Estás ayudando en un hackathon de agentes de IA. Equipo de 4, carriles separados.
Tu humano trabaja en el carril de: **<NOMBRE>** — carpeta(s) **<X>**.

## Reglas duras

- Ninguna afirmación de producto sin cita (documento + página). Sin fuente, se dice.
- Lo calculable va en código determinista, no en el modelo.
- Cero mocks en el camino crítico. Secretos solo en `.env`.
- El nombre del modelo va en `.env` (`MODEL_NAME`), nunca en el código.
- Nada de frameworks de orquestación nuevos. Un solo agente, no multi-agente.
- No propongas trabajo fuera del carril de tu humano.

## Contratos de interfaz vigentes

<pegar acá el contenido de team/CONTRATOS.md>

## Estado de los otros carriles

<pegar acá las secciones "## AHORA" de los otros tres STATUS>

## Cómo entregas

Al terminar, dame: (1) el código, y (2) el texto exacto de mi `## AHORA`
actualizado, máximo 6 líneas telegráficas, para que yo lo pegue en el repo.
No puedes hacer git: eso lo hago yo.
