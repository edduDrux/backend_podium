from enum import Enum


class DocumentStatus(str, Enum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    EXTRACTED = "EXTRACTED"
    CHUNKED = "CHUNKED"
    FAILED = "FAILED"
    READY = "READY"


class SessionStatus(str, Enum):
    READY = "READY"
    RUNNING = "RUNNING"
    FINISHED = "FINISHED"
    FAILED = "FAILED"


class QuestionIntent(str, Enum):
    CLARIFICATION = "clarification"
    DEEP_DIVE = "deep_dive"
    CHALLENGE = "challenge"
    PRACTICAL = "practical"
    GENERAL = "general"


class QuestionDifficulty(int, Enum):
    VERY_EASY = 1
    EASY = 2
    MEDIUM = 3
    HARD = 4
    VERY_HARD = 5
