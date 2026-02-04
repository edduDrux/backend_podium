from pydantic import BaseModel


class DocumentChunkOut(BaseModel):
    id: int
    document_id: int
    chunk_index: int
    content: str

    model_config = {"from_attributes": True}


class ChunkSearchHit(BaseModel):
    rank: float
    chunk: DocumentChunkOut
