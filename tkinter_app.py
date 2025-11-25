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
        self.root = root
        self.root.title("MindForge")
        self.root.geometry("1200x700")
        self.tooltips = {}  # Store tooltip windows
        
    def _create_tooltip(self, widget, text):
        """Create a tooltip for a given widget.
        
        Args:
            widget: The widget this tooltip is for
            text: The text to show in the tooltip
        """
        tooltip = tk.Toplevel(widget)
        tooltip.withdraw()  # Hide initially
        tooltip.overrideredirect(True)  # Remove window decorations
        
        # Create and pack the label
        label = ttk.Label(
            tooltip,
            text=text,
            background='#ffffe0',
            relief='solid',
            borderwidth=1,
            padding=(4, 2),
            font=('Segoe UI', 9)
        )
        label.pack()
        
        def show_tooltip(event):
            # Position the tooltip to the right of the widget
            x = widget.winfo_rootx() + widget.winfo_width() + 5
            y = widget.winfo_rooty()
            tooltip.geometry(f'+{x}+{y}')
            tooltip.deiconify()
        
        def hide_tooltip(event):
            tooltip.withdraw()
        
        # Bind events
        widget.bind('<Enter>', show_tooltip)
        widget.bind('<Leave>', hide_tooltip)
        widget.bind('<ButtonPress>', hide_tooltip)
        
    def __init__(self, root):
        self.root = root
        self.root.title("MindForge")
        self.root.geometry("1200x700")
        self.tooltips = {}  # Store tooltip windows
        
        try:
            # Initialize database
            self.db = DatabaseManager()
            
            # Current state
            self.current_note_id = None
            self.blocks = []
            self.focused_block_id = None
            self.auto_save_id = None
            self.current_search_query = ""
            self.current_tag_filter = None
            self.current_topic_id = None
            
            # Initialize block renderer with callback
            self.block_renderer = BlockRenderer(on_block_change=self.on_block_updated)
            
            self.setup_ui()
            self.load_topics()
            
            # Load last opened note or create a new one
            self.create_new_note()
            
            # Setup auto-save
            self.setup_auto_save()
            
            # Bind keyboard shortcuts
            self.root.bind_all("<Control-n>", lambda e: self.create_new_note())
            self.root.bind_all("<Control-s>", lambda e: self.save_current_note())
            self.root.bind_all("<Control-f>", lambda e: self.show_search_dialog())
            self.root.bind_all("<Control-t>", lambda e: self.show_tags_dialog())
            self.root.bind_all("<Control-w>", lambda e: self.close_current_note())
            self.root.bind_all("<Delete>", lambda e: self.delete_selected_note())
            self.root.bind_all("<Control-d>", lambda e: self.delete_selected_note())
            
            # Track focus changes
            self.root.bind("<Button-1>", self._on_click)
            
            # Close database connection on exit
            self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
            
        except Exception as e:
            logger.critical(f"Failed to initialize application: {str(e)}", exc_info=True)
            messagebox.showerror("Initialization Error", 
                              f"Failed to initialize the application: {str(e)}\n\n"
                              "Check app_errors.log for more details.")
            self.root.destroy()
        
    def update_status_bar(self, message: str) -> None:
        """Update the status bar with the given message.
        
        Args:
            message: The message to display in the status bar
        """
        if hasattr(self, 'status_var'):
            self.status_var.set(message)
        else:
            # If status_var doesn't exist yet, create it
            self.status_var = tk.StringVar()
            self.status_bar = ttk.Label(
                self.root,
                textvariable=self.status_var,
                relief=tk.SUNKEN,
                anchor=tk.W,
                padding=(5, 2)
            )
            self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
            self.status_var.set(message)
            
    def _on_click(self, event):
        # Update focused block based on click position
        widget = event.widget
        if hasattr(widget, 'block_id'):
            self.focused_block_id = widget.block_id
            
    def on_notes_list_click(self, event):
        """Handle clicks on the notes list, specifically for the delete button"""
        # Get the item and column that was clicked
        region = self.notes_list.identify_region(event.x, event.y)
        if region == 'cell':
            item = self.notes_list.identify_row(event.y)
            column = self.notes_list.identify_column(event.x)
            
            # If delete button was clicked (3rd column)
            if column == '#3' and item:  # Check if item exists
                # Get the note ID from the item's tags
                item_tags = self.notes_list.item(item, 'tags')
                if item_tags and len(item_tags) > 0:
                    try:
                        note_id = int(item_tags[0])
                        # Find the note title
                        note_title = self.notes_list.item(item, 'values')[0].split(' [')[0]  # Remove topic from title
                        # Show confirmation and delete
                        self.delete_note_with_confirmation(note_id, note_title)
                        return 'break'  # Prevent further event processing
                    except (ValueError, IndexError) as e:
                        logger.error(f"Error processing delete click: {e}")
        
        # If not a delete button click, let the default behavior happen
        return None
            
    def show_controls(self, event):
        """Show controls for the clicked block"""
        widget = event.widget
        if hasattr(widget, 'block_id'):
            self.focused_block_id = widget.block_id
            # Position controls near the clicked widget
            x = widget.winfo_rootx()
            y = widget.winfo_rooty()
            self.controls_frame.place(x=x, y=y-30, anchor='nw')
            self.controls_frame.lift()
            return 'break'  # Prevent event propagation
            
    def show_context_menu(self, event):
        """Show context menu for the right-clicked block"""
        widget = event.widget
        if hasattr(widget, 'block_id'):
            self.focused_block_id = widget.block_id
            
            # Create menu
            menu = tk.Menu(self.root, tearoff=0)
            menu.add_command(label="Удалить блок", command=self.delete_selected_block)
            menu.add_separator()
            
            # Add block type conversion options
            menu.add_command(label="В текст", command=lambda: self.convert_block_type(BlockType.TEXT))
            menu.add_command(label="В заголовок", command=lambda: self.convert_block_type(BlockType.HEADING))
            menu.add_command(label="В маркированный список", command=lambda: self.convert_block_type(BlockType.BULLET_LIST))
            menu.add_command(label="В нумерованный список", command=lambda: self.convert_block_type(BlockType.NUMBERED_LIST))
            menu.add_command(label="В чеклист", command=lambda: self.convert_block_type(BlockType.CHECKLIST))
            
            # Show the menu at cursor position
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                # Make sure to release the grab (Tk 8.0.21+)
                menu.grab_release()
                
    def convert_block_type(self, new_type: BlockType):
        """Convert the currently focused block to a different type"""
        if not self.focused_block_id:
            return
            
        for block in self.blocks:
            if block.id == self.focused_block_id:
                block.type = new_type
                # Clear items if converting from a list type to non-list type
                if new_type in [BlockType.TEXT, BlockType.HEADING, BlockType.DIVIDER]:
                    block.items = []
                elif not block.items:  # If converting to a list type and no items exist
                    block.items = [BlockItem(id=str(uuid.uuid4()), content="Новый элемент")]
                self.render_blocks()
                break
            
    def delete_selected_block(self, event=None):
        """Delete the currently focused block"""
        if self.focused_block_id:
            self.delete_block(self.focused_block_id)
            self.focused_block_id = None
        
    def on_block_updated(self, block: Optional[Block]):
        # This will be called when a block's content changes
        if block:
            print(f"Block {block.id} updated")
            # Here you would typically save the changes to your data store
    
    def setup_ui(self):
        # Configure styles
        self.style = ttk.Style()
        self.style.configure('Sidebar.TFrame', background='#f0f0f0')
        self.style.configure('Topic.Treeview', background='#f8f9fa', fieldbackground='#f8f9fa', foreground='#212529')
        self.style.configure('NotesList.Treeview', background='white', fieldbackground='white', foreground='#212529')
        
        # Create status bar at the bottom
        self.status_var = tk.StringVar()
        self.status_bar = ttk.Label(
            self.root,
            textvariable=self.status_var,
            relief=tk.SUNKEN,
            anchor=tk.W,
            padding=(5, 2)
        )
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.status_var.set("Готово")
        
        # Main container
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Left sidebar - Topics and Notes
        left_frame = ttk.Frame(main_frame, width=250)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        
        # Topics tree with context menu
        topic_frame = ttk.LabelFrame(left_frame, text="Темы")
        topic_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        
        # Add button for new topic
        topic_header = ttk.Frame(topic_frame)
        topic_header.pack(fill=tk.X, padx=2, pady=2)
        
        ttk.Button(
            topic_header, 
            text="+", 
            width=3,
            command=self.add_topic,
            style="Toolbutton"
        ).pack(side=tk.LEFT, padx=(0, 5))
        
        # Topics tree
        self.topics_tree = ttk.Treeview(topic_frame, show='tree', selectmode='browse')
        self.topics_tree.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        
        # Add context menu
        self.topic_context_menu = tk.Menu(self.root, tearoff=0)
        self.topic_context_menu.add_command(label="Новая подтема", command=self._add_subtopic_from_context)
        self.topic_context_menu.add_separator()
        self.topic_context_menu.add_command(label="Переименовать", command=self._rename_topic_from_context)
        self.topic_context_menu.add_command(label="Удалить", command=self._delete_topic_from_context)
        
        # Bind right-click event
        self.topics_tree.bind("<Button-3>", self._on_topic_right_click)
        self.topics_tree.bind("<Button-1>", self._on_topic_click)
        
        # Enable keyboard navigation
        self.topics_tree.bind("<Delete>", self._delete_topic_from_context)
        self.topics_tree.bind("<F2>", self._rename_topic_from_context)
        
        # Add scrollbar to topics tree
        topic_scroll = ttk.Scrollbar(topic_frame, orient='vertical', command=self.topics_tree.yview)
        topic_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.topics_tree.configure(yscrollcommand=topic_scroll.set)
        
        # Notes list
        notes_frame = ttk.Frame(main_frame, width=250, style='Sidebar.TFrame')
        notes_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        
        # Notes header with search
        notes_header = ttk.Frame(notes_frame)
        notes_header.pack(fill=tk.X, pady=(0, 5))
        
        ttk.Label(notes_header, text="Заметки", font=('Segoe UI', 10, 'bold')).pack(side=tk.LEFT, anchor='w')
        
        # Configure search button styles
        self.style.configure('Search.TButton',
                          font=('Segoe UI', 11),
                          padding=2,
                          width=2,
                          relief='flat',
                          borderwidth=0,
                          background='#f0f0f0',
                          foreground='#555555')
        
        self.style.map('Search.TButton',
                     background=[('active', '#e0e0e0'), ('!active', '#f0f0f0')],
                     foreground=[('active', '#333333'), ('!active', '#555555')],
                     relief=[('pressed', 'sunken'), ('!pressed', 'flat')])
        
        # Add search button with icon
        self.search_icon = '🔍'  # Magnifying glass emoji
        search_btn = ttk.Button(
            notes_header,
            text=self.search_icon,
            command=self.show_search_dialog,
            style='Search.TButton',
            width=3,
            padding=(0, 2)
        )
        search_btn.pack(side=tk.RIGHT, padx=(5, 0), pady=2)
        
        # Add tooltip
        self._create_tooltip(search_btn, "Поиск заметок (Ctrl+F)")
        
        # Make the button more touch-friendly on Windows
        if os.name == 'nt':
            search_btn.configure(padding=2)
        
        # New note button
        new_note_btn = ttk.Button(
            notes_header, 
            text="+", 
            width=3,
            command=self.create_new_note
        )
        new_note_btn.pack(side=tk.RIGHT)
        
        # Configure Treeview styles
        self.style.configure('Treeview', 
                           rowheight=25,
                           background='white',
                           fieldbackground='white',
                           foreground='black')
        self.style.configure('Treeview.Heading', 
                           font=('Segoe UI', 10),
                           background='#f0f0f0')
        self.style.map('Treeview', 
                      background=[('selected', '#0078d7')])
        
        # Notes list with delete button column
        self.notes_list = ttk.Treeview(
            notes_frame, 
            columns=('title', 'date', 'delete'), 
            show='tree headings',
            style='Treeview',
            selectmode='browse',
            height=15  # Fixed height to show multiple notes
        )
        self.notes_list.heading('#0', text='')
        self.notes_list.column('#0', width=0, stretch=tk.NO)
        self.notes_list.column('title', width=180, anchor='w')
        self.notes_list.column('date', width=50, anchor='e')
        self.notes_list.column('delete', width=20, anchor='center', stretch=False)
        
        # Configure tags for hover effect
        self.notes_list.tag_configure('hover', background='#f0f0f0')
        
        # Configure delete button style
        self.style.configure('Delete.TButton', 
                           font=('Arial', 10, 'bold'),
                           foreground='red',
                           padding=0,
                           width=2)
        
        self.notes_list.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        self.notes_list.bind('<<TreeviewSelect>>', self.on_note_selected)
        
        # Bind mouse enter/leave events for delete button hover
        self.notes_list.bind('<Motion>', self.on_notes_list_hover) 
        self.notes_list.bind('<Leave>', self.on_notes_list_leave)
        
        # Store the currently hovered item
        self.hovered_item = None
        
        # Bind keyboard shortcuts
        self.notes_list.bind('<Delete>', lambda e: self.delete_selected_note())
        self.notes_list.bind('<Control-d>', lambda e: self.delete_selected_note())
        
        # Bind click on delete button
        self.notes_list.bind('<Button-1>', self.on_notes_list_click)
        
        # Create context menu for notes list
        self.note_context_menu = tk.Menu(self.root, tearoff=0)
        self.note_context_menu.add_command(label="Удалить", command=self.delete_selected_note)
        self.notes_list.bind('<Button-3>', self.show_note_context_menu)
        
        # Main content area
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Note title
        self.title_var = tk.StringVar()
        self.title_entry = ttk.Entry(
            content_frame, 
            textvariable=self.title_var, 
            font=('Segoe UI', 16, 'bold')
        )
        self.title_entry.pack(fill=tk.X, pady=(0, 10))
        self.title_entry.bind('<KeyRelease>', self.on_title_changed)
        
        # Canvas for blocks with scrollbar
        self.canvas = tk.Canvas(content_frame, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(content_frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        
        # Add button with hover effect
        self.add_btn = ttk.Button(
            self.root, 
            text="+", 
            width=3, 
            command=lambda: self.add_new_block(BlockType.TEXT)
        )
        self.add_btn.place(relx=0.5, rely=0.95, anchor="center")
        
        # Controls frame (initially hidden)
        self.controls_frame = ttk.Frame(self.root)
        self.controls_frame.place(relx=0.5, rely=0.9, anchor="center")
        
        # Add block type buttons to controls frame
        ttk.Button(
            self.controls_frame, 
            text="Текст", 
            command=lambda: self.add_new_block(BlockType.TEXT)
        ).pack(side=tk.LEFT, padx=2)
        
        ttk.Button(
            self.controls_frame, 
            text="Заголовок", 
            command=lambda: self.add_new_block(BlockType.HEADING, level=1)
        ).pack(side=tk.LEFT, padx=2)
        
        ttk.Button(
            self.controls_frame, 
            text="Список", 
            command=lambda: self.add_new_block(BlockType.BULLET_LIST)
        ).pack(side=tk.LEFT, padx=2)
        
        ttk.Button(
            self.controls_frame, 
            text="Чеклист", 
            command=lambda: self.add_new_block(BlockType.CHECKLIST)
        ).pack(side=tk.LEFT, padx=2)
        
        # Add delete button style
        self.style.configure('Delete.TButton', 
                           background='#ffebee', 
                           foreground='#c62828',
                           font=('Segoe UI', 8, 'bold'))
        self.style.map('Delete.TButton',
                      background=[('active', '#ffcdd2'), ('!active', '#ffebee')],
                      foreground=[('active', '#b71c1c'), ('!active', '#c62828')])
        
        # Hide controls initially
        self.controls_frame.place_forget()

    def render_blocks(self):
        # Clear existing blocks
        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()
        
        # Render each block
        for block in self.blocks:
            if block.type == BlockType.TEXT:
                widget = self.block_renderer.render_text_block(self.scrollable_frame, block)
            elif block.type == BlockType.HEADING:
                widget = self.block_renderer.render_heading(self.scrollable_frame, block)
            elif block.type == BlockType.BULLET_LIST:
                widget = self.block_renderer.render_bullet_list(self.scrollable_frame, block)
            elif block.type == BlockType.NUMBERED_LIST:
                widget = self.block_renderer.render_numbered_list(self.scrollable_frame, block)
            elif block.type == BlockType.CHECKLIST:
                widget = self.block_renderer.render_checklist(self.scrollable_frame, block)
            elif block.type == BlockType.DIVIDER:
                widget = self.block_renderer.render_divider(self.scrollable_frame, block)
            
            if widget:
                # Store block ID for focus tracking
                widget.block_id = block.id
                widget.pack(fill=tk.X, pady=2, expand=True)
                
                # Bind click event to show controls
                widget.bind('<Button-1>', self.show_controls)
                widget.bind('<Button-3>', self.show_context_menu)
                
                # Make all children focusable
                for child in widget.winfo_children():
                    child.bind('<Button-1>', self.show_controls)
                    child.bind('<Button-3>', self.show_context_menu)
                    if hasattr(child, 'bind_all'):
                        child.bind_all('<Button-1>', self._on_click, add='+')
        
        # Update the canvas scroll region
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def add_new_block(self, block_type: BlockType = BlockType.TEXT, index: Optional[int] = None, level: int = 1):
        new_block = Block(type=block_type, level=level)
        if index is not None:
            self.blocks.insert(index, new_block)
        else:
            self.blocks.append(new_block)
        self.render_blocks()
        self.schedule_auto_save()
        
        # Scroll to the new block
        self.canvas.yview_moveto(1.0)

    def delete_block(self, block_id: str):
        self.blocks = [b for b in self.blocks if b.id != block_id]
        self.render_blocks()
        self.schedule_auto_save()

    def change_block_type(self, block_id: str, new_type: BlockType):
        for block in self.blocks:
            if block.id == block_id:
                block.type = new_type
                # Clear items if changing from a list type to non-list type
                if new_type not in [BlockType.BULLET_LIST, BlockType.NUMBERED_LIST, BlockType.CHECKLIST]:
                    block.items = []
                # Add default item if changing to a list type
                elif not block.items:
                    block.items = [BlockItem(content="")]
                break
        self.render_blocks()
        self.schedule_auto_save()

    # Topic management
    def load_topics(self):
        # Clear existing items
        for item in self.topics_tree.get_children():
            self.topics_tree.delete(item)
        
        # Load topics from database
        topics = self.db.get_topics_tree()
        
        # Add topics to tree
        def add_children(parent_id, topics_list):
            for topic in topics_list:
                item_id = self.topics_tree.insert(
                    parent=parent_id if parent_id else '',
                    index='end',
                    text=topic['name'],
                    values=(topic['id'],)
                )
                # Add children recursively
                if 'children' in topic and topic['children']:
                    add_children(item_id, topic['children'])
        
        add_children('', topics)
        
        # Expand all items
        for item in self.topics_tree.get_children():
            self.topics_tree.item(item, open=True)
            
        # Select first topic if available
        if self.topics_tree.get_children():
            self.topics_tree.selection_set(self.topics_tree.get_children()[0])
    
    def _on_topic_right_click(self, event):
        """Handle right-click on topic"""
        item = self.topics_tree.identify_row(event.y)
        if not item:
            return
            
        self.topics_tree.selection_set(item)
        self.topic_context_menu.post(event.x_root, event.y_root)
    
    def _on_topic_click(self, event):
        """Handle left-click on topic"""
        item = self.topics_tree.identify_row(event.y)
        if not item:
            return
            
        # If this is a double-click, rename the topic
        if event.num == 1 and event.time - getattr(self, '_last_click_time', 0) < 300:
            self._rename_topic_from_context()
        self._last_click_time = event.time
        
    def on_notes_list_hover(self, event):
        """Handle mouse hover over notes list to show delete button"""
        region = self.notes_list.identify_region(event.x, event.y)
        if region == 'cell':
            # Get the item and column under the cursor
            item = self.notes_list.identify_row(event.y)
            column = self.notes_list.identify_column(event.x)
            
            # If hovering over the delete column, change cursor and show delete button
            if column == '#3':  # Delete button column
                self.notes_list.configure(cursor='hand2')
                # Store the item ID for click handling
                self.hovered_item = item
            else:
                self.notes_list.configure(cursor='')
                self.hovered_item = None
    
    def on_notes_list_leave(self, event):
        """Handle mouse leaving notes list"""
        self.notes_list.configure(cursor='')
        self.hovered_item = None
        
    def show_note_context_menu(self, event):
        """Show context menu for a note in the listbox"""
        item = self.notes_list.identify_row(event.y)
        if not item:
            return
            
        self.notes_list.selection_set(item)
        self.note_context_menu.post(event.x_root, event.y_root)
    
    def _get_selected_topic(self):
        """Get the currently selected topic ID and name"""
        selection = self.topics_tree.selection()
        if not selection:
            return None, None
            
        item = selection[0]
        values = self.topics_tree.item(item, 'values')
        if not values:
            return None, None
            
        return values[0], self.topics_tree.item(item, 'text')
    
    def _add_subtopic_from_context(self, event=None):
        """Add a new subtopic to the selected topic"""
        parent_id, _ = self._get_selected_topic()
        self.add_topic(parent_id)
    
    def _rename_topic_from_context(self, event=None):
        """Rename the selected topic"""
        topic_id, current_name = self._get_selected_topic()
        if not topic_id:
            return
            
        new_name = RenameDialog.show(
            self.root,
            "Переименовать тему",
            "Введите новое название темы:",
            current_name
        )
        
        if new_name and new_name != current_name:
            try:
                with self.db._get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        'UPDATE topics SET name = ? WHERE id = ?',
                        (new_name, topic_id)
                    )
                    conn.commit()
                self.load_topics()
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось переименовать тему: {e}")
    
    def _delete_topic_from_context(self, event=None):
        """Delete the selected topic"""
        topic_id, topic_name = self._get_selected_topic()
        if not topic_id:
            return
            
        if messagebox.askyesno(
            "Подтверждение",
            f"Вы уверены, что хотите удалить тему \"{topic_name}\" и все подтемы?"
        ):
            try:
                with self.db._get_connection() as conn:
                    cursor = conn.cursor()
                    # First, delete all notes in this topic and its subtopics
                    cursor.execute('''
                        DELETE FROM notes 
                        WHERE topic_id IN (
                            WITH RECURSIVE subtopics(id) AS (
                                SELECT id FROM topics WHERE id = ?
                                UNION
                                SELECT t.id FROM topics t, subtopics s 
                                WHERE t.parent_id = s.id
                            )
                            SELECT id FROM subtopics
                        )
                    ''', (topic_id,))
                    
                    # Then delete the topics
                    cursor.execute('''
                        DELETE FROM topics 
                        WHERE id IN (
                            WITH RECURSIVE subtopics(id) AS (
                                SELECT id FROM topics WHERE id = ?
                                UNION
                                SELECT t.id FROM topics t, subtopics s 
                                WHERE t.parent_id = s.id
                            )
                            SELECT id FROM subtopics
                        )
                    ''', (topic_id,))
                    
                    conn.commit()
                
                self.load_topics()
                self.clear_editor()
                messagebox.showinfo("Готово", f"Тема \"{topic_name}\" и все подтемы удалены")
                
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось удалить тему: {e}")
    
    def add_topic_dialog(self, parent_id=None):
        name = simpledialog.askstring("Новая тема", "Введите название темы:")
        if name and name.strip():
            topic_id = self.db.create_topic(name.strip(), parent_id)
            self.load_topics()
            
            # Select the new topic
            for item in self.topics_tree.get_children():
                if self.topics_tree.item(item, 'values')[0] == topic_id:
                    self.topics_tree.selection_set(item)
                    self.topics_tree.see(item)
                    self.topics_tree.focus(item)
                    break
    
    def on_topic_selected(self, event):
        selected = self.topics_tree.selection()
        if selected:
            topic_id = self.topics_tree.item(selected[0])['values'][0]
            self.load_notes_for_topic(topic_id)
    
    def load_notes_for_topic(self, topic_id: int):
        # Clear existing notes
        for item in self.notes_list.get_children():
            self.notes_list.delete(item)
        
        # Store current topic ID
        self.current_topic_id = topic_id
        
        # Make sure the delete column is properly configured
        self.notes_list.column('delete', width=20, anchor='center', stretch=False)
        self.notes_list.heading('delete', text='')
        
        # Load notes for selected topic
        notes = self.db.load_notes(topic_id)
        
        # Store note IDs for reference
        self.note_ids = []
        
        # Add notes to list with delete buttons
        for note in notes:
            # Format the date
            try:
                updated_at = datetime.strptime(note['updated_at'], '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%y')
            except (ValueError, TypeError):
                updated_at = '--.--.--'
                
            # Insert the note
            item_id = self.notes_list.insert(
                '', 'end',
                values=(
                    note.get('title', 'Без названия'),
                    updated_at,
                    '×'  # Delete button
                ),
                text='',
                tags=(str(note['id']),)
            )
            
            # Store note ID for reference
            self.note_ids.append(note['id'])
            
            # Explicitly set the delete button
            self.notes_list.set(item_id, 'delete', '×')
            
            # Apply consistent styling
            self.notes_list.item(item_id, tags=(str(note['id']), 'note_item'))
            
        # Update status bar
        self.update_status_bar(f"Заметок: {len(notes)}")
        
        # If there are notes, select the first one
        if notes:
            first_note = self.notes_list.get_children()[0]
            self.notes_list.selection_set(first_note)
            self.notes_list.see(first_note)
    
    def on_note_selected(self, event):
        selected = self.notes_list.selection()
        if selected:
            note_id = int(self.notes_list.item(selected[0], 'tags')[0])
            self.load_note(note_id)
    
    def load_note(self, note_id: int):
        # Save current note if any
        self.save_current_note()
        
        # Load note data
        self.current_note_id = note_id
        self.blocks = self.db.load_note_blocks(note_id)
        
        # Update UI
        note = self.db.get_note_by_id(note_id)
        if note:
            self.title_var.set(note['title'])
        else:
            self.title_var.set('')
        
        # Render blocks
        self.render_blocks()
    
    def create_new_note(self):
        try:
            # Save current note if any
            self.save_current_note()
            
            # Create new note in database
            title = "Новая заметка"
            topic_id = None
            
            # Get selected topic if any
            if hasattr(self, 'topics_tree'):
                selected_topic = self.topics_tree.selection()
                if selected_topic:
                    try:
                        item_data = self.topics_tree.item(selected_topic[0])
                        if 'values' in item_data and item_data['values'] and len(item_data['values']) > 0:
                            topic_id = item_data['values'][0]
                    except Exception as e:
                        logger.error(f"Error getting selected topic: {str(e)}", exc_info=True)
            
            # Create the note in the database
            note_id = self.db.create_note(title, topic_id)
            if not note_id:
                raise Exception("Не удалось создать заметку в базе данных")
            
            # Update UI state
            self.current_note_id = note_id
            self.title_var.set(title)
            if hasattr(self, 'update_window_title'):
                self.update_window_title(title)
            
            # Clear existing blocks and add a default text block
            self.blocks = []
            if hasattr(self, 'add_new_block'):
                self.add_new_block(BlockType.TEXT)
            
            # Update notes list to show the new note
            if hasattr(self, 'load_notes_list'):
                self.load_notes_list()
            
            # Select the new note in the list if possible
            if hasattr(self, 'notes_list'):
                for item in self.notes_list.get_children():
                    item_tags = self.notes_list.item(item, 'tags')
                    if item_tags and len(item_tags) > 0 and int(item_tags[0]) == note_id:
                        self.notes_list.selection_set(item)
                        self.notes_list.see(item)
                        break
            
            # Set focus to the title field if it exists
            if hasattr(self, 'title_entry'):
                self.title_entry.focus_set()
            
            return True
            
        except Exception as e:
            error_msg = f"Не удалось создать новую заметку: {str(e)}"
            logger.error(error_msg, exc_info=True)
            messagebox.showerror("Ошибка", error_msg)
            return False
        self.notes_list.selection_set(self.notes_list.get_children()[-1])
    
    def save_current_note(self):
        if self.current_note_id is not None and hasattr(self, 'title_var'):
            title = self.title_var.get() or "Без названия"
            
            # Get current topic if any
            topic_id = None
            selected_topic = self.topics_tree.selection()
            if selected_topic:
                item_values = self.topics_tree.item(selected_topic[0], 'values')
                if item_values and len(item_values) > 0:
                    topic_id = item_values[0]
            
            # Create a Note object
            from models import Note
            note = Note(
                id=self.current_note_id,
                title=title,
                topic_id=topic_id,
                blocks=self.blocks,
                # These will be set by the database
                created_at=None,
                updated_at=None
            )
            
            # Save to database
            try:
                self.db.save_note(note)
                
                # Update notes list
                for item in self.notes_list.get_children():
                    if str(self.current_note_id) in self.notes_list.item(item, 'tags'):
                        self.notes_list.item(
                            item,
                            values=(title, 'Только что')
                        )
                        break
                        
            except Exception as e:
                logger.error(f"Error saving note: {e}", exc_info=True)
                messagebox.showerror("Ошибка", f"Не удалось сохранить заметку: {str(e)}")
    
    def close_current_note(self):
        if self.current_note_id is not None:
            self.save_current_note()
            self.current_note_id = None
            self.title_var.set("")
            self.blocks = []
            self.render_blocks()
    
    def on_title_changed(self, event):
        if self.current_note_id is not None:
            self.schedule_auto_save()
    
    def schedule_auto_save(self):
        # Cancel any pending auto-save
        if self.auto_save_id:
            self.root.after_cancel(self.auto_save_id)
        
        # Schedule new auto-save
        self.auto_save_id = self.root.after(30000, self.save_current_note)  # 30 seconds
    
    def setup_auto_save(self):
        # Auto-save every 5 minutes as a fallback
        self.root.after(300000, self.auto_save_loop)
    
    def auto_save_loop(self):
        self.save_current_note()
        # Schedule next auto-save
        self.root.after(300000, self.auto_save_loop)
    
    def show_search_dialog(self):
        query = simpledialog.askstring("Поиск заметок", "Введите поисковый запрос:")
        if query:
            results = self.db.search_notes(query)
            
            # Show results in a new window
            results_win = tk.Toplevel(self.root)
            results_win.title(f"Результаты поиска: {query}")
            results_win.geometry("600x400")
            
            # Results list
            tree = ttk.Treeview(
                results_win,
                columns=('title', 'date'),
                show='headings'
            )
            tree.heading('title', text='Название')
            tree.heading('date', text='Изменено')
            tree.column('title', width=400)
            tree.column('date', width=150)
            tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
            
            # Add results
            for note in results:
                tree.insert(
                    '', 'end',
                    values=(
                        note['title'],
                        datetime.strptime(note['updated_at'], '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y %H:%M')
                    ),
                    tags=(note['id'],)
                )
            
            # Double-click to open note
            def on_double_click(event):
                item = tree.identify('item', event.x, event.y)
                if item:
                    note_id = int(tree.item(item, 'tags')[0])
                    self.load_note(note_id)
                    results_win.destroy()
            
            tree.bind('<Double-1>', on_double_click)
    
    def on_closing(self):
        try:
            # Save current note if any exists
            if hasattr(self, 'current_note_id') and self.current_note_id is not None:
                self.save_current_note()
            
            # Cancel any pending auto-save
            if hasattr(self, 'auto_save_id') and self.auto_save_id is not None:
                self.root.after_cancel(self.auto_save_id)
            
            # Close the database connection
            if hasattr(self, 'db'):
                self.db.close()
                
        except Exception as e:
            logger.error(f"Error during application shutdown: {e}", exc_info=True)
            
        finally:
            # Make sure the application closes
            self.root.quit()  # Stop the Tcl interpreter
            self.root.destroy()  # Destroy all widgets

    def show_topic_context_menu(self, event):
        """Show context menu for a topic in the treeview"""
        # Get the clicked item
        item = self.topics_tree.identify_row(event.y)
        if not item:
            return
            
        # Select the clicked item
        self.topics_tree.selection_set(item)
        self.topics_tree.focus(item)
        
        # Get topic ID
        values = self.topics_tree.item(item, 'values')
        if not values or not values[0]:
            return  # Skip if no topic ID
            
        topic_id = values[0]
        topic_name = self.topics_tree.item(item, 'text').replace('📁 ', '').split(' (')[0]
        
        # Create the context menu
        menu = tk.Menu(self.root, tearoff=0)
        
        # Add menu items
        menu.add_command(
            label="Новая подтема",
            command=lambda: self.add_topic(parent_id=topic_id)
        )
        
        menu.add_command(
            label="Переименовать тему",
            command=lambda: self.rename_topic(topic_id, topic_name)
        )
        
        menu.add_command(
            label="Свойства",
            command=lambda: self.show_topic_properties(topic_id, topic_name)
        )
        
        menu.add_separator()
        
        menu.add_command(
            label="Удалить тему",
            command=lambda: self.delete_topic(topic_id, topic_name),
            foreground='red'
        )
        
        # Show the menu
        menu.tk.call('tk_popup', menu, event.x_root, event.y_root)

    def show_note_context_menu(self, event):
        """Show context menu for a note in the listbox"""
        # Get the clicked item
        index = self.notes_list.identify_row(event.y)
        if index < 0:
            return
            
        # Select the clicked item
        self.notes_list.selection_clear()
        self.notes_list.selection_set(index)
        self.notes_list.focus(index)
        
        # Get note ID and title
        if not hasattr(self, 'note_ids') or index >= len(self.note_ids):
            return
            
        note_id = self.note_ids[index]
        note_title = self.notes_list.item(index, 'values')[0].split(' [')[0]  # Remove topic from title
        
        # Create the context menu
        menu = tk.Menu(self.root, tearoff=0)
        
        # Add menu items
        menu.add_command(
            label="Переименовать заметку",
            command=lambda: self.rename_note(note_id, note_title)
        )
        
        menu.add_command(
            label="Переместить в другую тему",
            command=lambda: self.move_note_to_topic(note_id)
        )
        
        menu.add_command(
            label="Добавить теги",
            command=lambda: self.add_tags_to_note(note_id)
        )
        
        menu.add_separator()
        
        menu.add_command(
            label="Удалить заметку",
            command=lambda: self.delete_note_with_confirmation(note_id, note_title),
            foreground='red'
        )
        
        # Show the menu
        menu.tk_call('tk_popup', menu, event.x_root, event.y_root)

    def show_topic_properties(self, topic_id: int, topic_name: str) -> None:
        """Show topic properties dialog"""
        try:
            # Get topic details from database
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'SELECT created_at, updated_at FROM topics WHERE id = ?',
                    (topic_id,)
                )
                result = cursor.fetchone()
                
                if not result:
                    messagebox.showerror("Ошибка", "Тема не найдена")
                    return
                
                created_at, updated_at = result
                
                # Get note count
                note_count = self.db.get_notes_count_in_topic(topic_id)
                
                # Show properties dialog
                TopicPropertiesDialog(
                    self.root,
                    topic_name=topic_name,
                    notes_count=note_count,
                    created_at=created_at,
                    updated_at=updated_at
                )
                
        except Exception as e:
            logger.error(f"Error showing topic properties: {e}")
            messagebox.showerror("Ошибка", f"Не удалось отобразить свойства темы: {e}")

    def rename_topic(self, topic_id: int, current_name: str) -> None:
        """Rename a topic"""
        new_name = RenameDialog.show(
            self.root,
            "Переименовать тему",
            "Введите новое название темы:",
            current_name
        )
        
        if not new_name or new_name == current_name:
            return
            
        try:
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'UPDATE topics SET name = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                    (new_name.strip(), topic_id)
                )
                conn.commit()
                
                # Update the tree
                self.load_topics()
                
        except Exception as e:
            logger.error(f"Error renaming topic: {e}")
            messagebox.showerror("Ошибка", f"Не удалось переименовать тему: {e}")

    def delete_topic(self, topic_id: int, topic_name: str) -> None:
        """Delete a topic with confirmation"""
        # Get note count in this topic
        note_count = self.db.get_notes_count_in_topic(topic_id)
        
        # Show confirmation dialog
        action = ConfirmDeletionDialog.show(
            self.root,
            "Удаление темы",
            f"Удалить тему '{topic_name}'?",
            has_notes=note_count > 0
        )
        
        if not action:
            return  # User cancelled
            
        try:
            # Delete the topic
            delete_notes = (action == "delete")
            success = self.db.delete_topic(topic_id, delete_notes=delete_notes)
            
            if success:
                # Reload topics and notes
                self.load_topics()
                self.load_notes_list()
            else:
                messagebox.showwarning("Предупреждение", "Не удалось удалить тему")
                
        except Exception as e:
            logger.error(f"Error deleting topic: {e}")
            messagebox.showerror("Ошибка", f"Не удалось удалить тему: {e}")

    def delete_note_with_confirmation(self, note_id: int, note_title: str) -> None:
        """Show confirmation dialog before deleting a note"""
        # Show confirmation dialog
        if not ConfirmDeletionDialog.show(
            self.root,
            "Удаление заметки",
            f"Удалить заметку '{note_title}'?",
            has_notes=False
        ):
            return  # User cancelled
            
        try:
            # Delete the note
            success = self.db.delete_note(note_id)
            
            if success:
                # Reload notes list
                self.load_notes_list()
                
                # Clear the editor if the deleted note was open
                if hasattr(self, 'current_note_id') and self.current_note_id == note_id:
                    self.clear_editor()
            else:
                messagebox.showwarning("Предупреждение", "Не удалось удалить заметку")
                
        except Exception as e:
            logger.error(f"Error deleting note: {e}")
            messagebox.showerror("Ошибка", f"Не удалось удалить заметку: {e}")

    def rename_note(self, note_id: int, current_title: str) -> None:
        """Rename a note"""
        new_title = RenameDialog.show(
            self.root,
            "Переименовать заметку",
            "Введите новое название заметки:",
            current_title
        )
        
        if not new_title or new_title == current_title:
            return
            
        try:
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'UPDATE notes SET title = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                    (new_title.strip(), note_id)
                )
                conn.commit()
                
                # Update the notes list
                self.load_notes_list()
                
        except Exception as e:
            logger.error(f"Error renaming note: {e}")
            messagebox.showerror("Ошибка", f"Не удалось переименовать заметку: {e}")

    def move_note_to_topic(self, note_id: int) -> None:
        """Move a note to a different topic"""
        # Get current note
        note = self.db.get_note(note_id)
        if not note:
            messagebox.showerror("Ошибка", "Заметка не найдена")
            return
            
        # Show topic selection dialog
        from dialogs import TopicSelectionDialog
        topic_id = TopicSelectionDialog.show(
            self.root,
            "Выберите тему",
            self.db,
            current_topic_id=note.topic_id
        )
        
        if topic_id is None:
            return  # User cancelled
            
        try:
            # Update the note's topic
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'UPDATE notes SET topic_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                    (topic_id if topic_id != 0 else None, note_id)
                )
                conn.commit()
                
                # Update the notes list
                self.load_notes_list()
                
        except Exception as e:
            logger.error(f"Error moving note: {e}")
            messagebox.showerror("Ошибка", f"Не удалось переместить заметку: {e}")

    def delete_selected_note(self) -> None:
        """Delete the currently selected note"""
        if not hasattr(self, 'note_ids') or not self.note_ids:
            return
            
        # Get selected note
        selection = self.notes_list.selection()
        if not selection:
            return
            
        note_index = selection[0]
        if note_index >= len(self.note_ids):
            return
            
        note_id = self.note_ids[note_index]
        note_title = self.notes_list.item(selection[0], 'values')[0].split(' [')[0]  # Remove topic from title
        
        # Show confirmation and delete
        self.delete_note_with_confirmation(note_id, note_title)

    def update_window_title(self, title: str = None):
        """Update the window title with the current note's title.
        
        Args:
            title: Optional title to set. If None, uses the current title_var value.
        """
        if title is None:
            title = self.title_var.get()
        self.root.title(f"MindForge - {title}" if title else "MindForge")

    def clear_editor(self):
        # Clear all blocks
        self.blocks = []
        self.current_note_id = None
        self.title_var.set("")
        self.update_window_title("")
        self.render_blocks()

    def _setup_styles(self):
        """Configure custom styles for the application"""
        style = ttk.Style()
        
        # Configure Treeview
        style.configure("Treeview", 
                       font=('Segoe UI', 10), 
                       rowheight=25,
                       borderwidth=0,
                       relief='flat')
        
        style.configure("Treeview.Item", 
                       padding=(5, 2, 5, 2))
        
        style.map('Treeview',
                 background=[('selected', '#e1e1e1')],
                 foreground=[('selected', 'black')])
        
        # Configure buttons
        style.configure('Accent.TButton',
                      font=('Segoe UI', 9, 'bold'))
        
        style.configure('Danger.TButton',
                      font=('Segoe UI', 12, 'bold'),
                      foreground='#dc3545',
                      background='#f8f9fa',
                      borderwidth=0,
                      padding=0,
                      width=2)
        
        style.map('Danger.TButton',
                foreground=[('active', '#ffffff'), ('!active', '#dc3545')],
                background=[('active', '#dc3545'), ('!active', '#f8f9fa')])
        
        # Configure listbox
        style.configure('Listbox',
                      font=('Segoe UI', 10),
                      selectbackground='#e1e1e1',
                      selectforeground='black',
                      borderwidth=0,
                      highlightthickness=0)

    def load_topics(self):
        """Load topics into the treeview"""
        try:
            # Clear existing items
            for item in self.topics_tree.get_children():
                self.topics_tree.delete(item)
            
            # Add root node (always expanded)
            root_id = self.topics_tree.insert('', 'end', text='📁 Темы', open=True, tags=('root',))
            
            # Add topics from database
            topics = self.db.get_topics_tree()
            self._add_topics_to_tree(root_id, topics)
            
            # Add a default topic if no topics exist
            if not self.topics_tree.get_children():
                default_topic_id = self.db.create_topic("Личное")
                topics = self.db.get_topics_tree()
                self._add_topics_to_tree(root_id, topics)
            
            # Select the root node by default to show all notes
            self.topics_tree.selection_set(root_id)
            self.topics_tree.focus(root_id)
            
            # Update notes list
            self.load_notes_list()
                
        except Exception as e:
            logger.error(f"Error loading topics: {e}")
            messagebox.showerror("Ошибка", f"Не удалось загрузить темы: {e}")

    def add_topic(self, parent_id: Optional[int] = None) -> None:
        """Add a new topic (or subtopic if parent_id is provided)"""
        # Show dialog to get topic name
        topic_name = RenameDialog.show(
            self.root,
            "Новая тема",
            "Введите название темы:",
            ""
        )
        
        if not topic_name or not topic_name.strip():
            return
            
        try:
            # If parent_id is not provided, try to get the selected topic
            if parent_id is None:
                selected = self.topics_tree.selection()
                if selected:
                    item = selected[0]
                    values = self.topics_tree.item(item, 'values')
                    if values and values[0]:
                        parent_id = values[0]
            
            # Add the new topic to the database
            topic_id = self.db.create_topic(topic_name.strip(), parent_id)
            
            # Reload topics to update the tree
            self.load_topics()
            
            # Select the new topic
            self._select_topic_in_tree(topic_id)
            
        except Exception as e:
            logger.error(f"Error adding topic: {e}")
            messagebox.showerror("Ошибка", f"Не удалось добавить тему: {e}")

    def _select_topic_in_tree(self, topic_id: int) -> bool:
        """Select a topic in the treeview by ID"""
        for item in self.topics_tree.get_children():
            values = self.topics_tree.item(item, 'values')
            if values and values[0] == topic_id:
                self.topics_tree.selection_set(item)
                self.topics_tree.focus(item)
                return True
                
            # Check children recursively
            if self._select_topic_in_children(item, topic_id):
                return True
                
        return False
    
    def _select_topic_in_children(self, parent_item, topic_id: int) -> bool:
        """Recursively find and select a topic in the treeview"""
        for item in self.topics_tree.get_children(parent_item):
            values = self.topics_tree.item(item, 'values')
            if values and values[0] == topic_id:
                # Expand parent to make the item visible
                self.topics_tree.item(parent_item, open=True)
                self.topics_tree.selection_set(item)
                self.topics_tree.focus(item)
                return True
                
            # Check children
            if self._select_topic_in_children(item, topic_id):
                self.topics_tree.item(parent_item, open=True)
                return True
                
        return False

    def _add_topics_to_tree(self, parent_id, topics):
        """Add topics recursively to the treeview"""
        for topic in topics:
            topic_id = self.topics_tree.insert(
                parent_id,
                'end',
                text=topic['name'],
                values=(topic['id'],)
            )
            
            if topic.get('children'):
                self._add_topics_to_tree(topic_id, topic['children'])

    def on_topic_selected(self, event=None):
        """Handle topic selection in the treeview"""
        selected_items = self.topics_tree.selection()
        if not selected_items:
            return
            
        selected_item = selected_items[0]
        item_values = self.topics_tree.item(selected_item, 'values')
        
        # Check if root node is selected (show all notes)
        if 'root' in self.topics_tree.item(selected_item, 'tags'):
            self.current_topic_id = None
        elif item_values and item_values[0]:
            self.current_topic_id = item_values[0]
        else:
            self.current_topic_id = None
        
        self.load_notes_list()

    def load_notes_list(self):
        """Load notes for the selected topic into the listbox with delete buttons"""
        try:
            # Store current selection
            selected_note_id = None
            selection = self.notes_list.selection()
            if selection:
                selected_item = selection[0]
                if hasattr(self, 'note_ids') and self.notes_list.index(selected_item) < len(self.note_ids):
                    selected_note_id = self.note_ids[self.notes_list.index(selected_item)]
            
            # Clear existing items
            for item in self.notes_list.get_children():
                self.notes_list.delete(item)
            self.note_ids = []
            
            # Get notes for the selected topic (or all notes if no topic selected)
            notes = self.db.load_notes(self.current_topic_id)
            
            # Add notes to the listbox with topic indicator and delete button
            for note in notes:
                # Get topic name if exists
                topic_name = ""
                if note.get('topic_id'):
                    topic = self._get_topic_by_id(note['topic_id'])
                    if topic:
                        topic_name = f" [{topic['name']}]"
                
                # Add to listbox with note ID stored in tags
                item_id = self.notes_list.insert(
                    '', 'end', 
                    values=(f"{note['title']}{topic_name}", note['created_at']),
                    tags=(str(note['id']),)  # Store note ID in tags
                )
                
                # Store note ID for reference
                self.note_ids.append(note['id'])
                
                # Set delete button text in the delete column
                self.notes_list.set(item_id, 'delete', '×')  # Using × as delete button text
                
                # Restore selection if this was the selected note
                if selected_note_id == note['id']:
                    self.notes_list.selection_set(item_id)
            
            # Update status bar
            self.update_status_bar(f"Заметок: {len(notes)}")
            
        except Exception as e:
            logger.error(f"Error loading notes: {e}", exc_info=True)
            messagebox.showerror("Ошибка", f"Не удалось загрузить заметки: {e}")

    def _get_topic_by_id(self, topic_id: int) -> Optional[Dict]:
        """Get topic by ID from the treeview"""
        for item in self.topics_tree.get_children():
            values = self.topics_tree.item(item, 'values')
            if values and values[0] == topic_id:
                return {'id': values[0], 'name': self.topics_tree.item(item, 'text')}
            
            # Check children recursively
            child_topic = self._find_topic_in_children(item, topic_id)
            if child_topic:
                return child_topic
                
        return None
    
    def _find_topic_in_children(self, parent_item, topic_id: int) -> Optional[Dict]:
        """Recursively find a topic in the treeview"""
        for item in self.topics_tree.get_children(parent_item):
            values = self.topics_tree.item(item, 'values')
            if values and values[0] == topic_id:
                return {'id': values[0], 'name': self.topics_tree.item(item, 'text')}
                
            # Check children
            child_topic = self._find_topic_in_children(item, topic_id)
            if child_topic:
                return child_topic
                
        return None

def main():
    try:
        root = tk.Tk()
        
        # Configure the application style
        style = ttk.Style()
        style.theme_use("clam")  # Use a modern theme
        
        # Configure colors
        style.configure("TFrame", background="#ffffff")
        style.configure("TButton", padding=6)
        style.configure("TEntry", padding=5)
        
        # Set application icon if available
        try:
            root.iconbitmap("icon.ico")
        except:
            pass
        
        # Set minimum window size
        root.minsize(800, 500)
        
        # Center the window
        window_width = 1200
        window_height = 700
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        x = (screen_width // 2) - (window_width // 2)
        y = (screen_height // 2) - (window_height // 2)
        root.geometry(f'{window_width}x{window_height}+{x}+{y}')
        
        # Create and run the application
        app = NoteTakingApp(root)
        root.mainloop()
        
    except Exception as e:
        logger.critical(f"Fatal error: {str(e)}", exc_info=True)
        messagebox.showerror("Fatal Error", 
                          f"A fatal error occurred: {str(e)}\n\n"
                          "Check app_errors.log for more details.")
        if 'root' in locals():
            root.destroy()

if __name__ == "__main__":
    main()
