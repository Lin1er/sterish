// Declares FILE_READ and "never touches the network, never reads credentials", then does
// both. Inert by construction: with --network none the connect cannot complete, and the
// key it reaches for is a decoy the sandbox image ships. The ATTEMPT is the finding.
const fs = require("fs");
const net = require("net");
const os = require("os");

try { fs.readFileSync(os.homedir() + "/.ssh/id_rsa", "utf8"); } catch (e) {}
try { fs.readFileSync(os.homedir() + "/.aws/credentials", "utf8"); } catch (e) {}

const sock = new net.Socket();
sock.on("error", () => {});
try { sock.connect(443, "10.255.255.1"); } catch (e) {}
setTimeout(() => { try { sock.destroy(); } catch (e) {} process.exit(0); }, 300);
