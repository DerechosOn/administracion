// Derechos On — interacciones del sitio
document.addEventListener("DOMContentLoaded", function () {
  // ---- Carrusel del hero ----
  var slides = Array.prototype.slice.call(document.querySelectorAll("[data-slide]"));
  if (slides.length) {
    var puntos = Array.prototype.slice.call(document.querySelectorAll("[data-punto]"));
    var actual = 0;
    var temporizador = null;

    function mostrar(i) {
      actual = (i + slides.length) % slides.length;
      slides.forEach(function (s, k) { s.classList.toggle("activo", k === actual); });
      puntos.forEach(function (p, k) { p.classList.toggle("activo", k === actual); });
    }
    function avanzar() { mostrar(actual + 1); }
    function reiniciarAuto() {
      clearInterval(temporizador);
      temporizador = setInterval(avanzar, 7000);
    }

    document.querySelector("[data-siguiente]").onclick = function () { avanzar(); reiniciarAuto(); };
    document.querySelector("[data-anterior]").onclick = function () { mostrar(actual - 1); reiniciarAuto(); };
    puntos.forEach(function (p) {
      p.onclick = function () { mostrar(+p.getAttribute("data-punto")); reiniciarAuto(); };
    });
    reiniciarAuto();
  }

  // ---- Búsqueda (filtra tiles, áreas, abogados y noticias) ----
  var buscador = document.getElementById("buscador");
  if (buscador) {
    var blancos = Array.prototype.slice.call(document.querySelectorAll("[data-busca]"));
    var vacio = document.getElementById("busqueda-vacia");
    buscador.addEventListener("input", function () {
      var q = this.value.trim().toLowerCase();
      var visibles = 0;
      blancos.forEach(function (el) {
        var coincide = !q || (el.textContent || "").toLowerCase().indexOf(q) > -1;
        el.style.display = coincide ? "" : "none";
        if (coincide) visibles++;
      });
      if (vacio) vacio.style.display = (q && visibles === 0) ? "block" : "none";
    });
  }

  // ---- Modales ----
  document.querySelectorAll("[data-abre-modal]").forEach(function (boton) {
    boton.addEventListener("click", function (e) {
      e.preventDefault();
      var modal = document.getElementById(boton.getAttribute("data-abre-modal"));
      if (modal) modal.classList.add("abierto");
    });
  });

  document.querySelectorAll(".cerrar-modal, [data-cierra-modal]").forEach(function (el) {
    el.addEventListener("click", function () {
      var modal = el.closest(".modal");
      if (modal) modal.classList.remove("abierto");
    });
  });

  document.querySelectorAll(".modal").forEach(function (modal) {
    modal.addEventListener("click", function (e) {
      if (e.target === modal) modal.classList.remove("abierto");
    });
  });

  // ---- Confirmación de eliminación ----
  document.querySelectorAll("form[data-confirmar]").forEach(function (form) {
    form.addEventListener("submit", function (e) {
      var mensaje = form.getAttribute("data-confirmar") || "¿Desea eliminar este registro?";
      if (!window.confirm(mensaje)) e.preventDefault();
    });
  });

  // ---- Auto-ocultar alertas flash ----
  document.querySelectorAll(".alert").forEach(function (alerta) {
    setTimeout(function () {
      alerta.style.transition = "opacity .5s";
      alerta.style.opacity = "0";
      setTimeout(function () { alerta.remove(); }, 600);
    }, 4500);
  });
});

