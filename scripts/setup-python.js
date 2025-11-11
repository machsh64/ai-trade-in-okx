const { execSync } = require("child_process");
const { existsSync } = require("fs");
const path = require("path");
const os = require("os");

const projectRoot = path.resolve("./");
const isWin = os.platform().startsWith("win");
const condaPython = path.join(projectRoot, ".conda", isWin ? "python.exe" : "bin/python");

function run(cmd) {
  console.log(`> ${cmd}`);
  execSync(cmd, { stdio: "inherit", shell: true });
}

function detectConda() {
  try {
    execSync("conda --version", { stdio: "ignore", shell: true });
    return "conda";
  } catch {
    try {
      execSync("micromamba --version", { stdio: "ignore", shell: true });
      return "micromamba";
    } catch {
      return null;
    }
  }
}

try {
  console.log("🚀 Checking Python environment...");

  if (!existsSync(condaPython)) {
    const condaCmd = detectConda();
    if (!condaCmd) {
      console.error("Conda/Micromamba not found! Please install Miniconda first.");
      process.exit(1);
    }

    console.log(`Creating Python env with ${condaCmd} ...`);
    run(`${condaCmd} create -p ./.conda python=3.10 -y`);
  }

  console.log(`✅ Found project Python at ${condaPython}`);

  // 安装 pip/uv
  console.log("📦 Ensuring uv is installed...");
  run(`"${condaPython}" -m pip install -U pip uv`);

  console.log("📦 Installing backend dependencies with pip...");
  const coreDeps = [
    "fastapi",
    "uvicorn[standard]",
    "sqlalchemy",
    "python-dotenv",
    "ccxt",
    "schedule",
    "apscheduler",
    "requests",
    "python-multipart",
    "psycopg2-binary",
    "pandas",
    "numpy",
    "websockets",
    "pydantic",
    "letta-client"
  ];
  run(`"${condaPython}" -m pip install ${coreDeps.join(" ")}`);

  console.log("✅ Verifying dependencies...");
  run(`"${condaPython}" -c "import uvicorn, pandas, psycopg2, numpy"`);

  console.log("✅ Python dependencies installed successfully.");
} catch (err) {
  console.error("❌ Failed to setup Python environment:");
  console.error(err.message);
  process.exit(1);
}
