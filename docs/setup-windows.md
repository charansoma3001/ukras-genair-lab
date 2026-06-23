# GenAIR Lab on Windows

The simulator this lab uses (AI2-THOR) doesn't ship a Windows build for the version we
need. The fix is simple: we run everything inside WSL2, which gives you a real Ubuntu
Linux setup on your Windows machine. Most of the commands below go in the **Ubuntu**
terminal. A few go in **PowerShell**, and those are called out.

Set aside about half an hour the first time. It's mostly waiting on downloads, and you
only do it once.

## Step 1: Install WSL2 and Ubuntu

Open **PowerShell as Administrator** (right-click the Start button and pick
*Terminal (Admin)*), then run:

```powershell
wsl --install
```

Restart your laptop when it's done.

After the restart, open **PowerShell as Administrator** again and run these two:

```powershell
wsl --update
wsl --install -d Ubuntu
```

An Ubuntu window pops up and asks you to make a username and password. Use whatever you
like; this is your Linux login and has nothing to do with your Windows password. If it
asks you to opt in to telemetry or Ubuntu Pro, just say no.

If you ever see "no installed distributions", it means WSL turned on but Ubuntu never
got installed. The two commands above (`wsl --update` then `wsl --install -d Ubuntu`)
sort that out. You can run `wsl --list --online` to see what's available and
`wsl --list --verbose` to see what you've already got.

From now on, you open Ubuntu by typing `wsl` in PowerShell, or by clicking **Ubuntu** in
the Start menu.

## Step 2: Update Ubuntu

In the Ubuntu terminal. `pwd` tells you where you are, and `~` is your home folder:

```bash
pwd
cd ~
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl
```

It'll ask for the password you just made.

## Step 3: Install uv

uv is the tool that runs the lab's Python code:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
uv --version
```

The `source ~/.bashrc` line just makes uv available in your current terminal so you
don't have to close and reopen it.

## Step 4: Download the lab

Still in Ubuntu:

```bash
git clone https://github.com/charansoma3001/ukras-genair-lab.git
cd ukras-genair-lab
uv sync
source .venv/bin/activate
cp .env.example .env
uv run mkdocs build
```

`uv sync` installs everything the lab needs. Hold off on starting it for now; you need a
model server running first, which is the next step.

## Step 5: Set up Ollama (the model server)

There are two ways to do this. Option A is the one we recommend because it works on every
Windows machine. Option B is worth it only if you want to use your laptop's GPU.

### Option A: Ollama inside Ubuntu (recommended)

Everything stays inside Ubuntu, so there's nothing fiddly to configure. Install it:

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Open a second Ubuntu terminal (Start menu, Ubuntu, or `wsl` in another PowerShell window),
start the server, and leave that window open:

```bash
ollama serve
```

Back in your first Ubuntu terminal, grab the model we use. It's about 2.1 GB and you only
download it once:

```bash
ollama pull granite4.1:3b
ollama list
```

You should see `granite4.1:3b` in the list. It runs on the CPU on most laptops, which is
totally fine here; this is a small model and it keeps up well. The default `.env` already
points at `localhost:11434`, so you don't need to change anything.

### Option B: Ollama on Windows (uses your GPU)

This can tap your GPU, but now the lab (running in Ubuntu) has to talk to Ollama (running
on Windows), and those two don't share `localhost` by default. The clean way to connect
them is mirrored networking.

1. Install Ollama for Windows from <https://ollama.com/download>. Once installed it runs
   quietly in the background.
2. In a Windows terminal, download the model:

   ```powershell
   ollama pull granite4.1:3b
   ```

3. Turn on mirrored networking so Ubuntu can reach Windows over `localhost`. Open Notepad
   and create the file `C:\Users\<your-name>\.wslconfig` with this in it:

   ```ini
   [wsl2]
   networkingMode=mirrored
   ```

4. In PowerShell, restart WSL so the change takes effect:

   ```powershell
   wsl --shutdown
   ```

   Reopen Ubuntu with `wsl`. The default `.env` now works as-is.

This needs Windows 11 (22H2 or newer). If the robot later says it can't reach the model,
your Windows is probably on the older networking mode. Switch to Option A and you're done
with the problem.

## Step 6: Run it

In the Ubuntu terminal, inside the `ukras-genair-lab` folder:

```bash
uv run genair
```

The very first run downloads the AI2-THOR simulator, which takes a few minutes. Every run
after that boots in around six seconds. When it tells you it's serving on
`http://localhost:8001`, you're good.

Open any browser on Windows (Chrome, Edge, Firefox) and go to:

```
http://localhost:8001
```

Type "pick up the apple" and watch the robot in the live video. If it actually picks up
the apple, your model connection is working from end to end. The book icon in the header
opens the Guide, which is where Tasks 1 to 5 live.

## Coming back to it later

You don't reinstall anything. Each time you want to use the lab:

If you went with Option A, open one terminal and start the model server:

```bash
ollama serve
```

Then in a second terminal, start the lab:

```bash
cd ukras-genair-lab
source .venv/bin/activate
uv run genair
```

Open `http://localhost:8001` and you're back. (With Option B, Ollama is already running
on Windows in the background, so you only need the lab terminal.)

## When something goes wrong

**`wsl` says "no installed distributions".** Run `wsl --update`, then
`wsl --install -d Ubuntu`, and reopen Ubuntu.

**`uv: command not found`.** Run `source ~/.bashrc`, or just close and reopen Ubuntu.

**The robot can't reach the model ("connection refused").** On Option A, check that
`ollama serve` is still running in its own terminal. On Option B, switch to Option A, or
double-check mirrored networking and that you ran `wsl --shutdown`.

**A "model not found" warning when the lab starts.** Run `ollama pull granite4.1:3b` and
restart the lab.

**The browser won't load `localhost:8001`.** Make sure the lab terminal actually printed
that it's serving, then restart it with `uv run genair`.

**The first run looks frozen.** It's downloading the simulator. Give it a few minutes;
this only happens once.

**PowerShell doesn't recognize `wsl`.** Update Windows (Settings, then Windows Update) and
try Step 1 again.

Still stuck? Grab a demonstrator and tell them which step you're on and the exact error.
