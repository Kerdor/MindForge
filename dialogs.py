import tkinter as tk
from tkinter import ttk, messagebox
from typing import Optional, Callable, Any

class ConfirmDeletionDialog(tk.Toplevel):
    """Dialog for confirming deletion with options"""
    
    def __init__(self, parent, title: str, message: str, has_notes: bool = False):
        super().__init__(parent)
        self.title(title)
        self.parent = parent
        self.result = None
        
        # Center the dialog
        self.transient(parent)
        self.grab_set()
        
        # Configure window
        self.resizable(False, False)
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        
        # Create UI
        self._create_widgets(message, has_notes)
        
        # Center the dialog
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'+{x}+{y}')
    
    def _create_widgets(self, message: str, has_notes: bool):
        # Message
        msg_frame = ttk.Frame(self, padding=10)
        msg_frame.pack(fill=tk.X, padx=10, pady=(10, 0))
        
        icon = ttk.Label(msg_frame, text="⚠", font=('Arial', 16), foreground='orange')
        icon.pack(side=tk.LEFT, padx=(0, 10))
        
        msg = ttk.Label(msg_frame, text=message, wraplength=300, justify=tk.LEFT)
        msg.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Options frame
        if has_notes:
            options_frame = ttk.LabelFrame(self, text="Действие с заметками", padding=10)
            options_frame.pack(fill=tk.X, padx=10, pady=10)
            
            self.action = tk.StringVar(value="delete")
            
            ttk.Radiobutton(
                options_frame, 
                text="Удалить тему с заметками",
                variable=self.action,
                value="delete"
            ).pack(anchor=tk.W, pady=2)
            
            ttk.Radiobutton(
                options_frame,
                text="Переместить заметки в корень",
                variable=self.action,
                value="move"
            ).pack(anchor=tk.W, pady=2)
        
        # Buttons
        btn_frame = ttk.Frame(self, padding=10)
        btn_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        self.dont_ask = tk.BooleanVar(value=False)
        if not has_notes:  # Only show for simple confirmations
            ttk.Checkbutton(
                btn_frame, 
                text="Больше не спрашивать",
                variable=self.dont_ask
            ).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(
            btn_frame, 
            text="Отмена", 
            command=self._on_cancel
        ).pack(side=tk.RIGHT, padx=5)
        
        if has_notes:
            btn_text = "Подтвердить"
        else:
            btn_text = "Удалить"
            
        ttk.Button(
            btn_frame, 
            text=btn_text,
            style="Accent.TButton" if has_notes else "Danger.TButton",
            command=self._on_confirm
        ).pack(side=tk.RIGHT, padx=5)
    
    def _on_confirm(self):
        if hasattr(self, 'action'):
            self.result = self.action.get()
        else:
            self.result = "delete"
        self.destroy()
    
    def _on_cancel(self):
        self.result = None
        self.destroy()
    
    @staticmethod
    def show(parent, title: str, message: str, has_notes: bool = False) -> Optional[str]:
        """Show the dialog and return the user's choice"""
        dialog = ConfirmDeletionDialog(parent, title, message, has_notes)
        parent.wait_window(dialog)
        return dialog.result


class TopicPropertiesDialog(tk.Toplevel):
    """Dialog showing topic properties"""
    
    def __init__(self, parent, topic_name: str, notes_count: int, created_at: str, updated_at: str):
        super().__init__(parent)
        self.title(f"Свойства: {topic_name}")
        
        # Configure window
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)
        
        # Create UI
        self._create_widgets(topic_name, notes_count, created_at, updated_at)
        
        # Center the dialog
        self.update_idletasks()
        width = 350
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')
    
    def _create_widgets(self, topic_name: str, notes_count: int, created_at: str, updated_at: str):
        # Main frame
        main_frame = ttk.Frame(self, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Topic info
        ttk.Label(main_frame, text=f"Название:", font=('TkDefaultFont', 10, 'bold')).grid(row=0, column=0, sticky=tk.W, pady=(0, 5))
        ttk.Label(main_frame, text=topic_name).grid(row=0, column=1, sticky=tk.W, pady=(0, 5), padx=5)
        
        ttk.Label(main_frame, text="Количество заметок:", font=('TkDefaultFont', 10, 'bold')).grid(row=1, column=0, sticky=tk.W, pady=(0, 5))
        ttk.Label(main_frame, text=str(notes_count)).grid(row=1, column=1, sticky=tk.W, pady=(0, 5), padx=5)
        
        ttk.Label(main_frame, text="Создано:", font=('TkDefaultFont', 10, 'bold')).grid(row=2, column=0, sticky=tk.W, pady=(0, 5))
        ttk.Label(main_frame, text=created_at).grid(row=2, column=1, sticky=tk.W, pady=(0, 5), padx=5)
        
        ttk.Label(main_frame, text="Изменено:", font=('TkDefaultFont', 10, 'bold')).grid(row=3, column=0, sticky=tk.W, pady=(0, 10))
        ttk.Label(main_frame, text=updated_at).grid(row=3, column=1, sticky=tk.W, pady=(0, 10), padx=5)
        
        # Close button
        btn_frame = ttk.Frame(main_frame)
        btn_frame.grid(row=4, column=0, columnspan=2, pady=(10, 0))
        
        ttk.Button(btn_frame, text="Закрыть", command=self.destroy).pack()


class RenameDialog(tk.Toplevel):
    """Dialog for renaming items"""
    
    def __init__(self, parent, title: str, label: str, initial_value: str = ""):
        super().__init__(parent)
        self.title(title)
        self.result = None
        
        # Configure window
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)
        
        # Create UI
        self._create_widgets(label, initial_value)
        
        # Center the dialog
        self.update_idletasks()
        width = 350
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')
        
        # Set focus to entry
        self.entry.focus_set()
        self.entry.select_range(0, tk.END)
    
    def _create_widgets(self, label: str, initial_value: str):
        main_frame = ttk.Frame(self, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Label and entry
        ttk.Label(main_frame, text=label).pack(anchor=tk.W, pady=(0, 10))
        
        self.entry = ttk.Entry(main_frame, width=40)
        self.entry.pack(fill=tk.X, pady=(0, 15))
        self.entry.insert(0, initial_value)
        
        # Buttons
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(fill=tk.X, pady=(5, 0))
        
        ttk.Button(
            btn_frame, 
            text="Отмена", 
            command=self._on_cancel
        ).pack(side=tk.RIGHT, padx=5)
        
        self.confirm_btn = ttk.Button(
            btn_frame, 
            text="Сохранить",
            command=self._on_confirm,
            style="Accent.TButton"
        )
        self.confirm_btn.pack(side=tk.RIGHT)
        
        # Bind Enter key to confirm
        self.entry.bind('<Return>', lambda e: self._on_confirm())
        
        # Disable confirm button if entry is empty
        self.entry.bind('<KeyRelease>', self._validate_input)
        self._validate_input()
    
    def _validate_input(self, event=None):
        if self.entry.get().strip():
            self.confirm_btn.state(['!disabled'])
        else:
            self.confirm_btn.state(['disabled'])
    
    def _on_confirm(self):
        self.result = self.entry.get().strip()
        if self.result:
            self.destroy()
    
    def _on_cancel(self):
        self.result = None
        self.destroy()
    
    @staticmethod
    def show(parent, title: str, label: str, initial_value: str = "") -> Optional[str]:
        """Show the dialog and return the new name or None if cancelled"""
        dialog = RenameDialog(parent, title, label, initial_value)
        parent.wait_window(dialog)
        return dialog.result
