const FTMS_SERVICE = 0x1826;
const FITNESS_MACHINE_FEATURE = 0x2acc;
const INDOOR_BIKE_DATA = 0x2ad2;
const SUPPORTED_POWER_RANGE = 0x2ad8;
const FITNESS_MACHINE_CONTROL_POINT = 0x2ad9;
const FITNESS_MACHINE_STATUS = 0x2ada;

const OPCODES = {
  requestControl: 0x00,
  setTargetPower: 0x05,
  startOrResume: 0x07,
  stopOrPause: 0x08,
  setIndoorBikeSimulation: 0x11,
  setSpinDownControl: 0x13,
  responseCode: 0x80
};

const STATUS_OPCODES = {
  spinDownStatus: 0x14
};

const SPIN_DOWN_COMMANDS = {
  start: 0x01
};

const SPIN_DOWN_STATUSES = {
  0x01: "solicitada",
  0x02: "completada",
  0x03: "fallida",
  0x04: "deja de pedalear"
};

const RESULT_CODES = {
  0x01: "correcto",
  0x02: "no compatible",
  0x03: "valor no permitido",
  0x04: "operacion fallida",
  0x05: "control no permitido"
};

export class FtmsTrainer {
  constructor({ onData, onStatus, onMachineStatus, onDisconnect } = {}) {
    this.onData = onData;
    this.onStatus = onStatus;
    this.onMachineStatus = onMachineStatus;
    this.onDisconnect = onDisconnect;
    this.device = null;
    this.server = null;
    this.feature = null;
    this.supportedPowerRange = null;
    this.indoorBikeData = null;
    this.controlPoint = null;
    this.machineStatus = null;
    this.features = {
      rawMachineFeatures: 0,
      rawTargetSettingFeatures: 0,
      targetPower: null,
      spinDownControl: null,
      powerRange: null
    };
    this.pendingResponses = new Map();
    this.lastGrade = null;
    this.lastTargetPower = null;
  }

  get connected() {
    return Boolean(this.device?.gatt?.connected && this.controlPoint && this.indoorBikeData);
  }

  async connect() {
    if (!("bluetooth" in navigator)) {
      throw new Error("Este navegador no soporta Web Bluetooth. Usa Chrome o Edge.");
    }

    this.emitStatus("Selecciona el Tacx FLUX 2 Smart...");
    this.device = await navigator.bluetooth.requestDevice({
      filters: [
        { services: [FTMS_SERVICE] },
        { namePrefix: "Tacx" },
        { namePrefix: "FLUX" }
      ],
      optionalServices: [FTMS_SERVICE]
    });
    this.device.addEventListener("gattserverdisconnected", () => this.handleDisconnect());

    this.emitStatus("Conectando al rodillo...");
    this.server = await this.device.gatt.connect();
    const service = await this.server.getPrimaryService(FTMS_SERVICE);
    this.feature = await getOptionalCharacteristic(service, FITNESS_MACHINE_FEATURE);
    this.supportedPowerRange = await getOptionalCharacteristic(service, SUPPORTED_POWER_RANGE);
    this.indoorBikeData = await service.getCharacteristic(INDOOR_BIKE_DATA);
    this.controlPoint = await service.getCharacteristic(FITNESS_MACHINE_CONTROL_POINT);
    this.machineStatus = await getOptionalCharacteristic(service, FITNESS_MACHINE_STATUS);

    if (this.feature) this.features = parseFitnessMachineFeatures(await this.feature.readValue());
    if (this.supportedPowerRange) {
      this.features.powerRange = parseSupportedPowerRange(await this.supportedPowerRange.readValue());
      if (this.features.targetPower === null) this.features.targetPower = true;
    }

    this.controlPoint.addEventListener("characteristicvaluechanged", (event) => {
      this.handleControlPointResponse(event.target.value);
    });
    await this.controlPoint.startNotifications();

    this.indoorBikeData.addEventListener("characteristicvaluechanged", (event) => {
      this.onData?.(parseIndoorBikeData(event.target.value));
    });
    await this.indoorBikeData.startNotifications();

    if (this.machineStatus) {
      this.machineStatus.addEventListener("characteristicvaluechanged", (event) => {
        this.onMachineStatus?.(parseFitnessMachineStatus(event.target.value));
      });
      await this.machineStatus.startNotifications();
    }

    await this.writeControlPoint([OPCODES.requestControl], OPCODES.requestControl);
    this.emitStatus(`Conectado a ${this.device.name || "rodillo FTMS"}`);
    return this.device;
  }

  async disconnect() {
    if (!this.device) return;
    if (this.device.gatt?.connected) this.device.gatt.disconnect();
    this.handleDisconnect();
  }

