# YDL-7003-P web analyzer 1.15: update and hosting guide

Prepared 9 October 2026. Source baseline: mato4711/ydl7003p-rahti-web,
commit dc74d5273f9684be106917593f02c0ef98c9cf4f (main).
This is a prepared source update. It has not been pushed to GitHub or deployed
on your CSC account or home server.

## 1. What changed

The app distinguishes clear rupture, no clear rupture, and uncertain tests.
An operator can confirm either complete rupture or no complete rupture.
A small final force is no longer sufficient to declare a break.

All results are shown in the browser and included in the PDF and Excel reports:

- Maximum force and maximum engineering stress from the extracted curve.
- Extension and strain at maximum force.
- Initial stiffness, apparent tensile modulus, fit R-squared, tensile stiffness
  and stiffness index when their required inputs are available.
- Terminal extension, terminal strain and force at that point.
- Residual-load ratio: force at the selected endpoint / curve peak force.
- Work to maximum force, post-peak work and work to the selected endpoint.
- Break extension and break strain only for automatic clear rupture or
  operator-confirmed rupture.

For a plateau, the first digitized point reaching the maximum is used as the
peak location. Stress uses the curve peak, not the instrument MaxForce box,
so peak stress and peak strain describe the same curve point. The instrument
maximum is retained separately for comparison.

Engineering stress = F / (width x thickness in mm), in MPa.
Strain (%) = 100 x extension / gauge length.
Apparent modulus = initial force-extension slope x gauge length / area.
Post-peak work = integral of F dx from curve peak to selected endpoint.
1 N mm = 1 mJ. This is work, not energy per unit volume.

Work covers only the extracted interval. The app does not invent a straight
line from an unrecorded starting point to the first measured point.
The modulus fit uses a contiguous rising pre-peak interval and requires
R-squared >= 0.95. A low-resolution fit with fewer than eight image points
is flagged. If a usable fit is unavailable, modulus is left blank.
Thickness may be left blank: force, strain, stiffness and work are still
available, but stress and modulus are unavailable. Grammage is needed only
for stiffness index.

## 2. How to analyse a manually stopped test

1. Open the app and select the photograph. Check the corrected screen and
   the four graph corners as usual.
2. Confirm the actual axis values from the photograph. In this example the
   Y axis has 1 N ticks near a 12 N upper grid line, not 10 N ticks or 120 N.
   The X-axis limit must correspond to the right graph corner you selected;
   use the grid and tick labels, rather than assuming the displayed terminal
   extension is the X-axis maximum. The app supports low-force axis scales,
   but OCR may still require correction.
3. Check the instrument values against the photo: the supplied example shows
   extension 7.62 mm and MaxForce 1.23 N. Correct misread values and press
   'Use edited instrument values'.
4. In 'Observed test outcome', choose 'No rupture - manually stopped /
   extension limit' if you know the sample remained partly intact.
5. Leave 'Terminal extension' blank to use the estimated endpoint. If the
   trace drops to zero when you stop or unload the machine, inspect the
   estimated last loaded point. Enter the extension immediately BEFORE the
   unloading segment when needed, then press 'Apply outcome and endpoint'.
   The numeric extension must be inside the extracted/recorded test range.
6. Review peak, terminal and post-peak results, then export PDF or Excel.
   For a repeatable comparison, use the same test termination criterion and
   endpoint convention for every specimen.

'Uncertain' means a photograph cannot distinguish stopping/unloading from
physical rupture. It is deliberately not reported as complete rupture.
For a genuinely broken sample choose 'Complete rupture observed'. Ctrl-click
inside the analysis graph can set a confirmed manual break extension. This
is disabled when 'No rupture' is selected. Reapplying the outcome clears an
older manual break selection. To return to automatic analysis choose
'Automatic' and apply it; clear the terminal field if you also want its
automatic endpoint.

The automatic heuristic looks for a rapid drop from at least 50% of peak to
at most 5% of peak, followed by a sustained near-zero tail. Its search width
is 3.5% of the available extension span or at least three digitized steps.
It treats a drop within 4% of the endpoint span or four steps of the known
stopping position as uncertain. Smaller final drops are also uncertain.
A positive residual tail with no clear drop is 'No clear rupture'. These are
heuristic defaults, not a test standard or proof of a failure mechanism.

Terminal strain is the measured strain at the selected endpoint. It is NOT
written as '>= terminal strain'. If the specimen did not break, its unknown
break strain may exceed that value, but the measured terminal strain itself
is an ordinary measured value. Total work in a manually stopped test is
'Work to terminal point', not toughness to break.

