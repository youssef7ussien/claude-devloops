/* Zoom, pan and full screen for the site's Mermaid diagrams, like GitHub's diagram viewer.
   The theme draws each diagram into a closed shadow root, so the diagram's element is moved and
   scaled as a whole: it sits in a viewport that clips it, and dragging pans it. */
(function () {
  "use strict";

  var STEP = 1.25, MIN = 0.5, MAX = 6, DRAG_START = 4;

  function button(label, text, onClick) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "dl-diagram__button";
    b.textContent = text;
    b.addEventListener("click", onClick);
    setLabel(b, label);
    return b;
  }

  function setLabel(b, label) {
    b.title = label;
    b.setAttribute("aria-label", label);
  }

  /* The drawing's own size. Mermaid caps the drawing's width and keeps its proportions, so its
     height grows with the width up to the cap: two small widths give the proportion (and cancel
     any fixed height around the drawing), and a very large one gives the capped height. */
  function naturalSize(diagram) {
    function heightAt(width) {
      diagram.style.width = width + "px";
      return diagram.getBoundingClientRect().height;
    }
    var h100 = heightAt(100), h200 = heightAt(200), height = heightAt(100000);
    diagram.style.width = "";
    var ratio = (h200 - h100) / 100;
    return { width: ratio > 0 ? 100 + (height - h100) / ratio : 0, height: height };
  }

  function enhance(diagram) {
    if (diagram.closest(".dl-diagram")) return;
    var box = document.createElement("div");
    box.className = "dl-diagram";
    var viewport = document.createElement("div");
    viewport.className = "dl-diagram__viewport";
    var canvas = document.createElement("div");
    canvas.className = "dl-diagram__canvas";
    diagram.parentNode.insertBefore(box, diagram);
    canvas.appendChild(diagram);
    viewport.appendChild(canvas);
    box.appendChild(viewport);

    var scale = 1, x = 0, y = 0, fit = null;
    function fullScreen() {
      return document.fullscreenElement === box;
    }
    function apply() {
      canvas.style.transform = "translate(" + x + "px," + y + "px) scale(" + scale + ")";
      var moved = fit ? scale !== fit.scale || x !== fit.x || y !== fit.y : scale !== 1 || x !== 0 || y !== 0;
      box.classList.toggle("dl-diagram--zoomed", moved);
    }
    /* Never smaller than the fitted size, so a fitted drawing can always be zoomed back to. */
    function clamp(next) {
      return Math.min(MAX, Math.max(fit ? Math.min(MIN, fit.scale) : MIN, next));
    }
    /* Zoom to `next`, keeping where it is the point (px, py) of the box, by default the middle of
       the viewport. The canvas's top left corner is the origin of its transform. */
    function zoomTo(next, px, py) {
      if (px === undefined) {
        px = viewport.offsetLeft + viewport.clientWidth / 2;
        py = viewport.offsetTop + viewport.clientHeight / 2;
      }
      var lx = px - canvas.offsetLeft, ly = py - canvas.offsetTop;
      x = lx - (lx - x) * (next / scale);
      y = ly - (ly - y) * (next / scale);
      scale = next;
      apply();
    }
    /* Back to the start: the normal size on the page; in full screen, the whole drawing as large
       as the screen allows, in its middle. */
    function reset() {
      if (fit) {
        scale = fit.scale; x = fit.x; y = fit.y;
      } else {
        scale = 1; x = 0; y = 0;
      }
      apply();
    }

    var tools = document.createElement("div");
    tools.className = "dl-diagram__tools";
    tools.appendChild(button("Zoom in", "+", function () { zoomTo(clamp(scale * STEP)); }));
    tools.appendChild(button("Zoom out", "−", function () { zoomTo(clamp(scale / STEP)); }));
    tools.appendChild(button("Reset", "↺", reset));
    if (box.requestFullscreen) {
      var full = button("Full screen", "⛶", function () {
        if (fullScreen()) document.exitFullscreen();
        else box.requestFullscreen();
      });
      tools.appendChild(full);
      /* Fitted when the box takes the whole screen, which happens after "fullscreenchange",
         and again when the screen changes size (a phone turned round). */
      function refit() {
        /* The theme replaces the block with the drawn diagram, so it is looked up each time. */
        var drawn = canvas.firstElementChild;
        fit = null;
        drawn.style.width = "";
        if (fullScreen()) {
          var size = naturalSize(drawn);
          var padX = canvas.offsetLeft - viewport.offsetLeft, padY = canvas.offsetTop - viewport.offsetTop;
          var room = { width: viewport.clientWidth - 2 * padX, height: viewport.clientHeight - 2 * padY };
          if (size.width > 0 && size.height > 0) {
            drawn.style.width = size.width + "px";
            var s = Math.min(MAX, room.width / size.width, room.height / size.height);
            fit = { scale: s, x: (room.width - size.width * s) / 2, y: (room.height - size.height * s) / 2 };
          }
        }
        reset();
      }
      box.addEventListener("fullscreenchange", function () {
        setLabel(full, fullScreen() ? "Exit full screen" : "Full screen");
        refit();
      });
      if (window.ResizeObserver) {
        new ResizeObserver(function () { if (fullScreen() || fit) refit(); }).observe(viewport);
      }
    }
    box.appendChild(tools);

    /* Ctrl or Cmd with the wheel (or a trackpad pinch) zooms at the pointer; the wheel alone
       still scrolls the page, and at the smallest or largest size the browser zooms the page. */
    viewport.addEventListener("wheel", function (e) {
      if (!e.ctrlKey && !e.metaKey) return;
      var next = clamp(scale * Math.exp(-e.deltaY / 300));
      if (next === scale) return;
      e.preventDefault();
      var r = box.getBoundingClientRect();
      zoomTo(next, e.clientX - r.left, e.clientY - r.top);
    }, { passive: false });

    /* Drag to pan, once the diagram is zoomed or moved, and always in full screen. A drag starts
       only when the pointer has moved a few pixels, so a click still reaches the diagram. */
    var press = null;
    viewport.addEventListener("pointerdown", function (e) {
      if (e.button !== 0 || (!box.classList.contains("dl-diagram--zoomed") && !fullScreen())) return;
      press = { id: e.pointerId, cx: e.clientX, cy: e.clientY, sx: e.clientX - x, sy: e.clientY - y, dragging: false };
    });
    viewport.addEventListener("pointermove", function (e) {
      if (!press || e.pointerId !== press.id) return;
      if (!press.dragging) {
        if (Math.abs(e.clientX - press.cx) < DRAG_START && Math.abs(e.clientY - press.cy) < DRAG_START) return;
        press.dragging = true;
        viewport.setPointerCapture(e.pointerId);
        box.classList.add("dl-diagram--dragging");
        var selection = window.getSelection();
        if (selection) selection.removeAllRanges();
      }
      x = e.clientX - press.sx;
      y = e.clientY - press.sy;
      apply();
    });
    function stop(e) {
      if (!press || e.pointerId !== press.id) return;
      press = null;
      box.classList.remove("dl-diagram--dragging");
    }
    viewport.addEventListener("pointerup", stop);
    viewport.addEventListener("pointercancel", stop);
  }

  /* Before the theme draws the diagrams: while it draws one, the block loses its class. The
     script loads at the end of the page, so the blocks are there already. */
  document.querySelectorAll(".md-content .mermaid").forEach(enhance);
})();