  async start() {
    if (!this.connected) throw new Error("Conecta el rodillo antes de iniciar.");
    try {
      await this.writeControlPoint([OPCODES.startOrResume], OPCODES.startOrResume);
    } catch (error) {
      if (!String(error.message || "").includes("operacion fallida")) throw error;
    }
  }

  async pause() {
    if (!this.connected) return;
    await this.writeControlPoint([OPCODES.stopOrPause, 0x02], OPCODES.stopOrPause);
  }

  async neutralize() {
    if (!this.connected) return;
    this.lastTargetPower = null;
    await this.setGrade(0, { force: true });
    try {
      await this.pause();
    } catch (error) {
      if (!String(error.message || "").includes("operacion fallida")) throw error;
    }
  }

  async setGrade(gradePercent, { force = false } = {}) {
    if (!this.connected) return;
    const roundedGrade = Math.round(gradePercent * 10) / 10;
    if (!force && this.lastGrade !== null && Math.abs(roundedGrade - this.lastGrade) < 0.1) return;
    this.lastGrade = roundedGrade;

    const payload = new DataView(new ArrayBuffer(7));
    payload.setUint8(0, OPCODES.setIndoorBikeSimulation);
    payload.setInt16(1, 0, true);
    payload.setInt16(3, Math.round(gradePercent * 100), true);
    payload.setUint8(5, 40);
    payload.setUint8(6, 51);
    await this.writeControlPoint(payload, OPCODES.setIndoorBikeSimulation);
  }

  async setTargetPower(powerWatts, { force = false } = {}) {
    if (!this.connected) return;
    const targetPower = clampTargetPower(Math.round(powerWatts), this.features.powerRange);
    if (!force && this.lastTargetPower !== null && Math.abs(targetPower - this.lastTargetPower) < 1) return;
    this.lastTargetPower = targetPower;

    const payload = new DataView(new ArrayBuffer(3));
    payload.setUint8(0, OPCODES.setTargetPower);
    payload.setInt16(1, targetPower, true);
    await this.writeControlPoint(payload, OPCODES.setTargetPower);
  }

  async startSpinDownCalibration() {
    if (!this.connected) throw new Error("Conecta el rodillo antes de calibrar.");
    const response = await this.writeControlPoint(
      [OPCODES.setSpinDownControl, SPIN_DOWN_COMMANDS.start],
      OPCODES.setSpinDownControl
    );
    return parseSpinDownControlResponse(response.value);
  }

  async writeControlPoint(bytesOrView, responseOpcode) {
    if (!this.controlPoint) throw new Error("El punto de control FTMS no esta disponible.");
    const value = bytesOrView instanceof DataView ? bytesOrView : new Uint8Array(bytesOrView);
    const responsePromise = this.waitForResponse(responseOpcode);
    try {
      if (this.controlPoint.writeValueWithResponse) {
        await this.controlPoint.writeValueWithResponse(value);
      } else if (this.controlPoint.writeValue) {
        await this.controlPoint.writeValue(value);
      } else {
        await this.controlPoint.writeValueWithoutResponse(value);
      }
    } catch (error) {
      const pending = this.pendingResponses.get(responseOpcode);
      if (pending) {
        clearTimeout(pending.timer);
        this.pendingResponses.delete(responseOpcode);
      }
      throw error;
    }
    return responsePromise;
  }

  waitForResponse(opcode) {
    return new Promise((resolve, reject) => {
      const existing = this.pendingResponses.get(opcode);
      if (existing) {
        clearTimeout(existing.timer);
        existing.reject(new Error("Nueva orden FTMS enviada antes de confirmar la anterior."));
      }
      const timer = setTimeout(() => {
        this.pendingResponses.delete(opcode);
        resolve({ opcode, result: 0, message: "sin confirmacion" });
      }, 1800);
      this.pendingResponses.set(opcode, { resolve, reject, timer });
    });
  }

  handleControlPointResponse(value) {
    if (!value || value.byteLength < 3 || value.getUint8(0) !== OPCODES.responseCode) return;
    const requestOpcode = value.getUint8(1);
    const result = value.getUint8(2);
    const pending = this.pendingResponses.get(requestOpcode);
    if (!pending) return;
    clearTimeout(pending.timer);
    this.pendingResponses.delete(requestOpcode);
    if (result === 0x01) {
      pending.resolve({ opcode: requestOpcode, result, message: RESULT_CODES[result], value });
      return;
    }
    pending.reject(new Error(`FTMS rechazo la orden: ${RESULT_CODES[result] || `codigo ${result}`}.`));
  }

