/* Derechos On — comportamiento de la intranet administrativa */
(function () {
  "use strict";

  var app = document.querySelector(".ix-app");
  if (!app) return;

  var reduceMotion = window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function normalizar(texto) {
    return (texto || "")
      .toString()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .trim();
  }

  /* ------------------------------------------------ menú lateral móvil */
  var botonMenu = document.getElementById("ixMenuBtn");
  var botonCerrar = document.getElementById("ixSideClose");
  var fondo = document.getElementById("ixBackdrop");

  function abrirMenu(abrir) {
    app.classList.toggle("ix-side-abierto", abrir);
    document.body.classList.toggle("ix-lock", abrir);
    if (botonMenu) botonMenu.setAttribute("aria-expanded", abrir ? "true" : "false");
    if (fondo) fondo.hidden = !abrir;
  }

  if (botonMenu) botonMenu.addEventListener("click", function () { abrirMenu(true); });
  if (botonCerrar) botonCerrar.addEventListener("click", function () { abrirMenu(false); });
  if (fondo) fondo.addEventListener("click", function () { abrirMenu(false); });

  /* ------------------------------------------------ grupos plegables */
  var CLAVE_GRUPOS = "ix-grupos-cerrados";
  var cerrados = {};
  var hayPreferencias = false;
  try {
    hayPreferencias = localStorage.getItem(CLAVE_GRUPOS) !== null;
    cerrados = JSON.parse(localStorage.getItem(CLAVE_GRUPOS) || "{}") || {};
  } catch (e) { cerrados = {}; }

  var grupos = Array.prototype.slice.call(document.querySelectorAll("[data-ix-group]"));
  grupos.forEach(function (grupo, indice) {
    var boton = grupo.querySelector(".ix-group-toggle");
    if (!boton) return;
    var clave = boton.textContent.trim() || ("grupo-" + indice);
    if (cerrados[clave]) {
      grupo.classList.add("cerrado");
      boton.setAttribute("aria-expanded", "false");
    }
    boton.addEventListener("click", function () {
      var plegado = grupo.classList.toggle("cerrado");
      boton.setAttribute("aria-expanded", plegado ? "false" : "true");
      cerrados[clave] = plegado;
      try { localStorage.setItem(CLAVE_GRUPOS, JSON.stringify(cerrados)); } catch (e) {}
    });
  });

  /* En pantallas bajas, deja abierto solo el grupo de la página actual. */
  if (!hayPreferencias && window.innerHeight < 900) {
    grupos.forEach(function (grupo) {
      var activo = grupo.querySelector(".ix-link.activo");
      if (activo) return;
      grupo.classList.add("cerrado");
      var boton = grupo.querySelector(".ix-group-toggle");
      if (boton) boton.setAttribute("aria-expanded", "false");
    });
  }

  var enlaceActivo = document.querySelector(".ix-link.activo");
  if (enlaceActivo && enlaceActivo.scrollIntoView) {
    enlaceActivo.scrollIntoView({ block: "nearest" });
  }

  /* ------------------------------------------------ filtro del menú */
  var entradaMenu = document.getElementById("ixMenuBuscar");
  var vacio = document.getElementById("ixNavVacio");
  var enlaces = Array.prototype.slice.call(document.querySelectorAll(".ix-link"));

  function filtrarMenu() {
    if (!entradaMenu) return;
    var consulta = normalizar(entradaMenu.value);
    var visibles = 0;

    enlaces.forEach(function (enlace) {
      var texto = normalizar(enlace.getAttribute("data-ix-text") || enlace.textContent);
      var coincide = !consulta || texto.indexOf(consulta) !== -1;
      enlace.classList.toggle("ix-oculto", !coincide);
      if (coincide) visibles += 1;
    });

    grupos.forEach(function (grupo) {
      var alguno = grupo.querySelector(".ix-link:not(.ix-oculto)");
      grupo.classList.toggle("ix-oculto", !alguno);
      if (consulta) {
        grupo.classList.remove("cerrado");
        var boton = grupo.querySelector(".ix-group-toggle");
        if (boton) boton.setAttribute("aria-expanded", "true");
      }
    });

    if (vacio) vacio.hidden = visibles !== 0;
  }

  if (entradaMenu) entradaMenu.addEventListener("input", filtrarMenu);
  if (entradaMenu) {
    entradaMenu.addEventListener("keydown", function (evento) {
      if (evento.key === "Escape") {
        entradaMenu.value = "";
        filtrarMenu();
        entradaMenu.blur();
      }
    });
  }

  /* ------------------------------------------------ desplegables */
  var desplegables = Array.prototype.slice.call(document.querySelectorAll("[data-ix-drop]"));

  function cerrarDesplegables(excepto) {
    desplegables.forEach(function (drop) {
      if (drop === excepto) return;
      drop.classList.remove("abierto");
      var boton = drop.querySelector("[data-ix-drop-btn]");
      if (boton) boton.setAttribute("aria-expanded", "false");
    });
  }

  desplegables.forEach(function (drop) {
    var boton = drop.querySelector("[data-ix-drop-btn]");
    if (!boton) return;
    boton.addEventListener("click", function (evento) {
      evento.stopPropagation();
      var abierto = drop.classList.toggle("abierto");
      boton.setAttribute("aria-expanded", abierto ? "true" : "false");
      cerrarDesplegables(drop);
    });
    drop.querySelectorAll(".ix-drop-menu a").forEach(function (enlace) {
      enlace.addEventListener("click", function () { cerrarDesplegables(null); });
    });
  });

  document.addEventListener("click", function (evento) {
    if (!evento.target.closest("[data-ix-drop]")) cerrarDesplegables(null);
  });

  document.addEventListener("keydown", function (evento) {
    if (evento.key === "Escape") {
      cerrarDesplegables(null);
      abrirMenu(false);
    }
    if (evento.key === "/" && !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)) {
      var buscador = document.getElementById("ixBuscarGlobal") || entradaMenu;
      if (buscador) {
        evento.preventDefault();
        buscador.focus();
        buscador.select && buscador.select();
      }
    }
  });

  /* ------------------------------------------------ contadores animados */
  function animarNumero(elemento, destino) {
    if (!elemento) return;
    destino = parseInt(destino, 10);
    if (isNaN(destino)) return;
    var actual = parseInt(elemento.textContent.replace(/[^\d-]/g, ""), 10);
    if (isNaN(actual)) actual = 0;
    if (reduceMotion || actual === destino) {
      elemento.textContent = destino;
      return;
    }
    var inicio = performance.now();
    var duracion = 520;
    function paso(ahora) {
      var avance = Math.min((ahora - inicio) / duracion, 1);
      var suavizado = 1 - Math.pow(1 - avance, 3);
      elemento.textContent = Math.round(actual + (destino - actual) * suavizado);
      if (avance < 1) requestAnimationFrame(paso);
      else elemento.textContent = destino;
    }
    requestAnimationFrame(paso);
  }

  document.querySelectorAll("[data-ix-animar]").forEach(function (elemento) {
    animarNumero(elemento, elemento.getAttribute("data-ix-animar"));
  });

  /* ------------------------------------------------ resumen en vivo */
  var zonaViva = document.querySelector("[data-ix-live]");
  if (zonaViva) {
    var enCurso = false;

    function pintarSerie(nombre, serie) {
      var contenedor = document.querySelector('[data-ix-spark="' + nombre + '"]');
      if (!contenedor || !serie || !serie.length) return;
      var barras = contenedor.querySelectorAll("i");
      var maximo = Math.max.apply(null, serie.concat([1]));
      Array.prototype.forEach.call(barras, function (barra, indice) {
        var valor = serie[indice] || 0;
        barra.style.height = Math.max(2, Math.round((valor / maximo) * 100)) + "%";
        barra.title = valor + " en el día";
      });
    }

    function pintarDelta(nombre, delta) {
      var elemento = document.querySelector('[data-ix-delta="' + nombre + '"]');
      if (!elemento) return;
      var numero = parseInt(delta, 10) || 0;
      elemento.textContent = (numero > 0 ? "+" : "") + numero + "%";
      elemento.classList.remove("sube", "baja", "neutro");
      elemento.classList.add(numero > 0 ? "sube" : (numero < 0 ? "baja" : "neutro"));
    }

    function actualizar(datos) {
      if (!datos || !datos.kpis) return;
      Object.keys(datos.kpis).forEach(function (nombre) {
        var kpi = datos.kpis[nombre];
        var valor = document.querySelector('[data-ix-kpi="' + nombre + '"]');
        if (valor) valor.textContent = kpi.valor;
        pintarDelta(nombre, kpi.delta);
        pintarSerie(nombre, kpi.serie);
      });
      var contadores = datos.contadores || {};
      document.querySelectorAll("[data-ix-badge]").forEach(function (badge) {
        var clave = badge.getAttribute("data-ix-badge");
        var numero = parseInt(contadores[clave], 10) || 0;
        badge.textContent = numero;
        badge.hidden = numero === 0;
      });
      var marca = document.querySelector("[data-ix-actualizado]");
      if (marca && datos.actualizado) marca.textContent = datos.actualizado;
    }

    function refrescar() {
      if (enCurso || document.hidden) return;
      enCurso = true;
      fetch(zonaViva.getAttribute("data-ix-live") || "/admin/api/resumen", {
        headers: { "X-Requested-With": "fetch" },
        credentials: "same-origin"
      })
        .then(function (respuesta) {
          if (!respuesta.ok) throw new Error("respuesta " + respuesta.status);
          return respuesta.json();
        })
        .then(actualizar)
        .catch(function () { /* sin conexión: se reintenta en el próximo ciclo */ })
        .then(function () { enCurso = false; });
    }

    window.setInterval(refrescar, 60000);
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) refrescar();
    });
  }
})();