For rupture reports the integration endpoint is the last loaded point before
the selected break. Force and ratio therefore describe that selected point,
not a separate measurement of force after the broken specimen was unloaded.

## 3. Update your GitHub source from Windows 11 / WSL

Use your existing Git and GitHub CLI setup. These are bash commands for WSL.
Download the ZIP and the patch into C:\unix (WSL path /mnt/c/unix).
The ZIP contains the complete updated project; the patch is the smallest
way to update an existing checkout and makes the changes easy to inspect.

Create a fresh checkout for this update, or work in a clean existing one:

```bash
cd /mnt/c/unix
git clone https://github.com/mato4711/ydl7003p-rahti-web.git
cd ydl7003p-rahti-web
git status --short
git switch -c update-progressive-curves
```

If that directory already exists, enter it and check 'git status' first.
Commit or otherwise preserve your own uncommitted work before applying this
update. Do not overwrite it with ZIP contents blindly.

Check that the patch applies to the source you have, then apply it:

```bash
git apply --check ../ydl7003p-web-1.15.patch
git apply ../ydl7003p-web-1.15.patch
git diff --stat
git diff --check
```

If the check fails, your repository has changes since the recorded baseline.
Use the ZIP as a reference and merge the relevant changes rather than forcing
the patch. Do not copy the old desktop Python script over analyzer_core.py.

Optional local checks, in a Python virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pip install pytest httpx
python -m pytest -q tests
```

The prepared update passed 15 regression checks covering force scales,
progressive softening, rupture, stopping, interpolation, work balance, API
validation, reports and provisional export protection. Also exercised the
actual supplied photo through upload, recalibration and no-rupture reporting.
Photo results require checking calibration and the instrument readings.

Commit and push the review branch:

```bash
git add analyzer_core.py app.py static/app.js static/index.html
git add README.md DEPLOYMENT.md compose.yaml .gitignore .dockerignore tests
git commit -m "Analyse progressive curves and incomplete rupture"
git push -u origin update-progressive-curves
```

Open a pull request on GitHub, review it, and merge into the branch your CSC
BuildConfig uses (often main, but inspect it in the next section). If you
prefer command line:

```bash
gh pr create --base main --head update-progressive-curves --fill
```

Merging/pushing code does not necessarily update the running app: CSC still
needs a successful image build and rollout. A configured webhook may trigger
this automatically; otherwise start it explicitly.

## 4. Update the existing deployment at CSC Rahti

Do not create a second CSC project or delete your existing deployment/PVC.
Use the existing project's BuildConfig, service, route and persistent data.
The source repository does not record their actual cluster names, so the
commands below discover them rather than inventing them.

### 4.1 Log in and identify the resources

Open the Rahti web console and choose your user menu -> Copy Login Command.
Copy the displayed oc login command into WSL. Use the token locally.
If oc is not installed, download the Linux client from the console's Help ->
Command Line Tools and put the extracted oc binary on your WSL PATH.

```bash
oc version --client
oc whoami
oc projects
oc project YOUR_EXISTING_PROJECT
oc get bc,deployments,dc,svc,route,pvc
```

Replace YOUR_EXISTING_PROJECT with the project shown in the console.
Set the following variables to the actual resource names from the listing:

```bash
BC=YOUR_BUILD_CONFIG
DEPLOY=YOUR_DEPLOYMENT
ROUTE=YOUR_ROUTE
```

Confirm repository URL, branch and build context:

```bash
oc get bc "$BC" -o yaml
oc get deployment "$DEPLOY" -o yaml
```

Inspect spec.source.git.uri and spec.source.git.ref (a missing ref uses the
repository default), spec.source.contextDir, spec.strategy and the output
image. If the branch is main, merge the update into main before building.
These instructions assume a Dockerfile BuildConfig using this repository.
If there is no BuildConfig, inspect how your current external image is built;
rebuild that image in its existing pipeline and update its image reference.

### 4.2 Preserve the deployment and trained templates

Save the cluster configuration in a backup folder outside your repository:

```bash
mkdir -p ../ydl7003p-rahti-backup
oc get bc,deployments,dc,svc,route,pvc -o yaml \
  > ../ydl7003p-rahti-backup/resources.yaml