  handleDisconnect() {
    this.server = null;
    this.feature = null;
    this.indoorBikeData = null;
    this.controlPoint = null;
    this.machineStatus = null;
    this.features = {
      rawMachineFeatures: 0,
      rawTargetSettingFeatures: 0,
      targetPower: null,
      spinDownControl: null,
      powerRange: null
    };
    this.pendingResponses.forEach(({ timer, reject }) => {
      clearTimeout(timer);
      reject(new Error("El rodillo se ha desconectado."));
    });
    this.pendingResponses.clear();
    this.lastGrade = null;
    this.lastTargetPower = null;
    this.emitStatus("Rodillo desconectado");
    this.onDisconnect?.();
  }

  emitStatus(message) {
    this.onStatus?.(message);
  }
}

export function parseIndoorBikeData(value) {
  const flags = value.getUint16(0, true);
  let offset = 2;
  const data = {};

  if ((flags & 0x01) === 0) {
    data.speed_kph = readUint16(value, offset) / 100;
    offset += 2;
  }
  if (flags & 0x02) offset += 2;
  if (flags & 0x04) {
    data.cadence_rpm = readUint16(value, offset) / 2;
    offset += 2;
  }
  if (flags & 0x08) offset += 2;
  if (flags & 0x10) offset += 3;
  if (flags & 0x20) offset += 2;
  if (flags & 0x40) {
    data.power_w = readInt16(value, offset);
    offset += 2;
  }
  if (flags & 0x80) offset += 2;
  if (flags & 0x100) offset += 5;
  if (flags & 0x200) {
    data.heart_rate_bpm = value.getUint8(offset);
    offset += 1;
  }
  if (flags & 0x400) offset += 1;
  if (flags & 0x800) {
    data.elapsed_seconds = readUint16(value, offset);
    offset += 2;
  }
  if (flags & 0x1000) offset += 2;

  return data;
}

export function parseFitnessMachineFeatures(value) {
  const rawTargetSettingFeatures = readUint32(value, 4);
  return {
    rawMachineFeatures: readUint32(value, 0),
    rawTargetSettingFeatures,
    targetPower: value.byteLength >= 8 ? Boolean(rawTargetSettingFeatures & (1 << 3)) : null,
    spinDownControl: value.byteLength >= 8 ? Boolean(rawTargetSettingFeatures & (1 << 15)) : null,
    powerRange: null
  };
}

export function parseFitnessMachineStatus(value) {
  if (!value || value.byteLength < 1) return { opcode: 0, label: "estado desconocido" };
  const opcode = value.getUint8(0);
  if (opcode !== STATUS_OPCODES.spinDownStatus) return { opcode, label: "estado FTMS" };
  const spinDownStatus = value.byteLength >= 2 ? value.getUint8(1) : 0;
  return {
    opcode,
    type: "spin_down",
    spinDownStatus,
    label: SPIN_DOWN_STATUSES[spinDownStatus] || `estado ${spinDownStatus}`
  };
}

function parseSpinDownControlResponse(value) {
  const fallbackTargetSpeedKph = 30;
  if (!value || value.byteLength < 7) {
    return { targetSpeedKph: fallbackTargetSpeedKph, lowSpeedKph: null, highSpeedKph: null };
  }
  const firstSpeed = value.getUint16(3, true) / 100;
  const secondSpeed = value.getUint16(5, true) / 100;
  const speeds = [firstSpeed, secondSpeed].filter((speed) => speed > 0);
  if (!speeds.length) {
    return { targetSpeedKph: fallbackTargetSpeedKph, lowSpeedKph: null, highSpeedKph: null };
  }
  return {
    targetSpeedKph: Math.min(...speeds),
    lowSpeedKph: Math.min(...speeds),
    highSpeedKph: Math.max(...speeds)
  };
}

function parseSupportedPowerRange(value) {
  if (!value || value.byteLength < 6) return null;
  return {
    minPowerW: readInt16(value, 0),
    maxPowerW: readInt16(value, 2),
    incrementW: Math.max(1, readUint16(value, 4))
  };
}

function clampTargetPower(powerWatts, powerRange) {
  if (!powerRange) return powerWatts;
  const clamped = Math.min(powerRange.maxPowerW, Math.max(powerRange.minPowerW, powerWatts));
  const increment = powerRange.incrementW || 1;
  return Math.round(clamped / increment) * increment;
}

async function getOptionalCharacteristic(service, uuid) {
  try {
    return await service.getCharacteristic(uuid);
  } catch (error) {
    if (error.name === "NotFoundError") return null;
    throw error;
  }
}

function readUint16(value, offset) {
  return offset + 2 <= value.byteLength ? value.getUint16(offset, true) : 0;
}

function readInt16(value, offset) {
  return offset + 2 <= value.byteLength ? value.getInt16(offset, true) : 0;
}

function readUint32(value, offset) {
  return offset + 4 <= value.byteLength ? value.getUint32(offset, true) : 0;
}
