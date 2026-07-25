(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.YDLSettingsIO = api;
  }
}(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const KIND = "mechanical_tester_sample_settings";

  function numberOrNull(value) {
    if (value === null || value === undefined || value === "") return null;
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  function validSize(size) {
    return size &&
      Number.isFinite(Number(size.width)) && Number(size.width) > 0 &&
      Number.isFinite(Number(size.height)) && Number(size.height) > 0;
  }

  function normaliseCorners(points, size) {
    if (!Array.isArray(points) || points.length !== 4 || !validSize(size)) {
      return null;
    }
    const width = Number(size.width);
    const height = Number(size.height);
    const result = points.map(point => {
      if (!Array.isArray(point) || point.length < 2) return null;
      const x = Number(point[0]);
      const y = Number(point[1]);
      if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
      return [x / width, y / height];
    });
    return result.every(Boolean) ? result : null;
  }

  function buildSettingsConfig(options) {
    const sample = options.sample || {};
    const axes = options.axes || {};
    return {
      version: 2,
      kind: KIND,
      saved_at: options.savedAt || new Date().toISOString(),
      source_image: options.sourceImage || "",
      sample: {
        gauge_length_mm: numberOrNull(sample.gauge_length_mm),
        sample_width_mm: numberOrNull(sample.sample_width_mm),
        thickness_um: numberOrNull(sample.thickness_um),
        grammage_g_m2: numberOrNull(sample.grammage_g_m2)
      },
      axes: {
        x_min: numberOrNull(axes.x_min),
        x_max: numberOrNull(axes.x_max),
        y_min: numberOrNull(axes.y_min),
        y_max: numberOrNull(axes.y_max)
      },
      graph_corners_norm: normaliseCorners(
        options.graphCorners,
        options.rectifiedSize
      )
    };
  }

  function validateSettingsConfig(config) {
    if (!config || typeof config !== "object" || Array.isArray(config)) {
      throw new Error("The selected file does not contain a JSON settings object.");
    }
    if (config.kind && config.kind !== KIND) {
      throw new Error("The selected JSON file is not a YDL-7003-P settings file.");
    }

    const sample = config.sample || config;
    const result = {
      ...config,
      version: Number(config.version || 1),
      kind: KIND,
      sample: {
        gauge_length_mm: numberOrNull(sample.gauge_length_mm),
        sample_width_mm: numberOrNull(sample.sample_width_mm),
        thickness_um: numberOrNull(sample.thickness_um),
        grammage_g_m2: numberOrNull(sample.grammage_g_m2)
      }
    };

    if (config.axes && typeof config.axes === "object") {
      result.axes = {
        x_min: numberOrNull(config.axes.x_min),
        x_max: numberOrNull(config.axes.x_max),
        y_min: numberOrNull(config.axes.y_min),
        y_max: numberOrNull(config.axes.y_max)
      };
      if (
        result.axes.x_min !== null && result.axes.x_max !== null &&
        result.axes.x_max <= result.axes.x_min
      ) {
        throw new Error("Saved X-axis maximum must exceed its minimum.");
      }
      if (
        result.axes.y_min !== null && result.axes.y_max !== null &&
        result.axes.y_max <= result.axes.y_min
      ) {
        throw new Error("Saved Y-axis maximum must exceed its minimum.");
      }
    } else {
      result.axes = null;
    }

    if (config.graph_corners_norm != null) {
      if (
        !Array.isArray(config.graph_corners_norm) ||
        config.graph_corners_norm.length !== 4 ||
        !config.graph_corners_norm.every(point =>
          Array.isArray(point) &&
          point.length >= 2 &&
          Number.isFinite(Number(point[0])) &&
          Number.isFinite(Number(point[1]))
        )
      ) {
        throw new Error("Saved graph-corner coordinates are invalid.");
      }
    }

    return result;
  }

  function graphCornersFromConfig(config, width, height) {
    if (!(Number(width) > 0 && Number(height) > 0)) return null;

    if (
      Array.isArray(config.graph_corners_norm) &&
      config.graph_corners_norm.length === 4
    ) {
      return config.graph_corners_norm.map(point => [
        Number(point[0]) * Number(width),
        Number(point[1]) * Number(height)
      ]);
    }

    // Version-1 compatibility.
    const plot = config.graph_plot_norm;
    if (
      Array.isArray(plot) &&
      plot.length >= 4 &&
      plot.every(value => Number.isFinite(Number(value)))
    ) {
      return [
        [Number(plot[0]) * width, Number(plot[1]) * height],
        [Number(plot[2]) * width, Number(plot[1]) * height],
        [Number(plot[2]) * width, Number(plot[3]) * height],
        [Number(plot[0]) * width, Number(plot[3]) * height]
      ];
    }

    return null;
  }

  return {
    KIND,
    buildSettingsConfig,
    validateSettingsConfig,
    graphCornersFromConfig
  };
}));
