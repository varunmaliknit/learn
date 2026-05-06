const requiredMajor = 20;
const [major] = process.versions.node.split(".").map(Number);

if (major !== requiredMajor) {
  console.error(
    `Unsupported Node.js version ${process.version}. Use Node ${requiredMajor}.x for this project.`,
  );
  console.error(
    "Run `nvm use` if you have nvm installed, then rerun the npm command.",
  );
  process.exit(1);
}
