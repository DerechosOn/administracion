/* ==========================================================================
   Asistente IAT — agente experto para construir, evaluar y radicar proyectos
   de aprovechamiento ante la alcaldía. Streaming SSE, markdown progresivo,
   ficha sincronizada, carga de documento y evaluación con puntaje real.
   ========================================================================== */
(function () {
  "use strict";

  var wrap    = document.getElementById("iatAsis");
  if (!wrap) return;

  var hilo    = document.getElementById("iatHilo");
  var entrada = document.getElementById("iatEntrada");
  var btn     = document.getElementById("iatEnviar");
  var estado  = document.getElementById("iatEstado");
  var dot     = document.getElementById("iatDot");
  var eva     = document.getElementById("iatEva");
  var evaNum  = document.getElementById("iatPuntaje");
  var evaBar  = document.getElementById("iatBarra");
  var evaCuer = document.getElementById("iatEvaCuerpo");
  var evaInst = document.getElementById("iatInst");
  var fichero = document.getElementById("iatDoc");
  var docEst  = document.getElementById("iatDocEstado");
  var form    = document.getElementById("iatForm");
  var inputTipos = document.getElementById("iatTiposJson");
  var org     = document.getElementById("iatOrganizacion");

  var tipos = [];
  try { tipos = JSON.parse(inputTipos ? inputTipos.value : "[]"); } catch (e) {}
  var TIPO_DEF = (tipos.length && tipos.indexOf("Aprovechamiento") !== -1)
    ? "Aprovechamiento" : "Aprovechamiento";

  var ctrl = null;
  var generando = false;
  var cancelando = false;
  var turnos = [];
  var proyecto = {};
  var documentoTexto = "";
  var ultimaEvaluacion = null;
  var CHAT_KEY = "iat_chat_hist";

  /* ---------------------------------------------------------------- utils */
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
  function md(txt) {
    var s = esc(txt).replace(/\r/g, "");
    var out = [], L = s.split("\n"), i = 0;
    while (i < L.length) {
      var l = L[i];
      if (/^###\s+/.test(l)) { out.push("<h4>" + inl(l.replace(/^###\s+/, "")) + "</h4>"); i++; continue; }
      if (/^##\s+/.test(l)) { out.push("<h3>" + inl(l.replace(/^##\s+/, "")) + "</h3>"); i++; continue; }
      if (/^(---+|\*\*\*+)$/.test(l.trim())) { out.push("<hr>"); i++; continue; }
      if (/^>\s?/.test(l)) {
        var q = [];
        while (i < L.length && /^>\s?/.test(L[i])) { q.push(L[i].replace(/^>\s?/, "")); i++; }
        out.push("<blockquote>" + inl(q.join(" ")) + "</blockquote>");
        continue;
      }
      if (/^\s*\[\s*\]\s+/.test(l) || /^\s*\[x\]\s+/i.test(l)) {
        var cl = [];
        while (i < L.length && /^\s*\[[ x]\]\s+/i.test(L[i])) {
          var marc = /^\s*\[x\]/i.test(L[i]) ? "✔" : "☐";
          cl.push("<li>" + marc + " " + inl(L[i].replace(/^\s*\[[ x]\]\s+/i, "")) + "</li>"); i++;
        }
        out.push("<ul>" + cl.join("") + "</ul>");
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
      if (/^\|/.test(l)) {
        var tb = [];
        while (i < L.length && /^\|/.test(L[i])) {
          tb.push(L[i].replace(/^\||\|$/g, "").split("|").map(function (c) { return c.trim(); }));
          i++;
        }
        var ht = [];
        tb.forEach(function (r, ri) {
          if (ri === 1 && r.every(function (c) { return /^:?-{2,}:?$/.test(c); })) return;
          var tr = h("tr");
          r.forEach(function (c, ci) {
            var cel = h(ri === 0 ? "th" : "td", null, c.replace(/\*\*(.+?)\*\*/g, "$1"));
            tr.appendChild(cel);
          });
          ht.push(tr.outerHTML);
        });
        out.push("<table><tbody>" + ht.join("") + "</tbody></table>");
        continue;
      }
      if (!l.trim()) { i++; continue; }
      var p = [];
      while (i < L.length && L[i].trim() &&
             !/^(#{1,4}\s|>\s?|\s*[-*]\s|\s*\d+[.)]\s|^\s*\[[ x]\]|^|)/.test(L[i])) {
        p.push(L[i]); i++;
      }
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
  function reloj() {
    var d = new Date();
    return ("0" + d.getHours()).slice(-2) + ":" + ("0" + d.getMinutes()).slice(-2);
  }

  /* ------------------------------------------------------------- ficha */
  var campos = {};

  function leerFicha() {
    var el = wrap.querySelectorAll("[data-iat]");
    for (var i = 0; i < el.length; i++) {
      var n = el[i].getAttribute("data-iat");
      var v = el[i].value != null ? el[i].value.trim() : "";
      campos[n] = v;
    }
    return campos;
  }
  function escribirFicha(datos) {
    if (!datos) return;
    var el = wrap.querySelectorAll("[data-iat]");
    for (var i = 0; i < el.length; i++) {
      var n = el[i].getAttribute("data-iat");
      if (datos[n] !== undefined && datos[n] !== null && String(datos[n]) !== "") {
        if (el[i].tagName === "SELECT") {
          var encontro = false;
          for (var j = 0; j < el[i].options.length; j++) {
            if (el[i].options[j].value === String(datos[n])) { el[i].selectedIndex = j; encontro = true; break; }
          }
          if (!encontro) el[i].selectedIndex = 0;
        } else {
          el[i].value = String(datos[n]);
        }
      }
    }
    leerFicha();
  }
  wrap.addEventListener("input", function () { leerFicha(); });

  function sincroniza(datosDesdeAgente) {
    if (!datosDesdeAgente) return 0;
    var antes = JSON.stringify(campos);
    escribirFicha(datosDesdeAgente);
    var n = 0;
    for (var k in datosDesdeAgente) {
      if (datosDesdeAgente[k] && String(datosDesdeAgente[k]) !== "" && campos[k] === String(datosDesdeAgente[k])) n++;
    }
    return n;
  }

  /* ------------------------------------------------------------- chat */
  function vacio() {
    var v = h("div", "iat-vacio");
    v.appendChild(h("h4", null, "¿En qué te ayudo?"));
    v.appendChild(h("p", null, "Soy el agente experto en el Incentivo al Aprovechamiento (IAT). " +
      "Guío la construcción del proyecto, consulto la normatividad de tu municipio y evalúo tu proyecto con un puntaje real."));
    var sug = h("div", "iat-sug");
    ["¿Qué normatividad aplica en mi municipio?", "¿Qué requisitos exigen para radicar?",
     "Ayúdame a armar el proyecto paso a paso", "¿Cómo calculan el incentivo?"].forEach(function (p) {
      var b = h("button", "iat-chip", p);
      b.onclick = function () { preguntar(p); };
      sug.appendChild(b);
    });
    v.appendChild(sug);
    hilo.appendChild(v);
  }
  function quitarVacio() {
    var v = hilo.querySelector(".iat-vacio");
    if (v && v.parentNode) v.parentNode.removeChild(v);
  }
  function anclar() { hilo.scrollTop = hilo.scrollHeight; }
  function avisoUsuario(txt) {
    var n = h("div", "iat-nota", txt);
    hilo.appendChild(n);
    anclar();
  }

  function preguntar(texto) {
    if (!texto.trim()) return;
    if (generando) detener();
    quitarVacio();
    leerFicha();

    var yo = h("div", "iat-msg user");
    yo.appendChild(h("div", "iat-msg-bur", texto));
    hilo.appendChild(yo);
    turnos.push({ rol: "user", texto: texto });
    anclar();
    pedir(texto);
  }

  btn.onclick = function () { preguntar(entrada.value); entrada.value = ""; };
  entrada.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); btn.click(); }
  });

  function pedir(texto) {
    generando = true;
    btn.disabled = true;
    ctrl = window.AbortController ? new AbortController() : null;

    var bot = h("div", "iat-msg bot");
    var head = h("div", "iat-msg-head");
    head.appendChild(h("span", "iat-orb-sm"));
    head.appendChild(h("b", null, "Agente IAT"));
    head.appendChild(h("span", "iat-time", reloj()));
    var tag = h("span", "iat-pensando", "consultando normatividad…");
    head.appendChild(tag);
    bot.appendChild(head);
    var cuerpo = h("div", "iat-md");
    var destino = h("div", "iat-md");
    cuerpo.appendChild(destino);
    bot.appendChild(cuerpo);
    hilo.appendChild(bot);
    anclar();

    var escala = setTimeout(function () { tag.textContent = "analizando tu proyecto…"; }, 2400);
    var acumulado = "";
    var terminado = false;
    cancelando = false;

    function quitarTag() { clearTimeout(escala); if (tag.parentNode) tag.parentNode.removeChild(tag); }
    function pintar() { destino.innerHTML = md(acumulado); anclar(); }

    function finalizar(textoFinal, datosAg) {
      if (terminado) return;
      terminado = true;
      clearTimeout(escala);
      quitarTag();
      if (!acumulado && textoFinal) { acumulado = textoFinal; pintar(); }
      if (textoFinal) {
        turnos.push({ rol: "bot", texto: textoFinal });
        var n = sincroniza(datosAg);
        if (datosAg && n > 0) avisoUsuario("Reconocí datos del proyecto y los coloqué en la ficha de la derecha.");
      }
      generando = false;
      btn.disabled = false;
      anclar();
    }
    function error(txt) {
      if (terminado) return;
      terminado = true;
      clearTimeout(escala);
      quitarTag();
      var e = h("div", "iat-error");
      e.appendChild(h("span", null, txt));
      cuerpo.appendChild(e);
      generando = false;
      btn.disabled = false;
      anclar();
    }

    var fetchP = fetch("/api/asociacion/iat/agente", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mensaje: texto, proyecto: campos }),
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
        if (estado) estado.textContent = (ev.ia ? "Experto con IA activo" : "Modo guía (IA no configurada)");
        if (dot) dot.className = ev.ia ? "iat-dot" : "iat-dot off";
        if (ev.aviso) { quitarTag(); avisoUsuario(ev.aviso); }
        if (ev.extraidos && ev.extraidos.length) {
          avisoUsuario("Extraje del mensaje: " + ev.extraidos.join(", ") + ".");
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
        var sug = h("div", "iat-sug");
        ev.opciones.forEach(function (o) {
          var b = h("button", "iat-chip", o);
          b.onclick = function () { preguntar(o); };
          sug.appendChild(b);
        });
        cuerpo.appendChild(sug);
      } else if (ev.tipo === "fin") {
        finalizar(ev.texto, ev.datos);
      } else if (ev.tipo === "error") {
        error(ev.texto || "No pude responder.");
      }
    }

    function bombo() {
      return fetchP.then(function (reader) {
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
          cancelando = true;
          finalizar(acumulado, null);
          return;
        }
        error("No pudimos conectarnos con el agente. Revisa tu conexión e inténtalo de nuevo.");
      }).then(function () {
        if (!terminado && !acumulado) error("No hubo respuesta del agente.");
        else if (!terminado) finalizar(acumulado, null);
      });
    }
    bombo();
  }

  function detener() {
    if (ctrl) { try { ctrl.abort(); } catch (e) {} }
    ctrl = null;
    generando = false;
    btn.disabled = false;
  }

  /* ------------------------------------------------------ carga documento */
  fichero.addEventListener("change", function () {
    var f = fichero.files && fichero.files[0];
    if (!f) return;
    if (!/\.(txt|md|pdf|docx)$/i.test(f.name)) {
      docEst.textContent = "Formato no permitido. Usa TXT, MD, PDF o DOCX.";
      return;
    }
    if (f.size > 8 * 1024 * 1024) {
      docEst.textContent = "El archivo supera los 8 MB.";
      return;
    }
    docEst.textContent = "Cargando y extrayendo el texto del documento…";
    var fd = new FormData();
    fd.append("documento", f);

    fetch("/api/asociacion/iat/subir", { method: "POST", body: fd })
      .then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (res) {
        if (!res.ok || !res.j.ok) {
          docEst.textContent = res.j.error || "No se pudo cargar el documento.";
          return;
        }
        documentoTexto = res.j.texto || "";
        leerFicha();
        campos.documento = res.j.guardado;
        docEst.textContent = "Documento cargado: " + res.j.archivo +
          " (" + res.j.tamano.toLocaleString() + " caracteres extraídos). Listo para evaluar.";
        if (res.j.archivo) {
          avisoUsuario("Recibí el documento «" + res.j.archivo +
            "» y ya extraje su contenido para la evaluación del proyecto.");
        }
      }).catch(function () {
        docEst.textContent = "No se pudo conectar con el servidor al cargar el documento.";
      });
  });

  /* ------------------------------------------------------------ evaluación */
  function colorear(nota) {
    if (nota >= 80) return "alta";
    if (nota >= 60) return "media";
    return "baja";
  }
  function copiarTexto(t) {
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
  function tituloEva(t) { var hh = h("h4", "iat-ev-tit", t); return hh; }
  function lista(html, arr) {
    if (!arr || !arr.length) return;
    var u = h("ul");
    arr.forEach(function (x) { u.appendChild(h("li", null, x)); });
    html.appendChild(u);
  }

  document.getElementById("iatEvaluar").onclick = function () {
    leerFicha();
    document.getElementById("iatEvaluar").disabled = true;
    document.getElementById("iatEvaluar").textContent = "Evaluando…";
    fetch("/api/asociacion/iat/evaluar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ proyecto: campos, documento_texto: documentoTexto })
    }).then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); })
      .then(function (res) {
        document.getElementById("iatEvaluar").disabled = false;
        document.getElementById("iatEvaluar").textContent = "Evaluar proyecto";
        if (!res.ok || !res.j.ok) {
          avisoUsuario(res.j.error || "No se pudo evaluar el proyecto.");
          return;
        }
        ultimaEvaluacion = res.j.puntaje;
        campos.checklist = "1";
        pintarEvaluacion(res.j);
        eva.hidden = false;
        eva.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }).catch(function () {
        document.getElementById("iatEvaluar").disabled = false;
        document.getElementById("iatEvaluar").textContent = "Evaluar proyecto";
        avisoUsuario("No pudimos conectar con el servidor para evaluar.");
      });
  };

  function pintarEvaluacion(j) {
    var p = j.puntaje;
    evaNum.textContent = p;
    evaBar.style.width = p + "%";
    evaBar.style.background = p >= 80 ? "#1f9d55" : (p >= 60 ? "#e8a400" : "#c0392b");
    evaCuer.classList.remove("alta", "media", "baja");
    evaCuer.classList.add(colorear(p));

    var body = document.createElement("div");
    if (j.informe) {
      body.innerHTML = md(j.informe);
    } else {
      body.appendChild(tituloEva("Resultado determinista del agente"));
      body.appendChild(h("p", "iat-gris", "El puntaje lo calcula una rúbrica verificable (no lo inventa la IA)."));
      var t = h("table", "iat-tab");
      var cab = h("tr");
      ["Criterio", "Puntos", "Máximo", "Detalle"].forEach(function (c) {
        var th = h("th", null, c); cab.appendChild(th);
      });
      t.appendChild(cab);
      (j.desglose || []).forEach(function (d) {
        var tr = h("tr");
        tr.appendChild(h("td", null, d.criterio));
        tr.appendChild(h("td", null, d.puntos));
        tr.appendChild(h("td", null, d.max));
        tr.appendChild(h("td", "iat-det", d.detalle));
        t.appendChild(tr);
      });
      var trTotal = h("tr");
      trTotal.appendChild(h("td", "iat-fuerte", "Total"));
      trTotal.appendChild(h("td", "iat-fuerte", p));
      trTotal.appendChild(h("td", null, "100"));
      trTotal.appendChild(h("td", null, ""));
      t.appendChild(trTotal);
      body.appendChild(t);
      body.appendChild(tituloEva("Fortalezas"));
      lista(body, j.fortalezas);
      body.appendChild(tituloEva("Debilidades"));
      lista(body, j.debilidades);
      body.appendChild(tituloEva("Cambios que debes realizar"));
      lista(body, j.cambios);
    }
    evaCuer.innerHTML = "";
    evaCuer.appendChild(body);

    evaInst.innerHTML = "";
    if (j.instrumentos && j.instrumentos.length) {
      evaInst.appendChild(tituloEva("Instrumentos de radicación"));
      j.instrumentos.forEach(function (ins) {
        var det = h("details", "iat-inst");
        det.appendChild(h("summary", null, ins.titulo));
        var pre = h("pre", "iat-pre", ins.texto);
        var bC = h("button", "iat-copiar", "Copiar");
        bC.onclick = function () {
          if (copiarTexto(ins.texto)) { bC.textContent = "Copiado"; setTimeout(function () { bC.textContent = "Copiar"; }, 1500); }
        };
        det.appendChild(bC);
        det.appendChild(pre);
        evaInst.appendChild(det);
      });
    }
  }

  /* -------------------------------------------------------------- radicar */
  document.getElementById("iatRadicar").onclick = function () {
    leerFicha();
    var titulo = campos.titulo;
    var desc = campos.descripcion;
    if (!titulo || titulo.length < 8) {
      avisoUsuario("Falta el título del proyecto (mínimo 8 caracteres) antes de radicar.");
      return;
    }
    if (!desc || desc.length < 10) {
      avisoUsuario("Falta la descripción del proyecto antes de radicar.");
      return;
    }
    if (ultimaEvaluacion == null) {
      if (!window.confirm("Aún no has evaluado el proyecto. ¿Radicar igualmente sin puntaje?")) return;
    }
    var datos = {
      titulo: titulo, tipo: campos.tipo || TIPO_DEF, municipio: campos.municipio || "",
      toneladas: campos.toneladas || "0", censo: campos.censo || "0",
      asociados_pct: campos.asociados_pct || "0", formalizacion: campos.formalizacion || "en_formalizacion",
      meta_reduccion: campos.meta_reduccion || "", acuerdos: campos.acuerdos || "",
      descripcion: desc, documento_archivo: campos.documento || "",
      checklist: ultimaEvaluacion != null ? "1" : "",
      evaluacion_puntaje: ultimaEvaluacion != null ? String(ultimaEvaluacion) : ""
    };
    form.innerHTML = "";
    Object.keys(datos).forEach(function (k) {
      var inp = h("input");
      inp.type = "hidden";
      inp.name = k;
      inp.value = datos[k];
      form.appendChild(inp);
    });
    form.submit();
  };

  /* -------------------------------------------------------------- arranque */
  vacio();
})();