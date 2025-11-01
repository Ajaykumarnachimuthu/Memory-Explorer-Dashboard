import tkinter as tk
from tkinter import ttk, messagebox
import re

# --------------------- SEGMENT ALLOCATOR ---------------------
class SegmentAllocator:
    def __init__(self):
        self.segments = {
            "CS": {"base": 0x1000, "next_offset": 0x0000, "limit": 0x0FFF},
            "DS": {"base": 0x2000, "next_offset": 0x0000, "limit": 0x0FFF},
            "SS": {"base": 0x3000, "next_offset": 0x0000, "limit": 0x0FFF},
            "ES": {"base": 0x4000, "next_offset": 0x0000, "limit": 0x0FFF},
        }
        self.stack_pointer = 0xFFFE

    def allocate_byte(self, seg_name):
        seg_info = self.segments[seg_name]
        if seg_info["next_offset"] < seg_info["limit"]:
            off = seg_info["next_offset"]
            seg_info["next_offset"] += 1
            return seg_info["base"], off
        raise MemoryError(f"{seg_name} out of memory")

    def push_value(self, value):
        if self.stack_pointer - 1 >= (self.segments["SS"]["base"] << 4):
            self.stack_pointer -= 2
            return self.stack_pointer
        raise MemoryError("Stack overflow")

    def pop_value(self):
        if self.stack_pointer < (self.segments["SS"]["base"] << 4) + self.segments["SS"]["limit"]:
            old_sp = self.stack_pointer
            self.stack_pointer += 2
            return old_sp
        raise MemoryError("Stack underflow")

    def peek_next(self, seg_name):
        seg_info = self.segments[seg_name]
        if seg_info["next_offset"] < seg_info["limit"]:
            return seg_info["base"], seg_info["next_offset"]
        raise MemoryError(f"{seg_name} out of memory")

# --------------------- HELPERS ---------------------
def fmt_seg(seg): return f"{seg:04X}H"
def fmt_off(off): return f"{off:04X}H"
def fmt_phys(seg, off): return f"{(seg<<4)+off:05X}H"
def fmt_phys_calc(seg, off): return f"{(seg<<4)+off:05X}H = ({seg:04X}H × 10H) + {off:04X}H"

def classify_input(token: str) -> str:
    """FIXED SEGMENT CLASSIFICATION - NO OVERLAPS!"""
    token = token.upper()
    
    # 1. FIRST check ES (explicit segment references)
    if "ES:" in token or "DEST" in token or token.startswith("MOVS"):
        return "ES"   # Extra Segment
    
    # 2. THEN check Stack operations  
    stack_keywords = ["PUSH", "POP"]  # Only pure stack operations
    if token in stack_keywords:
        return "SS"   # Stack Segment
    
    # 3. THEN check Instructions
    code_keywords = ["MOV", "CALL", "JMP", "ADD", "SUB", "MUL", "DIV", "RET", "INC", "DEC"]
    if token in code_keywords:
        return "CS"   # Code Segment
    
    # 4. FINALLY Data (everything else)
    data_keywords = ["AX", "BX", "CX", "DX", "SI", "DI", "BP", "SP", "DATA", "WORD", "BYTE"]
    if token in data_keywords or token.isalpha() or token.isdigit():
        return "DS"   # Data Segment
    else:
        return "DS"   # Default to Data Segment

def parse_input_to_bytes(text):
    tokens = re.split(r"[,\s;]+", text.strip())
    bytes_out, cleaned_tokens = [], []
    for t in tokens:
        if not t: continue
        cleaned_tokens.append(t)
        
        # Handle string data
        if (t.startswith('"') and t.endswith('"')) or (t.startswith("'") and t.endswith("'")):
            bytes_out.extend(t[1:-1].encode('latin1'))
            continue
            
        # Handle numbers
        if re.fullmatch(r"0x[0-9A-Fa-f]+", t):
            v = int(t,16)
        elif re.fullmatch(r"[0-9A-Fa-f]+H", t, re.IGNORECASE):
            v = int(t[:-1],16)
        elif re.fullmatch(r"[0-9A-Fa-f]{1,2}", t):
            v = int(t,16)
        elif t.isdigit():
            v = int(t)
        else:
            bytes_out.extend(t.encode("latin1", errors="replace"))
            continue
            
        if v == 0:
            bytes_out.append(0)
        else:
            temp = []
            while v > 0:
                temp.append(v & 0xFF)
                v >>= 8
            bytes_out.extend(temp)
            
    return bytes_out, cleaned_tokens