oc get pods
```

If you trained digits online, select the running application pod and copy
its persistent template file. Absence of this file can simply mean no custom
training has been saved. The supplied digit_templates.npz remains bundled.

```bash
POD=YOUR_RUNNING_APP_POD
oc cp "$POD:/data/digit_templates_user.npz" \
  ../ydl7003p-rahti-backup/digit_templates_user.npz
```

The existing PVC mounted at /data should stay mounted. Without a PVC, custom
training disappears when the pod is replaced. Uploaded photos and reports
are temporary; download any reports you need before replacing the pod.

### 4.3 Build and observe rollout

After the GitHub update is merged into the configured source branch:

```bash
oc start-build "$BC" --follow --wait
oc get builds
oc rollout status deployment/"$DEPLOY" --timeout=300s
oc get pods
oc logs deployment/"$DEPLOY" --tail=100
oc get route "$ROUTE"
```

Use one replica and one Uvicorn worker: sessions live in a single Python
process. The Dockerfile already starts one worker. Keep the existing /data
PVC and edge HTTPS route.

If your older application uses a DeploymentConfig instead of a Deployment,
set DEPLOY to that name and substitute dc/$DEPLOY in rollout/log commands:

```bash
oc rollout status dc/"$DEPLOY" --timeout=300s
oc logs dc/"$DEPLOY" --tail=100
```

A successful build must be connected to the running workload by an image
change trigger, or its new image must be set explicitly. Inspect the
Deployment YAML for image.openshift.io/triggers. If nothing rolls out,
compare the BuildConfig output image with the deployment container image.
A blind pod restart is not evidence the new image was selected. Set the
container image to the newly built image digest using your existing image
stream/registry workflow, then wait for rollout.

### 4.4 Verify that the new version is actually running

```bash
APP_HOST=$(oc get route "$ROUTE" -o jsonpath='{.spec.host}')
curl -fsS "https://$APP_HOST/health"
```

Expected JSON includes status ok and version 1.15. Open the existing app URL
and press Ctrl+F5 to clear a cached interface. Confirm 'Observed test outcome'
and 'Terminal extension' appear. Analyse one normal broken specimen and one
manually stopped specimen. Check the graph, numerical results and PDF/Excel.

If the browser is old but /health says 1.15, refresh its cache. If /health
still shows the old version, check build and image rollout rather than
training data. A replaced pod invalidates old analysis sessions, so upload
the image again.

### 4.5 Web console alternative

After merging the code: choose the existing project -> Builds -> BuildConfigs
-> your existing BuildConfig -> Start Build (menu placement may vary). Watch
its logs to Complete. In Workloads -> Deployments, inspect the new rollout
and pod status. In Networking -> Routes open the existing route, refresh,
and verify /health. The CLI route above is more explicit if a build succeeds
but the workload does not update.

### 4.6 Local source build alternative (without a GitHub push)

From the extracted updated project directory, you can instead upload the
local build context to the existing BuildConfig:

```bash
oc start-build "$BC" --from-dir=. --follow --wait
```

This build uses the local files, not the committed GitHub revision. Keep the
repository in sync afterwards, otherwise the next Git-based build may undo
this update. Exclude .venv, data and backup folders from the uploaded context.

### 4.7 Rollback

Keep the previous working revision/image available. Deployment rollback:

```bash
oc rollout history deployment/"$DEPLOY"
oc rollout undo deployment/"$DEPLOY"
oc rollout status deployment/"$DEPLOY" --timeout=300s
```

If the image trigger reselects the new image, use a Git revert of the update
commit on the source branch and rebuild through the same BuildConfig. Do
not delete the /data PVC. Downloaded reports remain usable; live sessions
will have to be recreated after a pod replacement.

## 5. Host it on M720q / Debian

Your current Debian/Docker server can run the same app. No Android Studio,
GPU, external AI API, database, or desktop GUI is required. NumPy, OpenCV,
Pillow and Tesseract are installed inside the image. Allow approximately
1-2 GB RAM initially, with two CPUs as a starting limit; measure actual
usage with your images. This is a sizing estimate, not a server benchmark.
Keep this application as a separate Compose project from Immich and wine.

### 5.1 Copy the project to the server

The supplied ZIP contains folder ydl7003p-web-1.15. From WSL, copy it to the
M720q (the configured ssh alias may be used if available):

```bash
scp /mnt/c/unix/ydl7003p-web-1.15.zip m@192.168.178.185:~/
ssh m@192.168.178.185
```

On M720q:

```bash
docker --version
docker compose version
sudo install -d -o m -g m /opt/docker/ydl7003p
python3 -m zipfile -e ~/ydl7003p-web-1.15.zip /tmp/ydl-update
cp -a /tmp/ydl-update/ydl7003p-web-1.15/. /opt/docker/ydl7003p/
cd /opt/docker/ydl7003p
mkdir -p data
docker compose config
docker compose up -d --build
docker compose ps
curl -fsS http://127.0.0.1:8093/health
```

Use sudo for Docker commands if your existing setup requires it. Port 8093
is a proposed app port, not a claim about your current ports. If occupied,
change the left side of the Compose ports entry and the access commands.
The supplied compose.yaml binds to 127.0.0.1, so it is initially reachable
only on the server. The built-in Docker health check targets port 8080
inside the container; do not change that when changing the host port.
The Docker image has not been built in this workspace; these are your
initial on-server build and runtime checks.

### 5.2 Private remote access with Tailscale Serve (recommended)

First inspect your existing configuration so the analyzer does not replace
an Immich or wine service:

```bash
sudo tailscale serve status
sudo tailscale funnel status
```

Choose a free HTTPS port. Example using 8443 ONLY if it is currently unused:

```bash
sudo tailscale serve --bg --https=8443 http://127.0.0.1:8093
```

Open the HTTPS address printed by the command, including :8443, on a device
signed into your Tailscale network. Serve handles HTTPS and resumes with
--bg after reboot. Use the root of that port rather than /analyzer because
the application currently uses root-relative /api and /static URLs.

### 5.3 Optional public access with Tailscale Funnel

Funnel makes the app reachable publicly, including its shared template-
training function. The app currently has no login. For your own devices,
keep private Serve access. For intentional public access choose an unused
allowed HTTPS port (443, 8443 or 10000). For example, only if 10000 is free:

```bash
sudo tailscale funnel --bg --https=10000 http://127.0.0.1:8093
sudo tailscale funnel status
```

Follow the printed public address. Funnel may request enabling the feature
in your tailnet; complete that if needed. It works behind CGNAT without
router port forwarding. Do not run serve reset or funnel reset: those clear
existing configurations. Configure only the chosen unused port.

### 5.4 LAN access alternative

If you want access as http://192.168.178.185:8093 on the home LAN, change
127.0.0.1:8093:8080 to 192.168.178.185:8093:8080 in compose.yaml, then:

```bash
docker compose up -d
```

Use private Tailscale HTTPS when convenient; browser features such as a
native settings Save As dialog work better on HTTPS than a plain LAN URL.
If you change the bind away from loopback, adjust any Serve/Funnel target
accordingly; alternatively retain loopback and add a second LAN binding.

### 5.5 Updates, backup and recovery

For future updates preserve data/ and replace the application source, then:

```bash
cd /opt/docker/ydl7003p
docker compose up -d --build
docker compose logs --tail=100
curl -fsS http://127.0.0.1:8093/health
docker stats --no-stream ydl7003p-analyzer
```

Back up /opt/docker/ydl7003p/compose.yaml, the application source (or its Git
revision/ZIP), and /opt/docker/ydl7003p/data/. The custom recognizer is saved
as data/digit_templates_user.npz. Add that small directory to your existing
M720q-to-Synology backup; the existing off-site restic copy can then protect
it too. This task has not changed your backup scripts.

No permanent photo/report database is created. Sessions and generated
reports are temporary (/tmp in the container), are cleaned on access after
eight hours of inactivity, and are lost when the container is recreated.
Download reports you want to retain. Restoring source + compose.yaml + data/
and running docker compose up -d --build is sufficient to restore the app;
it cannot restore earlier temporary sessions.

To stop just this app:

```bash
cd /opt/docker/ydl7003p
docker compose down
```

This does not delete the bind-mounted data/ directory. Do not use a global
Docker prune as part of an application update or recovery.

## 6. Official deployment references

CSC: CLI download and login
https://docs.csc.fi/cloud/rahti/get-started/cli/

CSC: container builds, Git and local source
https://docs.csc.fi/cloud/rahti/usage/images/creating/

Tailscale Serve: private HTTPS proxy and background persistence
https://tailscale.com/docs/reference/tailscale-cli/serve

Tailscale Funnel: public HTTPS, allowed ports and background persistence
https://tailscale.com/docs/reference/tailscale-cli/funnel

Deployment names, current port occupancy, PVC status and remaining memory
must be checked on your actual systems. The guide supplies discovery steps
because no authenticated CSC or M720q session was available in this task.
