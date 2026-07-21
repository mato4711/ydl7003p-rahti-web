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