# --------------------- DASHBOARD ---------------------
class MemoryDashboard:
    SEG_COLORS = {"CS":"#ff6b6b","DS":"#51cf66","SS":"#339af0","ES":"#b197fc"}

    def __init__(self, root):
        self.root = root
        root.title("8086 Memory Allocation Dashboard")
        root.configure(bg="#1a1a1a")
        root.state("zoomed")

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TLabel", background="#1a1a1a", foreground="white", font=("Consolas",11))
        style.configure("TButton", font=("Consolas",10,"bold"))

        self.allocator = SegmentAllocator()
        self.memory = {}
        self.step_queue = []
        self.current_byte_value = None
        self.current_alloc_info = None
        self.after_id = None
        self.auto_delay = 700
        self.registers = {"AX":0,"BX":0,"CX":0,"DX":0,"SP":0xFFFE}

        self.setup_gui()

    def setup_gui(self):
        # ----------------- TOP FRAME -----------------
        top_frame = ttk.Frame(self.root, padding=10)
        top_frame.pack(fill="x")
        
        # Changed title with black font and white background
        title_label = tk.Label(top_frame, text="8086 MEMORY ALLOCATION DASHBOARD", 
                 font=("Consolas", 14, "bold"), bg="white", fg="black")
        title_label.pack(side="top", anchor="w", pady=5, fill="x")

        # Input section
        input_frame = ttk.Frame(top_frame)
        input_frame.pack(fill="x", pady=5)
        
        ttk.Label(input_frame, text="Input:").pack(side="left")
        self.input_entry = ttk.Entry(input_frame, font=("Consolas", 12), width=60)
        self.input_entry.pack(side="left", fill="x", expand=True, padx=(10, 10))
        self.input_entry.insert(0, "PUSH AX; POP BX; ES:DATA; MOV CX; 1234; 'HELLO'")
        
        # Control buttons
        btn_frame = ttk.Frame(input_frame)
        btn_frame.pack(side="left")
        ttk.Button(btn_frame, text="Allocate (Auto Play)", command=self.allocate_auto).pack(side="left", padx=2)
        ttk.Button(btn_frame, text="Allocate (Step)", command=self.allocate_step_start).pack(side="left", padx=2)
        ttk.Button(btn_frame, text="Next Step", command=self.next_step).pack(side="left", padx=2)

        # Delay control
        ttk.Label(btn_frame, text="Delay:").pack(side="left", padx=(10, 2))
        self.delay_entry = ttk.Entry(btn_frame, width=5)
        self.delay_entry.insert(0, "700")
        self.delay_entry.pack(side="left", padx=2)

        # ----------------- STEP-BY-STEP LOG FRAME (MOVED UP) -----------------
        log_frame = tk.Frame(self.root, bg="#111")
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        tk.Label(log_frame, text="Step-by-step Execution Log", bg="#111", fg="white", 
                font=("Consolas", 12, "bold")).pack(anchor="nw")
        
        # Log text with scrollbar
        log_text_frame = tk.Frame(log_frame)
        log_text_frame.pack(fill="both", expand=True)
        
        self.log_text = tk.Text(log_text_frame, bg="#1e1e1e", fg="#e6e6e6", 
                               height=4, font=("Consolas", 10), wrap="none")  # Reduced height to 4 lines
        log_scrollbar = ttk.Scrollbar(log_text_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        
        self.log_text.pack(side="left", fill="both", expand=True)
        log_scrollbar.pack(side="right", fill="y")

        # ----------------- MIDDLE FRAME -----------------
        middle_frame = ttk.Frame(self.root)
        middle_frame.pack(fill="both", expand=True, padx=10, pady=5)

        # LEFT PANEL - Segments + Registers
        left_panel = tk.Frame(middle_frame, bg="#222", width=300)
        left_panel.pack(side="left", fill="y", padx=(0, 10))
        left_panel.pack_propagate(False)

        # Segment display
        tk.Label(left_panel, text="Segment Registers", bg="#222", fg="white", 
                font=("Consolas", 12, "bold")).pack(anchor="nw", pady=(10, 5))
        
        self.seg_labels = {}
        for seg in ["CS", "DS", "SS", "ES"]:
            frame = tk.Frame(left_panel, bg="#222")
            frame.pack(fill="x", pady=3)
            lbl = tk.Label(frame, text=f"{seg}: {fmt_off(0)}", bg=self.SEG_COLORS[seg], 
                          fg="black", font=("Consolas", 11, "bold"), width=20, anchor="w")
            lbl.pack(side="left", padx=(5, 0))
            self.seg_labels[seg] = lbl

        # Register display - ALIGNED PROPERLY
        tk.Label(left_panel, text="Registers", bg="#222", fg="white", 
                font=("Consolas", 12, "bold")).pack(anchor="nw", pady=(20, 5))
        
        self.reg_labels = {}
        reg_frame = tk.Frame(left_panel, bg="#222")
        reg_frame.pack(fill="x", padx=5)
        
        registers = [("AX", "BX"), ("CX", "DX"), ("SP", "")]
        for reg1, reg2 in registers:
            frame = tk.Frame(reg_frame, bg="#222")
            frame.pack(fill="x", pady=2)
            
            if reg1:
                lbl = tk.Label(frame, text=f"{reg1}: 0000H", bg="#333", fg="#00ff00", 
                              font=("Consolas", 11, "bold"), width=10, anchor="w")  # Increased width and made bold
                lbl.pack(side="left", padx=(0, 10), ipadx=5)  # Added internal padding
                self.reg_labels[reg1] = lbl
                
            if reg2:
                lbl = tk.Label(frame, text=f"{reg2}: 0000H", bg="#333", fg="#00ff00", 
                              font=("Consolas", 11, "bold"), width=10, anchor="w")  # Increased width and made bold
                lbl.pack(side="left", ipadx=5)  # Added internal padding
                self.reg_labels[reg2] = lbl

        # RIGHT PANEL - Memory Map
        right_panel = tk.Frame(middle_frame, bg="#111")
        right_panel.pack(side="left", fill="both", expand=True)
        
        tk.Label(right_panel, text="Memory Map (All Segments)", bg="#111", fg="white", 
                font=("Consolas", 12, "bold")).pack(anchor="nw", pady=(0, 5))
        
        # Memory treeview
        tree_frame = tk.Frame(right_panel)
        tree_frame.pack(fill="both", expand=True)
        
        cols = ("Segment:Offset", "Physical", "Value", "Segment")
        self.tree = ttk.Treeview(tree_frame, columns=cols, show="headings", height=15)
        
        self.tree.heading("Segment:Offset", text="Segment:Offset")
        self.tree.heading("Physical", text="Physical Address") 
        self.tree.heading("Value", text="Value")
        self.tree.heading("Segment", text="Segment")
        
        self.tree.column("Segment:Offset", width=120)
        self.tree.column("Physical", width=100)
        self.tree.column("Value", width=80)
        self.tree.column("Segment", width=70)
        
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # ----------------- BOTTOM FRAME -----------------
        bottom_frame = ttk.Frame(self.root, padding=5)
        bottom_frame.pack(fill="x")
        
        ttk.Button(bottom_frame, text="Clear Log", command=self.clear_log).pack(side="left", padx=5)
        ttk.Button(bottom_frame, text="Reset Memory", command=self.reset_memory).pack(side="left", padx=5)
        
        self.status_label = ttk.Label(bottom_frame, text="Ready - All segments working!", foreground="yellow", 
                                     font=("Consolas", 10))
        self.status_label.pack(side="right")

        self.update_display()

    def log(self, text):
        self.log_text.config(state="normal")
        self.log_text.insert("end", text + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def clear_log(self):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")

    def update_display(self):
        # Update segment offsets
        for seg in self.seg_labels:
            try:
                base, next_off = self.allocator.peek_next(seg)
                self.seg_labels[seg].config(text=f"{seg}: {fmt_off(next_off)}")
            except:
                self.seg_labels[seg].config(text=f"{seg}: FULL")
        
        # Update registers
        for reg in self.registers:
            self.reg_labels[reg].config(text=f"{reg}: {self.registers[reg]:04X}H")

    def prepare_allocation(self, bytes_list, tokens):
        self.step_queue.clear()
        for i, (b, tok) in enumerate(zip(bytes_list, tokens)):
            seg_name = classify_input(tok)

            def make_steps(byte_value, index, token, seg_name):
                steps = []
                
                def step_select_segment():
                    base, off = self.allocator.peek_next(seg_name)
                    self.current_byte_value = byte_value
                    self.current_alloc_info = (seg_name, base, off)
                    self.log(f"[Byte {index+1}] Input '{token}' classified → {seg_name}")
                    self.log(f"    {seg_name} = {fmt_seg(base)}")
                    self.update_display()

                def step_show_offset():
                    seg_name, base, off = self.current_alloc_info
                    self.log(f"[Byte {index+1}] Next free offset in {seg_name} = {fmt_off(off)}")

                def step_calc_physical():
                    seg_name, base, off = self.current_alloc_info
                    self.log(f"[Byte {index+1}] Physical Address = {fmt_phys_calc(base, off)}")

                def step_write():
                    seg_name, base, off = self.current_alloc_info
                    phys = (base << 4) + off
                    self.memory[phys] = self.current_byte_value
                    self.allocator.allocate_byte(seg_name)
                    
                    # Handle special operations
                    description = ""
                    if token.upper() == "PUSH" and seg_name == "SS":
                        self.registers["AX"] = 0x1234
                        description = "PUSH AX data"
                        self.log(f"    → Register: AX = 1234H")
                    elif token.upper() == "POP" and seg_name == "SS":
                        try:
                            pop_addr = self.allocator.pop_value()
                            self.registers["BX"] = 0x1234
                            description = "POP BX"
                            self.log(f"    → Stack: Popped value 1234H from SS:{pop_addr:04X}H to BX")
                            self.log(f"    → Stack Pointer: SP = {self.allocator.stack_pointer:04X}H")
                        except MemoryError as e:
                            self.log(f"    → ERROR: {e}")
                    
                    self.tree.insert("", 0, values=(
                        f"{fmt_seg(base)}:{fmt_off(off)}",
                        fmt_phys(base, off),
                        f"{self.current_byte_value:02X}H",
                        seg_name
                    ))
                    self.log(f"[Byte {index+1}] Written {self.current_byte_value:02X}H at {seg_name} {fmt_seg(base)}:{fmt_off(off)}")
                    self.update_display()

                steps.extend([step_select_segment, step_show_offset, step_calc_physical, step_write])
                return steps

            self.step_queue.extend(make_steps(b, i, tok, seg_name))

        self.log(f"Prepared {len(bytes_list)} byte(s) for allocation ({len(self.step_queue)} steps)")

    def allocate_auto(self):
        try:
            self.auto_delay = max(50, int(self.delay_entry.get()))
        except:
            self.auto_delay = 700
            
        txt = self.input_entry.get()
        bytes_list, tokens = parse_input_to_bytes(txt)
        if not bytes_list:
            messagebox.showwarning("Input", "Please enter valid data to allocate.")
            return
            
        self.prepare_allocation(bytes_list, tokens)
        self.log("Starting automatic allocation...")
        self.run_auto_steps()

    def run_auto_steps(self):
        if not self.step_queue:
            self.log("Allocation complete.")
            return
        func = self.step_queue.pop(0)
        func()
        self.after_id = self.root.after(self.auto_delay, self.run_auto_steps)

    def allocate_step_start(self):
        txt = self.input_entry.get()
        bytes_list, tokens = parse_input_to_bytes(txt)
        if not bytes_list:
            messagebox.showwarning("Input", "Please enter valid data to allocate.")
            return
            
        self.prepare_allocation(bytes_list, tokens)
        self.log("Prepared allocation. Use 'Next Step' to proceed step-by-step.")

    def next_step(self):
        if self.after_id:
            self.root.after_cancel(self.after_id)
            self.after_id = None
            
        if not self.step_queue:
            self.log("No more steps. Allocation finished or nothing prepared.")
            return
            
        func = self.step_queue.pop(0)
        func()

    def reset_memory(self):
        if messagebox.askyesno("Reset", "Clear simulated memory and allocator?"):
            self.memory.clear()
            self.allocator = SegmentAllocator()
            self.registers = {"AX": 0, "BX": 0, "CX": 0, "DX": 0, "SP": 0xFFFE}
            for i in self.tree.get_children():
                self.tree.delete(i)
            self.clear_log()
            self.log("Memory and allocator reset")
            self.update_display()

# ----------------- RUN -----------------
if __name__ == "__main__":
    root = tk.Tk()
    app = MemoryDashboard(root)
    root.mainloop()
    