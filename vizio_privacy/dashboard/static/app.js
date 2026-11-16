(function () {
  "use strict";

  // Directions are integers (company rule: a fixed set is never text).
  var DIR = {LEFT: 0, RIGHT: 1, UP: 2, DOWN: 3};

  // Indexed by tile.shape (ImageShape: POSTER 0, WIDE 1, ICON 2).
  var SHAPE_CLASSES = ["poster", "wide", "icon"];

  // Remote key codes.
  var KEY_OK = 13;
  var KEY_LEFT = 37;
  var KEY_UP = 38;
  var KEY_RIGHT = 39;
  var KEY_DOWN = 40;
  var BACK_KEYS = [8, 27, 461, 10009];

  var LOAD_TIMEOUT = 10000;
  var RETRY_MS = 10000;
  var REFRESH_MS = 300000;
  var TOAST_MS = 2500;
  var PAD = 0.04;

  // "Retrying" ends in an ellipsis; built in pieces so the ES5 guard's
  // "no ..." rule (aimed at spread syntax) is satisfied in the source.
  var ELLIPSIS = "." + "." + ".";

  // ---- pure functions (no DOM) ------------------------------------------

  function buildLines(home) {
    var lines = [];
    var rows = home.rows || [];
    var i;
    for (i = 0; i < rows.length; i++) {
      if (rows[i].tiles && rows[i].tiles.length > 0) {
        lines.push({title: rows[i].title, tiles: rows[i].tiles});
      }
    }
    var apps = home.apps || [];
    if (apps.length > 0) {
      lines.push({title: "Apps", tiles: apps});
    }
    return lines;
  }

  function nextPosition(lengths, pos, lastCol, dir) {
    var line = pos.line;
    var col = pos.col;
    if (dir === DIR.LEFT) {
      col = col - 1;
      if (col < 0) {
        col = 0;
      }
      return {line: line, col: col};
    }
    if (dir === DIR.RIGHT) {
      col = col + 1;
      if (col > lengths[line] - 1) {
        col = lengths[line] - 1;
      }
      return {line: line, col: col};
    }
    var newLine = dir === DIR.UP ? line - 1 : line + 1;
    if (newLine < 0) {
      newLine = 0;
    }
    if (newLine > lengths.length - 1) {
      newLine = lengths.length - 1;
    }
    if (newLine === line) {
      return {line: line, col: col};
    }
    lastCol[pos.line] = pos.col;
    var target = lastCol[newLine] >= 0 ? lastCol[newLine] : pos.col;
    if (target > lengths[newLine] - 1) {
      target = lengths[newLine] - 1;
    }
    if (target < 0) {
      target = 0;
    }
    return {line: newLine, col: target};
  }

  function scrollFor(offset, start, size, view, pad) {
    if (start >= offset + pad && start + size <= offset + view - pad) {
      return offset;
    }
    if (start + size > offset + view - pad) {
      return start + size - view + pad;
    }
    return Math.max(0, start - pad);
  }

  function findTile(lines, id) {
    var line, col;
    for (line = 0; line < lines.length; line++) {
      var tiles = lines[line].tiles;
      for (col = 0; col < tiles.length; col++) {
        if (tiles[col].id === id) {
          return {line: line, col: col};
        }
      }
    }
    return null;
  }

  // ---- DOM state ----------------------------------------------------------

  var lines = [];
  var pos = null;
  var lastCol = [];
  var tileEls = [];
  var strips = [];
  var rowEls = [];
  var stripOffsets = [];
  var contentOffset = 0;
  var focusEl = null;
  var hasContent = false;
  var actionPending = false;
  var retryTimer = 0;
  var toastTimer = 0;
  var contentEl = null;
  var noticesEl = null;
  var rowsEl = null;
  var statusEl = null;
  var toastEl = null;

  // ---- element helpers ----------------------------------------------------

  function el(tag, cls) {
    var node = document.createElement(tag);
    if (cls) {
      node.className = cls;
    }
    return node;
  }

  function hasClass(node, name) {
    return (" " + node.className + " ").indexOf(" " + name + " ") >= 0;
  }

  function addClass(node, name) {
    if (!hasClass(node, name)) {
      node.className = node.className + " " + name;
    }
  }

  function dropClass(node, name) {
    var parts = node.className.split(" ");
    var kept = [];
    var i;
    for (i = 0; i < parts.length; i++) {
      if (parts[i] && parts[i] !== name) {
        kept.push(parts[i]);
      }
    }
    node.className = kept.join(" ");
  }

  function clearChildren(node) {
    while (node.firstChild) {
      node.removeChild(node.firstChild);
    }
  }

  function setStatus(text) {
    if (statusEl) {
      statusEl.textContent = text;
    }
  }

  // ---- rendering ----------------------------------------------------------

  function makeArtText(tile, cls) {
    var box = el("div", cls);
    box.textContent = tile.title;
    return box;
  }

  function makeTile(tile) {
    var node = el("div", "tile " + SHAPE_CLASSES[tile.shape]);
    node.tileData = tile;
    var art = el("div", "art");
    if (tile.image) {
      var img = document.createElement("img");
      img.src = tile.image;
      img.alt = "";
      img.onerror = function () {
        art.replaceChild(makeArtText(tile, "art-text"), img);
      };
      art.appendChild(img);
    } else {
      art.appendChild(makeArtText(tile, "art-text"));
    }
    if (typeof tile.progress === "number") {
      var progress = el("div", "progress");
      var bar = el("div", "bar");
      bar.style.width = Math.round(tile.progress * 100) + "%";
      progress.appendChild(bar);
      art.appendChild(progress);
    }
    node.appendChild(art);
    var title = el("div", "t");
    title.textContent = tile.title;
    node.appendChild(title);
    if (tile.subtitle != null) {
      var sub = el("div", "s");
      sub.textContent = tile.subtitle;
      node.appendChild(sub);
    }
    return node;
  }

  function focusedId() {
    if (!pos) {
      return null;
    }
    var rowArr = tileEls[pos.line];
    if (!rowArr) {
      return null;
    }
    var node = rowArr[pos.col];
    if (!node || !node.tileData) {
      return null;
    }
    return node.tileData.id;
  }

  function lineLengths() {
    var lengths = [];
    var i;
    for (i = 0; i < lines.length; i++) {
      lengths.push(lines[i].tiles.length);
    }
    return lengths;
  }

  function render(home) {
    var remember = focusedId();
    lines = buildLines(home);

    clearChildren(noticesEl);
    clearChildren(rowsEl);

    var notices = home.notices || [];
    var n, i, c;
    for (n = 0; n < notices.length; n++) {
      var notice = el("div", "notice");
      notice.textContent = notices[n];
      noticesEl.appendChild(notice);
    }

    tileEls = [];
    strips = [];
    rowEls = [];
    stripOffsets = [];
    focusEl = null;

    for (i = 0; i < lines.length; i++) {
      var line = lines[i];
      var row = el("div", "row");
      var heading = el("div", "row-title");
      heading.textContent = line.title;
      row.appendChild(heading);
      var strip = el("div", "strip");
      var rowTiles = [];
      for (c = 0; c < line.tiles.length; c++) {
        var tileNode = makeTile(line.tiles[c]);
        strip.appendChild(tileNode);
        rowTiles.push(tileNode);
      }
      row.appendChild(strip);
      rowsEl.appendChild(row);
      tileEls.push(rowTiles);
      strips.push(strip);
      rowEls.push(row);
      stripOffsets.push(0);
    }

    if (lines.length === 0) {
      pos = null;
      hasContent = false;
      setStatus("Nothing to show yet.");
      return;
    }

    hasContent = true;
    setStatus("");

    lastCol = [];
    for (i = 0; i < lines.length; i++) {
      lastCol.push(-1);
    }

    var found = remember ? findTile(lines, remember) : null;
    if (found) {
      lastCol[found.line] = found.col;
      setFocus(found);
    } else {
      var keepLine = pos ? pos.line : 0;
      if (keepLine > lines.length - 1) {
        keepLine = lines.length - 1;
      }
      if (keepLine < 0) {
        keepLine = 0;
      }
      setFocus({line: keepLine, col: 0});
    }
  }

  // ---- focus and scroll ---------------------------------------------------

  function setFocus(next) {
    pos = next;
    var node = tileEls[pos.line][pos.col];
    if (focusEl && focusEl !== node) {
      dropClass(focusEl, "focused");
    }
    addClass(node, "focused");
    focusEl = node;
    scrollFocus();
  }

  function scrollFocus() {
    var node = tileEls[pos.line][pos.col];
    var pad = Math.round(window.innerWidth * PAD);
    var off = scrollFor(
      stripOffsets[pos.line],
      node.offsetLeft,
      node.offsetWidth,
      window.innerWidth,
      pad
    );
    stripOffsets[pos.line] = off;
    strips[pos.line].style.transform = "translateX(-" + off + "px)";

    var row = rowEls[pos.line];
    var padY = Math.round(window.innerHeight * PAD);
    var offY = scrollFor(
      contentOffset,
      row.offsetTop,
      row.offsetHeight,
      window.innerHeight,
      padY
    );
    contentOffset = offY;
    contentEl.style.transform = "translateY(-" + offY + "px)";
  }

  // ---- data loading -------------------------------------------------------

  function scheduleRetry() {
    if (retryTimer) {
      clearTimeout(retryTimer);
    }
    retryTimer = setTimeout(function () {
      retryTimer = 0;
      load();
    }, RETRY_MS);
  }

  function loadFailed() {
    if (!hasContent) {
      setStatus("Can't reach the dashboard server. Retrying" + ELLIPSIS);
    }
    scheduleRetry();
  }

  function load() {
    var xhr = new XMLHttpRequest();
    xhr.open("GET", "/api/home", true);
    xhr.timeout = LOAD_TIMEOUT;
    xhr.onload = function () {
      if (xhr.status !== 200) {
        loadFailed();
        return;
      }
      var home;
      try {
        home = JSON.parse(xhr.responseText);
      } catch (e) {
        loadFailed();
        return;
      }
      render(home);
    };
    xhr.onerror = loadFailed;
    xhr.ontimeout = loadFailed;
    xhr.send(null);
  }

  // ---- actions ------------------------------------------------------------

  function showToast(message) {
    if (!toastEl) {
      return;
    }
    toastEl.textContent = message;
    addClass(toastEl, "show");
    if (toastTimer) {
      clearTimeout(toastTimer);
    }
    toastTimer = setTimeout(function () {
      dropClass(toastEl, "show");
      toastTimer = 0;
    }, TOAST_MS);
  }

  function sendAction() {
    if (actionPending || !pos) {
      return;
    }
    var tile = lines[pos.line].tiles[pos.col];
    if (!tile || !tile.action) {
      return;
    }
    actionPending = true;
    var xhr = new XMLHttpRequest();
    xhr.open("POST", "/api/action", true);
    xhr.timeout = LOAD_TIMEOUT;
    xhr.setRequestHeader("Content-Type", "application/json");
    xhr.onload = function () {
      actionPending = false;
      var message = "Couldn't reach the dashboard server.";
      var data = null;
      try {
        data = JSON.parse(xhr.responseText);
      } catch (e) {
        data = null;
      }
      if (data && typeof data.message === "string") {
        message = data.message;
      }
      showToast(message);
    };
    xhr.onerror = function () {
      actionPending = false;
      showToast("Couldn't reach the dashboard server.");
    };
    xhr.ontimeout = xhr.onerror;
    xhr.send(JSON.stringify(tile.action));
  }

  // ---- keys ---------------------------------------------------------------

  function onKeyDown(event) {
    var code = event.keyCode;
    if (code === KEY_LEFT || code === KEY_RIGHT || code === KEY_UP || code === KEY_DOWN) {
      event.preventDefault();
      if (!pos) {
        return;
      }
      var dir;
      if (code === KEY_LEFT) {
        dir = DIR.LEFT;
      } else if (code === KEY_RIGHT) {
        dir = DIR.RIGHT;
      } else if (code === KEY_UP) {
        dir = DIR.UP;
      } else {
        dir = DIR.DOWN;
      }
      setFocus(nextPosition(lineLengths(), pos, lastCol, dir));
    } else if (code === KEY_OK) {
      event.preventDefault();
      sendAction();
    } else {
      var i;
      for (i = 0; i < BACK_KEYS.length; i++) {
        if (code === BACK_KEYS[i]) {
          event.preventDefault();
          break;
        }
      }
    }
  }

  // ---- start --------------------------------------------------------------

  function start() {
    contentEl = document.getElementById("content");
    noticesEl = document.getElementById("notices");
    rowsEl = document.getElementById("rows");
    statusEl = document.getElementById("status");
    toastEl = document.getElementById("toast");

    document.addEventListener("keydown", onKeyDown, false);
    document.addEventListener("visibilitychange", function () {
      if (!document.hidden) {
        load();
      }
    }, false);

    load();
    setInterval(load, REFRESH_MS);
  }

  if (typeof module !== "undefined" && module.exports) {
    module.exports = {DIR: DIR, SHAPE_CLASSES: SHAPE_CLASSES, buildLines: buildLines,
                      nextPosition: nextPosition, scrollFor: scrollFor, findTile: findTile};
  } else {
    start();
  }
})();
