from pydantic import BaseModel, Field

from src.models.product import PriceSegment


class ClassificationItem(BaseModel):
    id: str
    segment: str


class SegmentBatchResponse(BaseModel):
    classifications: list[ClassificationItem] = Field(min_length=1)


SEGMENT_VALUES = [s.value for s in PriceSegment]

CLASSIFICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "classifications": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "segment": {
                        "type": "string",
                        "enum": SEGMENT_VALUES,
                    },
                },
                "required": ["id", "segment"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["classifications"],
    "additionalProperties": False,
}
