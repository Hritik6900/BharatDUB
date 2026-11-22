"""v1's copied-voice servers, with the same calls as the IndicF5 engines (`/ref`, `/tts`, `/health`):

  IndicF5V1Voice  gpu_engine_v1/tts_server.py (:9041): one IndicF5 that batches the lines it is given at once
  MayaVoice       gpu_engine_v1/maya_server.py (:9042): Maya 2, also speaks English
"""
import httpx

from app.config import Settings, get_settings
from app.providers.tts_gpu import GPU_LANGS, GpuVoice

MAYA_LANGS = GPU_LANGS | {"en-IN"}


class IndicF5V1Voice(GpuVoice):
    name = "indicf5_v1"

    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None,
                 lanes: int = 4) -> None:
        s = settings or get_settings()
        super().__init__(s.model_copy(update={"gpu_voice_url": s.v1_tts_server_url}), client)
        self.lanes = max(1, lanes)

    @property
    def capacity(self) -> int:   # the one server takes several lines at once and batches them
        return self.lanes if self.urls else 1


class MayaVoice(GpuVoice):
    name = "maya"

    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None,
                 lanes: int = 1) -> None:
        s = settings or get_settings()
        super().__init__(s.model_copy(update={"gpu_voice_url": s.v1_maya_url}), client)
        self.lanes = max(1, lanes)

    @property
    def capacity(self) -> int:
        return self.lanes if self.urls else 1

    def speaks(self, lang: str) -> bool:
        return self.enabled and lang in MAYA_LANGS
