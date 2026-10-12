/* ==========================================================================
   Jarvis — asistente jurídico con IA
   Streaming SSE sobre POST, markdown progresivo, panel de cita y exportar.
   ========================================================================== */
(function () {
  "use strict";

  var wrap   = document.getElementById("jvWrap");
  if (!wrap) return;

  var hilo     = document.getElementById("jvHilo");
  var scroller = document.getElementById("jvScroll");
  var entrada  = document.getElementById("jvEntrada");
  var btn      = document.getElementById("jvEnviar");
  var ico      = document.getElementById("jvIco");
  var jump     = document.getElementById("jvJump");
  var viva     = document.getElementById("jvViva");
  var modal    = document.getElementById("jvModal");
  var railHist = document.getElementById("jvHist");

  var ICO_SEND = '<path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/>';
  var ICO_STOP = '<rect x="6" y="6" width="12" height="12" rx="2"/>';

  var ctrl = null;
  var generando = false;
/* Marca que el usuario detuvo la generacion: evita mostrar "Respuesta
   completa" o el error "No hubo respuesta" despues de cancelar. */
var cancelando = false;
  var arrastre = false;
  var turnos = [];
  var ultima = "";

  /* --------------------------------------------------------------- utils */
  function h(t, c, x) {
    var n = document.createElement(t);
    if (c) n.className = c;
    if (x != null) n.textContent = x;
    return n;
  }
  function esc(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;")
      .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function reloj() {
    var d = new Date();
    return ("0" + d.getHours()).slice(-2) + ":" + ("0" + d.getMinutes()).slice(-2);
  }
  function reducir() {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }
  function cerca() {
    return scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 100;
  }
  function anclar() {
    if (reducir()) scroller.scrollTop = scroller.scrollHeight;
    else scroller.scrollTo({ top: scroller.scrollHeight, behavior: "smooth" });
  }
  function fija() { scroller.scrollTop = scroller.scrollHeight; }
  function avisar(t) { if (viva) viva.textContent = t; }

  function copiar(t) {
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(t);
      return true;
    }
    var ta = h("textarea");
    ta.value = t;
    document.body.appendChild(ta);
    ta.select();
    var ok = false;
    try { ok = document.execCommand("copy"); } catch (e) { ok = false; }
    document.body.removeChild(ta);
    return ok;
  }

  /* -------------------------------------------------- markdown progresivo */
  function md(txt) {
    var s = esc(txt).replace(/\r/g, "");
    var out = [], L = s.split("\n"), i = 0;
    while (i < L.length) {
      var l = L[i];
      if (/^###\s+/.test(l)) { out.push("<h3>" + inl(l.replace(/^###\s+/, "")) + "</h3>"); i++; continue; }
      if (/^##\s+/.test(l)) { out.push("<h2>" + inl(l.replace(/^##\s+/, "")) + "</h2>"); i++; continue; }
      if (/^(---+|\*\*\*+)$/.test(l.trim())) { out.push("<hr>"); i++; continue; }
      if (/^>\s?/.test(l)) {
        var q = [];
        while (i < L.length && /^>\s?/.test(L[i])) { q.push(L[i].replace(/^>\s?/, "")); i++; }
        out.push("<blockquote>" + inl(q.join(" ")) + "</blockquote>");
        continue;
      }
      if (/^\s*[-*]\s+/.test(l)) {
        var ul = [];
        while (i < L.length && /^\s*[-*]\s+/.test(L[i])) {
          ul.push("<li>" + inl(L[i].replace(/^\s*[-*]\s+/, "")) + "</li>"); i++;
        }
        out.push("<ul>" + ul.join("") + "</ul>");
        continue;
      }
      if (/^\s*\d+[.)]\s+/.test(l)) {
        var ol = [];
        while (i < L.length && /^\s*\d+[.)]\s+/.test(L[i])) {
          ol.push("<li>" + inl(L[i].replace(/^\s*\d+[.)]\s+/, "")) + "</li>"); i++;
        }
        out.push("<ol>" + ol.join("") + "</ol>");
        continue;
      }
      if (!l.trim()) { i++; continue; }
      var p = [];
      while (i < L.length && L[i].trim() &&
             !/^(###?\s|>\s?|\s*[-*]\s|\s*\d+[.)]\s|-{3,}$)/.test(L[i])) { p.push(L[i]); i++; }
      out.push("<p>" + inl(p.join(" ")) + "</p>");
    }
    return out.join("");
  }
  function inl(t) {
    return t
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|[\s(])\*([^*\n]+?)\*(?=[\s).,;:!?]|$)/g, "$1<em>$2</em>")
      .replace(/`([^`]+?)`/g, "<code>$1</code>");
  }

  /* ------------------------------------------------------------- launcher */
  function abrir() {
    wrap.hidden = false;
    document.body.style.overflow = "hidden";
    setTimeout(function () { entrada.focus(); }, 60);
    if (typeof window.DerechosOnTrack === "function") {
      try { window.DerechosOnTrack("chat_abierto"); } catch (e) {}
    }
  }
  function cerrar() {
    wrap.hidden = true;
    document.body.style.overflow = "";
    if (generando) detener();
  }
  document.getElementById("jvAbrir").onclick = abrir;
  document.getElementById("jvCerrar").onclick = cerrar;

  function nueva() {
    if (generando) detener();
    turnos = [];
    ultima = "";
    try { localStorage.removeItem("jv_hist"); } catch (e) {}
    if (railHist) railHist.innerHTML = "";
    hilo.innerHTML = "";
    pintarVacio();
    anclar();
    avisar("Nueva consulta iniciada.");
  }
  document.getElementById("jvNueva").onclick = nueva;
  document.getElementById("jvTopNueva").onclick = nueva;
  wrap.addEventListener("click", function (e) { if (e.target === wrap) cerrar(); });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && !wrap.hidden && modal.hidden) cerrar();
  });

  scroller.addEventListener("scroll", function () {
    if (cerca()) { arrastre = false; jump.style.display = "none"; }
    else if (turnos.length) { arrastre = true; jump.style.display = "inline-flex"; }
  });
  jump.onclick = function () { arrastre = false; jump.style.display = "none"; anclar(); };

  /* ------------------------------------------------------------ vacio */
  function pintarVacio() {
    var v = h("div", "jv-vacio");
    v.appendChild(h("span", "jv-orb-big"));
    v.appendChild(h("h3", null, "¿En qué te puedo ayudar?"));
    v.appendChild(h("p", null,
      "Cuéntame tu situación con tus propias palabras. Reviso la norma colombiana "
      + "que aplica, te digo qué puedes hacer, en qué plazo y con qué pruebas."));
    var sug = h("div", "jv-sug");
    PREGUNTAS.forEach(function (p) {
      var b = h("button", null, p[1] + " " + p[0]);
      b.onclick = function () { preguntar(p[0]); };
      sug.appendChild(b);
    });
    v.appendChild(sug);
    hilo.appendChild(v);
  }

  var PREGUNTAS = [
    ["Me despidieron sin carta, ¿qué puedo hacer?", "💼"],
    ["No me han pagado varios meses de salario", "💰"],
    ["¿Me pueden desalojar sin aviso?", "🏠"],
    ["¿Cuánto cuesta un proceso laboral?", "💳"]
  ];

  function limpiarVacio() {
    var v = hilo.querySelector(".jv-vacio");
    if (v && v.parentNode) v.parentNode.removeChild(v);
  }

  /* ----------------------------------------------------------- compositor */
  function crecer() {
    entrada.style.height = "auto";
    entrada.style.height = Math.min(entrada.scrollHeight, 130) + "px";
    if (!generando) btn.disabled = !entrada.value.trim();
  }
  entrada.addEventListener("input", crecer);
  entrada.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); enviar(); }
  });

  function estadoBoton(activo) {
    btn.classList.toggle("parando", activo);
    ico.innerHTML = activo ? ICO_STOP : ICO_SEND;
    btn.setAttribute("aria-label", activo ? "Detener respuesta" : "Enviar mensaje");
    btn.disabled = !activo && !entrada.value.trim();
    var chips = document.querySelectorAll(".jv-chip, .jv-sug button");
    for (var i = 0; i < chips.length; i++) chips[i].disabled = activo;
  }
  btn.onclick = function () { if (generando) detener(); else enviar(); };

  function enviar() {
    var v = entrada.value.trim();
    if (!v) return;
    entrada.value = "";
    crecer();
    preguntar(v);
  }

  function preguntar(texto) {
    if (generando) detener();
    limpiarVacio();
    arrastre = false;

    var yo = h("div", "jv-msg user");
    yo.appendChild(h("div", "jv-msg-bur", texto));
    hilo.appendChild(yo);
    turnos.push({ rol: "user", texto: texto });
    ultima = texto;
    anclar();
    pedir(texto);
    guardarHistorial();
  }

  /* ------------------------------------------------------------- pedir */
  function pedir(texto) {
    generando = true;
    estadoBoton(true);
    avisar("Generando respuesta.");
    ctrl = window.AbortController ? new AbortController() : null;

    var bot = h("div", "jv-msg bot");
    var head = h("div", "jv-msg-head");
    head.appendChild(h("span", "jv-orb-sm"));
    head.appendChild(h("b", null, "Asistente jurídico"));
    head.appendChild(h("span", "jv-time", reloj()));
    var tag = h("span", "jv-pensando", "pensando…");
    head.appendChild(tag);
    bot.appendChild(head);

    var cuerpo = h("div", "jv-md");
    bot.appendChild(cuerpo);
    var destino = h("div", "jv-md");
    var caret = h("span", "jv-caret");
    cuerpo.appendChild(destino);
    cuerpo.appendChild(caret);

    hilo.appendChild(bot);
    anclar();

    var escala = setTimeout(function () { tag.textContent = "analizando tu caso…"; }, 2200);
    var acumulado = "";
    var terminado = false;
    cancelando = false;

    function quitarTag() { clearTimeout(escala); if (tag.parentNode) tag.parentNode.removeChild(tag); }

    function pintar() {
      destino.innerHTML = md(acumulado);
      if (!arrastre) { if (cerca()) anclar(); else fija(); }
      else fija();
    }

    function finalizar(textoFinal, fuentes) {
      if (terminado) return;
      terminado = true;
      clearTimeout(escala);
      quitarTag();
      if (caret.parentNode) caret.parentNode.removeChild(caret);
      if (!acumulado && textoFinal) { acumulado = textoFinal; pintar(); }

      if (fuentes && fuentes.length) {
        var fw = h("div", "jv-fuentes");
        fuentes.forEach(function (f) {
          var p;
          if (f.url) {
            // Cita verificable: lleva al texto oficial consultado.
            p = h("a", "jv-fuente jv-fuente--enlace");
            p.href = f.url;
            p.target = "_blank";
            p.rel = "noopener noreferrer";
            p.textContent = f.t;
          } else {
            p = h("span", "jv-fuente");
            p.textContent = f.t;
          }
          var detalle = f.d || "";
          if (f.fecha) detalle += " · consultado el " + f.fecha;
          p.title = detalle;
          fw.appendChild(p);
        });
        cuerpo.appendChild(fw);
      }

      var textoLimpio = (textoFinal || acumulado).trim();
      if (textoLimpio) {
        turnos.push({ rol: "bot", texto: textoLimpio });
        acciones(bot, cuerpo, textoLimpio);
      }
      generando = false;
      estadoBoton(false);
      avisar(cancelando ? "Generación detenida." : "Respuesta completa.");
      fija();
    }

    function error(txt) {
      if (terminado) return;
      terminado = true;
      clearTimeout(escala);
      quitarTag();
      if (caret.parentNode) caret.parentNode.removeChild(caret);
      var e = h("div", "jv-error");
      e.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/></svg>';
      e.appendChild(h("span", null, txt));
      cuerpo.appendChild(e);
      generando = false;
      estadoBoton(false);
      avisar(txt);
      fija();
    }

    var opciones = fetch("/api/jarvis", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mensaje: texto }),
      signal: ctrl ? ctrl.signal : undefined
    }).then(function (r) {
      if (!r.ok || !r.body) throw new Error("HTTP " + r.status);
      return r.body.getReader();
    });

    var dec = (window.TextDecoder) ? new TextDecoder() : null;
    var buf = "";

    function manejar(bloque) {
      var linea = bloque.split("\n").filter(function (x) { return x.indexOf("data:") === 0; })[0];
      if (!linea) return;
      var ev;
      try { ev = JSON.parse(linea.slice(5)); } catch (e) { return; }

      if (ev.tipo === "inicio") {
        var punto = document.getElementById("jvDot");
        var txt = document.getElementById("jvEstado");
        if (punto && txt) {
          punto.className = ev.ia ? "jv-dot" : "jv-dot off";
          txt.textContent = ev.ia ? "Asistente con IA activo" : "Modo sin IA disponible";
        }
        if (ev.aviso) {
          quitarTag();
          var nota = h("div", "jv-error");
          nota.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/></svg>';
          nota.appendChild(h("span", null, ev.aviso));
          cuerpo.insertBefore(nota, destino);
        }
      } else if (ev.tipo === "reinicio") {
        acumulado = "";
        destino.innerHTML = "";
        quitarTag();
      } else if (ev.tipo === "delta" && ev.texto) {
        quitarTag();
        acumulado += ev.texto;
        pintar();
      } else if (ev.tipo === "opciones" && ev.opciones && ev.opciones.length) {
        quitarTag();
        var sug = h("div", "jv-fuentes");
        ev.opciones.forEach(function (o) {
          var b = h("button", "jv-chip", o.t);
          b.onclick = function () { preguntar(o.t); };
          sug.appendChild(b);
        });
        cuerpo.appendChild(sug);
      } else if (ev.tipo === "fin") {
        finalizar(ev.texto, ev.fuentes);
      } else if (ev.tipo === "error") {
        error(ev.texto || "No pude responder.");
      }
    }

    function bombo() {
      return opciones.then(function (reader) {
        function paso() {
          return reader.read().then(function (r) {
            if (r.done) { if (buf) manejar(buf); return; }
            buf += dec ? dec.decode(r.value, { stream: true }) : String(r.value);
            var trozos = buf.split("\n\n");
            buf = trozos.pop();
            trozos.forEach(manejar);
            return paso();
          });
        }
        return paso();
      }).catch(function (e) {
        if (e && e.name === "AbortError") {
          // El usuario detuvo: se cierra el turno una sola vez con lo que haya
          // llegado. Sin esto el .then de abajo volveria a finalizar el turno y
          // duplicaria los botones de copiar/regenerar.
          cancelando = true;
          finalizar(acumulado, null);
          return;
        }
        error("No pudimos conectarnos con el asistente. Revisa tu conexión e inténtalo de nuevo.");
      }).then(function () {
        if (!terminado && !acumulado) error("No hubo respuesta del asistente.");
        else if (!terminado) finalizar(acumulado, null);
      });
    }

    bombo();
  }

  function detener() {
    if (ctrl) { try { ctrl.abort(); } catch (e) {} }
    ctrl = null;
    generando = false;
    estadoBoton(false);
  }

  /* ------------------------------------------------------------ acciones */
  function acciones(bot, cuerpo, texto) {
    var cont = h("div", "jv-acts");

    var c1 = h("button", "jv-act");
    c1.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>Copiar';
    c1.onclick = function () {
      if (copiar(texto)) { c1.classList.add("hecho"); setTimeout(function () { c1.classList.remove("hecho"); }, 1300); }
    };
    cont.appendChild(c1);

    var c2 = h("button", "jv-act");
    c2.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M23 4v6h-6M1 20v-6h6"/><path d="M20.5 9a9 9 0 0 0-15-3.4L1 10M23 14l-3.5 3.4a9 9 0 0 1-15-3.4"/></svg>Otra vez';
    c2.onclick = function () {
      if (bot.parentNode) bot.parentNode.removeChild(bot);
      for (var i = turnos.length - 1; i >= 0; i--) {
        if (turnos[i].rol === "bot") { turnos.splice(i, 1); break; }
      }
      pedir(ultima);
    };
    cont.appendChild(c2);

    var c3 = h("button", "jv-act");
    c3.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/></svg>Agendar cita';
    c3.onclick = function () { panelCita(cuerpo); };
    cont.appendChild(c3);

    var c4 = h("button", "jv-act");
    c4.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="4" width="20" height="16" rx="2"/><path d="M22 7l-10 6L2 7"/></svg>Enviar a mi correo';
    c4.onclick = function () { modal.hidden = false; document.getElementById("jvMailInput").focus(); };
    cont.appendChild(c4);

    bot.appendChild(cont);
  }

  /* --------------------------------------------------------- panel de cita */
  function panelCita(cuerpo) {
    if (cuerpo.querySelector(".jv-cita")) return;

    var p = h("div", "jv-cita");
    var head = h("div", "jv-cita-head");
    head.appendChild(h("b", null, "Aparta tu cita"));
    head.appendChild(h("span", null, "Consulta inicial sin costo. Te confirmamos por correo."));
    p.appendChild(head);

    var body = h("div", "jv-cita-body");

    var bloqueFechas = h("div");
    bloqueFechas.appendChild(h("h4", null, "Día"));
    var fechas = h("div", "jv-fechas");
    bloqueFechas.appendChild(fechas);
    body.appendChild(bloqueFechas);

    var bloqueHoras = h("div");
    bloqueHoras.appendChild(h("h4", null, "Hora"));
    var horas = h("div", "jv-horas");
    bloqueHoras.appendChild(horas);
    body.appendChild(bloqueHoras);

    var elegido = { fecha: null, hora: null };

    function pintarHoras() {
      horas.innerHTML = "";
      if (!elegido.fecha) {
        horas.appendChild(h("span", null, "Elige primero un día."));
        return;
      }
      fetch("/api/jarvis/disponibilidad").then(function (r) { return r.json(); })
        .then(function (d) {
          var dia = null;
          for (var i = 0; i < (d.dias || []).length; i++) {
            if (d.dias[i].fecha === elegido.fecha) { dia = d.dias[i]; break; }
          }
          if (!dia || !dia.horas.length) {
            horas.appendChild(h("span", null, "Ese día ya no tiene horas libres."));
            return;
          }
          dia.horas.forEach(function (hh) {
            var b = h("button", "jv-ficha", hh);
            b.setAttribute("aria-pressed", elegido.hora === hh ? "true" : "false");
            b.onclick = function () {
              elegido.hora = hh;
              pintarHoras();
              validar();
            };
            horas.appendChild(b);
          });
        }).catch(function () {
          horas.appendChild(h("span", null, "No pudimos consultar la disponibilidad."));
        });
    }

    fetch("/api/jarvis/disponibilidad").then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.dias || !d.dias.length) {
          fechas.appendChild(h("span", null, "Por ahora no hay días con agenda abierta."));
          return;
        }
        d.dias.forEach(function (dd) {
          var b = h("button", "jv-ficha", dd.etiqueta);
          b.setAttribute("aria-pressed", elegido.fecha === dd.fecha ? "true" : "false");
          b.onclick = function () {
            elegido.fecha = dd.fecha;
            elegido.hora = null;
            var fs = fechas.querySelectorAll(".jv-ficha");
            for (var i = 0; i < fs.length; i++) fs[i].setAttribute("aria-pressed", "false");
            b.setAttribute("aria-pressed", "true");
            pintarHoras();
            validar();
          };
          fechas.appendChild(b);
        });
      }).catch(function () {
        fechas.appendChild(h("span", null, "No pudimos consultar la disponibilidad."));
      });

    var dos = h("div", "jv-dos");
    var cNombre = h("div", "jv-campo");
    cNombre.appendChild(h("label", null, "Nombre completo"));
    var iNombre = h("input");
    iNombre.type = "text";
    iNombre.placeholder = "Tu nombre";
    cNombre.appendChild(iNombre);

    var cCorreo = h("div", "jv-campo");
    cCorreo.appendChild(h("label", null, "Correo"));
    var iCorreo = h("input");
    iCorreo.type = "email";
    iCorreo.placeholder = "tucorreo@ejemplo.com";
    cCorreo.appendChild(iCorreo);

    dos.appendChild(cNombre);
    dos.appendChild(cCorreo);
    body.appendChild(dos);

    var dos2 = h("div", "jv-dos");
    var cTel = h("div", "jv-campo");
    cTel.appendChild(h("label", null, "Teléfono (opcional)"));
    var iTel = h("input");
    iTel.type = "tel";
    iTel.placeholder = "+57 300 000 0000";
    cTel.appendChild(iTel);

    var cMotivo = h("div", "jv-campo");
    cMotivo.appendChild(h("label", null, "Motivo (opcional)"));
    var iMotivo = h("input");
    iMotivo.type = "text";
    iMotivo.placeholder = "Ej. despido sin carta";
    cMotivo.appendChild(iMotivo);

    dos2.appendChild(cTel);
    dos2.appendChild(cMotivo);
    body.appendChild(dos2);

    var btnCita = h("button", "jv-enviar-cita", "Confirmar cita");
    btnCita.disabled = true;
    body.appendChild(btnCita);

    var msg = h("div", "jv-cita-msg");
    body.appendChild(msg);

    var cierra = h("button", "jv-cita-cierra", "Ahora no, gracias");
    body.appendChild(cierra);

    function validar() {
      btnCita.disabled = !(elegido.fecha && elegido.hora);
    }

    function avisarCita(txt, clase) {
      msg.textContent = txt;
      msg.className = "jv-cita-msg " + (clase || "");
    }

    btnCita.onclick = function () {
      btnCita.disabled = true;
      avisarCita("Apartando…", "");
      fetch("/api/jarvis/cita", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          fecha: elegido.fecha,
          hora: elegido.hora,
          nombre: iNombre.value.trim(),
          correo: iCorreo.value.trim(),
          telefono: iTel.value.trim(),
          motivo: iMotivo.value.trim()
        })
      }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
        .then(function (res) {
          if (!res.ok || !res.j.ok) {
            avisarCita(res.j.error || "No pudimos apartar la cita.", "err");
            btnCita.disabled = false;
            return;
          }
          avisarCita(res.j.texto, "ok");
          btnCita.textContent = "Cita apartada";
          btnCita.disabled = true;
        }).catch(function () {
          avisarCita("No pudimos conectarnos. Intenta de nuevo.", "err");
          btnCita.disabled = false;
        });
    };

    cierra.onclick = function () { if (p.parentNode) p.parentNode.removeChild(p); };

    p.appendChild(body);
    cuerpo.appendChild(p);
    anclar();
  }

  /* ------------------------------------------------------- exportar correo */
  document.getElementById("jvMailForm").addEventListener("submit", function (e) {
    e.preventDefault();
    var correo = document.getElementById("jvMailInput").value.trim();
    var salida = document.getElementById("jvMailMsg");
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(correo)) {
      salida.textContent = "Escribe un correo válido.";
      salida.className = "jv-modal-msg err";
      return;
    }
    salida.textContent = "Enviando…";
    salida.className = "jv-modal-msg";
    var lista = [];
    for (var i = 0; i < turnos.length; i++) {
      lista.push({ rol: turnos[i].rol === "user" ? "usuario" : "bot", texto: turnos[i].texto });
    }
    fetch("/chat/enviar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ correo: correo, mensajes: lista })
    }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (res) {
        if (!res.ok || !res.j.ok) {
          salida.textContent = res.j.error || "No se pudo enviar.";
          salida.className = "jv-modal-msg err";
        } else {
          salida.textContent = "Listo, te enviamos la conversación.";
          salida.className = "jv-modal-msg ok";
        }
      }).catch(function () {
        salida.textContent = "No se pudo enviar.";
        salida.className = "jv-modal-msg err";
      });
  });
  document.getElementById("jvMailCerrar").onclick = function () {
    modal.hidden = true;
    document.getElementById("jvMailMsg").textContent = "";
  };

  /* ------------------------------------------------------------- historial */
  function guardarHistorial() {
    try {
      var solo = [];
      for (var i = turnos.length - 1; i >= 0 && solo.length < 20; i--) {
        if (turnos[i].rol === "user") solo.push(turnos[i].texto);
      }
      localStorage.setItem("jv_hist", JSON.stringify(solo.slice(0, 10)));
      pintarRail(solo);
    } catch (e) {}
  }

  function pintarRail(lista) {
    if (!railHist) return;
    railHist.innerHTML = "";
    var ult = [];
    for (var i = turnos.length - 1; i >= 0 && ult.length < 8; i--) {
      if (turnos[i].rol === "user") ult.push(turnos[i].texto);
    }
    if (!ult.length && lista) ult = lista;
    for (var j = 0; j < ult.length; j++) {
      var it = h("button", "jv-hist-item");
      it.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>';
      it.appendChild(h("span", null, ult[j].length > 34 ? ult[j].slice(0, 34) + "…" : ult[j]));
      (function (t) { it.onclick = function () { preguntar(t); }; })(ult[j]);
      railHist.appendChild(it);
    }
  }

  /* --------------------------------------------------------------- chip CTA */
  var chips = document.querySelectorAll(".jv-chip");
  for (var ci = 0; ci < chips.length; ci++) {
    (function (b) { b.onclick = function () { preguntar(b.textContent.trim()); }; })(chips[ci]);
  }

  /* ----------------------------------------------------------------- hero */
  var heroAbrir = document.getElementById("jvHeroAbrir");
  if (heroAbrir) {
    heroAbrir.onclick = function () { wrap.hidden = false; document.body.style.overflow = "hidden"; };
  }

  /* ------------------------------------------------------------- arranque */
  wrap.hidden = true;
  pintarVacio();
  estadoBoton(false);
  try {
    var prev = JSON.parse(localStorage.getItem("jv_hist") || "[]");
    if (prev.length) pintarRail(prev);
  } catch (e) {}
})();