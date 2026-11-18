from core.adapters.base import ModelAdapter, SegmentationResult
from core.adapters.refattn_unet_v1 import RefAttUNetV1

ADAPTERS: dict[str, type[ModelAdapter]] = {
    RefAttUNetV1.name: RefAttUNetV1,
}

__all__ = ["ADAPTERS", "ModelAdapter", "SegmentationResult", "RefAttUNetV1"]
