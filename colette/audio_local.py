"""Transport audio local (micro / haut-parleurs du laptop) basé sur sounddevice.

Copie de `pipecat.transports.local.audio.LocalAudioTransport` (pipecat 1.15) où PyAudio est
remplacé par sounddevice : PyAudio n'a pas de wheel arm64 et le Homebrew de la machine est
Intel (pas de portaudio arm64), alors que sounddevice embarque son propre PortAudio universel.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

import sounddevice as sd
from loguru import logger

from pipecat.frames.frames import InputAudioRawFrame, OutputAudioRawFrame, StartFrame
from pipecat.processors.frame_processor import FrameProcessor, FrameProcessorSetup
from pipecat.transports.base_input import BaseInputTransport
from pipecat.transports.base_output import BaseOutputTransport
from pipecat.transports.base_transport import BaseTransport, TransportParams


class LocalAudioTransportParams(TransportParams):
    input_device: int | str | None = None
    output_device: int | str | None = None


class LocalAudioInputTransport(BaseInputTransport):
    _params: LocalAudioTransportParams

    def __init__(self, params: LocalAudioTransportParams):
        super().__init__(params)
        self._in_stream: sd.RawInputStream | None = None

    async def setup(self, setup: FrameProcessorSetup):
        await super().setup(setup)

    async def start(self, frame: StartFrame):
        await super().start(frame)
        if self._in_stream is None:
            num_frames = int(self.sample_rate / 100) * 2  # 20 ms
            self._in_stream = sd.RawInputStream(
                samplerate=self.sample_rate,
                channels=self._params.audio_in_channels,
                dtype="int16",
                blocksize=num_frames,
                device=self._params.input_device,
                callback=self._audio_in_callback,
            )
            self._in_stream.start()
            logger.info("Micro ouvert ({} Hz, device={})", self.sample_rate, self._params.input_device)
        await self.set_transport_ready(frame)

    async def cleanup(self):
        await super().cleanup()
        if self._in_stream is not None:
            self._in_stream.stop()
            self._in_stream.close()
            self._in_stream = None

    def _audio_in_callback(self, indata, frames, time_info, status):
        frame = InputAudioRawFrame(
            audio=bytes(indata),
            sample_rate=self.sample_rate,
            num_channels=self._params.audio_in_channels,
        )
        asyncio.run_coroutine_threadsafe(self.push_audio_frame(frame), self.get_event_loop())


class LocalAudioOutputTransport(BaseOutputTransport):
    _params: LocalAudioTransportParams

    def __init__(self, params: LocalAudioTransportParams):
        super().__init__(params)
        self._out_stream: sd.RawOutputStream | None = None
        self._executor = ThreadPoolExecutor(max_workers=1)

    async def start(self, frame: StartFrame):
        await super().start(frame)
        if self._out_stream is None:
            self._out_stream = sd.RawOutputStream(
                samplerate=self.sample_rate,
                channels=self._params.audio_out_channels,
                dtype="int16",
                device=self._params.output_device,
            )
            self._out_stream.start()
            logger.info("Haut-parleurs ouverts ({} Hz)", self.sample_rate)
        await self.set_transport_ready(frame)

    async def cleanup(self):
        try:
            await super().cleanup()
            if self._out_stream is not None:
                self._out_stream.stop()
                self._out_stream.close()
                self._out_stream = None
        finally:
            self._executor.shutdown(wait=False)

    async def write_audio_frame(self, frame: OutputAudioRawFrame) -> bool:
        if self._out_stream is None:
            return False
        await self.get_event_loop().run_in_executor(self._executor, self._out_stream.write, frame.audio)
        return True


class LocalAudioTransport(BaseTransport):
    def __init__(self, params: LocalAudioTransportParams):
        super().__init__()
        self._params = params
        self._input: LocalAudioInputTransport | None = None
        self._output: LocalAudioOutputTransport | None = None

    def input(self) -> FrameProcessor:
        if not self._input:
            self._input = LocalAudioInputTransport(self._params)
        return self._input

    def output(self) -> FrameProcessor:
        if not self._output:
            self._output = LocalAudioOutputTransport(self._params)
        return self._output
