# YDL-7003-P data analyzer — Rahti web deployment

This package converts the supplied Tkinter desktop analyzer into a server-side
FastAPI application with a browser user interface.

## Local Docker test

```bash
docker build -t ydl7003p-web .
docker run --rm -p 8080:8080 ydl7003p-web
```

Open http://localhost:8080

To test OpenShift's arbitrary user model:

```bash
docker run --rm --user 1001230000:0 -p 8080:8080 ydl7003p-web
```

## Rahti

Import this Git repository using the Dockerfile strategy. The container listens
on port 8080. Create an edge-terminated HTTPS Route.

Use one replica. Analysis sessions are held in one process and expire after
eight hours.

For persistent recognizer training, mount a ReadWriteOnce PVC at `/data`.
Without a PVC, training survives only until the pod is replaced.

Recommended initial resources:

- request: 500m CPU, 1 GiB RAM
- limit: 2 CPU, 4 GiB RAM

## Health check

- path: `/health`
- port: 8080
- initial delay: 30 seconds
- timeout: 5 seconds

## Privacy

Uploaded photographs and generated reports are stored under `/tmp` and deleted
after session expiry or pod replacement. Do not enable request-body logging.

## Version 2 changes

- Persistent training templates configured by `YDL_TEMPLATE_PATH` are now loaded first.
- Added live magnifiers and crosshairs while screen and graph handles are dragged.
- Made Working/Ready/Error state prominent.
- Reorganized results and exports beside the input settings and reduced image-view height.


## Version 4 interface changes

- The result-screen validation message is now shown compactly in the top toolbar.
- The redundant Fit views button was removed; canvases already refit automatically after tab changes and browser resizing.
- The right side now uses two deliberate columns:
  - Axis calibration, sample settings and instrument values in the left column.
  - Tensile results and exports in the right column.
- CSV was removed from the user interface because the Excel workbook already contains curve data.
  The API endpoint remains available for compatibility.
- Select **Customize panels** to rearrange panels between the two columns and resize their height.
  Layout changes are stored in browser `localStorage`, so they are restored for the same browser profile
  on the same computer. They are not synchronized between devices or users.
- Select **Reset panels** while customization mode is active to restore the default layout.


## Version 6 changes

- If the tester timestamp is not detected, the browser's current local date and
  time are saved automatically as an editable default.
- Date and time have their own panel above the tensile results and are included
  in the results, graph, Excel workbook and PDF.
- The generated graph uses approximately 130% of the largest extracted
  extension and 130% of the larger instrument/curve maximum force as axis
  limits, rounded to readable values.
- Hidden manual break correction: hold Ctrl and left-click inside the generated
  analysis graph. The nearest curve extension is used as the break point and
  marked `(manual)` in results and exports.
- The Force (N) title is rotated and vertically centred.
- The status indicator is directly beside the re-analysis button.
- During server processing, the page uses a wait cursor and blocks input.


## Version 7 changes

- Manual break markers are placed in the value column of the generated
  parameter table, preventing the parameter labels from colliding with values.
- The expected-layout confirmation/warning box has a compact maximum width.
- The wait cursor and input blocking are controlled directly by the Working
  status. Every `Working — please wait…` state now activates them immediately.
- Static CSS and JavaScript URLs use version 7 to prevent stale browser caching.


## Version 8 changes

- Thickness and grammage are optional.
- Clearing either field now persists after recalculation, re-analysis and
  settings reload.
- Tensile stiffness remains calculable from slope, gauge length and width.
- Stiffness index is omitted when grammage is unavailable.
- Tensile modulus is omitted when thickness is unavailable.
- Web results, the analysis graph and Excel notes explain omitted values.
- If an optional field is not empty, it must contain a positive number.


## Version 9 settings-file changes

- Save settings uses the browser's native Save As dialog through
  `showSaveFilePicker` when supported. Microsoft Edge and Chromium-based Chrome
  support this on HTTPS and localhost.
- A standards-compatible download fallback remains for other browsers. In that
  fallback, the browser's own "ask where to save each file" setting determines
  whether a location dialog appears.
- The settings file now saves the values currently visible in the browser,
  including unsaved edits, blank optional thickness/grammage values, axis
  calibration and normalized graph-corner positions.
- Settings can be loaded before an image is selected. They are retained and
  applied automatically after the next image has been analysed.
- Version-1 settings files using `graph_plot_norm` remain supported.
- Invalid JSON, incorrect file types, invalid axes and malformed graph
  coordinates produce a visible error instead of being applied partially.


## Version 10 settings-file changes

- Settings files contain only:
  - gauge length;
  - sample width;
  - thickness, including an empty value;
  - grammage, including an empty value.
- Graph corners, graph rectangles, screen corners and axis calibration are not
  saved.
- Every newly selected photograph therefore receives fresh screen-corner,
  graph-corner and axis detection.
- Version 1 and version 2 JSON files can still be loaded, but any stored axes or
  graph positions in them are deliberately ignored.


## Version 11 graph-corner confirmation

- Moving any graph corner marks the graph geometry as manually edited.
- After selecting **Apply graph corners, then confirm axes**, the application:
  - applies the four graph corners;
  - highlights the Axis calibration panel;
  - scrolls the panel into view;
  - focuses and selects X max;
  - asks the user to verify all four axis values;
  - keeps the warning active until **Confirm axes and re-extract curve** is used.
- Editing an axis field no longer dismisses the confirmation request.
- Auto-detecting the graph clears the manual-corner confirmation state because
  graph corners and axes are then detected together.


## Version 12 provisional-result protection

This protection is activated only when a user manually moves a graph corner.

- As soon as a graph corner is moved:
  - the Analysis graph tab is disabled;
  - tensile results are covered by a confirmation notice;
  - Excel, PDF and corrected-PNG exports are disabled;
  - manual break-point selection is disabled.
- Applying the graph corners keeps the results provisional and moves attention
  to Axis calibration.
- Results and exports become available only after **Confirm axes and re-extract
  curve** completes successfully.
- Changing axis values by itself does not activate provisional mode.
- Auto-detecting the graph, choosing a new photograph, correcting the whole
  screen, or re-analysing the image performs fresh detection and clears the
  provisional state.
- The backend also rejects direct export requests while manually adjusted graph
  corners await axis confirmation.


## Version 13 regression fixes

- A compliant newly selected image always switches to Corrected screen after
  analysis.
- Hidden tab canvases are no longer resized to 1 × 1 pixels. They are drawn
  after the selected tab is visible.
- The corrected-screen image falls back to the clean rectified image if the
  annotated image cannot be loaded or is unexpectedly blank/dark.
- Image objects are reset for every newly selected photograph so stale display
  data cannot leak from the previous session.
- Provisional-result protection remains limited to an actual manual graph-corner
  movement.
- X-axis OCR is cross-checked against the independently detected green-curve
  endpoint and the recognized instrument elongation. A clearly inconsistent
  default/incorrect X maximum is replaced only when the independent estimate
  agrees with a standard instrument scale.


## Version 14 progressive image loading

- Tensile-test results remain visible as soon as the server analysis JSON arrives.
- The corrected-screen image now loads and is displayed independently of the analysis graph.
- For a compliant new image, the application switches to **Corrected screen** as soon as that image is ready instead of waiting for the analysis graph.
- The analysis graph loads afterward in the background.
- Visible loading notices explain that the corrected screen and/or analysis graph are still being transferred and rendered.
- This improves perceived responsiveness when the numerical results arrive before the PNG images.
