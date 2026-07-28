"""El loop think -> act -> observe, escrito a mano.

Nada de frameworks de orquestación: el sábado no se aprende una librería nueva.

Estructura en dos fases, y la razón importa:

  FASE CONSULTA   primera llamada con `tool_config` en modo ANY, que OBLIGA al
                  modelo a llamar una herramienta en vez de responder de memoria.
                  Las rondas siguientes van en AUTO — dejar ANY en todas mete al
                  modelo en un loop infinito de llamadas a herramientas.

  FASE CIERRE     sin herramientas, solo redactar con lo que ya se recolectó.

Y una consecuencia de diseño que hay que tener clara: **la respuesta final no se
puede transmitir en streaming palabra por palabra desde el modelo**, porque el guard
tiene que verificarla completa ANTES de que el usuario la vea. Los eventos `token`
son la respuesta ya verificada, troceada para que el front la pinte progresivamente.
Es una decisión consciente: preferimos medio segundo más de espera antes que la
posibilidad de que un número sin respaldo alcance la pantalla.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from agent import images as imagenes
from agent import llm, prompts
from agent.events import Emitter
from agent.guardrails import VerifyResult, mensaje_degradacion, verificar  # noqa: F401
from agent.conversacion import Conversacion
from agent.memory import SessionMemory
from agent.sources import Source
from agent.tools import Registro

# Seis rondas de TOPE, no de costumbre: el loop corta solo cuando el modelo deja
# de pedir herramientas, así que el caso típico usa 2-3. El tope alto existe por el
# turno del ROI medido en vivo: buscar páginas IE1, leer su tabla, buscar IE3, leer
# su tabla y RECIÉN entonces calcular_ahorro — con tope 4 el loop cortaba justo
# antes del cálculo, el cierre no podía responder sin él, y salía vacío. Cada ronda
# de Flash son ~2-3 s: el peor caso cabe en la demo.
MAX_RONDAS = 6
TOKENS_POR_EVENTO = 6


@dataclass
class RespuestaFinal:
    texto: str
    sources: list[Source] = field(default_factory=list)
    verify: VerifyResult | None = None
    bloqueada: bool = False
    rondas: int = 0


class Agente:
    def __init__(
        self,
        cliente: llm.Cliente,
        registro: Registro,
        emitter: Emitter,
        memoria: SessionMemory | None = None,
        conversacion: Conversacion | None = None,
        *,
        tolerancia: float = 0.02,
        max_rondas: int = MAX_RONDAS,
        lado_maximo_imagen: int = 768,
    ) -> None:
        self.cliente = cliente
        self.registro = registro
        self.emitter = emitter
        # `is not None`, NO `or`: SessionMemory define __len__, así que una memoria
        # VACÍA es falsy y `or` la descartaba en silencio creando otra. Hoy da igual,
        # pero cuando api/ cree una memoria por session_id y la pase, la herramienta
        # escribiría en el objeto del llamador y el loop leería el suyo: la franja
        # MEMORIA se llena en pantalla y el agente nunca ve el hecho. Parece
        # funcionar, que es peor que fallar.
        self.memoria = memoria if memoria is not None else SessionMemory(emitter)
        # Misma trampa que arriba: `Conversacion` define __len__, así que una
        # conversación vacía es falsy. `is not None` o el servidor pierde el
        # historial justo en el primer turno, que es cuando se crea.
        self.conversacion = conversacion if conversacion is not None else Conversacion()
        self.tolerancia = tolerancia
        self.max_rondas = max_rondas
        self.lado_maximo_imagen = lado_maximo_imagen

    # ------------------------------------------------------------------ API

    def responder(
        self,
        mensaje: str,
        imagen: bytes | None = None,
        *,
        exigir_consulta: bool = True,
    ) -> RespuestaFinal:
        """Nunca lanza. Un turno que muere con traceback deja al front sin un solo
        evento y la pantalla congelada — y el momento más probable para que pase es
        justo cuando se agota la cuota, o sea en medio de la demo. Acá el fallo se
        convierte en un evento `error` y una respuesta honesta."""
        try:
            return self._responder(mensaje, imagen, exigir_consulta=exigir_consulta)
        except Exception as e:  # noqa: BLE001
            self.emitter.error("agente", str(e)[:300], recoverable=False)
            res = VerifyResult(
                ok=False,
                checked=0,
                confirmed=0,
                detail=f"BLOQUEADA: el turno falló antes de poder verificar ({type(e).__name__}).",
            )
            texto = (
                "Se me cayó la consulta antes de poder verificar la respuesta. "
                "No voy a improvisar un dato: repite la pregunta."
            )
            self.emitter.verify(**res.to_event_data())
            for trozo in _trocear(texto):
                self.emitter.token(trozo)
            return RespuestaFinal(texto=texto, verify=res, bloqueada=True)

    def _responder(
        self,
        mensaje: str,
        imagen: bytes | None = None,
        *,
        exigir_consulta: bool = True,
    ) -> RespuestaFinal:
        declaraciones = self.registro.declaraciones()

        # El reescalado se hace ACÁ, no en quien llama. Si dependiera del llamador,
        # la primera foto que suba la UI va cruda: 8 MB de celular son miles de
        # tokens y con 20 requests/día eso es cuota que no se recupera.
        if imagen:
            original = len(imagen)
            imagen, mime = imagenes.reescalar(imagen, self.lado_maximo_imagen)
            self.emitter.thought(imagenes.ahorro(original, len(imagen)))
            turno_actual: Any = llm.usuario_con_imagen(mensaje, imagen, mime)
        else:
            turno_actual = llm.texto_usuario(mensaje)

        # Lo hablado antes va DELANTE del turno actual. Sin esto el agente arrancaba
        # en blanco cada vez y el guion de levantamiento no podía pasar del paso 2:
        # preguntaba el voltaje sin acordarse de los HP que ya le habían dado.
        historial: list[Any] = [
            llm.texto_usuario(t.texto) if t.rol == "usuario" else llm.texto_modelo(t.texto)
            for t in self.conversacion
        ]
        historial.append(turno_actual)
        self.conversacion.agregar("usuario", mensaje)

        hechos = self.memoria.para_prompt()
        sistema = prompts.SISTEMA + prompts.FLUJO_MOTORES + prompts.GUION_COTIZACION
        if len(self.memoria):
            sistema += f"\n\nHechos ya establecidos en esta sesión:\n{hechos}\n"

        self.emitter.thought(
            "Voy a consultar la documentación antes de afirmar nada."
            if declaraciones
            else "No tengo herramientas de conocimiento registradas."
        )

        # -------------------------------------------------- FASE CONSULTA
        sources: list[Source] = []
        resultados_calculo: list[Any] = []
        herramientas_usadas: list[str] = []
        rondas = 0

        forzar_proxima = False
        for ronda in range(self.max_rondas):
            if not declaraciones:
                break
            modo = (
                llm.MODO_FORZAR
                if (ronda == 0 or forzar_proxima)
                else llm.MODO_LIBRE
            )
            forzar_proxima = False
            resp = self.cliente.generar(
                historial, sistema=sistema, declaraciones=declaraciones, modo=modo
            )
            rondas += 1

            if not resp.pidio_herramienta:
                # Caso anómalo medido en vivo (turno del ROI): el modelo devuelve una
                # parte SIN texto y SIN function_call — quiere hacer la cuenta él
                # mismo y el prompt se lo prohíbe, así que emite un cascarón vacío.
                # La cura: la siguiente ronda va en ANY, que lo obliga a usar una
                # herramienta de verdad (calcular_ahorro es la única salida que tiene).
                if not resp.texto and ronda + 1 < self.max_rondas:
                    self.emitter.thought(
                        "El modelo respondió vacío (quería calcular por su cuenta). "
                        "Lo fuerzo a usar una herramienta."
                    )
                    forzar_proxima = True
                    continue
                # NO se emite el texto del modelo acá. Ese texto es la respuesta SIN
                # verificar: si el modelo respondió de memoria con un número
                # inventado, emitirlo lo pone en pantalla antes de que el guard lo
                # bloquee — y el jurado ve la cifra falsa igual. El panel dice que
                # hubo intento, no cuál fue.
                if resp.texto:
                    self.emitter.thought(
                        "El modelo intentó responder sin consultar. "
                        "No muestro ese texto hasta verificarlo."
                    )
                break

            historial.append(_turno_del_modelo(resp))
            for llamada in resp.llamadas:
                salida = self._ejecutar(llamada)
                herramientas_usadas.append(llamada.nombre)
                sources.extend(salida.sources)
                tool = self.registro.obtener(llamada.nombre)
                if tool is not None and not tool.es_conocimiento:
                    resultados_calculo.append(salida.result)
                historial.append(
                    llm.respuesta_de_herramienta(llamada.nombre, salida.to_dict())
                )

        conocimiento = set(self.registro.de_conocimiento())
        hubo_consulta = any(n in conocimiento for n in herramientas_usadas)

        # ----------------------------------------------------- FASE CIERRE
        historial.append(llm.texto_usuario(prompts.CIERRE))
        final = self._cerrar(historial, sistema, declaraciones)
        texto = final.texto

        res = verificar(
            texto,
            sources,
            resultados_calculo,
            hubo_consulta=hubo_consulta,
            exigir_consulta=exigir_consulta,
            tolerancia=self.tolerancia,
        )

        # ------------------------------------- un reintento, y luego honestidad
        if not res.ok:
            texto, res, extra = self._reintentar(
                historial, sistema, declaraciones, res,
                sources, resultados_calculo, hubo_consulta, exigir_consulta,
            )
            sources.extend(extra)
            rondas += 1

        # Bloquear la respuesta COMPLETA se reserva para los casos en que no hay nada
        # que mostrar: no se consultó el conocimiento, o no se pudo confirmar NI UN
        # valor. Si confirmó parte, tragarse la respuesta es peor que mostrarla: en
        # el caso real de la demo el agente daba el motor correcto con su página y el
        # guard la tumbaba por un redondeo de unidades. La honestidad no se pierde —
        # se dice en pantalla qué valores no pudo confirmar, y el evento `verify`
        # sigue en rojo. Se muestra el dato Y la duda, no se esconden los dos.
        confirmo_algo = res.confirmed > 0
        bloqueada = not res.ok and (not res.hubo_consulta or not confirmo_algo)
        if bloqueada:
            texto = mensaje_degradacion(res)
        elif not res.ok:
            texto += (
                "\n\n⚠ No pude confirmar estos valores contra las fuentes: "
                + ", ".join(f.texto for f in res.faltantes)
                + ". Los demás sí están verificados."
            )

        # Se guarda el texto QUE SE MOSTRÓ, no el que el modelo redactó: si el guard
        # lo bloqueó, lo que el usuario leyó fue el mensaje de degradación, y el
        # agente tiene que recordar eso mismo. Guardar la versión bloqueada lo dejaría
        # creyendo que ya dio un dato que en pantalla nunca apareció.
        self.conversacion.agregar("agente", texto)
        self._emitir_salida(texto, sources, res)
        return RespuestaFinal(
            texto=texto, sources=_unicas(sources), verify=res,
            bloqueada=bloqueada, rondas=rondas,
        )

    # -------------------------------------------------------------- internos

    def _cerrar(self, historial, sistema, declaraciones):
        """La llamada que redacta la respuesta final.

        Manda las declaraciones de herramientas CON el modo NONE, y eso no es
        contradictorio: es obligatorio. En este punto el historial ya contiene
        `function_call` y `function_response`, y Gemini exige que las herramientas
        estén declaradas cuando la conversación las contiene. Si se omiten, la API
        **no da error**: devuelve texto vacío. Verificado en vivo — el turno con foto
        de placa llegaba hasta buscar el motor y luego el guard reportaba
        "el modelo no produjo una respuesta con contenido", dos veces.

        El modo NONE es lo que garantiza que redacte en vez de pedir otra herramienta.
        """
        if not declaraciones:
            resp = self.cliente.generar(historial, sistema=sistema)
        else:
            resp = self.cliente.generar(
                historial,
                sistema=sistema,
                declaraciones=declaraciones,
                modo=llm.MODO_SIN_TOOLS,
            )
        if not resp.texto:
            # Se emite el diagnóstico, no solo el síntoma: sin esto el panel decía
            # "no produjo respuesta" y no había forma de saber si fue MAX_TOKENS,
            # SAFETY o que el modelo solo devolvió partes de pensamiento.
            self.emitter.thought(
                f"cierre vacío · finish_reason={resp.finish_reason or '?'} "
                f"· partes={resp.partes} · {resp.tokens}"
            )
        return resp

    def _ejecutar(self, llamada: llm.LlamadaHerramienta):
        id_ = uuid.uuid4().hex[:8]
        # El contrato exige `motivo`, pero si el modelo lo omite no se tumba el
        # turno en vivo: se anota que faltó y se sigue.
        motivo = llamada.motivo or "(el modelo no explicó el motivo)"
        # `motivo` va en su propio campo del evento: dejarlo también dentro de `args`
        # hace que el panel lo pinte DOS veces en cada fila de herramienta.
        args = {k: v for k, v in llamada.args.items() if k != "motivo"}
        self.emitter.tool_call(id_, llamada.nombre, args, motivo)

        salida, ms = self.registro.ejecutar(llamada.nombre, llamada.args)
        self.emitter.tool_result(
            id_,
            llamada.nombre,
            ok=salida.uncertainty is None,
            ms=ms,
            summary=salida.resumen(),
            sources=salida.sources,
        )
        return salida

    def _reintentar(
        self, historial, sistema, declaraciones, res,
        sources, resultados_calculo, hubo_consulta, exigir_consulta,
    ) -> tuple[str, VerifyResult, list[Source]]:
        """Un reintento forzando consulta. Si vuelve a fallar, se degrada."""
        nuevas: list[Source] = []

        if not res.hubo_consulta:
            aviso = prompts.REINTENTO_SIN_CONSULTA
            modo = llm.MODO_FORZAR
        elif "no produjo una respuesta" in res.detail:
            # El cierre vino vacío: el modelo quería usar una herramienta (calcular,
            # casi siempre) y el cierre no se lo permitía. El reintento se la fuerza.
            aviso = (
                "Tu respuesta llegó vacía. Si te falta un cálculo, llama a la "
                "herramienta correspondiente AHORA; no intentes calcular tú."
            )
            modo = llm.MODO_FORZAR
        else:
            aviso = prompts.reintento_sin_respaldo([f.texto for f in res.faltantes])
            modo = llm.MODO_LIBRE

        self.emitter.verify(**res.to_event_data())
        self.emitter.thought("El verificador bloqueó la respuesta. Reintento una vez.")
        historial.append(llm.texto_usuario(aviso))

        if declaraciones:
            resp = self.cliente.generar(
                historial, sistema=sistema, declaraciones=declaraciones, modo=modo
            )
            if resp.pidio_herramienta:
                historial.append(_turno_del_modelo(resp))
                for llamada in resp.llamadas:
                    salida = self._ejecutar(llamada)
                    nuevas.extend(salida.sources)
                    tool = self.registro.obtener(llamada.nombre)
                    if tool is not None and not tool.es_conocimiento:
                        resultados_calculo.append(salida.result)
                    if tool is not None and tool.es_conocimiento:
                        hubo_consulta = True
                    historial.append(
                        llm.respuesta_de_herramienta(llamada.nombre, salida.to_dict())
                    )

        historial.append(llm.texto_usuario(prompts.CIERRE))
        segundo = self._cerrar(historial, sistema, declaraciones)

        res2 = verificar(
            segundo.texto,
            list(sources) + nuevas,
            resultados_calculo,
            hubo_consulta=hubo_consulta,
            exigir_consulta=exigir_consulta,
            tolerancia=self.tolerancia,
        )
        return segundo.texto, res2, nuevas

    def _emitir_salida(self, texto: str, sources: list[Source], res: VerifyResult) -> None:
        """Orden a propósito: primero el veredicto, después las citas, al final el texto.

        Así el panel muestra que se verificó ANTES de que apareciera la respuesta.
        """
        self.emitter.verify(**res.to_event_data())
        for s in _citables(sources, res):
            self.emitter.citation(s)
        for trozo in _trocear(texto):
            self.emitter.token(trozo)


def _turno_del_modelo(resp: llm.Respuesta):
    """Devuelve al historial el turno del modelo SIN reconstruirlo.

    Gemini 3 firma los turnos de function calling con `thought_signature`. Si se
    arma un Content a mano con los mismos nombres y argumentos, la API responde
    400 INVALID_ARGUMENT. Se reenvía el objeto original; la reconstrucción queda
    solo como respaldo por si algún día `contenido` llega vacío.
    """
    return resp.contenido or llm.peticion_de_herramienta(resp.llamadas)


def _citables(sources: list[Source], res: VerifyResult) -> list[Source]:
    """Las fuentes que se pintan como chips de cita.

    Solo las que respaldaron un valor. La búsqueda suele traer 3 fragmentos y la
    respuesta usar 1: pintar los 3 se ve prolijo pero es falso, y le regala al
    jurado la pregunta "¿por qué cita una hoja que no usó?".
    Si ningún valor se respaldó (p.ej. la respuesta fue un rechazo honesto), se
    muestra lo que se consultó, que es información útil igual.
    """
    unicas = _unicas(sources)
    if not res.respaldos:
        return unicas
    usadas = [s for s in unicas if s.etiqueta() in res.respaldos]
    return usadas or unicas


def _unicas(sources: list[Source]) -> list[Source]:
    vistas: dict[tuple[str, str, int | None], Source] = {}
    for s in sources:
        vistas.setdefault((s.doc, s.section, s.page), s)
    return list(vistas.values())


def _trocear(texto: str, palabras: int = TOKENS_POR_EVENTO) -> list[str]:
    piezas = texto.split(" ")
    return [
        " ".join(piezas[i : i + palabras]) + (" " if i + palabras < len(piezas) else "")
        for i in range(0, len(piezas), palabras)
    ]
