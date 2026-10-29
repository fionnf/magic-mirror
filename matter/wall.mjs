// The wall as a Matter on/off plug, so Smart Life (or Google Home, Apple Home) can switch it.
// Switching on resumes what was on before (or the art of the day); off turns the panels dark.
// It talks to the wall's own web app on this Pi (http://localhost/api/...), and follows it, so a
// change made in the app shows in Smart Life within a few seconds.
//
// The pairing code is made once and kept in ~/.matter/fortuna-pairing.json; it is also written to
// panel_setup/matter_pairing.json so the web app can show it.
import { Endpoint, ServerNode, VendorId } from "@matter/main";
import { OnOffPlugInUnitDevice } from "@matter/main/devices/on-off-plug-in-unit";
import { randomInt } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const WALL = "http://localhost";
const HERE = dirname(fileURLToPath(import.meta.url));
const SECRET = join(homedir(), ".matter", "fortuna-pairing.json");
const SHOWN = join(HERE, "..", "panel_setup", "matter_pairing.json");

function pairing() {
    if (existsSync(SECRET)) return JSON.parse(readFileSync(SECRET, "utf8"));
    const bad = new Set([0, 11111111, 22222222, 33333333, 44444444, 55555555, 66666666, 77777777,
                         88888888, 99999999, 12345678, 87654321]);
    let passcode;
    do passcode = randomInt(1, 99999999); while (bad.has(passcode));
    const p = { passcode, discriminator: randomInt(0, 4096) };
    mkdirSync(dirname(SECRET), { recursive: true });
    writeFileSync(SECRET, JSON.stringify(p), { mode: 0o600 });
    return p;
}

async function wall(path, body) {
    const r = await fetch(WALL + path, body === undefined ? {} :
        { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!r.ok) throw new Error(`${path}: ${r.status}`);
    return r.json();
}

const { passcode, discriminator } = pairing();
const server = await ServerNode.create({
    id: "fortuna-wall",
    network: { port: 5540 },
    commissioning: { passcode, discriminator },
    productDescription: { name: "Fortuna Wall", deviceType: OnOffPlugInUnitDevice.deviceType },
    basicInformation: {
        vendorName: "House Fortuna", vendorId: VendorId(0xfff1), productId: 0x8000,
        productName: "LED Wall", productLabel: "LED Wall", nodeLabel: "Fortuna Wall",
        serialNumber: "fortuna-wall-1", uniqueId: "fortuna-wall-1",
    },
});
const plug = new Endpoint(OnOffPlugInUnitDevice, { id: "wall" });
await server.add(plug);

let lastOn = "daily";          // what to bring back when switched on
let following = false;         // true while we copy the wall's state in (not a command from outside)

plug.events.onOff.onOff$Changed.on(async on => {
    if (following) return;
    try {
        await wall("/api/play", { mode: on ? lastOn : "off" });
        console.log(`[matter] switched ${on ? "on (" + lastOn + ")" : "off"}`);
    } catch (e) {
        console.log(`[matter] could not switch: ${e.message}`);
    }
});

async function follow() {
    try {
        const s = await wall("/api/status");
        const on = s.current !== "off" && s.current !== null;
        if (on) lastOn = s.current;
        if (plug.state.onOff.onOff !== on) {
            following = true;
            try { await plug.set({ onOff: { onOff: on } }); } finally { following = false; }
        }
    } catch (e) { /* the wall is restarting: try again next time */ }
}

await server.start();
const codes = server.state.commissioning.pairingCodes;
writeFileSync(SHOWN, JSON.stringify({ qr: codes.qrPairingCode, manual: codes.manualPairingCode,
                                      paired: server.state.commissioning.commissioned }));
console.log(`[matter] Fortuna Wall ready. Pairing code ${codes.manualPairingCode}  QR ${codes.qrPairingCode}`);
await follow();
setInterval(follow, 3000);
