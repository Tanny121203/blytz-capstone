/**
 * Blytz staff charts — thin Chart.js helper (black / white / gray theme).
 * Expects Chart global from static/vendor/chartjs/chart.umd.min.js
 */
(function () {
  "use strict";

  var COLORS = {
    ink: "#0A0A0A",
    muted: "#525252",
    subtle: "#737373",
    border: "#E5E5E5",
    surface: "#FAFAFA",
    canvas: "#FFFFFF",
    gray1: "#0A0A0A",
    gray2: "#525252",
    gray3: "#A3A3A3",
    gray4: "#D4D4D4",
    gold: "#C9A227",
  };

  function prefersReducedMotion() {
    return (
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches
    );
  }

  function isNarrow() {
    return (
      typeof window.matchMedia === "function" &&
      window.matchMedia("(max-width: 639px)").matches
    );
  }

  function parsePayload(scriptId) {
    var el = document.getElementById(scriptId);
    if (!el) return null;
    try {
      return JSON.parse(el.textContent);
    } catch (err) {
      return null;
    }
  }

  function isEmpty(payload) {
    if (!payload) return true;
    if (payload.empty === true) return true;
    var values = payload.values || [];
    if (!values.length) return true;
    return values.every(function (v) {
      return !v || Number(v) === 0;
    });
  }

  function baseOptions(payload) {
    var narrow = isNarrow();
    return {
      responsive: true,
      maintainAspectRatio: false,
      animation: prefersReducedMotion() ? false : { duration: 400 },
      plugins: {
        legend: {
          display: Boolean(payload.showLegend),
          position: "bottom",
          labels: {
            boxWidth: 12,
            color: COLORS.muted,
            font: { size: narrow ? 11 : 12 },
          },
        },
        tooltip: {
          backgroundColor: COLORS.ink,
          titleColor: COLORS.canvas,
          bodyColor: COLORS.canvas,
          cornerRadius: 4,
        },
      },
    };
  }

  function fillPalette(count) {
    var palette = [COLORS.gray1, COLORS.gray2, COLORS.gray3, COLORS.gray4];
    var out = [];
    for (var i = 0; i < count; i++) {
      out.push(palette[i % palette.length]);
    }
    return out;
  }

  function renderBar(canvas, payload) {
    var opts = baseOptions(payload);
    var narrow = isNarrow();
    opts.scales = {
      x: {
        ticks: {
          color: COLORS.muted,
          maxRotation: narrow ? 45 : 0,
          minRotation: narrow ? 45 : 0,
          autoSkip: true,
          font: { size: narrow ? 10 : 12 },
        },
        grid: { color: COLORS.border, drawBorder: false },
      },
      y: {
        beginAtZero: true,
        ticks: {
          color: COLORS.muted,
          precision: 0,
          font: { size: narrow ? 10 : 12 },
        },
        grid: { color: COLORS.border, drawBorder: false },
      },
    };
    return new Chart(canvas.getContext("2d"), {
      type: "bar",
      data: {
        labels: payload.labels || [],
        datasets: [
          {
            label: payload.datasetLabel || "Count",
            data: payload.values || [],
            backgroundColor: COLORS.ink,
            borderColor: COLORS.ink,
            borderWidth: 0,
            borderRadius: 2,
            maxBarThickness: 48,
          },
        ],
      },
      options: opts,
    });
  }

  function renderLine(canvas, payload) {
    var opts = baseOptions(payload);
    var narrow = isNarrow();
    opts.scales = {
      x: {
        ticks: {
          color: COLORS.muted,
          maxRotation: narrow ? 45 : 0,
          autoSkip: true,
          maxTicksLimit: narrow ? 6 : 10,
          font: { size: narrow ? 10 : 12 },
        },
        grid: { display: false },
      },
      y: {
        beginAtZero: true,
        ticks: {
          color: COLORS.muted,
          precision: 0,
          font: { size: narrow ? 10 : 12 },
        },
        grid: { color: COLORS.border, drawBorder: false },
      },
    };
    return new Chart(canvas.getContext("2d"), {
      type: "line",
      data: {
        labels: payload.labels || [],
        datasets: [
          {
            label: payload.datasetLabel || "Amount",
            data: payload.values || [],
            borderColor: COLORS.ink,
            backgroundColor: "rgba(10, 10, 10, 0.06)",
            pointBackgroundColor: COLORS.ink,
            pointBorderColor: COLORS.canvas,
            pointRadius: prefersReducedMotion() ? 0 : narrow ? 2 : 3,
            pointHoverRadius: 4,
            borderWidth: 2,
            fill: true,
            tension: prefersReducedMotion() ? 0 : 0.25,
          },
        ],
      },
      options: opts,
    });
  }

  function renderDoughnut(canvas, payload) {
    var opts = baseOptions(payload);
    opts.showLegend = true;
    opts.plugins.legend.display = true;
    var labels = payload.labels || [];
    return new Chart(canvas.getContext("2d"), {
      type: "doughnut",
      data: {
        labels: labels,
        datasets: [
          {
            data: payload.values || [],
            backgroundColor: fillPalette(labels.length),
            borderColor: COLORS.canvas,
            borderWidth: 2,
            hoverOffset: 4,
          },
        ],
      },
      options: opts,
    });
  }

  function mountRoot(root) {
    if (!root || typeof Chart === "undefined") return null;
    var scriptId = root.getAttribute("data-chart-script");
    var type = root.getAttribute("data-chart-type") || "bar";
    var payload = parsePayload(scriptId);
    var emptyEl = root.querySelector("[data-chart-empty]");
    var canvas = root.querySelector("canvas");
    var wrap = root.querySelector("[data-chart-canvas-wrap]");

    if (isEmpty(payload)) {
      if (emptyEl) emptyEl.classList.remove("hidden");
      if (wrap) wrap.classList.add("hidden");
      if (canvas) canvas.classList.add("hidden");
      return null;
    }

    if (emptyEl) emptyEl.classList.add("hidden");
    if (wrap) wrap.classList.remove("hidden");
    if (!canvas) return null;

    if (type === "line") return renderLine(canvas, payload);
    if (type === "doughnut" || type === "donut") return renderDoughnut(canvas, payload);
    return renderBar(canvas, payload);
  }

  function mountAll(selector) {
    var nodes = document.querySelectorAll(selector || "[data-chart-root]");
    var charts = [];
    nodes.forEach(function (node) {
      var chart = mountRoot(node);
      if (chart) charts.push(chart);
    });
    return charts;
  }

  window.BlytzCharts = {
    colors: COLORS,
    prefersReducedMotion: prefersReducedMotion,
    parsePayload: parsePayload,
    isEmpty: isEmpty,
    mountRoot: mountRoot,
    mountAll: mountAll,
  };

  document.addEventListener("DOMContentLoaded", function () {
    mountAll();
  });
})();
