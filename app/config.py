from pathlib import Path
import os
import math
from pydantic import BaseModel, Field, model_validator

ROOT = Path(os.getenv('SENTINEL_DATA', './data')).resolve()
ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
for part in ('uploads', 'documents', 'cache', 'jobs', 'tmp'):
    (ROOT / part).mkdir(exist_ok=True, mode=0o700)
DATABASE_URL = os.getenv('DATABASE_URL', f'sqlite:///{ROOT}/sentinel.db')
MAX_UPLOAD = int(os.getenv('MAX_UPLOAD_BYTES', str(1024**3)))
CHUNK_SIZE = 8 * 1024**2
MAX_PAGES = int(os.getenv('MAX_PAGES', '2000'))
MAX_PIXELS = int(os.getenv('MAX_RENDER_PIXELS', '16000000'))
PAGE_TIMEOUT = int(os.getenv('PAGE_TIMEOUT_SECONDS', '180'))
JOB_TIMEOUT = int(os.getenv('JOB_TIMEOUT_SECONDS', '21600'))
MEMORY_MB = int(os.getenv('WORKER_MEMORY_MB', '4096'))
CONCURRENCY = max(1, min(8, int(os.getenv('PAGE_CONCURRENCY', '2'))))
ENGINE_VERSION = 'sentinel-1.1.0'
BATCH_SIZE = max(1,min(32,int(os.getenv('PAGE_BATCH_SIZE','8'))))
DEFAULT_WEIGHTS = dict(text=25, semantic=5, visual=20, layout=12, typography=10,
                       images=7, logos=3, tables=8, structure=5, forms=5, metadata=0)
PROFILES = {
 'strict': dict(pixel_threshold=0, min_component_pixels=1, position_tolerance=0, color_tolerance=0, registration_px=0, ignore_whitespace=False),
 'standard': dict(pixel_threshold=20, min_component_pixels=3, position_tolerance=0.75, color_tolerance=4, registration_px=1, ignore_whitespace=False),
 'content': dict(pixel_threshold=30, min_component_pixels=5, position_tolerance=2, color_tolerance=8, registration_px=2, ignore_whitespace=True,
                 weights=dict(text=55, semantic=15, visual=5, layout=0, typography=0, images=3, logos=2, tables=15, structure=0, forms=5, metadata=0)),
 'visual': dict(pixel_threshold=12, min_component_pixels=2, position_tolerance=0.5, color_tolerance=2, registration_px=1, ignore_whitespace=False,
                weights=dict(text=10, semantic=0, visual=40, layout=20, typography=10, images=10, logos=5, tables=3, structure=2, forms=0, metadata=0)),
}
class LogoRegion(BaseModel):
    label: str = Field(default='Logo', max_length=80)
    page_a: int = Field(ge=1)
    page_b: int = Field(ge=1)
    bbox_a: list[float] = Field(min_length=4, max_length=4)
    bbox_b: list[float] = Field(min_length=4, max_length=4)
    @model_validator(mode='after')
    def boxes(self):
        for b in (self.bbox_a, self.bbox_b):
            if any(not math.isfinite(v) for v in b) or min(b) < 0 or b[2] <= b[0] or b[3] <= b[1]: raise ValueError('Logo boxes must be finite positive PDF-point rectangles')
        return self
class Options(BaseModel):
    profile: str = 'standard'
    dpi: int = Field(default=150, ge=72, le=300)
    pixel_threshold: int = Field(default=20, ge=0, le=100)
    min_component_pixels: int = Field(default=3, ge=1, le=100)
    position_tolerance: float = Field(default=0.75, ge=0, le=20)
    color_tolerance: float = Field(default=4, ge=0, le=30)
    registration_px: float = Field(default=1, ge=0, le=3)
    ignore_whitespace: bool = False
    ocr: bool = True
    ocr_confidence: float = Field(default=.85, ge=0, le=1)
    alignment_threshold: float = Field(default=.53, ge=.2, le=1)
    ignore_metadata: list[str] = Field(default_factory=lambda:['creationDate','modDate','producer','creator'])
    weights: dict[str,float] = Field(default_factory=lambda:DEFAULT_WEIGHTS.copy())
    severity: dict[str,str] = Field(default_factory=dict)
    logos: list[LogoRegion] = Field(default_factory=list, max_length=100)
    @model_validator(mode='after')
    def valid(self):
        if self.profile not in {*PROFILES, 'custom'}: raise ValueError('Unknown profile')
        if set(self.weights) != set(DEFAULT_WEIGHTS) or any(not math.isfinite(v) or v<0 or v>100 for v in self.weights.values()) or sum(self.weights.values())<=0:
            raise ValueError('Supply all eleven nonnegative weights, with a positive total')
        if any(v not in ('critical','major','minor','informational') for v in self.severity.values()): raise ValueError('Invalid severity')
        return self
    @classmethod
    def from_input(cls, data):
        p=data.get('profile','standard'); merged={**PROFILES.get(p,{}), **data}
        return cls(**merged)
