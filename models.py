from dataclasses import dataclass, field
from enum import Enum, auto
import uuid
import re
from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import field, dataclass
from typing import ClassVar

class ValidationError(ValueError):
    """Raised when validation fails for a model field"""
    pass

class BlockType(Enum):
    TEXT = "text"
    HEADING = "heading"
    BULLET_LIST = "bullet_list"
    NUMBERED_LIST = "numbered_list"
    CHECKLIST = "checklist"
    DIVIDER = "divider"
    
    @classmethod
    def has_value(cls, value):
        return value in cls._value2member_map_

@dataclass
class BlockItem:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    content: str = ""
    checked: bool = False
    
    def validate(self):
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValidationError("Block item ID must be a non-empty string")
        if not isinstance(self.content, str):
            raise ValidationError("Block item content must be a string")
        if not isinstance(self.checked, bool):
            raise ValidationError("Block item checked status must be a boolean")

@dataclass
class Block:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: BlockType = BlockType.TEXT
    content: str = ""
    items: List[BlockItem] = field(default_factory=list)
    level: int = 1  # For headings (1-6)
    
    def validate(self):
        if not isinstance(self.id, str) or not self.id.strip():
            raise ValidationError("Block ID must be a non-empty string")
            
        if not BlockType.has_value(self.type.value if isinstance(self.type, BlockType) else self.type):
            raise ValidationError(f"Invalid block type: {self.type}")
            
        if not isinstance(self.content, str):
            raise ValidationError("Block content must be a string")
            
        if not isinstance(self.level, int) or not (1 <= self.level <= 6):
            raise ValidationError("Block level must be an integer between 1 and 6")
            
        if not isinstance(self.items, list):
            raise ValidationError("Block items must be a list")
            
        for item in self.items:
            if not isinstance(item, BlockItem):
                raise ValidationError("All block items must be instances of BlockItem")
            item.validate()

@dataclass
class Note:
    id: Optional[int] = None
    title: str = ""
    topic_id: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    blocks: List[Block] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    
    # Validation patterns
    TITLE_MAX_LENGTH: ClassVar[int] = 200
    TAG_PATTERN: ClassVar[re.Pattern] = re.compile(r'^[\w\-]{1,50}$')
    
    def validate(self):
        # Validate title
        if not isinstance(self.title, str) or not self.title.strip():
            raise ValidationError("Note title cannot be empty")
        if len(self.title) > self.TITLE_MAX_LENGTH:
            raise ValidationError(f"Note title cannot exceed {self.TITLE_MAX_LENGTH} characters")
            
        # Validate topic_id if provided
        if self.topic_id is not None and (not isinstance(self.topic_id, int) or self.topic_id <= 0):
            raise ValidationError("Topic ID must be a positive integer")
            
        # Validate blocks
        if not isinstance(self.blocks, list):
            raise ValidationError("Blocks must be a list")
            
        for block in self.blocks:
            if not isinstance(block, Block):
                raise ValidationError("All blocks must be instances of Block")
            block.validate()
        
        # Validate tags
        if not isinstance(self.tags, list):
            raise ValidationError("Tags must be a list")
            
        for tag in self.tags:
            if not isinstance(tag, str):
                raise ValidationError("All tags must be strings")
            if not self.TAG_PATTERN.match(tag):
                raise ValidationError(
                    f"Invalid tag format: '{tag}'. Tags can only contain letters, numbers, underscores, and hyphens, "
                    "must be 1-50 characters long, and cannot contain spaces."
                )

@dataclass
class Topic:
    id: Optional[int] = None
    name: str = ""
    parent_id: Optional[int] = None
    children: List['Topic'] = field(default_factory=list)
    note_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    NAME_MAX_LENGTH: ClassVar[int] = 100
    
    def validate(self):
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValidationError("Topic name cannot be empty")
            
        if len(self.name) > self.NAME_MAX_LENGTH:
            raise ValidationError(f"Topic name cannot exceed {self.NAME_MAX_LENGTH} characters")
            
        if self.parent_id is not None and (not isinstance(self.parent_id, int) or self.parent_id <= 0):
            raise ValidationError("Parent ID must be a positive integer")
            
        if not isinstance(self.note_count, int) or self.note_count < 0:
            raise ValidationError("Note count must be a non-negative integer")
            
        for child in self.children:
            if not isinstance(child, Topic):
                raise ValidationError("All children must be instances of Topic")
            child.validate()
