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

  function buildSettingsConfig(options) {
    const sample = options.sample || {};
    return {
      version: 3,
      kind: KIND,
      sample: {
        gauge_length_mm: numberOrNull(sample.gauge_length_mm),
        sample_width_mm: numberOrNull(sample.sample_width_mm),
        thickness_um: numberOrNull(sample.thickness_um),
        grammage_g_m2: numberOrNull(sample.grammage_g_m2)
      }
    };
  }

  function validateSettingsConfig(config) {
    if (!config || typeof config !== "object" || Array.isArray(config)) {
      throw new Error("The selected file does not contain a JSON settings object.");
    }
    if (config.kind && config.kind !== KIND) {
      throw new Error("The selected JSON file is not a YDL-7003-P settings file.");
    }

    // Version 1–2 files may contain axes and graph positions. They are
    // intentionally ignored because every photograph must receive fresh
    // screen, graph and axis detection.
    const sample = config.sample || config;
    const result = {
      version: 3,
      kind: KIND,
      sample: {
        gauge_length_mm: numberOrNull(sample.gauge_length_mm),
        sample_width_mm: numberOrNull(sample.sample_width_mm),
        thickness_um: numberOrNull(sample.thickness_um),
        grammage_g_m2: numberOrNull(sample.grammage_g_m2)
      }
    };

    if (
      result.sample.gauge_length_mm !== null &&
      result.sample.gauge_length_mm <= 0
    ) {
      throw new Error("Gauge length must be greater than zero.");
    }
    if (
      result.sample.sample_width_mm !== null &&
      result.sample.sample_width_mm <= 0
    ) {
      throw new Error("Sample width must be greater than zero.");
    }
    if (
      result.sample.thickness_um !== null &&
      result.sample.thickness_um <= 0
    ) {
      throw new Error("Thickness must be greater than zero or left empty.");
    }
    if (
      result.sample.grammage_g_m2 !== null &&
      result.sample.grammage_g_m2 <= 0
    ) {
      throw new Error("Grammage must be greater than zero or left empty.");
    }

    return result;
  }

  return {
    KIND,
    buildSettingsConfig,
    validateSettingsConfig
  };
}));
