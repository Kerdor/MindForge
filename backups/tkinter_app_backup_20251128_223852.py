import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from typing import Dict, List, Optional, Any, Callable, Tuple, Union, Set, TypeVar
from enum import Enum, auto
import uuid
import json
import os
import logging
from datetime import datetime
from database import DatabaseManager, DatabaseError
from models import Block, BlockItem, BlockType, Note, Topic, ValidationError
from dialogs import ConfirmDeletionDialog, TopicPropertiesDialog, RenameDialog

# Configure logging
logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename='app_errors.log'
)
logger = logging.getLogger(__name__)


class BlockRenderer:
    def __init__(self, on_block_change: Optional[Callable] = None):
        self.on_block_change = on_block_change
        self.style = ttk.Style()
        self._setup_styles()
    
    def _setup_styles(self):
        self.style.configure('Block.TFrame', padding=5)
        self.style.configure('Block.TLabelframe', padding=5, relief='groove', borderwidth=1)
        self.style.configure('Heading1.TLabel', font=('Segoe UI', 20, 'bold'))
        self.style.configure('Heading2.TLabel', font=('Segoe UI', 16, 'bold'))
        self.style.configure('Heading3.TLabel', font=('Segoe UI', 14, 'bold'))
    
    def render_text_block(self, parent, block: 'Block') -> tk.Widget:
        frame = ttk.Frame(parent, style='Block.TFrame')
        text = tk.Text(frame, height=3, wrap=tk.WORD, padx=5, pady=5, font=('Segoe UI', 11))
        text.insert("1.0", block.content)
        text.bind('<KeyRelease>', lambda e, b=block: self._on_text_change(e, b))
        text.pack(fill=tk.X, expand=True)
        return frame

    def render_heading(self, parent, block: 'Block') -> tk.Widget:
        frame = ttk.Frame(parent, style='Block.TFrame')
        style = f'Heading{block.level}.TLabel'
        label = ttk.Label(frame, text=block.content, style=style)
        label.pack(fill=tk.X, expand=True)
        return frame

    def render_bullet_list(self, parent, block: 'Block') -> tk.Widget:
        frame = ttk.Frame(parent, style='Block.TFrame')
        for item in block.items:
            item_frame = ttk.Frame(frame)
            ttk.Label(item_frame, text="•").pack(side=tk.LEFT, padx=(0, 5))
            ttk.Label(item_frame, text=item.content).pack(side=tk.LEFT, fill=tk.X, expand=True)
            item_frame.pack(fill=tk.X, pady=2)
        return frame
        
    def render_checklist(self, parent, block: 'Block') -> tk.Widget:
        frame = ttk.Frame(parent, style='Block.TFrame')
        for item in block.items:
            item_frame = ttk.Frame(frame)
            var = tk.BooleanVar(value=item.checked)
            cb = ttk.Checkbutton(
                item_frame, 
                text=item.content,
                variable=var,
                command=lambda i=item, v=var: self._on_checkbox_change(i, v)
            )
            cb.pack(side=tk.LEFT, fill=tk.X, expand=True)
            item_frame.pack(fill=tk.X, pady=2)
        return frame
        
    def render_divider(self, parent, block: 'Block') -> tk.Widget:
        frame = ttk.Frame(parent, height=2, style='Block.TFrame')
        ttk.Separator(frame, orient='horizontal').pack(fill=tk.X, pady=10)
        return frame
        
    def _on_text_change(self, event, block: 'Block'):
        widget = event.widget
        block.content = widget.get("1.0", tk.END).strip()
        if self.on_block_change:
            self.on_block_change(block)
            
    def _on_checkbox_change(self, item: BlockItem, var: tk.BooleanVar):
        item.checked = var.get()
        if self.on_block_change:
            self.on_block_change(None)  # Pass None or the parent block if available

    def render_numbered_list(self, parent, block: Block) -> tk.Widget:
        frame = ttk.Frame(parent, style='Block.TFrame')
        for i, item in enumerate(block.items, 1):
            item_frame = ttk.Frame(frame)
            ttk.Label(item_frame, text=f"{i}.").pack(side=tk.LEFT, padx=(0, 5))
            ttk.Label(item_frame, text=item.content).pack(side=tk.LEFT, fill=tk.X, expand=True)
            item_frame.pack(fill=tk.X, pady=2)
        return frame

    def render_block(self, parent, block: Block) -> Optional[tk.Widget]:
        if block.type == BlockType.TEXT:
            return self.render_text_block(parent, block)
        elif block.type == BlockType.HEADING:
            return self.render_heading(parent, block)
        elif block.type == BlockType.BULLET_LIST:
            return self.render_bullet_list(parent, block)
        elif block.type == BlockType.NUMBERED_LIST:
            return self.render_numbered_list(parent, block)
        elif block.type == BlockType.CHECKLIST:
            return self.render_checklist(parent, block)
        elif block.type == BlockType.DIVIDER:
            return self.render_divider(parent, block)
        return None


