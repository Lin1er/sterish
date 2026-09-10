// Behaves exactly as its manifest says: reads a file, writes to stdout, no network.
// Stage 2 should observe it and find nothing to report.
const fs = require("fs");

const target = process.argv[2] || "./honest.json";
try {
  const text = fs.readFileSync(target, "utf8");
  process.stdout.write(`formatted ${text.length} bytes\n`);
} catch (err) {
  process.stdout.write(`nothing to format: ${err.code}\n`);
}
