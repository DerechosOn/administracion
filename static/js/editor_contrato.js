/* Editor de contratos estilo Word + panel de apoyo juridico con IA.
   Sin dependencias externas: usa contenteditable y document.execCommand. */
(function () {
  'use strict';

  var raiz = document.getElementById('doc-constructor');
  if (!raiz) return;

  var area = document.getElementById('plantilla');            // contenteditable
  var fuente = document.getElementById('plantilla-fuente');   // vista HTML
  var oculto = document.getElementById('plantilla-input');   // hidden del formulario
  var contador = document.getElementById('ct-contador');
  var aviso = document.getElementById('doc-aviso');
  var chips = document.querySelectorAll('.ct-chip');
  var rango = null;

  /* ---------- estado del documento ---------- */
  function fuenteVisible() {
    return !fuente.hidden && fuente.style.display !== 'none';
  }

  function htmlActual() {
    if (fuenteVisible()) return fuente.value;
    return area.innerHTML;
  }

  function sincronizar() {
    oculto.value = htmlActual();
    var texto = area.innerText || '';
    var palabras = texto.trim() ? texto.trim().split(/\s+/).length : 0;
    if (contador) {
      contador.textContent = palabras.toLocaleString('es-CO') + ' palabras · ' +
        texto.length.toLocaleString('es-CO') + ' caracteres';
    }
    if (aviso && !aviso.dataset.fijo) aviso.textContent = 'Cambios sin guardar.';
  }

  function guardarRango() {
    var sel = window.getSelection();
    if (sel && sel.rangeCount && area.contains(sel.anchorNode)) rango = sel.getRangeAt(0).cloneRange();
  }

  function recuperarRango() {
    if (!rango) return;
    area.focus();
    var sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(rango);
  }

  function ejecutar(comando, valor) {
    area.focus();
    if (rango) {
      var sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(rango);
    }
    document.execCommand(comando, false, valor || null);
    guardarRango();
    sincronizar();
  }

  function insertarHTML(html) {
    if (!rango) {
      area.focus();
      var sel = window.getSelection();
      var r = document.createRange();
      r.selectNodeContents(area);
      r.collapse(false);
      sel.removeAllRanges();
      sel.addRange(r);
      rango = r;
    }
    recuperarRango();
    rango.deleteContents();
    var frag = document.createRange().createContextualFragment(html);
    rango.insertNode(frag);
    rango.collapse(false);
    guardarRango();
    sincronizar();
  }

  /* ---------- barra de herramientas ---------- */
  raiz.querySelectorAll('[data-comando]').forEach(function (boton) {
    boton.addEventListener('mousedown', function (e) { e.preventDefault(); });
    boton.addEventListener('click', function () {
      var comando = boton.dataset.comando;
      if (comando === 'link') {
        var url = window.prompt('Dirección del enlace (https://…):', 'https://');
        if (url) ejecutar('createLink', url);
        return;
      }
      if (comando === 'bloque') {
        ejecutar('formatBlock', boton.dataset.valor || '<p>');
        return;
      }
      ejecutar(comando);
    });
  });

  raiz.querySelectorAll('[data-lista]').forEach(function (boton) {
    boton.addEventListener('mousedown', function (e) { e.preventDefault(); });
    boton.addEventListener('click', function () {
      raiz.querySelectorAll('[data-lista]').forEach(function (b) { b.classList.remove('activo'); });
      boton.classList.add('activo');
      ejecutar(boton.dataset.lista === 'ul' ? 'insertUnorderedList' : 'insertOrderedList');
    });
  });

  chips.forEach(function (chip) {
    chip.addEventListener('mousedown', function (e) { e.preventDefault(); });
    chip.addEventListener('click', function () { insertarHTML(chip.dataset.token); });
  });

  /* ---------- vista HTML ---------- */
  var btnFuente = document.getElementById('doc-fuente');
  if (btnFuente) {
    btnFuente.addEventListener('click', function () {
      if (fuenteVisible()) {
        area.innerHTML = fuente.value;
        fuente.hidden = true;
        fuente.style.display = 'none';
        area.style.display = '';
        area.hidden = false;
        btnFuente.textContent = 'Ver HTML';
        btnFuente.title = 'Ver el código HTML de la plantilla';
      } else {
        fuente.value = area.innerHTML;
        fuente.hidden = false;
        fuente.style.display = 'block';
        area.style.display = 'none';
        area.hidden = true;
        btnFuente.textContent = 'Ver documento';
        btnFuente.title = 'Volver al documento con formato';
      }
      sincronizar();
    });
  }

  /* ---------- pegado sin formato de Word ---------- */
  area.addEventListener('paste', function (e) {
    if (e.altKey) return;                       // Alt+V: pegar con formato
    var texto = (e.clipboardData || window.clipboardData).getData('text/plain');
    if (!texto) return;
    e.preventDefault();
    var lineas = texto.split(/\r?\n/);
    document.execCommand('insertText', false, lineas.join('\n'));
    sincronizar();
  });

  area.addEventListener('input', sincronizar);
  area.addEventListener('keyup', guardarRango);
  area.addEventListener('mouseup', guardarRango);
  document.addEventListener('selectionchange', function () {
    if (document.activeElement === area) guardarRango();
  });
  area.addEventListener('keydown', function (e) {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
      e.preventDefault();
      var formulario = document.getElementById('form-contrato');
      if (formulario && formulario.requestSubmit) formulario.requestSubmit();
    }
  });

  /* Red de seguridad: los botones del formulario publican el HTML vigente. */
  document.querySelectorAll('form#form-contrato').forEach(function (form) {
    form.addEventListener('submit', function () { oculto.value = htmlActual(); });
  });

  /* ---------- panel de IA ---------- */
  var ia = document.getElementById('ia-panel');
  if (!ia) { sincronizar(); return; }

  var estado = JSON.parse(ia.dataset.config || '{}');
  var salida = document.getElementById('ia-salida');
  var respuesta = document.getElementById('ia-respuesta');
  var entradaChat = document.getElementById('ia-pregunta');
  var tema = document.getElementById('ia-tema');
  var temaLibre = document.getElementById('ia-tema-libre');
  var honorarios = document.getElementById('ia-honorarios');
  var chat = document.getElementById('ia-chat');
  var botonEnviar = document.getElementById('ia-enviar');
  var historial = [];
  var ultima = '';

  function hablar(quien, texto) {
    var fila = document.createElement('div');
    fila.className = 'ia-burbuja ' + (quien === 'yo' ? 'ia-yo' : 'ia-ella');
    fila.textContent = texto;
    chat.appendChild(fila);
    chat.scrollTop = chat.scrollHeight;
  }

  function ocupado(activo) {
    ia.querySelectorAll('button').forEach(function (b) { b.disabled = activo || !estado.configurado; });
    if (botonEnviar) botonEnviar.disabled = activo || !estado.configurado;
    salida.textContent = activo ? 'La IA esta escribiendo…' : '';
    salida.classList.toggle('esperando', activo);
  }

  function pedir(accion) {
    if (!estado.configurado) return;
    var seleccion = '';
    try { seleccion = String(window.getSelection()) || ''; } catch (e) { seleccion = ''; }
    var eleccion = (tema && tema.value) || '';
    var temaTexto = eleccion;
    if (eleccion === 'libre') temaTexto = ((temaLibre && temaLibre.value) || '').trim();
    var cuerpo = {
      accion: accion,
      tema: temaTexto,
      honorarios: (honorarios && honorarios.value) || '',
      pregunta: (accion === 'chat') ? ((entradaChat && entradaChat.value) || '').trim() : '',
      documento: area.innerHTML,
      texto_seleccion: seleccion,
      historial: historial
    };
    if (accion === 'chat' && !cuerpo.pregunta) { salida.textContent = 'Escribe la pregunta.'; return; }
    if (accion === 'redactar' && !temaTexto) {
      salida.textContent = 'Elige o escribe la cláusula que necesitas.';
      return;
    }

    if (accion === 'chat') hablar('yo', cuerpo.pregunta);
    else hablar('yo', (ia.querySelector('[data-accion="' + accion + '"]') || {}).dataset.nombre || accion);
    historial.push({ rol: 'usuario', contenido: cuerpo.pregunta || cuerpo.tema || accion });
    ocupado(true);
    respuesta.innerHTML = '';
    document.getElementById('ia-insertar').style.display = 'none';

    fetch(ia.dataset.url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(cuerpo)
    }).then(function (r) {
      return r.json().then(function (d) { return { ok: r.ok, datos: d }; });
    }).then(function (r) {
      ocupado(false);
      if (!r.ok || r.datos.error) {
        salida.textContent = r.datos.error || 'No se pudo consultar la IA.';
        hablar('asistente', r.datos.error || 'Error desconocido.');
        return;
      }
      var html = r.datos.html || '';
      var texto = r.datos.texto || '';
      ultima = html;
      respuesta.innerHTML = html;
      hablar('asistente', texto.length > 900 ? texto.slice(0, 900) + '…' : texto);
      historial.push({ rol: 'asistente', contenido: texto.slice(0, 2000) });
      if (entradaChat) entradaChat.value = '';
      var uso = r.datos.uso || {};
      var detalle = [];
      if (r.datos.modelo) detalle.push(r.datos.modelo);
      if (uso.entrada) detalle.push(uso.entrada + ' tokens de entrada');
      if (uso.salida) detalle.push(uso.salida + ' tokens de respuesta');
      salida.textContent = detalle.length ? 'Respuesta lista · ' + detalle.join(' · ') : 'Respuesta lista.';
      document.getElementById('ia-insertar').style.display = 'inline-flex';
    }).catch(function () {
      ocupado(false);
      salida.textContent = 'No hay conexion con el servidor.';
    });
  }

  ia.querySelectorAll('[data-accion]').forEach(function (boton) {
    boton.addEventListener('click', function () { pedir(boton.dataset.accion); });
  });

  document.getElementById('ia-insertar').addEventListener('click', function () {
    if (!ultima) return;
    insertarHTML(ultima);
    salida.textContent = 'Texto insertado en el documento.';
    this.style.display = 'none';
  });

  document.getElementById('ia-copiar').addEventListener('click', function () {
    if (!ultima) return;
    if (navigator.clipboard) {
      navigator.clipboard.writeText(respuesta.innerText).then(function () {
        salida.textContent = 'Copiado al portapapeles.';
      });
    }
  });

  if (botonEnviar) {
    botonEnviar.addEventListener('click', function () { pedir('chat'); });
  }
  if (entradaChat) {
    entradaChat.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); pedir('chat'); }
    });
  }
  if (tema) {
    tema.addEventListener('change', function () {
      if (temaLibre) {
        temaLibre.style.display = this.value === 'libre' ? 'block' : 'none';
        if (this.value === 'libre') temaLibre.focus();
      }
    });
  }

  if (!estado.configurado) {
    salida.textContent = 'IA apagada: falta IA_CLAVE en /etc/derechoson.env.';
    ia.querySelectorAll('button').forEach(function (b) { b.disabled = true; });
    if (entradaChat) entradaChat.disabled = true;
  }
  sincronizar();
})();
