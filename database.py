import sqlite3
from typing import List, Dict, Optional, Any, Tuple, Union
from datetime import datetime
import os
import json
import logging
from dataclasses import asdict
from models import Block, BlockType, BlockItem

# Set up logging
logging.basicConfig(level=logging.ERROR, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                   filename='app_errors.log')
logger = logging.getLogger(__name__)

class DatabaseError(Exception):
    """Custom exception for database-related errors"""
    pass

class DatabaseManager:
    def __init__(self, db_path: str = 'mindforge.db'):
        self.db_path = db_path
        self._init_db()
        
    def _get_connection(self):
        try:
            conn = sqlite3.connect(self.db_path)
            # Enable foreign key constraints
            conn.execute('PRAGMA foreign_keys = ON')
            return conn
        except sqlite3.Error as e:
            logger.error(f"Error connecting to database: {e}")
            raise DatabaseError(f"Failed to connect to database: {e}")
    
    def _init_db(self):
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Enable foreign key support
                cursor.execute('PRAGMA foreign_keys = ON')
                
                # Create tables if they don't exist
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS topics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        parent_id INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (parent_id) REFERENCES topics (id) ON DELETE CASCADE
                    )
                ''')
                
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS notes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        topic_id INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (topic_id) REFERENCES topics (id) ON DELETE SET NULL,
                        CHECK (LENGTH(TRIM(title)) > 0)
                    )
                ''')
                
                # Tags table
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS tags (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL UNIQUE,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                # Note-Tag relationship
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS note_tags (
                        note_id INTEGER,
                        tag_id INTEGER,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (note_id, tag_id),
                        FOREIGN KEY (note_id) REFERENCES notes (id) ON DELETE CASCADE,
                        FOREIGN KEY (tag_id) REFERENCES tags (id) ON DELETE CASCADE
                    )
                ''')
                
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS blocks (
                        id TEXT PRIMARY KEY,
                        note_id INTEGER NOT NULL,
                        type TEXT NOT NULL,
                        content TEXT,
                        items_json TEXT,
                        level INTEGER DEFAULT 1,
                        position INTEGER NOT NULL,
                        FOREIGN KEY (note_id) REFERENCES notes (id) ON DELETE CASCADE,
                        CHECK (position >= 0),
                        CHECK (level BETWEEN 1 AND 6)
                    )
                ''')
                
                # Create indexes for better performance
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_blocks_note_id ON blocks(note_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_notes_topic_id ON notes(topic_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_topics_parent_id ON topics(parent_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_note_tags_note_id ON note_tags(note_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_note_tags_tag_id ON note_tags(tag_id)')
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name)')
                
                conn.commit()
                
        except sqlite3.Error as e:
            logger.error(f"Error initializing database: {e}")
            raise DatabaseError(f"Failed to initialize database: {e}")
    
    # Topic operations
    def create_topic(self, name: str, parent_id: Optional[int] = None) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO topics (name, parent_id) VALUES (?, ?)',
                (name, parent_id)
            )
            conn.commit()
            return cursor.lastrowid
    
    def get_topics_tree(self) -> List[Dict]:
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Fetch all topics
            cursor.execute('SELECT id, name, parent_id FROM topics ORDER BY name')
            topics = [dict(row) for row in cursor.fetchall()]
            
            # Build tree structure
            topic_map = {topic['id']: {**topic, 'children': []} for topic in topics}
            root_topics = []
            
            for topic in topics:
                if topic['parent_id'] is None:
                    root_topics.append(topic_map[topic['id']])
                else:
                    parent = topic_map.get(topic['parent_id'])
                    if parent:
                        parent['children'].append(topic_map[topic['id']])
            
            return root_topics
    
    # Note operations
    def create_note(self, title: str, topic_id: Optional[int] = None) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO notes (title, topic_id) VALUES (?, ?)',
                (title, topic_id)
            )
            conn.commit()
            return cursor.lastrowid
    
    def save_note(self, note: 'Note') -> int:
        if not hasattr(note, 'title') or not note.title.strip():
            raise ValueError("Note title cannot be empty")
            
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                if note.id is None:
                    # Insert new note
                    cursor.execute(
                        'INSERT INTO notes (title, topic_id) VALUES (?, ?)',
                        (note.title, note.topic_id)
                    )
                    note_id = cursor.lastrowid
                    note.id = note_id
                else:
                    # Update existing note
                    note_id = note.id
                    cursor.execute(
                        'UPDATE notes SET title = ?, topic_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                        (note.title, note.topic_id, note_id)
                    )
                    # Delete existing blocks
                    cursor.execute('DELETE FROM blocks WHERE note_id = ?', (note_id,))
                
                # Save blocks
                for i, block in enumerate(note.blocks):
                    if not hasattr(block, 'type') or not hasattr(block, 'content'):
                        logger.warning(f"Skipping invalid block: {block}")
                        continue
                        
                    items_json = json.dumps([asdict(item) for item in block.items]) if block.items else None
                    try:
                        cursor.execute(
                            'INSERT INTO blocks (id, note_id, type, content, items_json, level, position) '
                            'VALUES (?, ?, ?, ?, ?, ?, ?)',
                            (block.id, note_id, block.type.value, block.content, items_json, block.level, i)
                        )
                    except Exception as e:
                        logger.error(f"Error saving block {block.id}: {e}")
                        raise DatabaseError(f"Failed to save block: {e}")
                
                # Save tags
                if hasattr(note, 'tags') and note.tags:
                    self._update_note_tags(conn, note_id, note.tags)
                
                conn.commit()
                return note_id
                
        except sqlite3.Error as e:
            logger.error(f"Error saving note: {e}")
            raise DatabaseError(f"Failed to save note: {e}")
    
    def _update_note_tags(self, conn, note_id: int, tags: List[str]) -> None:
        """Update tags for a note"""
        cursor = conn.cursor()
        
        # Remove existing tags
        cursor.execute('DELETE FROM note_tags WHERE note_id = ?', (note_id,))
        
        # Add new tags
        for tag_name in set(tags):  # Remove duplicates
            if not tag_name.strip():
                continue
                
            # Get or create tag
            cursor.execute('INSERT OR IGNORE INTO tags (name) VALUES (?)', (tag_name.lower().strip(),))
            cursor.execute('SELECT id FROM tags WHERE name = ?', (tag_name.lower().strip(),))
            result = cursor.fetchone()
            if result:  # Check if we got a result
                tag_id = result[0]
                # Link tag to note
                cursor.execute(
                    'INSERT OR IGNORE INTO note_tags (note_id, tag_id) VALUES (?, ?)',
                    (note_id, tag_id)
                )
    
    def get_note_by_id(self, note_id: int) -> Optional[Dict]:
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                'SELECT id, title, topic_id, created_at, updated_at FROM notes WHERE id = ?',
                (note_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def load_notes(self, topic_id: Optional[int] = None) -> List[Dict]:
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            if topic_id is not None:
                cursor.execute(
                    '''
                    SELECT id, title, topic_id, created_at, updated_at 
                    FROM notes 
                    WHERE topic_id = ? 
                    ORDER BY updated_at DESC
                    ''',
                    (topic_id,)
                )
            else:
                cursor.execute(
                    'SELECT id, title, topic_id, created_at, updated_at FROM notes ORDER BY updated_at DESC'
                )
            
            return [dict(row) for row in cursor.fetchall()]
    
    def load_note_blocks(self, note_id: int) -> List[Block]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT id, type, content, items_json, level FROM blocks WHERE note_id = ? ORDER BY position',
                (note_id,)
            )
            
            blocks = []
            for row in cursor.fetchall():
                block_id, type_str, content, items_json, level = row
                block_type = BlockType(type_str)
                
                # Parse items if they exist
                items = []
                if items_json:
                    try:
                        items_data = json.loads(items_json)
                        items = [
                            BlockItem(
                                id=item.get('id', ''),
                                content=item.get('content', ''),
                                checked=item.get('checked', False)
                            )
                            for item in items_data
                        ]
                    except json.JSONDecodeError:
                        pass
                
                blocks.append(Block(
                    id=block_id,
                    type=block_type,
                    content=content,
                    items=items,
                    level=level
                ))
            
            return blocks
    
    def get_note(self, note_id: int) -> Optional['Note']:
        if not isinstance(note_id, int) or note_id <= 0:
            raise ValueError("Invalid note ID")
            
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                # Get note data
                cursor.execute('''
                    SELECT id, title, topic_id, created_at, updated_at 
                    FROM notes WHERE id = ?
                ''', (note_id,))
                note_data = cursor.fetchone()
                
                if not note_data:
                    return None
                    
                note = Note(
                    id=note_data[0],
                    title=note_data[1],
                    topic_id=note_data[2],
                    created_at=note_data[3],
                    updated_at=note_data[4]
                )
                
                # Get blocks for the note
                cursor.execute('''
                    SELECT id, type, content, items_json, level, position 
                    FROM blocks WHERE note_id = ? 
                    ORDER BY position
                ''', (note_id,))
                
                blocks = []
                for block_data in cursor.fetchall():
                    try:
                        block = Block(
                            id=block_data[0],
                            type=BlockType(block_data[1]),
                            content=block_data[2] or '',
                            level=block_data[4] or 1
                        )
                        
                        # Load items if available
                        if block_data[3]:
                            items_data = json.loads(block_data[3])
                            block.items = [BlockItem(**item) for item in items_data]
                        
                        blocks.append(block)
                    except (json.JSONDecodeError, ValueError) as e:
                        logger.error(f"Error loading block {block_data[0]}: {e}")
                        continue
                
                note.blocks = blocks
                
                # Load tags for the note
                cursor.execute('''
                    SELECT t.name 
                    FROM tags t
                    JOIN note_tags nt ON t.id = nt.tag_id
                    WHERE nt.note_id = ?
                ''', (note_id,))
                
                note.tags = [row[0] for row in cursor.fetchall()]
                
                return note
                
        except sqlite3.Error as e:
            logger.error(f"Error getting note {note_id}: {e}")
            raise DatabaseError(f"Failed to retrieve note: {e}")
    
    # Tag operations
    def add_tag(self, name: str) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('INSERT INTO tags (name) VALUES (?)', (name,))
                conn.commit()
                return cursor.lastrowid
            except sqlite3.IntegrityError:  # Tag already exists
                cursor.execute('SELECT id FROM tags WHERE name = ?', (name,))
                return cursor.fetchone()[0]
    
    def add_tag_to_note(self, note_id: int, tag_name: str) -> None:
        tag_id = self.add_tag(tag_name)
        with self._get_connection() as conn:
            try:
                cursor = conn.cursor()
                cursor.execute(
                    'INSERT OR IGNORE INTO note_tags (note_id, tag_id) VALUES (?, ?)',
                    (note_id, tag_id)
                )
                conn.commit()
            except sqlite3.IntegrityError:
                pass  # Already exists
    
    def get_note_tags(self, note_id: int) -> List[Dict]:
        with self._get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                'SELECT t.id, t.name FROM tags t JOIN note_tags nt ON t.id = nt.tag_id WHERE nt.note_id = ?',
                (note_id,)
            )
            return [dict(row) for row in cursor.fetchall()]
    
    def delete_topic(self, topic_id: int, delete_notes: bool = False) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                if delete_notes:
                    # Delete all notes in this topic
                    cursor.execute('DELETE FROM notes WHERE topic_id = ?', (topic_id,))
                else:
                    # Move notes to root (set topic_id to NULL)
                    cursor.execute('UPDATE notes SET topic_id = NULL WHERE topic_id = ?', (topic_id,))
                
                # Delete the topic and its subtopics (cascading delete)
                cursor.execute('DELETE FROM topics WHERE id = ?', (topic_id,))
                conn.commit()
                return cursor.rowcount > 0
            except sqlite3.Error as e:
                logger.error(f"Error deleting topic {topic_id}: {e}")
                raise DatabaseError(f"Failed to delete topic: {e}")
                
    def move_notes_to_root(self, topic_id: int) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('UPDATE notes SET topic_id = NULL WHERE topic_id = ?', (topic_id,))
                conn.commit()
                return cursor.rowcount > 0
            except sqlite3.Error as e:
                logger.error(f"Error moving notes from topic {topic_id} to root: {e}")
                raise DatabaseError(f"Failed to move notes to root: {e}")
                
    def delete_note(self, note_id: int) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('DELETE FROM notes WHERE id = ?', (note_id,))
                conn.commit()
                return cursor.rowcount > 0
            except sqlite3.Error as e:
                logger.error(f"Error deleting note {note_id}: {e}")
                raise DatabaseError(f"Failed to delete note: {e}")
                
    def get_notes_count_in_topic(self, topic_id: int) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('SELECT COUNT(*) FROM notes WHERE topic_id = ?', (topic_id,))
                return cursor.fetchone()[0] or 0
            except sqlite3.Error as e:
                logger.error(f"Error getting notes count for topic {topic_id}: {e}")
                raise DatabaseError(f"Failed to get notes count: {e}")
    
    def search_notes(self, query: str, tag: Optional[str] = None) -> List[Dict[str, Any]]:
        if not query.strip() and not tag:
            return []
            
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                
                query_parts = []
                params = []
                
                # Base query
                sql = '''
                    SELECT DISTINCT n.id, n.title, t.name as topic_name, n.updated_at,
                           GROUP_CONCAT(DISTINCT tag.name, ', ') as tags
                    FROM notes n
                    LEFT JOIN topics t ON n.topic_id = t.id
                    LEFT JOIN note_tags nt ON n.id = nt.note_id
                    LEFT JOIN tags tag ON nt.tag_id = tag.id
                '''
                
                # Add search conditions
                if query.strip():
                    search_term = f'%{query}%'
                    query_parts.append(''' 
                        (n.title LIKE ? OR n.id IN (
                            SELECT DISTINCT note_id FROM blocks 
                            WHERE content LIKE ?
                        ))
                    ''')
                    params.extend([search_term, search_term])
                
                # Add tag filter
                if tag:
                    query_parts.append('tag.name = ?')
                    params.append(tag.lower())
                
                # Combine conditions
                if query_parts:
                    sql += ' WHERE ' + ' AND '.join(query_parts)
                
                # Group and order
                sql += ' GROUP BY n.id ORDER BY n.updated_at DESC'
                
                cursor.execute(sql, params)
                
                return [
                    {
                        'id': row[0],
                        'title': row[1],
                        'topic': row[2],
                        'updated_at': row[3],
                        'tags': row[4].split(', ') if row[4] else []
                    }
                    for row in cursor.fetchall()
                ]
                
        except sqlite3.Error as e:
            logger.error(f"Error searching notes: {e}")
            raise DatabaseError(f"Search failed: {e}")
    
    def get_all_tags(self) -> List[Dict[str, Any]]:
        """Get all tags with their usage count"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(''' 
                    SELECT t.name, COUNT(nt.note_id) as count
                    FROM tags t
                    LEFT JOIN note_tags nt ON t.id = nt.tag_id
                    GROUP BY t.id
                    ORDER BY count DESC, t.name
                ''')
                return [{'name': row[0], 'count': row[1]} for row in cursor.fetchall()]
        except sqlite3.Error as e:
            logger.error(f"Error getting tags: {e}")
            raise DatabaseError(f"Failed to retrieve tags: {e}")
    
    def get_notes_by_tag(self, tag_name: str) -> List[Dict[str, Any]]:
        """Get all notes with a specific tag"""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(''' 
                    SELECT n.id, n.title, n.updated_at, t.name as topic_name
                    FROM notes n
                    JOIN note_tags nt ON n.id = nt.note_id
                    JOIN tags t ON n.topic_id = t.id
                    JOIN tags tag ON nt.tag_id = tag.id
                    WHERE tag.name = ?
                    ORDER BY n.updated_at DESC
                ''', (tag_name.lower(),))
                
                return [
                    {
                        'id': row[0],
                        'title': row[1],
                        'updated_at': row[2],
                        'topic': row[3]
                    }
                    for row in cursor.fetchall()
                ]
        except sqlite3.Error as e:
            logger.error(f"Error getting notes by tag '{tag_name}': {e}")
            raise DatabaseError(f"Failed to retrieve notes by tag: {e}")