class NoteTakingApp:
    def __init__(self, root):
        """Initialize the NoteTakingApp with the given root window."""
        self.root = root
        self.db = DatabaseManager()
        
        # Initialize notes list
        self.notes = []
        self.current_topic_id = None
        self.current_note_id = None
        
        # Set up the UI
        self.setup_ui()
        
        # Bind window close event
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Load initial data and render the tree
        self.load_initial_data()
        self.load_tree_data()  # Ensure tree is rendered on startup
        
    def create_root_topic(self):
        """Create a new root-level topic."""
        name = simpledialog.askstring("Новая тема", "Введите название темы:")
        if name and name.strip():
            try:
                topic_id = self.db.create_topic(name.strip())
                self.load_topics()
                self.status_var.set(f"Создана новая тема: {name}")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось создать тему: {str(e)}")
                logger.error(f"Error creating topic: {e}")

    def create_subtopic(self, parent_id):
        """Create a new subtopic under the specified parent."""
        name = simpledialog.askstring("Новая подтема", "Введите название подтемы:")
        if name and name.strip():
            try:
                topic_id = self.db.create_topic(name.strip(), parent_id)
                self.load_topics()
                self.status_var.set(f"Создана новая подтема: {name}")
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось создать подтему: {str(e)}")
                logger.error(f"Error creating subtopic: {e}")

    def show_topic_context_menu(self, event):
        """Show context menu for topics."""
        item = self.tree.identify('item', event.x, event.y)
        if item:
            self.tree.selection_set(item)
            menu = tk.Menu(self.root, tearoff=0)
            menu.add_command(label="Новая подтема", 
                           command=lambda: self.create_subtopic(self.tree.item(item)['values'][0]))
            menu.add_command(label="Переименовать", 
                           command=lambda: self.rename_topic(item))
            menu.add_separator()
            menu.add_command(label="Удалить", 
                           command=lambda: self.delete_topic(item))
            menu.post(event.x_root, event.y_root)
        else:
            # Show root menu if right-clicked on empty space
            self.topic_menu.post(event.x_root, event.y_root)

    def create_note(self, topic_id=None):
        """Create a new note in the current or specified topic."""
        try:
            # If topic_id is not provided, try to get it from selection
            if topic_id is None:
                selection = self.tree.selection()
                if selection:
                    item_id = selection[0]
                    if item_id.startswith('topic_'):
                        # Extract topic ID from the item ID
                        topic_id = int(item_id.split('_')[1])
            
            # Create default note title with current date
            date_str = datetime.now().strftime("%Y-%m-%d")
            default_title = f"Новая заметка {date_str}"
            
            try:
                # Create the note
                note_id = self.db.create_note(default_title, topic_id)
                
                # Refresh the tree to show the new note
                self.load_tree_data()
                
                # Select the new note in the tree
                note_item_id = f'note_{note_id}'
                if self.tree.exists(note_item_id):
                    # Expand the parent topic if it exists
                    if topic_id is not None:
                        topic_item_id = f'topic_{topic_id}'
                        if self.tree.exists(topic_item_id):
                            self.tree.item(topic_item_id, open=True)
                    
                    self.tree.selection_set(note_item_id)
                    self.tree.see(note_item_id)
                    self.load_note(note_id)
                
                # Set focus to title entry
                self.title_entry.focus_set()
                self.title_entry.select_range(0, tk.END)
                
                # Update status
                self.status_var.set(f"Создана новая заметка: {default_title}")
                
                return note_id
                
            except Exception as db_error:
                error_msg = str(db_error) or "Неизвестная ошибка базы данных"
                logger.error(f"Database error creating note: {error_msg}", exc_info=True)
                messagebox.showerror("Ошибка базы данных", f"Не удалось создать заметку: {error_msg}")
                return None
            
        except Exception as e:
            error_msg = str(e) or "Неизвестная ошибка"
            logger.error(f"Error in create_note: {error_msg}", exc_info=True)
            messagebox.showerror("Ошибка", f"Не удалось создать заметку: {error_msg}")
            return None

    def load_topics(self):
        """Load topics into the treeview."""
        try:
            # Clear the tree
            for item in self.tree.get_children():
                self.tree.delete(item)
            
            # Add root node
            root_id = self.tree.insert("", "end", text="Темы", values=(-1,), open=True)
            
            # Get topics from database
            topics = self.db.get_topics()
            
            # Create a dictionary to store topic nodes
            topic_nodes = {-1: root_id}  # -1 is the ID for the root
            
            # First pass: create all topic nodes
            for topic in topics:
                parent_id = topic['parent_id'] if topic['parent_id'] is not None else -1
                node_id = self.tree.insert(
                    topic_nodes.get(parent_id, ""), 
                    "end", 
                    text=topic['name'], 
                    values=(topic['id'],)
                )
                topic_nodes[topic['id']] = node_id
            
            # Expand all nodes
            for node in self.tree.get_children():
                self.tree.item(node, open=True)
                
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить темы: {str(e)}")
            logger.error(f"Error loading topics: {e}")

    def load_notes(self, topic_id=None):
        """Load notes for the selected topic."""
        try:
            self.current_topic_id = topic_id
            # The tree view is already updated by load_tree_data()
        except Exception as e:
            error_msg = str(e) or "Неизвестная ошибка"
            logger.error(f"Error loading notes: {error_msg}")
            messagebox.showerror("Ошибка", f"Не удалось загрузить заметки: {error_msg}")
            logger.error(f"Error loading notes: {e}")

    def on_topic_selected(self, event):
        """Handle topic selection change."""
        selection = self.tree.selection()
        if selection:
            topic_id = self.tree.item(selection[0])['values'][0]
            if topic_id != -1:  # Not the root "Themes" node
                self.current_topic_id = topic_id
                self.load_notes(topic_id)
            else:
                self.current_topic_id = None
                self.load_notes()  # Load all notes
        else:
            self.current_topic_id = None
            self.load_notes()  # Load all notes

    def load_initial_data(self):
        """Load initial data when the application starts."""
        try:
            # First, ensure the database is properly initialized
            self._ensure_database_initialized()
            
            # Ensure we have the root topic and default subtopics
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                
                # Check if root topic exists
                cursor.execute("SELECT id FROM topics WHERE name = 'Темы'")
                root_topic = cursor.fetchone()
                
                if not root_topic:
                    # Create root topic
                    cursor.execute(
                        'INSERT INTO topics (name, parent_id) VALUES (?, ?)',
                        ('Темы', None)
                    )
                    root_topic_id = cursor.lastrowid
                    
                    # Create default subtopics
                    default_subtopics = ['Аниме', 'Фильмы', 'Работа', 'Личное']
                    for subtopic in default_subtopics:
                        cursor.execute(
                            'INSERT INTO topics (name, parent_id) VALUES (?, ?)',
                            (subtopic, root_topic_id)
                        )
                    
                    conn.commit()
                
                # Check if we need to create a welcome note
                cursor.execute("SELECT COUNT(*) FROM notes")
                if cursor.fetchone()[0] == 0:  # No notes exist
                    # Get the first topic ID
                    cursor.execute("SELECT id FROM topics WHERE name = 'Личное'")
                    topic_id = cursor.fetchone()[0]
                    
                    welcome_content = """# Добро пожаловать в MindForge!
                    
Это ваша первая заметка. Вы можете:
- Создавать новые заметки
- Организовывать их по темам
- Форматировать текст
- И многое другое!

Начните с создания новой темы или добавления заметки."""
                    
                    # Create welcome note
                    cursor.execute(
                        'INSERT INTO notes (title, topic_id) VALUES (?, ?)',
                        ('Добро пожаловать', topic_id)
                    )
                    note_id = cursor.lastrowid
                    
                    # Save the note content
                    note = Note(
                        id=note_id,
                        title="Добро пожаловать",
                        topic_id=topic_id,
                        blocks=[
                            Block(
                                type=BlockType.TEXT,
                                content=welcome_content.strip()
                            )
                        ]
                    )
                    
                    # Save the note with the block
                    self.db.save_note(note)
                    conn.commit()
        
        except Exception as e:
            logger.error(f"Error loading initial data: {e}", exc_info=True)
            messagebox.showerror("Ошибка", f"Не удалось загрузить начальные данные: {str(e) or 'Неизвестная ошиб'}")
        finally:
            # Ensure the tree is properly refreshed
            if hasattr(self, 'tree'):
                self.load_tree_data()
    
    def _ensure_database_initialized(self):
        """Ensure the database is properly initialized with required tables."""
        try:
            # This will raise an exception if the database is not accessible
            self.db.get_topics()
        except Exception as e:
            logger.error(f"Database initialization error: {e}")
            # Try to reinitialize the database
            self.db._init_db()
    
    def _create_icons(self):
        """Create and store icons for the toolbar buttons."""
        try:
            # Modern Fluent UI style icons
            self.icons = {
                'create': '➕',      # Main create button
                'create_dropdown': '▼',  # Dropdown arrow
                'note': '�',       # New note
                'topic': '�',      # New topic
                'tag': '🏷️',       # New tag
                'edit': '✏️',      # Edit/rename
                'delete': '🗑️',    # Delete
                'refresh': '🔄',   # Refresh
            }
        except Exception as e:
            logger.error(f"Error creating icons: {e}")
            # Fallback to text if icons can't be created
            self.icons = {
                'create': '+',
                'create_dropdown': '▼',
                'note': 'N+',
                'topic': 'T+',
                'tag': '#',
                'edit': '✏️',
                'delete': 'X',
                'refresh': '⟳'
            }
    
    def setup_ui(self):
        """Set up the user interface."""
        self.root.title("MindForge")
        self.root.geometry("1200x800")
        
        # Create icons
        self._create_icons()
        
        # Configure styles
        self.style = ttk.Style()
        self.style.configure('Treeview', rowheight=25)
        self.style.configure('Treeview.Heading', font=('Segoe UI', 10, 'bold'))
        self.style.configure('Toolbutton', padding=3)
        
        # Main container
        self.main_container = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.main_container.pack(fill=tk.BOTH, expand=True)
        
        # Left sidebar
        self.left_sidebar = ttk.Frame(self.main_container, width=250, padding=5)
        self.main_container.add(self.left_sidebar, weight=0)
        
        # Main tree container
        self.tree_container = ttk.Frame(self.left_sidebar, padding=5)
        self.tree_container.pack(fill=tk.BOTH, expand=True)
        
        # Main toolbar with modern design
        self.tree_toolbar = ttk.Frame(self.tree_container, padding=(0, 2, 0, 2))
        self.tree_toolbar.pack(fill=tk.X, pady=(0, 5))
        
        # Right-aligned buttons
        right_buttons_frame = ttk.Frame(self.tree_toolbar)
        right_buttons_frame.pack(side=tk.RIGHT)
        
        # Create button with just the + icon (moved next to edit button)
        self.create_btn = ttk.Button(
            right_buttons_frame,
            text=self.icons['create'],
            command=self.show_create_menu,
            style='Toolbutton',
            width=3  # Increased from 2 to 3 to prevent cutoff
        )
        self.create_btn.pack(side=tk.LEFT, padx=(0, 2))  # Added right padding
        
        # Rename button
        self.rename_btn = ttk.Button(
            right_buttons_frame,
            text=self.icons['edit'],
            command=self.rename_selected_item,
            style='Toolbutton',
            width=3
        )
        self.rename_btn.pack(side=tk.LEFT, padx=1)
        
        # Create menu (initially hidden)
        self.create_menu = tk.Menu(self.root, tearoff=0)
        self.create_menu.add_command(
            label=f"📄 Новая заметка",
            command=self.create_note_under_selected,
            accelerator="Alt+N"
        )
        self.create_menu.add_command(
            label=f"📁 Новая тема",
            command=self.create_topic_under_selected,
            accelerator="Alt+T"
        )
        self.rename_btn.pack(side=tk.LEFT, padx=1)
        
        # Delete button
        self.delete_btn = ttk.Button(
            right_buttons_frame,
            text=self.icons['delete'],
            command=self.delete_selected_item,
            style='Toolbutton',
            width=3
        )
        self.delete_btn.pack(side=tk.LEFT, padx=1)
        
        # Separator
        ttk.Separator(right_buttons_frame, orient='vertical').pack(side=tk.LEFT, padx=3, fill='y')
        
        # Toggle expand/collapse button
        self.toggle_expand_btn = ttk.Button(
            right_buttons_frame,
            text='▼',  # Default to collapse (down arrow)
            command=self.toggle_expand_all,
            style='Toolbutton',
            width=2
        )
        self.toggle_expand_btn.pack(side=tk.LEFT, padx=1)
        self.all_expanded = False  # Track the current state
        
        # Refresh button
        self.refresh_btn = ttk.Button(
            right_buttons_frame,
            text=self.icons['refresh'],
            command=self.load_tree_data,
            style='Toolbutton',
            width=3
        )
        self.refresh_btn.pack(side=tk.LEFT, padx=1)
        
        # Bind keyboard shortcuts
        self.root.bind_all('<Alt-n>', lambda e: self.create_note_under_selected())
        self.root.bind_all('<Alt-N>', lambda e: self.create_note_under_selected())
        self.root.bind_all('<Alt-t>', lambda e: self.create_topic_under_selected())
        self.root.bind_all('<Alt-T>', lambda e: self.create_topic_under_selected())
        self.root.bind_all('<Alt-g>', lambda e: self.show_create_tag_dialog())
        self.root.bind_all('<Alt-G>', lambda e: self.show_create_tag_dialog())
        
        # Create the treeview with a scrollbar
        tree_frame = ttk.Frame(self.tree_container)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create a scrollbar for the treeview
        tree_scroll = ttk.Scrollbar(tree_frame)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Create the treeview with tree and headings visible
        self.tree = ttk.Treeview(
            tree_frame,
            yscrollcommand=tree_scroll.set,
            selectmode='browse',
            show='tree',
            height=20,
            style='Treeview',
            padding=(2, 2, 2, 2)
        )
        self.tree.pack(fill=tk.BOTH, expand=True)
        
        # Configure the scrollbar
        tree_scroll.config(command=self.tree.yview)
        
        # Configure treeview style and appearance
        style = ttk.Style()
        style.configure('Treeview', 
                       rowheight=28, 
                       font=('Segoe UI', 10),
                       indent=20)  # Add indentation for child items
        
        # Set custom icons for folders and notes using emoji
        self.tree.tag_configure('topic', font=('Segoe UI', 10, 'bold'))
        self.tree.tag_configure('note', font=('Segoe UI', 10))
        
        # Set treeview to show tree lines and item images
        style.configure("Treeview", 
                       rowheight=28,
                       font=('Segoe UI', 10),
                       background="#ffffff",
                       fieldbackground="#ffffff",
                       foreground="#000000")
        
        # Style for treeview items on hover and selection
        style.map('Treeview', 
                 background=[('selected', '#0078d7')],
                 foreground=[('selected', '#ffffff')])
        
        # Configure item padding and indentation
        style.configure('Treeview.Item', padding=(0, 3, 0, 3))
        
        # Ensure the tree shows the expand/collapse arrows
        style.layout('Treeview', [
            ('Treeview.treearea', {'sticky': 'nswe'})  # Make sure the tree area is sticky in all directions
        ])
        
        # Bind events
        self.tree.bind('<<TreeviewSelect>>', self.on_tree_select)
        self.tree.bind('<Double-1>', self.on_tree_double_click)
        self.tree.bind('<Button-3>', self.show_tree_context_menu)
        
        # Context menu for tree items
        self.tree_menu = tk.Menu(self.root, tearoff=0)
        self.tree_menu.add_command(
            label=f"{self.icons['topic']} Новая тема",
            command=self.create_topic_under_selected,
            accelerator="Alt+T"
        )
        self.tree_menu.add_command(
            label=f"{self.icons['note']} Новая заметка",
            command=self.create_note_under_selected,
            accelerator="Alt+N"
        )
        self.tree_menu.add_separator()
        self.tree_menu.add_command(
            label=f"{self.icons['edit']} Переименовать",
            command=self.rename_selected_item
        )
        self.tree_menu.add_command(
            label=f"{self.icons['delete']} Удалить",
            command=self.delete_selected_item
        )
        self.tree_menu.add_separator()
        self.tree_menu.add_command(
            label=f"{self.icons['refresh']} Обновить",
            command=self.load_tree_data,
            accelerator="F5"
        )
        
        # Right panel for note editor
        self.right_panel = ttk.Frame(self.main_container, padding=5)
        self.main_container.add(self.right_panel, weight=1)
        
        # Note title
        self.note_title_var = tk.StringVar()
        self.title_entry = ttk.Entry(
            self.right_panel, 
            textvariable=self.note_title_var,
            font=('Segoe UI', 14, 'bold')
        )
        self.title_entry.pack(fill=tk.X, pady=(0, 10))
        self.title_entry.bind('<KeyRelease>', self.on_title_changed)
        self.title_entry.bind('<Return>', self.on_title_changed)
        
        # Note content
        self.note_content = tk.Text(
            self.right_panel, 
            wrap=tk.WORD,
            font=('Segoe UI', 11),
            padx=5,
            pady=5
        )
        self.note_content.pack(fill=tk.BOTH, expand=True)
        
        # Status bar
        self.status_var = tk.StringVar()
        self.status_bar = ttk.Label(
            self.root, 
            textvariable=self.status_var,
            relief=tk.SUNKEN,
            anchor=tk.W
        )
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Set initial status
        self.status_var.set("Готово")
    
    def toggle_expand_all(self):
        """Toggle between expanding and collapsing all topics."""
        if not hasattr(self, 'tree'):
            return
            
        # Toggle the state
        self.all_expanded = not self.all_expanded
        
        # Update button text based on the new state
        self.toggle_expand_btn.config(text='▲' if self.all_expanded else '▼')
        
        # Function to recursively set open state for all subtopics
        def set_subtree_state(parent_id, is_open):
            for child_id in self.tree.get_children(parent_id):
                if 'topic' in self.tree.item(child_id, 'tags'):
                    self.tree.item(child_id, open=is_open)
                    set_subtree_state(child_id, is_open)
        
        # Process all root-level topics
        for item in self.tree.get_children(''):
            if 'topic' in self.tree.item(item, 'tags'):
                self.tree.item(item, open=self.all_expanded)
                # Always update all children to match the parent's state
                set_subtree_state(item, self.all_expanded)
        
        # Update status bar
        action = "развернуты" if self.all_expanded else "свернуты"
        self.status_var.set(f"Все темы {action}")
        
        # Force update the tree view to ensure all changes are visible
        self.tree.update_idletasks()
    
    def collapse_all_topics(self):
        """Collapse all topics in the tree, including all subtopics."""
        if not hasattr(self, 'tree'):
            return
            
        self.all_expanded = False
        if hasattr(self, 'toggle_expand_btn'):
            self.toggle_expand_btn.config(text='▼')
        
        # Function to recursively collapse all subtopics
        def collapse_recursive(parent_id):
            for child_id in self.tree.get_children(parent_id):
                if 'topic' in self.tree.item(child_id, 'tags'):
                    # First collapse all children
                    collapse_recursive(child_id)
                    # Then collapse the current topic
                    self.tree.item(child_id, open=False)
        
        # Start with root items
        for item in self.tree.get_children(''):
            if 'topic' in self.tree.item(item, 'tags'):
                # First collapse all children
                collapse_recursive(item)
                # Then collapse the root topic
                self.tree.item(item, open=False)
        
        self.status_var.set("Все темы свернуты")
        self.tree.update_idletasks()  # Ensure the UI updates immediately
    
    def expand_all_topics(self):
        """Expand all topics in the tree."""
        if not hasattr(self, 'tree'):
            return
            
        self.all_expanded = True
        if hasattr(self, 'toggle_expand_btn'):
            self.toggle_expand_btn.config(text='▲')
            
        # Get all topic items in the tree
        for item in self.tree.get_children(''):
            # Check if the item is a topic (has 'topic' tag)
            if 'topic' in self.tree.item(item, 'tags'):
                # Open the topic
                self.tree.item(item, open=True)
        
        self.status_var.set("Все темы развернуты")
    
    def load_tree_data(self):
        """Load topics and notes into the tree with proper hierarchy and icons."""
        if not hasattr(self, 'tree'):
            return  # Tree not initialized yet
            
        # Save expanded state of topics before clearing
        expanded_topics = set()
        if hasattr(self, 'topic_map'):  # Check if we have the previous topic_map
            for topic_id, item_id in self.topic_map.items():
                if self.tree.exists(item_id) and self.tree.item(item_id, 'open'):
                    expanded_topics.add(topic_id)
        
        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        # Reset topic_map for the new tree
        self.topic_map = {}
        
        try:
            # Get or create root "Темы" topic
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM topics WHERE name = 'Темы'")
                root_topic = cursor.fetchone()
                
                if not root_topic:
                    # Create root topic if it doesn't exist
                    cursor.execute(
                        'INSERT INTO topics (name, parent_id) VALUES (?, ?)',
                        ('Темы', None)
                    )
                    root_topic_id = cursor.lastrowid
                    
                    # Create default subtopics
                    default_subtopics = ['Аниме', 'Фильмы', 'Работа', 'Личное']
                    for subtopic in default_subtopics:
                        cursor.execute(
                            'INSERT INTO topics (name, parent_id) VALUES (?, ?)',
                            (subtopic, root_topic_id)
                        )
                    conn.commit()
                    root_topic_id = root_topic_id  # Use the newly created ID
                else:
                    root_topic_id = root_topic[0]
            
            # Get all topics and organize them by parent_id
            topics = self.db.get_topics()
            topics_by_parent = {}
            topic_map = {}
            
            # First pass: organize topics by parent_id
            for topic in topics:
                parent_id = topic.get('parent_id')
                if parent_id is None:  # Root level topics
                    parent_id = root_topic_id
                
                if parent_id not in topics_by_parent:
                    topics_by_parent[parent_id] = []
                topics_by_parent[parent_id].append(topic)
            
            # Add root "Темы" topic with folder icon
            root_item_id = f"topic_{root_topic_id}"
            self.tree.insert(
                '', 'end', 
                iid=root_item_id, 
                text='📁 Темы',
                tags=('topic', 'root')
            )
            self.topic_map[root_topic_id] = root_item_id
            
            # Function to add topics recursively
            def add_topics(parent_id, parent_item_id):
                for topic in topics_by_parent.get(parent_id, []):
                    if topic['id'] == root_topic_id:  # Skip root topic itself
                        continue
                        
                    topic_id = f"topic_{topic['id']}"
                    topic_map[topic['id']] = topic_id
                    self.topic_map[topic['id']] = topic_id
                    
                    self.tree.insert(
                        parent_item_id, 'end',
                        iid=topic_id,
                        text=f"📁 {topic['name']}"
                    )
                    
                    # Recursively add subtopics
                    add_topics(topic['id'], topic_id)
            
            # Add all topics under the root
            add_topics(root_topic_id, root_item_id)
            
            # Add notes under their respective topics
            notes = self.db.get_notes()
            for note in notes:
                if not note['topic_id']:
                    continue  # Skip notes without a topic
                    
                parent_id = f"topic_{note['topic_id']}"
                if parent_id in self.tree.get_children() or note['topic_id'] in topic_map:
                    self.tree.insert(
                        parent_id, 'end',
                        iid=f"note_{note['id']}",
                        text=f"📄 {note['title']}",
                        tags=('note',)
                    )
            
            # Restore expanded state of topics
            for topic_id in expanded_topics:
                if topic_id in self.topic_map:
                    self.tree.item(self.topic_map[topic_id], open=True)
            
            # If no topics were expanded, expand the root by default
            if not expanded_topics:
                self.tree.item(root_item_id, open=True)
            
            # Force update the tree view
            self.tree.update_idletasks()
            
        except Exception as e:
            logger.error(f"Error loading topic tree: {e}", exc_info=True)
            messagebox.showerror("Ошибка", f"Не удалось загрузить список тем: {e}")
            return
    
    def on_tree_select(self, event):
        """Handle selection of an item in the tree."""
        selected = self.tree.selection()
        if not selected:
            return
            
        item_id = selected[0]
        if item_id.startswith('note_'):
            # It's a note
            note_id = int(item_id.split('_')[1])
            self.load_note(note_id)
    
    def expand_all_subtopics(self, item_id):
        """Recursively expand all subtopics of the given item."""
        if not item_id.startswith('topic_'):
            return
            
        # Get all children of the current item
        children = self.tree.get_children(item_id)
        for child_id in children:
            # If it's a topic, expand it and its children
            if child_id.startswith('topic_'):
                self.tree.item(child_id, open=True)
                self.expand_all_subtopics(child_id)
    
    def on_tree_double_click(self, event):
        """Handle double-click on a tree item."""
        region = self.tree.identify_region(event.x, event.y)
        if region != 'cell':
            return
            
        item_id = self.tree.identify_row(event.y)
        if not item_id:
            return
            
        if item_id.startswith('topic_'):
            # Toggle expand/collapse
            if self.tree.item(item_id, 'open'):
                self.tree.item(item_id, open=False)
            else:
                self.tree.item(item_id, open=True)
                # Expand all subtopics when opening a topic
                self.expand_all_subtopics(item_id)
    
    def show_tree_context_menu(self, event):
        """Show the context menu for the tree."""
        item_id = self.tree.identify_row(event.y)
        if item_id:
            self.tree.selection_set(item_id)
            self.tree_menu.post(event.x_root, event.y_root)
    
    class TopicDialog(tk.Toplevel):
        def __init__(self, parent, title=None):
            super().__init__(parent)
            self.title(title or "Новая тема")
            self.parent = parent
            self.result = None
            
            # Make window modal and set minimum size
            self.transient(parent)
            self.resizable(False, False)  # Disable resizing
            
            # Center the dialog
            self.geometry("300x120")
            self.update_idletasks()
            width = self.winfo_width()
            height = self.winfo_height()
            x = (self.winfo_screenwidth() // 2) - (width // 2)
            y = (self.winfo_screenheight() // 2) - (height // 2)
            self.geometry(f'+{x}+{y}')
            
            # Add padding around the content
            self.columnconfigure(0, weight=1)
            self.rowconfigure(0, weight=1)
            
            # Create main frame
            main_frame = ttk.Frame(self, padding=10)
            main_frame.grid(row=0, column=0, sticky='nsew')
            
            # Label
            label = ttk.Label(main_frame, text="Введите название темы:")
            label.pack(pady=(10, 5), anchor='w')
            
            # Entry field
            self.entry = ttk.Entry(main_frame, width=30)
            self.entry.pack(pady=5, fill=tk.X)
            self.entry.focus_set()
            
            # Buttons frame
            btn_frame = ttk.Frame(main_frame)
            btn_frame.pack(pady=(10, 0), anchor='e')
            
            # OK button
            ok_btn = ttk.Button(btn_frame, text="OK", command=self.on_ok, width=10)
            ok_btn.pack(side=tk.RIGHT, padx=5)
            
            # Cancel button
            cancel_btn = ttk.Button(btn_frame, text="Отмена", command=self.on_cancel, width=10)
            cancel_btn.pack(side=tk.RIGHT)
            
            # Bind Enter and Escape keys
            self.bind('<Return>', lambda e: self.on_ok())
            self.bind('<Escape>', lambda e: self.on_cancel())
            
            # Set focus to the entry field
            self.entry.focus_set()
            
            # Make the window modal
            self.grab_set()
            self.wait_window(self)
        
        def on_ok(self):
            self.result = self.entry.get().strip()
            self.destroy()
            
        def on_cancel(self):
            self.result = None
            self.destroy()
            
        def show(self):
            self.wait_window()
            return self.result
    
    def create_topic_under_selected(self):
        """Create a new topic under the selected one."""
        selected = self.tree.selection()
        parent_id = None
        
        if selected:
            item_id = selected[0]
            if item_id.startswith('topic_'):
                parent_id = int(item_id.split('_')[1])
        
        # Use custom dialog instead of simpledialog
        dialog = self.TopicDialog(self.root, "Новая тема")
        name = dialog.result
        
        if name and name.strip():
            try:
                self.db.create_topic(name.strip(), parent_id)
                self.load_tree_data()
                self.status_var.set(f"Создана новая тема: {name}")
            except Exception as e:
                error_msg = str(e) or "Неизвестная ошибка"
                logger.error(f"Error creating topic: {error_msg}")
                messagebox.showerror("Ошибка", f"Не удалось создать тему: {error_msg}")
    
    class NoteDialog(tk.Toplevel):
        def __init__(self, parent, title=None, default_title=""):
            super().__init__(parent)
            self.title(title or "Новая заметка")
            self.parent = parent
            self.result = None
            
            # Make window modal and set minimum size
            self.transient(parent)
            self.resizable(False, False)  # Disable resizing
            
            # Center the dialog
            self.geometry("400x150")
            self.update_idletasks()
            width = self.winfo_width()
            height = self.winfo_height()
            x = (self.winfo_screenwidth() // 2) - (width // 2)
            y = (self.winfo_screenheight() // 2) - (height // 2)
            self.geometry(f'+{x}+{y}')
            
            # Add padding around the content
            self.columnconfigure(0, weight=1)
            self.rowconfigure(0, weight=1)
            
            # Create main frame
            main_frame = ttk.Frame(self, padding=10)
            main_frame.grid(row=0, column=0, sticky='nsew')
            
            # Label and entry for note title
            title_label = ttk.Label(main_frame, text="Введите название заметки:")
            title_label.pack(pady=(5, 5), anchor='w')
            
            self.title_entry = ttk.Entry(main_frame, width=40)
            self.title_entry.pack(pady=5, fill=tk.X)
            self.title_entry.insert(0, default_title)
            self.title_entry.select_range(0, tk.END)
            
            # Buttons frame
            btn_frame = ttk.Frame(main_frame)
            btn_frame.pack(pady=(15, 0), anchor='e')
            
            # OK button
            ok_btn = ttk.Button(btn_frame, text="Создать", command=self.on_ok, width=10)
            ok_btn.pack(side=tk.RIGHT, padx=5)
            
            # Cancel button
            cancel_btn = ttk.Button(btn_frame, text="Отмена", command=self.on_cancel, width=10)
            cancel_btn.pack(side=tk.RIGHT)
            
            # Bind Enter and Escape keys
            self.bind('<Return>', lambda e: self.on_ok())
            self.bind('<Escape>', lambda e: self.on_cancel())
            
            # Set focus to the entry field
            self.title_entry.focus_set()
            
            # Make the window modal
            self.grab_set()
            self.wait_window(self)
        
        def on_ok(self):
            self.result = self.title_entry.get().strip()
            self.destroy()
            
        def on_cancel(self):
            self.result = None
            self.destroy()
            
        def show(self):
            self.wait_window()
            return self.result
    
    def create_note_under_selected(self):
        """Create a new note under the selected topic."""
        try:
            selected = self.tree.selection()
            topic_id = None
            
            if selected:
                item_id = selected[0]
                if item_id.startswith('topic_'):
                    topic_id = int(item_id.split('_')[1])
            
            # Create default note title with current date
            date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            default_title = f"Новая заметка {date_str}"
            
            # Show custom dialog to get note title
            dialog = self.NoteDialog(self.root, "Новая заметка", default_title)
            if dialog.result is None:  # User clicked Cancel
                return
                
            note_title = dialog.result if dialog.result.strip() else default_title
            
            # Create the note
            note_id = self.db.create_note(note_title, topic_id)
            
            if not note_id:
                raise Exception("Не удалось создать заметку")
            
            # Refresh the tree to show the new note
            self.load_tree_data()
            
            # Select and focus the new note
            note_item_id = f'note_{note_id}'
            if self.tree.exists(note_item_id):
                # Expand parent topic if it exists
                if topic_id is not None:
                    topic_item_id = f'topic_{topic_id}'
                    if self.tree.exists(topic_item_id):
                        self.tree.item(topic_item_id, open=True)
                
                self.tree.selection_set(note_item_id)
                self.tree.see(note_item_id)
                self.load_note(note_id)
            
            # Set focus to title entry
            self.title_entry.focus_set()
            self.title_entry.select_range(0, tk.END)
            
            self.status_var.set(f"Создана новая заметка: {note_title}")
            
        except Exception as e:
            error_msg = str(e) or "Неизвестная ошибка"
            logger.error(f"Error creating note: {error_msg}")
            messagebox.showerror("Ошибка", f"Не удалось создать заметку: {error_msg}")
    
    class RenameDialog(tk.Toplevel):
        def __init__(self, parent, title=None, current_name=""):
            super().__init__(parent)
            self.title(title or "Переименовать")
            self.parent = parent
            self.result = None
            
            # Make window modal and set minimum size
            self.transient(parent)
            self.resizable(False, False)
            
            # Center the dialog
            self.geometry("400x150")
            self.update_idletasks()
            width = self.winfo_width()
            height = self.winfo_height()
            x = (self.winfo_screenwidth() // 2) - (width // 2)
            y = (self.winfo_screenheight() // 2) - (height // 2)
            self.geometry(f'+{x}+{y}')
            
            # Add padding around the content
            self.columnconfigure(0, weight=1)
            self.rowconfigure(0, weight=1)
            
            # Create main frame
            main_frame = ttk.Frame(self, padding=10)
            main_frame.grid(row=0, column=0, sticky='nsew')
            
            # Label and entry for new name
            title_label = ttk.Label(main_frame, text="Введите новое название:")
            title_label.pack(pady=(5, 5), anchor='w')
            
            self.name_entry = ttk.Entry(main_frame, width=40)
            self.name_entry.pack(pady=5, fill=tk.X)
            self.name_entry.insert(0, current_name)
            self.name_entry.select_range(0, tk.END)
            
            # Buttons frame
            btn_frame = ttk.Frame(main_frame)
            btn_frame.pack(pady=(15, 0), anchor='e')
            
            # OK button
            ok_btn = ttk.Button(btn_frame, text="ОК", command=self.on_ok, width=10)
            ok_btn.pack(side=tk.RIGHT, padx=5)
            
            # Cancel button
            cancel_btn = ttk.Button(btn_frame, text="Отмена", command=self.on_cancel, width=10)
            cancel_btn.pack(side=tk.RIGHT)
            
            # Bind Enter and Escape keys
            self.bind('<Return>', lambda e: self.on_ok())
            self.bind('<Escape>', lambda e: self.on_cancel())
            
            # Set focus to the entry field
            self.name_entry.focus_set()
            
            # Make the window modal
            self.grab_set()
            self.wait_window(self)
        
        def on_ok(self):
            self.result = self.name_entry.get().strip()
            self.destroy()
            
        def on_cancel(self):
            self.result = None
            self.destroy()
            
        def show(self):
            self.wait_window()
            return self.result
    
    def rename_selected_item(self):
        """Rename the selected topic or note."""
        selected = self.tree.selection()
        if not selected:
            return
            
        item_id = selected[0]
        current_name = self.tree.item(item_id, 'text')
        
        # Show custom rename dialog
        dialog = self.RenameDialog(self.root, "Переименовать", current_name)
        new_name = dialog.result
        
        if new_name and new_name.strip() and new_name != current_name:
            try:
                if item_id.startswith('topic_'):
                    topic_id = int(item_id.split('_')[1])
                    self.db.rename_topic(topic_id, new_name.strip())
                elif item_id.startswith('note_'):
                    note_id = int(item_id.split('_')[1])
                    self.db.update_note_title(note_id, new_name.strip())
                
                self.load_tree_data()
                self.status_var.set("Элемент переименован")
            except Exception as e:
                error_msg = str(e) or "Неизвестная ошибка"
                logger.error(f"Error renaming item: {error_msg}")
                messagebox.showerror("Ошибка", f"Не удалось переименовать: {error_msg}")
    
    def delete_selected_item(self):
        """Delete the selected topic or note."""
        selected = self.tree.selection()
        if not selected:
            return
            
        item_id = selected[0]
        item_name = self.tree.item(item_id, 'text')
        
        if messagebox.askyesno("Подтверждение удаления", 
                             f"Вы уверены, что хотите удалить '{item_name}'?"):
            try:
                if item_id.startswith('topic_'):
                    topic_id = int(item_id.split('_')[1])
                    self.db.delete_topic(topic_id)
                elif item_id.startswith('note_'):
                    note_id = int(item_id.split('_')[1])
                    self.db.delete_note(note_id)
                
                self.load_tree_data()
                self.status_var.set("Элемент удалён")
                
                # Clear the editor if the deleted item was being edited
                if hasattr(self, 'current_note_id') and \
                   ((item_id.startswith('note_') and int(item_id.split('_')[1]) == self.current_note_id) or
                    (item_id.startswith('topic_') and hasattr(self, 'current_topic_id') and 
                     int(item_id.split('_')[1]) == self.current_topic_id)):
                    self.note_content.delete('1.0', tk.END)
                    self.note_title_var.set("")
                    self.current_note_id = None
                    if hasattr(self, 'current_topic_id'):
                        delattr(self, 'current_topic_id')
                        
            except Exception as e:
                error_msg = str(e) or "Неизвестная ошибка"
                logger.error(f"Error deleting item: {error_msg}")
                messagebox.showerror("Ошибка", f"Не удалось удалить: {error_msg}")
    
    def on_title_changed(self, event=None):
        """Handle changes to the note title."""
        if not hasattr(self, 'current_note_id') or not self.current_note_id:
            return
            
        try:
            # Get the new title from the entry widget
            new_title = self.note_title_var.get().strip()
            
            # Don't save empty titles
            if not new_title:
                return
                
            # Update the note title in the database
            success = self.db.update_note_title(self.current_note_id, new_title)
            
            if success:
                # Update the tree to reflect the title change
                note_item_id = f"note_{self.current_note_id}"
                if self.tree.exists(note_item_id):
                    self.tree.item(note_item_id, text=new_title)
                
                # Update the status bar
                self.status_var.set(f"Заметка сохранена: {new_title}")
                logger.info(f"Note {self.current_note_id} title updated to: {new_title}")
            else:
                logger.error(f"Failed to update note {self.current_note_id} title")
                self.status_var.set("Ошибка при сохранении заголовка")
                
        except Exception as e:
            error_msg = str(e) or "Неизвестная ошибка"
            logger.error(f"Error saving note title: {error_msg}", exc_info=True)
            self.status_var.set("Ошибка при сохранении заголовка")
            messagebox.showerror("Ошибка", f"Не удалось обновить заголовок заметки: {error_msg}")
                
    def load_note(self, note_id):
        """Load a note's content into the editor."""
        try:
            # Get the note from the database
            note = self.db.get_note(note_id)
            if note:
                # Update the title entry
                self.note_title_var.set(note.title)
                
                # Clear the content area
                self.note_content.delete('1.0', tk.END)
                
                # If the note has content, insert it into the text widget
                if hasattr(note, 'content') and note.content:
                    self.note_content.insert('1.0', note.content)
                
                # Update status
                self.status_var.set(f"Заметка загружена: {note.title}")
                
        except Exception as e:
            error_msg = str(e) or "Неизвестная ошибка"
            logger.error(f"Error loading note {note_id}: {error_msg}", exc_info=True)
            messagebox.showerror("Ошибка", f"Не удалось загрузить заметку: {error_msg}")
    
    def on_note_selected(self, event=None):
        """Handle note selection from the tree."""
        selected = self.tree.selection()
        if not selected:
            return
            
        item_id = selected[0]
        if item_id.startswith('note_'):
            note_id = int(item_id.split('_')[1])
            self.current_note_id = note_id
            self.load_note(note_id)
    
    def rename_selected_topic(self):
        """Handle rename button click for the selected topic."""
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Информация", "Пожалуйста, выберите тему для переименования")
            return
        self.rename_topic(selection[0])
        
    def delete_selected_topic(self):
        """Handle delete button click for the selected topic."""
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Информация", "Пожалуйста, выберите тему для удаления")
            return
        self.delete_topic(selection[0])
    
    def show_create_menu(self, event=None):
        """Show the create menu below the create button."""
        try:
            # Get the coordinates of the create button
            x = self.create_btn.winfo_rootx()
            y = self.create_btn.winfo_rooty() + self.create_btn.winfo_height()
            
            # Post the menu at the calculated position
            self.create_menu.tk_popup(x, y)
            
            # Keep the menu open until an item is selected or it loses focus
            self.create_menu.grab_release()
            
        except Exception as e:
            logger.error(f"Error showing create menu: {e}")
            messagebox.showerror("Ошибка", "Не удалось отобразить меню создания")
    
    def show_create_tag_dialog(self):
        """Show dialog to create a new tag."""
        try:
            tag_name = simpledialog.askstring("Новый тег", "Введите название тега:", parent=self.root)
            if tag_name and tag_name.strip():
                # Here you would typically save the tag to your database
                # For now, we'll just show a success message
                messagebox.showinfo("Успех", f"Тег '{tag_name}' создан")
                
        except Exception as e:
            logger.error(f"Error creating tag: {e}")
            messagebox.showerror("Ошибка", f"Не удалось создать тег: {str(e) or 'Неизвестная ошибка'}")
    
    def on_closing(self):
        """Handle application shutdown."""
        try:
            # Save any unsaved changes
            if hasattr(self, 'current_note_id') and self.current_note_id:
                try:
                    content = self.note_content.get('1.0', tk.END).strip()
                    self.db.update_note_content(self.current_note_id, content)
                except Exception as e:
                    logger.error(f"Error saving note before exit: {e}")
            
            # Close the database connection
            if hasattr(self, 'db'):
                self.db.close()
                
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
            
        finally:
            # Always destroy the root window
            self.root.destroy()


def main():
    """Main entry point for the application."""
    try:
        # Create the root window
        root = tk.Tk()
        
        # Create and run the application
        app = NoteTakingApp(root)
        
        # Start the main event loop
        root.mainloop()
        
    except Exception as e:
        logger.critical(f"Fatal error: {e}", exc_info=True)
        messagebox.showerror("Критическая ошибка", 
                           f"Произошла критическая ошибка: {str(e)}\n\n"
                           "Проверьте файл app_errors.log для получения дополнительной информации.")


if __name__ == "__main__":
    main()
