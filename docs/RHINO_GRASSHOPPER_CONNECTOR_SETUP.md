# Rhino 8 / Grasshopper Local Connector Setup

This guide explains how to connect a local Rhino 8 installation to UrbanAgent's Rhino / Grasshopper connector.

## What UrbanAgent Expects

The current connector layer supports these execution modes:

1. Rhino.Compute health check
2. Grasshopper definition execution through Rhino.Compute
3. Grasshopper Hops HTTP endpoint invocation

UrbanAgent currently expects an HTTP-accessible service. A plain Rhino 8 desktop installation is not enough by itself; it needs one of the following:

1. Local Rhino.Compute launched from Rhino / Grasshopper
2. A local or remote Grasshopper Hops endpoint

## What Is Already Installed On This Machine

Rhino 8 is installed at:

`C:/Program Files/Rhino 8/System/Rhino.exe`

UrbanAgent has already verified that Rhino 8 exists locally. The previous connector health check failed because no local Rhino.Compute service was listening on `http://localhost:6500`.

## Recommended Path: Launch Local Rhino.Compute From Rhino 8

This is the fastest way to make the current connector work.

### Step 1. Open Rhino 8 and Grasshopper

1. Start Rhino 8.
2. Run the `Grasshopper` command.

### Step 2. Install Hops If Needed

According to the Rhino developer documentation for Rhino 7/8 on Windows, Hops can be installed from Rhino's package manager.

1. In Rhino, run `PackageManager`.
2. Search for `Hops`.
3. Install it.
4. Restart Rhino if prompted.

### Step 3. Enable Local Rhino.Compute

In Grasshopper:

1. Open `File > Preferences > Solver`.
2. Find the Hops settings.
3. Enable `Launch Local Rhino.Compute at Start`.
4. Set the compute server URL to `http://localhost:6500`.
5. Leave the API key empty for local testing, or set your own key and use the same value in UrbanAgent.
6. Restart Grasshopper or Rhino.

If this starts correctly, UrbanAgent's `rhino_health_check` should stop returning connection refused.

## Step 4. Configure UrbanAgent Environment Variables

Add these to the project environment file if you want explicit configuration:

```env
RHINO_COMPUTE_URL=http://localhost:6500
RHINO_COMPUTE_API_KEY=
RHINO_COMPUTE_TIMEOUT=120
```

If you set a non-empty API key in Hops / Rhino.Compute, the same key must be set in `RHINO_COMPUTE_API_KEY`.

## Step 5. Verify The Connector

Run:

```powershell
C:/Users/18029/.conda/envs/urban-mobility/python.exe d:/GitHub_1/world_agent/urban-mobility-agent/paper4_urban_svgagent/scripts/utils/test_rhino_connector.py --mode health
```

Expected outcome:

```json
{
  "success": true,
  "result": {
    ...
  }
}
```

If you still get `connection refused`, Rhino.Compute is not up yet.

## Creating A Grasshopper Definition That UrbanAgent Can Call

For the most stable first test, create a very small Grasshopper function.

### Example: Rectangle Area

1. Open Grasshopper.
2. Add two `Get Number` components named `width` and `height`.
3. Build a rectangle from those values.
4. Compute its area.
5. Add a `Context Print` or equivalent output component named `area`.
6. Save the file as a `.gh` or `.ghx` definition.

Suggested path:

`D:/GitHub_1/world_agent/urban-mobility-agent/paper4_urban_svgagent/artifacts/grasshopper/rectangle_area.ghx`

## Step 6. Execute The Definition Through UrbanAgent

Run:

```powershell
C:/Users/18029/.conda/envs/urban-mobility/python.exe d:/GitHub_1/world_agent/urban-mobility-agent/paper4_urban_svgagent/scripts/utils/test_rhino_connector.py --mode evaluate --definition-path "D:/GitHub_1/world_agent/urban-mobility-agent/paper4_urban_svgagent/artifacts/grasshopper/rectangle_area.ghx" --inputs-json "{\"width\": 12, \"height\": 8}"
```

UrbanAgent will:

1. read the Grasshopper definition
2. send it to Rhino.Compute
3. pass the input values as Grasshopper input trees
4. return the result JSON

## Optional Path: Use A Grasshopper Hops Endpoint

If you already expose a Hops endpoint, UrbanAgent can call it directly:

```powershell
C:/Users/18029/.conda/envs/urban-mobility/python.exe d:/GitHub_1/world_agent/urban-mobility-agent/paper4_urban_svgagent/scripts/utils/test_rhino_connector.py --mode hops --endpoint "http://localhost:6500/grasshopper" --inputs-json "{\"width\": 12, \"height\": 8}"
```

Use this route when you already have a Hops-based function service and do not want UrbanAgent to upload the full definition file each time.

## What Counts As A Real Software Breakthrough Here

Once this is working, UrbanAgent will not just analyze GIS data. It will be able to:

1. compute GIS indicators in Python
2. pass decision variables into Grasshopper
3. retrieve parametric design outputs
4. compare alternatives and loop back into analysis

That is the actual breakthrough: one agent framework coordinating urban GIS analysis and parametric design instead of treating them as separate software worlds.

## Current Limitation

The current connector is HTTP-based. It does not yet embed Rhino directly into Python. That means the supported production path today is:

`UrbanAgent -> connector -> Rhino.Compute / Hops -> Grasshopper`

If needed later, a second local execution path can be added via Rhino.Inside CPython.
