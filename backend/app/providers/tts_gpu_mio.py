"""The GPU engine's second voice: Indic-Mio (`gpu_engine/mio_engine.py`), used only when `GPU_VOICE_MODEL=mio`
and only by sessions and jobs on the GPU engine. The hosted engine keeps IndicF5.

Same calls as the IndicF5 engines (`/ref`, `/tts`), so this is the same client with three differences: one engine
process takes several lines at once (the language model batches them), it also speaks English, and it takes the
speaker from the sound alone, so the sample's text is not rewritten.
"""
import httpx

from app.config import Settings, get_settings
from app.providers.tts_gpu import GPU_LANGS, GpuVoice

MIO_LANGS = GPU_LANGS | {"en-IN"}


class MioVoice(GpuVoice):
    def __init__(self, settings: Settings | None = None, client: httpx.AsyncClient | None = None) -> None:
        s = settings or get_settings()
        super().__init__(s.model_copy(update={"gpu_voice_url": s.gpu_mio_url}), client)
        self.lanes = max(1, s.gpu_mio_lanes)

    @property
    def capacity(self) -> int:
        return self.lanes if self.urls else 1

    def speaks(self, lang: str) -> bool:
        return self.enabled and lang in MIO_LANGS
