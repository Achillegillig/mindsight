class MicrophoneRecorder extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = new Float32Array(2048);
    this.length = 0;
    this.remaining = 30 * sampleRate;
    this.port.onmessage = () => {
      this.flush();
      this.port.postMessage(null);
    };
  }

  flush() {
    if (!this.length) return;
    const chunk = this.buffer.slice(0, this.length);
    this.port.postMessage(chunk, [chunk.buffer]);
    this.length = 0;
  }

  process(inputs) {
    for (const sample of inputs[0]?.[0] ?? []) {
      if (this.remaining === 0) break;
      this.remaining--;
      this.buffer[this.length++] = sample;
      if (this.length === this.buffer.length) this.flush();
    }
    return true;
  }
}

registerProcessor("microphone-recorder", MicrophoneRecorder);