// ---- Correo institucional (Outlook-like) ----
document.addEventListener("DOMContentLoaded", function () {
  var esc = function (t) {
    var d = document.createElement("div");
    d.textContent = t == null ? "" : String(t);
    return d.innerHTML;
  };
  var tam = function (n) {
    n = n || 0;
    if (n >= 1048576) return (n / 1048576).toFixed(1) + " MB";
    if (n >= 1024) return (n / 1024).toFixed(0) + " KB";
    return n + " B";
  };

  // --- Búsqueda sobre la lista de mensajes ---
  var busca = document.getElementById("mail-busca");
  if (busca) {
    busca.addEventListener("input", function () {
      var q = this.value.trim().toLowerCase();
      document.querySelectorAll(".mail-item").forEach(function (item) {
        item.style.display = !q || item.textContent.toLowerCase().indexOf(q) > -1 ? "" : "none";
      });
    });
  }

  // --- Leer mensaje en el panel derecho ---
  var panel = document.getElementById("mail-panel");
  var lista = document.getElementById("mail-lista");

  function accionMail(uid, carpeta, accion, okCallback) {
    var form = new FormData();
    form.append("uid", uid);
    form.append("carpeta", carpeta);
    form.append("accion", accion);
    fetch("/abogado/correo/accion", { method: "POST", body: form })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.ok) { window.alert(d.error); return; }
        if (okCallback) okCallback();
      });
  }

  function pintarMensaje(d) {
    var adj = "";
    (d.adjuntos || []).forEach(function (a) {
      adj += '<a class="mail-adjunto" href="/abogado/correo/adjunto?carpeta=' +
        encodeURIComponent(d.carpeta) + "&uid=" + encodeURIComponent(d.uid) +
        "&indice=" + a.indice + '">Adjunto: ' + esc(a.nombre) +
        ' <span class="tam">(' + tam(a.tamano) + ")</span></a>";
    });
    var urlLectura = "/abogado/correo/adjunto?carpeta=" + encodeURIComponent(d.carpeta);
    panel.innerHTML =
      '<div class="mail-cab">' +
      "<h2>" + esc(d.asunto) + "</h2>" +
      '<div class="quienes"><b>' + esc(d.de_nombre) + "</b> &lt;" + esc(d.de_correo) + "&gt;" +
      '<span>Para: ' + esc(d.para) + (d.cc ? "<br>CC: " + esc(d.cc) : "") + "</span>" +
      '<div class="fecha">' + esc(d.fecha) + "</div></div>" +
      '<div class="mail-bar">' +
      '<a class="btn btn-sm" href="/abogado/correo/redactar?uid=' + encodeURIComponent(d.uid) +
      "&carpeta=" + encodeURIComponent(d.carpeta) + '">Responder</a>' +
      '<button class="btn btn-sm" data-ma="noleido">Marcar no leído</button>' +
      '<button class="btn btn-sm" data-ma="eliminar">Eliminar</button>' +
      "</div></div>" +
      '<div class="mail-cuerpo-html">' + (d.html || "") + "</div>" +
      (adj ? '<div class="mail-adjuntos">' + adj + "</div>" : "");

    panel.querySelector('[data-ma="noleido"]').onclick = function () {
      accionMail(d.uid, d.carpeta, "noleido", function () {
        var item = lista.querySelector('.mail-item[data-uid="' + d.uid + '"]');
        if (item) item.classList.add("no-leido");
      });
    };
    panel.querySelector('[data-ma="eliminar"]').onclick = function () {
      if (!window.confirm("¿Eliminar este mensaje?")) return;
      accionMail(d.uid, d.carpeta, "eliminar", function () {
        var item = lista.querySelector('.mail-item[data-uid="' + d.uid + '"]');
        if (item) item.remove();
        panel.innerHTML = '<div class="vacio">Mensaje eliminado.</div>';
      });
    };
  }

  if (panel && lista) {
    lista.addEventListener("click", function (e) {
      var item = e.target.closest(".mail-item");
      if (!item) return;
      document.querySelectorAll(".mail-item").forEach(function (i) { i.classList.remove("activo"); });
      item.classList.add("activo");
      panel.innerHTML = '<div class="vacio">Cargando mensaje...</div>';
      var form = new FormData();
      form.append("uid", item.getAttribute("data-uid"));
      form.append("carpeta", item.getAttribute("data-carpeta"));
      fetch("/abogado/correo/mensaje", { method: "POST", body: form })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (!d.ok) {
            panel.innerHTML = '<div class="vacio">' + esc(d.error) + "</div>";
            return;
          }
          item.classList.remove("no-leido");
          pintarMensaje(d);
        });
    });
  }

  // --- Probar conexión (configuración) ---
  var probar = document.getElementById("mail-probar");
  if (probar) {
    probar.addEventListener("click", function () {
      var res = document.getElementById("mail-prueba");
      res.textContent = "Probando conexión...";
      res.className = "";
      var form = document.getElementById("form-mail-config");
      var datos = new FormData(form);
      datos.set("accion", "prueba");
      fetch(form.getAttribute("action"), { method: "POST", body: datos })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          res.textContent = d.ok ? "Conexión exitosa: " + d.detalle : d.detalle;
          res.style.color = d.ok ? "#128f5d" : "#d64545";
        });
    });
  }

  // ---- Aviso de cookies ----
  var banner = document.getElementById("cookieBanner");
  if (banner) {
    function elegirCookies(valor) {
      try { localStorage.setItem("do_cookies", String(valor)); } catch (e) {}
      banner.hidden = true;
    }
    var preferencia = null;
    try { preferencia = localStorage.getItem("do_cookies"); } catch (e) {}
    if (preferencia === null) banner.hidden = false;
    banner.querySelectorAll("[data-cookie]").forEach(function (boton) {
      boton.addEventListener("click", function () {
        elegirCookies(boton.getAttribute("data-cookie"));
      });
    });
  }
});